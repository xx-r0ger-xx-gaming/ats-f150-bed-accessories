"""Render a preview of a built scene (build/v1.blend). Not proof of a working mod.

  blender --background build/v1.blend --python-exit-code 1 --python scripts/render_preview.py -- \
      --config config/v1.json --profile surface|surface-photo|gaming --output renders/v1-preview.png \
      [--view rear34|side|front34]

Renders the exact exported shell objects (collection 'camper_shell') on the render-only stand-in
pickup (scripts/lib/proxy_truck.py: original, generic, debadged geometry, colour-matched to the
shell paint), lit by the HDRI world + matching sun, on a road (config/render.json). Game materials
are swapped for render materials in memory only. Nothing is saved: the .blend on disk is not
modified and the stand-in is never exported or packaged.
For camper variants on their own trucks use scripts/render_variants.py.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy  # noqa: E402

from lib.common import (  # noqa: E402
    PipelineError, load_json, make_parser, repo_path, run_main, script_args, sha256_file, write_run_record,
)
from lib.environment import (  # noqa: E402
    add_ground, configure_render, load_render_config, place_camera, resolve_profile, setup_world,
    world_bbox,
)
from lib.materials import MaterialLibrary, upgrade_game_materials  # noqa: E402
from lib.proxy_truck import build_truck, spec_from_v1  # noqa: E402


def main():
    rcfg = load_render_config()
    views = [k for k in rcfg["views"] if not k.startswith("_")]
    profiles = [k for k in rcfg["profiles"] if not k.startswith("_")]
    p = make_parser("Render a preview image")
    p.add_argument("--config", required=True)
    p.add_argument("--profile", required=True, choices=profiles + ["surface-cpu"])
    p.add_argument("--output", required=True)
    p.add_argument("--view", default="rear34", choices=views)
    args = p.parse_args(script_args())

    if not bpy.data.filepath:
        raise PipelineError("open a built .blend before rendering")
    shell = bpy.data.collections.get("camper_shell")
    if shell is None:
        raise PipelineError("collection 'camper_shell' missing; run build_scene.py first")
    cfg = load_json(args.config)
    if args.profile == "surface-cpu":   # legacy alias: surface settings on Cycles CPU
        profile = dict(resolve_profile(rcfg, "surface"), engine="CYCLES", device="CPU")
    else:
        profile = resolve_profile(rcfg, args.profile)

    mats = MaterialLibrary(cfg["materials"]["shell_paint"])
    col = bpy.data.collections.new("preview_context")
    bpy.context.scene.collection.children.link(col)
    info = build_truck(spec_from_v1(cfg), mats, col)
    upgrade_game_materials(list(shell.objects), mats)
    world = setup_world(rcfg["hdri"])
    add_ground(info["ground_z"], rcfg["ground"], col)
    configure_render(profile)
    spec = dict(rcfg["views"][args.view])
    if not profile.get("dof"):
        spec["fstop"] = None
    world.set_sun_azimuth(spec.get("sun_azimuth_deg", rcfg["hdri"].get("sun_azimuth_deg", 200.0)))
    cam = place_camera(spec, world_bbox(info["objects"] + list(shell.objects)), info["ground_z"])

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
        "profile": args.profile, "settings": profile, "camera": cam, "sun": world.info(),
        "seconds": elapsed, "output": str(args.output), "output_sha256": sha256_file(out),
    })
    print(f"rendered {out} in {elapsed}s\nrecord {rec}")


run_main(main)
