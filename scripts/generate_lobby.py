# Blender background script: generate a compact, static, procedural cargo-ship lobby.
# Run: blender -b --python scripts/generate_lobby.py -- --output build/lobby.glb
import bpy, math, random, os, sys, traceback
from mathutils import Vector, Matrix

# A fresh CI profile (especially with --factory-startup) may not have the
# bundled glTF 2.0 exporter enabled. Enable it explicitly before using the op.
try:
    import addon_utils
    addon_utils.enable("io_scene_gltf2", default_set=True, persistent=True)
except Exception:
    traceback.print_exc()

if not hasattr(bpy.ops, "export_scene") or not hasattr(bpy.ops.export_scene, "gltf"):
    raise RuntimeError(
        "Blender glTF 2.0 exporter is unavailable. The io_scene_gltf2 add-on could not be enabled."
    )

print("Blender version:", bpy.app.version_string, flush=True)
print("glTF 2.0 exporter: enabled", flush=True)

random.seed(23)

def arg_value(flag, default):
    args = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    return args[args.index(flag)+1] if flag in args else default

OUT = os.path.abspath(arg_value("--output", "build/lobby.glb"))
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# Clean the file.
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.images):
    for block in list(datablocks):
        if block.users == 0:
            datablocks.remove(block)

def make_tex(name, base, size=128, rust=False, corrugation=False):
    """Create a small packed procedural pixel texture (portable in GLB)."""
    img = bpy.data.images.new(name, width=size, height=size, alpha=True)
    pixels = []
    br,bg,bb = [c/255.0 for c in base]
    for y in range(size):
        for x in range(size):
            n = random.random()
            # fine grain and weathering, plus vertical rust streaks
            streak = (math.sin(x*0.31 + math.sin(y*0.07)*2.0)+1)*0.5 if rust else 0
            rib = (0.5 + 0.5*math.cos(x*math.tau/8)) if corrugation else 0
            grime = (0.12*n + (0.17*streak if rust and n > 0.72 else 0) + 0.08*rib)
            k = 0.82 + grime
            if rust and n > 0.94:
                r,g,b = 0.42,0.19,0.10
            else:
                r,g,b = min(1,br*k), min(1,bg*k), min(1,bb*k)
            pixels.extend((r,g,b,1.0))
    img.pixels = pixels
    img.pack()
    return img

def material(name, color, rough=.65, metal=0.0, texture=False, rust=False, corr=False):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*[v/255 for v in color], 1)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*[v/255 for v in color], 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    if texture:
        img = make_tex(name+"_packed", color, rust=rust, corrugation=corr)
        tex = m.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.interpolation = "Linear"
        m.node_tree.links.new(tex.outputs["Color"], p.inputs["Base Color"])
    return m

blue = material("Worn navy container paint", (45,78,119), .68, .22, True, True, True)
upper = material("Dark green gray container", (48,74,80), .64, .25, True, True, True)
red = material("Oxidized red brown container", (122,63,51), .72, .18, True, True, True)
deck = material("Wet teal deck steel", (51,94,84), .29, .48, True, True)
walk = material("Dark non slip walkway", (16,22,30), .48, .25)
yellow = material("Faded safety yellow", (176,138,30), .52, .22)
frame = material("Dark frame steel", (27,35,43), .42, .68)
silver = material("Brushed aluminum", (185,190,190), .28, .82, True)
white = material("Off white plastic", (220,222,218), .62, .08, True)
crateblue = material("Blue plastic crate", (31,111,181), .62, .12, True)
beige = material("Weathered beige cargo box", (155,139,112), .78, .15, True, True)
rustmetal = material("Rusty crane steel", (93,55,42), .66, .45)
black = material("Black markings", (18,22,24), .72, .1)
drum_mat = material("Dirty pale drum", (181,180,170), .45, .55, True, True)

def assign(obj, mat):
    obj.data.materials.append(mat)
    return obj

def bevel(obj, amount=.035, segments=2):
    mod = obj.modifiers.new("Small worn edge bevel", "BEVEL")
    mod.width = amount
    mod.segments = segments
    mod2 = obj.modifiers.new("Weighted corner normals", "WEIGHTED_NORMAL")
    return obj

def cube(name, loc, scale, mat, bevel_amt=0.025):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat: assign(o, mat)
    if bevel_amt: bevel(o, bevel_amt)
    return o

def cyl(name, loc, radius, depth, mat, vertices=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    o=bpy.context.object; o.name=name; o.rotation_euler[0]=math.pi/2; assign(o,mat); bevel(o,.018,2); return o

def text_obj(body, loc, size, mat, rot=(0,0,0), name="Stencil"):
    cu=bpy.data.curves.new(name, "FONT"); cu.body=body; cu.size=size; cu.extrude=.0008
    ob=bpy.data.objects.new(name,cu); bpy.context.collection.objects.link(ob)
    ob.location=loc; ob.rotation_euler=rot; assign(ob,mat); return ob

def container(name, center, dims, paint, corrugated=True, end_mark=False):
    x,y,z=center; w,h,d=dims
    cube(name+"_body", center, dims, paint, .06)
    # corrugation on camera-facing long side, vertical ribs; low-poly, merged by material at export
    if corrugated:
        count=max(12,int(w*5))
        for i in range(count):
            xx=x-w/2+(i+.5)*w/count
            cube(name+"_rib_%02d"%i,(xx,y,z+d/2+.025),(.045,h*.92,.055),frame,.008)
    # corner castings and top/bottom rails
    for sx in (-1,1):
        for sz in (-1,1):
            cube(name+"_corner",(x+sx*(w/2-.07),y,z+sz*(d/2-.07)),(.14,h,.14),frame,.018)
    for yy in (y-h/2+.07,y+h/2-.07):
        cube(name+"_front_rail",(x,yy,z+d/2+.055),(w,.11,.11),frame,.015)
    if end_mark:
        # X lashing bars on rear-facing end panel
        for sign in (-1,1):
            bar=cube(name+"_tie",(x+sign*w*.24,y,z-d/2-.04),(.07,h*.88,.07),frame,.01)
            bar.rotation_euler[1]=sign*.55
    return

# 16 x 14m wet deck; top at z=0 in Blender.
cube("Deck", (0,-.12,-2), (16,.24,14), deck, .04)
# Two diagonal dark walkways and faded edge paint.
for xx in (-.15,):
    strip=cube("Diagonal walkway",(xx,.012,-2),(1.8,.025,16),walk,0)
    strip.rotation_euler[2]=math.radians(22)
    for side in (-1,1):
        edge=cube("Walkway yellow edge",(xx+side*.96,.03,-2),(.075,.025,16),yellow,0)
        edge.rotation_euler[2]=math.radians(22)
# Deck patch plates and tie-down plates.
for i in range(34):
    x=random.uniform(-7.4,7.4); y=.025; z=random.uniform(-8.5,4.5)
    plate=cube("Lashing plate",(x,y,z),(.32,.045,.23),frame,.012)
    cyl("Tie-down ring",(x,y+.035,z),.075,.025,silver,12)
for i in range(18):
    x=random.uniform(-7.5,7.5); z=random.uniform(-8,4.5)
    cube("Rust stain",(x,.006,z),(random.uniform(.12,.5),.008,random.uniform(.08,.35)),red,0)

# Left foreground stacked blue containers.
container("Left lower container",(-6.15,1.3,-1.5),(2.7,2.6,9.0),blue,True)
container("Left upper container",(-6.15,3.9,-1.5),(2.7,2.6,9.0),blue,True)
text_obj("ROHAN",(-7.0,.55,3.08),.62,white)
for yy in (2.05,4.85):
    cube("Height warning label",(-5.0,yy,3.08),(.43,.52,.045),yellow,.015)
    text_obj("2.6m",( -5.19,yy-.03,3.11),.12,black)
    text_obj("8'6\\\"",( -5.19,yy-.19,3.11),.12,black)
cube("Red container sticker",(-5.0,1.45,2.99),(.28,.22,.04),red,.01)
# right-side vertical locking bars/hinges
for x in (-4.82,):
    for z in (-5.5,2.8):
        cube("Door locking bar",(x,2.6,z),(.10,5.0,.12),frame,.018)
        for yy in (.6,1.8,3.0,4.2):
            cube("Door hinge",(x-.07,yy,z+.04),(.25,.14,.16),silver,.02)

# Center two-tier cargo stack.
container("Lower blue cargo",(-.65,1.3,-8.3),(3.0,2.6,2.5),blue,True)
container("Lower rust cargo",(2.45,1.3,-8.3),(3.0,2.6,2.5),red,True)
container("Upper green cargo",(.35,3.9,-8.3),(6.0,2.6,2.5),upper,True,True)
text_obj("..VOGEL",(-1.75,4.0,-7.0),.55,white)

# Dirty drum beside the left container.
cyl("Dirty steel drum",(-3.65,.52,-1.55),.36,1.04,drum_mat,32)
for yy in (.08,.96):
    bpy.ops.mesh.primitive_torus_add(major_radius=.345,minor_radius=.018,major_segments=24,minor_segments=6,rotation=(math.pi/2,0,0), location=(-3.65,yy,-1.55))
    assign(bpy.context.object,frame)
# Simple circular abstract emblem on front of drum (not a real-world logo).
disc=cyl("Drum emblem disc",(-3.65,.55,-1.18),.19,.018,black,24); disc.rotation_euler[0]=0
center_disc=cyl("Emblem center",(-3.65,.55,-1.165),.085,.02,silver,16); center_disc.rotation_euler[0]=0
for a in range(8):
    ang=a*math.tau/8
    cube("Emblem radial mark",(-3.65+math.cos(ang)*.13,.55+math.sin(ang)*.13,-1.15),(.025,.09,.02),white,.004)

# Right pallet and six plastic crates, then three aluminum transit cases.
cube("Cargo pallet",(4.65,.12,-5.4),(2.6,.22,2.1),frame,.04)
for row in range(3):
    for col in range(2):
        x=4.0+col*.9; z=-6.0+row*.62
        cm=crateblue if (row+col)%2==0 else white
        cube("Plastic crate",(x,.48+row*.62,z),(.82,.58,.72),cm,.055)
        # stamped dark round emblem on front
        cyl("Crate emblem",(x,.49+row*.62,z+.37),.13,.018,black,20)
        cube("Crate latch",(x,.45+row*.62,z+.39),(.12,.05,.025),silver,.008)
for row in range(3):
    y=.48+row*.62
    cube("Aluminum transit case",(5.75,y,-5.4),(1.65,.58,1.2),silver,.06)
    for zoff in (-.39,.39):
        cube("Case seam",(5.75,y,-5.4+zoff),(1.58,.025,.025),frame,.005)
    for xoff in (-.58,.58):
        cube("Case latch",(5.75+xoff,y,-4.78),(.18,.12,.05),frame,.012)

# Large battered beige crate, partly cropped at right edge.
cube("Large beige cargo crate",(7.45,1.55,-2.4),(1.6,3.1,2.3),beige,.07)
for i in range(8):
    x=6.8+random.random()*1.2; y=.25+random.random()*2.5
    cube("Black peeling paint patch",(x,y,-1.22),(.15+random.random()*.22,.08+random.random()*.18,.025),black,.006)

# Distant ship rail, red-brown bulwark, pipes and crane silhouette.
cube("Ship bulwark",(0,.8,-10.1),(16,1.6,.32),red,.04)
cube("Horizontal pipe",(4.0,2.0,-9.65),(8,.12,.12),silver,.025)
for x in (-3.8,-2.6,-1.4):
    cube("Distant crane leg",(x,3.3,-10.5),(.12,6.6,.12),rustmetal,.015)
cube("Distant crane beam",(-2.6,6.6,-10.5),(5.0,.15,.16),rustmetal,.02)
# Crane boom from upper right toward center.
boom=cube("Overhead crane boom",(5.0,7.1,-5.0),(7.0,.22,.3),rustmetal,.035)
boom.rotation_euler[1]=-.48
for i in range(5):
    x=3.0+i*.75
    cable=cube("Crane cable",(x,5.7,-5.2),(.018,3.0,.018),black,.002)
    cable.rotation_euler[1]=-.08
# Small distant helmet silhouette.
cyl("Distant bollard",(6.0,.7,-9.55),.14,1.4,black,8)
bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=.22, location=(6.0,1.5,-9.55))
assign(bpy.context.object,white)

# Export only the authored environment meshes. Lights/camera remain in scene only if added later.
bpy.ops.object.select_all(action="SELECT")
bpy.context.view_layer.objects.active = bpy.context.selected_objects[0] if bpy.context.selected_objects else None
print("Exporting GLB to:", OUT, flush=True)
export_result = bpy.ops.export_scene.gltf(
    filepath=OUT,
    export_format="GLB",
    use_selection=True,
    export_apply=True,
    export_texcoords=True,
    export_normals=True,
    export_materials="EXPORT",
    export_image_format="AUTO",
    export_cameras=False,
    export_lights=False,
)
print("Exporter result:", export_result, flush=True)
if "FINISHED" not in export_result:
    raise RuntimeError("glTF exporter did not finish successfully: %r" % (export_result,))
if not os.path.isfile(OUT) or os.path.getsize(OUT) <= 20:
    raise RuntimeError("Exporter returned without producing a non-empty GLB: " + OUT)
print("WROTE_GL B:", OUT, "size:", os.path.getsize(OUT), "bytes", flush=True)
