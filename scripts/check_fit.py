"""Fit check: camper vs truck mesh overlap and gaps (rails, sides, cab, tailgate). Render-only.

  blender --background --factory-startup --python-exit-code 1 --python scripts/check_fit.py -- \
      --variant v1_shell [--variant ...] | --all  [--set key=value ...] [--strict]

Per pose (as render_variants: every "renders" entry of the config):
  overlap   BVH triangle-pair intersections between each camper object and the truck (count + the
            bounding box of the touching camper triangles). Rubber seals / pads are expected to
            touch or be slightly compressed into the rail caps; any rigid part touching is a defect.
  seat      closest approach of the camper's underside to the rail caps (rays up into the camper,
            down onto the truck, across each rail cap): > 0 = floating, < 0 = buried (seals/pads).
  side      outermost camper x at its base minus the truck's rail-cap outer edge (rays) at that
            station: > 0 = overhangs the bed side, < 0 = inset.
  cab       truck cab back minus the camper front (rays toward +Y): the cab gap.
  rear      closed-tailgate outer face minus the camper rear (rays toward +Y from behind): > 0 =
            the camper sticks out behind the tailgate face, < 0 = sits forward of it.
Writes logs/check_fit-<timestamp>.json. --strict exits 1 when a rigid part overlaps the truck.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

from lib.common import PipelineError, make_parser, run_main, script_args, write_run_record  # noqa: E402
from render_variants import all_variants, load_variant, parse_sets, poses_for, stage_models  # noqa: E402

COMPLIANT = ("seal", "pad", "rubber")      # object-name hints for parts allowed to touch the truck


def bvh_of(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    for ob in objs:
        if ob.type != "MESH":
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ob.matrix_world
        base = len(verts)
        verts += [mw @ v.co for v in me.vertices]
        polys += [[base + i for i in p.vertices] for p in me.polygons]
        ev.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys, epsilon=0.0), verts, polys


def hit(tree, o, d, dist=10.0):
    loc, *_ = tree.ray_cast(Vector(o), Vector(d), dist)
    return loc


def check_pose(name, sets):
    cfg, info, objs = stage_models(name, sets)
    bed = info["bed"]
    bpy.context.view_layer.update()
    truck, tv, tp = bvh_of(info["objects"])
    camper, _, _ = bvh_of(objs)
    out = {"variant": name, "set": sets, "bed_profile": bed.name, "overlap": [], "seat": [], "side": [],
           "cab": [], "rear": []}
    # ---- overlaps, per camper object
    for ob in objs:
        if ob.type != "MESH" or not len(ob.data.polygons):
            continue
        t, vs, ps = bvh_of([ob])
        pairs = t.overlap(truck)
        if pairs:
            cs = [sum((vs[i] for i in ps[a]), Vector()) / len(ps[a]) for a, _ in pairs]
            clusters = {}
            for c in cs:                                   # coarse 10 cm cells, to locate contacts
                key = tuple(round(c[k] / 0.1) for k in range(3))
                clusters[key] = clusters.get(key, 0) + 1
            lo = [round(min(c[k] for c in cs), 3) for k in range(3)]
            hi = [round(max(c[k] for c in cs), 3) for k in range(3)]
            top = sorted(clusters.items(), key=lambda kv: -kv[1])[:6]
            out["overlap"].append({"object": ob.name, "pairs": len(pairs), "bbox": [lo, hi],
                                   "cells": [([round(k * 0.1, 1) for k in key], n) for key, n in top],
                                   "compliant": any(h in ob.name.lower() for h in COMPLIANT)})
    y0, y1 = bed["front_wall_inner_y"] - 0.05, bed["bed_side_rear_y"] + 0.05
    stations = [y0 + (y1 - y0) * i / 8 for i in range(9)]
    # ---- seat + side, along both rails: lowest camper surface over the rail cap, and its flank
    for y in stations:
        for sx in (-1, 1):
            xs = [bed["rail_inner_hw"] - 0.02 + 0.005 * i
                  for i in range(int((bed.rail_outer_hw_at(y) + 0.05 - bed["rail_inner_hw"]) / 0.005))]
            low = []                                       # (gap to the truck below, camper z, x)
            for x in xs:
                c = hit(camper, (sx * x, y, bed["rail_cap_z"] - 0.03), (0, 0, 1), 0.15)
                if c is not None:
                    t = hit(truck, (sx * x, y, c.z + 0.05), (0, 0, -1), 0.4)
                    if t is not None:
                        low.append((c.z - t.z, c.z, x))
            if not low:
                continue
            g, cz, x = min(low)                             # closest approach across the rail cap
            out["seat"].append({"x": round(sx * x, 3), "y": round(y, 3), "camper_z": round(cz, 4),
                                "gap": round(g, 4)})
            cz = min(v[1] for v in low)
            zs = cz + 0.012
            cs = hit(camper, (sx * 3.0, y, zs), (-sx, 0, 0), 3.0)
            # truck rail-cap outer edge at this station: walk outward until the cap rolls off
            xe = bed["rail_inner_hw"] + 0.03
            while xe < 1.2:
                d = hit(truck, (sx * xe, y, 1.0), (0, 0, -1), 2.0)
                if d is None or d.z < bed["rail_cap_z"] - 0.006:
                    break
                xe += 0.001
            if cs is not None:
                out["side"].append({"y": round(y, 3), "side": sx, "z": round(zs, 3), "camper_x": round(abs(cs.x), 4),
                                    "rail_edge": round(xe, 4), "overhang": round(abs(cs.x) - xe, 4)})
    # ---- cab gap (centre and both sides, several heights below the cab roof)
    for x in (0.0, -0.45, 0.45, -0.75, 0.75):
        for z in (0.05, 0.15, 0.30, 0.45):
            if z > bed["cab_roof_z"] - 0.06:
                continue
            c = hit(camper, (x, 3.0, z), (0, -1, 0), 4.0)
            if c is None or c.y < -0.5:
                continue
            t = hit(truck, (x, c.y - 0.002, z), (0, 1, 0), 1.0)
            out["cab"].append({"x": x, "z": z, "camper_y": round(c.y, 4),
                               "gap": round(t.y - c.y, 4) if t is not None else None})
    # ---- rear vs the closed tailgate face (skipped when the gate is removed)
    if info.get("tailgate", "closed") == "closed":
        for x in (0.0, -0.4, 0.4, -0.7, 0.7, -0.82, 0.82):
            tgs = [hit(truck, (x, -4.0, bed["tailgate_top_z"] - dz), (0, 1, 0), 3.0) for dz in (0.012, 0.02, 0.03)]
            tgs = [h for h in tgs if h is not None]
            tg = min(tgs, key=lambda h: h.y) if tgs else None      # outermost face just under the top
            for z in (0.03, 0.10, 0.25):
                c = hit(camper, (x, -4.0, z), (0, 1, 0), 3.0)
                if c is None or c.y > -1.0 or tg is None:
                    continue
                out["rear"].append({"x": x, "z": z, "camper_y": round(c.y, 4), "tailgate_y": round(tg.y, 4),
                                    "overhang": round(tg.y - c.y, 4)})
    return out


def summarize(r):
    def rng(key, field):
        v = [e[field] for e in r[key] if e.get(field) is not None]
        return f"{min(v):+.3f}..{max(v):+.3f}" if v else "n/a"
    rigid = [o for o in r["overlap"] if not o["compliant"]]
    soft = [o for o in r["overlap"] if o["compliant"]]
    lines = [f"== {r['variant']} {r['set'] or ''} (bed {r['bed_profile']})",
             f"  overlap rigid: {len(rigid)} object(s) {[(o['object'], o['pairs'], o['cells']) for o in rigid]}",
             f"  overlap compliant (seal/pad): {[(o['object'], o['pairs']) for o in soft]}",
             f"  seat gap {rng('seat', 'gap')}   side overhang {rng('side', 'overhang')}   "
             f"cab gap {rng('cab', 'gap')}   rear overhang {rng('rear', 'overhang')}"]
    return "\n".join(lines)


def main():
    p = make_parser("Camper/truck fit check")
    p.add_argument("--variant", action="append", default=[])
    p.add_argument("--all", action="store_true")
    p.add_argument("--set", dest="sets", action="append", default=[])
    p.add_argument("--strict", action="store_true")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(script_args())
    names = all_variants() if args.all else args.variant
    if not names:
        raise PipelineError("give --variant NAME or --all")
    cli = parse_sets(args.sets)
    results = []
    for n in names:
        poses = [{"suffix": "", "set": cli}] if cli else poses_for(load_variant(n))
        for pose in poses:
            r = check_pose(n, pose["set"])
            results.append(r)
            print(summarize(r))
            if args.verbose:
                for key in ("seat", "side", "cab", "rear"):
                    for e in r[key]:
                        print(f"    {key} {e}")
    rec = write_run_record("check_fit", {"blender": bpy.app.version_string, "results": results})
    print(f"record {rec}")
    if args.strict and any(not o["compliant"] for r in results for o in r["overlap"]):
        raise PipelineError("rigid camper parts intersect the truck (see above)")


if __name__ == "__main__":
    run_main(main)
