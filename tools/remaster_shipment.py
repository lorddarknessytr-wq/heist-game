#!/usr/bin/env python3
"""Remaster the raw Shipment GLB into a war-atmosphere lobby (assets/lobby.glb).
Reads environment.glb / environment.txt (real GLB bytes), keeps geometry,
re-grades + re-materials everything, merges for mobile, adds hero props.
Pure python: numpy + pillow + trimesh(export only)."""
import argparse, io, json, math, os, struct
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import trimesh
from trimesh.visual.material import PBRMaterial

# ---------------- GLB reader ----------------
def load_glb(path):
    b = open(path, 'rb').read()
    if b[:4] != b'glTF':
        raise ValueError('not a GLB: ' + path)
    ver, total = struct.unpack_from('<II', b, 4)
    off = 12; js = None; bin_ = b''
    while off < total:
        clen, ctype = struct.unpack_from('<II', b, off); off += 8
        chunk = b[off:off + clen]; off += clen
        if ctype == 0x4E4F534A: js = json.loads(chunk.decode('utf-8'))
        elif ctype == 0x004E4942: bin_ = chunk
    return js, bin_

def accessor(js, bin_, i):
    a = js['accessors'][i]; bv = js['bufferViews'][a['bufferView']]
    base = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    n = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
    dt = {5126: '<f4', 5125: '<u4', 5123: '<u2', 5121: '<u1', 5122: '<i2', 5120: '<i1'}[a['componentType']]
    es = np.dtype(dt).itemsize * n
    stride = bv.get('byteStride', es)
    out = np.empty((a['count'], n), dtype=dt)
    for k in range(a['count']):
        out[k] = np.frombuffer(bin_, dtype=dt, count=n, offset=base + k * stride)
    return out

def node_worlds(js):
    parents = {}
    for ni, n in enumerate(js.get('nodes', [])):
        for c in n.get('children', []): parents[c] = ni
    worlds = {}
    def rec(ni, pm):
        n = js['nodes'][ni]
        m = np.array(n['matrix'], float).reshape(4, 4).T if 'matrix' in n else np.eye(4)
        if 'translation' in n: m[:3, 3] = n['translation']
        w = pm @ m; worlds[ni] = w
        for c in n.get('children', []): rec(c, w)
    for r in js['scenes'][js.get('scene', 0)]['nodes']: rec(r, np.eye(4))
    return worlds

def read_primitives(js, bin_):
    worlds = node_worlds(js)
    mats = js.get('materials', [])
    prims = []
    for ni, n in enumerate(js.get('nodes', [])):
        if 'mesh' not in n: continue
        W = worlds.get(ni, np.eye(4))
        N = np.linalg.inv(W[:3, :3]).T
        for p in js['meshes'][n['mesh']]['primitives']:
            pos = accessor(js, bin_, p['attributes']['POSITION'])[:, :3]
            pw = (W @ np.hstack([pos, np.ones((len(pos), 1))]).T).T[:, :3]
            idx = accessor(js, bin_, p['indices']).reshape(-1).astype(np.uint32) if 'indices' in p else np.arange(len(pos), dtype=np.uint32)
            mi = p.get('material', 0)
            mname = mats[mi].get('name', '') if mi < len(mats) else ''
            prims.append((pw, idx.reshape(-1, 3), mname))
    return prims

def source_images(js, bin_):
    imgs = {}
    for ti, t in enumerate(js.get('textures', [])):
        si = t.get('source'); 
        if si is None: continue
        im = js['images'][si]
        if 'bufferView' in im:
            bv = js['bufferViews'][im['bufferView']]
            o = bv.get('byteOffset', 0); ln = bv['byteLength']
            try: imgs[ti] = Image.open(io.BytesIO(bin_[o:o + ln])).convert('RGB')
            except Exception: pass
    return imgs

# ---------------- procedural texture helpers ----------------
def tnoise(size, cells, seed):
    r = np.random.default_rng(seed)
    g = r.random((cells + 1, cells + 1)); g[-1, :] = g[0, :]; g[:, -1] = g[:, 0]
    x = np.linspace(0, cells, size, endpoint=False)
    x0 = np.floor(x).astype(int); fx = x - x0
    y = x[:, None]; y0 = np.floor(y).astype(int); fy = y - y0
    fx = fx[None, :]; fy = fy[:, None]
    a = g[y0, x0]; b = g[y0, x0 + 1]; c = g[y0 + 1, x0]; d = g[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy

def fbm(size, seed, octaves=4):
    s = np.zeros((size, size)); amp = .5; cells = 4
    for o in range(octaves):
        s += amp * tnoise(size, cells, seed + o * 7); amp *= .5; cells *= 2
    return s / s.max()

def grade(arr, sat=.86, con=1.12, bri=.96):
    a = arr.astype(np.float32) / 255.
    lum = a @ np.array([.299, .587, .114], np.float32)
    a = lum[..., None] + (a - lum[..., None]) * sat
    a = (a - .5) * con + .5
    a *= bri
    sh = np.clip(1 - lum, 0, 1)[..., None]
    a += sh * np.array([-.02, .0, .045], np.float32)      # cool shadows
    hi = np.clip(lum - .55, 0, 1)[..., None]
    a += hi * np.array([.05, .03, .0], np.float32)        # warm highlights
    return np.clip(a * 255, 0, 255).astype(np.uint8)

def normal_from(arr, strength=1.6):
    g = arr.astype(np.float32) @ np.array([.299, .587, .114], np.float32) / 255.
    gx = np.roll(g, -1, 1) - np.roll(g, 1, 1)
    gy = np.roll(g, -1, 0) - np.roll(g, 1, 0)
    nx = -gx * strength; ny = -gy * strength; nz = np.ones_like(g)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    out = np.stack([nx / ln, ny / ln, nz / ln], -1)
    return Image.fromarray(((out * .5 + .5) * 255).astype(np.uint8))

def mr_map(size, rough, metal, seed, wet=.3):
    n = fbm(size, seed, 3)
    r = np.clip(rough + (n - .5) * .22 - wet * (n > .62), .05, 1)
    a = np.zeros((size, size, 3), np.uint8)
    a[..., 0] = 255; a[..., 1] = (r * 255).astype(np.uint8); a[..., 2] = int(metal * 255)
    return Image.fromarray(a)

def font(sz):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if os.path.exists(p): return ImageFont.truetype(p, sz)
    return ImageFont.load_default()

def container_tex(target, label, seed, detail=None, size=1024):
    t = np.array(target, np.float32) / 255.
    n = fbm(size, seed, 4)
    base = np.ones((size, size, 3), np.float32) * t
    base *= (.72 + .5 * n)[..., None]
    x = np.arange(size)
    stripe = (np.sin(x / size * 2 * np.pi * 28) * .5 + .5) ** 1.5
    base *= (1 - .16 * stripe)[None, :, None]
    rail = np.zeros(size, np.float32)
    rail[:int(size * .05)] = 1; rail[int(size * .95):] = 1
    base *= (1 - .4 * rail)[:, None, None]
    rust = np.clip((fbm(size, seed + 3, 4) - .58) * 3, 0, 1)
    vgrad = np.linspace(0, 1, size)[:, None] ** 1.4
    rust *= vgrad
    base = base * (1 - rust[..., None]) + (np.array([96, 52, 30]) / 255.) * rust[..., None]
    if detail is not None:
        d = np.array(detail.resize((size, size))).astype(np.float32) @ np.array([.299, .587, .114], np.float32) / 255.
        base *= (.55 + .6 * d)[..., None]
    img = Image.fromarray(grade(np.clip(base * 255, 0, 255).astype(np.uint8)))
    d = ImageDraw.Draw(img, 'RGBA')
    d.text((size * .06, size * .78), label, font=font(int(size * .13)), fill=(225, 232, 236, 120))
    d.rectangle([size * .08, size * .12, size * .2, size * .24], fill=(216, 182, 42, 230))
    d.text((size * .09, size * .13), "2,6m", font=font(int(size * .05)), fill=(20, 18, 10, 255))
    d.rectangle([size * .08, size * .3, size * .15, size * .37], fill=(176, 48, 40, 230))
    return img

def deck_tex(detail, seed, size=1024):
    n = fbm(size, seed, 4)
    base = np.zeros((size, size, 3), np.float32)
    base[..., 0] = 47 + 18 * n; base[..., 1] = 90 + 24 * n; base[..., 2] = 82 + 20 * n
    if detail is not None:
        d = np.array(detail.resize((size, size))).astype(np.float32) @ np.array([.299, .587, .114], np.float32) / 255.
        base *= (.45 + .8 * d)[..., None]
    wet = (fbm(size, seed + 9, 3) > .6).astype(np.float32)
    base *= (1 - .35 * wet)[..., None]
    rust = np.clip((fbm(size, seed + 5, 4) - .66) * 3, 0, 1)
    base = base * (1 - rust[..., None]) + np.array([122, 63, 40]) * rust[..., None]
    return Image.fromarray(grade(np.clip(base, 0, 255).astype(np.uint8), sat=.9, con=1.15))

def wood_tex(detail, seed, size=512):
    n = fbm(size, seed, 4)
    base = np.zeros((size, size, 3), np.float32)
    base[..., 0] = 62 + 26 * n; base[..., 1] = 46 + 18 * n; base[..., 2] = 32 + 12 * n
    plank = (np.arange(size) // (size // 6)) % 2
    base *= (.8 + .2 * plank)[:, None, None]
    if detail is not None:
        d = np.array(detail.resize((size, size))).astype(np.float32) @ np.array([.299, .587, .114], np.float32) / 255.
        base *= (.5 + .7 * d)[..., None]
    return Image.fromarray(grade(np.clip(base, 0, 255).astype(np.uint8), sat=.8, con=1.1, bri=.85))

def metal_tex(seed, size=512):
    n = fbm(size, seed, 4)
    v = 40 + 26 * n
    base = np.stack([v, v + 3, v + 7], -1)
    scr = np.clip((fbm(size, seed + 2, 3) - .7) * 4, 0, 1)
    base += scr[..., None] * 60
    return Image.fromarray(grade(np.clip(base, 0, 255).astype(np.uint8), sat=.7, con=1.15))

def walkway_tex(size=1024):
    im = Image.new('RGBA', (size, size), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    band = Image.new('RGBA', (size * 3, int(size * .26)), (0, 0, 0, 0)); bd = ImageDraw.Draw(band)
    h = band.height
    bd.rectangle([0, int(h * .1), size * 3, int(h * .9)], fill=(16, 21, 29, 235))
    bd.rectangle([0, 0, size * 3, int(h * .08)], fill=(176, 138, 30, 235))
    bd.rectangle([0, int(h * .92), size * 3, h], fill=(176, 138, 30, 235))
    band = band.rotate(22, expand=True, resample=Image.BICUBIC)
    im.paste(band, ((size - band.width) // 2, (size - band.height) // 2), band)
    return im

# ---------------- geometry helpers ----------------
def box_tris(w, h, d, x, y, z, ry=0):
    b = trimesh.creation.box(extents=(w, h, d))
    if ry: b.apply_transform(trimesh.transformations.rotation_matrix(math.radians(ry), (0, 1, 0)))
    b.apply_translation((x, y, z))
    return b.vertices[b.faces].reshape(-1, 3, 3)

def cyl_tris(r, h, x, y, z, sec=16):
    c = trimesh.creation.cylinder(radius=r, height=h, sections=sec)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-90), (1, 0, 0)))
    c.apply_translation((x, y, z))
    return c.vertices[c.faces].reshape(-1, 3, 3)

def build_unmerged(tris, tile):
    tris = np.asarray(tris, np.float32)
    v = tris.reshape(-1, 3)
    e1 = tris[:, 1] - tris[:, 0]; e2 = tris[:, 2] - tris[:, 0]
    n = np.cross(e1, e2)
    ln = np.linalg.norm(n, axis=1, keepdims=True); ln[ln == 0] = 1
    n = n / ln
    nf = np.repeat(n, 3, axis=0)
    uv = np.zeros((len(v), 2), np.float32)
    for f in range(len(tris)):
        ax = int(np.argmax(np.abs(n[f])))
        idx = [i for i in range(3) if i != ax]
        if ax == 1: idx = [0, 2]
        p = tris[f][:, idx] / tile
        uv[f * 3:(f + 1) * 3] = p
    return v, nf, uv, np.arange(len(v), dtype=np.uint32).reshape(-1, 3)

def mat_for(img, rough, metal, seed, normal_strength=1.4, alpha=None):
    arr = np.array(img)
    return PBRMaterial(baseColorTexture=img,
                       metallicRoughnessTexture=mr_map(img.width, rough, metal, seed),
                       normalTexture=normal_from(arr, normal_strength),
                       metallicFactor=1.0, roughnessFactor=1.0,
                       alphaMode=alpha or 'OPAQUE', doubleSided=True)

# ---------------- main ----------------
def find_input(explicit):
    cands = [explicit] if explicit else []
    cands += ['environment.glb', 'environment.txt', 'shipment.glb', 'shipment.txt',
              'assets/environment.glb', 'assets/environment.txt']
    for c in cands:
        if c and os.path.exists(c):
            with open(c, 'rb') as f:
                if f.read(4) == b'glTF': return c
    for f in os.listdir('.'):
        if f.endswith(('.glb', '.txt')):
            with open(f, 'rb') as fh:
                if fh.read(4) == b'glTF': return f
    raise SystemExit('No GLB input found (environment.glb / environment.txt).')

def main(out):
    src = find_input(None)
    print('input:', src)
    js, bin_ = load_glb(src)
    prims = read_primitives(js, bin_)
    imgs = source_images(js, bin_)
    # detail image per material-name keyword
    def detail_for(mname):
        for ti, t in enumerate(js.get('textures', [])):
            mi = None
            for k, m in enumerate(js.get('materials', [])):
                bc = m.get('pbrMetallicRoughness', {}).get('baseColorTexture', {})
                if bc.get('index') == ti: mi = k; break
            if mi is not None and mi < len(js['materials']):
                nm = js['materials'][mi].get('name', '').lower()
                key = mname.lower()
                if ('red' in key and 'red' in nm) or ('bamboo' in key and 'bamboo' in nm) \
                   or ('concrete' in key and 'concrete' in nm) or ('generic' in key and 'generic' in nm):
                    return imgs.get(ti)
        return None

    # gather world triangles + class
    raw = []
    allv = []
    for pw, faces, mname in prims:
        tris = pw[faces]
        allv.append(tris.reshape(-1, 3))
        mn = mname.lower()
        bbmin = tris.reshape(-1, 3).min(0); bbmax = tris.reshape(-1, 3).max(0)
        dim = bbmax - bbmin; ctr = (bbmax + bbmin) / 2
        if 'bamboo' in mn or 'wood' in mn: cls = 'wood'
        elif 'concrete' in mn: cls = 'deck'
        elif 'black' in mn: cls = 'metal'
        elif 'red' in mn: cls = 'container'
        else:
            cls = 'container' if (dim[1] > 1.5 and dim.max() > 3) else 'metal'
        raw.append((tris, cls, ctr))
    allv = np.vstack(allv)
    mn = allv.min(0); mx = allv.max(0)
    span = max(mx[0] - mn[0], mx[2] - mn[2])
    scale = 26.0 / span if span > 0 else 1.0
    cx = (mn[0] + mx[0]) / 2; cz = (mn[2] + mx[2]) / 2; y0 = mn[1]
    def xf(p):
        q = (p - np.array([cx, y0, cz])) * scale
        return q

    buckets = {}
    def add(cls, tris, name):
        buckets.setdefault(name, {'cls': cls, 'tris': []})['tris'].append(tris)
    for tris, cls, ctr in raw:
        t = xf(tris)
        c = xf(ctr)
        if cls == 'container':
            if c[0] < -3: name = 'left_wall'
            elif c[2] < -3 and c[1] > 2.6: name = 'center_green'
            elif c[2] < -3: name = 'center_blue'
            elif c[0] > 3: name = 'center_red'
            else: name = 'center_blue'
        elif cls == 'deck': name = 'deck'
        elif cls == 'wood': name = 'steel_merged'
        else: name = 'steel_merged'
        add(cls, t, name)

    # hero props near lobby focus
    add('metal', cyl_tris(.35, 1, -3.2, .5, -1.2), 'drum')
    add('metal', box_tris(1.15, .5, .72, 4.6, .27, -4.6), 'alum_stack')
    add('metal', box_tris(1.15, .5, .72, 4.6, .79, -4.6), 'alum_stack')
    add('metal', box_tris(1.15, .5, .72, 4.6, 1.31, -4.6), 'alum_stack')
    add('container', box_tris(.55, .42, .5, 3.6, .33, -4.2), 'crates_blue')
    add('container', box_tris(.55, .42, .5, 4.2, .33, -4.2), 'crates_white')
    add('container', box_tris(.55, .42, .5, 3.6, .77, -4.2), 'crates_white')
    add('container', box_tris(.55, .42, .5, 4.2, .77, -4.2), 'crates_blue')
    add('container', box_tris(1.6, 2.2, 1.4, 7.2, 1.1, -3.6), 'beige_case')
    add('metal', box_tris(.5, .18, .3, -3.4, 4.2, -6.0), 'lamp')
    # walkway decal plane
    wt = walkway_tex()
    wv = np.array([[-9, .015, 6], [9, .015, 6], [9, .015, -8], [-9, .015, -8]], np.float32)
    wf = np.array([[0, 1, 2], [0, 2, 3]], np.uint32)
    wuv = np.array([[0, 1], [1, 1], [1, 0], [0, 0]], np.float32)

    # textures per class
    tex = {
        'left_wall':   mat_for(container_tex((45, 78, 122), 'Rohan', 11, detail_for('generic')), .58, .5, 11),
        'center_blue': mat_for(container_tex((51, 84, 127), 'BLOCK', 12, detail_for('generic')), .58, .5, 12),
        'center_green':mat_for(container_tex((47, 74, 80), '..VOGEL', 13, detail_for('generic')), .58, .5, 13),
        'center_red':  mat_for(container_tex((122, 63, 51), 'HARBOR', 14, detail_for('red')), .62, .45, 14),
        'deck':        mat_for(deck_tex(detail_for('concrete'), 21), .28, .35, 21, normal_strength=1.0),
        'wood':        mat_for(wood_tex(detail_for('bamboo'), 31), .6, .1, 31),
        'metal':       mat_for(metal_tex(41), .5, .7, 41),
        'drum':        mat_for(metal_tex(42), .45, .6, 42),
        'alum_stack':  mat_for(metal_tex(43), .32, .85, 43),
        'crates_blue': mat_for(container_tex((31, 111, 181), '', 15), .6, .05, 15),
        'crates_white':mat_for(container_tex((232, 232, 232), '', 16), .6, .05, 16),
        'beige_case':  mat_for(container_tex((207, 196, 168), '', 17), .72, .1, 17),
        'lamp':        PBRMaterial(baseColorFactor=[.87, .92, 1, 1], emissiveFactor=[1, 1, 1],
                                   metallicFactor=0, roughnessFactor=.4, doubleSided=True),
    }
    tiles = {'container': 2.44, 'deck': 4.0, 'wood': 1.2, 'metal': 1.5}

    sc = trimesh.Scene()
    for name, b in buckets.items():
        tris = np.vstack(b['tris'])
        cls = b['cls']
        v, n, uv, f = build_unmerged(tris, tiles.get(cls, 1.5))
        m = trimesh.Trimesh(vertices=v, faces=f, vertex_normals=n, process=False)
        m.visual = trimesh.visual.TextureVisuals(uv=uv, material=tex[name])
        sc.add_geometry(m, node_name=name, geom_name=name)
    # walkway
    wm = trimesh.Trimesh(vertices=wv, faces=wf, process=False)
    wm.visual = trimesh.visual.TextureVisuals(uv=wuv, material=PBRMaterial(
        baseColorTexture=wt, metallicFactor=0, roughnessFactor=.5, alphaMode='BLEND', doubleSided=True))
    sc.add_geometry(wm, node_name='deck_paint', geom_name='deck_paint')

    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    sc.export(out)
    chk = trimesh.load(out)
    tris = sum(len(g.faces) for g in chk.geometry.values())
    print(f'OK {out} | nodes={len(chk.geometry)} tris={tris} size={os.path.getsize(out)/1024:.0f} KB')

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--out', default='assets/lobby.glb')
    main(ap.parse_args().out)
