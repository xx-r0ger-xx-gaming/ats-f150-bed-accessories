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
from lib.meshkit import Part, add_weighted_normals, annulus_prism, box, cylinder_x, loft, oriented_box
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


def fit_shell_cfg(shell_cfg, bed, camper=None):
    """Render fit: size and place the shell from the shared bed dimensions (lib/bed.py, config/bed.json).

    Front face cab_gap (default 4 cm) behind the cab back and leaning with it; base on the rails
    (above the raised bed front wall, the rail seal fills the gap down to the rail cap); sides flush
    with the outer edge of the rail caps, tapering with them; rear corners on the closed tailgate's
    outer face and the rear face bowed like the tailgate; roof cab-high. config/v1.json (the export
    geometry) is not changed."""
    cp = camper or {}
    cfg = copy.deepcopy(shell_cfg)
    fp = bed.footprint(cab_gap=cp.get("cab_gap", 0.04), seal_min=cp.get("seal_min", 0.012))
    base_z, y_front, y_rear, hw_r = fp["base_z"], fp["y_front"], fp["y_rear"], fp["hw_rear"]
    H = bed["cab_roof_z"] - base_z + cfg["shell"]["height_offset_from_cab"]
    b, sh, seal = cfg["bed"], cfg["shell"], cfg["rail_seal"]
    b["length_at_rails"] = round(y_front - y_rear, 4)
    b["width_at_rails"] = round(2 * fp["hw_front"], 4)
    b["width_at_rails_rear"] = round(2 * hw_r, 4)
    b["cab_height_above_rails"] = round(bed["cab_roof_z"] - base_z, 4)
    sh["rear_bow"] = round(fp["bow"], 4)
    sh["front_rake"] = round(-bed["cab_back_lean"] * H, 4)
    sh["roof_divisions"] = max(sh["roof_divisions"], 12)
    seal["drop"] = round(base_z - bed["rail_cap_z"] + 0.001, 4)
    seal["front_drop"] = round(base_z - bed["front_wall_top_z"] + 0.001, 4)
    seal["front_zone_hw"] = bed["rail_inner_hw"]
    seal["front_zone_depth"] = 0.06
    seal["outset"] = 0.0                                # flush with the bed side
    seal["height"] = 0.004                              # tucked just into the skin's bottom edge
    cfg["origin"]["offset"] = [0.0, round(y_front, 4), round(base_z, 4)]
    print(f"[shell fit] {bed.name}: front y {y_front:+.3f} (cab gap {cp.get('cab_gap', 0.04):.3f}), base z "
          f"{base_z:+.3f}, length {y_front - y_rear:.3f}, width {2 * fp['hw_front']:.3f} -> "
          f"{2 * hw_r:.3f}, rear bow {sh['rear_bow']:.3f}, front rake {sh['front_rake']:+.3f}, H {H:.3f}")
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
    # rear hatch: hinge strip above the glass (segments follow a bowed rear face), two lock
    # cylinders beside the handle
    gz1 = fr.H - win["rear_margin_top"]
    gz0 = win["rear_margin_bottom"]
    hw_top = fr.rear_hw(gz1) - win["rear_margin_side"]
    _rear_band(p, fr, -(hw_top - 0.05), hw_top - 0.05, gz1 + 0.032, 0.022, 0.004, 0.01, "trim_gloss", bev=0.003)
    for sx in (-1, 1):
        x = sx * (hw_top - 0.08)
        oriented_box(p, fr.rear_point(x, gz1 + 0.032, 0.008), fr.rear_axes(x, gz1 + 0.032),
                     (0.07, 0.03, 0.012), "steel", bev=0.003)
    hw_bot = fr.rear_hw(gz0) - win["rear_margin_side"]
    for sx in (-1, 1):
        x = sx * (hw_bot - 0.12)
        ax = fr.rear_axes(x, gz0 + 0.045)
        c = fr.rear_point(x, gz0 + 0.045, 0.0)
        oriented_box(p, c + ax[2] * 0.006, ax, (0.05, 0.05, 0.012), "trim_gloss", bev=0.006)
        oriented_box(p, c + ax[2] * 0.014, ax, (0.026, 0.026, 0.008), "chrome", bev=0.004)
    # base trim line just above the rail seal (sides + rear), satin black, 4 mm proud, on the panels
    z0, z1 = 0.026, 0.040
    zm = 0.5 * (z0 + z1)
    for sx in (-1, 1):
        y0, y1 = -fr.L + 0.09, -0.09
        ax = fr.side_axes(sx)
        c = fr.side_point(sx, 0.5 * (y0 + y1), zm, 0.001)
        oriented_box(p, c, ax, ((y1 - y0) / ax[0].y, z1 - z0, 0.006), "trim_gloss")
    _rear_band(p, fr, -fr.rear_hw(zm) + 0.09, fr.rear_hw(zm) - 0.09, zm, z1 - z0, 0.0015, 0.005, "trim_gloss")
    return p.finish(collection, smooth=40)


def _rear_band(p, fr, x0, x1, z, height, off, depth, key, bev=0.0):
    """Strip across the rear face at height z (centre `off` out of the skin, `depth` thick): one
    continuous swept band that follows the bow of the rear face (a plain box when it is flat)."""
    if not fr.bow:
        ax = fr.rear_axes(0.0, z)
        oriented_box(p, fr.rear_point(0.5 * (x0 + x1), z, off), ax, (x1 - x0, height, depth), key, bev=bev)
        return
    rings = []
    n = 24
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        _, up, nrm = fr.rear_axes(x, z)
        c = fr.rear_point(x, z, off)
        h, d = up * (height / 2), nrm * (depth / 2)
        rings.append([c - h - d, c - h + d, c + h + d, c + h - d])
    loft(p, rings, key)


def shell_interior(cfg, fr, mats, collection, bed, offset, prefix=""):
    """Headliner, drawer base, sleeping platform, duffel and cooler. Built in the shell frame; the
    bed-bound parts are placed from the shared bed dimensions (variant frame minus `offset`)."""
    p = Part(prefix + "shell_interior", mats)
    L, H = fr.L, fr.H
    oy, oz = offset.y, offset.z
    wall = cfg["shell"]["wall_thickness"]
    hx = fr.side_x(H) - wall - 0.06
    box(p, (-hx, -L + 0.12, H - 0.03), (hx, -0.10, H - 0.012), "v1_headliner", bev=0.01)
    bx = bed["rail_inner_hw"] - 0.03
    yr = bed["bed_inner_rear_y"] + 0.02 - oy                # inside the closed tailgate
    yf = bed["front_wall_inner_y"] - 0.05 - oy              # clear of the corrugated bed front wall
    zp = bed["rail_cap_z"] - 0.10 - oz                      # platform a little below the rails
    box(p, (-bx, yr, zp), (bx, yf, zp + 0.025), "wood", bev=0.004)
    # drawer base between the wheel housings, standing on the bed floor
    dx = bed["wheelhouse_inner_hw"] - 0.012
    box(p, (-dx, yr + 0.01, bed["bed_floor_rib_z"] + 0.002 - oz), (dx, yf - 0.01, zp), "v1_drawers", bev=0.006)
    box(p, (-bx + 0.03, yr + 0.03, zp + 0.025), (bx - 0.03, yf - 0.03, zp + 0.13), "v1_mattress", bev=0.03, seg=3)
    # duffel (rolled) and a cooler near the tailgate
    zt = zp + 0.13
    cylinder_x(p, yr + 0.38, zt + 0.08, 0.08, -0.55, -0.05, "v1_duffel", seg=14, bev=0.03)
    box(p, (0.12, yr + 0.13, zt), (0.62, yr + 0.45, zt + 0.27), "v1_cooler", bev=0.02)
    box(p, (0.10, yr + 0.11, zt + 0.25), (0.64, yr + 0.47, zt + 0.29), "plastic_white", bev=0.012)
    return p.finish(collection, smooth=40)


def build(cfg, collection, mats):
    shell_materials(mats)
    shell_cfg = fit_shell_cfg(load_json(cfg["camper"].get("config", "config/v1.json")), cfg["bed"], cfg["camper"])
    role_mats = {"shell_paint": mats["paint"], "glass": mats["glass_tint"], "trim": mats["seal"],
                 "lamp": mats["lamp_red_lens"]}
    objs = build_shell(shell_cfg, role_mats, collection)
    for ob in objs:
        if ob.name.startswith("shell_body"):
            add_weighted_normals(ob)
    fr = ShellFrame(shell_cfg)
    offset = Vector(shell_cfg["origin"]["offset"])
    extra = [shell_details(shell_cfg, fr, mats, collection),
             shell_interior(shell_cfg, fr, mats, collection, cfg["bed"], offset)]
    for ob in extra:
        ob.location = offset
    return objs + extra
