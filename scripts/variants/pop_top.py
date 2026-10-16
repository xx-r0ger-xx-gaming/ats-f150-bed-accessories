"""Pop-top camper: dark cab-high base box on the bed, light aluminium hard lid with a drip lip,
olive canvas tent walls (zippered mesh windows); smoked base windows over an interior.

Parameters (cfg["camper"], all optional):
  state               "deployed" (default) or "closed" (travel pose: lid down, no tent walls/struts)
  lift_front/rear     lid underside rise above the base top at the base's front/rear edge (m).
                      Equal values = level lift; lift_front < lift_rear = front-hinged wedge.
  base_top_above_roof base box top above the cab roof (m)
  lid_front_overhang  lid nose reaching forward over the cab roof (m)
  lid_rear_overhang, lid_side_overhang, lid_thickness
  fabric_sag          inward pull of the taut tent walls at mid height (m)
  fabric_folds        amplitude of the diagonal tension folds (m)
  struts              gas struts at the four corners when deployed (bool)
  lid_lip             depth of the drip lip skirt under the lid edge (m)
  closed_gap          travel pose: lid height above the base top, filled by the folded canvas (m)
  cab_gap, seal_min   base front face clearance to the cab back / minimum rail-seal height (m)

The base footprint comes from the shared bed dimensions (cfg["bed"], lib/bed.py Bed.footprint).

Original geometry only (no logos/brands). Render-only, never exported.
"""
import math

import bmesh
from mathutils import Matrix, Vector

from lib.meshkit import (
    Part, add_weighted_normals, annulus_prism, box, build_prism, cut_openings, faces_of, loft, rounded_rect,
    set_smooth,
)
from lib.shell_v1 import strip_fill

TRUCK_TYPES = ("pickup",)
DESCRIPTION = "Pop-top camper (raised lid, fabric tent walls)"

NAME = "pop_top"


# ------------------------------------------------------------------ materials

def _materials(mats):
    if "pop_lid" in mats:
        return
    mats.add("pop_lid", mats.car_paint("pop_lid", (0.80, 0.81, 0.80, 1), metallic=0.25, roughness=0.32,
                                       clearcoat=0.6, flake=0.08))
    mats.add("pop_base", mats.car_paint("pop_base", (0.016, 0.017, 0.018, 1), metallic=0.0, roughness=0.55,
                                        clearcoat=0.25, clearcoat_roughness=0.25, flake=0.0))
    # tent canvas: olive-charcoal ripstop canvas (weave + soft wrinkles + mottling, library factory)
    mats.add("pop_fabric", mats.canvas_material("pop_fabric", (0.060, 0.064, 0.048)))
    mats.add("pop_mesh", mats["canvas_mesh"])
    # zipper flap seam: darker, smoother webbing; zipper coil: satin black
    mats.add("pop_zip", mats.principled("pop_zip", base_color=(0.020, 0.021, 0.018, 1), roughness=0.55,
                                         specular=0.35, sheen=0.4))


# ------------------------------------------------------------------ helpers

def _resample(poly, spacing):
    """Uniformly resample a closed (x, y) polyline; returns pts, outward normals, arclength, total."""
    n = len(poly)
    seg = [(Vector(poly[i]), Vector(poly[(i + 1) % n])) for i in range(n)]
    lens = [(b - a).length for a, b in seg]
    total = sum(lens)
    count = max(8, int(round(total / spacing)))
    pts, ss = [], []
    i, acc = 0, 0.0
    for k in range(count):
        s = total * k / count
        while acc + lens[i] < s and i < n - 1:
            acc += lens[i]
            i += 1
        a, b = seg[i]
        f = (s - acc) / lens[i] if lens[i] > 0 else 0.0
        pts.append(a.lerp(b, f))
        ss.append(s)
    nrm = []
    for k in range(count):
        t = (pts[(k + 1) % count] - pts[k - 1]).normalized()
        nrm.append(Vector((t.y, -t.x)))      # CCW outline -> right-hand side is outward
    return pts, nrm, ss, total


class Plan:
    """Dense closed plan outline with arclength lookup (s in metres, wraps)."""

    def __init__(self, poly, spacing):
        self.pts, self.nrm, self.ss, self.total = _resample(poly, spacing)

    def at(self, s):
        s %= self.total
        n = len(self.pts)
        step = self.total / n
        k = int(s / step) % n
        f = (s - k * step) / step
        k2 = (k + 1) % n
        p = self.pts[k].lerp(self.pts[k2], f)
        q = self.nrm[k].lerp(self.nrm[k2], f).normalized()
        return p, q

    def s_of(self, x, y):
        target = Vector((x, y))
        k = min(range(len(self.pts)), key=lambda i: (self.pts[i] - target).length_squared)
        return self.ss[k]


def _densify(poly, step=0.06):
    """Insert points so no closed-outline segment is longer than step (keeps fabric-following panes)."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = Vector(poly[i]), Vector(poly[(i + 1) % n])
        k = max(1, int(math.ceil((b - a).length / step)))
        out += [tuple(a.lerp(b, j / k)) for j in range(k)]
    return out


def _tube(part, p, q, r, key, seg=10):
    """Capped cylinder between points p and q."""
    p, q = Vector(p), Vector(q)
    d = q - p
    res = bmesh.ops.create_cone(part.bm, cap_ends=True, cap_tris=False, segments=seg,
                                radius1=r, radius2=r, depth=d.length)
    vs = res["verts"]
    rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    bmesh.ops.transform(part.bm, matrix=Matrix.Translation((p + q) / 2) @ rot, verts=vs)
    part.set_mat(faces_of(vs), key)
    return vs


def _offset(ol, d):
    """Offset a CCW (u, v) outline by d (d > 0 = outward)."""
    n = len(ol)
    out = []
    for i in range(n):
        a, b = Vector(ol[i - 1]), Vector(ol[(i + 1) % n])
        t = (b - a).normalized()
        out.append((ol[i][0] + t.y * d, ol[i][1] - t.x * d))
    return out


def _glaze(part, ol, mapper, outward, strips=False):
    """Smoked pane 12 mm under the skin + rubber seal lip around the opening (mapper(u, v, d)).
    strips=True builds the pane from vertical strips (for a curved face)."""
    bm = part.bm
    for poly in (strip_fill(ol) if strips else [ol]):
        pane = bm.faces.new([bm.verts.new(mapper(u, v, -0.012)) for u, v in poly])
        pane.normal_update()
        if pane.normal.dot(Vector(outward)) < 0:
            pane.normal_flip()
        part.set_mat([pane], "glass")              # the truck's own cab glass
    for (d_in, d_out, a, b, key) in ((-0.012, 0.0, -0.016, 0.003, "seal"), (0.0, 0.016, -0.002, 0.005, "seal")):
        o, i = _offset(ol, d_out), _offset(ol, d_in)
        faces = annulus_prism(bm, [mapper(u, v, a) for u, v in o], [mapper(u, v, b) for u, v in o],
                              [mapper(u, v, a) for u, v in i], [mapper(u, v, b) for u, v in i])
        part.set_mat(faces, key)


def _tris(objs):
    return sum(sum(len(pl.vertices) - 2 for pl in o.data.polygons) for o in objs if o.type == "MESH")


# ------------------------------------------------------------------ fitted footprint helpers

def _dense_section(pts, bot_i, top_i, n):
    """Insert n points into the bottom edge (pts[bot_i] -> pts[bot_i + 1]) and the top edge of a
    closed section so a rear-bow warp can bend those faces. Returns (points, source segment index
    per new segment, bottom-run start, top-run start); each run has n + 2 points, x running
    -x -> +x along the bottom and +x -> -x along the top."""
    out, src = [], []
    starts = {}
    m = len(pts)
    for i in range(m):
        a, b = Vector(pts[i]), Vector(pts[(i + 1) % m])
        if i in (bot_i, top_i):
            starts[i] = len(out)
            k = n + 1
            for j in range(k):
                out.append(tuple(a.lerp(b, j / k)))
                src.append(i)
        else:
            out.append(tuple(a))
            src.append(i)
    return out, src, starts[bot_i], starts[top_i]


def _cap_strips(part, ring, bstart, tstart, n, key):
    """Cap a densified section ring (BMVerts) with vertical strips + two side polygons."""
    bm = part.bm
    m = n + 1
    L = len(ring)
    B = [ring[(bstart + k) % L] for k in range(m + 1)]
    T = [ring[(tstart + k) % L] for k in range(m + 1)]
    faces = [bm.faces.new([B[k], B[k + 1], T[m - k - 1], T[m - k]]) for k in range(m)]
    right = [ring[i % L] for i in range(bstart + m, tstart + 1)]
    left = [ring[i % L] for i in range(tstart + m, bstart + L + 1)]
    for poly in (right, left):
        if len(poly) >= 3:
            faces.append(bm.faces.new(poly))
    part.set_mat(faces, key)
    return faces


def _side_bar(part, sx, x_in, x_out, y0, y1, z0, z1, key):
    """Bar along a tapered side: x_in(y) / x_out(y) give its inner/outer half widths."""
    rings = []
    for y in (y0, y1):
        xi, xo = x_in(y), x_out(y)
        rings.append([(sx * xi, y, z0), (sx * xo, y, z0), (sx * xo, y, z1), (sx * xi, y, z1)])
    faces = build_prism(part.bm, rings[0], rings[1])
    bmesh.ops.recalc_face_normals(part.bm, faces=faces)
    part.set_mat(faces, key)


def _x_boxes(part, x0, x1, lo_yz, hi_yz, key, n=16, bev=0.0):
    """A box spanning x0..x1, split into n segments so the rear-bow warp can bend it."""
    for i in range(n):
        a, b = x0 + (x1 - x0) * i / n, x0 + (x1 - x0) * (i + 1) / n
        box(part, (a, lo_yz[0], lo_yz[1]), (b, hi_yz[0], hi_yz[1]), key, bev=bev)


def _rear_warp(bed, fp, yr):
    """Bend everything near the rear end (fully for y < yr + 0.06, fading out by yr + 0.30) rearward
    by the tailgate bow, so a rear face built flat ends up flush with the curved tailgate."""
    if fp["bow"] <= 1e-6:
        return lambda part: None

    def apply(part):
        for v in part.bm.verts:
            t = (yr + 0.30 - v.co.y) / 0.24
            t = 1.0 if t >= 1.0 else (0.0 if t <= 0.0 else t * t * (3 - 2 * t))
            if t:
                v.co.y -= bed.rear_bow_at(v.co.x, fp) * t
    return apply


# ------------------------------------------------------------------ build

def build(cfg, collection, mats):
    c = cfg["camper"]
    bed = cfg["bed"]
    _materials(mats)
    deployed = c.get("state", "deployed") != "closed"
    gap = float(c.get("closed_gap", 0.03))       # travel pose: lid rests on the folded canvas
    lift_f = float(c.get("lift_front", 0.88)) if deployed else gap
    lift_r = float(c.get("lift_rear", 0.92)) if deployed else gap
    deployed = deployed and max(lift_f, lift_r) > 0.05

    # ---- base box footprint from the shared bed dimensions (lib/bed.py): on the rails, sides flush
    # with the tapering rail caps, front cab_gap behind the cab, rear corners on the tailgate face and
    # the rear end bowed like the tailgate (warp)
    fp = bed.footprint(cab_gap=float(c.get("cab_gap", 0.04)), seal_min=float(c.get("seal_min", 0.012)))
    yf, yr, zb = fp["y_front"], fp["y_rear"], fp["base_z"]
    zt = bed["cab_roof_z"] + float(c.get("base_top_above_roof", 0.035))
    warp = _rear_warp(bed, fp, yr)
    ND = 16                                       # extra points across the bottom/top edges

    def hw(y):                                    # bottom half width: flush with the rail caps
        return bed.rail_outer_hw_at(y)

    # tumblehome: the cab greenhouse's (measured, config/bed.json cab_*), scaled by
    # tumblehome_from_cab, so the base flank continues the cab's side line
    tumble = float(c.get("tumblehome_from_cab", 1.0)) * (bed.cab_hw_at(zb) - bed.cab_hw_at(zt - 0.04))

    def hwt(y):                                   # top half width
        return hw(y) - tumble

    def side_x(z, y):
        return hw(y) + (hwt(y) - hw(y)) * (z - zb) / ((zt - 0.04) - zb)

    objs = []

    # ---------------------------------------------------------------- base box
    base = Part(f"{NAME}_base", mats)

    def base_sec(y, d, dz):
        a, b_, top = hw(y) - d, hwt(y) - d, zt - dz
        sec = [(-a, zb), (a, zb), (b_, top - 0.04), (b_ - 0.014, top - 0.01), (b_ - 0.04, top),
               (-(b_ - 0.04), top), (-(b_ - 0.014), top - 0.01), (-b_, top - 0.04)]
        pts, _, bs, ts = _dense_section(sec, 0, 4, ND)
        return [(x, y, z) for x, z in pts], bs, ts

    stations = [(yr, 0.03, 0.014), (yr + 0.012, 0.009, 0.004), (yr + 0.035, 0, 0),
                (yf - 0.035, 0, 0), (yf - 0.012, 0.009, 0.004), (yf, 0.03, 0.014)]
    secs = [base_sec(*s) for s in stations]
    vr, _ = loft(base, [s[0] for s in secs], "pop_base", cap_start=False)
    _cap_strips(base, vr[0], secs[0][1], secs[0][2], ND, "pop_base")
    bmesh.ops.recalc_face_normals(base.bm, faces=base.bm.faces[:])
    # rail seal under the base (sides, rear; front: on the raised bed front wall inboard of the
    # rails, down to the rail caps outboard)
    seal = Part(f"{NAME}_rail_seal", mats)
    zs0, zs1 = bed["rail_cap_z"] - 0.001, zb + 0.004
    for sx in (-1, 1):
        _side_bar(seal, sx, lambda y: hw(y) - 0.07, lambda y: hw(y) - 0.002, yr + 0.04, yf - 0.02, zs0, zs1, "trim")
    _x_boxes(seal, -hw(yr) + 0.04, hw(yr) - 0.04, (yr + 0.004, zs0), (yr + 0.06, zs1), "trim")
    xi = bed["rail_inner_hw"]
    box(seal, (-xi, yf - 0.06, bed["front_wall_top_z"] - 0.001), (xi, yf - 0.004, zs1), "trim")
    for sx in (-1, 1):
        x0, x1 = sorted((sx * xi, sx * (hw(yf) - 0.07)))
        box(seal, (x0, yf - 0.06, zs0), (x1, yf - 0.004, zs1), "trim")
    warp(seal)
    objs.append(seal.finish(collection, smooth=35))
    # rear hatch handle + third brake light
    box(base, (-0.11, yr - 0.022, zb + 0.058), (0.11, yr + 0.01, zb + 0.083), "trim_gloss", bev=0.006)
    box(base, (-0.16, yr - 0.004, zt - 0.055), (0.16, yr + 0.02, zt - 0.03), "lamp_red_lens", bev=0.004)
    warp(base)
    base_ob = base.finish(collection, smooth=35)

    # windows: side windows (both sides) + rear hatch glass, as flush pockets
    openings = []
    glaze = Part(f"{NAME}_glazing", mats)
    # side glass on the cab's window line (as low as the rail seal allows, top level with the cab glass)
    wz0 = max(zb + 0.03, bed["cab_glass_bottom_z"], bed["rail_top_z"] + 0.045)
    wz1 = min(zt - 0.095, bed["cab_glass_top_z"])
    win_y0, win_y1 = yr + 0.20, yf - 0.16
    for sx in (-1, 1):
        def sp(y, z, d, sx=sx):                    # point on the side skin, d > 0 = outward
            return (sx * (side_x(z, y) + d), y, z)
        ol = rounded_rect(win_y0, win_y1, wz0, wz1, 0.06, 4)
        openings.append(([sp(y, z, 0.03) for y, z in ol], [sp(y, z, -0.20) for y, z in ol]))
        _glaze(glaze, ol, sp, (sx, 0, 0))
    hr = hwt(yr) - 0.15
    ol = _densify(rounded_rect(-hr, hr, zb + 0.103, zt - 0.085, 0.06, 4), 0.05)

    def rp(x, z, d):                               # point on the (bowed) rear face
        return (x, yr - bed.rear_bow_at(x, fp) - d, z)
    openings.append(([rp(x, z, 0.04 + fp["bow"]) for x, z in ol], [rp(x, z, -0.20) for x, z in ol]))
    _glaze(glaze, ol, rp, (0, -1, 0), strips=True)
    cut_openings(base_ob, openings, mats, collection, glass_key="curtain", wall_key="interior")
    objs.append(glaze.finish(collection, smooth=40))
    set_smooth(base_ob, 35)
    add_weighted_normals(base_ob)
    objs.append(base_ob)

    # ---------------------------------------------------------------- lid transform (hinge at base front)
    ang = math.atan2(lift_r - lift_f, yf - yr)
    M = (Matrix.Translation((0, yf, zt + lift_f)) @ Matrix.Rotation(-ang, 4, "X")
         @ Matrix.Translation((0, -yf, -zt)))

    # ---------------------------------------------------------------- lid
    lid = Part(f"{NAME}_lid", mats)
    thk = float(c.get("lid_thickness", 0.11))
    so = float(c.get("lid_side_overhang", 0.025))

    def W(y):                                     # lid half width follows the base top
        return hwt(min(y, yf)) + so
    ylr = yr - float(c.get("lid_rear_overhang", 0.015))
    fo = float(c.get("lid_front_overhang", 0.34))
    ylf = yf + fo
    tip_h = 0.072
    TRIM = {0, 1, 2, 10, 11}                      # bottom-band segments of the 12-point section

    def lid_sec(y, w, h):
        sec = [(-w + 0.015, 0), (w - 0.015, 0), (w, 0.015), (w, 0.034), (w, h - 0.03), (w - 0.01, h - 0.01),
               (w - 0.035, h), (-(w - 0.035), h), (-(w - 0.01), h - 0.01), (-w, h - 0.03), (-w, 0.034),
               (-w, 0.015)]
        pts, src, bs, ts = _dense_section(sec, 0, 6, ND)
        return [(x, y, zt + z) for x, z in pts], src, bs, ts

    lst = [(ylr, W(ylr) - 0.035, thk - 0.02), (ylr + 0.012, W(ylr) - 0.01, thk - 0.005),
           (ylr + 0.035, W(ylr + 0.035), thk), (yf - 0.06, W(yf - 0.06), thk)]
    for f in (0.25, 0.5, 0.72, 0.88):
        lst.append((yf + f * fo, W(yf) - 0.035 * f ** 2, thk - (thk - tip_h) * f ** 1.4))
    lst += [(ylf - 0.012, W(yf) - 0.035 - 0.012, tip_h - 0.004), (ylf, W(yf) - 0.035 - 0.04, tip_h - 0.014)]
    lsecs = [lid_sec(*s) for s in lst]
    rings, faces = loft(lid, [s[0] for s in lsecs], "pop_lid", cap_start=False)
    src = lsecs[0][1]
    n = len(src)
    for k, f in enumerate(faces[:(len(lst) - 1) * n]):
        if src[k % n] in TRIM:
            f.material_index = lid.idx("trim")
    _cap_strips(lid, rings[0], lsecs[0][2], lsecs[0][3], ND, "pop_lid")
    bmesh.ops.recalc_face_normals(lid.bm, faces=lid.bm.faces[:])
    # low ribs on the lid top (stiffeners), follow the nose slope
    for xr in (-0.42, 0.0, 0.42):
        box(lid, (xr - 0.035, ylr + 0.12, zt + thk - 0.004), (xr + 0.035, yf - 0.10, zt + thk + 0.008),
            "pop_lid", bev=0.006)
    # drip lip: a skirt under the lid edge (sides + rear) that hangs past the base top
    lip = float(c.get("lid_lip", 0.012))
    for sx in (-1, 1):
        _side_bar(lid, sx, lambda y: W(y) - 0.011, lambda y: W(y) + 0.001, ylr + 0.035, yf - 0.06,
                  zt - lip, zt + 0.03, "trim")
    _x_boxes(lid, -(W(ylr) - 0.03), W(ylr) - 0.03, (ylr + 0.010, zt - lip), (ylr + 0.022, zt + 0.03), "trim")
    warp(lid)
    lid_verts = list(lid.bm.verts)
    bmesh.ops.transform(lid.bm, matrix=M, verts=lid_verts)
    objs.append(lid.finish(collection, smooth=40, weighted=True))

    # ---------------------------------------------------------------- tent walls
    if deployed:
        objs += _build_tent(c, collection, mats, M, hwt, yf, yr, zt, side_x, warp)
    else:
        objs.append(_folded_seam(collection, mats, M, hwt(yr), yf, yr, zt, lift_f, warp))
        # over-centre latches on the base flank, hooks on the lid lip
        latch = Part(f"{NAME}_latches", mats)
        for sx in (-1, 1):
            for yy in (yf - 0.25, yr + 0.25):
                xs = side_x(zt - 0.08, yy)
                x0, x1 = sorted((sx * (xs - 0.002), sx * (xs + 0.018)))
                box(latch, (x0, yy - 0.03, zt - 0.11), (x1, yy + 0.03, zt - 0.05), "trim_gloss", bev=0.004)
                x0, x1 = sorted((sx * (xs + 0.006), sx * (xs + 0.012)))
                box(latch, (x0, yy - 0.012, zt - 0.06), (x1, yy + 0.012, zt + lift_f - 0.015), "steel", bev=0.002)
                x0, x1 = sorted((sx * (W(yy) - 0.001), sx * (W(yy) + 0.006)))
                box(latch, (x0, yy - 0.022, zt + lift_f - 0.02), (x1, yy + 0.022, zt + lift_f + 0.012), "steel",
                    bev=0.002)
        objs.append(latch.finish(collection, smooth=35))

    print(f"[{NAME}] state={'deployed' if deployed else 'closed'} lift=({lift_f:.2f},{lift_r:.2f}) "
          f"footprint y {yf:+.3f}..{yr:+.3f} hw {hw(yf):.3f}->{hw(yr):.3f} bow {fp['bow']:.3f} "
          f"base z {zb:+.3f} camper tris={_tris(objs)}")
    return objs


def _folded_seam(collection, mats, M, hwt, yf, yr, zt, gap, warp):
    """Travel pose: the tent canvas folded into the gap between base top and lid, bulging out a
    little in soft irregular pleats, with the attachment channel visible at the base top."""
    hx = hwt - 0.035
    plan = Plan(rounded_rect(-hx, hx, yr + 0.035, yf - 0.035, 0.06, 3), 0.03)
    part = Part(f"{NAME}_folded_canvas", mats)
    prof = [(0.0, -0.004), (0.026, 0.22), (0.042, 0.5), (0.03, 0.8), (0.0, 1.0)]
    rings = []
    for off, t in prof:
        ring = []
        for s_ in plan.ss:
            p, n = plan.at(s_)
            w = 1.0 + 0.45 * math.sin(s_ / 0.11) * math.sin(s_ / 0.043 + 1.3)
            o = off * w if 0.0 < t < 1.0 else off
            q = Vector((p.x + n.x * o, p.y + n.y * o, zt + t * gap))
            ring.append(q)
        rings.append(ring)
    loft(part, rings, "pop_fabric", cap_start=False, cap_end=False)
    warp(part)
    return part.finish(collection, smooth=70)


def _build_tent(c, collection, mats, M, hwt, yf, yr, zt, side_x, warp):
    """hwt(y), side_x(z, y): base top half width / base flank; warp(part) bends the rear end."""
    objs = []
    sag = float(c.get("fabric_sag", 0.032))
    folds = float(c.get("fabric_folds", 0.007))
    hx = hwt(yr) - 0.05                           # narrowest (rear) base top: the tent fits it all along
    fy0, fy1 = yr + 0.05, yf - 0.05
    plan = Plan(rounded_rect(-hx, hx, fy0, fy1, 0.06, 3), 0.045)

    def ends(s):
        p, nrm = plan.at(s)
        bot = Vector((p.x, p.y, zt - 0.008))
        top = M @ Vector((p.x, p.y, zt + 0.012))
        return bot, top, nrm

    def disp(s, t):
        env = math.sin(math.pi * t)
        d = -sag * env
        # diagonal tension folds, strongest towards the top/bottom corners of each wall
        d += folds * env ** 0.6 * math.sin(2 * math.pi * s / 0.38 + 6.0 * t)
        return d

    def point(s, h, off=0.0):
        """Fabric surface at arclength s, height h (m above the bottom seam), pushed off outward."""
        bot, top, nrm = ends(s)
        H = top.z - bot.z
        t = max(0.0, min(1.0, h / H))
        p = bot.lerp(top, t)
        dd = disp(s, t) + off
        return Vector((p.x + nrm.x * dd, p.y + nrm.y * dd, p.z))

    def height(s):
        bot, top, _ = ends(s)
        return top.z - bot.z

    # fabric skin
    fab = Part(f"{NAME}_tent", mats)
    K = 14
    rings = []
    for k in range(K + 1):
        t = k / K
        ring = []
        for s in plan.ss:
            bot, top, nrm = ends(s)
            p = bot.lerp(top, t)
            dd = disp(s, t)
            ring.append((p.x + nrm.x * dd, p.y + nrm.y * dd, p.z))
        rings.append(ring)
    loft(fab, rings, "pop_fabric", cap_start=False, cap_end=False)
    # attachment channels (bottom on the base top, top under the lid)
    for which in (0, 1):
        r3 = []
        for oo, dz in ((0.014, 0.0), (0.014, 0.026), (-0.004, 0.026)):
            ring = []
            for s in plan.ss:
                bot, top, nrm = ends(s)
                if which == 0:
                    ring.append((bot.x + nrm.x * oo, bot.y + nrm.y * oo, bot.z + 0.006 + dz))
                else:
                    q = top + Vector((nrm.x * oo, nrm.y * oo, 0))
                    ring.append((q.x, q.y, q.z - 0.012 - dz))
            r3.append(ring)
        loft(fab, r3, "trim", cap_start=False, cap_end=False)
    warp(fab)
    tent_ob = fab.finish(collection, smooth=60)
    objs.append(tent_ob)

    # windows: mesh pane + zipper flap outline + rolled flap + toggles
    det = Part(f"{NAME}_tent_windows", mats)

    def window(sc, w, h0, h1):
        H = min(height(sc - w / 2), height(sc + w / 2))
        h1 = min(h1, H - 0.10)
        bm = det.bm
        out = _densify(rounded_rect(sc - w / 2, sc + w / 2, h0, h1, 0.07, 4))
        cu, cv = sc, (h0 + h1) / 2
        m = len(out)
        vr = [[bm.verts.new(point(cu + (u - cu) * f, cv + (v - cv) * f, 0.008)) for u, v in out]
              for f in (1.0, 0.7, 0.4)]
        vc = bm.verts.new(point(cu, cv, 0.008))
        fs = []
        for A, B in zip(vr, vr[1:]):
            for i in range(m):
                j = (i + 1) % m
                fs.append(bm.faces.new([A[i], A[j], B[j], B[i]]))
        for i in range(m):
            fs.append(bm.faces.new([vr[-1][i], vr[-1][(i + 1) % m], vc]))
        det.set_mat(fs, "pop_mesh")
        # zipper / flap seam band around the opening
        for grow, off, key in ((0.028, 0.010, "pop_zip"), (0.006, 0.0115, "trim")):
            big = _densify(rounded_rect(sc - w / 2 - grow, sc + w / 2 + grow, h0 - grow, h1 + grow, 0.07 + grow, 4))
            bw = 0.010 if key == "trim" else 0.03
            sml =[(cu + (u - cu) * (1 - bw / ((w / 2) + grow)), cv + (v - cv) * (1 - bw / ((h1 - h0) / 2 + grow)))
                   for u, v in big]
            a = [bm.verts.new(point(u, v, off)) for u, v in big]
            b = [bm.verts.new(point(u, v, off)) for u, v in sml]
            mb = len(a)
            fs = [bm.faces.new([a[i], a[(i + 1) % mb], b[(i + 1) % mb], b[i]]) for i in range(mb)]
            det.set_mat(fs, key)
        # rolled flap above the window (fabric roll, held by two toggles)
        rr = 0.024
        hroll = h1 + 0.045
        ring_list = []
        nseg = 10
        for i in range(nseg + 1):
            u = sc - w / 2 + 0.02 + (w - 0.04) * i / nseg
            _, _, nrm = ends(u)
            ctr = point(u, hroll, rr + 0.004)
            ring = []
            for a8 in range(8):
                a = 2 * math.pi * a8 / 8
                ring.append(ctr + Vector((nrm.x, nrm.y, 0)) * (rr * math.cos(a)) + Vector((0, 0, rr * math.sin(a))))
            ring_list.append(ring)
        loft(det, ring_list, "pop_fabric")
        for u in (sc - w * 0.3, sc + w * 0.3):
            _, _, nrm = ends(u)
            p0 = point(u, hroll + rr + 0.01, 0.006)
            p1 = point(u, hroll - rr - 0.03, 2 * rr + 0.008)
            t = Vector((-nrm.y, nrm.x, 0))
            quad = [p0 - t * 0.012, p0 + t * 0.012, p1 + t * 0.012, p1 - t * 0.012]
            bm_ = det.bm
            vs = [bm_.verts.new(q) for q in quad]
            det.set_mat([bm_.faces.new(vs)], "pop_zip")

    side_w = min(0.80, (fy1 - fy0) - 0.40)
    yc_side = (fy0 + fy1) / 2 - 0.08
    for sx in (-1, 1):
        window(plan.s_of(sx * hx, yc_side), side_w, 0.20, 0.80)
    window(plan.s_of(0.0, fy0), min(1.0, 2 * hx - 0.42), 0.17, 0.82)       # rear
    window(plan.s_of(0.0, fy1), min(0.70, 2 * hx - 0.6), 0.26, 0.72)       # front
    warp(det)
    objs.append(det.finish(collection, smooth=50))

    # gas struts at the corners (outside the fabric, on the base/lid flanks)
    if c.get("struts", True):
        st = Part(f"{NAME}_struts", mats)
        for sx in (-1, 1):
            for ya, yb in ((yf - 0.10, yf - 0.34), (yr + 0.10, yr + 0.34)):
                za = zt - 0.065
                pa = Vector((sx * (side_x(za, ya) + 0.026), ya, za))
                pb = M @ Vector((sx * (hwt(yb) + 0.005), yb, zt - 0.006))
                d = pb - pa
                L = d.length
                body_end = pa + d * 0.56
                _tube(st, pa + d.normalized() * 0.03, body_end, 0.0115, "trim_gloss")
                _tube(st, body_end - d.normalized() * 0.01, pb - d.normalized() * 0.03, 0.0048, "chrome", seg=8)
                for p in (pa, pb):
                    _tube(st, p - d.normalized() * 0.035, p + d.normalized() * 0.035, 0.008, "steel", seg=8)
                # brackets: base flank plate, lid underside block
                xa = side_x(za, ya)
                box(st, (min(sx * xa, sx * (xa + 0.03)), ya - 0.03, za - 0.035),
                    (max(sx * xa, sx * (xa + 0.03)), ya + 0.03, za + 0.025), "steel", bev=0.004)
                blk = [M @ Vector(v) for v in ((sx * (hwt(yb) - 0.01), yb, zt + 0.003), )]
                cx, cy, cz = blk[0]
                box(st, (cx - 0.02, cy - 0.03, cz - 0.03), (cx + 0.02, cy + 0.03, cz + 0.004), "steel", bev=0.004)
        objs.append(st.finish(collection, smooth=40))
    return objs
