"""Build the V1 bed shell scene deterministically from a config file.

Run with Blender (pinned 3.6.x):
  blender --background --factory-startup --python-exit-code 1 --python scripts/build_scene.py -- \
      --config config/v1.json --output build/v1.blend

Geometry is authored in Blender axes: +Z up, +Y toward the cab. The origin is the
top of the bed rails, centred, at the bed's front wall; the shell extends to -Y.

Shell = factory-style cab-high cap: crowned roof flush with the cab roof, near-vertical rear,
rounded edges (bmesh bevel), solid wall (bmesh solidify), real window openings cut with an
exact boolean (rounded-rectangle cutters), inset glass panes, rear hatch glass with a thin
painted frame, third brake light + hatch handle, black rubber seal along the rail.
Everything comes from config/v1.json; no randomness is used in the geometry.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy  # noqa: E402

from lib.common import (  # noqa: E402
    PipelineError, load_json, make_parser, repo_path, run_main, script_args,
    sha256_file, sha256_json, write_run_record,
)
from lib.shell_v1 import build_shell  # noqa: E402

COLLECTION = "camper_shell"
MAX_SHELL_TRIS = 6000


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    return scene


def make_material(name, spec):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = spec["base_color"]
    bsdf.inputs["Roughness"].default_value = spec["roughness"]
    for key, socket in (("metallic", "Metallic"), ("clearcoat", "Clearcoat"),
                        ("clearcoat_roughness", "Clearcoat Roughness")):
        if key in spec:
            bsdf.inputs[socket].default_value = spec[key]
    if "emission_strength" in spec:
        bsdf.inputs["Emission"].default_value = spec["base_color"]
        bsdf.inputs["Emission Strength"].default_value = spec["emission_strength"]
    if "alpha" in spec:
        bsdf.inputs["Alpha"].default_value = spec["alpha"]
        mat.blend_method = "BLEND"
    mat.diffuse_color = spec["base_color"]
    # Role is read by export_scs.py to choose the SCS material effect.
    mat["camper_role"] = spec["role"]
    return mat


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def main():
    p = make_parser("Build the V1 shell scene")
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args(script_args())

    cfg = load_json(args.config)
    random.seed(cfg["seed"])
    reset_scene()

    collection = bpy.data.collections.new(COLLECTION)
    bpy.context.scene.collection.children.link(collection)
    mats = {name: make_material(name, spec) for name, spec in sorted(cfg["materials"].items())}

    objs = build_shell(cfg, mats, collection)

    tris = sum(tri_count(o) for o in objs)
    if tris > MAX_SHELL_TRIS:
        raise PipelineError(f"shell is {tris} triangles; budget is {MAX_SHELL_TRIS}")

    out = repo_path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=False)
    stats = {o.name: {"verts": len(o.data.vertices), "faces": len(o.data.polygons), "tris": tri_count(o),
                      "dimensions": [round(d, 4) for d in o.dimensions]} for o in objs}
    rec = write_run_record("build_scene", {
        "blender": bpy.app.version_string,
        "config": str(args.config), "config_sha256": sha256_json(cfg),
        "output": str(args.output), "output_sha256": sha256_file(out),
        "objects": stats, "total_tris": tris,
    })
    print(f"saved {out}\nshell triangles: {tris}\nrecord {rec}")


run_main(main)
