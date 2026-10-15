"""Overland bed rack (generic, unbranded, original geometry): low-profile powder-coated black frame on the
bed rails with corner uprights, MOLLE-slotted side panels, top side rails and crossbars just below the cab
roof, plus overlanding gear: hard-shell rooftop tent on the crossbars, two recovery boards, jerry cans, a
shovel, a packed side awning, a light bar on the front crossbar and a cargo case in the bed.

Everything is fitted from truck_info (rail top = z 0, bed front wall = y 0). camper.loadout: "full"
(default) or "bare" (rack only) - the fixed combinations planned for the game (see docs/roadmap.md).
"""
import math

import bmesh
from mathutils import Vector

from lib.meshkit import Part, cylinder_x, cylinder_y, cylinder_z, oriented_box, prism_y, prism_z, rounded_rect
from lib.meshkit import box as _box
from variants.overland_canopy import _case

TRUCK_TYPES = ("pickup",)
DESCRIPTION = "Overland bed rack with rooftop tent, recovery boards, jerry cans, awning and light bar"
P = "bed_rack"


def box(p, lo, hi, key, bev=0.0, seg=1):
    return _box(p, lo, hi, key, bev, seg)


def _materials(mats):
    if "br_powder" in mats:
        return
    mats.add("br_powder", mats.principled(P + "_powder", base_color=(0.011, 0.011, 0.012, 1.0), roughness=0.62,
                                          metallic=0.25, specular=0.35))
    mats.add("br_hw", mats.principled(P + "_hardware", base_color=(0.30, 0.30, 0.31, 1.0), metallic=1.0,
                                      roughness=0.35))
    mats.add("br_tent_shell", mats.principled(P + "_tent_shell", base_color=(0.022, 0.023, 0.025, 1.0),
                                              roughness=0.38, clearcoat=0.3, clearcoat_roughness=0.25))
    mats.add("br_tent_base", mats.principled(P + "_tent_base", base_color=(0.05, 0.052, 0.055, 1.0), roughness=0.55))
    mats.add("br_canvas", mats.canvas_material(P + "_canvas", (0.10, 0.095, 0.075), wrinkle=0.6))
    mats.add("br_board", mats.principled(P + "_board", base_color=(0.30, 0.22, 0.12, 1.0), roughness=0.6))
    mats.add("br_can", mats.principled(P + "_can", base_color=(0.045, 0.055, 0.032, 1.0), roughness=0.5,
                                       clearcoat=0.2, clearcoat_roughness=0.3))
    mats.add("br_awning", mats.principled(P + "_awning", base_color=(0.016, 0.017, 0.018, 1.0), roughness=0.62,
                                          specular=0.3))
    if "case" not in mats:
        mats.add("case", mats.principled(P + "_case", base_color=(0.018, 0.019, 0.02, 1.0), roughness=0.42))
        mats.add("case_dark", mats.principled(P + "_case_dark", base_color=(0.006, 0.006, 0.007, 1.0),
                                              roughness=0.6))


class Frame:
    """Rack layout in the pickup variant frame (metres)."""

    def __init__(self, cp, ti):
        self.t = cp.get("tube", 0.05)                     # square tube size
        ihw, ohw = ti["bed_inner_hw"], ti["rail_outer_hw"]
        self.xr = (ihw + ohw) / 2                          # tube centreline over the middle of the rail cap
        self.yf = -cp.get("front_gap", 0.03) - self.t / 2  # front upright centre (cab back is at +y)
        rear = ti.get("bed_inner_rear_y", ti["tailgate_y"] + 0.05)
        self.yr = rear + self.t / 2 + cp.get("rear_inset", 0.0)
        self.z_top = ti["roof_z"] - cp.get("top_below_roof", 0.02)  # top of the side rails / crossbars
        self.z_foot = cp.get("foot_clearance", 0.003)
        self.z_base0 = self.z_foot + 0.010                 # base rail bottom (on clamp feet)
        self.z_base1 = self.z_base0 + 0.04
        self.z_rail0 = self.z_top - 0.045                  # top side rail bottom
        self.ihw = ihw


# ------------------------------------------------------------------ rack

def _molle_panel(p, fr, sx, y0, y1, z0, z1):
    """Side panel in the upright plane with rows of through slots (built from strips, real holes)."""
    th = 0.005
    x0, x1 = sorted((sx * (fr.xr - th / 2), sx * (fr.xr + th / 2)))
    slot_l, slot_h, gap_y, pitch_z, margin = 0.070, 0.024, 0.030, 0.062, 0.035
    n_rows = int((z1 - z0 - 2 * margin + pitch_z - slot_h) // pitch_z)
    n_cols = int((y0 - y1 - 2 * margin + gap_y) // (slot_l + gap_y))
    span_y = n_cols * slot_l + (n_cols - 1) * gap_y
    span_z = n_rows * slot_h + (n_rows - 1) * (pitch_z - slot_h)
    ys0 = (y0 + y1) / 2 + span_y / 2                     # first slot front edge
    zs0 = (z0 + z1) / 2 - span_z / 2                     # first slot bottom
    # horizontal strips: bottom margin, between rows, top margin
    zb = z0
    for r in range(n_rows):
        zr = zs0 + r * pitch_z
        box(p, (x0, y1, zb), (x1, y0, zr), "br_powder")
        zb = zr + slot_h
    box(p, (x0, y1, zb), (x1, y0, z1), "br_powder")
    # webs between slots in each row (and the end margins)
    for r in range(n_rows):
        zr = zs0 + r * pitch_z
        yb = y0
        for c in range(n_cols):
            ys = ys0 - c * (slot_l + gap_y)
            box(p, (x0, ys, zr), (x1, yb, zr + slot_h), "br_powder")
            yb = ys - slot_l
        box(p, (x0, y1, zr), (x1, yb, zr + slot_h), "br_powder")


def _rack(cp, fr, collection, mats):
    p = Part(P + "_frame", mats)
    t, xr = fr.t, fr.xr
    for sx in (-1, 1):
        x = sx * xr
        # clamp feet on the rail cap (the clamps hook under the rail lip, hidden inside the bed)
        for y in (fr.yf, (fr.yf + fr.yr) / 2, fr.yr):
            box(p, (x - 0.04, y - 0.06, fr.z_foot), (x + 0.04, y + 0.06, fr.z_base0), "br_powder", 0.003)
            cylinder_z(p, x, y, 0.009, fr.z_base1, fr.z_base1 + 0.004, "br_hw", seg=12)
        # base rail along the bed rail
        box(p, (x - t / 2, fr.yr - t / 2, fr.z_base0), (x + t / 2, fr.yf + t / 2, fr.z_base1), "br_powder", 0.004)
        # corner uprights + a mid post
        for y in (fr.yf, fr.yr):
            box(p, (x - t / 2, y - t / 2, fr.z_base1), (x + t / 2, y + t / 2, fr.z_rail0), "br_powder", 0.004)
        ym = (fr.yf + fr.yr) / 2
        box(p, (x - 0.02, ym - 0.02, fr.z_base1), (x + 0.02, ym + 0.02, fr.z_rail0), "br_powder", 0.003)
        # top side rail
        box(p, (x - t / 2, fr.yr - t / 2, fr.z_rail0), (x + t / 2, fr.yf + t / 2, fr.z_top), "br_powder", 0.005)
        # MOLLE panels (front and rear bays, either side of the mid post)
        for ya, yb in ((fr.yf - t / 2, ym + 0.02), (ym - 0.02, fr.yr + t / 2)):
            _molle_panel(p, fr, sx, ya, yb, fr.z_base1, fr.z_rail0)
        # corner gussets (triangular plates where the uprights meet the top rail), on the outer face
        for y, d in ((fr.yf - t / 2, -1), (fr.yr + t / 2, 1)):
            g = 0.10
            xo = sx * (xr + 0.0026)
            prof = [(y, fr.z_rail0), (y + d * g, fr.z_rail0), (y, fr.z_rail0 - g)]
            pts = [(xo, yy, zz) for yy, zz in prof]
            pts2 = [(xo + sx * 0.006, yy, zz) for yy, zz in prof]
            bm = p.bm
            a = [bm.verts.new(v) for v in pts]
            b = [bm.verts.new(v) for v in pts2]
            fs = [bm.faces.new(a), bm.faces.new(b[::-1])]
            for i in range(3):
                j = (i + 1) % 3
                fs.append(bm.faces.new([a[i], a[j], b[j], b[i]]))
            bmesh.ops.recalc_face_normals(bm, faces=fs)
            p.set_mat(fs, "br_powder")
    # crossbars (front, middle, rear) with a T-slot channel on top, joined by end plates
    ys = (fr.yf, (fr.yf + fr.yr) / 2, fr.yr)
    for y in ys:
        box(p, (-xr - t / 2, y - 0.025, fr.z_top - 0.04), (xr + t / 2, y + 0.025, fr.z_top), "br_powder", 0.005)
        box(p, (-xr + t / 2, y - 0.006, fr.z_top - 0.002), (xr - t / 2, y + 0.006, fr.z_top + 0.0005), "underbody")
        for sx in (-1, 1):
            box(p, (sx * xr - 0.035, y - 0.04, fr.z_top - 0.05), (sx * xr + 0.035, y + 0.04, fr.z_top + 0.004),
                "br_powder", 0.004)
            cylinder_z(p, sx * xr, y, 0.01, fr.z_top + 0.004, fr.z_top + 0.009, "br_hw", seg=12)
    return p.finish(collection, smooth=40, weighted=True)


# ------------------------------------------------------------------ gear

def _rounded_slab(p, x0, x1, y0, y1, z0, z1, r, key, seg=4):
    prism_z(p, rounded_rect(x0, x1, y0, y1, r, seg), z0, z1, key)


def _tent(cp, fr, collection, mats):
    """Low hard-shell rooftop tent (clamshell, closed): base tray, canvas band, domed lid, latches."""
    p = Part(P + "_tent", mats)
    hw, yf, yr = cp.get("tent_half_width", 0.68), cp.get("tent_front_y", -0.12), cp.get("tent_rear_y", -1.92)
    z0 = fr.z_top + 0.025
    # mounting brackets on each crossbar (L-feet under the tray)
    for y in (fr.yf, (fr.yf + fr.yr) / 2, fr.yr):
        if yr + 0.03 < y < yf - 0.03:
            for sx in (-1, 1):
                box(p, (sx * 0.52 - 0.04, y - 0.03, fr.z_top), (sx * 0.52 + 0.04, y + 0.03, z0), "br_hw", 0.003)
    h_tray, h_band, h_lid = 0.11, 0.035, 0.12
    _rounded_slab(p, -hw, hw, yr, yf, z0, z0 + h_tray, 0.07, "br_tent_base")
    _rounded_slab(p, -hw - 0.006, hw + 0.006, yr - 0.006, yf + 0.006, z0 + h_tray - 0.012, z0 + h_tray, 0.075,
                  "br_tent_shell")                                           # tray lip
    zb = z0 + h_tray
    _rounded_slab(p, -hw + 0.025, hw - 0.025, yr + 0.025, yf - 0.025, zb, zb + h_band, 0.06, "br_canvas")
    zl = zb + h_band
    # lid: two stacked rounded slabs give a soft dome, edge lip slightly proud
    _rounded_slab(p, -hw - 0.004, hw + 0.004, yr - 0.004, yf + 0.004, zl, zl + 0.035, 0.075, "br_tent_shell")
    _rounded_slab(p, -hw + 0.01, hw - 0.01, yr + 0.01, yf - 0.01, zl + 0.035, zl + h_lid - 0.025, 0.08,
                  "br_tent_shell")
    _rounded_slab(p, -hw + 0.06, hw - 0.06, yr + 0.06, yf - 0.06, zl + h_lid - 0.025, zl + h_lid, 0.10,
                  "br_tent_shell")
    # stiffening ribs on the lid (low, running front-to-back)
    for x in (-0.36, -0.12, 0.12, 0.36):
        box(p, (x - 0.025, yr + 0.18, zl + h_lid - 0.002), (x + 0.025, yf - 0.18, zl + h_lid + 0.01), "br_tent_shell",
            0.006, 2)
    # rear latches + front hinge blocks
    for x in (-0.45, 0.45):
        box(p, (x - 0.03, yr - 0.016, zb - 0.04), (x + 0.03, yr - 0.004, zl + 0.03), "br_powder", 0.004)
        box(p, (x - 0.05, yf + 0.002, zb - 0.01), (x + 0.05, yf + 0.014, zl + 0.02), "br_powder", 0.004)
    # side ladder stowed along the tray (telescoping, two stiles + rungs), driver side
    xl = -hw - 0.035
    for zz in (z0 + 0.025, z0 + 0.085):
        cylinder_y(p, xl, zz, 0.014, yr + 0.30, yr + 1.30, "alloy", seg=12)
    for i in range(7):
        y = yr + 0.36 + i * 0.145
        box(p, (xl - 0.012, y - 0.012, z0 + 0.025), (xl + 0.012, y + 0.012, z0 + 0.085), "alloy")
    for y in (yr + 0.45, yr + 1.15):
        box(p, (xl, y - 0.02, z0 + 0.04), (-hw, y + 0.02, z0 + 0.07), "br_powder")
    return p.finish(collection, smooth=40, weighted=True)


def _boards(fr, sx, y_center, collection, mats):
    """Two stacked recovery boards standing on edge against the side panel (generic, no branding),
    held by two locking pins and straps."""
    p = Part(P + "_boards", mats)
    L, W, T = 1.08, 0.30, 0.038
    xo = fr.xr + 0.003 + 0.02                          # panel outer face + standoff
    z0 = (fr.z_base1 + fr.z_rail0) / 2 - W / 2
    y0, y1 = y_center - L / 2, y_center + L / 2
    for k in range(2):
        xa = xo + k * (T + 0.004)
        x_lo, x_hi = sorted((sx * xa, sx * (xa + T)))
        box(p, (x_lo, y0, z0), (x_hi, y1, z0 + W), "br_board", 0.012, 2)
        # rounded hand holes near the ends (dark recess on the outer face)
    xt = xo + 2 * (T + 0.004)
    for i in range(10):                                # cleats on the outer board
        y = y0 + 0.08 + i * (L - 0.16) / 9
        for j in (-1, 0, 1):
            zc = z0 + W / 2 + j * 0.085
            x_lo, x_hi = sorted((sx * (xt - 0.002), sx * (xt + 0.013)))
            box(p, (x_lo, y - 0.02, zc - 0.02), (x_hi, y + 0.02, zc + 0.02), "br_board", 0.004)
    for y in (y0 + 0.17, y1 - 0.17):                   # handle slots
        x_lo, x_hi = sorted((sx * (xt - 0.003), sx * (xt + 0.001)))
        box(p, (x_lo, y - 0.07, z0 + W - 0.075), (x_hi, y + 0.07, z0 + W - 0.04), "underbody")
    for y in (y_center - 0.30, y_center + 0.30):       # mounting pins (through the panel slots)
        cylinder_x(p, y, z0 + W / 2, 0.022, *sorted((sx * (fr.xr - 0.01), sx * (xt + 0.03))), "br_powder", seg=16)
        cylinder_x(p, y, z0 + W / 2, 0.04, *sorted((sx * (xt + 0.03), sx * (xt + 0.045))), "br_powder", seg=20)
    for y in (y0 + 0.08, y1 - 0.08):                   # straps around the stack
        x_lo, x_hi = sorted((sx * (xo - 0.004), sx * (xt + 0.018)))
        box(p, (x_lo, y - 0.019, z0 - 0.004), (x_hi, y + 0.019, z0 + W + 0.004), "trim")
    return p.finish(collection, smooth=40, weighted=True)


def _jerry_can(p, sx, xi, yc, z0):
    """Classic 20 l jerry can standing upright on a side panel (generic military pattern, no markings).
    xi = inner face distance from the centreline; the can's thickness runs outward."""
    D, W, H = 0.165, 0.345, 0.465
    x_lo, x_hi = sorted((sx * xi, sx * (xi + D)))
    box(p, (x_lo, yc - W / 2, z0), (x_hi, yc + W / 2, z0 + H - 0.04), "br_can", 0.022, 2)
    # recessed X stiffeners on the outer face
    xf = sx * (xi + D)
    zc = z0 + (H - 0.04) / 2
    for ang in (math.atan2(H - 0.12, W - 0.08), -math.atan2(H - 0.12, W - 0.08)):
        ln = math.hypot(H - 0.12, W - 0.08) * 0.92
        ax = Vector((0, math.cos(ang), math.sin(ang)))
        oriented_box(p, Vector((xf + sx * 0.002, yc, zc)), (Vector((1, 0, 0)), ax, Vector((0, -math.sin(ang), math.cos(ang)))),
                     (0.008, ln, 0.03), "br_can", bev=0.003, seg=1)
    # three handles on top + spout
    zt = z0 + H - 0.04
    xm0, xm1 = sorted((sx * (xi + 0.06), sx * (xi + D - 0.06)))
    for k in (-1, 0, 1):
        y = yc - 0.03 + k * 0.075
        box(p, (xm0, y - 0.012, zt), (xm1, y + 0.012, zt + 0.04), "br_can", 0.006, 1)
    box(p, (xm0, yc - 0.15, zt + 0.028), (xm1, yc + 0.09, zt + 0.04), "br_can", 0.006, 1)
    cylinder_z(p, sx * (xi + D / 2), yc + 0.13, 0.022, zt, zt + 0.035, "br_can", seg=16)
    cylinder_z(p, sx * (xi + D / 2), yc + 0.13, 0.026, zt + 0.02, zt + 0.045, "br_hw", seg=16)


def _side_gear(fr, collection, mats, sx, name, can_ys, shovel_grip_y=None):
    """Jerry cans in panel-mounted holders and (optionally) a shovel, on one side's panel."""
    p = Part(name, mats)
    xi = fr.xr + fr.t / 2 + 0.005                     # clear of the tubes
    z0 = fr.z_base1 + 0.006
    for yc in can_ys:
        _jerry_can(p, sx, xi, yc, z0)
        x_lo, x_hi = sorted((sx * (fr.xr + fr.t / 2 + 0.001), sx * (xi + 0.18)))
        box(p, (x_lo, yc - 0.185, z0 - 0.012), (x_hi, yc + 0.185, z0), "br_powder", 0.003)       # tray
        x_lo, x_hi = sorted((sx * (fr.xr + 0.003), sx * (xi + 0.17)))
        box(p, (x_lo, yc - 0.18, z0 + 0.30), (x_hi, yc + 0.18, z0 + 0.335), "trim")              # strap
    if shovel_grip_y is not None:
        xs = sx * (fr.xr + 0.05)
        zs = fr.z_base1 + 0.12
        g = shovel_grip_y
        cylinder_y(p, xs, zs, 0.016, g - 0.74, g - 0.08, "wood", seg=12)                       # handle
        for dz in (-0.055, 0.045):                                                           # D-grip
            box(p, (xs - 0.007, g - 0.10, zs + dz), (xs + 0.007, g, zs + dz + 0.012), "br_powder", 0.003)
        box(p, (xs - 0.009, g - 0.014, zs - 0.055), (xs + 0.009, g, zs + 0.057), "br_powder", 0.004)
        box(p, (xs - 0.008, g - 1.0, zs - 0.10), (xs + 0.008, g - 0.74, zs + 0.10), "br_powder", 0.01, 2)  # blade
        for y in (g - 0.25, g - 0.60):                                                       # clamps
            x_lo, x_hi = sorted((sx * (fr.xr + fr.t / 2), sx * (fr.xr + 0.075)))
            box(p, (x_lo, y - 0.018, zs - 0.03), (x_hi, y + 0.018, zs + 0.03), "trim")
    return p.finish(collection, smooth=40, weighted=True)


def _awning(fr, collection, mats, sx, y0, y1):
    """Packed side awning: rounded PVC bag on three L-brackets off the top side rail."""
    p = Part(P + "_awning", mats)
    xc = sx * (fr.xr + 0.025 + 0.095)
    zc = fr.z_top + 0.085                             # above the top rail, clear of the panel gear
    prof = rounded_rect(xc - 0.07, xc + 0.07, zc - 0.085, zc + 0.085, 0.06, 5)
    prism_y(p, prof, y1, y0, "br_awning")
    for y in (y0 - 0.005, y1 + 0.005):                # end caps
        prof2 = rounded_rect(xc - 0.076, xc + 0.076, zc - 0.091, zc + 0.091, 0.064, 5)
        prism_y(p, prof2, y - 0.03, y + 0.03, "br_tent_base")
    for k in range(4):                                # hook-and-loop straps
        y = y1 + 0.20 + k * (y0 - y1 - 0.40) / 3
        prof3 = rounded_rect(xc - 0.073, xc + 0.073, zc - 0.088, zc + 0.088, 0.062, 5)
        prism_y(p, prof3, y - 0.02, y + 0.02, "trim")
    for k in range(3):                                # L-brackets bolted on the top rail
        y = y1 + 0.15 + k * (y0 - y1 - 0.30) / 2
        x_lo, x_hi = sorted((sx * (fr.xr - 0.02), sx * (fr.xr + 0.20)))
        box(p, (x_lo, y - 0.03, fr.z_top), (x_hi, y + 0.03, fr.z_top + 0.006), "br_powder", 0.002)
        x_lo, x_hi = sorted((sx * (fr.xr + 0.035), sx * (fr.xr + 0.041)))
        box(p, (x_lo, y - 0.03, fr.z_top), (x_hi, y + 0.03, zc + 0.02), "br_powder", 0.002)
    return p.finish(collection, smooth=40, weighted=True)


def _light_bar(fr, collection, mats):
    """Slim single-row LED bar on two brackets above the front crossbar, facing forward over the cab."""
    p = Part(P + "_light_bar", mats)
    hw = 0.40
    yc = fr.yf + 0.005
    zc = fr.z_top + 0.10                              # beam clears the cab roof
    box(p, (-hw, yc - 0.035, zc - 0.03), (hw, yc + 0.03, zc + 0.03), "trim_gloss", 0.01, 2)
    box(p, (-hw + 0.03, yc + 0.026, zc - 0.021), (hw - 0.03, yc + 0.034, zc + 0.021), "lamp_clear", 0.004)
    for i in range(12):
        x = -hw + 0.06 + i * (2 * hw - 0.12) / 11
        cylinder_y(p, x, zc, 0.014, yc + 0.018, yc + 0.027, "reflector", seg=14)
    for sx in (-1, 1):                                # end caps / brackets down to the crossbar
        box(p, (sx * hw - 0.012, yc - 0.03, zc - 0.035), (sx * hw + 0.012, yc + 0.025, zc + 0.035), "br_powder", 0.004)
        box(p, (sx * (hw - 0.05) - 0.02, yc - 0.03, fr.z_top), (sx * (hw - 0.05) + 0.02, yc + 0.01, zc - 0.028),
            "br_powder", 0.003)
    return p.finish(collection, smooth=40, weighted=True)


def build(cfg, collection, mats):
    cp, ti = cfg["camper"], cfg["truck_info"]
    _materials(mats)
    fr = Frame(cp, ti)
    objs = [_rack(cp, fr, collection, mats)]
    if cp.get("loadout", "full") == "bare":
        return objs
    objs.append(_tent(cp, fr, collection, mats))
    objs.append(_light_bar(fr, collection, mats))
    # driver side (-x, the side the standard views show): recovery boards on the front bay, a jerry can on
    # the rear bay, packed awning above the top rail
    objs.append(_boards(fr, -1, fr.yf - 0.03 - 0.54, collection, mats))
    objs.append(_side_gear(fr, collection, mats, -1, P + "_gear_left", [fr.yr + 0.215]))
    objs.append(_awning(fr, collection, mats, -1, fr.yf - 0.02, fr.yr + 0.02))
    # passenger side: second jerry can and the shovel
    objs.append(_side_gear(fr, collection, mats, 1, P + "_gear_right", [fr.yr + 0.215], fr.yf - 0.06))
    # cargo case in the bed (reuses the overland canopy's rotomoulded case)
    floor = ti.get("bed_floor_z", -0.52)
    # (the floor is ribbed: sit 3 cm up, on the rib tops)
    case = _case(P + "_bed_case", 0.0, cp.get("case_y", -0.95), floor + 0.03, 0.78, 0.46, 0.26, collection, mats)
    objs.append(case)
    return objs
