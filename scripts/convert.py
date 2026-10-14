"""Convert SCS intermediate files (build/mid) with SCS Conversion Tools 2.21.

  python scripts/convert.py [--mid build/mid] [--src-mod src/mod] [--output build/converted]

Documented layout (modding.scssoft.com/wiki/Documentation/Tools/Conversion_Tools, checked
against the 2.21 zip): input goes in <tools>/base, convert.cmd -> bin/win_x64/_convert.bat
runs `resconvert -update -root base`, output lands in <tools>/rsrc/base/@cache and the log
in <tools>/mass_convert.log. convert.cmd only launches bin/win_x64/_convert.bat via `start /wait` in a new console
(uncapturable, hangs on `pause` after failures), so this script runs _convert.bat directly
from the same directory and captures its output plus mass_convert.log.

To never touch the shared tool directory, the tools are copied into a project staging area
(build/convert_stage/ct) and run there. The stock `base` content shipped with the tools
(effect defs) also gets converted into @cache; a one-time baseline run of an unmodified copy
is used to exclude those SCS-owned files from build/converted (they must never be shipped).
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.common import (  # noqa: E402
    LOG_DIR, PipelineError, REPO_ROOT, ensure_inside, inventory, load_tools_config, make_parser,
    repo_path, run_main, script_args, sha256_file, sha256_json, write_run_record,
)
from lib.fsutil import copy_tree, safe_rmtree  # noqa: E402

ERROR_RE = re.compile(r"\b(error|fatal|exception)\b", re.I)
OK_RE = re.compile(r"\b0\s+errors?\b|no errors", re.I)
WARN_RE = re.compile(r"\bwarning\b", re.I)
# input extension -> converted extension that must appear if any input of that kind exists
EXPECT = {".pim": ".pmg", ".pic": ".pmc", ".pia": ".pma"}


def run_convert(ct_dir, timeout):
    """Run the tool's real batch (what convert.cmd launches) with captured output.

    convert.cmd itself only does `start /wait _convert.bat` in a NEW console, which cannot be
    captured and hangs forever on the batch's own `pause` after a failure. _convert.bat is
    the documented workhorse, so it is run directly from its own directory (same as convert.cmd).
    NoDefaultCurrentDirectoryInExePath is cleared because the batch relies on cmd finding
    resconvert.exe in the current directory (verified: with it set, every run fails 9009).
    """
    if sys.platform != "win32":
        raise PipelineError("the conversion tools need Windows (or run them under Wine yourself)")
    env = {k: v for k, v in os.environ.items() if k.upper() != "NODEFAULTCURRENTDIRECTORYINEXEPATH"}
    cmd = ["cmd", "/c", "_convert.bat"]
    try:
        p = subprocess.run(cmd, cwd=ct_dir / "bin" / "win_x64", env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise PipelineError(f"conversion timed out after {timeout}s") from e
    log = ct_dir / "mass_convert.log"
    log_text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    return cmd, p.returncode, p.stdout or "", p.stderr or "", log_text


def scan_log(*texts):
    errors, warnings = [], 0
    for text in texts:
        for line in text.splitlines():
            if ERROR_RE.search(line) and not OK_RE.search(line):
                errors.append(line.strip())
            elif WARN_RE.search(line):
                warnings += 1
    return errors, warnings


def stage_tools(tools_dir, ct_dir, work_root):
    safe_rmtree(ct_dir, work_root)
    shutil.copytree(tools_dir, ct_dir)
    # Fresh start: no stale output or log carried over from the source tool dir.
    safe_rmtree(ct_dir / "rsrc", work_root)
    (ct_dir / "rsrc").mkdir()
    (ct_dir / "mass_convert.log").unlink(missing_ok=True)


def cache_files(ct_dir):
    cache = ct_dir / "rsrc" / "base" / "@cache"
    if not cache.is_dir():
        return cache, {}
    return cache, {i["path"]: i["sha256"] for i in inventory(cache)}


def baseline(tools_dir, stage, work_root, timeout, fingerprint):
    path = work_root / "convert_baseline.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("fingerprint") == fingerprint:
            return data["files"]
    print("[convert] computing baseline (stock tool content) ...")
    ct = stage / "ct_baseline"
    stage_tools(tools_dir, ct, work_root)
    _cmd, code, out, err, log = run_convert(ct, timeout)
    errs, _ = scan_log(out, err, log)
    if code != 0 or errs:
        raise PipelineError(f"baseline conversion failed (exit {code}): {errs[:3]}")
    _cache, files = cache_files(ct)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fingerprint": fingerprint, "files": files}, indent=1, sort_keys=True),
                    encoding="utf-8")
    safe_rmtree(ct, work_root)
    return files


def main():
    ap = make_parser("Convert build/mid with SCS Conversion Tools 2.21 in a project staging area")
    ap.add_argument("--mid", default="build/mid", help="SCS intermediate files from export_scs.py")
    ap.add_argument("--src-mod", default="src/mod", help="hand-authored mod files (def/ is staged)")
    ap.add_argument("--stage-dir", default="build/convert_stage")
    ap.add_argument("--output", default="build/converted")
    ap.add_argument("--work-root", default="build", help="the only tree this script may delete in")
    ap.add_argument("--tools-dir", help="override conversion_tools_dir from tools.local.json")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--no-baseline", action="store_true",
                    help="do not exclude stock tool content from the output (NOT releasable)")
    ap.add_argument("--dry-run", action="store_true", help="stage only; do not run convert.cmd")
    args = ap.parse_args(script_args())

    work_root = repo_path(args.work_root).resolve()
    stage = ensure_inside(repo_path(args.stage_dir), work_root)
    output = ensure_inside(repo_path(args.output), work_root)
    mid = repo_path(args.mid)
    src_mod = repo_path(args.src_mod)

    if args.tools_dir:
        tools_dir = repo_path(args.tools_dir)
    else:
        tools_dir = repo_path(load_tools_config(("conversion_tools_dir",))["conversion_tools_dir"])
    for rel in ("convert.cmd", "bin/win_x64/_convert.bat", "base"):
        if not (tools_dir / rel).exists():
            raise PipelineError(f"conversion tools incomplete, missing {rel} in {tools_dir}")
    if not mid.is_dir() or not any(mid.rglob("*")):
        raise PipelineError(f"missing/empty intermediate dir: {mid} (run export_scs.py first)")

    fingerprint = sha256_json({"base": inventory(tools_dir / "base"),
                               "cmd": sha256_file(tools_dir / "convert.cmd")})
    started = datetime.datetime.now()
    print(f"[convert] tools={tools_dir}\n[convert] mid={mid}")

    base_files = {}
    if not args.no_baseline and not args.dry_run:
        base_files = baseline(tools_dir, stage, work_root, args.timeout, fingerprint)

    ct = stage / "ct"
    stage_tools(tools_dir, ct, work_root)
    staged = copy_tree(mid, ct / "base")
    if (src_mod / "def").is_dir():
        # UNVERIFIED: whether resconvert passes plain def/*.sii into @cache. package.py also
        # overlays src/mod/def directly, so the packaged result is the same either way.
        staged += copy_tree(src_mod / "def", ct / "base" / "def")
    print(f"[convert] staged {len(staged)} files into {ct / 'base'}")
    if args.dry_run:
        print("[convert] --dry-run: stopping before convert.cmd")
        return

    cmd, code, out, err, mlog = run_convert(ct, args.timeout)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"convert-{stamp}.log"
    log_path.write_text(
        f"command: {cmd}\ncwd: {ct}\nexit code: {code}\n\n=== stdout ===\n{out}\n"
        f"=== stderr ===\n{err}\n=== mass_convert.log ===\n{mlog}\n", encoding="utf-8")
    errors, warnings = scan_log(out, err, mlog)
    print(f"[convert] exit={code} errors={len(errors)} warnings={warnings} log={log_path}")

    problems = []
    if code != 0:
        problems.append(f"convert.cmd exit code {code}")
    if not mlog.strip():
        problems.append("mass_convert.log missing/empty (conversion may not have run)")
    problems += [f"log error: {e}" for e in errors[:10]]

    cache, files = cache_files(ct)
    new = {p: h for p, h in files.items() if base_files.get(p) != h}
    if not files:
        problems.append(f"no output at {cache}")
    elif not new:
        problems.append("conversion produced nothing beyond the stock baseline")
    in_exts = {p.suffix.lower() for p in mid.rglob("*") if p.is_file()}
    out_exts = {Path(p).suffix.lower() for p in new}
    for src_ext, dst_ext in EXPECT.items():
        if src_ext in in_exts and dst_ext not in out_exts:
            problems.append(f"input has {src_ext} but output has no {dst_ext}")

    try:
        log_rel = str(log_path.relative_to(REPO_ROOT))
    except ValueError:
        log_rel = str(log_path)
    record = {"command": cmd, "exit_code": code, "errors": errors[:50], "warnings": warnings,
              "tool_fingerprint": fingerprint, "log": log_rel,
              "baseline_excluded": len(files) - len(new), "problems": problems,
              "mid_hash": sha256_json(inventory(mid)),
              "tool_zip_sha256_file": "tools/conversion_tools_2_21.sha256"}
    if problems:
        write_run_record("convert", {**record, "result": "fail"})
        raise PipelineError("conversion failed:\n  " + "\n  ".join(problems))

    safe_rmtree(output, work_root)
    for rel in sorted(new):
        dst = output / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cache / rel, dst)
    inv = inventory(output)
    rec = write_run_record("convert", {**record, "result": "pass", "output": inv,
                                       "output_hash": sha256_json(inv)})
    print(f"[convert] OK: {len(inv)} files -> {output}  (record {rec.name})")


if __name__ == "__main__":
    run_main(main)
