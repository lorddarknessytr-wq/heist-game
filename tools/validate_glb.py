import sys, json, struct
p = sys.argv[1]
d = open(p, 'rb').read()
magic, ver, length = struct.unpack('<4sII', d[:12])
assert magic == b'glTF' and ver == 2 and length == len(d), 'bad GLB header'
clen, ctype = struct.unpack('<II', d[12:20])
assert ctype == 0x4E4F534A, 'first chunk is not JSON'
j = json.loads(d[20:20 + clen])
tris = sum(j['accessors'][pr['indices']]['count'] // 3
           for m in j['meshes'] for pr in m['primitives'] if 'indices' in pr)
names = {n.get('name') for n in j['nodes']}
need = {'SLOT_0', 'SLOT_1', 'SLOT_2', 'SLOT_3', 'CAM_POS', 'CAM_TARGET'}
print(f"size={len(d)//1024}KB meshes={len(j['meshes'])} materials={len(j.get('materials', []))} "
      f"images={len(j.get('images', []))} triangles={tris}")
bad = []
if tris > 60000: bad.append('triangles > 60000')
if len(j['meshes']) > 40: bad.append('draw calls > 40')
if not need <= names: bad.append(f'missing nodes: {need - names}')
if bad:
    print('FAIL:', '; '.join(bad)); sys.exit(1)
print('GLB OK')
