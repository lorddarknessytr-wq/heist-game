# =============================================================================
# BLOCK HARBOR — THE NIGHT COURIER (corrected build)
# Blender 4.2 LTS | Output: character.glb
# Procedural voxel character, 20-bone rig, pixel atlas, 7 animation clips.
#
# Run:
#   blender --background --factory-startup --python night_courier.py -- ./output
# =============================================================================

import bpy
import sys
import os
import math
import json
import struct
import random
import tempfile
import shutil
import traceback
from mathutils import Vector, Matrix, Quaternion

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
FPS = 30
TARGET_HEIGHT = 2.20
CHARACTER_NAME = "NIGHT_COURIER"
OUTPUT_NAME = "character.glb"
ATLAS_SIZE = 256
TILE_SIZE = 16
GRID = ATLAS_SIZE // TILE_SIZE
MASK_COL = 12
MASK_ROW = 0

# Texture atlas tiles (row-major indexing: row * GRID + column).
T_FABRIC = 0
T_HOOD = 1
T_ARMOR = 2
T_TROUSERS = 3
T_MASK_SIDE = 4
T_TEAL = 5
T_AMBER = 6
T_LIGHT = 7
T_BOOT = 8
T_GLOVE = 9
T_PACK = 10
T_SIGIL = 11
T_STRAP = 22
T_METAL = 23
T_SCREEN = 24
T_HOOD_INNER = 25
T_KNEE = 26
T_CHEST = 27
T_BELT = 30
T_SOLE = 31
T_VENT = 32
T_TRIM = 33

M_FABRIC, M_ARMOR, M_MASK, M_BOOT, M_GEAR = range(5)

REQUIRED_BONES = [
    "Root", "Hips", "Spine", "Chest", "Neck", "Head",
    "Shoulder_L", "UpperArm_L", "LowerArm_L", "Hand_L",
    "Shoulder_R", "UpperArm_R", "LowerArm_R", "Hand_R",
    "UpperLeg_L", "LowerLeg_L", "Foot_L",
    "UpperLeg_R", "LowerLeg_R", "Foot_R",
]

# clip -> (frame count, intended loop, key sampling step)
CLIPS = {
    "IDLE":         (121, True,  3),
    "LOOK_AROUND":  (151, True,  3),
    "WALK":          (49, True,  1),
    "RUN":           (31, True,  1),
    "TURN_LEFT":     (46, False, 1),
    "TURN_RIGHT":    (46, False, 1),
    "SOCIAL_WAVE":   (91, False, 1),
}

TAU = math.pi * 2.0
RNG = random.Random(20261113)


def log(message):
    print("[NIGHT_COURIER] " + str(message), flush=True)


def fail(message):
    raise RuntimeError(str(message))


def clamp(value, low, high):
    return max(low, min(high, value))


def smoothstep(value):
    value = clamp(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def animation_envelope(t, rise=0.16, fall=0.18):
    """Smooth 0->1->0 envelope for a one-shot gesture."""
    if t < rise:
        return smoothstep(t / rise)
    if t > 1.0 - fall:
        return smoothstep((1.0 - t) / fall)
    return 1.0


# -----------------------------------------------------------------------------
# Pixel-art atlas generation
# -----------------------------------------------------------------------------

def hex_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def shade(color, amount):
    return tuple(int(clamp(c + amount, 0, 255)) for c in color)


PALETTE = {
    "fabric": hex_rgb("#23262C"),
    "hood": hex_rgb("#191C21"),
    "armor": hex_rgb("#3A4149"),
    "trousers": hex_rgb("#2B3037"),
    "mask": hex_rgb("#282D34"),
    "teal": hex_rgb("#2F8F86"),
    "eye": hex_rgb("#5FF2DF"),
    "amber": hex_rgb("#C98A3D"),
    "light": hex_rgb("#A7B0B8"),
    "boot": hex_rgb("#17191D"),
    "glove": hex_rgb("#21252B"),
    "pack": hex_rgb("#272C32"),
    "metal": hex_rgb("#3A424B"),
    "dark": hex_rgb("#0C0E11"),
}


class PixelAtlas:
    def __init__(self, size):
        self.size = size
        self.rows = [[(0, 0, 0) for _ in range(size)] for _ in range(size)]

    def rect(self, x, y, width, height, color):
        for yy in range(max(0, y), min(self.size, y + height)):
            row = self.rows[yy]
            for xx in range(max(0, x), min(self.size, x + width)):
                row[xx] = color

    def tile_origin(self, tile_index):
        return (tile_index % GRID) * TILE_SIZE, (tile_index // GRID) * TILE_SIZE

    def fill_tile(self, tile_index, color, noise=0):
        ox, oy = self.tile_origin(tile_index)
        for y in range(TILE_SIZE):
            for x in range(TILE_SIZE):
                delta = RNG.randint(-noise, noise) if noise else 0
                self.rows[oy + y][ox + x] = shade(color, delta)

    def flatten(self):
        # Blender's pixel buffer starts at the bottom-left; our atlas is drawn top-down.
        values = []
        for y in range(self.size - 1, -1, -1):
            for x in range(self.size):
                r, g, b = self.rows[y][x]
                values.extend((r / 255.0, g / 255.0, b / 255.0, 1.0))
        return values


def paint_atlases():
    base = PixelAtlas(ATLAS_SIZE)
    emissive = PixelAtlas(ATLAS_SIZE)
    base.rect(0, 0, ATLAS_SIZE, ATLAS_SIZE, hex_rgb("#101317"))
    emissive.rect(0, 0, ATLAS_SIZE, ATLAS_SIZE, (0, 0, 0))

    def tile_rect(atlas, tile, x, y, w, h, color):
        ox, oy = atlas.tile_origin(tile)
        atlas.rect(ox + x, oy + y, w, h, color)

    # Base material tiles.
    tile_colors = {
        T_FABRIC: PALETTE["fabric"], T_HOOD: PALETTE["hood"],
        T_ARMOR: PALETTE["armor"], T_TROUSERS: PALETTE["trousers"],
        T_MASK_SIDE: PALETTE["mask"], T_TEAL: PALETTE["teal"],
        T_AMBER: PALETTE["amber"], T_LIGHT: PALETTE["light"],
        T_BOOT: PALETTE["boot"], T_GLOVE: PALETTE["glove"],
        T_PACK: PALETTE["pack"], T_SIGIL: PALETTE["pack"],
        T_STRAP: shade(PALETTE["fabric"], -10), T_METAL: PALETTE["metal"],
        T_SCREEN: hex_rgb("#061014"), T_HOOD_INNER: PALETTE["dark"],
        T_KNEE: PALETTE["armor"], T_CHEST: PALETTE["fabric"],
        T_BELT: shade(PALETTE["fabric"], -10), T_SOLE: hex_rgb("#0A0C0E"),
        T_VENT: shade(PALETTE["mask"], -8), T_TRIM: shade(PALETTE["teal"], -30),
    }
    for idx, color in tile_colors.items():
        base.fill_tile(idx, color, 5)
        ox, oy = base.tile_origin(idx)
        base.rect(ox, oy, 16, 1, shade(color, -14))
        base.rect(ox, oy + 15, 16, 1, shade(color, -18))

    # Fabric seams and restrained pixel details.
    ox, oy = base.tile_origin(T_FABRIC)
    base.rect(ox + 2, oy + 5, 1, 7, shade(PALETTE["fabric"], 16))
    base.rect(ox + 11, oy + 3, 2, 1, shade(PALETTE["fabric"], 12))
    ox, oy = base.tile_origin(T_HOOD)
    for i in range(16):
        base.rect(ox + i, oy + (i * 3) % 15, 1, 1, shade(PALETTE["hood"], -8))
    ox, oy = base.tile_origin(T_ARMOR)
    base.rect(ox + 2, oy + 2, 2, 2, shade(PALETTE["armor"], 24))
    base.rect(ox + 12, oy + 12, 2, 2, shade(PALETTE["armor"], -16))
    ox, oy = base.tile_origin(T_BOOT)
    base.rect(ox, oy + 12, 16, 2, shade(PALETTE["boot"], 18))
    ox, oy = base.tile_origin(T_SOLE)
    for x in range(1, 16, 3):
        base.rect(ox + x, oy, 1, 16, hex_rgb("#171A1E"))

    # Small wrist-scanner display.
    ox, oy = base.tile_origin(T_SCREEN)
    base.rect(ox + 1, oy + 1, 14, 14, hex_rgb("#07171A"))
    for y in (3, 6, 9, 12):
        base.rect(ox + 2, oy + y, 12, 1, shade(PALETTE["teal"], -25))
    for x, y in ((3, 8), (4, 7), (5, 9), (6, 6), (7, 8), (8, 5), (9, 7), (10, 8), (11, 6), (12, 8)):
        base.rect(ox + x, oy + y, 1, 1, PALETTE["eye"])
        emissive.rect(ox + x, oy + y, 1, 1, PALETTE["eye"])

    # Original courier emblem.
    ox, oy = base.tile_origin(T_SIGIL)
    emblem_pixels = [
        (5, 2), (6, 2), (7, 2), (8, 2), (9, 2), (10, 2),
        (3, 4), (12, 4), (2, 6), (13, 6), (2, 7), (13, 7),
        (2, 8), (13, 8), (3, 11), (12, 11), (5, 13), (6, 13),
        (7, 13), (8, 13), (9, 13), (10, 13),
    ]
    for x, y in emblem_pixels:
        base.rect(ox + x, oy + y, 1, 1, PALETTE["teal"])
    for x, y in ((7, 9), (8, 8), (9, 7), (8, 10), (9, 9), (10, 8)):
        base.rect(ox + x, oy + y, 1, 1, PALETTE["eye"])
        emissive.rect(ox + x, oy + y, 1, 1, PALETTE["eye"])

    # Corrected 32x32 face-mask atlas region: row * GRID + column = 12.
    mask_x = MASK_COL * TILE_SIZE
    mask_y = MASK_ROW * TILE_SIZE
    base.rect(mask_x, mask_y, 32, 32, PALETTE["mask"])
    base.rect(mask_x, mask_y, 32, 1, shade(PALETTE["mask"], -20))
    base.rect(mask_x, mask_y + 31, 32, 1, shade(PALETTE["mask"], -20))
    base.rect(mask_x, mask_y, 1, 32, shade(PALETTE["mask"], -20))
    base.rect(mask_x + 31, mask_y, 1, 32, shade(PALETTE["mask"], -20))
    # Angular brow, dark eye sockets, cyan eye strips, central nose bridge and vents.
    for x in range(2, 30):
        y = 5 + int(abs(x - 15.5) / 6)
        base.rect(mask_x + x, mask_y + y, 1, 2, shade(PALETTE["armor"], 12))
    base.rect(mask_x + 4, mask_y + 11, 9, 4, hex_rgb("#080B0E"))
    base.rect(mask_x + 19, mask_y + 11, 9, 4, hex_rgb("#080B0E"))
    base.rect(mask_x + 5, mask_y + 12, 7, 2, PALETTE["eye"])
    base.rect(mask_x + 20, mask_y + 12, 7, 2, PALETTE["eye"])
    base.rect(mask_x + 6, mask_y + 12, 5, 1, hex_rgb("#E8FFFA"))
    base.rect(mask_x + 21, mask_y + 12, 5, 1, hex_rgb("#E8FFFA"))
    emissive.rect(mask_x + 5, mask_y + 12, 7, 2, PALETTE["eye"])
    emissive.rect(mask_x + 20, mask_y + 12, 7, 2, PALETTE["eye"])
    base.rect(mask_x + 15, mask_y + 9, 2, 11, shade(PALETTE["mask"], 13))
    base.rect(mask_x + 14, mask_y + 9, 1, 11, shade(PALETTE["mask"], -12))
    base.rect(mask_x + 17, mask_y + 9, 1, 11, shade(PALETTE["mask"], -12))
    base.rect(mask_x + 10, mask_y + 22, 12, 6, shade(PALETTE["mask"], -12))
    for y in (23, 25, 27):
        base.rect(mask_x + 11, mask_y + y, 10, 1, hex_rgb("#07090B"))
    base.rect(mask_x + 27, mask_y + 20, 2, 2, PALETTE["amber"])
    emissive.rect(mask_x + 27, mask_y + 20, 2, 2, PALETTE["amber"])

    return base, emissive


def create_image_from_atlas(atlas, name, temp_dir):
    image = bpy.data.images.new(name, width=ATLAS_SIZE, height=ATLAS_SIZE, alpha=False)
    image.pixels.foreach_set(atlas.flatten())
    image.filepath_raw = os.path.join(temp_dir, name + ".png")
    image.file_format = "PNG"
    image.save()
    loaded = bpy.data.images.load(image.filepath_raw, check_existing=False)
    loaded.name = name
    loaded.colorspace_settings.name = "sRGB"
    loaded.pack()
    bpy.data.images.remove(image)
    return loaded


# -----------------------------------------------------------------------------
# Materials
# -----------------------------------------------------------------------------
def create_materials(base_image, emissive_image):
    specs = [
        ("NC_Fabric", 0.90, 0.00),
        ("NC_Armor", 0.52, 0.45),
        ("NC_Mask", 0.46, 0.35),
        ("NC_Boot", 0.78, 0.05),
        ("NC_Gear", 0.62, 0.25),
    ]
    materials = []
    for name, roughness, metallic in specs:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()
        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (500, 40)
        shader = nodes.new("ShaderNodeBsdfPrincipled")
        shader.location = (180, 40)
        shader.inputs["Roughness"].default_value = roughness
        shader.inputs["Metallic"].default_value = metallic
        base_tex = nodes.new("ShaderNodeTexImage")
        base_tex.location = (-240, 140)
        base_tex.image = base_image
        base_tex.interpolation = "Closest"
        emissive_tex = nodes.new("ShaderNodeTexImage")
        emissive_tex.location = (-240, -120)
        emissive_tex.image = emissive_image
        emissive_tex.interpolation = "Closest"
        links.new(base_tex.outputs["Color"], shader.inputs["Base Color"])
        emission_input = shader.inputs.get("Emission Color") or shader.inputs.get("Emission")
        if emission_input is not None:
            links.new(emissive_tex.outputs["Color"], emission_input)
        strength_input = shader.inputs.get("Emission Strength")
        if strength_input is not None:
            strength_input.default_value = 1.0
        links.new(shader.outputs["BSDF"], output.inputs["Surface"])
        materials.append(mat)
    return materials


# -----------------------------------------------------------------------------
# Voxel mesh builder
# -----------------------------------------------------------------------------
FACE_KEYS = ("-Z", "+Z", "-Y", "+Y", "+X", "-X")
FACE_VERTICES = (
    (0, 3, 2, 1),  # -Z
    (4, 5, 6, 7),  # +Z
    (0, 1, 5, 4),  # -Y: front
    (2, 3, 7, 6),  # +Y: back
    (1, 2, 6, 5),  # +X
    (3, 0, 4, 7),  # -X
)


def atlas_uv(tile_index, span=1):
    column = tile_index % GRID
    row = tile_index // GRID
    pad = 0.35
    u0 = (column * TILE_SIZE + pad) / ATLAS_SIZE
    u1 = ((column + span) * TILE_SIZE - pad) / ATLAS_SIZE
    v1 = 1.0 - (row * TILE_SIZE + pad) / ATLAS_SIZE
    v0 = 1.0 - ((row + span) * TILE_SIZE - pad) / ATLAS_SIZE
    return u0, v0, u1, v1


def resolve_tile(spec, face_key):
    selected = spec.get(face_key, spec.get("all", T_FABRIC)) if isinstance(spec, dict) else spec
    if isinstance(selected, tuple):
        return selected
    return selected, 1


class PartBuilder:
    def __init__(self):
        self.vertices = []
        self.faces = []
        self.uvs = []
        self.material_indices = []

    def box(self, width, depth, height, x, y, z, tile_spec, material_slot, rotation=None):
        hx, hy, hz = width / 2.0, depth / 2.0, height / 2.0
        corners = [
            (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
            (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
        ]
        transform = Matrix.Translation((x, y, z))
        if rotation is not None:
            transform = transform @ rotation
        base_index = len(self.vertices)
        for corner in corners:
            self.vertices.append(tuple(transform @ Vector(corner)))
        for face_index, face in enumerate(FACE_VERTICES):
            self.faces.append(tuple(base_index + i for i in face))
            tile_index, span = resolve_tile(tile_spec, FACE_KEYS[face_index])
            u0, v0, u1, v1 = atlas_uv(tile_index, span)
            self.uvs.extend(((u0, v0), (u1, v0), (u1, v1), (u0, v1)))
            self.material_indices.append(material_slot)

    def build_object(self, name, bone_name, materials, armature, collection):
        if not self.faces:
            fail("PartBuilder for %s contains no faces" % name)
        if len(self.faces) != len(self.material_indices):
            fail("Face/material index count mismatch for %s" % name)
        mesh = bpy.data.meshes.new(name + "_Mesh")
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        for mat in materials:
            mesh.materials.append(mat)
        uv_layer = mesh.uv_layers.new(name="UVMap")
        uv_index = 0
        for polygon in mesh.polygons:
            polygon.material_index = self.material_indices[polygon.index]
            if polygon.material_index >= len(mesh.materials):
                fail("Invalid material index on %s" % name)
            for loop_index in polygon.loop_indices:
                uv_layer.data[loop_index].uv = self.uvs[uv_index]
                uv_index += 1
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        group = obj.vertex_groups.new(name=bone_name)
        group.add(list(range(len(mesh.vertices))), 1.0, "REPLACE")
        modifier = obj.modifiers.new("NC_Armature", "ARMATURE")
        modifier.object = armature
        modifier.use_vertex_groups = True
        obj.parent = armature
        obj.parent_type = "OBJECT"
        obj.location = (0.0, 0.0, 0.0)
        obj.rotation_euler = (0.0, 0.0, 0.0)
        obj.scale = (1.0, 1.0, 1.0)
        return obj


# -----------------------------------------------------------------------------
# Character geometry
# Blender coordinates: Z up, character front points toward -Y.
# -----------------------------------------------------------------------------
def build_character(materials, armature, mesh_collection):
    parts = {}

    def part(name, bone):
        builder = PartBuilder()
        parts[name] = (builder, bone)
        return builder

    # Hips / belt.
    p = part("NC_Hips", "Hips")
    p.box(0.50, 0.30, 0.16, 0, 0, 0.96, T_TROUS, M_FABRIC)
    p.box(0.52, 0.32, 0.07, 0, 0, 1.03, {"-Y": T_BELT, "all": T_STRAP}, M_GEAR)
    p.box(0.10, 0.03, 0.06, 0, -0.17, 1.03, T_LIGHT, M_ARMOR)
    p.box(0.06, 0.10, 0.12, 0.26, 0, 0.95, T_PACK, M_GEAR)
    p.box(0.06, 0.10, 0.12, -0.26, 0, 0.95, T_PACK, M_GEAR)

    # Lower jacket / spine.
    p = part("NC_Spine", "Spine")
    p.box(0.54, 0.31, 0.20, 0, 0, 1.14, T_FABRIC, M_FABRIC)
    p.box(0.55, 0.32, 0.04, 0, 0, 1.06, T_STRAP, M_GEAR)
    p.box(0.02, 0.20, 0.16, 0.275, 0, 1.14, T_TEAL, M_FABRIC)
    p.box(0.02, 0.20, 0.16, -0.275, 0, 1.14, T_TEAL, M_FABRIC)

    # Chest, shoulder plates, backpack and insignia.
    p = part("NC_Chest", "Chest")
    p.box(0.56, 0.32, 0.32, 0, 0, 1.40,
          {"-Y": T_CHEST, "+Y": T_FABRIC, "+Z": T_HOOD_INNER, "all": T_FABRIC}, M_FABRIC)
    p.box(0.30, 0.26, 0.06, 0, 0, 1.585, T_HOOD_INNER, M_FABRIC)
    for side in (1, -1):
        p.box(0.28, 0.32, 0.12, side * 0.38, 0, 1.52, T_ARMOR, M_ARMOR)
        p.box(0.22, 0.26, 0.05, side * 0.38, 0, 1.595,
              {"+Z": T_TEAL, "all": T_ARMOR}, M_ARMOR)
        p.box(0.13, 0.05, 0.11, side * 0.14, -0.185, 1.30,
              {"-Y": T_PACK, "all": T_FABRIC}, M_FABRIC)
        p.box(0.14, 0.055, 0.03, side * 0.14, -0.185, 1.365, T_ARMOR, M_ARMOR)
        p.box(0.02, 0.20, 0.16, side * 0.29, 0, 1.40, T_TEAL, M_FABRIC)
        p.box(0.07, 0.36, 0.05, side * 0.16, 0.02, 1.565, T_STRAP, M_GEAR,
              Matrix.Rotation(0.10, 3, "X"))
    p.box(0.06, 0.02, 0.04, 0.38, -0.17, 1.54, T_AMBER, M_GEAR)
    p.box(0.03, 0.02, 0.05, 0, -0.175, 1.52, T_AMBER, M_GEAR)
    p.box(0.40, 0.02, 0.30, 0, 0.17, 1.42, T_PACK, M_GEAR)
    p.box(0.30, 0.08, 0.30, 0, 0.20, 1.38, T_HOOD_INNER, M_FABRIC)
    p.box(0.40, 0.16, 0.44, 0, 0.26, 1.38, {"+Y": T_SIGIL, "all": T_PACK}, M_GEAR)
    p.box(0.36, 0.15, 0.09, 0, 0.265, 1.625, T_ARMOR, M_ARMOR)
    p.box(0.09, 0.12, 0.22, 0.245, 0.26, 1.35, {"+X": T_TEAL, "all": T_PACK}, M_GEAR)
    p.box(0.09, 0.12, 0.22, -0.245, 0.26, 1.35, {"-X": T_TEAL, "all": T_PACK}, M_GEAR)
    p.box(0.36, 0.13, 0.10, 0, 0.26, 1.11, T_TROUS, M_FABRIC)
    for cx, cz in ((0.185, 1.585), (-0.185, 1.585), (0.185, 1.175), (-0.185, 1.175)):
        p.box(0.05, 0.17, 0.05, cx, 0.26, cz, T_ARMOR, M_ARMOR)
    p.box(0.04, 0.02, 0.04, 0.12, 0.345, 1.50, T_AMBER, M_GEAR)

    # Neck.
    p = part("NC_Neck", "Neck")
    p.box(0.16, 0.16, 0.08, 0, 0, 1.60, T_HOOD_INNER, M_FABRIC)

    # Head and layered hood. FIX: mask atlas tile index is row * GRID + column (12), not 192.
    p = part("NC_Head", "Head")
    p.box(0.50, 0.50, 0.50, 0, 0, 1.88,
          {"-Y": T_HOOD_INNER, "all": T_HOOD}, M_FABRIC)
    mask_start_tile = MASK_ROW * GRID + MASK_COL  # Corrected row-major indexing.
    p.box(0.40, 0.06, 0.36, 0, -0.26, 1.87,
          {"-Y": (mask_start_tile, 2), "all": T_MASK_SIDE}, M_MASK)
    p.box(0.42, 0.07, 0.07, 0, -0.265, 2.045, T_ARMOR, M_ARMOR)
    p.box(0.07, 0.05, 0.15, 0.175, -0.265, 1.785, T_ARMOR, M_ARMOR)
    p.box(0.07, 0.05, 0.15, -0.175, -0.265, 1.785, T_ARMOR, M_ARMOR)
    p.box(0.18, 0.05, 0.07, 0, -0.265, 1.705, T_VENT, M_MASK)
    p.box(0.44, 0.02, 0.44, 0, -0.225, 1.88, T_HOOD_INNER, M_FABRIC)
    p.box(0.58, 0.56, 0.08, 0, 0.02, 2.16, T_HOOD, M_FABRIC)
    p.box(0.58, 0.07, 0.52, 0, 0.285, 1.89, T_HOOD, M_FABRIC)
    p.box(0.07, 0.52, 0.48, 0.285, 0.03, 1.90, T_HOOD, M_FABRIC)
    p.box(0.07, 0.52, 0.48, -0.285, 0.03, 1.90, T_HOOD, M_FABRIC)
    p.box(0.58, 0.16, 0.10, 0, -0.21, 2.12, T_HOOD, M_FABRIC)
    p.box(0.40, 0.09, 0.14, 0, 0.27, 1.575, T_HOOD, M_FABRIC)
    p.box(0.30, 0.08, 0.08, 0, 0.24, 1.50, T_HOOD, M_FABRIC)
    p.box(0.22, 0.18, 0.05, 0, 0.16, 2.175, T_HOOD, M_FABRIC)

    # Arms and hands.
    for side, suffix in ((1, "L"), (-1, "R")):
        p = part("NC_UpperArm_" + suffix, "UpperArm_" + suffix)
        p.box(0.18, 0.20, 0.30, side * 0.37, 0, 1.35, T_FABRIC, M_FABRIC)
        p.box(0.20, 0.22, 0.08, side * 0.37, 0, 1.48, T_ARMOR, M_ARMOR)
        p.box(0.19, 0.21, 0.04, side * 0.37, 0, 1.22, T_STRAP, M_GEAR)

        p = part("NC_LowerArm_" + suffix, "LowerArm_" + suffix)
        p.box(0.16, 0.18, 0.24, side * 0.37, 0, 1.07, T_FABRIC, M_FABRIC)
        p.box(0.17, 0.19, 0.05, side * 0.37, 0, 0.965, T_STRAP, M_GEAR)
        if suffix == "L":
            p.box(0.05, 0.09, 0.07, side * 0.475, 0, 1.10,
                  {"+X": T_SCREEN, "all": T_METAL}, M_GEAR)

        p = part("NC_Hand_" + suffix, "Hand_" + suffix)
        p.box(0.17, 0.19, 0.13, side * 0.37, 0, 0.875, T_GLOVE, M_BOOT)
        p.box(0.18, 0.10, 0.04, side * 0.37, -0.05, 0.90, T_ARMOR, M_ARMOR)
        p.box(0.10, 0.04, 0.06, side * 0.37, -0.10, 0.84, T_GLOVE, M_BOOT)

    # Legs and boots.
    for side, suffix in ((1, "L"), (-1, "R")):
        p = part("NC_UpperLeg_" + suffix, "UpperLeg_" + suffix)
        p.box(0.22, 0.24, 0.34, side * 0.15, 0, 0.75, T_TROUSERS, M_FABRIC)
        p.box(0.24, 0.26, 0.05, side * 0.15, 0, 0.84, T_STRAP, M_GEAR)
        p.box(0.05, 0.14, 0.12, side * 0.285, -0.02, 0.75, T_PACK, M_GEAR)

        p = part("NC_LowerLeg_" + suffix, "LowerLeg_" + suffix)
        p.box(0.20, 0.22, 0.32, side * 0.15, 0, 0.40, T_TROUSERS, M_FABRIC)
        p.box(0.22, 0.06, 0.12, side * 0.15, -0.12, 0.56,
              {"-Y": T_KNEE, "all": T_ARMOR}, M_ARMOR)

        p = part("NC_Foot_" + suffix, "Foot_" + suffix)
        p.box(0.26, 0.34, 0.24, side * 0.15, -0.04, 0.12,
              {"+Z": T_BOOT, "-Z": T_SOLE, "all": T_BOOT}, M_BOOT)
        p.box(0.27, 0.10, 0.10, side * 0.15, -0.17, 0.06, T_ARMOR, M_ARMOR)
        p.box(0.10, 0.04, 0.06, side * 0.15, 0.145, 0.20, T_TEAL, M_FABRIC)
        p.box(0.20, 0.02, 0.04, side * 0.15, -0.165, 0.215, T_STRAP, M_GEAR)

    objects = []
    for object_name, (builder, bone_name) in parts.items():
        objects.append(builder.build_object(object_name, bone_name, materials, armature, mesh_collection))
    return objects


# -----------------------------------------------------------------------------
# Armature (exactly 20 deform bones)
# -----------------------------------------------------------------------------
def build_armature(rig_collection):
    armature_data = bpy.data.armatures.new(CHARACTER_NAME + "_Armature")
    armature = bpy.data.objects.new(CHARACTER_NAME + "_Rig", armature_data)
    rig_collection.objects.link(armature)
    armature.location = (0.0, 0.0, 0.0)
    bpy.ops.object.select_all(action="DESELECT")
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature_data.edit_bones

    def add_bone(name, head, tail, parent=None, connected=False):
        bone = edit_bones.new(name)
        bone.head = Vector(head)
        bone.tail = Vector(tail)
        bone.use_deform = True
        if parent:
            bone.parent = edit_bones[parent]
            bone.use_connect = connected
        return bone

    add_bone("Root", (0, 0, 0), (0, 0, 0.20))
    add_bone("Hips", (0, 0, 0.98), (0, 0, 1.12), "Root")
    add_bone("Spine", (0, 0, 1.12), (0, 0, 1.32), "Hips", True)
    add_bone("Chest", (0, 0, 1.32), (0, 0, 1.56), "Spine", True)
    add_bone("Neck", (0, 0, 1.56), (0, 0, 1.64), "Chest", True)
    add_bone("Head", (0, 0, 1.64), (0, 0, 2.14), "Neck", True)

    for side, suffix in ((1, "L"), (-1, "R")):
        add_bone("Shoulder_" + suffix, (side * 0.10, 0, 1.52),
                 (side * 0.30, 0, 1.52), "Chest")
        add_bone("UpperArm_" + suffix, (side * 0.37, 0, 1.50),
                 (side * 0.37, 0, 1.20), "Shoulder_" + suffix)
        add_bone("LowerArm_" + suffix, (side * 0.37, 0, 1.20),
                 (side * 0.37, 0, 0.94), "UpperArm_" + suffix, True)
        add_bone("Hand_" + suffix, (side * 0.37, 0, 0.94),
                 (side * 0.37, 0, 0.82), "LowerArm_" + suffix, True)
        add_bone("UpperLeg_" + suffix, (side * 0.15, 0, 0.94),
                 (side * 0.15, 0, 0.56), "Hips")
        add_bone("LowerLeg_" + suffix, (side * 0.15, 0, 0.56),
                 (side * 0.15, 0, 0.24), "UpperLeg_" + suffix, True)
        add_bone("Foot_" + suffix, (side * 0.15, 0, 0.24),
                 (side * 0.15, -0.22, 0.06), "LowerLeg_" + suffix, True)

    bpy.ops.object.mode_set(mode="OBJECT")
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"
    return armature


# -----------------------------------------------------------------------------
# Animation authoring
# -----------------------------------------------------------------------------
class Animator:
    def __init__(self, armature):
        self.armature = armature
        self.inverse_rest = {
            bone.name: bone.matrix_local.to_3x3().inverted()
            for bone in armature.data.bones
        }

    def reset_pose(self):
        for pose_bone in self.armature.pose.bones:
            pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            pose_bone.location = (0.0, 0.0, 0.0)

    def rotate_world_axis(self, bone_name, axis, angle):
        if abs(angle) < 1e-8:
            return
        local_axis = self.inverse_rest[bone_name] @ Vector(axis)
        if local_axis.length < 1e-8:
            return
        local_axis.normalize()
        delta = Quaternion(local_axis, angle)
        pose_bone = self.armature.pose.bones[bone_name]
        pose_bone.rotation_quaternion = (delta @ pose_bone.rotation_quaternion).normalized()

    def move_world(self, bone_name, delta):
        local_delta = self.inverse_rest[bone_name] @ Vector(delta)
        pose_bone = self.armature.pose.bones[bone_name]
        pose_bone.location = Vector(pose_bone.location) + local_delta

    def build_action(self, name, frame_count, sample_step, pose_function):
        action = bpy.data.actions.new(name)
        action.use_fake_user = True
        self.armature.animation_data_create()
        self.armature.animation_data.action = action
        frames = list(range(1, frame_count + 1, sample_step))
        if frames[-1] != frame_count:
            frames.append(frame_count)
        for frame in frames:
            t = (frame - 1) / float(frame_count - 1)
            self.reset_pose()
            pose_function(self, t)
            for pose_bone in self.armature.pose.bones:
                pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=pose_bone.name)
                pose_bone.keyframe_insert(data_path="location", frame=frame, group=pose_bone.name)
        # Smooth curves; exact loop endpoints are authored at the same pose.
        for curve in action.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = "BEZIER"
                key.handle_left_type = "AUTO_CLAMPED"
                key.handle_right_type = "AUTO_CLAMPED"
        self.armature.animation_data.action = None
        return action


def pose_idle(animator, t):
    breath = math.sin(TAU * t)
    secondary = math.sin(TAU * 2.0 * t)
    animator.move_world("Hips", (0.0, 0.0, 0.006 * breath))
    animator.rotate_world_axis("Hips", (0, 0, 1), 0.012 * breath)
    animator.rotate_world_axis("Spine", (1, 0, 0), 0.010 * math.sin(TAU * t + 0.6))
    animator.move_world("Chest", (0.0, 0.0, 0.008 * breath))
    animator.rotate_world_axis("Chest", (0, 0, 1), -0.010 * breath)
    animator.rotate_world_axis("Head", (0, 0, 1), 0.055 * breath + 0.018 * secondary)
    animator.rotate_world_axis("Head", (1, 0, 0), 0.020 * math.sin(TAU * t + 1.2))
    animator.rotate_world_axis("UpperArm_L", (1, 0, 0), 0.025 * math.sin(TAU * t + 0.4))
    animator.rotate_world_axis("UpperArm_R", (1, 0, 0), 0.025 * math.sin(TAU * t + 0.9))
    animator.rotate_world_axis("LowerArm_L", (1, 0, 0), -0.05 + 0.015 * breath)
    animator.rotate_world_axis("LowerArm_R", (1, 0, 0), -0.05 + 0.015 * breath)
    animator.rotate_world_axis("UpperLeg_L", (1, 0, 0), 0.006 * breath)
    animator.rotate_world_axis("UpperLeg_R", (1, 0, 0), -0.006 * breath)


def pose_look_around(animator, t):
    yaw = 0.42 * math.sin(TAU * t)
    animator.rotate_world_axis("Head", (0, 0, 1), yaw)
    animator.rotate_world_axis("Head", (1, 0, 0), 0.045 * math.sin(TAU * 2.0 * t))
    animator.rotate_world_axis("Neck", (0, 0, 1), 0.14 * yaw)
    animator.rotate_world_axis("Chest", (0, 0, 1), 0.10 * math.sin(TAU * t - 0.4))
    animator.rotate_world_axis("Spine", (0, 0, 1), 0.04 * math.sin(TAU * t - 0.2))
    animator.move_world("Hips", (0.0, 0.0, 0.003 * math.sin(TAU * 2.0 * t)))


def pose_walk(animator, t):
    phase = TAU * t
    left = math.sin(phase)
    right = math.sin(phase + math.pi)
    stride = 0.34
    animator.rotate_world_axis("UpperLeg_L", (1, 0, 0), stride * left)
    animator.rotate_world_axis("UpperLeg_R", (1, 0, 0), stride * right)
    knee_l = 0.40 * max(0.0, -math.sin(phase - 0.55)) + 0.035
    knee_r = 0.40 * max(0.0, -math.sin(phase + math.pi - 0.55)) + 0.035
    animator.rotate_world_axis("LowerLeg_L", (1, 0, 0), knee_l)
    animator.rotate_world_axis("LowerLeg_R", (1, 0, 0), knee_r)
    animator.rotate_world_axis("Foot_L", (1, 0, 0), -stride * left * 0.48 - knee_l * 0.28)
    animator.rotate_world_axis("Foot_R", (1, 0, 0), -stride * right * 0.48 - knee_r * 0.28)
    animator.rotate_world_axis("UpperArm_L", (1, 0, 0), -0.23 * left)
    animator.rotate_world_axis("UpperArm_R", (1, 0, 0), -0.23 * right)
    animator.rotate_world_axis("LowerArm_L", (1, 0, 0), -0.15 - 0.06 * max(0.0, left))
    animator.rotate_world_axis("LowerArm_R", (1, 0, 0), -0.15 - 0.06 * max(0.0, right))
    animator.move_world("Hips", (0.008 * left, 0.0, 0.018 * (0.5 - 0.5 * math.cos(2.0 * phase))))
    animator.rotate_world_axis("Hips", (0, 0, 1), 0.035 * left)
    animator.rotate_world_axis("Chest", (0, 0, 1), -0.045 * left)
    animator.rotate_world_axis("Head", (0, 0, 1), 0.018 * left)


def pose_run(animator, t):
    phase = TAU * t
    left = math.sin(phase)
    right = math.sin(phase + math.pi)
    stride = 0.58
    animator.rotate_world_axis("UpperLeg_L", (1, 0, 0), stride * left)
    animator.rotate_world_axis("UpperLeg_R", (1, 0, 0), stride * right)
    knee_l = 0.78 * max(0.0, -math.sin(phase - 0.65)) + 0.08
    knee_r = 0.78 * max(0.0, -math.sin(phase + math.pi - 0.65)) + 0.08
    animator.rotate_world_axis("LowerLeg_L", (1, 0, 0), knee_l)
    animator.rotate_world_axis("LowerLeg_R", (1, 0, 0), knee_r)
    animator.rotate_world_axis("Foot_L", (1, 0, 0), -stride * left * 0.45 - knee_l * 0.30)
    animator.rotate_world_axis("Foot_R", (1, 0, 0), -stride * right * 0.45 - knee_r * 0.30)
    animator.rotate_world_axis("UpperArm_L", (1, 0, 0), -0.46 * left)
    animator.rotate_world_axis("UpperArm_R", (1, 0, 0), -0.46 * right)
    animator.rotate_world_axis("LowerArm_L", (1, 0, 0), -0.62)
    animator.rotate_world_axis("LowerArm_R", (1, 0, 0), -0.62)
    animator.move_world("Hips", (0.010 * left, 0.0, 0.035 * (0.5 - 0.5 * math.cos(2.0 * phase))))
    animator.rotate_world_axis("Hips", (0, 0, 1), 0.055 * left)
    animator.rotate_world_axis("Spine", (1, 0, 0), 0.075)
    animator.rotate_world_axis("Chest", (0, 0, 1), -0.065 * left)
    animator.rotate_world_axis("Head", (1, 0, 0), -0.035)


def make_turn_pose(direction):
    def pose(animator, t):
        eased = smoothstep(clamp((t - 0.10) / 0.78, 0.0, 1.0))
        animator.rotate_world_axis("Root", (0, 0, 1), direction * (math.pi / 2.0) * eased)
        animator.rotate_world_axis("Head", (0, 0, 1), direction * 0.22 * smoothstep(clamp(t / 0.28, 0.0, 1.0)) * (1.0 - eased))
        animator.rotate_world_axis("Chest", (0, 0, 1), direction * 0.08 * math.sin(math.pi * t))
        step = math.sin(math.pi * clamp((t - 0.05) / 0.48, 0.0, 1.0))
        lead = "UpperLeg_L" if direction > 0 else "UpperLeg_R"
        trail = "UpperLeg_R" if direction > 0 else "UpperLeg_L"
        lead_knee = "LowerLeg_L" if direction > 0 else "LowerLeg_R"
        animator.rotate_world_axis(lead, (1, 0, 0), -0.22 * step)
        animator.rotate_world_axis(lead_knee, (1, 0, 0), 0.32 * step)
        animator.rotate_world_axis(trail, (1, 0, 0), 0.10 * step)
        animator.move_world("Hips", (0.0, 0.0, -0.018 * step))
        animator.rotate_world_axis("UpperArm_L", (1, 0, 0), 0.11 * step * direction)
        animator.rotate_world_axis("UpperArm_R", (1, 0, 0), -0.11 * step * direction)
    return pose


def pose_social_wave(animator, t):
    env = animation_envelope(t, 0.18, 0.18)
    # Right arm is on negative X. Rotation about Y lifts it outward and upward.
    animator.rotate_world_axis("Shoulder_R", (0, 1, 0), 0.22 * env)
    animator.rotate_world_axis("UpperArm_R", (0, 1, 0), 2.05 * env)
    animator.rotate_world_axis("UpperArm_R", (1, 0, 0), -0.20 * env)
    animator.rotate_world_axis("LowerArm_R", (1, 0, 0), -0.72 * env)
    wrist_wave = 0.34 * math.sin(TAU * 2.5 * t) * env
    animator.rotate_world_axis("Hand_R", (0, 1, 0), wrist_wave)
    animator.rotate_world_axis("Hand_R", (0, 0, 1), 0.10 * math.sin(TAU * 2.5 * t) * env)
    animator.rotate_world_axis("Head", (0, 0, 1), -0.08 * env)
    animator.rotate_world_axis("Chest", (0, 0, 1), -0.035 * env)


POSE_FUNCTIONS = {
    "IDLE": pose_idle,
    "LOOK_AROUND": pose_look_around,
    "WALK": pose_walk,
    "RUN": pose_run,
    "TURN_LEFT": make_turn_pose(1),
    "TURN_RIGHT": make_turn_pose(-1),
    "SOCIAL_WAVE": pose_social_wave,
}


def build_animations(armature):
    animator = Animator(armature)
    actions = {}
    for name, (frame_count, should_loop, step) in CLIPS.items():
        action = animator.build_action(name, frame_count, step, POSE_FUNCTIONS[name])
        actions[name] = action
        log("Created action %-13s frames=1..%d loop=%s" % (name, frame_count, should_loop))

    animation_data = armature.animation_data
    animation_data.action = None
    for name, action in actions.items():
        track = animation_data.nla_tracks.new()
        track.name = name
        strip = track.strips.new(name, int(action.frame_range[0]), action)
        strip.name = name
        strip.blend_type = "REPLACE"
        strip.extrapolation = "NOTHING"
        strip.use_auto_blend = False
        strip.mute = False
        track.mute = False
    return actions


# -----------------------------------------------------------------------------
# Preflight checks
# -----------------------------------------------------------------------------
def preflight(armature, mesh_objects, materials, actions):
    log("Running preflight checks...")
    min_point = Vector((1e9, 1e9, 1e9))
    max_point = Vector((-1e9, -1e9, -1e9))
    for obj in mesh_objects:
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            min_point = Vector((min(min_point[i], world[i]) for i in range(3)))
            max_point = Vector((max(max_point[i], world[i]) for i in range(3)))
    height = max_point.z - min_point.z
    if not (TARGET_HEIGHT - 0.12 <= height <= TARGET_HEIGHT + 0.12):
        fail("Character height %.3f is outside target %.2f" % (height, TARGET_HEIGHT))
    if abs(min_point.z) > 0.025:
        fail("Feet are not grounded: minimum Z is %.4f" % min_point.z)
    if min_point.y > -0.20:
        fail("Character front check failed: expected geometry toward -Y")

    bone_names = {bone.name for bone in armature.data.bones}
    missing_bones = [name for name in REQUIRED_BONES if name not in bone_names]
    if missing_bones:
        fail("Missing required bones: %s" % missing_bones)
    if len(bone_names) != len(REQUIRED_BONES):
        fail("Expected exactly %d bones, found %d" % (len(REQUIRED_BONES), len(bone_names)))

    total_vertices = 0
    for obj in mesh_objects:
        mesh = obj.data
        total_vertices += len(mesh.vertices)
        if not mesh.uv_layers:
            fail("Mesh %s has no UV map" % obj.name)
        if len(mesh.materials) != len(materials):
            fail("Mesh %s has %d material slots, expected %d" % (obj.name, len(mesh.materials), len(materials)))
        if any(poly.material_index >= len(materials) for poly in mesh.polygons):
            fail("Mesh %s has an invalid material index" % obj.name)
        groups = {group.name for group in obj.vertex_groups}
        if len(groups) != 1:
            fail("Mesh %s must have exactly one rigid vertex group" % obj.name)
        for vertex in mesh.vertices:
            weight_sum = sum(item.weight for item in vertex.groups)
            if abs(weight_sum - 1.0) > 1e-4:
                fail("Mesh %s vertex %d has weight sum %.4f" % (obj.name, vertex.index, weight_sum))
        if not any(mod.type == "ARMATURE" and mod.object == armature for mod in obj.modifiers):
            fail("Mesh %s has no correct armature modifier" % obj.name)

    for name in CLIPS:
        if name not in actions:
            fail("Missing action %s" % name)
        if len(actions[name].fcurves) == 0:
            fail("Action %s contains no animation curves" % name)
    log("Preflight OK: height=%.3f bones=%d meshes=%d vertices=%d materials=%d" %
        (height, len(bone_names), len(mesh_objects), total_vertices, len(materials)))
    return height, total_vertices


# -----------------------------------------------------------------------------
# GLB parser / validation
# -----------------------------------------------------------------------------
def read_glb_json(path):
    with open(path, "rb") as handle:
        data = handle.read()
    if len(data) < 20 or data[:4] != b"glTF":
        fail("Output is not a binary glTF file")
    version, total_length = struct.unpack_from("<II", data, 4)
    if version != 2:
        fail("Expected GLB version 2, got %d" % version)
    if total_length != len(data):
        fail("GLB header length %d does not match actual size %d" % (total_length, len(data)))
    offset = 12
    json_chunk = None
    while offset + 8 <= len(data):
        chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunk = data[offset:offset + chunk_length]
        if len(chunk) != chunk_length:
            fail("Truncated GLB chunk")
        if chunk_type == 0x4E4F534A:
            json_chunk = chunk
        offset += chunk_length
    if json_chunk is None:
        fail("GLB is missing its JSON chunk")
    return json.loads(json_chunk.decode("utf-8").rstrip("\x00 \t\r\n")), len(data)


def validate_glb(path):
    doc, size = read_glb_json(path)
    problems = []
    if not doc.get("meshes"):
        problems.append("no meshes")
    if not doc.get("materials"):
        problems.append("no materials")
    skins = doc.get("skins", [])
    if not skins:
        problems.append("no skin/skeleton")
    else:
        joints = skins[0].get("joints", [])
        if len(joints) != len(REQUIRED_BONES):
            problems.append("skin joint count %d != %d" % (len(joints), len(REQUIRED_BONES)))

    found = {}
    for animation in doc.get("animations", []):
        name = animation.get("name", "")
        if not animation.get("channels"):
            problems.append("animation %s has no channels" % name)
        for required in CLIPS:
            if name == required or name.endswith(required) or name.endswith("|" + required):
                found[required] = name
    missing = sorted(set(CLIPS) - set(found))
    if missing:
        problems.append("missing animation clips: %s" % missing)

    embedded_images = [image for image in doc.get("images", []) if "bufferView" in image]
    if len(embedded_images) < 2:
        problems.append("expected two embedded atlases, found %d" % len(embedded_images))
    if size < 25_000 or size > 60_000_000:
        problems.append("implausible GLB size: %d bytes" % size)

    # Confirm the skinned mesh attributes exist.
    has_skin_attributes = False
    for mesh in doc.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            attrs = primitive.get("attributes", {})
            if "JOINTS_0" in attrs and "WEIGHTS_0" in attrs:
                has_skin_attributes = True
                break
    if not has_skin_attributes:
        problems.append("no JOINTS_0 / WEIGHTS_0 attributes found")

    return problems, found, size, doc


def ensure_gltf_exporter():
    """Make sure Blender's official glTF 2.0 exporter is registered."""
    try:
        bpy.ops.export_scene.gltf.get_rna_type()
        return
    except Exception:
        pass
    try:
        bpy.ops.preferences.addon_enable(module="io_scene_gltf2")
        bpy.ops.export_scene.gltf.get_rna_type()
        return
    except Exception as exc:
        fail("Blender glTF 2.0 exporter is unavailable or could not be enabled: %s" % exc)


def export_glb(armature, output_path):
    # Filter options against the installed Blender operator RNA so small API
    # differences do not make the whole build fail with an unknown property.
    ensure_gltf_exporter()
    operator_type = bpy.ops.export_scene.gltf.get_rna_type()
    valid_properties = {prop.identifier for prop in operator_type.properties}
    options = {
        "filepath": output_path,
        "export_format": "GLB",
        "use_selection": False,
        "export_animations": True,
        "export_skins": True,
        "export_yup": True,
        "export_apply": False,
        "export_materials": "EXPORT",
        "export_image_format": "AUTO",
        "export_cameras": False,
        "export_lights": False,
        "export_extras": False,
        "export_morph": False,
        "export_force_sampling": True,
        "export_animation_mode": "NLA_TRACKS",
        "export_frame_step": 1,
        "export_optimize_animation_size": False,
    }
    filtered_options = {key: value for key, value in options.items() if key in valid_properties}
    log("Exporting GLB using NLA_TRACKS animation mode...")
    result = bpy.ops.export_scene.gltf(**filtered_options)
    if "FINISHED" not in result:
        fail("Blender glTF exporter did not finish: %s" % result)
    if not os.path.isfile(output_path) or os.path.getsize(output_path) <= 0:
        fail("Exporter did not create a non-empty output file")
    problems, found, size, doc = validate_glb(output_path)
    if problems:
        fail("Exported GLB failed validation: " + "; ".join(problems))
    return found, size, doc


# -----------------------------------------------------------------------------
# Scene setup and main
# -----------------------------------------------------------------------------
def setup_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    root = bpy.data.collections.new(CHARACTER_NAME)
    scene.collection.children.link(root)
    mesh_collection = bpy.data.collections.new("Courier_Meshes")
    rig_collection = bpy.data.collections.new("Courier_Rig")
    root.children.link(mesh_collection)
    root.children.link(rig_collection)
    return scene, mesh_collection, rig_collection


def get_output_dir():
    argv = sys.argv
    if "--" in argv:
        index = argv.index("--")
        if index + 1 < len(argv):
            return os.path.abspath(os.path.expanduser(argv[index + 1]))
    return os.path.abspath(".")


def main():
    if bpy.app.version < (4, 2, 0):
        fail("This script requires Blender 4.2 or newer; found %s" % bpy.app.version_string)
    output_dir = get_output_dir()
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, OUTPUT_NAME)
    log("Blender version: %s" % bpy.app.version_string)
    log("Output directory: %s" % output_dir)

    scene, mesh_collection, rig_collection = setup_scene()
    temp_dir = tempfile.mkdtemp(prefix="night_courier_atlas_")
    try:
        log("Generating pixel-art atlases...")
        base_atlas, emissive_atlas = paint_atlases()
        base_image = create_image_from_atlas(base_atlas, "NC_BaseColor", temp_dir)
        emissive_image = create_image_from_atlas(emissive_atlas, "NC_Emissive", temp_dir)
        materials = create_materials(base_image, emissive_image)

        log("Building 20-bone rig...")
        armature = build_armature(rig_collection)
        log("Building voxel character meshes...")
        mesh_objects = build_character(materials, armature, mesh_collection)
        log("Authoring seven animation clips...")
        actions = build_animations(armature)

        scene.frame_start = 1
        scene.frame_end = CLIPS["IDLE"][0]
        scene.render.fps = FPS
        bpy.context.view_layer.update()
        height, vertex_count = preflight(armature, mesh_objects, materials, actions)
        found, size, document = export_glb(armature, output_path)

        log("================ EXPORT REPORT ================")
        log("File            : %s" % output_path)
        log("Format          : GLB v2")
        log("Size            : %.2f MB" % (size / 1_000_000.0))
        log("Height          : %.3f units" % height)
        log("Facing          : Blender -Y -> Three.js +Z")
        log("Bones           : %d" % len(document["skins"][0]["joints"]))
        log("Meshes          : %d" % len(document.get("meshes", [])))
        log("Materials       : %d" % len(document.get("materials", [])))
        log("Embedded images : %d" % len([i for i in document.get("images", []) if "bufferView" in i]))
        log("Vertices        : %d" % vertex_count)
        log("Animation clips :")
        for clip_name, (frames, looping, _step) in CLIPS.items():
            log("  %-13s -> %s (%d frames @ %d fps, %s)" %
                (clip_name, found[clip_name], frames, FPS, "loop" if looping else "one-shot"))
        log("STATUS          : SUCCESS — all checks passed")
        log("================================================")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        log("FAILED — character.glb was not confirmed as valid")
        sys.exit(1)
