#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Block Harbor — Environment Enhancer v1.1
GLB ساده را می‌گیرد و یک GLB حرفه‌ای با رنگ‌بندی بندری/جنگی + جزئیات تحویل می‌دهد.
وابستگی‌ها: numpy, pillow
تغییرات v1.1: رفع کرش tex_wood، اصلاح وایندینگ استوانه‌ها، اصلاح محور سیم خارخاری،
ارث‌بری رنگ پنل‌های کانتینر از بدنه، extensionsUsed پویا.
"""
import argparse, io, json, math, os, random, struct, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---------------------------------------------------------------- GLB I/O
def read_glb(path):
    data = open(path, 'rb').read()
    if data[:4] != b'glTF':
        sys.exit(f"[ERROR] '{path}' یک GLB معتبر نیست (magic='glTF' ندارد).")
    ver, total = struct.unpack_from('<II', data, 4)
    if ver != 2: sys.exit("[ERROR] فقط glTF 2.0 پشتیبانی می‌شود.")
    off, gj, bin_ = 12, None, None
    while off < total:
        clen, ctype = struct.unpack_from('<I4s', data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == b'JSON': gj = json.loads(chunk.decode('utf-8'))
        elif ctype == b'BIN\x00': bin_ = chunk
        off += 8 + clen
    if gj is None or bin_ is None: sys.exit("[ERROR] chunk های JSON/BIN ناقص است.")
    return gj, bin_

def write_glb(path, gj, bin_):
    jb = json.dumps(gj, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    jb += b' ' * ((4 - len(jb) % 4) % 4)
    bb = bin_ + b'\x00' * ((4 - len(bin_) % 4) % 4)
    total = 12 + 8 + len(jb) + 8 + len(bb)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(struct.pack('<4sII', b'glTF', 2, total))
        f.write(struct.pack('<I4s', len(jb), b'JSON')); f.write(jb)
        f.write(struct.pack('<I4s', len(bb), b'BIN\x00')); f.write(bb)

COMP = {5120: ('i1', 1), 5121: ('u1', 1), 5122: ('i2', 2),
        5123: ('u2', 2), 5125: ('u4', 4), 5126: ('f4', 4)}
NCOMP = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}

def acc_array(gj, bin_, idx):
    a = gj['accessors'][idx]
    if 'sparse' in a: sys.exit("[ERROR] accessor sparse پشتیبانی نمی‌شود.")
    bv = gj['bufferViews'][a['bufferView']]
    dt, cs = COMP[a['componentType']]; n = NCOMP[a['type']]
    stride = bv.get('byteStride', n * cs)
    start = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    return np.ndarray((a['count'], n), dtype=np.dtype('<' + dt),
                      buffer=bin_, offset=start, strides=(stride, cs))

def node_matrix(n):
    if 'matrix' in n:
        return np.array(n['matrix'], dtype=np.float64).reshape(4, 4).T
    M = np.eye(4)
    if 'scale' in n: M = M @ np.diag(n['scale'] + [1.0])
    if 'rotation' in n:
        x, y, z, w = n['rotation']; R = np.eye(4)
        R[0, 0] = 1 - 2 * (y * y + z * z); R[0, 1] = 2 * (x * y - z * w); R[0, 2] = 2 * (x * z + y * w)
        R[1, 0] = 2 * (x * y + z * w); R[1, 1] = 1 - 2 * (x * x + z * z); R[1, 2] = 2 * (y * z - x * w)
        R[2, 0] = 2 * (x * z - y * w); R[2, 1] = 2 * (y * z + x * w); R[2, 2] = 1 - 2 * (x * x + y * y)
        M = M @ R
    if 'translation' in n:
        T = np.eye(4); T[:3, 3] = n['translation']; M = T @ M
    return M

# ---------------------------------------------------------------- Buffer writer
class BinWriter:
    def __init__(self): self.buf = bytearray()
    def add(self, blob):
        self.buf += b'\x00' * ((4 - len(self.buf) % 4) % 4)
        off = len(self.buf); self.buf += blob
        return off, len(blob)

# ---------------------------------------------------------------- Textures
FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "C:/Windows/Fonts/arialbd.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
def get_font(px):
    for p in FONT_PATHS:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, px)
            except Exception: pass
    try: return ImageFont.load_default(size=px)
    except TypeError: return ImageFont.load_default()

def hexrgb(h):
    h = h.lstrip('#'); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def noise(rng, s, amp): return rng.integers(-amp, amp + 1, (s, s, 1)).astype(np.float32)
def to_img(a): return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')

def rust_layer(rng, s, n_streak, n_spot):
    lay = Image.new('RGBA', (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for _ in range(n_streak):
        x = int(rng.integers(0, s)); y = int(rng.integers(int(s * .4), s))
        w = int(rng.integers(2, max(3, s // 90))); h = int(rng.integers(s // 20, s // 5))
        d.rectangle([x, y, x + w, y + h], fill=(122, 66, 34, int(rng.integers(35, 80))))
    for _ in range(n_spot):
        x = int(rng.integers(0, s)); y = int(rng.integers(0, s)); r = int(rng.integers(s // 60, s // 22))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(105, 58, 30, int(rng.integers(20, 55))))
    return lay.filter(ImageFilter.GaussianBlur(max(1, s / 256)))

def tex_container(s, color, logo, rng):
    a = np.zeros((s, s, 3), np.float32); a[:] = hexrgb(color)
    x = np.arange(s, dtype=np.float32)
    rib = .80 + .20 * np.power(.5 + .5 * np.cos(2 * np.pi * x / (s / 8.0)), .8)
    a *= rib[None, :, None]
    e = max(2, int(s * .05)); a[:e] *= .78; a[-e:] *= .85
    a += noise(rng, s, 6)
    img = to_img(a).convert('RGBA')
    img = Image.alpha_composite(img, rust_layer(rng, s, 16, 10))
    d = ImageDraw.Draw(img)
    lum = sum(hexrgb(color)) / 3
    ink = (245, 245, 240, 235) if lum < 140 else (25, 28, 32, 235)
    d.text((s * .5, s * .42), logo, font=get_font(int(s * .15)), fill=ink, anchor='mm')
    code = f"BH {int(rng.integers(100000, 999999))} {int(rng.integers(0, 9))}"
    d.text((s * .06, s * .10), code, font=get_font(int(s * .055)), fill=ink, anchor='lm')
    for _ in range(8):
        x0 = int(rng.integers(0, s)); y0 = int(rng.integers(0, s))
        d.line([x0, y0, x0 + int(rng.integers(-s // 8, s // 8)), y0 + int(rng.integers(0, s // 10))],
               fill=(230, 230, 225, 40), width=1)
    return img.convert('RGB')

def tex_door(s, color, rng):
    a = np.zeros((s, s, 3), np.float32); a[:] = hexrgb(color); a += noise(rng, s, 5)
    for rx in (.30, .70):
        w = s * .035
        a[:, int(s * rx - w):int(s * rx + w)] *= 1.25
        a[:, int(s * rx - w - 2):int(s * rx - w)] *= .6
    img = to_img(a).convert('RGBA')
    img = Image.alpha_composite(img, rust_layer(rng, s, 8, 5))
    d = ImageDraw.Draw(img)
    for hy in (.15, .85):
        d.rectangle([s * .02, s * hy, s * .07, s * hy + s * .06], fill=(40, 42, 46, 255))
        d.rectangle([s * .93, s * hy, s * .98, s * hy + s * .06], fill=(40, 42, 46, 255))
    return img.convert('RGB')

def tex_wood(s, rng):
    a = np.zeros((s, s, 3), np.float32); a[:] = (146, 108, 60)
    y = np.arange(s, dtype=np.float32); x = np.arange(s, dtype=np.float32)
    row = (y // (s / 4)).astype(int)
    gap = (y % (s / 4)) < max(2, s * .015)
    grain = .9 + .1 * np.sin(2 * np.pi * x[None, :] / (s / 3) + row[:, None] * 1.7)
    a *= grain[:, :, None]
    tint = rng.uniform(.85, 1.12, 4)
    a *= tint[row][:, None, None]          # ✅ FIX: (s,1,1) broadcast روی (s,s,3)
    a[gap] *= .45; a += noise(rng, s, 8)
    img = to_img(a); d = ImageDraw.Draw(img)
    for r in range(4):
        for nx in (.08, .92):
            d.ellipse([s * nx - 2, s * (r + .5) / 4 - 2, s * nx + 2, s * (r + .5) / 4 + 2], fill=(60, 45, 30))
    return img

def tex_fence(s, rng):
    a = np.zeros((s, s, 3), np.float32); a[:] = (63, 132, 58)
    x = np.arange(s, dtype=np.float32); y = np.arange(s, dtype=np.float32)
    post = (x % (s / 4)) < s * .04
    a[:, post] *= .7
    a[:int(s * .08)] *= 1.15
    a *= (1 - .35 * (y / s) ** 2)[:, None, None]
    a += noise(rng, s, 7)
    return to_img(a)

def tex_asphalt(s, rng):
    a = np.zeros((s, s, 3), np.float32); a[:] = (43, 46, 51); a += noise(rng, s, 9)
    img = to_img(a).convert('RGBA')
    lay = Image.new('RGBA', (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for _ in range(7):
        px, py = float(rng.integers(0, s)), float(rng.integers(0, s))
        pts = [(px, py)]
        for _ in range(24):
            px += float(rng.uniform(-s / 40, s / 40)); py += float(rng.uniform(-s / 40, s / 40))
            pts.append((px, py))
        d.line(pts, fill=(20, 21, 24, 150), width=max(1, s // 256))
    for _ in range(6):
        cx, cy = int(rng.integers(0, s)), int(rng.integers(0, s)); r = int(rng.integers(s // 18, s // 7))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(15, 16, 18, 60))
    lay = lay.filter(ImageFilter.GaussianBlur(max(1, s / 300)))
    return Image.alpha_composite(img, lay).convert('RGB')

def tex_concrete(s, rng):
    a = np.zeros((s, s, 3), np.float32); a[:] = (154, 158, 162)
    g = (np.arange(s) % (s / 4)) < max(2, s * .01)
    a[g, :] *= .7; a[:, g] *= .7; a += noise(rng, s, 6)
    img = to_img(a).convert('RGBA')
    lay = Image.new('RGBA', (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for _ in range(8):
        cx, cy = int(rng.integers(0, s)), int(rng.integers(0, s)); r = int(rng.integers(s // 20, s // 8))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(90, 90, 88, 45))
    return Image.alpha_composite(img, lay.filter(ImageFilter.GaussianBlur(2))).convert('RGB')

def tex_hazard(s, rng):
    x = np.arange(s)[None, :]; y = np.arange(s)[:, None]
    stripe = (((x + y) // (s / 8)) % 2).astype(bool)
    a = np.zeros((s, s, 3), np.float32)
    a[stripe] = (224, 180, 20); a[~stripe] = (30, 30, 32)
    a += noise(rng, s, 6)
    return to_img(a)

def tex_metal(s, rng, base=(52, 56, 62)):
    a = np.zeros((s, s, 3), np.float32); a[:] = base; a += noise(rng, s, 6)
    img = to_img(a); d = ImageDraw.Draw(img)
    for _ in range(10):
        x0, y0 = int(rng.integers(0, s)), int(rng.integers(0, s))
        d.line([x0, y0, x0 + int(rng.integers(-s // 6, s // 6)), y0 + int(rng.integers(-s // 12, s // 12))],
               fill=(150, 155, 160), width=1)
    return img

def tex_barrel(s, color, rng):
    a = np.zeros((s, s, 3), np.float32); a[:] = hexrgb(color)
    y = np.arange(s, dtype=np.float32)
    for ry in (.30, .70):
        band = np.abs(y - s * ry) < s * .03
        a[band] *= 1.25
    a[:int(s * .05)] *= .7; a[-int(s * .05):] *= .7
    a += noise(rng, s, 5)
    img = to_img(a).convert('RGBA')
    return Image.alpha_composite(img, rust_layer(rng, s, 6, 4)).convert('RGB')

def tex_crate(s, rng):
    a = np.zeros((s, s, 3), np.float32); a[:] = (91, 107, 58)
    b = int(s * .08)
    a[:b] *= .7; a[-b:] *= .7; a[:, :b] *= .7; a[:, -b:] *= .7
    a += noise(rng, s, 6)
    img = to_img(a); d = ImageDraw.Draw(img)
    d.text((s * .5, s * .40), "BH SUPPLY", font=get_font(int(s * .12)), fill=(235, 235, 225), anchor='mm')
    cx, cy, R, r = s * .5, s * .68, s * .10, s * .045
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = R if i % 2 == 0 else r
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    d.polygon(pts, fill=(235, 235, 225))
    return img

def jpeg_bytes(img, q=82):
    b = io.BytesIO(); img.save(b, 'JPEG', quality=q, optimize=True); return b.getvalue()

# ---------------------------------------------------------------- Geometry builder
class MeshBuilder:
    def __init__(self):
        self.p, self.n, self.u, self.i = [], [], [], []
    def _v(self, pos, nrm, uv):
        self.p.append(pos); self.n.append(nrm); self.u.append(uv)
        return len(self.p) - 1
    def quad(self, p0, p1, p2, p3, nrm):
        a = self._v(p0, nrm, (0, 0)); b = self._v(p1, nrm, (1, 0))
        c = self._v(p2, nrm, (1, 1)); d = self._v(p3, nrm, (0, 1))
        self.i += [a, b, c, a, c, d]
    def box(self, cx, cy, cz, sx, sy, sz):
        x0, x1 = cx - sx / 2, cx + sx / 2; y0, y1 = cy - sy / 2, cy + sy / 2
        z0, z1 = cz - sz / 2, cz + sz / 2
        self.quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), (0, 0, 1))
        self.quad((x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (0, 0, -1))
        self.quad((x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (1, 0, 0))
        self.quad((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0), (-1, 0, 0))
        self.quad((x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0), (0, 1, 0))
        self.quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), (0, -1, 0))
    def cylinder(self, cx, cy, cz, r, h, seg=16):
        y0, y1 = cy, cy + h
        for i in range(seg):
            t0, t1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
            n0 = (math.cos(t0), 0, math.sin(t0)); n1 = (math.cos(t1), 0, math.sin(t1))
            p0 = (cx + r * n0[0], y0, cz + r * n0[2]); p1 = (cx + r * n1[0], y0, cz + r * n1[2])
            p2 = (cx + r * n1[0], y1, cz + r * n1[2]); p3 = (cx + r * n0[0], y1, cz + r * n0[2])
            a = self._v(p0, n0, (i / seg, 0)); b = self._v(p1, n1, ((i + 1) / seg, 0))
            c = self._v(p2, n1, ((i + 1) / seg, 1)); d = self._v(p3, n0, (i / seg, 1))
            self.i += [a, d, c, a, c, b]          # ✅ FIX: وایندینگ رو به بیرون
        for yy, nn in ((y1, (0, 1, 0)), (y0, (0, -1, 0))):
            c0 = self._v((cx, yy, cz), nn, (.5, .5))
            ring = []
            for i in range(seg):
                t = 2 * math.pi * i / seg
                ring.append(self._v((cx + r * math.cos(t), yy, cz + r * math.sin(t)), nn,
                                    (.5 + .5 * math.cos(t), .5 + .5 * math.sin(t))))
            for i in range(seg):
                a, b = ring[i], ring[(i + 1) % seg]
                self.i += [c0, b, a] if nn[1] > 0 else [c0, a, b]   # ✅ FIX: کپ‌ها
    def arrays(self):
        return (np.asarray(self.p, np.float32), np.asarray(self.n, np.float32),
                np.asarray(self.u, np.float32),
                np.asarray(self.i, np.uint32 if len(self.p) > 65535 else np.uint16))

# ---------------------------------------------------------------- Main
PALETTE = ['#b3382e', '#2e6da3', '#d9a521', '#3f7f4f', '#c96a2b',
           '#7a8894', '#20655f', '#8a2f3c', '#4a5568', '#b9bec4']
LOGOS = ["BH LINES", "BLOCK HARBOR", "NIGHT COURIER", "BHC", "HARBOR CO", "CARGO-X"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--output', default='dist/environment_enhanced.glb')
    ap.add_argument('--report', default='dist/report.json')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--detail', choices=['low', 'standard', 'high'], default='standard')
    ap.add_argument('--tex-size', type=int, default=0)
    ap.add_argument('--no-props', action='store_true')
    ap.add_argument('--no-wire', action='store_true')
    args = ap.parse_args()

    S_TEX = args.tex_size or {'low': 256, 'standard': 512, 'high': 1024}[args.detail]
    PROP_MUL = {'low': .5, 'standard': 1.0, 'high': 1.5}[args.detail]
    rng = np.random.default_rng(args.seed)
    prng = random.Random(args.seed)

    gj, bin_ = read_glb(args.input)
    print(f"[i] input: {args.input}  meshes={len(gj.get('meshes', []))}  nodes={len(gj.get('nodes', []))}")

    # ---- world AABB per primitive
    entries = []
    def walk(ni, parent):
        n = gj['nodes'][ni]; W = parent @ node_matrix(n)
        if 'mesh' in n:
            for pi, prim in enumerate(gj['meshes'][n['mesh']]['primitives']):
                pa = gj['accessors'][prim['attributes']['POSITION']]
                mn = np.array(pa.get('min') or acc_array(gj, bin_, prim['attributes']['POSITION']).min(0))
                mx = np.array(pa.get('max') or acc_array(gj, bin_, prim['attributes']['POSITION']).max(0))
                corners = np.array([[x, y, z, 1] for x in (mn[0], mx[0])
                                    for y in (mn[1], mx[1]) for z in (mn[2], mx[2])])
                wc = (W @ corners.T).T[:, :3]
                lo, hi = wc.min(0), wc.max(0)
                uv_span = 0.0
                if 'TEXCOORD_0' in prim['attributes']:
                    uv = acc_array(gj, bin_, prim['attributes']['TEXCOORD_0'])
                    uv_span = float((uv.max(0) - uv.min(0)).max())
                entries.append(dict(node=ni, mesh=n['mesh'], prim=pi,
                                    name=n.get('name', gj['meshes'][n['mesh']].get('name', f'm{ni}')),
                                    lo=lo, hi=hi, size=hi - lo, center=(hi + lo) / 2,
                                    mat=prim.get('material', -1), uv_span=uv_span))
        for c in n.get('children', []): walk(c, W)
    for r in gj['scenes'][gj.get('scene', 0)]['nodes']: walk(r, np.eye(4))
    if not entries: sys.exit("[ERROR] هیچ mesh ای پیدا نشد.")

    scene_lo = np.min([e['lo'] for e in entries], 0)
    scene_hi = np.max([e['hi'] for e in entries], 0)
    S = float(max(scene_hi[0] - scene_lo[0], scene_hi[2] - scene_lo[2]))

    # ---- classification
    for e in entries:
        sx, sy, sz = e['size']; h = sorted([sx, sz]); nm = e['name'].lower()
        if e['mat'] in (3, 4) or (sy <= .03 * S and h[1] >= .35 * S):
            e['cls'] = 'ground_concrete' if e['mat'] in (3, 4) else 'ground_asphalt'
        elif e['mat'] == 1 or any(k in nm for k in ('wood', 'plank')):
            e['cls'] = 'wood'
        elif any(k in nm for k in ('door', 'frame', 'f1', 'f2', 'df1', 'df2')):
            e['cls'] = 'door'
        elif h[0] <= .015 * S and h[1] >= .05 * S and .02 * S <= sy <= .15 * S:
            e['cls'] = 'fence'
        elif e['mat'] == 5:
            e['cls'] = 'metal'
        elif min(sx, sy, sz) >= .02 * S and max(sx, sy, sz) >= .07 * S and \
                1.4 <= max(sx, sy, sz) / max(1e-6, sorted([sx, sy, sz])[1]) <= 3.6:
            e['cls'] = 'container'
        else:
            e['cls'] = 'metal'

    containers = [e for e in entries if e['cls'] == 'container']
    containers.sort(key=lambda e: (round(e['center'][0] / (.05 * S)),
                                   round(e['center'][2] / (.05 * S)), e['center'][1]))
    for i, e in enumerate(containers): e['color'] = (i * 3 + args.seed) % len(PALETTE)
    for i, e in enumerate([e for e in entries if e['cls'] == 'door']):
        e['color'] = (i * 5 + 2) % len(PALETTE)

    # ---- v1.1: پنل‌های نازکِ چسبیده به بدنه، رنگ همان کانتینر را می‌گیرند
    pad = .02 * S
    for e in entries:
        if e['cls'] != 'metal': continue
        sx, sy, sz = e['size']
        if min(sx, sz) > .02 * S or sy < .05 * S: continue
        c = e['center']
        for k in containers:
            if (k['lo'][0] - pad <= c[0] <= k['hi'][0] + pad and
                k['lo'][1] - pad <= c[1] <= k['hi'][1] + pad and
                k['lo'][2] - pad <= c[2] <= k['hi'][2] + pad):
                long_dim = max(sx, sz)
                e['cls'] = 'container' if long_dim >= .35 * max(k['size'][0], k['size'][2]) else 'door'
                e['color'] = k['color']
                break

    grounds = [e for e in entries if e['cls'].startswith('ground')]
    if grounds:
        gmain = max(grounds, key=lambda e: e['size'][0] * e['size'][2])
        ground_top = float(gmain['hi'][1]); bounds = (gmain['lo'], gmain['hi'])
    else:
        ground_top = float(scene_lo[1]); bounds = (scene_lo, scene_hi)
    u = float(np.median([e['size'][1] for e in containers])) if containers else .05 * S

    counts = {}
    for e in entries: counts[e['cls']] = counts.get(e['cls'], 0) + 1
    print("[i] classification:", counts)

    # ---- rebuild buffer (keep geometry only) + new assets
    used_bv = sorted({gj['accessors'][a]['bufferView'] for a in range(len(gj['accessors']))})
    bw = BinWriter(); new_bvs = []; remap = {}
    for old in used_bv:
        bv = gj['bufferViews'][old]
        off, ln = bw.add(bin_[bv.get('byteOffset', 0): bv.get('byteOffset', 0) + bv['byteLength']])
        nb = dict(bv); nb['byteOffset'] = off; nb['buffer'] = 0
        remap[old] = len(new_bvs); new_bvs.append(nb)
    for a in gj['accessors']: a['bufferView'] = remap[a['bufferView']]

    textures, images, materials = [], [], []
    tex_cache, mat_cache = {}, {}
    def add_tex(key, maker):
        if key in tex_cache: return tex_cache[key]
        blob = jpeg_bytes(maker())
        off, ln = bw.add(blob)
        new_bvs.append({'buffer': 0, 'byteOffset': off, 'byteLength': ln})
        images.append({'bufferView': len(new_bvs) - 1, 'mimeType': 'image/jpeg', 'name': key})
        textures.append({'sampler': 0, 'source': len(images) - 1})
        tex_cache[key] = len(textures) - 1
        return tex_cache[key]
    def add_mat(key, texkey, maker, metallic, rough, tiled, emissive=None):
        mk = (key, tiled)
        if mk in mat_cache: return mat_cache[mk]
        m = {'name': key + ('_tiled' if tiled else ''), 'doubleSided': True,
             'pbrMetallicRoughness': {'metallicFactor': metallic, 'roughnessFactor': rough}}
        if texkey is not None:
            ti = add_tex(texkey, maker)
            bt = {'index': ti}
            if tiled: bt['extensions'] = {'KHR_texture_transform': {'scale': [0.005, 0.005]}}
            m['pbrMetallicRoughness']['baseColorTexture'] = bt
        if emissive:
            m['emissiveFactor'] = emissive
            m['extensions'] = {'KHR_materials_emissive_strength': {'emissiveStrength': 3.0}}
        mat_cache[mk] = len(materials); materials.append(m)
        return mat_cache[mk]

    def surf_mat(e, kind):
        tiled = e['uv_span'] > 50
        if kind == 'container':
            c = e['color']; logo = LOGOS[c % len(LOGOS)]
            return add_mat(f'BH_Container_{c}', f'cont_{c}_{S_TEX}',
                           lambda: tex_container(S_TEX, PALETTE[c], logo, np.random.default_rng(args.seed + c)),
                           .12, .58, tiled)
        if kind == 'door':
            c = e['color']
            return add_mat(f'BH_Door_{c}', f'door_{c}_{S_TEX}',
                           lambda: tex_door(S_TEX, PALETTE[c], np.random.default_rng(args.seed + 40 + c)),
                           .15, .55, tiled)
        if kind == 'wood':
            return add_mat('BH_Wood', f'wood_{S_TEX}', lambda: tex_wood(S_TEX, np.random.default_rng(args.seed + 1)),
                           0.0, .8, tiled)
        if kind == 'fence':
            return add_mat('BH_Fence', f'fence_{S_TEX}', lambda: tex_fence(S_TEX, np.random.default_rng(args.seed + 2)),
                           .05, .7, tiled)
        if kind == 'ground_asphalt':
            return add_mat('BH_Asphalt', f'asph_{S_TEX}', lambda: tex_asphalt(S_TEX, np.random.default_rng(args.seed + 3)),
                           0.0, .95, tiled)
        if kind == 'ground_concrete':
            return add_mat('BH_Concrete', f'conc_{S_TEX}', lambda: tex_concrete(S_TEX, np.random.default_rng(args.seed + 4)),
                           0.0, .9, tiled)
        return add_mat('BH_Gunmetal', f'metal_{S_TEX}', lambda: tex_metal(S_TEX, np.random.default_rng(args.seed + 5)),
                       .35, .5, tiled)

    for e in entries:
        gj['meshes'][e['mesh']]['primitives'][e['prim']]['material'] = surf_mat(e, e['cls'])

    # ---- props
    obstacles = [(e['lo'], e['hi']) for e in entries if e['cls'] in ('container', 'fence', 'metal')]
    def free(x, z, r):
        if not (bounds[0][0] + r < x < bounds[1][0] - r and bounds[0][2] + r < z < bounds[1][2] - r):
            return False
        for lo, hi in obstacles:
            if lo[0] - r < x < hi[0] + r and lo[2] - r < z < hi[2] + r: return False
        return True
    def spot_near(e, r, tries=60):
        for _ in range(tries):
            ax = prng.choice([0, 2]); side = prng.choice([-1, 1])
            x = e['center'][0] + (side * (e['size'][0] / 2 + r * 1.6) if ax == 0 else prng.uniform(-e['size'][0] / 2, e['size'][0] / 2))
            z = e['center'][2] + (side * (e['size'][2] / 2 + r * 1.6) if ax == 2 else prng.uniform(-e['size'][2] / 2, e['size'][2] / 2))
            if free(x, z, r): return x, z
        return None

    prop_nodes = []
    def add_prop_mesh(name, builder, mat):
        p, n, uv, idx = builder.arrays()
        if len(p) == 0: return
        attrs = {}
        for key, arr, typ in (('POSITION', p, 'VEC3'), ('NORMAL', n, 'VEC3'), ('TEXCOORD_0', uv, 'VEC2')):
            off, ln = bw.add(arr.tobytes())
            new_bvs.append({'buffer': 0, 'byteOffset': off, 'byteLength': ln, 'target': 34962})
            a = {'bufferView': len(new_bvs) - 1, 'componentType': 5126, 'count': len(arr), 'type': typ}
            if key == 'POSITION': a['min'] = arr.min(0).tolist(); a['max'] = arr.max(0).tolist()
            gj['accessors'].append(a); attrs[key] = len(gj['accessors']) - 1
        off, ln = bw.add(idx.tobytes())
        new_bvs.append({'buffer': 0, 'byteOffset': off, 'byteLength': ln, 'target': 34963})
        gj['accessors'].append({'bufferView': len(new_bvs) - 1,
                                'componentType': 5125 if idx.dtype == np.uint32 else 5123,
                                'count': len(idx), 'type': 'SCALAR'})
        gj['meshes'].append({'name': name, 'primitives': [
            {'attributes': attrs, 'indices': len(gj['accessors']) - 1, 'material': mat, 'mode': 4}]})
        gj['nodes'].append({'mesh': len(gj['meshes']) - 1, 'name': name})
        prop_nodes.append(len(gj['nodes']) - 1)

    placed = {}
    if not args.no_props and containers:
        mb_bar = {c: MeshBuilder() for c in ('#2e6da3', '#b3382e', '#b9bec4', '#c96a2b')}
        mb_pal, mb_crate, mb_tire, mb_pole, mb_lamp, mb_pad = (MeshBuilder() for _ in range(6))
        n_clusters = max(1, int(5 * PROP_MUL))
        for _ in range(n_clusters):
            e = prng.choice(containers); sp = spot_near(e, .12 * u)
            if not sp: continue
            col = prng.choice(list(mb_bar))
            for k in range(prng.randint(3, 5)):
                bx, bz = sp[0] + prng.uniform(-.18, .18) * u, sp[1] + prng.uniform(-.18, .18) * u
                if free(bx, bz, .12 * u):
                    mb_bar[col].cylinder(bx, ground_top, bz, .11 * u, .34 * u)
                    placed['barrels'] = placed.get('barrels', 0) + 1
        for _ in range(max(1, int(7 * PROP_MUL))):
            e = prng.choice(containers); sp = spot_near(e, .25 * u)
            if sp:
                mb_pal.box(sp[0], ground_top + .025 * u, sp[1], .45 * u, .05 * u, .45 * u)
                placed['pallets'] = placed.get('pallets', 0) + 1
        for _ in range(max(1, int(6 * PROP_MUL))):
            e = prng.choice(containers); sp = spot_near(e, .16 * u)
            if sp:
                mb_crate.box(sp[0], ground_top + .15 * u, sp[1], .3 * u, .3 * u, .3 * u)
                placed['crates'] = placed.get('crates', 0) + 1
        for _ in range(max(1, int(4 * PROP_MUL))):
            e = prng.choice(containers); sp = spot_near(e, .14 * u)
            if sp:
                for k in range(3):
                    mb_tire.cylinder(sp[0], ground_top + k * .09 * u, sp[1], .13 * u, .09 * u, 14)
                placed['tire_stacks'] = placed.get('tire_stacks', 0) + 1
        for _ in range(max(1, int(6 * PROP_MUL))):
            e = prng.choice(containers); sp = spot_near(e, .45 * u)
            if sp:
                mb_pad.box(sp[0], ground_top + .006 * u, sp[1], .9 * u, .012 * u, .5 * u)
                placed['hazard_pads'] = placed.get('hazard_pads', 0) + 1
        ix = .06 * S
        for cx, cz in ((bounds[0][0] + ix, bounds[0][2] + ix), (bounds[1][0] - ix, bounds[0][2] + ix),
                       (bounds[0][0] + ix, bounds[1][2] - ix), (bounds[1][0] - ix, bounds[1][2] - ix)):
            if not free(cx, cz, .1 * u): continue
            mb_pole.cylinder(cx, ground_top, cz, .03 * u, 2.3 * u, 10)
            mb_pole.box(cx, ground_top + 2.3 * u, cz, .24 * u, .12 * u, .14 * u)
            mb_lamp.box(cx, ground_top + 2.235 * u, cz, .20 * u, .01 * u, .11 * u)
            placed['floodlights'] = placed.get('floodlights', 0) + 1

        m_bar = {c: add_mat(f'BH_Barrel_{c}', f'bar_{c}_{S_TEX}',
                            lambda c=c: tex_barrel(S_TEX, c, np.random.default_rng(args.seed + 60)),
                            .2, .5, False) for c in mb_bar}
        for c, b in mb_bar.items(): add_prop_mesh(f'BH_Barrels_{c}', b, m_bar[c])
        add_prop_mesh('BH_Pallets', mb_pal, add_mat('BH_Wood', f'wood_{S_TEX}',
                      lambda: tex_wood(S_TEX, np.random.default_rng(args.seed + 1)), 0, .8, False))
        add_prop_mesh('BH_Crates', mb_crate, add_mat('BH_Crate', f'crate_{S_TEX}',
                      lambda: tex_crate(S_TEX, np.random.default_rng(args.seed + 6)), 0, .75, False))
        add_prop_mesh('BH_Tires', mb_tire, add_mat('BH_Rubber', f'rub_{S_TEX}',
                      lambda: tex_metal(S_TEX, np.random.default_rng(args.seed + 7), (24, 25, 27)), 0, .95, False))
        add_prop_mesh('BH_HazardPads', mb_pad, add_mat('BH_Hazard', f'haz_{S_TEX}',
                      lambda: tex_hazard(S_TEX, np.random.default_rng(args.seed + 8)), 0, .8, False))
        add_prop_mesh('BH_FloodlightMasts', mb_pole, add_mat('BH_Gunmetal', f'metal_{S_TEX}',
                      lambda: tex_metal(S_TEX, np.random.default_rng(args.seed + 5)), .35, .5, False))
        add_prop_mesh('BH_FloodlightLamps', mb_lamp, add_mat('BH_Lamp', None, None, 0, .4, False,
                      emissive=[1.0, .96, .82]))

    # ---- razor wire on fences (LINES)
    wire_verts = 0
    fences = [e for e in entries if e['cls'] == 'fence']
    if not args.no_wire and fences:
        pts = []
        r, pitch = .04 * u, .09 * u
        for e in fences:
            ax = 0 if e['size'][0] >= e['size'][2] else 2
            perp = 2 if ax == 0 else 0                 # ✅ FIX: محور عمود افقی
            L = e['size'][ax]; steps = max(8, int(L / pitch * 8))
            prev = None
            for i in range(steps + 1):
                t = L * i / steps; th = 2 * math.pi * t / pitch
                p = [0.0, 0.0, 0.0]
                p[ax] = float(e['lo'][ax]) + t
                p[perp] = float(e['center'][perp]) + r * math.sin(th)
                p[1] = float(e['hi'][1]) + r * .6 + r * math.cos(th)
                if prev is not None: pts += [prev, p]
                prev = p
        if pts:
            arr = np.asarray(pts, np.float32); wire_verts = len(arr)
            off, ln = bw.add(arr.tobytes())
            new_bvs.append({'buffer': 0, 'byteOffset': off, 'byteLength': ln, 'target': 34962})
            gj['accessors'].append({'bufferView': len(new_bvs) - 1, 'componentType': 5126,
                                    'count': len(arr), 'type': 'VEC3',
                                    'min': arr.min(0).tolist(), 'max': arr.max(0).tolist()})
            materials.append({'name': 'BH_RazorWire',
                              'pbrMetallicRoughness': {'baseColorFactor': [.16, .17, .19, 1],
                                                       'metallicFactor': 0, 'roughnessFactor': .9}})
            gj['meshes'].append({'name': 'BH_RazorWire', 'primitives': [
                {'attributes': {'POSITION': len(gj['accessors']) - 1},
                 'material': len(materials) - 1, 'mode': 1}]})
            gj['nodes'].append({'mesh': len(gj['meshes']) - 1, 'name': 'BH_RazorWire'})
            prop_nodes.append(len(gj['nodes']) - 1)

    # ---- finalize glTF
    if prop_nodes:
        gj['nodes'].append({'name': 'BH_Enhanced_Details', 'children': prop_nodes})
        gj['scenes'][gj.get('scene', 0)]['nodes'].append(len(gj['nodes']) - 1)
    gj['bufferViews'] = new_bvs
    gj['buffers'] = [{'byteLength': len(bw.buf)}]
    gj['materials'] = materials
    gj['textures'] = textures
    gj['images'] = images
    gj['samplers'] = [{'magFilter': 9729, 'minFilter': 9987, 'wrapS': 10497, 'wrapT': 10497}]
    used_ext = ['KHR_texture_transform']
    if any('KHR_materials_emissive_strength' in m.get('extensions', {}) for m in materials):
        used_ext.append('KHR_materials_emissive_strength')
    gj['extensionsUsed'] = used_ext
    gj.setdefault('asset', {})['generator'] = 'BlockHarbor Enhancer 1.1'

    write_glb(args.output, gj, bytes(bw.buf))
    report = {'input': args.input, 'output': args.output, 'seed': args.seed, 'detail': args.detail,
              'tex_size': S_TEX, 'classification': counts, 'props': placed,
              'wire_vertices': wire_verts, 'materials': len(materials),
              'output_bytes': os.path.getsize(args.output),
              'mesh_classes': {e['name']: e['cls'] for e in entries}}
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    json.dump(report, open(args.report, 'w'), indent=2, ensure_ascii=False)
    print(f"[✓] wrote {args.output} ({os.path.getsize(args.output) / 1e6:.2f} MB) "
          f"materials={len(materials)} props={placed}")

if __name__ == '__main__':
    main()
