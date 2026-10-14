"""Overland canopy: black cab-high V1 shell shape + low steel roof platform rack + two hard cases."""
from mathutils import Vector

from lib.common import load_json
from lib.meshkit import Part, add_weighted_normals
from lib.meshkit import box as _box
from lib.shell_v1 import ShellFrame, build_shell

def box(p, lo, hi, key, bev=0.0, seg=1):
    return _box(p, lo, hi, key, bev, seg)


TRUCK_TYPES = ("pickup",)
DESCRIPTION = "Black overland canopy with roof rack platform and storage cases"


def _rack(cp, fr, collection, mats):
    z0 = fr.H + fr.crown + 0.012          # rack frame sits on the roof crown via feet
    xr = fr.side_x(fr.H) - cp["rack_inset_x"]
    y0, y1 = cp["rack_front_y"], cp["rack_rear_y"]
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


def _case(name, cx, cy, zbase, lx, ly, lz, collection, mats):
    p = Part(name, mats)
    box(p, (cx - lx / 2, cy - ly / 2, zbase), (cx + lx / 2, cy + ly / 2, zbase + lz), "case", 0.025, 2)
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


def build(cfg, collection, mats):
    cp = cfg["camper"]
    shell_cfg = load_json(cp.get("config", "config/v1.json"))
    black = mats.car_paint("oc_black_paint", cp["paint_color"], metallic=0.0, roughness=0.55,
                           clearcoat=0.0, clearcoat_roughness=0.3, flake=0.0)
    mats.add("steel_blk", mats.principled("oc_steel_blk", base_color=(0.012, 0.012, 0.013, 1.0),
                                          roughness=0.5, metallic=0.6))
    mats.add("case", mats.principled("oc_case", base_color=(0.018, 0.019, 0.02, 1.0), roughness=0.42))
    mats.add("case_dark", mats.principled("oc_case_dark", base_color=(0.006, 0.006, 0.007, 1.0), roughness=0.6))
    role = {"shell_paint": black, "glass": mats["glass_flush"], "trim": mats["trim"], "lamp": mats["lamp_red_lens"]}
    objs = build_shell(shell_cfg, role, collection)
    for ob in objs:
        ob.name = "overland_canopy_" + ob.name
        if "shell_body" in ob.name:
            add_weighted_normals(ob)
    fr = ShellFrame(shell_cfg)
    rack, zdeck, xr = _rack(cp, fr, collection, mats)
    objs.append(rack)
    y0, y1 = cp["rack_front_y"], cp["rack_rear_y"]
    objs.append(_case("overland_case_big", 0.0, y0 - 0.55, zdeck, 0.95, 0.50, 0.32, collection, mats))
    objs.append(_case("overland_case_small", 0.05, y1 + 0.38, zdeck, 0.72, 0.42, 0.24, collection, mats))
    return objs
