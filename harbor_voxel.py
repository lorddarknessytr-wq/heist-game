# =============================================================================
# PROJECT 02 - ORIGINAL VOXEL CONTAINER HARBOR
# Target: Blender 4.2+  |  Output: environment.glb
# Fully procedural. No external assets, no plugins.
# =============================================================================
import bpy, bmesh, math, os, sys, random
from mathutils import Matrix, Vector, Euler

# ----------------------------- GLOBAL CONSTANTS -----------------------------
W, L, HMAX = 56.0, 44.0, 12.0          # world bounds
TEX_WORLD = 4.0                        # one texture tile = 4 world units
VOX = 0.25                             # detail grid
RNG = random.Random(20261112)

COL_NAMES = ["ENVIRONMENT_GEO", "CONTAINERS", "INDUSTRIAL_PROPS", "LIGHTING", "COLLISION"]
COLS = {}
ROOTS = {}

# ----------------------------- PIXEL FONT (3x5) -----------------------------
FONT = {
 'A':'010101111101101','B':'110101110101110','C':'011100100100011','D':'110101101101110',
 'E':'111100110100111','F':'111100110100100','G':'011100101101011','H':'101101111101101',
 'I':'111010010010111','J':'001001001101010','K':'101101110101101','L':'100100100100111',
 'M':'101111101101101','N':'110101101101101','O':'010101101101010','P':'110101110100100',
 'Q':'010101101111011','R':'110101110101101','S':'011100010001110','T':'111010010010010',
 'U':'101101101101111','V':'101101101101101010'[:15],'W':'101101111111101','X':'101101010101101',
 'Y':'101101010010010','Z':'111001010100111',
 '0':'111101101101111','1':'010110010010111','2':'111001111100111','3':'111001111001111',
 '4':'101101111001001','5':'111100111001111','6':'111100111101111','7':'111001001010010',
 '8':'111101111101111','9':'111101111001111',
 '-':'000000111000000','.':'000000000000010',' ':'000000000000000',
}

def text_pixels(text):
    text = text.upper()
    w = max(1, len(text)*4-1); h = 5
    grid = [[0]*w for _ in range(h)]
    for i,ch in enumerate(text):
        pat = FONT.get(ch, FONT[' '])
        for r in range(5):
            for c in range(3):
                if pat[r*3+c]=='1' and i*4+c < w:
                    grid[r][i*4+c]=1
    return grid, w, h

# ----------------------------- TEXTURE FACTORY ------------------------------
def make_image(name, w, h, painter):
    img = bpy.data.images.new(name, w, h, alpha=False)
    buf = [0.0]*(w*h*4)
    for y in range(h):
        for x in range(w):
            r,g,b = painter(x,y,w,h)
            i = (y*w+x)*4
            buf[i],buf[i+1],buf[i+2],buf[i+3] = r,g,b,1.0
    img.pixels.foreach_set(buf)
    img.pack()
    img.colorspace_settings.name = 'sRGB'
    return img

def tex_metal(base, seed):
    rnd = random.Random(seed)
    cols = [0.88+0.24*rnd.random() for _ in range(64)]
    def p(x,y,w,h):
        f = cols[x%64]*(0.92+0.16*rnd.random())
        r,g,b = [c*f for c in base]
        if y in (0,15,31): r,g,b = [c*0.7 for c in (r,g,b)]
        if y < 7 and rnd.random()<0.16: r,g,b = 0.36,0.19,0.11
        if rnd.random()<0.02: r,g,b = [min(1,c*1.5) for c in (r,g,b)]
        return r,g,b
    return p

def tex_concrete(base, seed):
    rnd = random.Random(seed)
    cracks = []
    for _ in range(3):
        x,y = rnd.randrange(32), rnd.randrange(32); pts=set()
        for _ in range(26):
            pts.add((x%32,y%32)); x+=rnd.choice((-1,0,1)); y+=rnd.choice((-1,0,1))
        cracks.append(pts)
    def p(x,y,w,h):
        f = 0.9+0.2*rnd.random()
        r=g=b=base*f
        if x==0 or y==0: r=g=b=base*0.6
        for c in cracks:
            if (x,y) in c: r=g=b=base*0.55
        return r,g,b
    return p

def tex_asphalt(x,y,w,h):
    f=0.85+0.3*RNG.random(); v=0.14*f; return v,v,v*1.05

def tex_wood(x,y,w,h):
    f=0.85+0.3*RNG.random()
    r,g,b = 0.46*f,0.33*f,0.19*f
    if y%8==0: r,g,b = [c*0.55 for c in (r,g,b)]
    if (x*7+y)%23==0: r,g,b=[c*0.8 for c in (r,g,b)]
    return r,g,b

def tex_hazard(x,y,w,h):
    return (0.72,0.52,0.08) if ((x+y)//4)%2==0 else (0.08,0.08,0.08)

def tex_grate(x,y,w,h):
    v = 0.03 if (x%8 in (2,3,4,5) and y%8 in (2,3,4,5)) else 0.12
    return v,v,v

def tex_checker(x,y,w,h):
    v = 0.34 if ((x+y)%8<2 or (x-y)%8<2) else 0.22
    return v,v,v*1.05

def tex_paint(base, seed):
    rnd=random.Random(seed)
    def p(x,y,w,h):
        if rnd.random()<0.12: return 0.25,0.25,0.25
        f=0.9+0.2*rnd.random(); return [c*f for c in base]
    return p

def make_text_image(name, text, bg, fg, pad=1):
    grid,w,h = text_pixels(text)
    W_,H_ = w+pad*2, h+pad*2
    def p(x,y,w_,h_):
        gx,gy = x-pad, y-pad
        if 0<=gx<w and 0<=gy<h and grid[gy][gx]: return fg
        if x==0 or y==0 or x==w_-1 or y==h_-1: return [c*0.5 for c in bg]
        return bg
    return make_image(name, W_, H_, p), W_, H_

# ----------------------------- MATERIALS ------------------------------------
MATS = {}
def mat_plain(name, color, rough=0.8, metal=0.0, emis=None, estr=0.0):
    m = bpy.data.materials.new(name); m.use_nodes=True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs['Base Color'].default_value = (*color,1)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    if emis:
        bsdf.inputs['Emission Color'].default_value = (*emis,1)
        bsdf.inputs['Emission Strength'].default_value = estr
    MATS[name]=m; return m

def mat_tex(name, img, rough=0.8, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes=True
    nt=m.node_tree; bsdf=nt.nodes.get("Principled BSDF")
    bsdf.inputs['Roughness'].default_value=rough
    bsdf.inputs['Metallic'].default_value=metal
    t=nt.nodes.new('ShaderNodeTexImage'); t.image=img; t.interpolation='Closest'
    nt.links.new(t.outputs['Color'], bsdf.inputs['Base Color'])
    MATS[name]=m; return m

def init_materials():
    mat_tex("concrete_a", make_image("t_conc_a",32,32,tex_concrete(0.34,1)))
    mat_tex("concrete_b", make_image("t_conc_b",32,32,tex_concrete(0.30,2)))
    mat_tex("concrete_c", make_image("t_conc_c",32,32,tex_concrete(0.38,3)))
    mat_tex("asphalt",    make_image("t_asph",32,32,tex_asphalt),0.95)
    mat_tex("wood",       make_image("t_wood",32,32,tex_wood),0.85)
    mat_tex("hazard",     make_image("t_haz",32,32,tex_hazard),0.7)
    mat_tex("grate",      make_image("t_grate",32,32,tex_grate),0.6,0.3)
    mat_tex("checker",    make_image("t_check",32,32,tex_checker),0.6,0.3)
    mat_tex("paint_yellow",make_image("t_py",32,32,tex_paint((0.72,0.52,0.10),7)),0.7)
    mat_tex("paint_white", make_image("t_pw",32,32,tex_paint((0.75,0.75,0.72),8)),0.7)
    palette = {
        "rust":(0.45,0.18,0.12),"navy":(0.10,0.16,0.30),"teal":(0.08,0.28,0.28),
        "green":(0.20,0.30,0.18),"yellow":(0.65,0.48,0.10),"gray":(0.38,0.40,0.42),
        "orange":(0.60,0.30,0.12)}
    for i,(k,v) in enumerate(palette.items()):
        mat_tex("ctr_"+k, make_image("t_ctr_"+k,32,32,tex_metal(v,100+i)),0.75,0.15)
    mat_tex("roof_metal", make_image("t_roof",32,32,tex_metal((0.22,0.23,0.25),50)),0.7,0.2)
    mat_plain("metal_dark",(0.10,0.10,0.11),0.6,0.3)
    mat_plain("metal_mid",(0.28,0.29,0.30),0.55,0.3)
    mat_plain("rubber",(0.05,0.05,0.05),0.9)
    mat_plain("puddle",(0.05,0.07,0.09),0.08,0.0)
    mat_plain("lamp_warm",(0.2,0.12,0.05),0.5,0.0,(1.0,0.72,0.40),5.0)
    mat_plain("lamp_cool",(0.1,0.12,0.15),0.5,0.0,(0.6,0.8,1.0),3.0)
    mat_plain("window",(0.15,0.12,0.06),0.4,0.0,(0.95,0.8,0.5),2.0)
    mat_plain("collect",(0.05,0.2,0.15),0.4,0.0,(0.2,1.0,0.8),3.0)
    mat_plain("collision_proxy",(0.5,0.5,0.5),1.0)

def mat_label(text, bg=(0.82,0.82,0.78), fg=(0.08,0.08,0.08)):
    name = "lbl_"+text.replace(" ","_")
    if name in MATS: return name, MATS[name+"_img_w"], MATS[name+"_img_h"]
    img,w,h = make_text_image("t_"+name, text, bg, fg)
    mat_tex(name, img, 0.7)
    MATS[name+"_img_w"]=w; MATS[name+"_img_h"]=h
    return name, w, h

# ----------------------------- MESH BATCHING --------------------------------
FACE_DEF = [  # (vert order, uv axes)
    ((0,3,2,1),(0,1)), ((4,5,6,7),(0,1)),
    ((0,1,5,4),(0,2)), ((2,3,7,6),(0,2)),
    ((0,4,7,3),(1,2)), ((1,2,6,5),(1,2)),
]
class Batch:
    def __init__(self):
        self.verts=[]; self.faces=[]; self.uvs=[]; self.mats=[]; self.mat_idx={}
        # Store one material slot index for every polygon. Without this,
        # Blender assigns material slot 0 to every face in a batched mesh.
        self.face_mats=[]
    def _mi(self,m):
        if m not in self.mat_idx:
            self.mat_idx[m]=len(self.mats); self.mats.append(m)
        return self.mat_idx[m]
    def box(self,cx,cy,cz,sx,sy,sz,mat,uv='tile',rot=None):
        hx,hy,hz=sx/2,sy/2,sz/2
        local=[(-hx,-hy,-hz),(hx,-hy,-hz),(hx,hy,-hz),(-hx,hy,-hz),
               (-hx,-hy,hz),(hx,-hy,hz),(hx,hy,hz),(-hx,hy,hz)]
        M = Matrix.Translation((cx,cy,cz))
        if rot is not None: M = M @ rot
        base=len(self.verts)
        for v in local: self.verts.append(tuple(M @ Vector(v)))
        mi=self._mi(mat)
        for order,(ax,ay) in FACE_DEF:
            self.faces.append(tuple(base+i for i in order))
            self.face_mats.append(mi)
            if uv=='fit':
                aa=[local[i][ax] for i in order]; bb=[local[i][ay] for i in order]
                a0,a1=min(aa),max(aa); b0,b1=min(bb),max(bb)
                da=(a1-a0) or 1; db=(b1-b0) or 1
                self.uvs.append([((local[i][ax]-a0)/da,(local[i][ay]-b0)/db) for i in order])
            else:
                self.uvs.append([(local[i][ax]/TEX_WORLD, local[i][ay]/TEX_WORLD) for i in order])
        return mi
    def build(self,name,coll,parent=None,extras=None):
        if not self.faces: return None
        me=bpy.data.meshes.new(name)
        me.from_pydata(self.verts,[],self.faces)
        me.update()
        if len(me.polygons) != len(self.face_mats):
            raise RuntimeError(
                f"Material assignment mismatch for {name}: "
                f"{len(me.polygons)} polygons vs {len(self.face_mats)} material indices"
            )
        for poly, material_index in zip(me.polygons, self.face_mats):
            poly.material_index = material_index
        uv=me.uv_layers.new(name="UVMap")
        for fi,fu in enumerate(self.uvs):
            for k in range(4):
                uv.data[fi*4+k].uv=fu[k]
        for mn in self.mats: me.materials.append(MATS[mn])
        ob=bpy.data.objects.new(name,me)
        coll.objects.link(ob)
        if parent: ob.parent=parent
        if extras:
            for k,v in extras.items(): ob[k]=v
        return ob

# ----------------------------- SCENE SETUP ----------------------------------
def setup_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc=bpy.context.scene
    sc.unit_settings.system='METRIC'; sc.unit_settings.scale_length=1.0
    for cn in COL_NAMES:
        c=bpy.data.collections.new(cn); sc.collection.children.link(c); COLS[cn]=c
        e=bpy.data.objects.new(cn+"_ROOT",None); c.objects.link(e); ROOTS[cn]=e
    w=bpy.data.worlds.new("HarborWorld"); sc.world=w; w.use_nodes=True
    bg=w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value=(0.03,0.045,0.07,1); bg.inputs[1].default_value=0.5
    try:
        sc.render.engine='BLENDER_EEVEE_NEXT'
    except Exception:
        sc.render.engine='BLENDER_EEVEE'
    sc.render.resolution_x=1280; sc.render.resolution_y=720

ENV=None; PROPS=None
def E(): return ENV
def P(): return PROPS

def col_box(name,cx,cy,cz,sx,sy,sz,rot=None):
    hx,hy,hz=sx/2,sy/2,sz/2
    vs=[(-hx,-hy,-hz),(hx,-hy,-hz),(hx,hy,-hz),(-hx,hy,-hz),
        (-hx,-hy,hz),(hx,-hy,hz),(hx,hy,hz),(-hx,hy,hz)]
    fs=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,4,7,3),(1,2,6,5)]
    M=Matrix.Translation((cx,cy,cz))
    if rot is not None: M=M@rot
    me=bpy.data.meshes.new(name)
    me.from_pydata([tuple(M@Vector(v)) for v in vs],[],fs); me.update()
    me.materials.append(MATS["collision_proxy"])
    ob=bpy.data.objects.new(name,me); COLS["COLLISION"].objects.link(ob)
    ob.parent=ROOTS["COLLISION"]; ob.display_type='WIRE'; ob.hide_render=True
    ob["collision"]=1
    return ob

# ----------------------------- CONTAINERS -----------------------------------
CTR_COUNT=0
def build_container(x,y,z,rot_deg,color,length=6.0,height=2.5,open_doors=False,tag=None):
    global CTR_COUNT
    CTR_COUNT+=1
    b=Batch(); Wd=2.5; Lh=length/2; Wh=Wd/2; Hh=height/2
    body="ctr_"+color
    b.box(0,0,Hh, length,Wd,height, body)                      # shell
    n=int(length/0.5)
    for i in range(n):                                       # corrugation ribs
        rx=-Lh+0.25+i*0.5
        b.box(rx, Wh+0.03, Hh, 0.22,0.06,height-0.3, body)
        b.box(rx,-Wh-0.03, Hh, 0.22,0.06,height-0.3, body)
    for sx in (-1,1):                                        # corner posts + castings
        for sy in (-1,1):
            b.box(sx*(Lh-0.12), sy*(Wh-0.12), Hh, 0.24,0.24,height, "metal_dark")
            for sz in (0.15,height-0.15):
                b.box(sx*(Lh-0.1), sy*(Wh-0.1), sz, 0.3,0.3,0.3, "metal_dark")
    for i in range(3):                                       # roof bows
        b.box(-Lh+length*(i+1)/4, 0, height+0.03, 0.15,Wd-0.2,0.06, body)
    dx=Lh+0.04                                               # doors (+X end)
    if not open_doors:
        for sy in (-1,1):
            b.box(dx, sy*Wd/4, Hh, 0.06,Wd/2-0.12,height-0.3, body)
            for by in (sy*Wd/4-0.4, sy*Wd/4+0.4):            # locking bars
                b.box(dx+0.06, by, Hh, 0.06,0.06,height-0.5, "metal_mid")
                b.box(dx+0.1, by, Hh-0.3, 0.08,0.16,0.06, "metal_mid")  # handle
            for hy in (0.4, Hh, height-0.4):                 # hinges
                b.box(dx, sy*(Wh-0.08), hy, 0.1,0.12,0.16, "metal_dark")
    else:
        for sy in (-1,1):                                    # swung-open panels
            b.box(Lh+Wd/4, sy*Wh, Hh, Wd/2,0.06,height-0.3, body)
        b.box(0,0,0.1, length-0.4,Wd-0.4,0.1, "wood")        # interior floor
        b.box(-1,0,0.55, 1.0,1.0,0.9, "wood")
        b.box(0.6,0.4,0.45, 0.8,0.8,0.7, "wood")
    tag = tag or ("VXU %04d" % (1000+CTR_COUNT*37))
    lm,lw,lh = mat_label(tag)
    pw=1.6; ph=pw*lh/lw
    b.box(Lh-1.1, Wh+0.07, height-0.6, pw,0.02,ph, lm, uv='fit')
    rot=Matrix.Rotation(math.radians(rot_deg),4,'Z')
    name="CTR_%02d_%s" % (CTR_COUNT,color)
    ob=b.build(name, COLS["CONTAINERS"], ROOTS["CONTAINERS"],
               extras={"zone":"container","type":color})
    ob.location=(x,y,z); ob.rotation_euler=(0,0,math.radians(rot_deg))
    # collision in world space
    if rot_deg%180==0: sx,sy=length,Wd
    else: sx,sy=Wd,length
    col_box("COL_"+name, x,y,z+height/2, sx,sy,height)
    return ob

# ----------------------------- GROUND & PERIMETER ---------------------------
def build_ground():
    b=E()
    b.box(0,0,-0.25, W,L,0.5, "asphalt")
    col_box("COL_ground",0,0,-0.25,W,L,0.5)
    for i in range(14):                                      # concrete tiles
        for j in range(11):
            x=-28+2+i*4; y=-22+2+j*4
            m=["concrete_a","concrete_b","concrete_c"][(i+j)%3]
            if (i in (6,7) and j<3): m="asphalt"             # vehicle lane
            b.box(x,y,-0.02, 3.9,3.9,0.08, m)
    # painted guide lane around court
    for (cx,cy,sx,sy) in [(-13,-9,0.15,20),(13,-9,0.15,20),(0,-19,26,0.15),(0,1,26,0.15)]:
        b.box(cx,cy,0.03,sx,sy,0.02,"paint_yellow")
    for k in range(5):                                       # crosswalk at gate
        b.box(1+k*1.0,-20.5,0.03,0.5,2.4,0.02,"paint_white")
    for (cx,cy) in [(-8,14),(16,14),(13.5,-12)]:              # hazard pads
        b.box(cx,cy,0.03,3.4,3.4,0.02,"hazard")
    b.box(4,14,0.03,7,4,0.02,"hazard")
    for (txt,cx,cy) in [("A CARGO",0,-13.5),("B STACKS",-21,-4),("C SERVICE",12,-5.5),("D CRANE",4,7.5)]:
        lm,lw,lh=mat_label(txt,(0.55,0.45,0.10),(0.1,0.1,0.1))
        b.box(cx,cy,0.035,3.0,3.0*lh/lw,0.02,lm,uv='fit')
    lm,lw,lh=mat_label("KEEP CLEAR",(0.6,0.15,0.1),(0.9,0.9,0.85))
    b.box(4,10.5,0.035,3.2,3.2*lh/lw,0.02,lm,uv='fit')
    # drainage grates
    b.box(-27.2,0,0.02,0.6,40,0.06,"grate")
    b.box(0,21.2,0.02,52,0.6,0.06,"grate")
    # puddles
    for (cx,cy,sx,sy) in [(10,-14,2.4,1.6),(-4,-10,1.8,1.2),(18,4,2.2,1.4),(-21,20,1.6,1.2)]:
        b.box(cx,cy,0.045,sx,sy,0.02,"puddle")
    # perimeter curb
    for (cx,cy,sx,sy) in [(0,-21.85,56,0.3),(-27.85,0,0.3,44),(27.85,0,0.3,44),(-14,21.85,28,0.3),(17,21.85,22,0.3)]:
        b.box(cx,cy,0.12,sx,sy,0.25,"concrete_b")
    # fence (north / east / west, gate gap south)
    def fence_run(x0,y0,x1,y1):
        dx,dy=x1-x0,y1-y0; ln=math.hypot(dx,dy); n=int(ln/4)
        for k in range(n+1):
            t=k/n; b.box(x0+dx*t,y0+dy*t,1.25,0.15,0.15,2.5,"metal_dark")
        ang=math.atan2(dy,dx)
        b.box((x0+x1)/2,(y0+y1)/2,1.2,ln,0.08,2.0,"ctr_gray",rot=Matrix.Rotation(ang,4,'Z'))
        b.box((x0+x1)/2,(y0+y1)/2,2.45,ln,0.1,0.08,"metal_dark",rot=Matrix.Rotation(ang,4,'Z'))
        col_box("COL_fence",(x0+x1)/2,(y0+y1)/2,1.2,ln if abs(dx)>abs(dy) else 0.2,
                0.2 if abs(dx)>abs(dy) else ln,2.4)
    fence_run(-27.5,21.5,27.5,21.5)
    fence_run(27.5,-21.5,27.5,21.5)
    fence_run(-27.5,-21.5,-27.5,21.5)
    fence_run(-27.5,-21.5,-1,-21.5)
    fence_run(7,-21.5,27.5,-21.5)

# ----------------------------- AREA A : COURT -------------------------------
def build_court():
    b=E()
    # landmark: harbor beacon
    b.box(0,-8,0.25,4,4,0.5,"concrete_c")
    b.box(0,-8,0.6,3,3,0.2,"hazard")
    b.box(0,-8,3.5,1.4,1.4,6.0,"concrete_b")
    for z in (1.5,3.0,4.5):
        b.box(0,-8,z,1.6,1.6,0.15,"metal_dark")
    b.box(0,-8,6.6,2.0,2.0,1.2,"metal_dark")
    for sx in (-1,1):
        for sy in (-1,1):
            b.box(sx*0.95,-8+sy*0.95,6.6,0.12,0.12,1.0,"lamp_warm")
    b.box(0,-8,6.6,1.7,1.7,0.9,"lamp_warm")
    b.box(0,-8,7.35,2.3,2.3,0.25,"roof_metal")
    b.box(0,-8,7.7,0.3,0.3,0.5,"metal_dark")
    col_box("COL_beacon",0,-8,3.5,1.6,1.6,7.0)
    col_box("COL_beacon_base",0,-8,0.25,4,4,0.5)
    lm,lw,lh=mat_label("K-02",(0.1,0.1,0.1),(0.95,0.75,0.3))
    b.box(0,-9.0,3.0,1.2,0.02,1.2*lh/lw,lm,uv='fit')
    # court containers
    build_container(-8,-16,0,0,"rust")
    build_container(-1,-18,0,0,"navy")
    build_container(6,-15,0,90,"teal")
    build_container(10,-9,0,0,"green")
    build_container(-12,-8,0,90,"yellow",height=3.0)
    build_container(-5,-2,0,0,"gray")
    build_container(2,-2,0,0,"orange")
    build_container(8,-3,0,90,"rust",length=3.0)
    build_container(-13,-2,0,0,"navy",open_doors=True,tag="VXU 0000")
    # flatbed truck
    b=P()
    b.box(4,-10,0.9,6.5,2.2,0.35,"metal_dark")
    b.box(7.6,-10,1.6,1.8,2.2,1.6,"ctr_navy")
    b.box(8.4,-10,1.7,0.1,1.8,0.7,"window")
    b.box(4,-10,1.35,5.5,2.0,0.5,"wood")
    b.box(3,-10,1.9,1.2,1.2,0.8,"wood")
    b.box(5,-10,1.9,1.0,1.0,0.8,"ctr_green")
    for wx in (1.5,4.5,7.5):
        for wy in (-1,1):
            b.box(wx,-10+wy*1.1,0.4,0.8,0.3,0.8,"rubber")
    b.box(8.55,-10,1.2,0.06,1.6,0.25,"lamp_warm")
    col_box("COL_truck",4.5,-10,1.1,8.5,2.4,2.2)
    # bollards
    for x in range(-14,15,4):
        if 0<=x<=6: continue
        b.box(x,-20.5,0.45,0.25,0.25,0.9,"paint_yellow")
        b.box(x,-20.5,0.7,0.27,0.27,0.15,"hazard")
        col_box("COL_bollard",x,-20.5,0.45,0.3,0.3,0.9)

# ----------------------------- AREA B : ELEVATED DISTRICT -------------------
def railing(b,x0,y0,x1,y1,z):
    dx,dy=x1-x0,y1-y0; ln=math.hypot(dx,dy); n=max(1,int(ln/1.5))
    ang=math.atan2(dy,dx); R=Matrix.Rotation(ang,4,'Z')
    for k in range(n+1):
        t=k/n; b.box(x0+dx*t,y0+dy*t,z+0.55,0.08,0.08,1.1,"metal_mid")
    b.box((x0+x1)/2,(y0+y1)/2,z+1.05,ln,0.06,0.06,"metal_mid",rot=R)
    b.box((x0+x1)/2,(y0+y1)/2,z+0.55,ln,0.05,0.05,"metal_mid",rot=R)
    col_box("COL_rail",(x0+x1)/2,(y0+y1)/2,z+0.55,
            max(ln,0.1) if abs(dx)>abs(dy) else 0.1,
            0.1 if abs(dx)>abs(dy) else max(ln,0.1),1.1)

def deck(b,x0,x1,y0,y1,z,rails=()):
    b.box((x0+x1)/2,(y0+y1)/2,z-0.1,(x1-x0),(y1-y0),0.2,"checker")
    col_box("COL_deck",(x0+x1)/2,(y0+y1)/2,z-0.1,(x1-x0),(y1-y0),0.2)
    for px in (x0+0.3,x1-0.3):
        for py in (y0+0.3,y1-0.3):
            if z>0.3: b.box(px,py,(z-0.2)/2,0.2,0.2,z-0.2,"metal_dark")
    for (a,c,d,e) in rails: railing(b,a,c,d,e,z)

def stairs(b,x,y,z0,z1,direction,width=1.6):
    rise=0.25; tread=0.4
    n=int(round((z1-z0)/rise)); run=n*tread
    dx,dy=direction
    for k in range(n):
        h=z0+(k+1)*rise
        cx=x+dx*(k*tread+tread/2); cy=y+dy*(k*tread+tread/2)
        sx=tread if dx else width; sy=tread if dy else width
        b.box(cx,cy,h/2,sx,sy,h,"concrete_c")
    ang=math.atan2(z1-z0,run)
    ln=math.hypot(run,z1-z0)
    R=Matrix.Rotation(ang,4,'X') if dy else Matrix.Rotation(-ang,4,'Y')
    mx=x+dx*run/2; my=y+dy*run/2; mz=(z0+z1)/2
    for s in (-1,1):
        ox=s*width/2 if dx else 0; oy=s*width/2 if dy else 0
        b.box(mx+ox,my+oy,mz+1.0,0.06 if dx else ln,ln if dx else 0.06,0.06,"metal_mid",rot=R)
    col_box("COL_stairs",mx,my,mz,
            (run if dx else width)+0.1,(run if dy else width)+0.1,0.3,rot=R)

def build_district_b():
    b=E()
    build_container(-24,2,0,90,"teal")
    build_container(-24,9,0,90,"rust")
    build_container(-24,16,0,90,"gray")
    build_container(-24,2,2.5,90,"orange")
    build_container(-24,9,2.5,90,"navy")
    build_container(-24,9,5.0,90,"yellow")
    build_container(-19,5,0,90,"green")
    build_container(-19,12,0,90,"rust")
    build_container(-19,5,2.5,90,"gray")
    build_container(-19,12,2.5,90,"teal")
    deck(b,-22.75,-20.25,-1,19,2.5,
         rails=[(-22.75,-1,-22.75,19),(-20.25,-1,-20.25,6),(-20.25,14,-20.25,19)])
    deck(b,-22.75,-20.25,6,14,5.0,
         rails=[(-22.75,6,-22.75,14),(-20.25,6,-20.25,14)])
    stairs(b,-21.5,-1,0,2.5,(0,-1))
    stairs(b,-21.5,14,2.5,5.0,(0,1))
    # bridge to crane west platform
    deck(b,-20.25,-9.5,13.25,14.75,5.0,
         rails=[(-20.25,13.25,-9.5,13.25),(-20.25,14.75,-9.5,14.75)])
    lm,lw,lh=mat_label("B STACKS",(0.1,0.1,0.1),(0.9,0.75,0.3))
    b.box(-21.5,-0.9,3.6,1.4,0.02,1.4*lh/lw,lm,uv='fit')

# ----------------------------- AREA C : SERVICE -----------------------------
def build_service_c():
    b=E(); p=P()
    x0,x1,y0,y1=15,25,-15.5,-8.5; h=4.0; t=0.3
    b.box((x0+x1)/2,(y0+y1)/2,0.05,(x1-x0),(y1-y0),0.1,"concrete_c")
    b.box((x0+x1)/2,y0+t/2,h/2,(x1-x0),t,h,"concrete_b")     # south wall
    b.box((x0+x1)/2,y1-t/2,h/2,(x1-x0),t,h,"concrete_b")     # north wall
    b.box(x1-t/2,(y0+y1)/2,h/2,t,(y1-y0),h,"concrete_b")     # east wall
    # west wall with 3u door bay (y -13.5..-10.5)
    b.box(x0+t/2,(y0-13.5)/2,h/2,t,(-13.5-y0),h,"concrete_b")
    b.box(x0+t/2,(-10.5+y1)/2,h/2,t,(y1+10.5),h,"concrete_b")
    b.box(x0+t/2,-12,(3+h)/2,t,3.0,h-3.0,"concrete_b")
    b.box((x0+x1)/2,(y0+y1)/2,h+0.15,(x1-x0)+0.4,(y1-y0)+0.4,0.3,"roof_metal")
    for (cx,cy,sx,sy) in [((x0+x1)/2,y0,(x1-x0),t),((x0+x1)/2,y1,(x1-x0),t),
                          (x1,(y0+y1)/2,t,(y1-y0)),(x0,(y0-13.5)/2,t,(-13.5-y0)),
                          (x0,(-10.5+y1)/2,t,(y1+10.5))]:
        col_box("COL_bldg",cx,cy,h/2,sx,sy,h)
    col_box("COL_roof",(x0+x1)/2,(y0+y1)/2,h+0.15,(x1-x0)+0.4,(y1-y0)+0.4,0.3)
    # interior
    p.box(23.5,-12,0.5,1.0,4.0,1.0,"wood")
    p.box(23.5,-12,1.6,0.8,3.6,0.1,"metal_mid")
    p.box(20,-14.8,1.0,3.0,0.6,2.0,"metal_dark")
    p.box(20,-12,3.7,2.0,1.0,0.1,"lamp_warm")
    lm,lw,lh=mat_label("SERVICE",(0.15,0.15,0.15),(0.95,0.75,0.3))
    b.box(14.8,-12,3.5,0.02,2.6,2.6*lh/lw,lm,uv='fit')
    lm,lw,lh=mat_label("BAY 1",(0.6,0.15,0.1),(0.9,0.9,0.85))
    b.box(14.8,-9.5,2.2,0.02,1.2,1.2*lh/lw,lm,uv='fit')
    p.box(14.7,-14.5,1.2,0.15,0.4,0.5,"ctr_rust")           # extinguisher
    # roof props + railing + stairs
    p.box(18,-13,4.7,1.4,1.0,0.8,"metal_mid")
    p.box(22,-10,4.6,0.8,0.8,0.6,"metal_dark")
    railing(b,15, -15.5,25,-15.5,4.3); railing(b,15,-8.5,25,-8.5,4.3)
    railing(b,15,-15.5,15,-8.5,4.3)
    stairs(b,26,-15,0,4.0,(0,1),width=1.4)
    # loading dock + ramp
    b.box(13.5,-12,0.5,3,5,1.0,"concrete_c")
    col_box("COL_dock",13.5,-12,0.5,3,5,1.0)
    ang=math.atan2(1.0,5.0)
    R=Matrix.Rotation(-ang,4,'Y')
    b.box(10.0,-12,0.5,5.2,3,0.25,"checker",rot=R)
    col_box("COL_ramp",10.0,-12,0.5,5.2,3,0.25,rot=R)
    for y in (-14.2,-9.8):
        b.box(12.2,y,1.1,0.25,0.25,1.0,"paint_yellow")
    # forklift
    p.box(11,-7,0.6,1.5,1.1,0.8,"ctr_yellow")
    p.box(10.4,-7,1.2,0.6,1.0,0.6,"metal_dark")
    p.box(11.9,-7,1.2,0.12,1.0,2.2,"metal_dark")
    p.box(12.3,-7,0.18,0.9,0.12,0.06,"metal_mid")
    for sx in (-1,1):
        for sy in (-1,1):
            p.box(11+sx*0.6,-7+sy*0.55,0.35,0.4,0.25,0.7,"rubber")
            p.box(11+sx*0.6,-7+sy*0.5,1.7,0.08,0.08,1.2,"metal_dark")
    p.box(11,-7,2.3,1.4,1.1,0.08,"ctr_yellow")
    p.box(11,-7,2.45,0.2,0.2,0.15,"lamp_warm")
    col_box("COL_forklift",11.3,-7,1.1,2.6,1.3,2.2)
    # pallets / crates / drums
    def pallet(cx,cy,z):
        p.box(cx,cy,z+0.06,1.2,1.2,0.12,"wood")
        for o in (-0.45,0,0.45): p.box(cx+o,cy,z+0.0,0.15,1.2,0.12,"wood")
    def crate(cx,cy,z,s=0.9):
        p.box(cx,cy,z+s/2,s,s,s,"wood")
        p.box(cx,cy,z+s/2,s+0.04,s+0.04,0.1,"metal_dark")
    pallet(3,-6,0); pallet(3,-6,0.15); crate(3,-6,0.3)
    pallet(4.5,-6,0); crate(4.5,-6,0.15); crate(4.5,-6,1.05,0.7)
    pallet(-3,-12,0); crate(-3,-12,0.15)
    pallet(14,-16,0); pallet(14,-16,0.15); pallet(14,-16,0.3)
    crate(16,-6,0); crate(17,-6,0); crate(16,-6,0.9)
    crate(-16,-13,0); crate(22,-8,0); crate(6,-19,0)
    for (dx,dy) in [(24,-6),(24.7,-6),(24,-6.8)]:
        p.box(dx,dy,0.4,0.55,0.55,0.8,"ctr_navy")
        p.box(dx,dy,0.55,0.57,0.57,0.08,"metal_dark")
    p.box(-26,-2,0.6,1.2,1.0,1.2,"wood")
    p.box(-26,-2,0.6,1.3,0.15,1.3,"wood")
    p.box(26,6,0.6,1.2,1.0,1.2,"wood")
    for k in range(3):
        p.box(-24,-8+k*0.45,0.2,4,0.4,0.4,"metal_mid")
    for k in range(2):
        p.box(-24,-7.8+k*0.45,0.6,4,0.4,0.4,"metal_mid")
    p.box(15,-8,0.5,0.7,0.7,1.0,"ctr_green")
    build_container(16,-4,0,0,"orange")
    build_container(24,-4,0,90,"gray",length=3.0)

# ----------------------------- AREA D : CRANE & OBSERVATION -----------------
def build_crane_d():
    b=E(); p=P()
    for lx in (-8,16):                                       # gantry legs
        b.box(lx,14,5,1.2,1.2,10,"ctr_yellow")
        b.box(lx,14,0.6,1.5,1.5,1.2,"hazard")
        for z in (2.5,5,7.5):
            b.box(lx,14,z,1.3,1.3,0.15,"metal_dark")
        col_box("COL_craneleg",lx,14,5,1.4,1.4,10)
        deck(b,lx-1.5,lx+1.5,12.5,15.5,5.0,
             rails=[(lx-1.5,12.5,lx+1.5,12.5),(lx-1.5,15.5,lx+1.5,15.5)])
    b.box(4,14,10.3,28,1.2,1.2,"ctr_yellow")                 # main beam
    b.box(4,14,11.0,28,0.4,0.3,"metal_dark")
    for x in range(-9,18,2):
        b.box(x,14,10.3,0.15,1.3,1.3,"metal_dark")
    lm,lw,lh=mat_label("MAX 12T",(0.6,0.15,0.1),(0.95,0.95,0.9))
    b.box(4,13.3,10.3,2.4,0.02,2.4*lh/lw,lm,uv='fit')
    b.box(-8,12.6,9.0,1.5,1.5,1.5,"ctr_navy")                # operator cab
    b.box(-8,11.8,9.0,1.2,0.06,0.8,"window")
    b.box(4,14,9.4,1.6,1.6,0.8,"metal_dark")                 # trolley
    for sx in (-1,1):
        for sy in (-1,1):
            b.box(4+sx*2.5,14+sy*0.9,7.5,0.05,0.05,3.6,"metal_dark")  # cables
    b.box(4,14,5.6,6.0,0.5,0.3,"paint_yellow")               # spreader
    build_container(4,14,3.2,0,"yellow",tag="VXU 9999")
    # observation platform
    deck(b,18,26,12,20,5.0,
         rails=[(18,20,26,20),(26,12,26,20),(18,12,18,13.2),(18,14.8,18,20)])
    stairs(b,22,4,0,5.0,(0,1),width=2.0)
    deck(b,17.5,18,13.25,14.75,5.0)                          # link bridge
    p.box(25.5,19.5,7,0.25,0.25,4,"metal_mid")               # antenna mast
    p.box(25.5,19.5,8.6,0.8,0.08,0.08,"metal_mid")
    p.box(25.5,19.5,9.0,0.15,0.15,0.3,"lamp_cool")
    lm,lw,lh=mat_label("OBS",(0.1,0.1,0.1),(0.6,0.8,1.0))
    b.box(22,19.9,6.1,1.0,0.02,1.0*lh/lw,lm,uv='fit')
    build_container(10,18,0,0,"navy")
    build_container(-2,19,0,0,"green")

# ----------------------------- LIGHTING & PROPS -----------------------------
def mast(b,p,x,y,with_light=False):
    p.box(x,y,0.25,0.5,0.5,0.5,"concrete_b")
    p.box(x,y,3.2,0.2,0.2,6.0,"metal_dark")
    p.box(x+0.6,y,6.1,1.4,0.15,0.15,"metal_dark")
    p.box(x+1.2,y,6.0,0.6,0.3,0.2,"lamp_warm")
    col_box("COL_mast",x,y,3,0.3,0.3,6)
    if with_light:
        ld=bpy.data.lights.new("L_"+str(x)+"_"+str(y),'POINT')
        ld.energy=800; ld.color=(1.0,0.72,0.45); ld.shadow_soft_size=0.4
        ob=bpy.data.objects.new(ld.name,ld); COLS["LIGHTING"].objects.link(ob)
        ob.parent=ROOTS["LIGHTING"]; ob.location=(x+1.2,y,5.8)

def build_lights_props():
    b=E(); p=P()
    for (x,y,wl) in [(-12,-19,False),(12,-19,True),(12,1,False),(-12,1,False),
                     (-26,-6,False),(26,-2,True),(0,20,False),(26,20,False)]:
        mast(b,p,x,y,wl)
    # extra point lights
    for (name,loc,en,col) in [("L_beacon",(0,-8,7.0),500,(1,0.7,0.4)),
                              ("L_bay",(20,-12,3.4),400,(1,0.8,0.55)),
                              ("L_cab",(-8,12,8.6),300,(0.9,0.8,0.6)),
                              ("L_obs",(22,16,6.5),400,(1,0.75,0.5)),
                              ("L_deckB",(-21.5,8,4.3),300,(1,0.75,0.5))]:
        ld=bpy.data.lights.new(name,'POINT'); ld.energy=en; ld.color=col
        ld.shadow_soft_size=0.35
        ob=bpy.data.objects.new(name,ld); COLS["LIGHTING"].objects.link(ob)
        ob.parent=ROOTS["LIGHTING"]; ob.location=loc
    sun=bpy.data.lights.new("Sun",'SUN'); sun.energy=3.5
    sun.color=(1.0,0.95,0.85); sun.angle=math.radians(2)
    so=bpy.data.objects.new("Sun",sun); COLS["LIGHTING"].objects.link(so)
    so.parent=ROOTS["LIGHTING"]; so.rotation_euler=(math.radians(55),0,math.radians(30))
    # collectibles
    spots=[(0,-8,0.75),(-21.5,10,5.25),(-8,14,5.25),(22,16,5.25),
           (20,-12,4.5),(-9,-3.5,0.25),(4,14,0.25),(13.5,-12,1.25)]
    for i,(x,y,z) in enumerate(spots):
        cb=Batch()
        cb.box(0,0,0.2,0.4,0.4,0.4,"collect")
        cb.box(0,0,0.2,0.44,0.44,0.1,"metal_dark")
        ob=cb.build("COLLECTIBLE_%02d"%(i+1),COLS["INDUSTRIAL_PROPS"],
                    ROOTS["INDUSTRIAL_PROPS"],extras={"collectible":1,"id":i+1})
        ob.location=(x,y,z)
    # hand pallet truck
    p.box(12.5,-10,0.15,1.2,0.5,0.1,"ctr_orange")
    p.box(13.2,-10,0.5,0.1,0.4,0.8,"metal_dark")

# ----------------------------- EXPORT ---------------------------------------
def export_glb():
    out_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()
    args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    if args: out_dir = args[0]
    out_dir = os.path.abspath(os.path.expanduser(out_dir))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "environment.glb")
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.export_scene.gltf(
        filepath=path, export_format='GLB', export_yup=True, export_apply=True,
        export_lights=True, export_extras=True, export_cameras=False,
        export_animations=False, use_visible=False, use_renderable=True)
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise RuntimeError(f"GLB export did not create a valid output file: {path}")
    return path

def main():
    global ENV, PROPS
    setup_scene(); init_materials()
    ENV=Batch(); PROPS=Batch()
    build_ground(); build_court(); build_district_b(); build_service_c()
    build_crane_d(); build_lights_props()
    ENV.build("ENV_Static", COLS["ENVIRONMENT_GEO"], ROOTS["ENVIRONMENT_GEO"])
    PROPS.build("PROPS_Static", COLS["INDUSTRIAL_PROPS"], ROOTS["INDUSTRIAL_PROPS"])
    # preview camera
    cam=bpy.data.cameras.new("PreviewCam"); co=bpy.data.objects.new("PreviewCam",cam)
    bpy.context.scene.collection.objects.link(co)
    co.location=(42,-40,26); co.rotation_euler=(math.radians(60),0,math.radians(46))
    bpy.context.scene.camera=co
    tris=sum(len(m.polygons)*2 for m in bpy.data.meshes if not m.name.startswith("COL_"))
    path=export_glb()
    print("="*70)
    print("VOXEL HARBOR COMPLETE")
    print("Containers:",CTR_COUNT,"| Approx triangles:",tris)
    print("Objects:",len(bpy.data.objects),"| Materials:",len(bpy.data.materials))
    print("EXPORTED:",path)
    print("="*70)

main()