#!/usr/bin/env python3
"""BLOCK HARBOR — bake the rainy cargo-deck lobby into assets/lobby.glb.
Pure python (trimesh+pillow+numpy). No external assets. Runs on GitHub Actions."""
import argparse, math, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import trimesh
from trimesh.visual.material import PBRMaterial

rng = np.random.default_rng(20261122)
S = 512
RESAMPLE = getattr(Image, "Resampling", Image).BICUBIC

def font(sz):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    try:
        return ImageFont.load_default(size=sz)
    except TypeError:
        return ImageFont.load_default()

def grime(d, w, h, n, col, a):
    for _ in range(n):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        d.rectangle([x, y, x + int(rng.integers(2, 30)), y + int(rng.integers(2, 12))],
                    fill=col + (int(rng.integers(0, a)),))

def rust(d, w, h, n):
    for _ in range(n):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h // 2))
        d.rectangle([x, y, x + int(rng.integers(2, 5)), y + int(rng.integers(40, 280))],
                    fill=(96, 52, 30, int(rng.integers(40, 95))))

def stripes(d, w, h, n=32):
    p = w / n
    for i in range(n):
        x = i * p
        d.rectangle([x, 0, x + p * .30, h], fill=(255, 255, 255, 30))
        d.rectangle([x + p * .62, 0, x + p, h], fill=(0, 0, 0, 48))

def container_tex(base, rohan=False, vogel=False, seam=False, ribs=False):
    im = Image.new("RGB", (S, S), base); d = ImageDraw.Draw(im, "RGBA")
    if not ribs: stripes(d, S, S)
    grime(d, S, S, 260, (10, 14, 18), 42)
    grime(d, S, S, 110, (210, 220, 225), 14)
    rust(d, S, S, 26)
    d.rectangle([0, 0, S, 10], fill=(0, 0, 0, 90))
    d.rectangle([0, S - 12, S, S], fill=(0, 0, 0, 90))
    if seam: d.rectangle([0, S // 2 - 4, S, S // 2 + 4], fill=(0, 0, 0, 140))
    if rohan:
        d.text((26, S - 128), "Rohan", font=font(92), fill=(190, 205, 220, 92))
        for y in (40, 230):
            d.rectangle([60, y, 148, y + 66], fill=(216, 182, 42))
            d.text((70, y + 4), "2,6m", font=font(25), fill=(21, 19, 12))
            d.text((70, y + 34), "8'6\"", font=font(25), fill=(21, 19, 12))
        d.rectangle([52, 150, 98, 196], fill=(176, 48, 40))
    if vogel:
        d.text((84, 168), "..VOGEL", font=font(82), fill=(235, 240, 242, 215))
    return im

def deck_tex():
    im = Image.new("RGB", (S, S), "#2f5a52"); d = ImageDraw.Draw(im, "RGBA")
    for _ in range(90):
        x, y = int(rng.integers(0, S)), int(rng.integers(0, S))
        d.rectangle([x, y, x + int(rng.integers(30, 120)), y + int(rng.integers(24, 90))],
                    fill=(int(rng.integers(47, 62)), int(rng.integers(90, 112)), int(rng.integers(82, 100)), 120))
    band = Image.new("RGBA", (S * 3, 132), (0, 0, 0, 0)); bd = ImageDraw.Draw(band)
    bd.rectangle([0, 12, S * 3, 120], fill=(16, 21, 29, 255))
    bd.rectangle([0, 5, S * 3, 13], fill=(176, 138, 30, 215))
    bd.rectangle([0, 119, S * 3, 127], fill=(176, 138, 30, 215))
    band = band.rotate(22, expand=True, resample=RESAMPLE)
    im.paste(band, ((S - band.width) // 2, (S - band.height) // 2), band)
    grime(d, S, S, 300, (8, 12, 14), 55)
    for _ in range(26):
        x, y = int(rng.integers(0, S)), int(rng.integers(0, S))
        d.ellipse([x, y, x + int(rng.integers(8, 34)), y + int(rng.integers(6, 20))],
                  fill=(122, 63, 40, int(rng.integers(30, 90))))
    for _ in range(40):  # wet sheen streaks
        x, y = int(rng.integers(0, S)), int(rng.integers(0, S))
        d.rectangle([x, y, x + 2, y + int(rng.integers(20, 80))], fill=(200, 220, 235, 14))
    d.line([(S // 4, 0), (S // 4, S)], fill=(0, 0, 0, 60), width=2)
    d.line([(S // 2, 0), (S // 2, S)], fill=(0, 0, 0, 60), width=2)
    d.line([(3 * S // 4, 0), (3 * S // 4, S)], fill=(0, 0, 0, 60), width=2)
    return im

def alum_tex():
    im = Image.new("RGB", (S, S), "#cfd2d4"); d = ImageDraw.Draw(im, "RGBA")
    for y in range(0, S, 2):
        v = int(rng.integers(180, 240)); d.line([(0, y), (S, y)], fill=(v, v + 3, v + 6, 60))
    for i in (1, 2):
        d.line([(0, i * S // 3), (S, i * S // 3)], fill=(60, 66, 72, 200), width=6)
    d.rectangle([8, 8, S - 8, S - 8], outline=(90, 96, 102, 160), width=3)
    cols = [(200, 69, 44), (63, 127, 79), (216, 182, 42), (232, 232, 232)]
    for i in range(10):
        x, y = int(rng.integers(30, S - 90)), int(rng.integers(20, S - 60))
        d.rectangle([x, y, x + int(rng.integers(18, 48)), y + int(rng.integers(10, 26))],
                    fill=cols[i % 4] + (215,))
    for _ in range(40):
        x, y = int(rng.integers(0, S)), int(rng.integers(0, S))
        d.line([(x, y), (x + int(rng.integers(10, 50)), y + int(rng.integers(-3, 4)))],
               fill=(255, 255, 255, 90))
    grime(d, S, S, 120, (40, 44, 48), 30)
    return im

def emblem(d, cx, cy, r, col):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=5)
    d.ellipse([cx - r * .62, cy - r * .62, cx + r * .62, cy + r * .62], outline=col, width=4)
    d.ellipse([cx - r * .62, cy - r * .28, cx + r * .62, cy + r * .28], outline=col, width=4)
    d.line([(cx, cy - r * .62), (cx, cy + r * .62)], fill=col, width=4)
    for s in (-1, 1):
        d.polygon([(cx + s * r * .2, cy - r * .1), (cx + s * r * .95, cy - r * .55),
                   (cx + s * r * .75, cy - r * .05), (cx + s * r * .95, cy + r * .15),
                   (cx + s * r * .25, cy + r * .25)], fill=col)

def crate_tex(base, dark):
    im = Image.new("RGB", (256, 256), base); d = ImageDraw.Draw(im, "RGBA")
    d.rectangle([6, 6, 250, 250], outline=(0, 0, 0, 70), width=5)
    for i in (1, 2, 3):
        d.line([(i * 64, 10), (i * 64, 246)], fill=(0, 0, 0, 60), width=4)
    emblem(d, 128, 128, 52, dark)
    grime(d, 256, 256, 90, (20, 24, 28), 30)
    return im

def drum_tex():
    im = Image.new("RGB", (256, 256), "#b9b8b0"); d = ImageDraw.Draw(im, "RGBA")
    d.rectangle([0, 0, 256, 14], fill=(70, 66, 58, 140))
    d.rectangle([0, 240, 256, 256], fill=(70, 66, 58, 140))
    for _ in range(14):
        x = int(rng.integers(0, 256))
        d.rectangle([x, 10, x + 3, 10 + int(rng.integers(14, 44))], fill=(120, 80, 50, 110))
    d.line([(0, 85), (256, 85)], fill=(60, 58, 52, 130), width=4)
    d.line([(0, 170), (256, 170)], fill=(60, 58, 52, 130), width=4)
    emblem(d, 128, 128, 56, (28, 30, 34, 230))
    grime(d, 256, 256, 140, (60, 56, 48), 45)
    return im

def beige_tex():
    im = Image.new("RGB", (S, S), "#cfc4a8"); d = ImageDraw.Draw(im, "RGBA")
    grime(d, S, S, 200, (90, 80, 60), 40)
    for _ in range(70):
        x, y = int(rng.integers(0, S)), int(rng.integers(0, S))
        pts = [(x + int(rng.integers(-23, 24)), y + int(rng.integers(-15, 16))) for _ in range(5)]
        d.polygon(pts, fill=(16, 14, 10, int(rng.integers(130, 230))))
    rust(d, S, S, 18)
    d.rectangle([4, 4, S - 4, S - 4], outline=(40, 36, 28, 180), width=8)
    return im

def corr_normal():
    x = np.arange(256)
    nx = -np.cos(x / 8 * 2 * np.pi) * .85
    nz = np.sqrt(np.maximum(.05, 1 - nx ** 2))
    a = np.zeros((256, 256, 3), np.uint8)
    a[..., 0] = ((nx * .5 + .5) * 255).astype(np.uint8)[None, :]
    a[..., 1] = 128
    a[..., 2] = (nz * 255).astype(np.uint8)[None, :]
    return Image.fromarray(a)

def mr_tex(rough, metal, variation=0):
    a = np.zeros((64, 64, 3), np.uint8)
    r = np.clip(rough * 255 + rng.integers(-variation, variation + 1, (64, 64)), 0, 255)
    a[..., 0] = 255
    a[..., 1] = r.astype(np.uint8)
    a[..., 2] = int(metal * 255)
    return Image.fromarray(a)

def tex_mat(img, rough, metal, normal=None, var=0):
    return PBRMaterial(baseColorTexture=img, metallicRoughnessTexture=mr_tex(rough, metal, var),
                       normalTexture=normal, metallicFactor=1.0, roughnessFactor=1.0, doubleSided=True)

def fac_mat(rgb, rough, metal, emissive=None):
    return PBRMaterial(baseColorFactor=[rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 1],
                       metallicFactor=metal, roughnessFactor=rough,
                       emissiveFactor=emissive, doubleSided=True)

def merge(ms):
    """Concatenate meshes ignoring visuals (deterministic, version-proof)."""
    v = np.vstack([m.vertices for m in ms])
    f, off = [], 0
    for m in ms:
        f.append(m.faces + off)
        off += len(m.vertices)
    return trimesh.Trimesh(vertices=v, faces=np.vstack(f), process=False)

def torus(R, r, ms=12, ns=8):
    try:
        return trimesh.creation.torus(major_radius=R, minor_radius=r,
                                      major_sections=ms, minor_sections=ns)
    except Exception:
        t = np.linspace(0, 2 * np.pi, ns, endpoint=False)
        prof = np.column_stack([R + r * np.cos(t), r * np.sin(t)])
        prof = np.vstack([prof, prof[0]])
        return trimesh.creation.revolve(prof, sections=ms)

def auto_uv(m):
    m.unmerge_vertices()
    v = m.vertices[m.faces]; n = m.face_normals
    uv = np.zeros((len(v) * 3, 2))
    for f in range(len(v)):
        ax = int(np.argmax(np.abs(n[f])))
        idx = [i for i in range(3) if i != ax]
        p = v[f][:, idx]
        p = (p - p.min(0)) / (np.ptp(p, axis=0) + 1e-9)
        uv[f * 3:(f + 1) * 3] = p
    return uv

def cyl_uv(m, r, h):
    m.unmerge_vertices()
    uv = np.zeros((len(m.vertices), 2))
    for i, (x, y, z) in enumerate(m.vertices):
        if abs(abs(y) - h / 2) < 1e-6:
            uv[i] = [x / (2 * r) + .5, z / (2 * r) + .5]
        else:
            uv[i] = [math.atan2(x, z) / (2 * math.pi) + .5, 1 - (y / h + .5)]
    return uv

def T(x, y, z, ry=0, rx=0, rz=0):
    M = trimesh.transformations.rotation_matrix(math.radians(ry), (0, 1, 0))
    if rx: M = trimesh.transformations.rotation_matrix(math.radians(rx), (1, 0, 0)) @ M
    if rz: M = trimesh.transformations.rotation_matrix(math.radians(rz), (0, 0, 1)) @ M
    M[:3, 3] = (x, y, z)
    return M

def box(w, h, d, x, y, z, **kw):
    b = trimesh.creation.box(extents=(w, h, d))
    b.apply_transform(T(x, y, z, **kw))
    return b

def cylY(r, h, x, y, z, sec=12, **kw):
    c = trimesh.creation.cylinder(radius=r, height=h, sections=sec)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-90), (1, 0, 0)))
    c.apply_transform(T(x, y, z, **kw))
    return c

def align_cyl(r, a, b, sec=8):
    a, b = np.array(a, float), np.array(b, float)
    d = b - a; L = np.linalg.norm(d); dn = d / L
    c = trimesh.creation.cylinder(radius=r, height=L, sections=sec)
    c.apply_transform(trimesh.transformations.rotation_matrix(math.radians(-90), (1, 0, 0)))
    up = np.array([0, 1, 0]); axis = np.cross(up, dn)
    if np.linalg.norm(axis) > 1e-8:
        ang = math.acos(np.clip(np.dot(up, dn), -1, 1))
        c.apply_transform(trimesh.transformations.rotation_matrix(ang, axis))
    c.apply_transform(trimesh.transformations.translation_matrix((a + b) / 2))
    return c

def quad(bl, br, tr, tl):
    v = np.array([bl, br, tr, tl], float)
    f = np.array([[0, 1, 2], [0, 2, 3]])
    m = trimesh.Trimesh(vertices=v, faces=f, process=False)
    m.visual = trimesh.visual.TextureVisuals(uv=np.array([[0, 1], [1, 1], [1, 0], [0, 0]], float))
    return m

def put(scene, mesh, material, name, uvfn=None):
    uv = uvfn(mesh) if uvfn else auto_uv(mesh)
    mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=material)
    scene.add_geometry(mesh, node_name=name, geom_name=name)

def main(out):
    nrm = corr_normal()
    mLeft  = tex_mat(container_tex("#2d4e7a", rohan=True, seam=True, ribs=True), .62, .35)
    mBlue  = tex_mat(container_tex("#33547f"), .60, .35, nrm)
    mRed   = tex_mat(container_tex("#7a3f33"), .68, .30, nrm)
    mGreen = tex_mat(container_tex("#2f4a50", vogel=True), .60, .35, nrm)
    mDeck  = tex_mat(deck_tex(), .30, .55, var=22)
    mAlum  = tex_mat(alum_tex(), .35, .80, var=14)
    mCB    = tex_mat(crate_tex("#1f6fb5", (10, 18, 26, 220)), .60, .05)
    mCW    = tex_mat(crate_tex("#e8e8e8", (24, 30, 36, 220)), .60, .05)
    mDrum  = tex_mat(drum_tex(), .50, .55)
    mBeige = tex_mat(beige_tex(), .75, .10)
    sBlue  = fac_mat((45, 78, 122), .60, .35)
    sGreen = fac_mat((47, 74, 80), .60, .35)
    steel  = fac_mat((35, 42, 49), .62, .45)
    white  = fac_mat((232, 232, 232), .50, .10)
    lamp   = fac_mat((223, 234, 255), .40, .0, emissive=[1, 1, 1])
    seaM   = fac_mat((29, 36, 43), .85, .20)

    sc = trimesh.Scene()

    # deck (manual UV so the diagonal walkway reads correctly)
    put(sc, quad((-8, 0, 5), (8, 0, 5), (8, 0, -9), (-8, 0, -9)), mDeck, "deck",
        uvfn=lambda m: m.visual.uv)

    # left wall: base + textured camera-facing quad + REAL corrugation ribs
    put(sc, box(2.7, 5.2, 9, -6.15, 2.6, -1.5), sBlue, "left_base")
    put(sc, quad((-4.799, 0, 3), (-4.799, 0, -6), (-4.799, 5.2, -6), (-4.799, 5.2, 3)),
        mLeft, "left_wall", uvfn=lambda m: m.visual.uv)
    ribs = [box(.07, 5.0, .16, -4.76, 2.6, 2.85 - i * .285) for i in range(32)]
    put(sc, merge(ribs), sBlue, "left_ribs")

    # central stack
    put(sc, box(3, 2.6, 2.44, -.7, 1.3, -7.8), sBlue, "center_blue_base")
    put(sc, quad((-2.2, 0, -6.579), (.8, 0, -6.579), (.8, 2.6, -6.579), (-2.2, 2.6, -6.579)),
        mBlue, "center_blue", uvfn=lambda m: m.visual.uv)
    put(sc, box(3, 2.6, 2.44, 2.3, 1.3, -7.8), fac_mat((122, 63, 51), .68, .3), "center_red")
    put(sc, box(6.1, 2.6, 2.44, .8, 3.9, -7.8), sGreen, "center_green_base")
    put(sc, quad((-2.25, 2.6, -6.579), (3.85, 2.6, -6.579), (3.85, 5.2, -6.579), (-2.25, 5.2, -6.579)),
        mGreen, "center_green", uvfn=lambda m: m.visual.uv)

    # drum (wrapped UV so the emblem faces the camera)
    put(sc, cylY(.35, 1, -3.6, .5, -1.5, sec=24), mDrum, "drum", uvfn=lambda m: cyl_uv(m, .35, 1))

    # crates merged per color
    cb, cw = [], []
    for r in range(3):
        for c in range(2):
            b = box(.55, .42, .5, 4.62 + c * .6, .33 + r * .44, -5.4, ry=(r * 2 + c) * 3 - 3)
            (cb if (r + c) % 2 else cw).append(b)
    put(sc, merge(cb), mCB, "crates_blue")
    put(sc, merge(cw), mCW, "crates_white")

    # aluminum stack + beige case
    put(sc, merge([box(1.15, .5, .72, 5.55, .27 + i * .52, -6.0, ry=(i - 1) * 3) for i in range(3)]),
        mAlum, "alum_stack")
    put(sc, box(1.6, 2.2, 1.4, 7.6, 1.1, -4.6), mBeige, "beige_case")

    # ---- all dark steel merged into ONE mesh ----
    st = []
    def frame(cx, cy, cz, w, h, d):
        hw, hd, hh = w / 2 - .06, d / 2 - .06, h / 2 - .06
        for sx in (-1, 1):
            for sz in (-1, 1):
                st.append(box(.12, h, .12, cx + sx * hw, cy, cz + sz * hd))
        for sy in (-1, 1):
            st.append(box(w, .12, .12, cx, cy + sy * hh, cz - hd))
            st.append(box(w, .12, .12, cx, cy + sy * hh, cz + hd))
            st.append(box(.12, .12, d, cx - hw, cy + sy * hh, cz))
            st.append(box(.12, .12, d, cx + hw, cy + sy * hh, cz))
    frame(-6.15, 2.6, -1.5, 2.7, 5.2, 9)
    frame(-.7, 1.3, -7.8, 3, 2.6, 2.44)
    frame(2.3, 1.3, -7.8, 3, 2.6, 2.44)
    frame(.8, 3.9, -7.8, 6.1, 2.6, 2.44)
    for i in range(6):  # hanging chain
        t = torus(.055, .016, 12, 8)
        t.apply_transform(T(-4.78, 2.62 - i * .11, 2.7, rx=90, ry=90 if i % 2 else 0))
        st.append(t)
    hook = torus(.09, .02, 12, 8)
    hook.apply_transform(T(-4.78, 1.86, 2.7, rz=35))
    st.append(hook)
    st.append(box(.1, .5, .1, -4.8, 2.9, 2.7))
    for s in (-1, 1):  # X lashing braces + clamps
        st.append(cylY(.035, 4.6, .8, 3.9, -6.55, sec=8, rz=s * 35.6))
        for e in (-1, 1):
            st.append(box(.16, .16, .09, .8 + e * 1.87, 3.9 + e * s * 1.34, -6.55))
    for i in range(12):  # lashing plates + rings
        t = i / 11
        x = -6 + 12 * t + float(rng.uniform(-.7, .7))
        z = 3 - 10 * t + float(rng.uniform(-.8, .8))
        st.append(box(.24, .025, .15, x, .015, z, ry=float(rng.uniform(0, 90))))
        ring = torus(.05, .014, 10, 6)
        ring.apply_transform(T(x, .04, z))
        st.append(ring)
    st.append(box(1.7, .12, 1.2, 4.9, .06, -5.4))  # pallet
    for i in range(3):  # case latches
        for sx in (-.35, .35):
            st.append(box(.12, .1, .06, 5.55 + sx, .42 + i * .52, -5.62))
    st.append(box(1.6, 7, 1.2, -3.6, 3.5, -13.5))  # mast
    st.append(box(3.4, .25, .25, -3.6, 6.4, -13.5))
    st.append(box(.25, 2.4, .25, -2.4, 5.2, -13.5))
    for i in range(9):
        st.append(box(.5, .05, .05, -2.72, .7 + i * .7, -12.86))
    st.append(box(.05, 6.4, .05, -2.95, 3.6, -12.86))
    st.append(box(.05, 6.4, .05, -2.5, 3.6, -12.86))
    st.append(cylY(.12, 5, -1, 2.4, -12.5, rz=90))  # horizontal pipe
    st.append(box(7, 1.6, .25, 5.5, .8, -10.8))  # ship wall
    for i in range(9):
        st.append(box(.05, 1, .05, -7 + i * 1.75, .5, -8.9))
    st.append(box(15, .05, .05, .1, 1.0, -8.9))
    st.append(box(.08, 1.1, .08, 6.9, .55, -10.4))  # helmet post
    st.append(align_cyl(.11, (8.5, 10.5, -7), (2.2, 5.2, -4.2)))  # crane boom
    pul = torus(.22, .06, 14, 8)
    pul.apply_transform(T(2.2, 5.05, -4.2))
    st.append(pul)
    for a, b in [((2.2, 5, -4.2), (-1.5, .1, -6.5)), ((2.2, 5, -4.2), (.5, .1, -7.2)),
                 ((2.2, 5, -4.2), (3.8, 2.6, -7.6)), ((10, 12, -5), (2.2, 5.05, -4.2)),
                 ((10.5, 11, -6.5), (2.35, 5.1, -4.25)), ((9.5, 12.5, -4), (2.1, 5.15, -4.1)),
                 ((-3.6, 7, -13.5), (-6.2, 5.2, -6)), ((-3.6, 7, -13.5), (.8, 5.2, -7.8))]:
        st.append(align_cyl(.012, a, b, sec=6))
    put(sc, merge(st), steel, "steel_merged")

    helmet = trimesh.creation.uv_sphere(radius=.16, count=[16, 10])
    helmet.apply_transform(T(6.9, 1.12, -10.4))
    put(sc, helmet, white, "helmet")
    put(sc, box(.5, .18, .3, -3.6, 6.9, -13.2), lamp, "lamp")
    put(sc, quad((-120, -.55, 80), (120, -.55, 80), (120, -.55, -160), (-120, -.55, -160)), seaM, "sea",
        uvfn=lambda m: m.visual.uv)

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sc.export(out)
    chk = trimesh.load(out)
    tris = sum(len(g.faces) for g in chk.geometry.values())
    print(f"OK {out} | nodes={len(chk.geometry)} tris={tris} size={os.path.getsize(out)/1024:.0f} KB")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="assets/lobby.glb")
    main(ap.parse_args().out)
