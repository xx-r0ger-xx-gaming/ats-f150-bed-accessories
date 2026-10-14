"""V1 cab-high bed shell geometry (shared by build_scene.py and the v1_shell render variant).

Pure geometry builders driven by config/v1.json. build_scene.py saves/exports their result; the
variant framework (scripts/variants/v1_shell.py) calls build_shell() with render materials.
Shell frame: origin = top of bed rails, centred, at the bed front wall; +Y toward the cab; +Z up.
"""
import math

import bmesh
import bpy
from mathutils import Vector

from lib.common import PipelineError
from lib.meshkit import add_box, build_prism, new_object, rounded_rect


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


def build_shell(cfg, mats, collection):
    """Build every shell object. mats: {'shell_paint','glass','trim','lamp'} -> bpy materials."""
    objs = [build_body(cfg, mats, collection)]
    objs += build_glass(cfg, mats, collection)
    objs += [build_hatch_hardware(cfg, mats, collection), build_rail_seal(cfg, mats, collection)]
    offset = Vector(cfg["origin"]["offset"])
    for obj in objs:
        obj.location = offset
    return objs
