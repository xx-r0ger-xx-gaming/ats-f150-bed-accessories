"""Export build/v1.blend to SCS game-format files with SCS Blender Tools (pinned zip).

Run with Blender (pinned 3.6.x), from the repo root:
  blender --background build/v1.blend --python-exit-code 1 --python scripts/export_scs.py -- \
      --config config/v1.json --materials config/scs_materials.json --output build/mid

Add-on isolation (no user AppData involved):
  The pinned zip (path from config/tools.local.json) is extracted to
  tools/blender_user/addons/io_scs_tools (re-extracted if the zip sha256 differs from the marker).
  tools/blender_user is then registered at runtime as an extra script directory
  (Preferences > File Paths > Script Directories, Blender 3.6+) so bpy.utils.script_paths() -- which the
  add-on uses to find its own install dir and write its config.txt -- includes it. The add-on is enabled
  with addon_utils.enable(default_set=True, persistent=False): registered in the in-memory preferences only (background runs never save prefs).

Everything is driven through the add-on's own operators/props:
  object.scs_tools_create_scs_root   (operators/object.py, SCSRoot) creates the SCS Root + parts + looks
  shader presets: same steps as properties/addon_preferences.py set_shader_presets_item (UI enum setter)
  scene.scs_tools_export_by_scope    (operators/scene.py): see main() -- its invoke() is SCSExportHelper.execute_export
"""
import importlib
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import addon_utils  # noqa: E402
import bpy  # noqa: E402

from lib.common import (  # noqa: E402
    REPO_ROOT, PipelineError, ensure_inside, inventory, load_json, load_tools_config,
    make_parser, repo_path, run_main, script_args, sha256_file, write_run_record,
)

ADDON = "io_scs_tools"
USER_DIR = REPO_ROOT / "tools" / "blender_user"
ROLE_PROP = "camper_role"
EXPECTED_BLENDER = (3, 6)


class _StderrTee:
    """Tee sys.stderr so Python tracebacks that Blender prints for exceptions inside add-on callbacks
    (property update functions, handlers, timers: they do NOT abort the script or change the exit code)
    can be inspected after the export."""

    def __init__(self, inner):
        self.inner = inner
        self.text = []

    def write(self, s):
        self.text.append(s)
        return len(s)

    def flush(self):
        pass

    def replay(self):
        """Forward everything captured except the known-benign traceback (reported as one note instead)."""
        text = "".join(self.text)
        n = 0
        for block in split_tracebacks(text):
            if is_known_benign(block):
                text = text.replace(block, "", 1)
                n += 1
        if n:
            self.inner.write(f"note: ignored {n} known-benign add-on exception(s) from scs_tools_create_scs_root "
                             "(see KNOWN_BENIGN_MSG in scripts/export_scs.py)\n")
        self.inner.write(text)
        self.inner.flush()

    def __getattr__(self, name):
        return getattr(self.inner, name)


# Known, harmless add-on exception (BlenderTools 2.4.x, unmodified upstream bug), matched exactly:
# bpy.ops.object.scs_tools_create_scs_root sets empty_object_type='SCS_Root' (which adds the default part to
# the new root's inventory -> ObjectPartInventoryItem.name_update) BEFORE it makes the new root the active
# object. name_update looks up the SCS root of context.active_object (still the pre-selected mesh, which has
# no root yet) and gets None. The callback only normalises/de-duplicates the name of a freshly added default
# part, which is already normalised and unique, so nothing is lost. Any other traceback fails the export.
KNOWN_BENIGN_MSG = "'NoneType' object has no attribute 'scs_object_part_inventory'"


def split_tracebacks(text):
    blocks, cur = [], None
    for line in text.splitlines():
        if line.startswith("Traceback (most recent call last):"):
            if cur:
                blocks.append(cur)
            cur = [line]
        elif cur is not None:
            if line.startswith((" ", "\t")):
                cur.append(line)
            else:  # exception line ends the block
                cur.append(line)
                blocks.append(cur)
                cur = None
    if cur:
        blocks.append(cur)
    return ["\n".join(b) for b in blocks]


def is_known_benign(block):
    return (KNOWN_BENIGN_MSG in block and "in name_update" in block
            and "properties" in block and "object.py" in block)


def install_addon(zip_path):
    """Extract the pinned zip into the isolated per-repo scripts dir, register it, enable it."""
    zip_path = repo_path(zip_path)
    if not zip_path.is_file():
        raise PipelineError(f"SCS Blender Tools zip missing: {zip_path}")
    zip_sha = sha256_file(zip_path)
    addons_dir = USER_DIR / "addons"
    target = addons_dir / ADDON
    marker = USER_DIR / "scs_tools_zip.sha256"
    if not target.is_dir() or not marker.is_file() or marker.read_text().strip() != zip_sha:
        ensure_inside(target, USER_DIR)
        if target.exists():
            shutil.rmtree(target)
        addons_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                if not name.startswith(ADDON + "/"):
                    raise PipelineError(f"unexpected zip member outside {ADDON}/: {name}")
                ensure_inside(addons_dir / name, addons_dir)
            z.extractall(addons_dir)
        marker.write_text(zip_sha)

    # Make the add-on importable and make bpy.utils.script_paths() include our dir.
    if str(addons_dir) not in sys.path:
        sys.path.insert(0, str(addons_dir))
    dirs = bpy.context.preferences.filepaths.script_directories
    if not any(Path(d.directory).resolve() == USER_DIR.resolve() for d in dirs):
        d = dirs.new()
        d.name = "repo_blender_user"
        d.directory = str(USER_DIR)
    if not any(Path(p).resolve() == USER_DIR.resolve() for p in bpy.utils.script_paths()):
        raise PipelineError(f"{USER_DIR} not in bpy.utils.script_paths(); add-on config would land elsewhere")

    importlib.invalidate_caches()
    mod = addon_utils.enable(ADDON, default_set=True, persistent=False, handle_error=None)
    if mod is None:
        raise PipelineError("addon_utils.enable returned None for io_scs_tools")
    if Path(mod.__file__).resolve().parent != target.resolve():
        raise PipelineError(f"add-on imported from unexpected location: {mod.__file__}")
    v = mod.bl_info["version"]
    return {"name": mod.bl_info["name"], "version": ".".join(str(x) for x in v),
            "bl_info_blender": list(mod.bl_info["blender"]),
            "zip": str(zip_path), "zip_sha256": zip_sha, "path": str(target)}


def drain_async_paths(limit=200):
    """The add-on initialises paths/libraries (shader presets etc.) from bpy.app.timers, which never fire in
    a --background script run. Call the add-on's own timer function until it reports it is done."""
    from io_scs_tools.internals.containers.config import AsyncPathsInit
    for _ in range(limit):
        if AsyncPathsInit._process_paths() is None:
            return
    raise PipelineError("SCS paths initialisation did not finish")


def check_operators():
    needed = {
        "object": ["scs_tools_create_scs_root"],
        "scene": ["scs_tools_export_by_scope"],
    }
    missing = []
    for cat, names in needed.items():
        mod = getattr(bpy.ops, cat)
        for n in names:
            if not hasattr(mod, n):
                missing.append(f"bpy.ops.{cat}.{n}")
    if missing:
        raise PipelineError("SCS operators missing (add-on not enabled or wrong version): " + ", ".join(missing))


def apply_presets(mats_cfg, model_dir_abs, model_dir_rel, objs, uv_name="UVMap"):
    """Assign shader presets to every material by camper_role; mirrors the UI preset setter."""
    from io_scs_tools.internals import shader_presets as sp
    from io_scs_tools.utils import material as mat_utils

    roles = mats_cfg["roles"]
    src_dir = repo_path(mats_cfg["texture_source_dir"])
    applied = {}
    for mat in sorted(bpy.data.materials, key=lambda m: m.name):
        role = mat.get(ROLE_PROP)
        if role is None:
            continue
        if role not in roles:
            raise PipelineError(f"material {mat.name}: role {role!r} not in scs_materials.json")
        spec = roles[role]
        if not sp.has_preset(spec["preset"]):
            raise PipelineError(f"shader preset {spec['preset']!r} not found in the add-on's shader_presets.txt")
        section = sp.get_section(spec["preset"], spec.get("flavors", ""))
        # Update callbacks resolve the material from context.active_object.active_material.
        owner = next((o for o in objs if any(s.material == mat for s in o.material_slots)), None)
        if owner is None:
            raise PipelineError(f"material {mat.name} is not used by any exported object")
        bpy.context.view_layer.objects.active = owner
        owner.active_material_index = [s.material for s in owner.material_slots].index(mat)

        mat.scs_props.mat_effect_name = section.get_prop_value("Effect")
        mat_utils.set_shader_data_to_material(mat, section)
        mat.scs_props.active_shader_preset_name = spec["preset"]

        tex_src = src_dir / spec["texture_file"]
        if not tex_src.is_file():
            raise PipelineError(f"texture missing (run scripts/make_textures.py): {tex_src}")
        shutil.copy2(tex_src, model_dir_abs / spec["texture_file"])
        mat.scs_props.shader_texture_base = "/" + model_dir_rel + "/" + spec["texture_file"]
        for item in mat.scs_props.shader_texture_base_uv:
            if item.tex_coord != -1:
                item.value = uv_name
        if "reflection_file" in spec:
            shutil.copy2(src_dir / spec["reflection_file"], model_dir_abs / spec["reflection_file"])
            mat.scs_props.shader_texture_reflection = "/" + model_dir_rel + "/" + spec["reflection_file"]
        applied[mat.name] = {"role": role, "preset": spec["preset"], "effect": mat.scs_props.mat_effect_name,
                             "texture": mat.scs_props.shader_texture_base}
    if not applied:
        raise PipelineError(f"no materials with custom prop {ROLE_PROP!r}")
    return applied


def main():
    p = make_parser("Export V1 shell with SCS Blender Tools")
    p.add_argument("--config", required=True)
    p.add_argument("--materials", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args(script_args())
    tee = sys.stderr = _StderrTee(sys.__stderr__)

    if bpy.app.version[:2] != EXPECTED_BLENDER:
        raise PipelineError(f"Blender {bpy.app.version_string}; pinned series is {EXPECTED_BLENDER}")
    if not bpy.data.filepath:
        raise PipelineError("run with the saved source .blend loaded (blender --background build/v1.blend ...)")

    cfg = load_json(args.config)
    mats_cfg = load_json(args.materials)
    scs_cfg = cfg["scs"]
    tools_cfg = load_tools_config(required=("scs_blender_tools_zip",))

    addon_info = install_addon(tools_cfg["scs_blender_tools_zip"])
    check_operators()

    from io_scs_tools.internals.persistent.initialization import init_scs_tools
    from io_scs_tools.utils import get_scs_globals
    if not init_scs_tools():
        raise PipelineError("init_scs_tools() failed")
    drain_async_paths()
    out_root = repo_path(args.output)
    if out_root.exists():
        ensure_inside(out_root, REPO_ROOT / "build")
        shutil.rmtree(out_root)
    model_rel = scs_cfg["model_path"].strip("/")
    model_dir = out_root / model_rel
    model_dir.mkdir(parents=True)

    g = get_scs_globals()
    g.scs_project_path = str(out_root)
    drain_async_paths()
    g.export_scope = "scene"
    g.export_output_type = scs_cfg["export_output_type"]
    if g.scs_project_path.rstrip("\\/") != str(out_root).rstrip("\\/"):
        raise PipelineError(f"SCS project path not applied: {g.scs_project_path!r}")

    coll = bpy.data.collections.get("camper_shell")
    if coll is None:
        raise PipelineError("collection 'camper_shell' missing; run build_scene.py first")
    objs = sorted(coll.objects, key=lambda o: o.name)
    if not objs:
        raise PipelineError("camper_shell collection is empty")

    # SCS Root: create exactly as the UI operator does (selected objects become its children).
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.scs_tools_create_scs_root(scs_root_object_string=scs_cfg["model_name"])
    root = bpy.context.view_layer.objects.active
    if root is None or root.scs_props.empty_object_type != "SCS_Root" or root.name != scs_cfg["model_name"]:
        raise PipelineError(f"SCS Root creation failed (got {root!r})")
    # Export lands in <project>/<model_path>: per-root custom export path (the scene-level default path is not
    # usable because the add-on exports from a temporary "SCS Export" scene).
    root.scs_props.scs_root_object_allow_custom_path = True
    root.scs_props.scs_root_object_export_filepath = model_rel
    unparented = [o.name for o in objs if o.parent != root]
    if unparented:
        raise PipelineError(f"objects not parented to SCS Root: {unparented}")

    applied = apply_presets(mats_cfg, model_dir, model_rel, objs)

    # Save the SCS-prepared scene before export (project rule). Saved as a separate file so the pristine
    # build_scene output (build/v1.blend) is never mutated and the script stays re-runnable.
    scs_blend = Path(bpy.data.filepath).with_name(Path(bpy.data.filepath).stem + "_scs.blend")
    bpy.ops.wm.save_as_mainfile(filepath=str(scs_blend), compress=False)

    wm = bpy.context.window_manager
    if not wm.windows:
        raise PipelineError("no window available for the export in background mode")
    # bpy.ops.scene.scs_tools_export_by_scope only defines invoke()/modal() (no execute()), and Blender cannot
    # supply an event in --background, so the operator call is rejected ("invalid operator call"). Its invoke()
    # for export_scope='scene' is just SCSExportHelper.execute_export(context, True); call that same add-on
    # routine on a minimal stand-in that supplies the report() the real operator would provide.
    from io_scs_tools.operators.bases.export import SCSExportHelper

    class Reporter(SCSExportHelper):
        def __init__(self):
            super().__init__()
            self.reports = []

        def report(self, kind, message):
            self.reports.append((sorted(kind)[0], message))

    rep = Reporter()
    win = wm.windows[0]
    area = next((a for a in win.screen.areas), None)
    if area is None:
        raise PipelineError("no screen area available; the add-on's progress redraw (wm.redraw_timer) needs one")
    region = next((r for r in area.regions if r.type == "WINDOW"), area.regions[0])
    # The add-on's progress messenger calls bpy.ops.wm.redraw_timer, whose poll fails in --background (no active
    # window). It is a pure UI redraw hack (printout.py), so no-op it for the duration of the export only.
    import io_scs_tools.utils.printout as printout
    messenger = printout.immediate_messenger
    messenger.report_message_and_redraw = lambda message: None
    try:
        with bpy.context.temp_override(window=win, screen=win.screen, area=area, region=region, scene=bpy.context.scene):
            result = rep.execute_export(bpy.context, True)
    finally:
        del messenger.report_message_and_redraw
    for kind, msg in rep.reports:
        print(f"SCS report [{kind}] {msg}")
    if result != {"FINISHED"}:
        raise PipelineError(f"export returned {result}; reports: {rep.reports}")
    bad = [r for r in rep.reports if r[0] in ("ERROR", "WARNING")]
    if any(r[0] == "ERROR" for r in bad):
        raise PipelineError(f"export reported errors: {bad}")

    import io_scs_tools.utils.printout as pr
    errs = list(getattr(pr, "error_messages", []) or [])
    warns = list(getattr(pr, "warning_messages", []) or [])

    tracebacks = split_tracebacks("".join(tee.text))
    ignored = [t for t in tracebacks if is_known_benign(t)]
    unexpected = [t for t in tracebacks if not is_known_benign(t)]

    files = inventory(out_root)
    exts = {Path(f["path"]).suffix.lower() for f in files}
    required = set(mats_cfg["required_export_extensions"])
    missing = sorted(required - exts)
    rec = write_run_record("export_scs", {
        "blender": bpy.app.version_string,
        "addon": addon_info,
        "config": str(args.config), "materials_config": str(args.materials),
        "output": str(args.output), "source_blend": str(scs_blend), "source_blend_sha256": sha256_file(scs_blend),
        "materials": applied, "export_reports": rep.reports, "addon_errors": errs, "addon_warnings": warns,
        "python_tracebacks_unexpected": unexpected, "python_tracebacks_known_benign": len(ignored),
        "files": files, "missing_required_extensions": missing,
        "not_applicable_extensions": mats_cfg["not_applicable_extensions"],
    })
    print(f"record {rec}")
    for f in files:
        print(f"  {f['path']}  {f['size']}  {f['sha256'][:12]}")
    if unexpected:
        raise PipelineError(f"{len(unexpected)} unexpected Python exception(s) during export:\n"
                            + "\n".join(unexpected))
    if errs:
        raise PipelineError(f"add-on reported {len(errs)} export error(s): {errs}")
    if missing:
        raise PipelineError(f"export produced no {missing} files (see {rec})")


def guarded():
    try:
        main()
    finally:
        if isinstance(sys.stderr, _StderrTee):
            t = sys.stderr
            sys.stderr = t.inner
            t.replay()


run_main(guarded)
