"""Render a preview of a built scene. Not proof of a working mod.

  blender --background build/v1.blend --python-exit-code 1 --python scripts/render_preview.py -- \
      --config config/v1.json --profile surface --output renders/v1-preview.png

Adds a grey stand-in bed/cab (generic boxes, not game assets) for context only;
the .blend on disk is not modified.
"""
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from lib.common import (  # noqa: E402
    PipelineError, load_json, make_parser, repo_path, run_main, script_args,
    sha256_file, write_run_record,
)


def add_box(name, center, size, color, collection):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    mat = bpy.data.materials.new(name + "_mat")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = color
    obj.data.materials.append(mat)
    for c in obj.users_collection:
        c.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def add_context(cfg):
    """Generic pickup-shaped boxes so the shell reads at the right scale."""
    col = bpy.data.collections.new("preview_context")
    bpy.context.scene.collection.children.link(col)
    L, W = cfg["bed"]["length_at_rails"], cfg["bed"]["width_at_rails"]
    H = cfg["bed"]["cab_height_above_rails"]
    grey = (0.35, 0.36, 0.38, 1.0)
    add_box("ctx_bed", (0, -L / 2, -0.25), (W + 0.04, L + 0.04, 0.5), grey, col)
    add_box("ctx_cab", (0, 1.0, -0.25 + (H + 0.5) / 2), (W + 0.04, 1.9, H + 0.5 + 0.2), grey, col)
    add_box("ctx_ground", (0, 0, -1.0), (30, 30, 0.02), (0.6, 0.6, 0.58, 1.0), col)


def setup_camera_and_light(cfg):
    L = cfg["bed"]["length_at_rails"]
    cam_data = bpy.data.cameras.new("preview_cam")
    cam_data.lens = 40
    cam = bpy.data.objects.new("preview_cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    target = Vector((0, -L / 2, 0.1))
    cam.location = Vector((-4.2, -L - 3.6, 2.2))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam

    sun_data = bpy.data.lights.new("preview_sun", "SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("preview_sun", sun_data)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
    bpy.context.scene.collection.objects.link(sun)

    world = bpy.data.worlds.new("preview_world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.65, 0.8, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
    bpy.context.scene.world = world
    return {"camera_location": list(cam.location), "lens": cam_data.lens}


def configure_render(profile):
    scene = bpy.context.scene
    r = scene.render
    r.resolution_x, r.resolution_y = profile["resolution"]
    r.resolution_percentage = 100
    r.image_settings.file_format = "PNG"
    r.engine = profile["engine"]
    if profile["engine"] == "BLENDER_EEVEE":
        scene.eevee.taa_render_samples = profile["samples"]
    elif profile["engine"] == "CYCLES":
        scene.cycles.samples = profile["samples"]
        scene.cycles.device = profile.get("device", "CPU")
        scene.cycles.seed = 0
    else:
        raise PipelineError(f"unsupported render engine {profile['engine']}")
    scene.view_settings.view_transform = "Filmic"


def main():
    p = make_parser("Render a preview image")
    p.add_argument("--config", required=True)
    p.add_argument("--profile", required=True, choices=["surface", "gaming", "surface-cpu"])
    p.add_argument("--output", required=True)
    args = p.parse_args(script_args())

    if not bpy.data.filepath:
        raise PipelineError("open a built .blend before rendering")
    cfg = load_json(args.config)
    if args.profile == "surface-cpu":
        profile = dict(cfg["render"]["surface"], engine="CYCLES", device="CPU")
    else:
        profile = cfg["render"][args.profile]

    add_context(cfg)
    cam = setup_camera_and_light(cfg)
    configure_render(profile)

    out = repo_path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(out)
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    elapsed = round(time.time() - t0, 2)
    if not out.is_file():
        raise PipelineError(f"render produced no file at {out}")
    rec = write_run_record("render_preview", {
        "blender": bpy.app.version_string, "source": bpy.data.filepath,
        "profile": args.profile, "settings": profile, "camera": cam,
        "seconds": elapsed, "output": str(args.output), "output_sha256": sha256_file(out),
    })
    print(f"rendered {out} in {elapsed}s\nrecord {rec}")


run_main(main)
