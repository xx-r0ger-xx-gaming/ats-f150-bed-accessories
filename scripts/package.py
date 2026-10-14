"""Package the converted mod in Steam Workshop structure plus a local-install zip.

  python scripts/package.py [--converted build/converted] [--src-mod src/mod] [--out dist]
                            [--allow-todo]

Output (all deterministic: sorted entries, 1980-01-01 timestamps, fixed permissions):
  dist/f150_camper_shell/versions.sii            Workshop root: only versions.sii + version packages
  dist/f150_camper_shell/universal/              one version package (folder, per Workshop docs)
      manifest.sii  mod_description.txt  mod_icon.jpg  base.zip   (converted data + def/)
  dist/f150_camper_shell.zip                     same content flattened at the zip root, for
                                                 copying into <ATS>/mod (used by deploy.py)
  dist/SHA256SUMS, dist/inventory.json

Docs: Workshop_mod_structure (package = folder or zip; data in `base`/`base.zip`; manifest,
description and icon required), versions.sii needs exactly one universal entry (no
compatible_versions) per the validation-errors page, package names [a-z0-9_]. The exact unit name
syntax of versions.sii follows the wiki's example (`package_version_info : .latest`); the page
text for the file was only partially readable, so the format is UNVERIFIED until uploaded.

Safety: refuses anything under local-reference/, anything whose sha256 matches a file in
local-reference/ (extracted game assets), extraction-looking paths, non-allowlisted extensions,
and (unless --allow-todo) any remaining TODO markers.
"""
import fnmatch
import re
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.common import (  # noqa: E402
    PipelineError, REPO_ROOT, ensure_inside, make_parser, repo_path, run_main, script_args,
    sha256_file, write_run_record,
)
from lib.fsutil import jpeg_size, safe_rmtree  # noqa: E402

MOD_NAME = "f150_camper_shell"
PACKAGE_NAME = "universal"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
ALLOWED_EXT = {".pmd", ".pmg", ".pmc", ".pma", ".pmd", ".ppd", ".tobj", ".dds", ".mat", ".sii",
               ".sui", ".txt", ".jpg", ".png"}
BANNED_PATTERNS = ["*.scs", "*.scs.extracted", "*/extracted/*", "extracted/*", "*/local-reference/*",
                   "local-reference/*", "*.blend", "*.blend1", "*.tga", "*.psd", "*.pim", "*.pia",
                   "*.pis", "*.pic", "*.pip", "*.pit"]
TEXT_EXT = {".sii", ".sui", ".txt", ".mat", ".tobj"}
TODO_RE = re.compile(r"\bTODO(_[A-Z0-9_]*)?\b")
UNVERIFIED_RE = re.compile(r"UNVERIFIED")
ICON_SIZE = (276, 162)  # documented Workshop limit
ICON_MAX_BYTES = 1 << 20
MIN_DESC_BYTES = 50


def collect_sources(converted, src_mod):
    """Map archive path -> source file. converted/ first, then src/mod/def overlay (conflict = error)."""
    files = {}
    if converted.is_dir():
        for p in sorted(converted.rglob("*")):
            if p.is_file():
                files[p.relative_to(converted).as_posix()] = p
    def_root = src_mod / "def"
    if def_root.is_dir():
        for p in sorted(def_root.rglob("*")):
            if p.is_file():
                rel = "def/" + p.relative_to(def_root).as_posix()
                if rel in files and sha256_file(files[rel]) != sha256_file(p):
                    raise PipelineError(f"conflict: {rel} exists in converted output and src/mod with different content")
                files[rel] = p
    return files


def reference_hashes(ref_dir):
    hashes = {}
    if ref_dir.is_dir():
        for p in ref_dir.rglob("*"):
            if p.is_file():
                hashes[sha256_file(p)] = p.relative_to(ref_dir).as_posix()
    return hashes


def check_files(files, ref_dir, allow_todo):
    errors, warnings = [], []
    ref_hashes = reference_hashes(ref_dir)
    for rel, src in files.items():
        low = rel.lower()
        ext = Path(low).suffix
        resolved = src.resolve()
        if "local-reference" in {part.lower() for part in resolved.parts} or (
                ref_dir.is_dir() and ref_dir.resolve() in resolved.parents):
            errors.append(f"{rel}: source is under local-reference/")
        if any(fnmatch.fnmatch(low, pat) for pat in BANNED_PATTERNS):
            errors.append(f"{rel}: matches banned/extracted-asset pattern")
        if ext not in ALLOWED_EXT:
            errors.append(f"{rel}: extension {ext or '(none)'} not in allowlist")
        if ".." in rel.split("/") or rel.startswith("/"):
            errors.append(f"{rel}: unsafe path")
        digest = sha256_file(src)
        if digest in ref_hashes:
            errors.append(f"{rel}: identical to extracted reference file {ref_hashes[digest]}")
        todo_hits = []
        if TODO_RE.search(rel):
            todo_hits.append("path")
        if ext in TEXT_EXT:
            text = src.read_text(encoding="utf-8", errors="replace")
            if TODO_RE.search(text):
                todo_hits.append("content")
            if UNVERIFIED_RE.search(text):
                warnings.append(f"{rel}: contains UNVERIFIED markers")
        if todo_hits:
            msg = f"{rel}: TODO marker in {'+'.join(todo_hits)}"
            (warnings if allow_todo else errors).append(msg)
    return errors, warnings


def check_metadata(src_mod):
    """Validate manifest/description/icon against the documented Workshop rules."""
    errors = []
    manifest = src_mod / "manifest.sii"
    if not manifest.is_file():
        return [f"missing {manifest}"]
    text = manifest.read_text(encoding="utf-8")
    if not text.lstrip().startswith("SiiNunit"):
        errors.append("manifest.sii must start with SiiNunit")
    fields = {}
    for key in ("icon", "description_file"):
        m = re.search(rf'^\s*{key}\s*:\s*"([^"]+)"', text, re.M)
        if not m:
            errors.append(f"manifest.sii: {key} not set")
        else:
            fields[key] = m.group(1)
    if "mod_package" not in text:
        errors.append("manifest.sii: no mod_package unit")
    if "icon" in fields:
        icon = src_mod / fields["icon"]
        if not icon.is_file():
            errors.append(f"icon file missing: {icon}")
        else:
            if icon.suffix.lower() != ".jpg":
                errors.append("icon must be .jpg")
            elif jpeg_size(icon) != ICON_SIZE:
                errors.append(f"icon is {jpeg_size(icon)}, must be {ICON_SIZE}")
            if icon.stat().st_size > ICON_MAX_BYTES:
                errors.append("icon larger than 1 MB")
    if "description_file" in fields:
        desc = src_mod / fields["description_file"]
        if not desc.is_file():
            errors.append(f"description file missing: {desc}")
        else:
            raw = desc.read_bytes()
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError:
                errors.append("description must be UTF-8")
            if len(raw) < MIN_DESC_BYTES:
                errors.append(f"description under {MIN_DESC_BYTES} bytes")
    return errors, fields


def write_zip(path, entries):
    """entries: list of (archive_name, bytes_or_path). Deterministic."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, src in sorted(entries, key=lambda e: e[0]):
            info = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            data = src if isinstance(src, bytes) else Path(src).read_bytes()
            z.writestr(info, data, compresslevel=9)


def versions_sii():
    return ("SiiNunit\n{\n"
            f"package_version_info : .{PACKAGE_NAME}\n{{\n"
            f'\tpackage_name: "{PACKAGE_NAME}"\n'
            "}\n}\n").encode("utf-8")


def main():
    ap = make_parser("Package the mod in Workshop structure + local-install zip")
    ap.add_argument("--converted", default="build/converted")
    ap.add_argument("--src-mod", default="src/mod")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--reference-dir", default="local-reference")
    ap.add_argument("--allow-todo", action="store_true",
                    help="dry run: warn instead of fail on TODO markers (output is NOT releasable)")
    args = ap.parse_args(script_args())

    converted, src_mod = repo_path(args.converted), repo_path(args.src_mod)
    out = repo_path(args.out).resolve()
    ref_dir = repo_path(args.reference_dir)
    if not converted.is_dir() or not any(converted.rglob("*")):
        raise PipelineError(f"missing/empty converted output: {converted} (run convert.py)")

    meta_result = check_metadata(src_mod)
    meta_errors = meta_result if isinstance(meta_result, list) else meta_result[0]
    if meta_errors:
        raise PipelineError("metadata invalid:\n  " + "\n  ".join(meta_errors))
    fields = meta_result[1]

    files = collect_sources(converted, src_mod)
    meta_files = {"manifest.sii": src_mod / "manifest.sii",
                  fields["description_file"]: src_mod / fields["description_file"],
                  fields["icon"]: src_mod / fields["icon"]}
    errors, warnings = check_files(files, ref_dir, args.allow_todo)
    m_errors, m_warnings = check_files(meta_files, ref_dir, args.allow_todo)
    errors += m_errors
    warnings += m_warnings
    if not any(rel.startswith("def/") for rel in files):
        warnings.append("no def/ content in package (accessory definition missing)")
    for w in warnings:
        print(f"[package] WARN {w}")
    if errors:
        write_run_record("package", {"result": "fail", "errors": errors, "warnings": warnings,
                                     "allow_todo": args.allow_todo})
        raise PipelineError("refusing to package:\n  " + "\n  ".join(errors))

    # Clean only our own outputs inside dist/.
    work = ensure_inside(out, REPO_ROOT) if out.is_relative_to(REPO_ROOT) else out
    workshop = work / MOD_NAME
    safe_rmtree(workshop, work)
    for name in (f"{MOD_NAME}.zip", "SHA256SUMS", "inventory.json"):
        (work / name).unlink(missing_ok=True)
    (workshop / PACKAGE_NAME).mkdir(parents=True)

    data_entries = [(rel, src) for rel, src in files.items()]
    meta_entries = [(rel, src) for rel, src in meta_files.items()]

    # Workshop tree
    (workshop / "versions.sii").write_bytes(versions_sii())
    for rel, src in meta_entries:
        shutil.copyfile(src, workshop / PACKAGE_NAME / rel)
    write_zip(workshop / PACKAGE_NAME / "base.zip", data_entries)
    # Local-install zip (everything at the root)
    write_zip(work / f"{MOD_NAME}.zip", data_entries + meta_entries)

    items = []
    for p in sorted(work.rglob("*")):
        if p.is_file() and p.name not in ("SHA256SUMS", "inventory.json"):
            items.append({"path": p.relative_to(work).as_posix(), "size": p.stat().st_size,
                          "sha256": sha256_file(p)})
    (work / "SHA256SUMS").write_text("".join(f"{i['sha256']}  {i['path']}\n" for i in items),
                                     encoding="utf-8", newline="\n")
    contents = {}
    for zp in (workshop / PACKAGE_NAME / "base.zip", work / f"{MOD_NAME}.zip"):
        with zipfile.ZipFile(zp) as z:
            contents[zp.relative_to(work).as_posix()] = [
                {"name": i.filename, "size": i.file_size, "crc32": f"{i.CRC:08x}"} for i in z.infolist()]
    import json
    (work / "inventory.json").write_text(json.dumps(
        {"mod": MOD_NAME, "allow_todo_dry_run": args.allow_todo, "files": items,
         "zip_contents": contents}, indent=2, sort_keys=True), encoding="utf-8")
    write_run_record("package", {"result": "pass", "allow_todo": args.allow_todo,
                                 "warnings": warnings, "files": items})
    print(f"[package] OK{' (DRY RUN, not releasable)' if args.allow_todo else ''}: "
          f"{len(items)} files in {work}")


if __name__ == "__main__":
    run_main(main)
