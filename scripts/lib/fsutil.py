"""Filesystem helpers shared by convert/package/deploy. Stdlib only."""
import os
import shutil
import stat
from pathlib import Path

from lib.common import PipelineError, ensure_inside


def _on_rm_error(func, path, _exc):
    # Windows: clear read-only bit then retry once.
    os.chmod(path, stat.S_IWRITE)
    func(path)


def safe_rmtree(path, root):
    """Delete a directory tree, but only if it is strictly inside `root`."""
    path = ensure_inside(path, root)
    if path == Path(root).resolve():
        raise PipelineError(f"refusing to delete the root itself: {path}")
    if path.exists():
        shutil.rmtree(path, onerror=_on_rm_error)


def safe_remove(path, root):
    path = ensure_inside(path, root)
    if path.is_file():
        path.unlink()


def copy_tree(src, dst, allow_overwrite=False):
    """Copy files from src into dst (merging). Returns list of relative posix paths copied."""
    src, dst = Path(src), Path(dst)
    copied = []
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        target = dst / rel
        if target.exists() and not allow_overwrite:
            raise PipelineError(f"staging collision, would overwrite existing file: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
        copied.append(rel.as_posix())
    return copied


SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def jpeg_size(path):
    """Return (width, height) of a JPEG by walking marker segments to the SOFn marker."""
    data = Path(path).read_bytes()
    if data[:2] != b"\xff\xd8":
        raise PipelineError(f"not a JPEG: {path}")
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            raise PipelineError(f"corrupt JPEG segment structure in {path}")
        marker = data[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        length = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in SOF_MARKERS:
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            return w, h
        i += 2 + length
    raise PipelineError(f"no SOF marker found in {path}")
