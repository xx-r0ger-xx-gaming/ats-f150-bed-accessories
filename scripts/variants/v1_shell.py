"""V1 colour-matched cab-high bed shell (the exported mod geometry, rebuilt with render materials).

Uses the exact same builders as scripts/build_scene.py (lib/shell_v1.py), driven by the config
named in cfg["camper"]["config"] (default config/v1.json), so the render shows the real shell.
Render-only extras (never exported): smoked see-through glazing, proud rubber window seals, hatch
hinge strip + lock cylinders, a base trim line above the rail seal, and a simple interior (headliner,
sleeping platform with mattress, a duffel and a cooler) so the glass has something behind it.
"""
import copy

from mathutils import Vector

from lib.common import load_json
from lib.meshkit import Part, add_weighted_normals, annulus_prism, box, cylinder_x, oriented_box
from lib.shell_v1 import ShellFrame, build_shell, map_outline, window_outlines

TRUCK_TYPES = ("pickup",)
DESCRIPTION = "Colour-matched cab-high camper shell (V1 mod geometry)"


def offset2d(pts, d):
    """Offset a closed 2D outline by d (d > 0 = outward), orientation independent."""
    n = len(pts)
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    sgn = 1.0 if area > 0 else -1.0
    out = []
    for i in range(n):
        a, b = Vector(pts[i - 1]), Vector(pts[(i + 1) % n])
        t = (b - a).normalized()
        nrm = Vector((t.y, -t.x)) * sgn
        out.append((pts[i][0] + nrm.x * d, pts[i][1] + nrm.y * d))
    return out


def fit_shell_cfg(shell_cfg, ti):
    """Render-only refit: on the measured reference truck, size the shell to its bed (length to the
    tailgate face, rail-to-rail width, cab-high roof). config/v1.json itself is not changed."""
    if ti.get("source") != "reference":
        return shell_cfg
    cfg = copy.deepcopy(shell_cfg)
    cfg["bed"]["length_at_rails"] = round(-ti["tailgate_y"], 4)
    cfg["bed"]["width_at_rails"] = round(2 * ti["rail_outer_hw"], 4)
    cfg["bed"]["cab_height_above_rails"] = round(ti["roof_z"] - cfg["shell"]["height_offset_from_cab"], 4)
    return cfg


def shell_materials(mats):
    if "v1_headliner" in mats:
        return
    mats.add("v1_headliner", mats.principled("v1_headliner", base_color=(0.16, 0.16, 0.155, 1), roughness=0.95,
                                             sheen=0.6))
    mats.add("v1_mattress", mats.canvas_material("v1_mattress", (0.10, 0.115, 0.13), wrinkle=0.6))
    mats.add("v1_duffel", mats.canvas_material("v1_duffel", (0.20, 0.09, 0.03), wrinkle=1.2))
    mats.add("v1_drawers", mats.principled("v1_drawers", base_color=(0.03, 0.03, 0.032, 1), roughness=0.7))
    mats.add("v1_cooler", mats.principled("v1_cooler", base_color=(0.05, 0.11, 0.16, 1), roughness=0.4,
                                          clearcoat=0.3))


def shell_details(cfg, fr, mats, collection, prefix=""):
    win = cfg["windows"]
    p = Part(prefix + "shell_render_details", mats)
    # proud rubber seal around every opening (bonded-glass look), 14 mm wide, 4 mm proud
    for kind, sign, pts in window_outlines(fr, cfg):
        outer = offset2d(pts, 0.014)
        inner = offset2d(pts, -0.002)
        faces = annulus_prism(p.bm, map_outline(fr, kind, sign, outer, -0.003),
                              map_outline(fr, kind, sign, outer, 0.004),
                              map_outline(fr, kind, sign, inner, -0.003),
                              map_outline(fr, kind, sign, inner, 0.004))
        p.set_mat(faces, "seal")
    # rear hatch: hinge strip above the glass, two lock cylinders beside the handle
    n = fr.rear_normal()
    ax = Vector((1, 0, 0))
    up = n.cross(ax).normalized()
    if up.z < 0:
        up = -up
    gz1 = fr.H - win["rear_margin_top"]
    gz0 = win["rear_margin_bottom"]
    hw_top = fr.side_x(gz1) - win["rear_margin_side"]
    oriented_box(p, fr.rear_point(0.0, gz1 + 0.032, 0.004), (ax, up, n), (2 * hw_top - 0.10, 0.022, 0.01),
                 "trim_gloss", bev=0.003)
    for sx in (-1, 1):
        oriented_box(p, fr.rear_point(sx * (hw_top - 0.08), gz1 + 0.032, 0.008), (ax, up, n),
                     (0.07, 0.03, 0.012), "steel", bev=0.003)
    hw_bot = fr.side_x(gz0) - win["rear_margin_side"]
    for sx in (-1, 1):
        c = fr.rear_point(sx * (hw_bot - 0.12), gz0 + 0.045, 0.0)
        oriented_box(p, c + n * 0.006, (ax, up, n), (0.05, 0.05, 0.012), "trim_gloss", bev=0.006)
        oriented_box(p, c + n * 0.014, (ax, up, n), (0.026, 0.026, 0.008), "chrome", bev=0.004)
    # base trim line just above the rail seal (sides + rear), satin black, 4 mm proud
    z0, z1 = 0.026, 0.040
    for sx in (-1, 1):
        x0 = sx * fr.side_x(z0)
        box(p, (min(x0, x0 + sx * 0.004), -fr.L + 0.09, z0), (max(x0, x0 + sx * 0.004), -0.09, z1), "trim_gloss")
    box(p, (-fr.hw + 0.09, fr.rear_y(z0) - 0.004, z0), (fr.hw - 0.09, fr.rear_y(z0) + 0.001, z1), "trim_gloss")
    return p.finish(collection, smooth=40)


def shell_interior(cfg, fr, mats, collection, ti, prefix=""):
    p = Part(prefix + "shell_interior", mats)
    L, H = fr.L, fr.H
    wall = cfg["shell"]["wall_thickness"]
    hx = fr.side_x(H) - wall - 0.06
    box(p, (-hx, -L + 0.12, H - 0.03), (hx, -0.10, H - 0.012), "v1_headliner", bev=0.01)
    bx = ti["bed_inner_hw"] - 0.02
    # sleeping platform at rail height minus a little, mattress on top
    box(p, (-bx, -L + 0.06, -0.10), (bx, -0.04, -0.075), "wood", bev=0.004)
    # drawer base between the wheel housings, standing on the bed floor
    box(p, (-0.56, -L + 0.08, ti.get("bed_floor_z", -0.52) + 0.004), (0.56, -0.06, -0.10), "v1_drawers", bev=0.006)
    box(p, (-bx + 0.03, -L + 0.10, -0.075), (bx - 0.03, -0.08, 0.03), "v1_mattress", bev=0.03, seg=3)
    # duffel (rolled) and a cooler near the tailgate
    cylinder_x(p, -L + 0.45, 0.11, 0.08, -0.55, -0.05, "v1_duffel", seg=14, bev=0.03)
    box(p, (0.12, -L + 0.20, 0.03), (0.62, -L + 0.52, 0.30), "v1_cooler", bev=0.02)
    box(p, (0.10, -L + 0.18, 0.28), (0.64, -L + 0.54, 0.32), "plastic_white", bev=0.012)
    return p.finish(collection, smooth=40)


def build(cfg, collection, mats):
    shell_materials(mats)
    shell_cfg = fit_shell_cfg(load_json(cfg["camper"].get("config", "config/v1.json")), cfg["truck_info"])
    role_mats = {"shell_paint": mats["paint"], "glass": mats["glass_tint"], "trim": mats["seal"],
                 "lamp": mats["lamp_red_lens"]}
    objs = build_shell(shell_cfg, role_mats, collection)
    for ob in objs:
        if ob.name.startswith("shell_body"):
            add_weighted_normals(ob)
    fr = ShellFrame(shell_cfg)
    offset = Vector(shell_cfg["origin"]["offset"])
    extra = [shell_details(shell_cfg, fr, mats, collection),
             shell_interior(shell_cfg, fr, mats, collection, cfg["truck_info"])]
    for ob in extra:
        ob.location = offset
    return objs + extra
