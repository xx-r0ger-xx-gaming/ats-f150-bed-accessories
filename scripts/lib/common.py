"""Shared helpers for pipeline scripts.

Stdlib only: imported both by plain Python (preflight, package, deploy) and by
Blender's bundled Python (build_scene, export_scs, render_preview).
"""
import argparse
import datetime
import hashlib
import json
import os
import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "logs"


class PipelineError(RuntimeError):
    """Raised for any condition that must stop the pipeline."""


def script_args(argv=None):
    """Return the arguments after '--' (Blender convention) or all args when run by plain Python."""
    argv = sys.argv if argv is None else argv
    if "--" in argv:
        return argv[argv.index("--") + 1:]
    return argv[1:]


def make_parser(description):
    return argparse.ArgumentParser(description=description)


def repo_path(p):
    """Resolve a repo-relative or absolute path."""
    p = Path(p)
    return p if p.is_absolute() else (REPO_ROOT / p)


def load_json(path):
    path = repo_path(path)
    if not path.is_file():
        raise PipelineError(f"missing input: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_tools_config(required=()):
    """Load config/tools.local.json and check the listed keys point at existing paths."""
    cfg_path = REPO_ROOT / "config" / "tools.local.json"
    if not cfg_path.is_file():
        raise PipelineError(
            "config/tools.local.json not found; copy config/tools.example.json and set local paths"
        )
    cfg = load_json(cfg_path)
    for key in required:
        value = cfg.get(key)
        if not value or "<you>" in str(value):
            raise PipelineError(f"tools.local.json: '{key}' is not set")
        if not repo_path(value).exists():
            raise PipelineError(f"tools.local.json: '{key}' path does not exist: {value}")
    return cfg


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def sha256_json(obj):
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    """Sorted list of {path, size, sha256} for every file under root."""
    root = Path(root)
    items = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            items.append({
                "path": p.relative_to(root).as_posix(),
                "size": p.stat().st_size,
                "sha256": sha256_file(p),
            })
    return items


def write_run_record(step, record):
    """Append evidence for one pipeline step to logs/<step>-<timestamp>.json."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    record = dict(record)
    record.setdefault("step", step)
    record.setdefault("timestamp", stamp)
    record.setdefault("host", platform.node())
    record.setdefault("python", sys.version.split()[0])
    out = LOG_DIR / f"{step}-{stamp}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, sort_keys=True)
    return out


def ensure_inside(path, root):
    """Refuse to write outside an expected directory (protects shared tool/game dirs)."""
    path = Path(path).resolve()
    root = Path(root).resolve()
    if os.path.commonpath([path, root]) != str(root):
        raise PipelineError(f"refusing to touch {path}: outside {root}")
    return path


def run_main(main):
    """Run main(), convert PipelineError into exit code 1 with a clear message."""
    try:
        main()
    except PipelineError as e:
        print(f"PIPELINE ERROR: {e}", file=sys.stderr)
        sys.exit(1)
