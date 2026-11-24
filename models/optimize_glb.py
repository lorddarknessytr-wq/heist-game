#!/usr/bin/env python3
"""
Blender Headless GLB Optimizer for Mobile WebGL / Three.js
=========================================================
Converts raw 3D models (.fbx, .obj, .dae, .blend, .gltf, .glb) into
lightweight, engine-ready .glb files:
  - Strips embedded lights and cameras (prevents lighting conflicts)
  - Normalizes scale, grounds bottom-center to Y=0, applies transforms
  - Optional triangle budget decimation per mesh
  - Downscales packed textures to <= max_tex_size (default 512px) as JPEG/WebP
  - Exports .glb with optional Draco compression

Usage (via Blender CLI):
  blender --background --python scripts/optimize_glb.py -- \
    --input assets/raw/crate.fbx \
    --output public/models/crate.glb \
    --max-tris 15000 \
    --max-tex 512 \
    --draco
"""

import argparse
import os
import sys
import math


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(description="Optimize 3D asset to mobile-ready GLB")
    parser.add_argument("--input", required=True, help="Path to source 3D file")
    parser.add_argument("--output", required=True, help="Destination .glb path")
    parser.add_argument("--max-tris", type=int, default=20000, help="Target max triangles per mesh")
    parser.add_argument("--max-tex", type=int, default=512, help="Max texture dimension (px)")
    parser.add_argument("--target-height", type=float, default=0.0, help="Optional target height in meters (0 = keep)")
    parser.add_argument("--ground", action="store_true", help="Shift model so min Y sits at 0.0")
    parser.add_argument("--draco", action="store_true", help="Enable Draco mesh compression")
    return parser.parse_args(argv)


def clear_scene(bpy):
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_model(bpy, filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=filepath)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=filepath, automatic_bone_orientation=True)
    elif ext == ".obj":
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=filepath)
        else:
            bpy.ops.import_scene.obj(filepath=filepath)
    elif ext == ".dae":
        bpy.ops.wm.collada_import(filepath=filepath)
    elif ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=filepath)
    else:
        raise ValueError(f"Unsupported input format: {ext}")


def strip_non_render_objects(bpy):
    to_remove = [obj for obj in bpy.data.objects if obj.type in ("LIGHT", "CAMERA", "SPEAKER")]
    for obj in to_remove:
        bpy.data.objects.remove(obj, do_unlink=True)


def apply_scale_and_ground(bpy, Vector, target_height: float, ground: bool):
    mesh_objs = [o for o in bpy.data.objects if o.type == "MESH"]
    if not mesh_objs:
        return

    bpy.context.view_layer.update()
    min_y = float("inf")
    max_y = float("-inf")
    for obj in mesh_objs:
        for corner in obj.bound_box:
            world_pt = obj.matrix_world @ Vector(corner)
            min_y = min(min_y, world_pt.y)
            max_y = max(max_y, world_pt.y)

    # Note: in Blender Z-up before glTF Y-up conversion, Z is vertical.
    min_z = float("inf")
    max_z = float("-inf")
    for obj in mesh_objs:
        for corner in obj.bound_box:
            world_pt = obj.matrix_world @ Vector(corner)
            min_z = min(min_z, world_pt.z)
            max_z = max(max_z, world_pt.z)

    current_height = max(1e-5, max_z - min_z)
    scale_factor = (target_height / current_height) if target_height > 0 else 1.0

    roots = [o for o in bpy.data.objects if o.parent is None]
    if abs(scale_factor - 1.0) > 1e-4:
        for r in roots:
            r.scale *= scale_factor
        bpy.context.view_layer.update()
        min_z *= scale_factor

    if ground and math.isfinite(min_z):
        for r in roots:
            r.location.z -= min_z
        bpy.context.view_layer.update()


def decimate_heavy_meshes(bpy, max_tris: int):
    if max_tris <= 0:
        return
    for obj in bpy.data.objects:
        if obj.type != "MESH" or not obj.data:
            continue
        # Count triangulated polygons roughly
        tri_count = sum(max(1, len(p.vertices) - 2) for p in obj.data.polygons)
        if tri_count <= max_tris:
            continue
        ratio = max(0.05, float(max_tris) / float(tri_count))
        mod = obj.modifiers.new(name="MobileDecimate", type="DECIMATE")
        mod.ratio = ratio
        mod.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = obj
        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
            print(f"[decimate] {obj.name}: {tri_count} -> ~{int(tri_count * ratio)} tris")
        except Exception as exc:
            print(f"[warn] Could not decimate {obj.name}: {exc}")


def resize_textures(bpy, max_tex: int):
    if max_tex <= 0:
        return
    for img in bpy.data.images:
        if not img or img.source not in ("FILE", "GENERATED"):
            continue
        w, h = img.size[0], img.size[1]
        if w <= 0 or h <= 0:
            continue
        if max(w, h) > max_tex:
            scale = max_tex / float(max(w, h))
            nw = max(16, int(round(w * scale)))
            nh = max(16, int(round(h * scale)))
            # Snap to multiple of 4 for GPU compatibility
            nw = max(4, (nw // 4) * 4)
            nh = max(4, (nh // 4) * 4)
            try:
                img.scale(nw, nh)
                print(f"[texture] {img.name}: {w}x{h} -> {nw}x{nh}")
            except Exception as exc:
                print(f"[warn] Texture resize skipped for {img.name}: {exc}")


def export_glb(bpy, output_path: str, draco: bool):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    kwargs = dict(
        filepath=output_path,
        export_format="GLB",
        export_yup=True,
        export_apply=True,
        export_texcoords=True,
        export_normals=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
        export_animations=True,
        export_skins=True,
        export_image_format="AUTO",
        export_draco_mesh_compression_enable=bool(draco),
    )
    if draco:
        kwargs.update(
            export_draco_mesh_compression_level=6,
            export_draco_position_quantization=12,
            export_draco_normal_quantization=10,
            export_draco_texcoord_quantization=10,
        )
    bpy.ops.export_scene.gltf(**kwargs)
    size_kb = os.path.getsize(output_path) / 1024.0
    print(f"[export] Wrote {output_path} ({size_kb:.1f} KB)")


def main():
    args = parse_args()
    import bpy
    from mathutils import Vector

    clear_scene(bpy)
    import_model(bpy, args.input)
    strip_non_render_objects(bpy)
    apply_scale_and_ground(bpy, Vector, args.target_height, args.ground)
    decimate_heavy_meshes(bpy, args.max_tris)
    resize_textures(bpy, args.max_tex)
    export_glb(bpy, args.output, args.draco)


if __name__ == "__main__":
    main()
