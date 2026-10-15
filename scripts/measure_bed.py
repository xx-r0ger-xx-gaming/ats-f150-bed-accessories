"""Measure the reference truck's bed (ray casts) and print / store it as a config/bed.json profile.

  blender --background --factory-startup --python-exit-code 1 --python scripts/measure_bed.py -- \
      [--truck '{"type": "pickup", "source": "reference"}'] [--profile reference_glb] [--write]

--write stores the measured values as profiles.<profile> (other profiles and `active` are kept).
Render-only reference data; nothing here is exported.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bpy  # noqa: E402

from lib.bed import BED_CONFIG, measure  # noqa: E402
from lib.common import load_json, make_parser, repo_path, run_main, script_args  # noqa: E402
from lib.materials import MaterialLibrary  # noqa: E402
from lib.proxy_truck import build_truck  # noqa: E402


def main():
    p = make_parser("Measure the reference truck bed")
    p.add_argument("--truck", default='{"type": "pickup", "source": "reference"}')
    p.add_argument("--profile", default="reference_glb")
    p.add_argument("--write", action="store_true")
    args = p.parse_args(script_args())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    col = bpy.data.collections.new("truck")
    bpy.context.scene.collection.children.link(col)
    info = build_truck(json.loads(args.truck), MaterialLibrary({"base_color": [0.4, 0.4, 0.4, 1.0]}), col)
    prof, fit = measure(info)
    print(json.dumps({"profile": prof, "fit": fit}, indent=1))
    if args.write:
        path = repo_path(BED_CONFIG)
        cfg = load_json(path) if path.is_file() else {"active": args.profile, "profiles": {}}
        old = cfg["profiles"].get(args.profile, {})
        new = {k: v for k, v in old.items() if k.startswith("_")}
        new.update(prof)
        cfg["profiles"][args.profile] = new
        path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        print(f"wrote profiles.{args.profile} to {path}")


if __name__ == "__main__":
    run_main(main)
