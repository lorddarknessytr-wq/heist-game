"""
build_lobby.py  -  Procedural cargo-ship-deck LOBBY  ->  lobby.glb
Blender 4.2+ (headless):
  blender -b --factory-startup --python tools/build_lobby.py -- --out out/lobby.glb

Authoring space = Three.js space (x right, y up, z toward camera).
P(...) converts to Blender space; the glTF exporter converts back (Y-up),
so positions in the GLB equal the numbers written here.
Everything is merged PER MATERIAL  ->  draw calls == number of materials.
Lights / fog / rain / light-shafts are NOT in the GLB (see lobby.meta.json).
"""
import bpy, bmesh, math, random, json, sys, os
import numpy as np
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = argv[argv.index('--out') + 1] if '--out' in argv else 'out/lobby.glb'
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ----------------------------------------------------------------- helpers
CONV = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))  # (x,y,z)->(x,-z,y)

def P(x=0.0, y=0.0, z=0.0, yaw=0.0):
    """local Three-style coords -> Blender world. yaw = rotation about Three Y (deg)."""
    return Matrix.Translation((x, -z, y)) @ Matrix.Rotation(math.radians(yaw), 4, 'Z') @ CONV

I = P()

def hexc(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

def lin(c):
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)

# ----------------------------------------------------------------- textures (numpy, seamless)
def fnoise(n, beta, seed):
    rng = np.random.default_rng(seed)
    s = np.fft.fft2(rng.standard_normal((n, n)))
    k = np.fft.fftfreq(n)
    kk = np.hypot(*np.meshgrid(k, k))
    kk[0, 0] = 1
    a = np.real(np.fft.ifft2(s / kk ** (beta / 2)))
    a -= a.mean()
    a /= (np.abs(a).max() + 1e-9)
    return a * 0.5 + 0.5

def sstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)

def mixc(img, col, m):
    return img * (1 - m[..., None]) + np.array(col) * m[..., None]

def streaks(n, seed):
    col = sstep(fnoise(n, 2.0, seed)[0:1, :], 0.45, 0.85)       # constant along v -> vertical streaks
    return col * (0.3 + 0.7 * fnoise(n, 3.0, seed + 1))

def scratches(img, n, seed, count=60, tint=0.25):
    rng = np.random.default_rng(seed)
    for _ in range(count):
        x, y = rng.integers(0, n, 2)
        a = rng.uniform(0, 6.28)
        for t in range(int(rng.integers(8, 40))):
            px, py = int(x + math.cos(a) * t) % n, int(y + math.sin(a) * t) % n
            img[py, px] = img[py, px] * (1 - tint) + tint * 0.85
    return img

def to_image(name, img):
    n = img.shape[0]
    rgba = np.ones((n, n, 4), dtype=np.float32)
    rgba[..., :3] = np.clip(img, 0, 1)
    im = bpy.data.images.new(name, n, n, alpha=False)
    im.pixels.foreach_set(rgba.ravel())
    im.update()
    im.colorspace_settings.name = 'sRGB'
    try:
        im.pack()
    except Exception as e:
        print('pack warning', e)
    return im

def tex_paint(name, hexcol, n=512, seed=1, rust=0.5, streak=True, grain=0.16):
    img = np.ones((n, n, 3)) * np.array(hexc(hexcol))
    img *= (1 + (fnoise(n, 2.2, seed) - 0.5) * grain * 2)[..., None]
    img *= (1 + (fnoise(n, 1.2, seed + 7) - 0.5) * 0.12)[..., None]
    m = sstep(fnoise(n, 3.0, seed + 2), 0.55, 0.8) * (streaks(n, seed + 3) if streak else 1) * rust
    img = mixc(img, (0.36, 0.17, 0.08), np.clip(m * 1.6, 0, 1))
    img = mixc(img, (0.05, 0.05, 0.05), sstep(fnoise(n, 2.5, seed + 4), 0.6, 0.9) * 0.35)
    return to_image(name, scratches(img, n, seed + 5))

def tex_deck(n=512):
    a, b = np.array(hexc('#2f5a52')), np.array(hexc('#3d6f63'))
    m = sstep(fnoise(n, 2.6, 11), 0.4, 0.62)[..., None]
    img = a * (1 - m) + b * m
    img *= (1 + (fnoise(n, 1.4, 12) - 0.5) * 0.25)[..., None]
    img = mixc(img, (0.30, 0.16, 0.09), sstep(fnoise(n, 3.0, 13), 0.62, 0.85) * 0.8)
    img *= (1 - 0.25 * sstep(fnoise(n, 2.0, 14), 0.5, 0.8))[..., None]
    return to_image('deck', scratches(img, n, 15, 90, 0.15))

def tex_frame(n=256):
    img = np.ones((n, n, 3)) * np.array(hexc('#20252b'))
    img *= (1 + (fnoise(n, 2.0, 21) - 0.5) * 0.4)[..., None]
    img = mixc(img, (0.30, 0.15, 0.08), sstep(fnoise(n, 3.0, 22), 0.62, 0.85) * 0.7)
    return to_image('frame', scratches(img, n, 23, 40))

def tex_alu(n=256):
    img = np.ones((n, n, 3)) * np.array(hexc('#c9ccce'))
    img *= (1 + (fnoise(n, 1.0, 31)[:, 0:1] - 0.5) * 0.14)[..., None]
    img *= (1 - 0.25 * sstep(fnoise(n, 2.6, 32), 0.55, 0.85))[..., None]
    return to_image('alu', scratches(img, n, 33, 70, 0.3))

def tex_worn(n=256):
    img = np.ones((n, n, 3)) * np.array(hexc('#cdc2a0'))
    img *= (1 + (fnoise(n, 2.0, 41) - 0.5) * 0.2)[..., None]
    img = mixc(img, (0.07, 0.065, 0.05), sstep(fnoise(n, 2.4, 42), 0.54, 0.58) * 0.95)
    return to_image('worn', scratches(img, n, 43, 50))

def tex_drum(n=256):
    img = np.ones((n, n, 3)) * np.array(hexc('#b9b8b0'))
    img *= (1 + (fnoise(n, 2.2, 51) - 0.5) * 0.2)[..., None]
    img = mixc(img, (0.12, 0.11, 0.1), streaks(n, 52) * 0.5)
    for v in (0.14, 0.5, 0.86):
        r = int(v * n)
        img[r - 3:r + 3] *= 0.7
    img[:8] = mixc(img[:8], (0.3, 0.15, 0.08), np.full((8, n), 0.6))
    img[-8:] = mixc(img[-8:], (0.3, 0.15, 0.08), np.full((8, n), 0.6))
    return to_image('drum', scratches(img, n, 53, 40))

def tex_emblem(n=128):
    y, x = np.mgrid[0:n, 0:n]
    x = (x + .5) / n * 2 - 1
    y = (y + .5) / n * 2 - 1
    r = np.hypot(x, y)
    img = np.ones((n, n, 3)) * np.array(hexc('#17191b'))
    ring = (r > 0.86) & (r < 0.95)
    globe = (r < 0.36) & ((abs(r - 0.36) < 0.04) | (abs(x) < 0.03) | (abs(y) < 0.03) | (abs(r - 0.2) < 0.025))
    ax = abs(x)
    wing = (ax > 0.3) & (ax < 0.82) & (y > -0.05 - 0.5 * (ax - 0.3)) & (y < 0.35 - 0.55 * (ax - 0.3))
    img[ring | globe | wing] = hexc('#cfcfc6')
    return to_image('emblem', img)

def tex_stickers(n=128):
    img = np.ones((n, n, 3)); h = n // 2
    img[:h, :h] = (.9, .9, .88); img[:h, h:] = (.85, .68, .1)
    img[h:, :h] = (.65, .12, .1); img[h:, h:] = (.1, .45, .25)
    d = np.arange(h)[8:-8]
    img[d, d] = (.05, .05, .05); img[d, (h - 1 - np.arange(h))[8:-8]] = (.05, .05, .05)
    img[10:h - 10, h + 10:h + 16] = (.05, .05, .05); img[10:h - 10, h + 26:h + 32] = (.05, .05, .05)
    img[h + 20:n - 20, h + 20:n - 20] = (.9, .9, .9)
    return to_image('stickers', img)

# ----------------------------------------------------------------- material library
def mat(name, color=None, tex=None, rough=0.5, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    b.inputs['Metallic'].default_value = metal
    b.inputs['Roughness'].default_value = rough
    if tex:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = tex
        nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    else:
        b.inputs['Base Color'].default_value = (*lin(hexc(color)), 1)
    return m

def create_material_library():
    return {
        'deck':      mat('WetDeckMetal', tex=tex_deck(), rough=0.30, metal=0.35),
        'stripe':    mat('DeckStripe', '#10151d', rough=0.28, metal=0.2),
        'yellow':    mat('DeckYellow', '#b08a1e', rough=0.40, metal=0.1),
        'frame':     mat('DarkFrameSteel', tex=tex_frame(), rough=0.55, metal=0.7),
        'c_blue':    mat('CorrugatedBlue', tex=tex_paint('c_blue', '#2d4e7a', seed=100), rough=0.62, metal=0.4),
        'c_blue2':   mat('CorrugatedBlue2', tex=tex_paint('c_blue2', '#33547f', seed=110), rough=0.60, metal=0.4),
        'c_red':     mat('CorrugatedRust', tex=tex_paint('c_red', '#7a3f33', seed=120, rust=0.8), rough=0.65, metal=0.4),
        'c_green':   mat('CorrugatedGreen', tex=tex_paint('c_green', '#2f4a50', seed=130), rough=0.60, metal=0.4),
        't_rohan':   mat('TextRohan', '#3b6192', rough=0.6, metal=0.2),
        't_white':   mat('TextWhite', '#d8dde0', rough=0.6, metal=0.1),
        'lbl_yellow': mat('LabelYellow', '#d9b21e', rough=0.5),
        'lbl_text':  mat('LabelText', '#15130a', rough=0.6),
        'lbl_red':   mat('LabelRed', '#a3231d', rough=0.5),
        'drum':      mat('DirtyDrum', tex=tex_drum(), rough=0.55, metal=0.5),
        'emblem':    mat('Emblem', tex=tex_emblem(), rough=0.6),
        'plasticB':  mat('PlasticBlue', tex=tex_paint('plasticB', '#1f6fb5', 256, 200, 0.0, False, 0.1), rough=0.6),
        'plasticW':  mat('PlasticWhite', tex=tex_paint('plasticW', '#e8e8e8', 256, 210, 0.0, False, 0.08), rough=0.6),
        'alu':       mat('BrushedAluminumCase', tex=tex_alu(), rough=0.35, metal=0.8),
        'stickers':  mat('Stickers', tex=tex_stickers(), rough=0.5),
        'worn':      mat('WornCrate', tex=tex_worn(), rough=0.7, metal=0.1),
        'mast':      mat('MastOrange', '#a8482a', rough=0.6, metal=0.5),
        'crane':     mat('CraneRust', '#5a3523', rough=0.7, metal=0.4),
        'pipe':      mat('PipeGrey', '#6a6e72', rough=0.5, metal=0.6),
        'hull':      mat('HullRed', '#6b3b30', rough=0.75, metal=0.3),
        'helmet':    mat('HelmetWhite', '#e8e8e6', rough=0.45),
        'sea':       mat('Sea', '#27323b', rough=0.35, metal=0.2),
    }

# ----------------------------------------------------------------- geometry (merged per material)
BM = {}
FOOT = []   # ground footprints (xmin,xmax,zmin,zmax) so lashing plates avoid objects

def bm_for(k):
    if k not in BM:
        b = bmesh.new()
        b.loops.layers.uv.new('UVMap')
        BM[k] = b
    return BM[k]

def box_uv(s):
    tab = [(2, 1), (0, 2), (0, 1)]
    def f(p, n):
        ax = max(range(3), key=lambda i: abs(n[i]))
        a, b = tab[ax]
        return (p[a] * s, p[b] * s)
    return f

def emit(key, M, verts, faces, uvf=None, smooth=False, uvx=None):
    bm = bm_for(key)
    uvl = bm.loops.layers.uv.active
    vs = [bm.verts.new(M @ Vector(v)) for v in verts]
    for k, fi in enumerate(faces):
        try:
            f = bm.faces.new([vs[i] for i in fi])
        except ValueError:
            continue
        f.smooth = smooth
        if uvx is not None:
            for l, uv in zip(f.loops, uvx[k]):
                l[uvl].uv = uv
        elif uvf:
            a, b, c = [Vector(verts[i]) for i in fi[:3]]
            n = (b - a).cross(c - a)
            n = n.normalized() if n.length > 1e-12 else Vector((0, 1, 0))
            for l, i in zip(f.loops, fi):
                l[uvl].uv = uvf(Vector(verts[i]), n)

BF = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (3, 0, 4, 7), (1, 2, 6, 5)]

def box(key, M, c, s, uvs=0.4):
    hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
    v = [(c[0] + a * hx, c[1] + b * hy, c[2] + d * hz) for a, b, d in
         ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))]
    emit(key, M, v, BF, box_uv(uvs))

def rod(key, M, a, b, ra, rb=None, seg=6):
    a, b = Vector(a), Vector(b)
    rb = ra if rb is None else rb
    ax = b - a
    if ax.length < 1e-6:
        return
    w = ax.normalized()
    t = Vector((0, 1, 0)) if abs(w.y) < 0.9 else Vector((1, 0, 0))
    u = w.cross(t).normalized()
    v = w.cross(u)
    ring = lambda c, r: [tuple(c + (u * math.cos(2 * math.pi * i / seg) + v * math.sin(2 * math.pi * i / seg)) * r)
                         for i in range(seg)]
    verts = ring(a, ra) + ring(b, rb)
    faces = [(i, (i + 1) % seg, seg + (i + 1) % seg, seg + i) for i in range(seg)]
    emit(key, M, verts, faces, box_uv(0.5))

def cyl(key, M, cx, y0, cz, r, h, seg=24, smooth=True):
    ring = lambda y, rr: [(cx + rr * math.sin(2 * math.pi * i / seg), y, cz + rr * math.cos(2 * math.pi * i / seg))
                          for i in range(seg)]
    v = ring(y0, r) + ring(y0 + h, r)
    faces = [(i, (i + 1) % seg, seg + (i + 1) % seg, seg + i) for i in range(seg)]
    uvx = [[(i / seg, y0), ((i + 1) / seg, y0), ((i + 1) / seg, y0 + h), (i / seg, y0 + h)] for i in range(seg)]
    emit(key, M, v, faces, smooth=smooth, uvx=uvx)
    emit(key, M, ring(y0 + h, r), [tuple(range(seg))], box_uv(1.0))
    emit(key, M, ring(y0, r), [tuple(range(seg - 1, -1, -1))], box_uv(1.0))

def dome(key, M, c, r, lat=5, lon=12):
    v = []
    for j in range(lat + 1):
        ph = (math.pi / 2) * j / lat
        rr, y = r * math.cos(ph), c[1] + r * math.sin(ph)
        v += [(c[0] + rr * math.sin(2 * math.pi * i / lon), y, c[2] + rr * math.cos(2 * math.pi * i / lon))
              for i in range(lon)]
    faces = [(j * lon + i, j * lon + (i + 1) % lon, (j + 1) * lon + (i + 1) % lon, (j + 1) * lon + i)
             for j in range(lat) for i in range(lon)]
    emit(key, M, v, faces, smooth=True)

def disc_patch(key, M, center_fn, R, seg=24):
    pts = [(R * math.cos(2 * math.pi * i / seg), R * math.sin(2 * math.pi * i / seg)) for i in range(seg)]
    verts = [center_fn(0, 0)] + [center_fn(*p) for p in pts]
    faces = [(0, 1 + i, 1 + (i + 1) % seg) for i in range(seg)]
    uv = lambda p: (0.5 + p[0] / (2 * R), 0.5 + p[1] / (2 * R))
    uvx = [[(.5, .5), uv(pts[i]), uv(pts[(i + 1) % seg])] for i in range(seg)]
    emit(key, M, verts, faces, uvx=uvx)

def quad(key, M, x0, y0, x1, y1, z, uv=None):
    emit(key, M, [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], [(0, 1, 2, 3)],
         uvx=[uv] if uv else None)

def text(key, M, body, size, pos, rot=0.0, ext=0.004):
    cu = bpy.data.curves.new('t', 'FONT')
    cu.body, cu.size, cu.extrude = body, size, ext
    cu.align_x, cu.align_y, cu.resolution_u = 'CENTER', 'CENTER', 2
    ob = bpy.data.objects.new('t', cu)
    scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    if not me.vertices:
        print('WARNING: empty text mesh for', body)
    R = Matrix.Rotation(math.radians(rot), 3, 'Z')
    emit(key, M, [tuple(R @ v.co + Vector(pos)) for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)

def clip_rect(poly, xmin, xmax, zmin, zmax):
    def clip(poly, inside, inter):
        out = []
        for i in range(len(poly)):
            a, b = poly[i - 1], poly[i]
            ia, ib = inside(a), inside(b)
            if ib:
                if not ia:
                    out.append(inter(a, b))
                out.append(b)
            elif ia:
                out.append(inter(a, b))
        return out
    ix = lambda xc: (lambda a, b: (xc, a[1] + (b[1] - a[1]) * (xc - a[0]) / (b[0] - a[0])))
    iz = lambda zc: (lambda a, b: (a[0] + (b[0] - a[0]) * (zc - a[1]) / (b[1] - a[1]), zc))
    for ins, it in ((lambda p: p[0] >= xmin, ix(xmin)), (lambda p: p[0] <= xmax, ix(xmax)),
                    (lambda p: p[1] >= zmin, iz(zmin)), (lambda p: p[1] <= zmax, iz(zmax))):
        if not poly:
            break
        poly = clip(poly, ins, it)
    return poly

def flat_poly(key, pts, y):
    if len(pts) < 3:
        return
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    if area > 0:
        pts = pts[::-1]
    emit(key, I, [(x, y, z) for x, z in pts], [tuple(range(len(pts)))])

# ----------------------------------------------------------------- scene pieces
def container(key, pos, yaw=0.0, L=6.1, W=2.44, H=2.6):
    """Corrugated container. Local: x = long axis, y = up, z = width (+z = camera-facing side at yaw 0)."""
    M = P(pos[0], pos[1], pos[2], yaw)
    d, pitch = 0.06, 0.25
    hw = W / 2 - d - 0.04
    box(key, M, (0, (0.12 + H - 0.06) / 2, 0), (L - 0.12, H - 0.18, 2 * hw), 0.4)
    n = max(2, int((L - 0.24) / pitch))
    p = (L - 0.24) / n
    for side in (1, -1):
        pts = []
        for i in range(n):
            for fx, off in ((0, 0), (0.3, 0), (0.5, d), (0.8, d)):
                pts.append((-L / 2 + 0.12 + (i + fx) * p, side * (W / 2 - off)))
        pts.append((-L / 2 + 0.12 + n * p, side * W / 2))
        verts, faces = [], []
        for x, z in pts:
            verts += [(x, 0.12, z), (x, H - 0.12, z)]
        for i in range(len(pts) - 1):
            a, b = 2 * i, 2 * i + 2
            f = (a, b, b + 1, a + 1)
            faces.append(f if side == 1 else f[::-1])
        emit(key, M, verts, faces, lambda q, nn: (q.x * 0.4, q.y * 0.4))
    hx, hz = L / 2 - 0.06, W / 2 - 0.06
    for sz in (-1, 1):
        for y in (0.06, H - 0.06):
            box('frame', M, (0, y, sz * hz), (L, 0.12, 0.12))
    for sx in (-1, 1):
        for y in (0.06, H - 0.06):
            box('frame', M, (sx * hx, y, 0), (0.12, 0.12, W))
        for sz in (-1, 1):
            box('frame', M, (sx * hx, H / 2, sz * hz), (0.12, H, 0.12))
    for z in (-0.4, 0.4):
        box('frame', M, (L / 2 - 0.04, H / 2, z), (0.04, H - 0.4, 0.05))
    if abs(pos[1]) < 0.01:
        hxx, hzz = (L / 2, W / 2) if abs(yaw % 180) < 1 else (W / 2, L / 2)
        FOOT.append((pos[0] - hxx, pos[0] + hxx, pos[2] - hzz, pos[2] + hzz))
    return M

def label(M, x, y, z, w=0.32, h=0.5):
    quad('lbl_yellow', M, x - w / 2, y - h / 2, x + w / 2, y + h / 2, z + 0.004)
    text('lbl_text', M, "2,6m\n8'6\"", 0.085, (x, y, z + 0.008), ext=0.002)

def barrel(cx, cz, r=0.35, h=1.0):
    cyl('drum', I, cx, 0, cz, r, h, 28)
    for y in (0.14, 0.5, 0.86):
        cyl('drum', I, cx, y - 0.025, cz, r + 0.012, 0.05, 28)
    cyl('drum', I, cx, h, cz, r * 0.93, 0.03, 28)
    a0, yc = 0.35, 0.58
    disc_patch('emblem', I, lambda du, dv: ((cx + (r + 0.004) * math.sin(a0 + du / r)), yc + dv,
                                           cz + (r + 0.004) * math.cos(a0 + du / r)), 0.16)

def plastic_crates(x, z):
    box('frame', I, (x, 0.07, z), (1.2, 0.14, 0.85))
    grid = [['w', 'b'], ['w', 'w'], ['b', 'b']]   # top -> bottom
    ch, cw, cd = 0.4, 0.56, 0.5
    FOOT.append((x - 0.65, x + 0.65, z - 0.45, z + 0.45))
    for r, row in enumerate(grid):
        y = 0.14 + ch / 2 + (2 - r) * ch
        for c, col in enumerate(row):
            cx = x + (-0.29 if c == 0 else 0.29)
            box('plasticW' if col == 'w' else 'plasticB', I, (cx, y, z), (cw, ch - 0.01, cd))
            box('frame', I, (cx, y + ch / 2 - 0.02, z), (cw + 0.02, 0.03, cd + 0.02))
            if c == 0:
                disc_patch('emblem', I, lambda du, dv, cx=cx, y=y: (cx + du, y + dv, z + cd / 2 + 0.003), 0.12)

def alu_cases(x, z):
    w, h, d = 1.1, 0.58, 0.72
    FOOT.append((x - 0.6, x + 0.6, z - 0.4, z + 0.4))
    for i in range(3):
        y = h / 2 + i * (h + 0.01)
        box('alu', I, (x, y, z), (w, h, d), 0.5)
        for dy in (h / 2 - 0.12, -h / 2 + 0.12):
            box('alu', I, (x, y + dy, z), (w + 0.03, 0.03, d + 0.03))
        for lx in (-0.3, 0.3):
            box('frame', I, (x + lx, y + 0.08, z + d / 2 + 0.02), (0.12, 0.07, 0.03))
    rng = random.Random(5)
    fz = z + d / 2 + 0.004
    for _ in range(14):
        case = rng.randrange(3)
        sw = rng.uniform(0.07, 0.15)
        sh = sw * rng.uniform(0.6, 1.1)
        sx = x + rng.uniform(-0.45, 0.3)
        sy = case * (h + 0.01) + h / 2 + rng.uniform(-0.2, 0.15)
        q = rng.randrange(4)
        u0, v0 = (q % 2) * 0.5 + 0.06, (q // 2) * 0.5 + 0.06
        quad('stickers', I, sx, sy, sx + sw, sy + sh, fz,
             [(u0, v0), (u0 + .38, v0), (u0 + .38, v0 + .38), (u0, v0 + .38)])

def mast(x, z):
    h, s = 9.0, 0.5
    for sx in (-s, s):
        for sz in (-s, s):
            rod('mast', I, (x + sx, 0, z + sz), (x + sx, h, z + sz), 0.06, 0.05)
    for k in range(1, 6):
        y = 1.5 * k
        ring = [(-s, -s), (s, -s), (s, s), (-s, s)]
        for i in range(4):
            a, b = ring[i], ring[(i + 1) % 4]
            rod('mast', I, (x + a[0], y, z + a[1]), (x + b[0], y, z + b[1]), 0.03, seg=4)
        rod('mast', I, (x - s, y - 1.5, z + s), (x + s, y, z + s), 0.025, seg=4)
        rod('mast', I, (x + s, y - 1.5, z + s), (x - s, y, z + s), 0.025, seg=4)
    box('mast', I, (x, 3.0, z), (1.9, 0.06, 1.9))
    for px in (-0.95, 0, 0.95):
        for pz in (-0.95, 0.95):
            rod('mast', I, (x + px, 3.0, z + pz), (x + px, 4.0, z + pz), 0.02, seg=4)
    for pz in (-0.95, 0.95):
        rod('mast', I, (x - 0.95, 4.0, z + pz), (x + 0.95, 4.0, z + pz), 0.02, seg=4)
    for px in (-0.95, 0.95):
        rod('mast', I, (x + px, 4.0, z - 0.95), (x + px, 4.0, z + 0.95), 0.02, seg=4)
    cyl('pipe', I, x + 0.7, 3.0, z - 0.2, 0.12, 3.0, 10)
    box('mast', I, (x - 0.5, 3.6, z - 0.4), (0.6, 1.2, 0.5))
    for k in range(1, 11):
        rod('frame', I, (x - 0.15, 0.3 * k, z + 0.58), (x + 0.15, 0.3 * k, z + 0.58), 0.01, seg=4)
    for lx in (-0.15, 0.15):
        rod('frame', I, (x + lx, 0, z + 0.58), (x + lx, 3.0, z + 0.58), 0.015, seg=4)
    for tx, tz in ((-7, 4), (-2, 6), (3, 5), (-9, -2), (7, -3)):   # rigging to deck
        rod('frame', I, (x, h - 0.2, z), (x + tx, 0.5, z + tz + 8), 0.008, seg=4)

def crane_boom():
    A, B = (6.0, 6.3, -2.5), (12.0, 10.6, -6.0)
    rod('crane', I, A, B, 0.13, 0.07, 8)
    box('frame', I, (A[0] - 0.1, A[1] - 0.3, A[2]), (0.3, 0.45, 0.2))
    for dx in (-0.12, 0.12):
        rod('frame', I, (A[0] + dx, A[1] - 0.1, A[2] - 0.12), (A[0] + dx, A[1] - 0.1, A[2] + 0.12), 0.13, seg=12)
    for end in ((14, 11.5, -7), (13, 9.5, -4), (10.5, 12.5, -3), (9, 5.8, -5.5), (15, 12.5, -5)):
        rod('frame', I, (A[0] + 0.1, A[1] + 0.05, A[2]), end, 0.008, seg=4)
    rod('frame', I, (A[0] - 0.1, A[1] - 0.5, A[2]), (A[0] - 0.1, A[1] - 2.2, A[2]), 0.01, seg=4)

def empty(name, x, y, z):
    e = bpy.data.objects.new(name, None)
    e.location = (x, -z, y)
    scene.collection.objects.link(e)

# ----------------------------------------------------------------- build
def build():
    DX0, DX1, DZ0, DZ1 = -8, 8, -12, 5          # deck extended to z=-12 so the far stacks don't overhang
    emit('deck', I, [(DX0, 0, DZ1), (DX1, 0, DZ1), (DX1, 0, DZ0), (DX0, 0, DZ0)], [(0, 1, 2, 3)],
         uvx=[[(DX0 / 5, DZ1 / 5), (DX1 / 5, DZ1 / 5), (DX1 / 5, DZ0 / 5), (DX0 / 5, DZ0 / 5)]])

    # diagonal walkway band (24 deg) + yellow edge lines
    a = math.radians(24)
    dvec, nvec, P0 = (math.cos(a), -math.sin(a)), (math.sin(a), math.cos(a)), (-4.0, 1.0)
    def band(s0, s1):
        poly = [(P0[0] + dvec[0] * t + nvec[0] * s, P0[1] + dvec[1] * t + nvec[1] * s)
                for t, s in ((-40, s0), (40, s0), (40, s1), (-40, s1))]
        return clip_rect(poly, DX0, DX1, DZ0, DZ1)
    flat_poly('stripe', band(-1.3, 1.3), 0.012)
    flat_poly('yellow', band(-1.25, -1.13), 0.02)
    flat_poly('yellow', band(1.13, 1.25), 0.02)

    # left container wall (2 high, 9 m long along Z)
    M1 = container('c_blue', (-6.1, 0, -1.5), 90, L=9.0)
    container('c_blue', (-6.1, 2.6, -1.5), 90, L=9.0)
    W = 2.44
    text('t_rohan', M1, 'Rohan', 0.8, (-2.6, 0.62, W / 2 + 0.012))
    label(M1, -3.3, 1.75, W / 2)
    M1u = P(-6.1, 2.6, -1.5, 90)
    label(M1u, -3.3, 1.75, W / 2)
    quad('lbl_red', M1, -2.95, 2.25, -2.73, 2.47, W / 2 + 0.004)
    rod('frame', M1, (-4.15, 2.0, W / 2 + 0.05), (-4.15, 3.7, W / 2 + 0.05), 0.025)
    box('frame', M1, (-4.15, 2.6, W / 2 + 0.06), (0.1, 0.5, 0.04))
    rod('frame', M1, (-4.15, 3.3, W / 2 + 0.06), (-4.0, 2.0, W / 2 + 0.06), 0.012, seg=4)
    box('frame', M1, (-4.0, 1.9, W / 2 + 0.06), (0.06, 0.16, 0.04))

    barrel(-3.6, -1.5)
    FOOT.append((-3.95, -3.25, -1.85, -1.15))

    # centre stack
    container('c_blue2', (-0.675, 0, -9), 0, L=3.05)
    container('c_red', (2.375, 0, -9), 0, L=3.05)
    Mg = container('c_green', (0.8, 2.6, -9), 0, L=6.1)
    text('t_white', Mg, 'VOGEL', 0.62, (0.4, 1.5, W / 2 + 0.012), rot=-3)
    for (x0, y0, x1, y1) in ((-2.9, 0.1, 2.9, 2.5), (2.9, 0.1, -2.9, 2.5)):
        rod('frame', Mg, (x0, y0, W / 2 + 0.04), (x1, y1, W / 2 + 0.04), 0.015, seg=4)
    for x in (-2.9, 2.9):
        for y in (0.1, 2.5):
            box('frame', Mg, (x, y, W / 2 + 0.04), (0.1, 0.1, 0.06))

    # right side
    plastic_crates(4.9, -5.6)
    alu_cases(5.8, -5.9)
    box('worn', I, (7.75, 1.1, -3.2), (1.4, 2.2, 1.7), 0.35)
    FOOT.append((7.0, 8.5, -4.1, -2.3))

    # lashing plates
    rng = random.Random(7)
    placed = 0
    while placed < 46:
        x, z = rng.uniform(-7, 7), rng.uniform(-10.5, 4.5)
        if any(f[0] - 0.5 < x < f[1] + 0.5 and f[2] - 0.5 < z < f[3] + 0.5 for f in FOOT):
            continue
        yaw = rng.choice((0, 12, 24, 90))
        box('frame', P(x, 0, z, yaw), (0, 0.012, 0), (0.30, 0.024, 0.20))
        box('frame', P(x, 0, z, yaw), (0, 0.03, 0), (0.12, 0.02, 0.08))
        placed += 1

    # background silhouettes (cheap)
    mast(-3.6, -13.0)
    crane_boom()
    rod('pipe', I, (3.3, 2.2, -9.8), (9.5, 2.2, -9.8), 0.09, seg=10)
    box('hull', I, (6.8, 1.2, -12.5), (6.6, 2.4, 0.5))
    box('frame', I, (7.0, 0.35, -11.6), (0.3, 0.7, 0.3))
    dome('helmet', I, (7.0, 0.72, -11.6), 0.22)
    emit('sea', I, [(-80, -1.5, -12.8), (80, -1.5, -12.8), (80, -1.5, -90), (-80, -1.5, -90)], [(0, 1, 2, 3)])

    # anchors for the game code
    for i, (sx, sz) in enumerate(((-2.4, 0), (-0.8, 0.2), (0.8, 0.2), (2.4, 0))):
        empty(f'SLOT_{i}', sx, 0, sz)
    empty('CAM_POS', 0.4, 1.5, 9.5)
    empty('CAM_TARGET', 0, 1.3, -2)

def main():
    mats = create_material_library()
    build()
    tris = 0
    for key, bm in BM.items():
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        me = bpy.data.meshes.new(key)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mats[key])
        scene.collection.objects.link(bpy.data.objects.new(key, me))
        tris += len(me.polygons)
    print(f'LOBBY STATS: triangles={tris} draw_calls={len(BM)} materials={len(mats)}')
    if tris > 60000:
        raise RuntimeError('triangle budget exceeded')
    if len(BM) > 40:
        print('WARNING: draw-call budget exceeded')

    bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_apply=True, export_yup=True,
                              export_image_format='JPEG', export_jpeg_quality=75,
                              export_cameras=False, export_lights=False,
                              export_texcoords=True, export_normals=True, export_materials='EXPORT')
    meta = {
        'camera': {'pos': [0.4, 1.5, 9.5], 'target': [0, 1.3, -2], 'fov': 70},
        'slots': [[-2.4, 0, 0], [-0.8, 0, 0.2], [0.8, 0, 0.2], [2.4, 0, 0]],
        'spot': {'color': '#dfeaff', 'pos': [-5.5, 7, -6], 'target': [2, 0, -3]},
        'warm': {'color': '#ffb36b', 'pos': [5.5, 0.4, -3.5], 'intensity': 'low'},
        'fogExp2': {'color': '#3a4550', 'density': 0.035},
        'toneMapping': {'type': 'ACESFilmic', 'exposure': 0.9},
        'sky': {'top': '#1a1e24', 'horizon': '#55606a'},
        'rain': {'streaks': 350},
    }
    with open(os.path.splitext(OUT)[0] + '.meta.json', 'w') as f:
        json.dump(meta, f, indent=2)
    print('EXPORTED', OUT, os.path.getsize(OUT) // 1024, 'KB')

main()
