"""Overland canopy: black cab-high V1 shell shape (fitted to the shared bed dimensions like v1_shell) (smoked glass, seals, hatch hardware, interior) + low
steel roof platform rack with two rounded hard cases, stacked recovery boards and a shovel."""
from mathutils import Vector

from lib.common import load_json
from lib.meshkit import Part, add_weighted_normals
from lib.meshkit import box as _box
from lib.shell_v1 import build_shell, make_frame
from variants.v1_shell import fit_shell_cfg, shell_details, shell_interior, shell_materials

def box(p, lo, hi, key, bev=0.0, seg=1):
    return _box(p, lo, hi, key, bev, seg)


TRUCK_TYPES = ("pickup",)
DESCRIPTION = "Black overland canopy with roof rack platform and storage cases"


def _rack(cp, fr, collection, mats):
    z0 = fr.H + fr.crown + 0.012          # rack frame sits on the roof crown via feet
    xr = fr.side_x(fr.H) - cp["rack_inset_x"]          # narrowest (rear) roof width
    y0, y1 = _rack_span(cp, fr)
    h = cp["rack_height"]
    p = Part("overland_rack", mats)
    s = 0.038
    # feet / risers
    for x in (-xr + 0.02, xr - 0.02):
        for y in (y0 - 0.05, (y0 + y1) / 2, y1 + 0.05):
            box(p, (x - 0.03, y - 0.04, z0 - 0.03), (x + 0.03, y + 0.04, z0 + 0.03), "steel_blk", 0.008)
    zb = z0 + 0.03
    # base frame: side rails and end rails
    for x in (-xr, xr):
        box(p, (x - s / 2, y1, zb), (x + s / 2, y0, zb + s), "steel_blk", 0.007)
    for y in (y0, y1 + s):
        box(p, (-xr, y - s, zb), (xr, y, zb + s), "steel_blk", 0.007)
    # slat deck (crossbars) every ~0.17 m, low profile
    n = 9
    for i in range(n):
        y = y0 - s - 0.06 - i * ((y0 - y1 - 2 * s - 0.12) / (n - 1))
        box(p, (-xr, y - 0.03, zb + s - 0.012), (xr, y + 0.03, zb + s + 0.012), "steel_blk", 0.004)
    # two long runners under the cases
    for x in (-0.28, 0.28):
        box(p, (x - 0.02, y1 + s, zb + s - 0.02), (x + 0.02, y0 - s, zb + s), "steel_blk", 0.004)
    # perimeter fence: posts + top rail + mid rail
    top = zb + s + h
    posts = []
    for x in (-xr + s / 2, xr - s / 2):
        for i in range(6):
            y = y0 - s / 2 - i * ((y0 - y1 - s) / 5)
            posts.append((x, y))
    for x in (-xr + s / 2, xr - s / 2):
        pass
    for x, y in posts:
        box(p, (x - 0.012, y - 0.012, zb + s), (x + 0.012, y + 0.012, top), "steel_blk", 0.003)
    for x in (-xr + s / 2, xr - s / 2):
        box(p, (x - 0.014, y1 + s / 2, top - 0.028), (x + 0.014, y0 - s / 2, top), "steel_blk", 0.005)
    for y in (y0 - s / 2, y1 + s / 2):                       # end rails (front/rear), gap-free
        box(p, (-xr + s / 2, y - 0.014, top - 0.028), (xr - s / 2, y + 0.014, top), "steel_blk", 0.005)
        for x in (-xr + s / 2, 0.0, xr - s / 2):
            box(p, (x - 0.012, y - 0.012, zb + s), (x + 0.012, y + 0.012, top), "steel_blk", 0.003)
    # tie-down loops (D-rings) at the rail corners and mid-sides, bolted inside the base rails
    tie = []
    for sx in (-1, 1):
        for y in (y0 - 0.18, (y0 + y1) / 2, y1 + 0.18):
            tie.append((sx * (xr - 0.08), y))
    for x, y in tie:
        box(p, (x - 0.025, y - 0.03, zb + s - 0.004), (x + 0.025, y + 0.03, zb + s + 0.008), "steel_blk", 0.003)
        box(p, (x - 0.018, y - 0.02, zb + s + 0.008), (x + 0.018, y - 0.012, zb + s + 0.034), "steel_blk", 0.002)
        box(p, (x - 0.018, y + 0.012, zb + s + 0.008), (x + 0.018, y + 0.02, zb + s + 0.034), "steel_blk", 0.002)
        box(p, (x - 0.018, y - 0.02, zb + s + 0.026), (x + 0.018, y + 0.02, zb + s + 0.036), "steel_blk", 0.002)
    ob = p.finish(collection, smooth=40, weighted=True)
    return ob, zb + s + 0.012, xr


def _rack_span(cp, fr):
    """Rack front/rear y (shell frame): inset from the roof's front and rear edges."""
    return (fr.front_y(fr.H) - cp.get("rack_front_inset", 0.14),
            fr.rear_y(fr.H) + cp.get("rack_rear_inset", 0.15))


def _case(name, cx, cy, zbase, lx, ly, lz, collection, mats):
    p = Part(name, mats)
    # rounded rotomoulded shell: generous radius, slightly narrower lid half
    box(p, (cx - lx / 2, cy - ly / 2, zbase), (cx + lx / 2, cy + ly / 2, zbase + lz * 0.44), "case", 0.045, 4)
    box(p, (cx - lx / 2 + 0.01, cy - ly / 2 + 0.01, zbase + lz * 0.40), (cx + lx / 2 - 0.01, cy + ly / 2 - 0.01,
        zbase + lz), "case", min(0.06, lz * 0.3), 4)
    # lid parting groove (dark band) and top ribs
    gz = zbase + lz * 0.42
    box(p, (cx - lx / 2 - 0.004, cy - ly / 2 - 0.004, gz), (cx + lx / 2 + 0.004, cy + ly / 2 + 0.004, gz + 0.012), "case_dark", 0.003)
    for i in (-1, 1):
        box(p, (cx + i * lx * 0.28 - 0.025, cy - ly * 0.32, zbase + lz), (cx + i * lx * 0.28 + 0.025, cy + ly * 0.32, zbase + lz + 0.008), "case_dark", 0.003)
    # latches on both long sides
    for sy in (-1, 1):
        for fx in (-0.3, 0.3):
            yy = cy + sy * (ly / 2 + 0.006)
            box(p, (cx + fx * lx - 0.03, yy - 0.008, gz - 0.035), (cx + fx * lx + 0.03, yy + 0.008, gz + 0.045), "case_dark", 0.004)
    # end handles (recessed grips)
    for sx in (-1, 1):
        xx = cx + sx * (lx / 2 + 0.008)
        box(p, (xx - 0.01, cy - 0.06, zbase + lz * 0.62), (xx + 0.01, cy + 0.06, zbase + lz * 0.78), "case_dark", 0.004)
    return p.finish(collection, smooth=40, weighted=True)


def _traction_boards(cx, cy, zbase, collection, mats):
    """Two stacked recovery boards (sand-coloured, cleated) strapped along the rack, plus a shovel."""
    p = Part("overland_boards", mats)
    L, W, T = 1.10, 0.31, 0.04
    for k in range(2):
        z0 = zbase + k * (T + 0.004)
        x0 = cx + (k - 0.5) * 0.004
        box(p, (x0 - W / 2, cy - L / 2, z0), (x0 + W / 2, cy + L / 2, z0 + T), "oc_board", 0.012, 2)
    zt = zbase + 2 * (T + 0.004)
    for i in range(9):                 # cleat rows (top board)
        y = cy - L / 2 + 0.09 + i * (L - 0.18) / 8
        for j in (-1, 0, 1):
            box(p, (cx + j * 0.09 - 0.022, y - 0.022, zt - 0.002), (cx + j * 0.09 + 0.022, y + 0.022, zt + 0.014),
                "oc_board", 0.004, 1)
    for y in (cy - L * 0.3, cy + L * 0.3):   # straps
        box(p, (cx - W / 2 - 0.006, y - 0.02, zbase - 0.012), (cx + W / 2 + 0.006, y + 0.02, zt + 0.018), "trim")
    # shovel: handle along the rail, blade at the rear
    sx = cx + W / 2 + 0.10
    box(p, (sx - 0.016, cy - 0.40, zbase + 0.006), (sx + 0.016, cy + 0.46, zbase + 0.034), "wood", 0.006, 1)
    box(p, (sx - 0.09, cy - 0.66, zbase + 0.004), (sx + 0.09, cy - 0.40, zbase + 0.016), "steel_blk", 0.01, 2)
    return p.finish(collection, smooth=40, weighted=True)


def build(cfg, collection, mats):
    cp = cfg["camper"]
    shell_cfg = fit_shell_cfg(load_json(cp.get("config", "config/v1.json")), cfg["bed"], cp)
    black = mats.car_paint("oc_black_paint", cp["paint_color"], metallic=0.0, roughness=0.55,
                           clearcoat=0.0, clearcoat_roughness=0.3, flake=0.0)
    mats.add("steel_blk", mats.principled("oc_steel_blk", base_color=(0.012, 0.012, 0.013, 1.0),
                                          roughness=0.5, metallic=0.6))
    mats.add("case", mats.principled("oc_case", base_color=(0.018, 0.019, 0.02, 1.0), roughness=0.42))
    mats.add("case_dark", mats.principled("oc_case_dark", base_color=(0.006, 0.006, 0.007, 1.0), roughness=0.6))
    mats.add("oc_board", mats.principled("oc_board", base_color=(0.30, 0.22, 0.12, 1.0), roughness=0.6))
    role = {"shell_paint": black, "glass": mats["glass"], "trim": mats["seal"], "lamp": mats["lamp_red_lens"]}
    objs = build_shell(shell_cfg, role, collection)
    for ob in objs:
        ob.name = "overland_canopy_" + ob.name
        if "shell_body" in ob.name:
            add_weighted_normals(ob)
    fr = make_frame(shell_cfg)
    offset = Vector(shell_cfg["origin"]["offset"])
    shell_materials(mats)
    extra = [shell_details(shell_cfg, fr, mats, collection, prefix="overland_canopy_"),
             shell_interior(shell_cfg, fr, mats, collection, cfg["bed"], offset, prefix="overland_canopy_")]
    rack, zdeck, xr = _rack(cp, fr, collection, mats)
    extra.append(rack)
    y0, y1 = _rack_span(cp, fr)
    extra.append(_case("overland_case_big", -0.22, y0 - 0.42, zdeck, 0.78, 0.46, 0.26, collection, mats))
    extra.append(_case("overland_case_small", -0.22, y1 + 0.34, zdeck, 0.62, 0.40, 0.20, collection, mats))
    extra.append(_traction_boards(0.36, (y0 + y1) / 2, zdeck, collection, mats))
    for ob in extra:                       # everything above is built in the shell frame
        ob.location = offset
    return objs + extra
