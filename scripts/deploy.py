"""Reversible install of the packaged mod into the ATS mod directory.

  python scripts/deploy.py                       install dist/f150_camper_shell.zip
  python scripts/deploy.py --uninstall           remove exactly what was installed (hash-verified)
  python scripts/deploy.py --collect-log         copy game.log.txt into logs/ and grep it

Every placed file is recorded in logs/deploy-manifest.json with its sha256. Uninstall only
deletes recorded files whose current hash still matches; anything else is reported and left
alone (use --force to delete a modified recorded file). Nothing else in the mod dir is touched,
and an existing unrecorded file with the same name is never overwritten.
"""
import datetime
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.common import (  # noqa: E402
    LOG_DIR, PipelineError, REPO_ROOT, ensure_inside, load_tools_config, make_parser, repo_path,
    run_main, script_args, sha256_file, write_run_record,
)

MOD_NAME = "f150_camper_shell"
LOG_PATTERN = re.compile(r"f150|camper|shell|Road ?Trip|\[error\]|\berror\b|\bfailed\b|\bmissing\b|cannot|"
                         r"unable", re.I)
MOD_PATTERN = re.compile(r"f150_camper|camper_shell|f150_bed_shell", re.I)
BAD_PATTERN = re.compile(r"error|fail|missing|cannot|unable|invalid", re.I)


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def load_manifest(path):
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"files": []}


def save_manifest(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def install(args, mod_dir, mpath):
    pkg = repo_path(args.package)
    if not pkg.is_file():
        raise PipelineError(f"package not found: {pkg} (run package.py)")
    manifest = load_manifest(mpath)
    if manifest["files"]:
        raise PipelineError(f"already installed per {mpath.name}; run --uninstall first")
    target = ensure_inside(mod_dir / pkg.name, mod_dir)
    if target.exists():
        raise PipelineError(f"{target} already exists and was not placed by deploy.py; refusing to overwrite")
    mod_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pkg, target)
    digest = sha256_file(target)
    if digest != sha256_file(pkg):
        target.unlink()
        raise PipelineError("copy verification failed")
    save_manifest(mpath, {"installed_at": now(), "mod_dir": str(mod_dir),
                          "source": str(pkg), "files": [{"path": str(target), "sha256": digest,
                                                         "size": target.stat().st_size}]})
    write_run_record("deploy", {"action": "install", "target": str(target), "sha256": digest})
    print(f"[deploy] installed {target}\n[deploy] sha256 {digest}\n[deploy] manifest {mpath}")
    print("[deploy] Reminder: use a SEPARATE ATS profile, enable the mod in the Mod Manager.")


def uninstall(args, mod_dir, mpath):
    manifest = load_manifest(mpath)
    if not manifest["files"]:
        print("[deploy] nothing recorded; nothing to remove")
        return
    problems, removed = [], []
    for entry in manifest["files"]:
        p = Path(entry["path"])
        try:
            ensure_inside(p, mod_dir)
        except PipelineError as e:
            problems.append(str(e))
            continue
        if not p.exists():
            print(f"[deploy] already gone: {p}")
            removed.append(entry["path"])
            continue
        if sha256_file(p) != entry["sha256"] and not args.force:
            problems.append(f"{p} was modified since install (hash mismatch); left in place (--force to delete)")
            continue
        p.unlink()
        removed.append(entry["path"])
        print(f"[deploy] removed {p}")
    manifest["files"] = [e for e in manifest["files"] if e["path"] not in removed]
    manifest["uninstalled_at"] = now()
    save_manifest(mpath, manifest)
    write_run_record("deploy", {"action": "uninstall", "removed": removed, "problems": problems})
    if problems:
        raise PipelineError("uninstall incomplete:\n  " + "\n  ".join(problems))


def collect_log(args, cfg):
    src = Path(args.game_log or cfg.get("ats_game_log", ""))
    if not src.is_file():
        raise PipelineError(f"game log not found: {src}")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = LOG_DIR / f"game-{stamp}.log.txt"
    shutil.copyfile(src, dst)
    lines = dst.read_text(encoding="utf-8", errors="replace").splitlines()
    hits = [(i + 1, ln) for i, ln in enumerate(lines) if LOG_PATTERN.search(ln)]
    mod_bad = [(i, ln) for i, ln in hits if MOD_PATTERN.search(ln) and BAD_PATTERN.search(ln)]
    matches = LOG_DIR / f"game-{stamp}-matches.txt"
    matches.write_text("".join(f"{i}: {ln}\n" for i, ln in hits), encoding="utf-8")
    print(f"[deploy] copied -> {dst}  ({len(lines)} lines)")
    print(f"[deploy] {len(hits)} matching lines -> {matches}; {len(mod_bad)} mention the mod with an error word")
    for i, ln in hits[:40]:
        print(f"  {i}: {ln}")
    write_run_record("deploy", {"action": "collect-log", "log": str(dst), "matches": len(hits),
                                "mod_errors": [ln for _, ln in mod_bad]})
    if mod_bad:
        raise PipelineError(f"{len(mod_bad)} log line(s) mention the mod together with an error")


def main():
    ap = make_parser("Reversible install of the packaged mod into the ATS mod dir")
    ap.add_argument("--package", default=f"dist/{MOD_NAME}.zip")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--collect-log", action="store_true")
    ap.add_argument("--force", action="store_true", help="uninstall: delete even if the hash changed")
    ap.add_argument("--mod-dir", help="override ats_mod_dir (for tests)")
    ap.add_argument("--game-log", help="override ats_game_log (for tests)")
    ap.add_argument("--manifest", default="logs/deploy-manifest.json")
    args = ap.parse_args(script_args())

    cfg = {}
    if args.collect_log and args.game_log:
        pass
    else:
        cfg = load_tools_config(("ats_game_log",) if args.collect_log else ())
    if args.collect_log:
        return collect_log(args, cfg)

    if args.mod_dir:
        mod_dir = Path(args.mod_dir)
    else:
        cfg = load_tools_config(("ats_mod_dir",))
        mod_dir = Path(cfg["ats_mod_dir"])
    if not mod_dir.is_dir():
        raise PipelineError(f"mod dir does not exist: {mod_dir}")
    mod_dir = mod_dir.resolve()
    mpath = repo_path(args.manifest)
    if args.uninstall:
        uninstall(args, mod_dir, mpath)
    else:
        install(args, mod_dir, mpath)


if __name__ == "__main__":
    run_main(main)
