"""Shared bed dimensions: the ONE source every bed-mounted variant fits its footprint to.

config/bed.json holds named bed profiles in the variant frame (metres; origin = rail-top contact
plane, centred, at the bed front wall; +Y toward the cab; +Z up). `active` picks the profile all
variants use; switching it (e.g. to the measured in-game F-150) is the single change that refits
every camper. A variant config may pin another profile with "bed_profile" (or --set bed_profile=..).

The special profile name "truck" derives the dimensions from the rendered truck's own TruckInfo
(coarse: constant rail width, flat tailgate) - the fallback for the procedural stand-in.

measure(info) ray-casts the loaded reference truck and returns a full profile dict; it is what
scripts/measure_bed.py writes into config/bed.json, and the runner uses it to check that the active
profile still matches the reference model (see check_against_truck).
"""
import math

from lib.common import PipelineError, load_json

BED_CONFIG = "config/bed.json"

# keys every profile must provide (all metres, variant frame)
REQUIRED = (
    "rail_top_z", "rail_cap_z", "rail_inner_hw", "rail_outer_hw_front", "rail_outer_hw_rear",
    "rail_outer_y_front", "rail_outer_y_rear", "bed_inner_hw", "bed_floor_z", "bed_floor_rib_z", "bed_inner_rear_y",
    "wheelhouse_inner_hw", "wheelhouse_top_z", "wheelhouse_front_y", "wheelhouse_rear_y",
    "front_wall_inner_y", "front_wall_outer_y", "front_wall_top_z", "cab_back_y", "cab_back_lean",
    "cab_roof_z", "bed_side_rear_y", "tailgate_top_z", "tailgate_face_y", "tailgate_face_bow",
)


class Bed(dict):
    """A bed profile plus the derived shapes variants need. All values in the variant frame."""

    @property
    def name(self):
        return self.get("_name", "?")

    def rail_outer_hw_at(self, y):
        """Outer edge of the flat rail-cap top at station y (linear taper front -> rear)."""
        y0, y1 = self["rail_outer_y_front"], self["rail_outer_y_rear"]
        t = (y - y0) / (y1 - y0) if y1 != y0 else 0.0
        return self["rail_outer_hw_front"] + (self["rail_outer_hw_rear"] - self["rail_outer_hw_front"]) * t

    def rail_mid_hw_at(self, y):
        return 0.5 * (self["rail_inner_hw"] + self.rail_outer_hw_at(y))

    def rail_taper(self):
        """Half-width lost per metre toward the rear (d hw / d(-y))."""
        return ((self["rail_outer_hw_front"] - self["rail_outer_hw_rear"])
                / (self["rail_outer_y_front"] - self["rail_outer_y_rear"]))

    def tailgate_face_at(self, x):
        """Closed tailgate outer face (y) at lateral offset x: parabola, centre most rearward;
        tailgate_face_bow = how far forward the face is at x = rail_inner_hw."""
        k = self["tailgate_face_bow"] / self["rail_inner_hw"] ** 2
        return self["tailgate_face_y"] + k * x * x

    def cab_back_at(self, z):
        """Cab back wall (y) at height z on the centreline (it leans forward with height)."""
        return self["cab_back_y"] + self["cab_back_lean"] * z

    def footprint(self, cab_gap=0.04, seal_min=0.012, front_clearance=0.004):
        """Where a full-bed hard camper (cap, canopy, pop-top base) sits, per the measured bed:

        base_z    underside height: on the rails with at least seal_min for a rail seal, and clear
                  of a raised bed front wall (front_clearance above its top);
        y_front   front face, cab_gap behind the cab back at base_z (lean with cab_back_lean);
        y_rear    rear CORNERS on the closed tailgate's outer face (where they meet the rail edge);
        hw_front, hw_rear  half widths flush with the rail-cap outer edge at y_front / y_rear;
        bow       how far the tailgate face (and so a flush rear face) bows rearward at the centre
                  relative to those corners (rear_bow_at(x) gives it across the width)."""
        base_z = max(self["rail_top_z"] + seal_min, self["front_wall_top_z"] + front_clearance)
        y_front = self.cab_back_at(base_z) - cab_gap
        hw_r = self.rail_outer_hw_at(self["tailgate_face_y"])
        for _ in range(6):                               # corner on the face (converges fast)
            y_rear = self.tailgate_face_at(hw_r)
            hw_r = self.rail_outer_hw_at(y_rear)
        return {"base_z": base_z, "y_front": y_front, "y_rear": y_rear, "cab_gap": cab_gap,
                "hw_front": self.rail_outer_hw_at(y_front), "hw_rear": hw_r,
                "bow": self.tailgate_face_at(hw_r) - self.tailgate_face_at(0.0)}

    def rear_bow_at(self, x, fp):
        """Rearward offset of a tailgate-flush rear face at x, relative to its corners (>= 0 inside)."""
        return self.tailgate_face_at(fp["hw_rear"]) - self.tailgate_face_at(x)

    def summary(self):
        return (f"bed '{self.name}': rail z {self['rail_top_z']:+.3f}, rail outer hw "
                f"{self['rail_outer_hw_front']:.3f}->{self['rail_outer_hw_rear']:.3f}, inner hw "
                f"{self['bed_inner_hw']:.3f}, front wall {self['front_wall_inner_y']:+.3f}/"
                f"{self['front_wall_outer_y']:+.3f} top {self['front_wall_top_z']:+.3f}, cab back "
                f"{self['cab_back_y']:+.3f} (+{self['cab_back_lean']:.3f}/m), tailgate face "
                f"{self['tailgate_face_y']:+.3f} (bow {self['tailgate_face_bow']:.3f}), roof "
                f"{self['cab_roof_z']:+.3f}")


def _from_truck_info(ti):
    """Coarse profile from a TruckInfo (procedural truck fallback)."""
    floor = ti.get("bed_floor_z", -0.52)
    return {
        "_name": "truck", "truck_source": ti.get("source", "procedural"),
        "rail_top_z": 0.0, "rail_cap_z": 0.0, "rail_inner_hw": ti["bed_inner_hw"],
        "rail_outer_hw_front": ti["rail_outer_hw"], "rail_outer_hw_rear": ti["rail_outer_hw"],
        "rail_outer_y_front": 0.0, "rail_outer_y_rear": ti["tailgate_y"],
        "bed_inner_hw": ti["bed_inner_hw"], "bed_floor_z": floor, "bed_floor_rib_z": floor,
        "bed_inner_rear_y": ti.get("bed_inner_rear_y", ti["tailgate_y"] + 0.06),
        "wheelhouse_inner_hw": ti["bed_inner_hw"] - 0.22, "wheelhouse_top_z": floor + 0.26,
        "wheelhouse_front_y": ti["rear_axle_y"] + 0.45, "wheelhouse_rear_y": ti["rear_axle_y"] - 0.45,
        "front_wall_inner_y": 0.0, "front_wall_outer_y": max(ti["cab_back_y"] - 0.04, 0.0),
        "front_wall_top_z": 0.0, "cab_back_y": ti["cab_back_y"], "cab_back_lean": 0.0,
        "cab_roof_z": ti["roof_z"], "bed_side_rear_y": ti["tailgate_y"], "tailgate_top_z": 0.0,
        "tailgate_face_y": ti["tailgate_y"], "tailgate_face_bow": 0.0,
    }


def load_bed(truck_info, profile=None):
    """Return the Bed for this render: `profile` (or config/bed.json `active`)."""
    cfg = load_json(BED_CONFIG)
    name = profile or cfg.get("active")
    if not name:
        raise PipelineError(f"{BED_CONFIG}: no 'active' profile")
    if name == "truck":
        return Bed(_from_truck_info(truck_info))
    profiles = cfg.get("profiles", {})
    if name not in profiles:
        raise PipelineError(f"{BED_CONFIG}: unknown bed profile '{name}' (have {', '.join(profiles)})")
    p = {k: v for k, v in profiles[name].items()}
    missing = [k for k in REQUIRED if not isinstance(p.get(k), (int, float))]
    if missing:
        raise PipelineError(f"{BED_CONFIG}: profile '{name}' has no numeric value for {', '.join(missing)}"
                            f" (fill it from a measurement before making it active)")
    p["_name"] = name
    bed = Bed(p)
    src = truck_info.get("source", "procedural")
    if p.get("truck_source") and p["truck_source"] != src:
        print(f"[bed] WARNING: profile '{name}' was measured on '{p['truck_source']}', rendering on the "
              f"'{src}' truck; campers follow the profile, so they will not sit exactly on this truck")
    return bed


# ------------------------------------------------------------------ measurement (needs bpy)

def measure(info):
    """Ray-cast the loaded truck (variant frame, mount at the origin) and return a profile dict."""
    import bpy

    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    scene = bpy.context.scene

    def ray(o, d):
        hit, loc, *_ = scene.ray_cast(dg, o, d, distance=20.0)
        return loc if hit else None

    def down(x, y, z0=3.0):
        h = ray((x, y, z0), (0, 0, -1))
        return h.z if h is not None else -9.0

    def median(v):
        v = sorted(v)
        return v[len(v) // 2]

    floor = info["bed_floor_z"]
    inner_hw = info["bed_inner_hw"]
    # rail cap: inner lip edge and the flat cap height, sampled along the bed
    stations = [-0.05 - 0.1 * i for i in range(17)]          # y = -0.05 .. -1.65
    lips, caps, tops = [], [], []
    for y in stations:
        x = inner_hw - 0.06
        while x < inner_hw + 0.06 and down(x, y) < -0.05:
            x += 0.001
        lips.append(x)
        prof = [down(x + 0.001 * i, y) for i in range(5, 60)]
        caps.append(median(prof))
        tops.append(max(prof))
    rail_inner = median(lips)
    rail_cap = median(caps)
    rail_top = max(tops)
    # outer edge of the flat cap (where the shoulder starts rolling down), per station; linear fit
    outer = []
    for y in stations:
        x = rail_inner + 0.03
        while x < 1.2 and down(x, y) > rail_cap - 0.006:
            x += 0.001
        outer.append((y, x))
    # the edge narrows slightly faster toward the rear (concave): the front-to-rear chord never
    # overhangs it, so planar camper sides fitted to the chord stay on the cap (max inset = resid)
    (ya, xa), (yb, xb) = outer[0], outer[-1]
    b = (xa - xb) / (ya - yb)
    a = xa - b * ya
    y_f, y_r = 0.0, yb
    resid = max(abs(x - (a + b * y)) for y, x in outer)
    # floor ribs: highest floor surface between the wheel housings
    rib = max(down(0.02 * i, -0.1 - 0.05 * j) for i in range(-25, 26) for j in range(31))
    # wheel housings (inside the bed, above the floor)
    wh = []
    xmax = rail_inner - 0.06
    for j in range(0, 121):
        y = info["rear_axle_y"] + 0.60 - 0.01 * j
        x = 0.30
        while x < xmax and down(x, y) < floor + 0.05:
            x += 0.002
        if x < xmax:
            wh.append((y, x, max(down(xx / 1000, y) for xx in range(int(x * 1000), int(xmax * 1000), 4))))
    if not wh:
        raise PipelineError("bed measure: wheel housings not found")
    # front bed wall: inner face, top, outer face (centreline)
    fw_in = median([ray((0.0, -0.5, z), (0, 1, 0)).y for z in (-0.40, -0.35, -0.30, -0.25, -0.20, -0.15)])
    tops = [(down(0.0, fw_in + 0.002 * i), fw_in + 0.002 * i) for i in range(1, 30)]
    fw_top, y = max(tops)
    while down(0.0, y) > fw_top - 0.01:
        y += 0.0005
    fw_out = y
    # cab back: horizontal rays toward the cab from inside the gap, line fit y = c0 + lean * z
    cz = [0.03 + 0.02 * i for i in range(21)]                 # 0.03 .. 0.43
    cy = [ray((0.0, fw_out + 0.002, z), (0, 1, 0)).y for z in cz]
    mz, mcy = sum(cz) / len(cz), sum(cy) / len(cy)
    lean = sum((z - mz) * (q - mcy) for z, q in zip(cz, cy)) / sum((z - mz) ** 2 for z in cz)
    cab0 = mcy - lean * mz
    # tailgate: top height and outer face (just under its top edge), parabola y = yc + k x^2
    tg_top = median([down(x, info["bed_inner_rear_y"] - 0.06) for x in (-0.4, -0.2, 0.0, 0.2, 0.4)])
    pts = []
    for i in range(0, 16):
        x = 0.05 * i
        ys = [ray((x, -4.0, tg_top - dz), (0, 1, 0)) for dz in (0.012, 0.02, 0.03)]
        ys = [h.y for h in ys if h is not None]
        if ys:
            pts.append((x * x, min(ys)))
    mu = sum(u for u, _ in pts) / len(pts)
    mv = sum(v for _, v in pts) / len(pts)
    k = sum((u - mu) * (v - mv) for u, v in pts) / sum((u - mu) ** 2 for u, _ in pts)
    yc = mv - k * mu
    tg_resid = max(abs(v - (yc + k * u)) for u, v in pts)
    # rear end of the bed sides at rail height (tail-lamp tops), at the rail centre line
    xr = 0.5 * (rail_inner + a + b * y_r)
    side_rear = ray((xr, -4.0, rail_cap - 0.03), (0, 1, 0)).y
    prof = {
        "truck_source": info.get("source", "procedural"),
        "rail_top_z": round(rail_top, 4), "rail_cap_z": round(rail_cap, 4),
        "rail_inner_hw": round(rail_inner, 4),
        "rail_outer_hw_front": round(a + b * y_f, 4), "rail_outer_hw_rear": round(a + b * y_r, 4),
        "rail_outer_y_front": y_f, "rail_outer_y_rear": round(y_r, 4),
        "bed_inner_hw": round(inner_hw, 4), "bed_floor_z": round(floor, 4), "bed_floor_rib_z": round(rib, 4),
        "bed_inner_rear_y": round(info["bed_inner_rear_y"], 4),
        "wheelhouse_inner_hw": round(min(x for _, x, _ in wh), 4),
        "wheelhouse_top_z": round(max(z for _, _, z in wh), 4),
        "wheelhouse_front_y": round(max(y for y, _, _ in wh), 4),
        "wheelhouse_rear_y": round(min(y for y, _, _ in wh), 4),
        "front_wall_inner_y": round(fw_in, 4), "front_wall_outer_y": round(fw_out, 4),
        "front_wall_top_z": round(fw_top, 4),
        "cab_back_y": round(cab0, 4), "cab_back_lean": round(lean, 4),
        "cab_roof_z": round(info["roof_z"], 4), "bed_side_rear_y": round(side_rear, 4),
        "tailgate_top_z": round(tg_top, 4), "tailgate_face_y": round(yc, 4),
        "tailgate_face_bow": round(k * rail_inner ** 2, 4),
    }
    fit = {"rail_outer_fit_max_resid": round(resid, 4), "tailgate_fit_max_resid": round(tg_resid, 4),
           "rail_outer_samples": [(round(y, 3), round(x, 4)) for y, x in outer]}
    return prof, fit


# tolerance for "the active profile still describes the loaded reference model"
CHECK_KEYS = ("rail_top_z", "bed_inner_hw", "bed_floor_z", "bed_inner_rear_y", "cab_roof_z")


def check_against_truck(bed, info, tol=0.006):
    """Cheap consistency check (TruckInfo values only) when the profile was measured on this truck."""
    if bed.get("truck_source") != info.get("source") or bed.name == "truck":
        return []
    ref = {"rail_top_z": 0.0, "bed_inner_hw": info["bed_inner_hw"], "bed_floor_z": info.get("bed_floor_z"),
           "bed_inner_rear_y": info.get("bed_inner_rear_y"), "cab_roof_z": info["roof_z"]}
    bad = [f"{k} profile {bed[k]:+.4f} vs truck {ref[k]:+.4f}" for k in CHECK_KEYS
           if ref.get(k) is not None and not math.isclose(bed[k], ref[k], abs_tol=tol)]
    if bad:
        raise PipelineError(f"bed profile '{bed.name}' no longer matches the {info.get('source')} truck "
                            f"({'; '.join(bad)}); re-run scripts/measure_bed.py --write")
    return bad
