"""Hard-sided slide-in truck camper for a half-ton 5.5 ft bed (render-only, original geometry).

Layout (variant frame, origin = bed rail top at the bed front wall, +Y forward):
  - basement: narrow box inside the bed (below the rails), mostly hidden by the bed sides;
  - main body: full-width "wing walls" from just above the rails to the roof, rear overhang past
    the bed end, cabover sleeping section over the cab roof with a chamfered/rounded nose;
  - framed RV windows (recessed dark glazing), rear entry door with window, rear ladder, roof AC +
    vents, side storage hatch, fridge vents, tail/marker/clearance lamps, stowed corner jacks,
    subtle dark-grey graphic swooshes.
With truck.tailgate "closed" the camper simply overhangs the closed tailgate.
"""
import math

import bmesh
from mathutils import Vector

from lib.meshkit import (
    Part, annulus_prism, bevel, bm_object, boolean_apply, box, build_prism, cylinder_x, cylinder_y,
    cylinder_z, finish_hard_surface, oriented_box, prism_x, rounded_rect,
)

TRUCK_TYPES = ("pickup",)
DESCRIPTION = "Hard-sided slide-in camper with cabover (half-ton, 5.5 ft bed)"

NAME = "slide_in"


# ------------------------------------------------------------------ 2D helpers

def fillet_poly(pts):
    """[(u, v, r)] polygon (convex or concave corners) -> outline with every corner filleted."""
    out = []
    n = len(pts)
    for i in range(n):
        p0 = Vector(pts[i - 1][:2])
        p1 = Vector(pts[i][:2])
        p2 = Vector(pts[(i + 1) % n][:2])
        r = pts[i][2]
        a, b = (p0 - p1), (p2 - p1)
        la, lb = a.length, b.length
        a.normalize()
        b.normalize()
        ang = a.angle(b)
        if r <= 0 or abs(ang - math.pi) < 1e-3:
            out.append((p1.x, p1.y))
            continue
        t = min(r / math.tan(ang / 2), la * 0.45, lb * 0.45)
        rr = t * math.tan(ang / 2)
        s, e = p1 + a * t, p1 + b * t
        c = p1 + (a + b).normalized() * (rr / math.sin(ang / 2))
        a0 = math.atan2(s.y - c.y, s.x - c.x)
        a1 = math.atan2(e.y - c.y, e.x - c.x)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        seg = max(2, min(8, int(rr / 0.03) + 2))
        for k in range(seg + 1):
            aa = a0 + da * k / seg
            out.append((c.x + rr * math.cos(aa), c.y + rr * math.sin(aa)))
    return out


def offset_rect(u0, u1, v0, v1, r, d, seg=4):
    return rounded_rect(u0 - d, u1 + d, v0 - d, v1 + d, max(r + d, 0.004), seg)


# ------------------------------------------------------------------ surface mappers  (u, v, d) -> xyz

class Geo:
    def __init__(self, cfg):
        c, ti = cfg["camper"], cfg["truck_info"]
        self.hw = c.get("half_width", 1.08)
        self.yr = ti["tailgate_y"] - c.get("rear_overhang", 0.50)
        self.z0 = 0.03
        self.ztop = c.get("roof_above_rails", 1.52)
        self.zc = ti["roof_z"] + c.get("cabover_floor_above_cab_roof", 0.11)
        self.yb = ti["cab_back_y"] + 0.03
        self.yn = c.get("cabover_nose_y", 1.40)
        # front face of the nose: from (yn - 0.04, zc + 0.15) to (yn, zc + 0.55)
        self.ff0 = (self.yn - 0.06, self.zc + 0.18)
        self.ff1 = (self.yn, self.zc + 0.54)
        t = Vector((0.0, self.ff1[0] - self.ff0[0], self.ff1[1] - self.ff0[1])).normalized()
        self.fn = Vector((0.0, t.z, -t.y))           # forward-ish normal of the front face
        # upper nose slope (for clearance lamps)
        self.sl0 = (self.yn, self.zc + 0.54)
        self.sl1 = (self.yn - 0.42, self.ztop)
        self.ti = ti

    def side(self, sgn):
        hw = self.hw
        return lambda u, v, d: Vector((sgn * (hw + d), u, v))

    def rear(self):
        yr = self.yr
        return lambda u, v, d: Vector((u, yr - d, v))

    def front(self):
        (y0, z0), (y1, z1), n = self.ff0, self.ff1, self.fn

        def m(u, v, d):
            y = y0 + (v - z0) * (y1 - y0) / (z1 - z0)
            return Vector((u, y, v)) + n * d
        return m


def ring(mapper, outline, d):
    return [mapper(u, v, d) for u, v in outline]


def plate(part, mapper, outline, d0, d1, key):
    """Thin prism on a body surface: outline [(u, v)] between depths d0..d1 (d > 0 = outward)."""
    bm = part.bm
    faces = build_prism(bm, ring(mapper, outline, d0), ring(mapper, outline, d1))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    # recalc can flip a thin concave plate inside out; the outer cap must face away from the body
    u, v = outline[0]
    out = mapper(u, v, 1.0) - mapper(u, v, 0.0)
    cap = faces[1] if d1 > d0 else faces[0]
    cap.normal_update()
    if cap.normal.dot(out) < 0:
        bmesh.ops.reverse_faces(bm, faces=faces)
    part.set_mat(faces, key)
    return faces


def frame(part, mapper, outline_in, outline_out, d0, d1, key):
    faces = annulus_prism(part.bm, ring(mapper, outline_out, d0), ring(mapper, outline_out, d1),
                          ring(mapper, outline_in, d0), ring(mapper, outline_in, d1))
    part.set_mat(faces, key)
    return faces


# ------------------------------------------------------------------ materials

def setup_materials(cfg, mats):
    c = cfg["camper"]
    gel = mats.principled("rv_slide_in_gelcoat", base_color=tuple(c.get("gelcoat", (0.80, 0.785, 0.74, 1.0))),
                          roughness=0.26, specular=0.5, clearcoat=0.45, clearcoat_roughness=0.12)
    mats.add("sl_gel", gel)
    mats.add("sl_stripe", mats.principled("rv_slide_in_stripe",
                                          base_color=tuple(c.get("stripe", (0.055, 0.058, 0.062, 1.0))),
                                          roughness=0.45, specular=0.3))
    mats.add("sl_frame", mats.principled("rv_slide_in_frame", base_color=(0.018, 0.018, 0.02, 1.0),
                                         roughness=0.42, metallic=0.25))
    mats.add("sl_acwhite", mats.principled("rv_slide_in_ac", base_color=(0.70, 0.70, 0.68, 1.0),
                                           roughness=0.38, clearcoat=0.2))


# ------------------------------------------------------------------ body

def window_list(g):
    """(mapper, outline, mullion_u or None) for every window."""
    wins = []
    for sgn in (-1, 1):
        s = g.side(sgn)
        wins.append((s, rounded_rect(0.42, 0.92, g.zc + 0.21, g.zc + 0.53, 0.05, 4), None))
        wins.append((s, rounded_rect(-1.18, -0.32, 0.78, 1.22, 0.06, 4), -0.75))
    fz0, fz1 = g.ff0[1] + 0.09, g.ff1[1] - 0.08
    wins.append((g.front(), rounded_rect(-0.56, 0.56, fz0, fz1, 0.05, 4), None))
    wins.append((g.rear(), rounded_rect(0.06, 0.46, 0.80, 1.16, 0.05, 4), None))
    wins.append((g.rear(), rounded_rect(-0.66, -0.28, 0.86, 1.24, 0.05, 4), None))   # door window
    return wins


DOOR = (-0.78, -0.16, 0.12, 1.38, 0.06)          # rear entry door (u = x, v = z)
HATCH = (-1.92, -1.47, 0.12, 0.38, 0.035)        # left side storage hatch (u = y, v = z)


def build_body(g, mats, col):
    yr, yb, yn, z0, zc, zt = g.yr, g.yb, g.yn, g.z0, g.zc, g.ztop
    prof = fillet_poly([
        (yr, z0, 0.05),
        (yb, z0, 0.03),
        (yb, zc, 0.06),                           # concave corner under the cabover
        (yn - 0.40, zc, 0.12),
        (g.ff0[0], g.ff0[1], 0.10),
        (g.ff1[0], g.ff1[1], 0.16),
        (yn - 0.42, zt, 0.34),
        (yr, zt, 0.09),
    ])
    p = Part(f"{NAME}_body", mats)
    vs = prism_x(p, prof, -g.hw, g.hw, "sl_gel")
    bm = p.bm
    cap_edges = list({e for v in vs for e in v.link_edges if abs(e.verts[0].co.x - e.verts[1].co.x) < 1e-6})
    bevel(bm, cap_edges, 0.065, 3)
    bm.normal_update()
    under = [f for f in bm.faces if f.normal.z < -0.55]
    p.set_mat(under, "underbody")
    body = p.finish(col, smooth=35)

    # cutters: window pockets (glass floor) + door / hatch panel-gap grooves
    cbm = bmesh.new()
    for mapper, ol, _ in window_list(g):
        faces = build_prism(cbm, ring(mapper, ol, 0.08), ring(mapper, ol, -0.03), mat_index=1)
        bmesh.ops.recalc_face_normals(cbm, faces=faces)
        faces[0].material_index = 1
        faces[1].material_index = 0
    gap = 0.006
    for mapper, (u0, u1, v0, v1, r) in ((g.rear(), DOOR), (g.side(-1), HATCH)):
        o = rounded_rect(u0, u1, v0, v1, r, 4)
        i = offset_rect(u0, u1, v0, v1, r, -gap)
        annulus_prism(cbm, ring(mapper, o, 0.05), ring(mapper, o, -0.018),
                      ring(mapper, i, 0.05), ring(mapper, i, -0.018), 1)
    cutter = bm_object(f"{NAME}_cut", cbm, [mats["glass_flush"], mats["sl_frame"]], col)
    boolean_apply(body, cutter)
    finish_hard_surface(body, 35)

    # basement inside the bed. Tailgate closed: a dark box hidden by the bed sides / tailgate.
    # Tailgate down/removed: it fills the bed to the bed end like a real unit (gelcoat, a rubber
    # bumper strip at the floor and a dark rear trim band), visible under the rear overhang.
    bp = Part(f"{NAME}_basement", mats)
    ti = g.ti
    bhw = min(ti["bed_inner_hw"] - 0.04, 0.80)
    if ti.get("tailgate", "closed") == "closed":
        box(bp, (-bhw, ti["tailgate_y"] + 0.07, -0.50), (bhw, yb - 0.02, z0 + 0.02), "underbody", bev=0.02)
    else:
        ye = ti["tailgate_y"] - 0.02
        box(bp, (-bhw, ye, -0.50), (bhw, yb - 0.02, z0 + 0.02), "sl_gel", bev=0.02)
        box(bp, (-bhw + 0.01, ye - 0.035, -0.505), (bhw - 0.01, ye + 0.02, -0.44), "rubber", bev=0.008)
        box(bp, (-bhw + 0.01, ye - 0.006, -0.20), (bhw - 0.01, ye + 0.01, -0.17), "sl_stripe")
        for sgn in (-1, 1):              # basement tail/marker lamps low on the rear face
            a_, b_ = sorted((sgn * (bhw - 0.06), sgn * (bhw - 0.16)))
            box(bp, (a_, ye - 0.012, -0.36), (b_, ye + 0.01, -0.30), "lamp_red_lens", bev=0.006)
    return [body, bp.finish(col, smooth=35)]


# ------------------------------------------------------------------ details

def stripes(g, p):
    for sgn in (-1, 1):
        s = g.side(sgn)
        y0, ytip, n = g.yr + 0.075, -0.30, 14

        def top_a(t):
            return 0.86 - 0.58 * t ** 1.15

        def th_a(t):
            return 0.15 * (1 - t) ** 0.85

        for top, th in ((top_a, th_a),
                        (lambda t: top_a(t) - th_a(t) - 0.032 * (1 - t), lambda t: 0.042 * (1 - t) ** 0.85)):
            ts = [i / n for i in range(n + 1)]
            upper = [(y0 + (ytip - y0) * t, top(t)) for t in ts]
            lower = [(y0 + (ytip - y0) * t, top(t) - th(t)) for t in ts[:-1]]
            plate(p, s, upper + lower[::-1], -0.003, 0.004, "sl_stripe")
        # thin cabover line, widening toward the nose
        n2 = 8
        ys = [0.20 + (1.02 - 0.20) * i / n2 for i in range(n2 + 1)]
        zb = g.zc + 0.09
        upper = [(y, zb + 0.016 + 0.03 * ((y - 0.20) / 0.82) ** 1.5) for y in ys]
        lower = [(y, zb) for y in ys]
        plate(p, s, lower + upper[::-1], -0.003, 0.004, "sl_stripe")
    # rear: a band picking up the swoosh height, either side of the door / window
    r = g.rear()
    for u0, u1 in ((-g.hw + 0.075, DOOR[0] - 0.04), (0.50, g.hw - 0.075)):
        plate(p, r, [(u0, 0.71), (u1, 0.71), (u1, 0.85), (u0, 0.85)], -0.003, 0.004, "sl_stripe")
        plate(p, r, [(u0, 0.645), (u1, 0.645), (u1, 0.678), (u0, 0.678)], -0.003, 0.004, "sl_stripe")


def windows_trim(g, p):
    for mapper, ol, mull in window_list(g):
        # recover the rect from the outline extents
        us, vs = [q[0] for q in ol], [q[1] for q in ol]
        u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
        outer = offset_rect(u0, u1, v0, v1, 0.05, 0.035)
        inner = offset_rect(u0, u1, v0, v1, 0.05, -0.004)
        frame(p, mapper, inner, outer, -0.004, 0.014, "sl_frame")
        if mull is not None:
            plate(p, mapper, [(mull - 0.012, v0), (mull + 0.012, v0), (mull + 0.012, v1), (mull - 0.012, v1)],
                  -0.03, 0.008, "sl_frame")
        # slider track line across the bottom of the glass
        plate(p, mapper, [(u0, v0), (u1, v0), (u1, v0 + 0.018), (u0, v0 + 0.018)], -0.03, 0.004, "sl_frame")


def rear_details(g, p, mats):
    r = g.rear()
    hw, yr, zt = g.hw, g.yr, g.ztop
    # door: handle + lock, hinges, grab handle
    plate(p, r, rounded_rect(-0.255, -0.205, 0.66, 0.80, 0.015, 2), 0.0, 0.02, "chrome")
    plate(p, r, rounded_rect(-0.25, -0.21, 0.83, 0.87, 0.015, 2), 0.0, 0.015, "sl_frame")
    for z in (0.30, 0.75, 1.20):
        plate(p, r, [(-0.80, z), (-0.74, z), (-0.74, z + 0.07), (-0.80, z + 0.07)], 0.0, 0.012, "sl_frame")
    for z in (0.42, 0.92):
        cylinder_y(p, -0.08, z, 0.012, yr + 0.01, yr - 0.06, "chrome", seg=8)
    cylinder_z(p, -0.08, yr - 0.06, 0.014, 0.40, 0.94, "chrome", seg=10)
    # porch light over the door
    plate(p, r, rounded_rect(-0.52, -0.42, 1.43, 1.47, 0.012, 2), 0.0, 0.03, "plastic_white")
    plate(p, r, rounded_rect(-0.51, -0.43, 1.432, 1.444, 0.004, 1), 0.02, 0.031, "lamp_clear")
    # tail lamps (red over amber over clear) in black bezels, lower corners
    for sgn in (-1, 1):
        ua, ub = sorted((sgn * (hw - 0.22), sgn * (hw - 0.09)))
        plate(p, r, rounded_rect(ua, ub, 0.11, 0.47, 0.02, 2), 0.0, 0.018, "sl_frame")
        plate(p, r, rounded_rect(ua + 0.012, ub - 0.012, 0.29, 0.455, 0.012, 2), 0.01, 0.03, "lamp_red_lens")
        plate(p, r, rounded_rect(ua + 0.012, ub - 0.012, 0.19, 0.28, 0.012, 2), 0.01, 0.03, "lamp_amber")
        plate(p, r, rounded_rect(ua + 0.012, ub - 0.012, 0.125, 0.18, 0.012, 2), 0.01, 0.03, "lamp_clear")
        # top corner clearance lamps
        uc = sgn * (hw - 0.12)
        plate(p, r, rounded_rect(uc - 0.035, uc + 0.035, zt - 0.11, zt - 0.075, 0.01, 2), 0.0, 0.02,
              "lamp_red_lens")
    for u in (-0.12, 0.0, 0.12):     # ID lamp bar
        plate(p, r, rounded_rect(u - 0.03, u + 0.03, zt - 0.11, zt - 0.08, 0.01, 2), 0.0, 0.02, "lamp_red_lens")
    # reflectors under the tail lamps? keep a pair of small red reflectors on the door side
    # ladder (right of the window)
    ly = yr - 0.075
    for x in (0.60, 0.90):
        cylinder_z(p, x, ly, 0.016, 0.40, zt + 0.10, "alloy", seg=10)
        cylinder_y(p, x, zt + 0.10, 0.016, ly, yr + 0.26, "alloy", seg=10)
        cylinder_z(p, x, yr + 0.26, 0.016, zt - 0.01, zt + 0.10, "alloy", seg=10)
        for z in (0.48, 1.30):
            cylinder_y(p, x, z, 0.011, yr + 0.01, ly, "alloy", seg=8)
    for k in range(5):
        z = 0.52 + k * 0.215
        cylinder_x(p, ly, z, 0.013, 0.60, 0.90, "alloy", seg=8)
    # stowed entry step under the door
    box(p, (DOOR[0] + 0.04, yr + 0.02, -0.11), (DOOR[1] - 0.04, yr + 0.30, -0.02), "sl_frame", bev=0.008)
    box(p, (DOOR[0] + 0.06, yr - 0.005, -0.10), (DOOR[1] - 0.06, yr + 0.02, -0.03), "steel")


def side_details(g, p):
    hw, zt, zc = g.hw, g.ztop, g.zc
    for sgn in (-1, 1):
        s = g.side(sgn)
        # bottom rub rail + roof edge cap (sides)
        plate(p, s, [(g.yr + 0.07, 0.055), (g.yb - 0.02, 0.055), (g.yb - 0.02, 0.085), (g.yr + 0.07, 0.085)],
              -0.004, 0.01, "sl_frame")
        plate(p, s, [(g.yr + 0.07, zt - 0.085), (g.yn - 0.42, zt - 0.085), (g.yn - 0.42, zt - 0.06),
                     (g.yr + 0.07, zt - 0.06)], -0.004, 0.012, "sl_frame")
        # amber front side marker, red rear side marker
        plate(p, s, rounded_rect(1.16, 1.22, zc + 0.20, zc + 0.24, 0.01, 2), 0.0, 0.018, "lamp_amber")
        plate(p, s, rounded_rect(g.yr + 0.12, g.yr + 0.18, zt - 0.13, zt - 0.09, 0.01, 2), 0.0, 0.018,
              "lamp_red_lens")
        plate(p, s, rounded_rect(-0.62, -0.56, 0.12, 0.16, 0.01, 2), 0.0, 0.016, "lamp_amber")
    # left: storage hatch lock + hinge
    s = g.side(-1)
    u0, u1, v0, v1, _ = HATCH
    plate(p, s, rounded_rect((u0 + u1) / 2 - 0.03, (u0 + u1) / 2 + 0.03, v0 + 0.05, v0 + 0.09, 0.01, 2),
          0.0, 0.014, "chrome")
    plate(p, s, [(u0 + 0.03, v1 - 0.03), (u1 - 0.03, v1 - 0.03), (u1 - 0.03, v1 - 0.012), (u0 + 0.03, v1 - 0.012)],
          0.0, 0.01, "sl_frame")
    # left: shore power / water fill
    plate(p, s, rounded_rect(-1.30, -1.20, 0.14, 0.24, 0.015, 2), 0.0, 0.012, "plastic_white")
    plate(p, s, rounded_rect(-1.27, -1.23, 0.17, 0.21, 0.01, 2), 0.0, 0.02, "sl_frame")
    # right: fridge vents (white frame, dark louvres)
    s = g.side(1)
    for v0, v1 in ((0.12, 0.36), (1.25, 1.40)):
        u0, u1 = -1.92, -1.47
        plate(p, s, rounded_rect(u0, u1, v0, v1, 0.02, 2), -0.003, 0.012, "plastic_white")
        nl = max(2, int((v1 - v0) / 0.04))
        for k in range(nl):
            vv = v0 + 0.025 + k * (v1 - v0 - 0.05) / max(nl - 1, 1)
            plate(p, s, [(u0 + 0.03, vv - 0.008), (u1 - 0.03, vv - 0.008), (u1 - 0.03, vv + 0.008),
                         (u0 + 0.03, vv + 0.008)], 0.0, 0.016, "sl_frame")


def front_details(g, p):
    (y0, z0), (y1, z1) = g.sl0, g.sl1
    t = Vector((0.0, y1 - y0, z1 - z0)).normalized()
    n = Vector((0.0, -t.z, t.y))
    if n.y < 0:
        n = -n
    ax = (Vector((1, 0, 0)), t, n)
    base = Vector((0.0, y0, z0)) + t * 0.13
    for u in (-0.16, 0.0, 0.16):
        oriented_box(p, base + Vector((u, 0, 0)) + n * 0.006, ax, (0.06, 0.035, 0.018), "lamp_amber", bev=0.004)
    for sgn in (-1, 1):
        oriented_box(p, base + Vector((sgn * (g.hw - 0.14), 0, 0)) + n * 0.006, ax, (0.06, 0.035, 0.018),
                     "lamp_amber", bev=0.004)
    # front window: small rock-guard lip over the top
    f = g.front()
    zt = g.ff1[1] - 0.04
    plate(p, f, [(-0.62, zt), (0.62, zt), (0.62, zt + 0.02), (-0.62, zt + 0.02)], -0.004, 0.03, "sl_frame")


def roof(g, p):
    zt = g.ztop
    # air conditioner shroud
    prof = fillet_poly([(-1.32, zt, 0.0), (-0.38, zt, 0.0), (-0.38, zt + 0.12, 0.06),
                        (-0.58, zt + 0.25, 0.10), (-1.26, zt + 0.25, 0.06), (-1.32, zt + 0.20, 0.03)])
    vs = prism_x(p, prof, -0.37, 0.37, "sl_acwhite")
    edges = list({e for v in vs for e in v.link_edges if abs(e.verts[0].co.x - e.verts[1].co.x) < 1e-6
                  and min(e.verts[0].co.z, e.verts[1].co.z) > zt + 0.01})
    bevel(p.bm, edges, 0.04, 2)
    for sgn in (-1, 1):
        x = sgn * 0.37
        box(p, (min(x, x + sgn * 0.006), -1.20, zt + 0.05), (max(x, x + sgn * 0.006), -0.62, zt + 0.17), "sl_frame")
        for k in range(5):
            z = zt + 0.065 + k * 0.023
            box(p, (min(x, x + sgn * 0.012), -1.20, z), (max(x, x + sgn * 0.012), -0.62, z + 0.008), "sl_acwhite")
    # roof vents: white base + smoked tilted lid
    for yc in (0.55, -1.80):
        box(p, (-0.21, yc - 0.21, zt - 0.01), (0.21, yc + 0.21, zt + 0.045), "plastic_white", bev=0.01)
        ang = math.radians(9)
        t = Vector((0, math.cos(ang), -math.sin(ang)))
        n = Vector((0, math.sin(ang), math.cos(ang)))
        c = Vector((0, yc, zt + 0.045 + 0.04))
        oriented_box(p, c, (Vector((1, 0, 0)), t, n), (0.38, 0.40, 0.025), "trim_gloss", bev=0.008)
    # roof edge cap across the rear
    box(p, (-g.hw + 0.06, g.yr - 0.012, zt - 0.085), (g.hw - 0.06, g.yr + 0.01, zt - 0.06), "sl_frame")


def jacks(g, p):
    hw = g.hw
    for yc in (g.yb - 0.16, g.yr + 0.12):
        for sgn in (-1, 1):
            xs = sorted((sgn * (hw - 0.01), sgn * (hw + 0.035)))
            box(p, (xs[0], yc - 0.07, 0.12), (xs[1], yc + 0.07, 0.78), "sl_frame", bev=0.006)
            xc = sgn * (hw + 0.08)
            cylinder_z(p, xc, yc, 0.032, 0.02, 0.80, "sl_frame", seg=12)
            cylinder_z(p, xc, yc, 0.024, -0.14, 0.02, "steel", seg=12)
            box(p, (xc - 0.055, yc - 0.055, -0.16), (xc + 0.055, yc + 0.055, -0.14), "sl_frame", bev=0.004)
            box(p, (xc - 0.045, yc - 0.045, 0.80), (xc + 0.045, yc + 0.045, 0.88), "sl_frame", bev=0.008)
            cylinder_x(p, yc, 0.84, 0.009, xc, xc + sgn * 0.08, "steel", seg=8)
            for z in (0.18, 0.70):           # clamp collars
                box(p, (min(xc, sgn * (hw + 0.03)), yc - 0.02, z), (max(xc, sgn * (hw + 0.03)), yc + 0.02, z + 0.04),
                    "sl_frame")


def build(cfg, collection, mats):
    setup_materials(cfg, mats)
    g = Geo(cfg)
    objs = build_body(g, mats, collection)
    p = Part(f"{NAME}_details", mats)
    stripes(g, p)
    windows_trim(g, p)
    rear_details(g, p, mats)
    side_details(g, p)
    front_details(g, p)
    roof(g, p)
    jacks(g, p)
    objs.append(p.finish(collection, smooth=35))
    tris = sum(len(pl.vertices) - 2 for o in objs for pl in o.data.polygons)
    print(f"[{NAME}] camper triangles: {tris}")
    return objs
