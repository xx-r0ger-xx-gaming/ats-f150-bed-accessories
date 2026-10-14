"""Generate tiny original solid-colour placeholder textures (uncompressed 24-bit TGA).

Plain Python, deterministic, no game assets:
  python scripts/make_textures.py --config config/scs_materials.json
Colours come from each role's "texture_rgb" in the config.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.common import PipelineError, load_json, make_parser, repo_path, run_main, script_args  # noqa: E402

SIZE = 32


def write_tga(path, rgb, size=SIZE):
    r, g, b = (max(0, min(255, int(round(c * 255)))) for c in rgb)
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, size, size, 24, 0x20)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + bytes((b, g, r)) * (size * size))


def main():
    p = make_parser("Generate placeholder textures")
    p.add_argument("--config", default="config/scs_materials.json")
    args = p.parse_args(script_args())
    cfg = load_json(args.config)
    out_dir = repo_path(cfg["texture_source_dir"])
    for role, spec in sorted(cfg["roles"].items()):
        if "texture_file" not in spec:
            raise PipelineError(f"role {role}: texture_file missing")
        write_tga(out_dir / spec["texture_file"], spec["texture_rgb"])
        print(f"wrote {out_dir / spec['texture_file']}")
        if "reflection_file" in spec:
            write_tga(out_dir / spec["reflection_file"], spec["reflection_rgb"])
            print(f"wrote {out_dir / spec['reflection_file']}")


run_main(main)
