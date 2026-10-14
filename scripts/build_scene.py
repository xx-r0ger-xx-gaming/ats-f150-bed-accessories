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
import math
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


def new_object(name, bm, collection, materials, smooth_angle=None):
    bm.normal_update()
    add_box_uv(bm)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for m in materials:
        mesh.materials.append(m)
    if smooth_angle is not None:
        for p in mesh.polygons:
            p.use_smooth = True
        mesh.use_auto_smooth = True
        mesh.auto_smooth_angle = math.radians(smooth_angle)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


# ---------------------------------------------------------------- shell surface model

class ShellFrame:
    """Analytic description of the outer skin's flat panels (before edge rounding)."""

    def __init__(self, cfg):
        bed, sh = cfg["bed"], cfg["shell"]
        self.L, self.W = bed["length_at_rails"], bed["width_at_rails"]
        self.H = bed["cab_height_above_rails"] + sh["height_offset_from_cab"]
        self.hw = self.W / 2
        self.t = sh["side_tumblehome"]
        self.fr, self.rr = sh["front_rake"], sh["rear_rake"]
        self.crown = sh["roof_crown"]

    def side_x(self, z):
        return self.hw - self.t * z / self.H

    def rear_y(self, z):
        return -self.L + self.rr * z / self.H

    def front_y(self, z):
        return -self.fr * z / self.H

    def side_point(self, sign, y, z, off=0.0):
        """Point on the left (sign=-1) / right (+1) side panel plus `off` along its outward normal."""
        n = self.side_normal(sign)
        return Vector((sign * self.side_x(z), y, z)) + n * off

    def side_normal(self, sign):
        return Vector((sign * self.H, 0.0, self.t)).normalized()

    def rear_point(self, x, z, off=0.0):
        return Vector((x, self.rear_y(z), z)) + self.rear_normal() * off

    def rear_normal(self):
        return Vector((0.0, -self.H, self.rr)).normalized()


def rounded_rect(u0, u1, v0, v1, r, seg):
    """CCW outline (u right, v up) of a rounded rectangle; seg segments per 90-degree corner."""
    r = min(r, (u1 - u0) / 2 - 1e-4, (v1 - v0) / 2 - 1e-4)
    corners = [((u1 - r, v0 + r), -90), ((u1 - r, v1 - r), 0), ((u0 + r, v1 - r), 90), ((u0 + r, v0 + r), 180)]
    pts = []
    for (cu, cv), a0 in corners:
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cu + r * math.cos(a), cv + r * math.sin(a)))
    return pts


def build_skin(fr, cfg):
    """Open-bottomed outer skin: crowned roof, raked front/rear, tumblehome sides, bevelled edges."""
    sh = cfg["shell"]
    n = sh["roof_divisions"]
    bm = bmesh.new()
    top_f, top_r = [], []
    for i in range(n + 1):
        u = -1 + 2 * i / n
        x = u * fr.side_x(fr.H)
        z = fr.H + fr.crown * (1 - u * u)
        top_f.append(bm.verts.new((x, fr.front_y(fr.H), z)))
        top_r.append(bm.verts.new((x, fr.rear_y(fr.H), z)))
    bfl = bm.verts.new((-fr.hw, 0.0, 0.0))
    bfr = bm.verts.new((fr.hw, 0.0, 0.0))
    brl = bm.verts.new((-fr.hw, -fr.L, 0.0))
    brr = bm.verts.new((fr.hw, -fr.L, 0.0))
    bm.faces.new([brl, bfl, top_f[0], top_r[0]])            # left
    bm.faces.new([bfr, brr, top_r[-1], top_f[-1]])          # right
    for i in range(n):                                     # roof strips
        bm.faces.new([top_f[i], top_f[i + 1], top_r[i + 1], top_r[i]])
    bm.faces.new([brr, brl] + top_r)                        # rear
    bm.faces.new([bfl, bfr] + top_f[::-1])                  # front
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    sharp = [e for e in bm.edges if len(e.link_faces) == 2
             and e.link_faces[0].normal.angle(e.link_faces[1].normal) > math.radians(20)]
    bmesh.ops.bevel(bm, geom=sharp, offset=sh["edge_bevel"], segments=sh["bevel_segments"],
                    profile=0.5, affect="EDGES", clamp_overlap=True)
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=sh["wall_thickness"])
    for f in bm.faces:
        f.material_index = 0
    return bm


def window_outlines(fr, cfg):
    """Return [(kind, sign, outline2d)] for every glass opening; side outlines in (y, z), rear in (x, z)."""
    win = cfg["windows"]
    seg = win["corner_segments"]
    out = []
    y_front = -win["side_margin_front"]
    y_rear = -fr.L + win["side_margin_rear"]
    z0, z1 = win["side_margin_bottom"], fr.H - win["side_margin_top"]
    split = y_front + (y_rear - y_front) * win["side_split"]
    half_p = win["pillar_width"] / 2
    for sign in (-1, 1):
        # u runs toward -Y (rear) so both panes share one outline routine.
        for (a, b) in ((y_front, split + half_p), (split - half_p, y_rear)):
            pts = rounded_rect(-a, -b, z0, z1, win["side_corner_radius"], seg)
            out.append(("side", sign, [(-u, v) for u, v in pts]))
    rz0, rz1 = win["rear_margin_bottom"], fr.H - win["rear_margin_top"]
    m = win["rear_margin_side"]
    hw0 = fr.side_x(rz0) - m
    pts = rounded_rect(-hw0, hw0, rz0, rz1, win["rear_corner_radius"], seg)
    # Follow the tumblehome: narrow each point's x with height so the frame stays even.
    pts = [(u * (fr.side_x(v) - m) / hw0, v) for u, v in pts]
    out.append(("rear", 0, pts))
    return out


def map_outline(fr, kind, sign, pts, off):
    if kind == "side":
        return [fr.side_point(sign, y, z, off) for y, z in pts]
    return [fr.rear_point(x, z, off) for x, z in pts]


def build_prism(bm, ring_a, ring_b, mat_index=0):
    """Closed prism between two equal-length rings (caps + sides) appended to bm."""
    va = [bm.verts.new(p) for p in ring_a]
    vb = [bm.verts.new(p) for p in ring_b]
    faces = [bm.faces.new(va), bm.faces.new(vb[::-1])]
    n = len(va)
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new([va[i], va[j], vb[j], vb[i]]))
    for f in faces:
        f.material_index = mat_index
    return faces


def cut_windows(fr, cfg, skin_bm, mats, collection):
    """Boolean-difference the window openings out of the skin; returns a bmesh of the result."""
    sh = cfg["shell"]
    deep = sh["wall_thickness"] * 3 + 0.02
    cut_bm = bmesh.new()
    for kind, sign, pts in window_outlines(fr, cfg):
        faces = build_prism(cut_bm, map_outline(fr, kind, sign, pts, deep),
                            map_outline(fr, kind, sign, pts, -deep), mat_index=1)
        bmesh.ops.recalc_face_normals(cut_bm, faces=faces)

    def tmp_obj(name, bm):
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mats["shell_paint"])
        me.materials.append(mats["trim"])
        ob = bpy.data.objects.new(name, me)
        collection.objects.link(ob)
        return ob

    body = tmp_obj("_skin_tmp", skin_bm)
    cutter = tmp_obj("_cutter_tmp", cut_bm)
    mod = body.modifiers.new("windows", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.material_mode = "INDEX"  # cutter walls (index 1 = trim) become the black window gaskets
    mod.object = cutter
    dg = bpy.context.evaluated_depsgraph_get()
    result = bmesh.new()
    result.from_mesh(body.evaluated_get(dg).to_mesh())
    body.evaluated_get(dg).to_mesh_clear()
    for ob in (body, cutter):
        me = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
    bmesh.ops.dissolve_degenerate(result, dist=1e-6, edges=result.edges[:])
    return result


def build_body(cfg, mats, collection):
    fr = ShellFrame(cfg)
    skin = build_skin(fr, cfg)
    half_w = max(abs(v.co.x) for v in skin.verts)
    if half_w > fr.hw + 1e-4:
        raise PipelineError(f"shell wider than rails ({half_w * 2:.4f} > {fr.W:.4f}); solidify went outward")
    bm = cut_windows(fr, cfg, skin, mats, collection)
    # Opening count sanity: each window adds one hole (boundary-free result expected).
    if any(e.is_boundary for e in bm.edges):
        raise PipelineError("shell_body is not closed after the window cut")
    return new_object("shell_body", bm, collection, [mats["shell_paint"], mats["trim"]], smooth_angle=40)


def build_glass(cfg, mats, collection):
    """Inset glass panes, one object per side + rear hatch, matching the cut openings."""
    fr = ShellFrame(cfg)
    inset = -cfg["windows"]["glass_inset"]
    groups = {"left": [], "right": [], "rear": []}
    for kind, sign, pts in window_outlines(fr, cfg):
        key = "rear" if kind == "rear" else ("left" if sign < 0 else "right")
        groups[key].append(map_outline(fr, kind, sign, pts, inset))
    objs = []
    for key in ("left", "right", "rear"):
        bm = bmesh.new()
        for ring in groups[key]:
            f = bm.faces.new([bm.verts.new(p) for p in ring])
            out = fr.rear_normal() if key == "rear" else fr.side_normal(-1 if key == "left" else 1)
            f.normal_update()
            if f.normal.dot(out) < 0:
                f.normal_flip()
        objs.append(new_object(f"shell_glass_{key}", bm, collection, [mats["glass"]]))
    return objs


def add_box(bm, center, axes, size, mat_index, bevel=0.0):
    """Oriented box: axes = (ax, ay, az) unit vectors, size = full extents along them."""
    res = bmesh.ops.create_cube(bm, size=1.0)
    verts = res["verts"]
    for v in verts:
        lx, ly, lz = v.co
        v.co = center + axes[0] * lx * size[0] + axes[1] * ly * size[1] + axes[2] * lz * size[2]
    faces = list({f for v in verts for f in v.link_faces})
    for f in faces:
        f.material_index = mat_index
    if bevel > 0:
        edges = list({e for v in verts for e in v.link_edges})
        bmesh.ops.bevel(bm, geom=edges, offset=bevel, segments=2, profile=0.5,
                        affect="EDGES", clamp_overlap=True)


def build_hatch_hardware(cfg, mats, collection):
    """Third brake light at the top of the hatch glass and the hatch handle at its bottom."""
    fr = ShellFrame(cfg)
    win, hw_cfg = cfg["windows"], cfg["hatch_hardware"]
    n = fr.rear_normal()
    ax = Vector((1, 0, 0))
    up = n.cross(ax).normalized()
    if up.z < 0:
        up = -up
    gz1 = fr.H - win["rear_margin_top"]
    gz0 = win["rear_margin_bottom"]
    bm = bmesh.new()
    bl = hw_cfg["brake_light"]
    c = fr.rear_point(0.0, gz1 - bl["from_glass_top"], bl["depth"] / 2 - win["glass_inset"])
    add_box(bm, c, (ax, up, n), (bl["width"], bl["height"], bl["depth"]), 1, bevel=0.005)
    hd = hw_cfg["handle"]
    c = fr.rear_point(0.0, gz0 + hd["from_glass_bottom"], hd["depth"] / 2 - win["glass_inset"])
    add_box(bm, c, (ax, up, n), (hd["width"], hd["height"], hd["depth"]), 0, bevel=0.006)
    return new_object("shell_hatch_hardware", bm, collection, [mats["trim"], mats["lamp"]])


def build_rail_seal(cfg, mats, collection):
    """Black rubber seal band following the shell's rounded base outline, on top of the rails."""
    fr = ShellFrame(cfg)
    sh, seal = cfg["shell"], cfg["rail_seal"]
    seg = sh["bevel_segments"] + 2
    r = sh["edge_bevel"]
    # Plan outline: u = x, v = y (front wall at v = 0, rear at v = -L).
    outline = rounded_rect(-fr.hw, fr.hw, -fr.L, 0.0, r, seg)
    nrm = []
    k = len(outline)
    for i in range(k):
        a, b = Vector(outline[i - 1]), Vector(outline[(i + 1) % k])
        d = (b - a).normalized()
        nrm.append(Vector((d.y, -d.x)))  # CCW outline -> outward normal
    bm = bmesh.new()
    rings = []
    zb, zt = -seal["drop"], seal["height"]
    for (x, y), nv in zip(outline, nrm):
        p = Vector((x, y))
        inner = p - nv * seal["inset"]
        outer = p + nv * seal["outset"]
        rings.append([bm.verts.new((inner.x, inner.y, zb)), bm.verts.new((outer.x, outer.y, zb)),
                      bm.verts.new((outer.x, outer.y, zt)), bm.verts.new((inner.x, inner.y, zt))])
    for i in range(k):
        a, b = rings[i], rings[(i + 1) % k]
        for j in range(4):
            jj = (j + 1) % 4
            bm.faces.new([a[j], b[j], b[jj], a[jj]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return new_object("shell_rail_seal", bm, collection, [mats["trim"]], smooth_angle=50)


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

    objs = [build_body(cfg, mats, collection)]
    objs += build_glass(cfg, mats, collection)
    objs += [build_hatch_hardware(cfg, mats, collection), build_rail_seal(cfg, mats, collection)]
    offset = Vector(cfg["origin"]["offset"])
    for obj in objs:
        obj.location = offset

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
