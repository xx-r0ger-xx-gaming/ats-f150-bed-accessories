"""Render-only stand-in pickup (generic, debadged, original low-poly geometry).

Built by render_preview.py for context around the shell. Never exported, never packaged, and
not a game or manufacturer model: only approximate published overall proportions of a
full-size crew-cab pickup with a 5.5 ft bed (config/v1.json "preview"). No logos or lettering.

Frame: built with the ground at z = 0, the bed's front wall at y = 0, +Y toward the cab; the
caller offsets the whole group down by the rail height so the rails meet the shell origin.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

COLLECTION = "preview_context"


# ------------------------------------------------------------------ materials

def material(name, color, rough=0.5, metallic=0.0, clearcoat=0.0, emission=0.0, spec=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    if spec is not None:
        color = spec["base_color"]
        rough = spec["roughness"]
        metallic = spec.get("metallic", 0.0)
        clearcoat = spec.get("clearcoat", 0.0)
        b.inputs["Clearcoat Roughness"].default_value = spec.get("clearcoat_roughness", 0.03)
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Clearcoat"].default_value = clearcoat
    if emission:
        b.inputs["Emission"].default_value = color
        b.inputs["Emission Strength"].default_value = emission
    mat.diffuse_color = color
    return mat


def make_materials(cfg):
    paint = cfg["materials"]["shell_paint"]
    return {
        "paint": material("pv_paint", None, spec=paint),
        "black": material("pv_black_trim", (0.008, 0.008, 0.009, 1), rough=0.62),
        "glass": material("pv_glass", (0.006, 0.007, 0.009, 1), rough=0.03, clearcoat=1.0),
        "tire": material("pv_tire", (0.018, 0.018, 0.018, 1), rough=0.85),
        "rim": material("pv_rim", (0.62, 0.63, 0.65, 1), rough=0.22, metallic=1.0),
        "dark_rim": material("pv_rim_recess", (0.05, 0.05, 0.055, 1), rough=0.5, metallic=0.4),
        "bumper": material("pv_bumper", (0.06, 0.062, 0.066, 1), rough=0.4, metallic=0.6),
        "tail": material("pv_tail_light", (0.45, 0.012, 0.01, 1), rough=0.12, emission=0.6),
        "lens": material("pv_lens", (0.75, 0.77, 0.8, 1), rough=0.08, metallic=0.3),
        "amber": material("pv_amber", (0.6, 0.25, 0.02, 1), rough=0.15),
        "plate": material("pv_plate", (0.78, 0.78, 0.76, 1), rough=0.6),
        "under": material("pv_underbody", (0.02, 0.02, 0.022, 1), rough=0.9),
        "liner": material("pv_bed_liner", (0.02, 0.02, 0.02, 1), rough=0.95),
    }


# ------------------------------------------------------------------ bmesh helpers

class Part:
    """One mesh object being assembled from several primitives; material slots by key."""

    def __init__(self, name, mats):
        self.name, self.mats = name, mats
        self.bm = bmesh.new()
        self.slots = []

    def idx(self, key):
        if key not in self.slots:
            self.slots.append(key)
        return self.slots.index(key)

    def set_mat(self, faces, key):
        i = self.idx(key)
        for f in faces:
            f.material_index = i

    def finish(self, collection, smooth=35):
        bm = self.bm
        bm.normal_update()
        me = bpy.data.meshes.new(self.name)
        bm.to_mesh(me)
        bm.free()
        for k in self.slots:
            me.materials.append(self.mats[k])
        if smooth:
            for p in me.polygons:
                p.use_smooth = True
            me.use_auto_smooth = True
            me.auto_smooth_angle = math.radians(smooth)
        ob = bpy.data.objects.new(self.name, me)
        collection.objects.link(ob)
        return ob


def bevel(bm, edges, offset, segments=2):
    edges = [e for e in edges if e.is_valid]
    if edges and offset > 0:
        bmesh.ops.bevel(bm, geom=edges, offset=offset, segments=segments, profile=0.5,
                        affect="EDGES", clamp_overlap=True)


def faces_of(verts):
    return list({f for v in verts for f in v.link_faces})


def edges_of(verts):
    return list({e for v in verts for e in v.link_edges})


def box(part, lo, hi, key, bev=0.0, seg=2):
    bm = part.bm
    res = bmesh.ops.create_cube(bm, size=1.0)
    vs = res["verts"]
    for v in vs:
        v.co = Vector(tuple(hi[i] if v.co[i] > 0 else lo[i] for i in range(3)))
    part.set_mat(faces_of(vs), key)
    bevel(bm, edges_of(vs), bev, seg)
    return vs


def oriented_box(part, center, axes, size, key, bev=0.0):
    bm = part.bm
    vs = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    for v in vs:
        lx, ly, lz = v.co
        v.co = center + axes[0] * lx * size[0] + axes[1] * ly * size[1] + axes[2] * lz * size[2]
    part.set_mat(faces_of(vs), key)
    bevel(bm, edges_of(vs), bev, 2)
    return vs


def prism_x(part, profile_yz, x0, x1, key):
    """Extrude a side-profile polygon (y, z) across x0..x1; returns (verts, cap_a, cap_b)."""
    bm = part.bm
    a = [bm.verts.new((x0, y, z)) for y, z in profile_yz]
    b = [bm.verts.new((x1, y, z)) for y, z in profile_yz]
    faces = [bm.faces.new(a), bm.faces.new(b[::-1])]
    n = len(a)
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new([a[i], a[j], b[j], b[i]]))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    part.set_mat(faces, key)
    return a + b


def cylinder_x(part, cy, cz, r, x0, x1, key, seg=32, bev=0.0, bev_seg=2):
    bm = part.bm
    res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                                radius1=r, radius2=r, depth=abs(x1 - x0))
    vs = res["verts"]
    m = Matrix.Translation(((x0 + x1) / 2, cy, cz)) @ Matrix.Rotation(math.radians(90), 4, "Y")
    bmesh.ops.transform(bm, matrix=m, verts=vs)
    part.set_mat(faces_of(vs), key)
    if bev:
        rim_edges = [e for e in edges_of(vs) if all(abs(math.hypot(v.co.y - cy, v.co.z - cz) - r) < 1e-4
                                                     for v in e.verts)
                     and abs(e.verts[0].co.x - e.verts[1].co.x) < 1e-6]
        bevel(bm, rim_edges, bev, bev_seg)
    return vs


def arc_band_x(part, cy, cz, r0, r1, a0, a1, x0, x1, key, seg=16):
    """Annular arc (angles in degrees, 0 = +Y, 90 = up) extruded over x0..x1 - a fender lip."""
    bm = part.bm
    rings = []
    for i in range(seg + 1):
        a = math.radians(a0 + (a1 - a0) * i / seg)
        dy, dz = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((x, cy + r * dy, cz + r * dz)) for x, r in
                      ((x0, r0), (x1, r0), (x1, r1), (x0, r1))])
    faces = []
    for i in range(seg):
        A, B = rings[i], rings[i + 1]
        for j in range(4):
            k = (j + 1) % 4
            faces.append(bm.faces.new([A[j], A[k], B[k], B[j]]))
    faces.append(bm.faces.new(rings[0]))
    faces.append(bm.faces.new(rings[-1][::-1]))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    part.set_mat(faces, key)


def revolve_x(part, cy, cz, profile_xr, key, seg=40):
    """Revolve a closed (x, radius) profile around the axis parallel to X through (cy, cz)."""
    bm = part.bm
    rings = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((x, cy + r * ca, cz + r * sa)) for x, r in profile_xr])
    faces = []
    n = len(profile_xr)
    for i in range(seg):
        A, B = rings[i], rings[(i + 1) % seg]
        for j in range(n):
            k = (j + 1) % n
            faces.append(bm.faces.new([A[j], A[k], B[k], B[j]]))
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    part.set_mat(faces, key)


def taper_sides(bm, crease_z, k_up, low_z, k_low, min_abs_x=0.3):
    """Tumblehome above a shoulder crease and a tuck-under below the door: gives the flat
    extrusions a body-side character line in the reflections. The mesh is cut at both heights
    first so the side panels stay planar strips and the crease edges are marked sharp."""
    for z in (crease_z, low_z):
        res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                     plane_co=(0, 0, z), plane_no=(0, 0, 1))
        for e in res["geom_cut"]:
            if isinstance(e, bmesh.types.BMEdge) and all(abs(v.co.x) > min_abs_x for v in e.verts):
                e.smooth = False
    for v in bm.verts:
        x = v.co.x
        if abs(x) < min_abs_x:
            continue
        shift = k_up * max(0.0, v.co.z - crease_z) + k_low * max(0.0, low_z - v.co.z)
        v.co.x = math.copysign(abs(x) - shift, x)


# ------------------------------------------------------------------ truck

class Dims:
    def __init__(self, cfg):
        pv, bed, sh = cfg["preview"], cfg["bed"], cfg["shell"]
        self.rail = bed["rail_height_above_ground"]
        self.bed_len = bed["length_at_rails"]
        self.bed_hw = bed["width_at_rails"] / 2 + 0.004
        self.roof = self.rail + bed["cab_height_above_rails"] + sh["height_offset_from_cab"]
        self.hw = pv["width"] / 2 - 0.025          # body side; fender lips reach full width
        self.R = pv["tire_diameter"] / 2
        self.rim_r = pv["rim_diameter"] / 2
        self.y_ra = -pv["rear_axle_behind_bed_front"]
        self.y_fa = self.y_ra + pv["wheelbase"]
        self.y_tail = -self.bed_len - pv["tailgate_thickness"]
        self.y_rear = self.y_tail - pv["rear_bumper_depth"]
        self.y_front = self.y_rear + pv["overall_length"]
        self.arch_r = self.R + 0.06
        self.arch_z = self.R + 0.025
        self.track_hw = self.hw - 0.14


def build_cab_body(d, mats, col):
    """Front clip + cab lower body as one extruded side profile with a stepped hood/cowl."""
    p = Part("pv_cab_body", mats)
    yb, yf = 0.075, d.y_front
    belt = d.rail - 0.01
    prof = [
        (yb, 0.58), (yf - 0.10, 0.58), (yf - 0.02, 0.70), (yf, 0.80), (yf + 0.01, 1.24),
        (yf - 0.05, 1.325), (yf - 0.40, 1.355), (yf - 1.25, 1.385), (yf - 1.52, 1.395),
        (yf - 1.60, belt - 0.02), (yb + 0.02, belt), (yb, belt - 0.02),
    ]
    vs = prism_x(p, prof, -d.hw, d.hw, "paint")
    bevel(p.bm, edges_of(vs), 0.05, 3)
    taper_sides(p.bm, 1.16, 0.10, 0.74, 0.12)
    ob = p.finish(col)
    return ob


def build_greenhouse(d, mats, col):
    """Cab upper: windshield, 4 side windows (black B-pillar), rear window, painted roof/pillars."""
    p = Part("pv_cab_greenhouse", mats)
    bm = p.bm
    z0, z1 = d.rail - 0.05, d.roof - 0.005
    yf = d.y_front
    ws_base = yf - 1.58
    ws_top = ws_base - 0.80
    hb, ht = d.hw - 0.06, d.hw - 0.20
    y_b = [ws_base, ws_base - 0.17, 1.22, 1.10, 0.23, 0.11]
    y_t = [ws_top, ws_top - 0.06, 1.24, 1.12, 0.30, 0.15]
    keys = ["paint", "glass", "black", "glass", "paint"]
    sides = {}
    for s in (-1, 1):
        bot = [bm.verts.new((s * hb, y, z0)) for y in y_b]
        top = [bm.verts.new((s * ht, y, z1)) for y in y_t]
        sides[s] = (bot, top)
        for i in range(5):
            q = [bot[i], bot[i + 1], top[i + 1], top[i]]
            f = bm.faces.new(q if s > 0 else q[::-1])
            p.set_mat([f], keys[i])
    (bl, tl), (br, tr) = sides[-1], sides[1]
    ws = bm.faces.new([bl[0], br[0], tr[0], tl[0]])
    rw = bm.faces.new([br[-1], bl[-1], tl[-1], tr[-1]])
    roof = bm.faces.new(tl + tr[::-1])
    floor = bm.faces.new(bl[::-1] + br)
    p.set_mat([ws, rw], "glass")
    p.set_mat([roof, floor], "paint")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    upper = [e for e in bm.edges if len(e.link_faces) == 2 and min(v.co.z for v in e.verts) > z0 + 0.01
             and e.link_faces[0].normal.angle(e.link_faces[1].normal) > math.radians(25)]
    bevel(bm, upper, 0.06, 3)
    glass_i = p.idx("glass")
    glass = [f for f in bm.faces if f.material_index == glass_i]
    res = bmesh.ops.inset_individual(bm, faces=glass, thickness=0.028, depth=-0.012, use_even_offset=True)
    p.set_mat(res["faces"], "black")
    return p.finish(col, smooth=30)


def build_bed(d, mats, col):
    p = Part("pv_bed", mats)
    bm = p.bm
    lo = (-d.hw, d.y_tail, 0.66)
    hi = (d.hw, 0.045, d.rail)
    vs = box(p, lo, hi, "paint")
    top = [f for f in faces_of(vs) if f.normal.z > 0.9]
    p.set_mat(top, "liner")
    vert_rear = [e for e in edges_of(vs) if abs(e.verts[0].co.z - e.verts[1].co.z) > 0.1]
    bevel(bm, vert_rear, 0.05, 3)
    tops = [e for e in bm.edges if all(v.co.z > d.rail - 1e-4 for v in e.verts)]
    bevel(bm, tops, 0.012, 1)
    bottoms = [e for e in bm.edges if all(v.co.z < 0.66 + 1e-4 for v in e.verts)]
    bevel(bm, bottoms, 0.03, 2)
    k = max(0.0, (d.hw - d.bed_hw) / (d.rail - 1.16))
    taper_sides(bm, 1.16, k, 0.74, 0.12)
    return p.finish(col)


def build_details(d, mats, col):
    p = Part("pv_details", mats)
    yr, yt, yf = d.y_rear, d.y_tail, d.y_front
    hw, bhw = d.hw, d.bed_hw
    X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
    # Rear: bumper, plate, hitch, tail lights, tailgate seams + handle.
    box(p, (-bhw + 0.01, yr, 0.50), (bhw - 0.01, yt + 0.03, 0.72), "bumper", bev=0.03, seg=2)
    box(p, (-bhw + 0.03, yr - 0.005, 0.69), (bhw - 0.03, yt + 0.02, 0.715), "black", bev=0.006)  # step pad
    box(p, (-0.155, yr - 0.008, 0.535), (0.155, yr + 0.02, 0.675), "plate", bev=0.006)
    box(p, (-0.04, yr - 0.10, 0.42), (0.04, yr + 0.1, 0.49), "black")
    for s in (-1, 1):
        x_out, x_in = s * (bhw + 0.004), s * (bhw - 0.17)
        box(p, (min(x_out, x_in), yt - 0.02, 1.02), (max(x_out, x_in), yt + 0.06, 1.40), "tail", bev=0.012)
        box(p, (min(x_out, x_in) + 0.02, yt - 0.024, 1.25), (max(x_out, x_in) - 0.02, yt - 0.01, 1.30),
            "lens", bev=0.003)
        xs = s * (bhw - 0.18)
        box(p, (xs - 0.003, yt - 0.004, 0.72), (xs + 0.003, yt + 0.01, d.rail - 0.02), "black")
    box(p, (-bhw + 0.18, yt - 0.004, 0.722), (bhw - 0.18, yt + 0.01, 0.728), "black")
    box(p, (-0.13, yt - 0.018, d.rail - 0.10), (0.13, yt + 0.01, d.rail - 0.055), "black", bev=0.008)
    box(p, (-bhw + 0.26, yt - 0.006, 0.80), (bhw - 0.26, yt + 0.01, d.rail - 0.16), "paint", bev=0.02)
    box(p, (-bhw + 0.19, yt - 0.012, d.rail - 0.035), (bhw - 0.19, yt + 0.04, d.rail + 0.004), "paint",
        bev=0.012)  # tailgate cap
    # Front: grille, headlights, bumper, skid.
    box(p, (-0.70, yf - 0.03, 0.80), (0.70, yf + 0.022, 1.20), "black", bev=0.02)
    for i in range(4):
        z = 0.87 + i * 0.08
        box(p, (-0.66, yf + 0.018, z), (0.66, yf + 0.03, z + 0.022), "bumper", bev=0.004)
    for s in (-1, 1):
        x0, x1 = sorted((s * 0.71, s * (hw - 0.02)))
        box(p, (x0, yf - 0.06, 1.06), (x1, yf + 0.018, 1.19), "lens", bev=0.015)
        box(p, (x0, yf - 0.06, 1.02), (x1, yf + 0.016, 1.05), "amber", bev=0.005)
    box(p, (-hw + 0.04, yf - 0.06, 0.50), (hw - 0.04, yf + 0.06, 0.78), "bumper", bev=0.035, seg=2)
    box(p, (-0.55, yf - 0.20, 0.42), (0.55, yf + 0.02, 0.52), "black", bev=0.02)
    # Underbody, running boards, fender lips, door seams, handles, mirrors.
    box(p, (-0.82, yr + 0.15, 0.32), (0.82, yf - 0.25, 0.62), "under")
    for s in (-1, 1):
        x0, x1 = sorted((s * (hw - 0.13), s * (hw + 0.02)))
        box(p, (x0, -0.20, 0.43), (x1, d.y_fa - d.arch_r - 0.06, 0.49), "black", bev=0.015)
        for y_ax, bh in ((d.y_fa, hw), (d.y_ra, bhw)):
            xa, xb = sorted((s * (bh - 0.03), s * (d.hw + 0.025)))
            arc_band_x(p, y_ax, d.arch_z, d.arch_r - 0.005, d.arch_r + 0.03, -4, 184, xa, xb, "black")

        if s > 0:  # wheel-well liners span the whole boolean tunnel so nothing shows through
            for y_ax, bh in ((d.y_fa, hw), (d.y_ra, bhw)):
                arc_band_x(p, y_ax, d.arch_z, d.arch_r - 0.012, d.arch_r - 0.002, -4, 184,
                           -bh + 0.02, bh - 0.02, "under")
        xs = s * (hw + 0.001)
        for yy in (d.y_fa - d.arch_r - 0.09, 1.16, 0.15):
            box(p, (xs - 0.003, yy - 0.003, 0.60), (xs + 0.003, yy + 0.003, d.rail - 0.02), "black")
        for yy in (1.30, 0.32):
            box(p, (xs - 0.012 * (s < 0) - 0.0, yy - 0.14, 1.26), (xs + 0.012 * (s > 0), yy, 1.30), "black",
                bev=0.006)
        my = d.y_front - 1.70
        box(p, (min(s * (hw - 0.02), s * (hw + 0.06)), my - 0.06, 1.42),
            (max(s * (hw - 0.02), s * (hw + 0.06)), my + 0.02, 1.46), "black")
        oriented_box(p, Vector((s * (hw + 0.13), my - 0.04, 1.50)), (X, Y, Z), (0.18, 0.11, 0.24), "paint",
                     bev=0.03)
        oriented_box(p, Vector((s * (hw + 0.13), my - 0.096, 1.50)), (X, Y, Z), (0.15, 0.005, 0.20), "black")
    return p.finish(col, smooth=40)


def build_wheel(d, mats, col, name, y, side):
    p = Part(name, mats)
    w = 0.275
    xo = side * (d.track_hw + w / 2)
    xi = side * (d.track_hw - w / 2)
    x0, x1 = sorted((xi, xo))
    R, rr = d.R, d.rim_r
    ri = rr + 0.012
    prof = [(x0, ri), (x0, R - 0.085), (x0 + 0.012, R - 0.035), (x0 + 0.04, R - 0.006), (x0 + 0.07, R),
            (x1 - 0.07, R), (x1 - 0.04, R - 0.006), (x1 - 0.012, R - 0.035), (x1, R - 0.085), (x1, ri)]
    revolve_x(p, y, d.R, prof, "tire", seg=40)
    face = xo - side * 0.022          # rim lip plane, just inside the sidewall
    rec = xo - side * 0.075           # spoke-gap recess
    a, b = sorted((rec, face))
    cylinder_x(p, y, d.R, rr - 0.005, a - side * 0.0, b, "dark_rim", seg=32)
    lip_a, lip_b = sorted((face - side * 0.035, face + side * 0.004))
    arc_band_x(p, y, d.R, rr - 0.035, rr + 0.012, 0, 360, lip_a, lip_b, "rim", seg=32)
    hub_a, hub_b = sorted((rec, face + side * 0.006))
    cylinder_x(p, y, d.R, 0.085, hub_a, hub_b, "rim", seg=16)
    cylinder_x(p, y, d.R, 0.035, *sorted((face, face + side * 0.012)), "dark_rim", seg=12)
    n_spokes = 6
    for i in range(n_spokes):
        ang = math.radians(90 + i * 360 / n_spokes)
        rad = Vector((0, math.cos(ang), math.sin(ang)))
        tang = Vector((0, -math.sin(ang), math.cos(ang)))
        mid_r = (0.07 + rr - 0.03) / 2
        c = Vector(((face + rec) / 2 + side * 0.012, y, d.R)) + rad * mid_r
        oriented_box(p, c, (Vector((1, 0, 0)), rad, tang), (abs(face - rec) - 0.01, rr - 0.10, 0.055), "rim",
                     bev=0.008)
    return p.finish(col, smooth=40)


def arch_cutter(d, col, name, y, hw):
    p = Part(name, {"black": bpy.data.materials["pv_black_trim"]})
    cylinder_x(p, y, d.arch_z, d.arch_r, -hw - 0.2, hw + 0.2, "black", seg=40)
    ob = p.finish(col, smooth=0)
    ob.hide_render = True
    ob.hide_viewport = True
    return ob


def add_arch(body, cutter):
    mod = body.modifiers.new("arch_" + cutter.name, "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.material_mode = "TRANSFER"
    mod.object = cutter


def build_truck(cfg, collection=None):
    """Create the stand-in truck; returns (objects, dims)."""
    if collection is None:
        collection = bpy.data.collections.new(COLLECTION)
        bpy.context.scene.collection.children.link(collection)
    d = Dims(cfg)
    mats = make_materials(cfg)
    body = build_cab_body(d, mats, collection)
    bed = build_bed(d, mats, collection)
    objs = [body, bed, build_greenhouse(d, mats, collection), build_details(d, mats, collection)]
    fc = arch_cutter(d, collection, "pv_arch_front", d.y_fa, d.hw)
    rc = arch_cutter(d, collection, "pv_arch_rear", d.y_ra, d.hw)
    add_arch(body, fc)
    add_arch(bed, rc)
    for y_ax, tag in ((d.y_fa, "f"), (d.y_ra, "r")):
        for s, sd in ((-1, "l"), (1, "r")):
            objs.append(build_wheel(d, mats, collection, f"pv_wheel_{tag}{sd}", y_ax, s))
    for ob in objs + [fc, rc]:
        ob.location.z -= d.rail
    return objs, d
