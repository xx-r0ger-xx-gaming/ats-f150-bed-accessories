"""Preflight checks before a pipeline stage. Prints a pass/fail table, writes a run record.

  python scripts/preflight.py --stage {build,convert,package,deploy}

Stages are cumulative in the order build < convert < package < deploy (each includes the
earlier checks that its inputs depend on, except that the ATS mod dir is only checked for deploy).
Exit code 1 if any check fails.
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.common import (  # noqa: E402
    PipelineError, REPO_ROOT, load_json, make_parser, repo_path, run_main, script_args,
    sha256_file, write_run_record,
)

STAGES = ["build", "convert", "package", "deploy"]
REQUIRED_KEYS = ["machine", "blender_exe", "blender_expected_version", "scs_blender_tools_zip",
                 "conversion_tools_dir", "game_archive_extractor_exe", "ats_mod_dir", "ats_game_log"]
# keys that must be set (not the <you> placeholder) per stage
STAGE_KEYS = {"build": ["blender_exe", "blender_expected_version", "scs_blender_tools_zip"],
              "convert": ["conversion_tools_dir"],
              "package": [],
              "deploy": ["ats_mod_dir"]}


class Table:
    def __init__(self):
        self.rows = []

    def add(self, name, status, detail=""):
        self.rows.append({"check": name, "status": status, "detail": detail})

    @property
    def failed(self):
        return any(r["status"] == "FAIL" for r in self.rows)

    def print(self):
        w = max(len(r["check"]) for r in self.rows)
        for r in self.rows:
            print(f"  {r['status']:<4}  {r['check']:<{w}}  {r['detail']}")


def blender_version(exe):
    try:
        p = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    m = re.search(r"Blender\s+(\d+\.\d+\.\d+)", p.stdout)
    return (m.group(1) if m else None), (p.stdout.strip().splitlines() or [""])[0]


def main():
    ap = make_parser("Preflight checks for a pipeline stage")
    ap.add_argument("--stage", choices=STAGES, required=True)
    ap.add_argument("--config", default="config/tools.local.json")
    args = ap.parse_args(script_args())
    upto = STAGES.index(args.stage)
    t = Table()

    v = sys.version_info
    t.add("python >= 3.10", "PASS" if v >= (3, 10) else "FAIL", sys.version.split()[0])

    cfg_path = repo_path(args.config)
    cfg = None
    if not cfg_path.is_file():
        t.add("tools.local.json exists", "FAIL", f"{cfg_path} (copy config/tools.example.json)")
    else:
        cfg = load_json(cfg_path)
        t.add("tools.local.json exists", "PASS", str(cfg_path.relative_to(REPO_ROOT)))
        missing = [k for k in REQUIRED_KEYS if k not in cfg]
        t.add("tools.local.json keys", "FAIL" if missing else "PASS",
              f"missing: {missing}" if missing else f"{len(REQUIRED_KEYS)} keys")

    def val(key):
        v_ = (cfg or {}).get(key)
        return None if not v_ or "<you>" in str(v_) else v_

    if cfg is not None:
        need = [k for s in STAGES[:upto + 1] for k in STAGE_KEYS[s]]
        for key in need:
            if val(key) is None:
                t.add(f"config {key} set", "FAIL", "unset or still the <you> placeholder")

        if "build" in STAGES[:upto + 1] and val("blender_exe"):
            exe = repo_path(cfg["blender_exe"])
            if not exe.is_file():
                t.add("blender executable", "FAIL", f"not found: {exe}")
            else:
                found, line = blender_version(exe)
                want = cfg.get("blender_expected_version")
                ok = found is not None and found == want
                t.add("blender version", "PASS" if ok else "FAIL", f"{found or line} (expected {want})")
        if val("scs_blender_tools_zip"):
            z = repo_path(cfg["scs_blender_tools_zip"])
            t.add("SCS Blender Tools zip", "PASS" if z.is_file() else "FAIL",
                  f"sha256 {sha256_file(z)[:16]}..." if z.is_file() else f"not found: {z}")
        if upto >= 1 and val("conversion_tools_dir"):
            d = repo_path(cfg["conversion_tools_dir"])
            ok = (d / "convert.cmd").is_file() and (d / "base").is_dir()
            t.add("conversion tools (convert.cmd)", "PASS" if ok else "FAIL",
                  str(d) if ok else f"convert.cmd/base missing in {d}")
        if upto >= 2:
            ok = (REPO_ROOT / "src" / "mod" / "manifest.sii").is_file()
            t.add("src/mod/manifest.sii", "PASS" if ok else "FAIL")
        if upto >= 3 and val("ats_mod_dir"):
            d = Path(cfg["ats_mod_dir"])
            t.add("ATS mod dir exists", "PASS" if d.is_dir() else "FAIL", str(d))
            log = cfg.get("ats_game_log")
            t.add("ATS game.log.txt", "PASS" if log and Path(log).is_file() else "WARN",
                  str(log) + " (appears after first game launch)")
        gaming = cfg.get("machine") == "gaming-pc"
        if args.stage == "deploy" and not gaming:
            t.add("machine is gaming-pc", "WARN", f"machine={cfg.get('machine')}; deploy is meant for the gaming PC")

    print(f"Preflight stage={args.stage}")
    t.print()
    rec = write_run_record("preflight", {"stage": args.stage, "checks": t.rows,
                                         "result": "fail" if t.failed else "pass"})
    print(f"record: {rec.relative_to(REPO_ROOT)}")
    if t.failed:
        raise PipelineError("preflight failed")


if __name__ == "__main__":
    run_main(main)
