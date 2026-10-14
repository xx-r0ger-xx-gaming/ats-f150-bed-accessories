"""Build the V1 bed shell scene deterministically from a config file.

Run with Blender (pinned 3.6.x):
  blender --background --factory-startup --python-exit-code 1 --python scripts/build_scene.py -- \
      --config config/v1.json --output build/v1.blend

Geometry is authored in Blender axes: +Z up, +Y toward the cab. The origin is the
top of the bed rails, centred, at the bed's front wall; the shell extends to -Y.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from lib.common import (  # noqa: E402
    PipelineError, load_json, make_parser, repo_path, run_main, script_args,
    sha256_file, sha256_json, write_run_record,
)

COLLECTION = "camper_shell"


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
    if "alpha" in spec:
        bsdf.inputs["Alpha"].default_value = spec["alpha"]
        mat.blend_method = "BLEND"
    # Role is read by export_scs.py to choose the SCS material effect.
    mat["camper_role"] = spec["role"]
    return mat


def add_box_uv(bm, name="UVMap"):
    """Deterministic box-projection UVs (metres, projected along each face's dominant normal axis).

    Placeholder mapping so SCS materials have a UV layer; real unwrap/texel density is a later phase.
    """
    uv_layer = bm.loops.layers.uv.get(name) or bm.loops.layers.uv.new(name)
    for face in bm.faces:
        n = face.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        u_i, v_i = [(1, 2), (0, 2), (0, 1)][ax]
        for loop in face.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co[u_i], co[v_i])


def new_object(name, bm, collection, materials):
    bm.normal_update()
    add_box_uv(bm)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for m in materials:
        mesh.materials.append(m)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def shell_corners(cfg):
    """Return the bottom and top outline of the shell's outer skin."""
    bed, sh = cfg["bed"], cfg["shell"]
    L, W = bed["length_at_rails"], bed["width_at_rails"]
    H = bed["cab_height_above_rails"] + sh["height_offset_from_cab"]
    t = sh["side_tumblehome"]
    bottom = {
        "fl": Vector((-W / 2, 0.0, 0.0)), "fr": Vector((W / 2, 0.0, 0.0)),
        "rl": Vector((-W / 2, -L, 0.0)), "rr": Vector((W / 2, -L, 0.0)),
    }
    top = {
        "fl": Vector((-W / 2 + t, -sh["front_rake"], H)), "fr": Vector((W / 2 - t, -sh["front_rake"], H)),
        "rl": Vector((-W / 2 + t, -L + sh["rear_rake"], H)), "rr": Vector((W / 2 - t, -L + sh["rear_rake"], H)),
    }
    return bottom, top, (L, W, H)


def build_body(cfg, mats, collection):
    sh = cfg["shell"]
    bottom, top, (L, W, H) = shell_corners(cfg)
    crown = sh["roof_crown"]
    bm = bmesh.new()
    v = {}
    for k, co in bottom.items():
        v["b" + k] = bm.verts.new(co)
    for k, co in top.items():
        v["t" + k] = bm.verts.new(co)
    v["tfc"] = bm.verts.new((0.0, top["fl"].y, H + crown))
    v["trc"] = bm.verts.new((0.0, top["rl"].y, H + crown))
    faces = {
        "front": [v["bfl"], v["bfr"], v["tfr"], v["tfc"], v["tfl"]],
        "rear": [v["brr"], v["brl"], v["trl"], v["trc"], v["trr"]],
        "left": [v["brl"], v["bfl"], v["tfl"], v["trl"]],
        "right": [v["bfr"], v["brr"], v["trr"], v["tfr"]],
        "roof_l": [v["tfl"], v["tfc"], v["trc"], v["trl"]],
        "roof_r": [v["tfc"], v["tfr"], v["trr"], v["trc"]],
    }
    for name, verts in faces.items():
        f = bm.faces.new(verts)
        f.material_index = 1 if name == "rear" else 0  # rear opening is trimmed hatch
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    inner_edges = [e for e in bm.edges if not e.is_boundary]
    bmesh.ops.bevel(bm, geom=inner_edges, offset=sh["edge_bevel"], segments=sh["bevel_segments"],
                    profile=0.5, affect="EDGES", clamp_overlap=True)
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=sh["wall_thickness"])
    obj = new_object("shell_body", bm, collection, [mats["shell_paint"], mats["trim"]])
    # Solidify direction depends on normals; the skin must not grow past the rails.
    half_w = max(abs(vt.co.x) for vt in obj.data.vertices)
    if half_w > W / 2 + 1e-4:
        raise PipelineError(f"shell_body wider than rails ({half_w * 2:.4f} > {W:.4f}); solidify went outward")
    return obj


def bilerp(q, u, v):
    """Bilinear point on quad q = (bottom_a, bottom_b, top_b, top_a)."""
    a = q[0].lerp(q[1], u)
    b = q[3].lerp(q[2], u)
    return a.lerp(b, v)


def build_side_glass(cfg, mats, collection, side):
    win = cfg["windows"]
    bottom, top, (L, W, H) = shell_corners(cfg)
    s = "l" if side == "left" else "r"
    q = (bottom["f" + s], bottom["r" + s], top["r" + s], top["f" + s])
    u0, u1 = win["side_inset_front"] / L, 1 - win["side_inset_rear"] / L
    v0, v1 = win["side_inset_bottom"] / H, 1 - win["side_inset_top"] / H
    pts = [bilerp(q, u0, v0), bilerp(q, u1, v0), bilerp(q, u1, v1), bilerp(q, u0, v1)]
    normal = (pts[1] - pts[0]).cross(pts[3] - pts[0]).normalized()
    if (normal.x > 0) != (side == "right"):
        normal = -normal
        pts.reverse()
    off = normal * win["glass_offset"]
    bm = bmesh.new()
    bm.faces.new([bm.verts.new(p + off) for p in pts])
    return new_object(f"shell_glass_{side}", bm, collection, [mats["glass"]])


def build_rear_glass(cfg, mats, collection):
    win = cfg["windows"]
    bottom, top, (L, W, H) = shell_corners(cfg)
    q = (bottom["rr"], bottom["rl"], top["rl"], top["rr"])
    f = win["rear_hatch_frame"]
    u0, u1, v0, v1 = f / W, 1 - f / W, f / H, 1 - f / H
    pts = [bilerp(q, u0, v0), bilerp(q, u1, v0), bilerp(q, u1, v1), bilerp(q, u0, v1)]
    normal = (pts[1] - pts[0]).cross(pts[3] - pts[0]).normalized()
    if normal.y > 0:
        normal = -normal
        pts.reverse()
    off = normal * win["glass_offset"]
    bm = bmesh.new()
    bm.faces.new([bm.verts.new(p + off) for p in pts])
    return new_object("shell_glass_rear", bm, collection, [mats["glass"]])


def build_rail_trim(cfg, mats, collection):
    """Closed rectangular band covering the clamp rail along the shell's base."""
    bed, sh = cfg["bed"], cfg["shell"]
    L, W = bed["length_at_rails"], bed["width_at_rails"]
    o, h = sh["rail_trim_outset"], sh["rail_trim_height"]
    bm = bmesh.new()
    x0, x1, y0, y1 = -W / 2 - o, W / 2 + o, o, -L - o
    bmesh.ops.create_cube(bm, size=1.0)
    for vert in bm.verts:
        vert.co.x = x1 if vert.co.x > 0 else x0
        vert.co.y = y0 if vert.co.y > 0 else y1
        vert.co.z = h if vert.co.z > 0 else 0.0
    return new_object("shell_rail_trim", bm, collection, [mats["trim"]])


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

    objs = [
        build_body(cfg, mats, collection),
        build_side_glass(cfg, mats, collection, "left"),
        build_side_glass(cfg, mats, collection, "right"),
        build_rear_glass(cfg, mats, collection),
        build_rail_trim(cfg, mats, collection),
    ]
    offset = Vector(cfg["origin"]["offset"])
    for obj in objs:
        obj.location = offset

    out = repo_path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=False)
    stats = {o.name: {"verts": len(o.data.vertices), "faces": len(o.data.polygons),
                      "dimensions": [round(d, 4) for d in o.dimensions]} for o in objs}
    rec = write_run_record("build_scene", {
        "blender": bpy.app.version_string,
        "config": str(args.config), "config_sha256": sha256_json(cfg),
        "output": str(args.output), "output_sha256": sha256_file(out),
        "objects": stats,
    })
    print(f"saved {out}\nrecord {rec}")


run_main(main)
