# Camper variants: render framework

Render-only framework for showing several camper designs, each on its own stand-in truck, lit and
staged the same way. Nothing here is exported or packaged, and a render is not evidence that a mod
works in game. The V1 shell export pipeline (`build_scene.py` -> `export_scs.py` -> ...) is
separate and uses the same shell geometry code (`scripts/lib/shell_v1.py`).

## Quick start

```bash
B=tools/blender-3.6.23-windows-x64/blender.exe
# fast Eevee check (~10-30 s per view on the Surface)
$B --background --factory-startup --python-exit-code 1 --python scripts/render_variants.py -- \
   --variant my_camper --profile surface
# photoreal Cycles CPU (~1.5-3.5 min per 1280x720 view on the Surface i7-1185G7)
$B --background --factory-startup --python-exit-code 1 --python scripts/render_variants.py -- \
   --variant my_camper --profile surface-photo [--views rear34,side,front34] [--no-sheet]
# everything (skips reference configs whose name starts with "_"), incl. every pose in "renders"
$B ... --python scripts/render_variants.py -- --all --profile surface-photo
# one-off pose / experiment: override config keys (value JSON-parsed, else a plain string)
$B ... --python scripts/render_variants.py -- --variant pop_top --set camper.state=closed --suffix _closed
$B ... -- --variant v1_shell --set truck.tailgate=down --set 'cameras.side={"sun_azimuth_deg":200}' --suffix _test --no-sheet
```

- `--set key.path=value` (repeatable) is applied to the variant config before anything is built
  (`camper.*`, `truck.*`, `paint`, `cameras.*`, `views` ...). Missing intermediate keys are created.
- `--suffix _x` names the outputs `<name>_x_<view>.png` (they appear as their own contact-sheet row).
- If `--set` or `--suffix` is given, it replaces the config's `renders` list with that single pose.
- `render_variants.py` only runs `main()` under `if __name__ == "__main__"` (Blender's `--python`
  sets `__name__ == "__main__"`), so other scripts can `import render_variants` for
  `load_variant`, `apply_sets`, `parse_sets`, `render_variant`, `build_sheet`.

Outputs: `renders/variants/<name><suffix>_<view>.png` and `renders/variants/contact_sheet.png` (rows =
variants, columns = rear34 / side / front34, rebuilt from every `<name>_<view>.png` present, so
variants rendered in separate runs or by separate agents all land on one sheet). Run evidence goes
to `logs/render_variants-<timestamp>.json` (settings, camera, sun, seconds, output sha256).

Needs the HDRI: `powershell.exe -File scripts/fetch_tools.ps1` (CC0, sha256-checked, into
`tools/hdri/`, gitignored). Rendering fails with a clear message if it is missing.
The pickup variants also need the reference truck model, downloaded by hand (see
`docs/gaming-pc-setup.md`, "Reference truck for preview renders").

## Adding a variant (two files, nothing else)

1. `config/variants/<name>.json`
2. `scripts/variants/<module>.py` (usually `<module>` = `<name>`)

Parallel authors should only create/edit their own pair. Changes to shared code
(`scripts/lib/*`, `render_variants.py`, `config/render.json`) affect every variant: coordinate them.

### Config (`config/variants/<name>.json`)

```json
{
  "name": "popup_camper",
  "title": "Pop-top camper",
  "camper": {"module": "popup_camper", "roof_lift": 0.9, "any": "module parameters"},
  "truck": {"type": "pickup"},
  "paint": "config/v1.json#materials.shell_paint",
  "views": ["rear34", "side", "front34"],
  "renders": [{"suffix": "", "set": {}}, {"suffix": "_closed", "set": {"camper.state": "closed"}}],
  "cameras": {"side": {"lens": 50, "sun_azimuth_deg": 240}}
}
```

| key | meaning |
| --- | --- |
| `camper.module` | file `scripts/variants/<module>.py` (or a name registered with `@register`). Other `camper.*` keys are free-form module parameters. |
| `truck` | proxy truck spec, see below. |
| `paint` | body paint used for the truck AND `mats["paint"]` (colour match). Use the shared `"config/v1.json#materials.shell_paint"` ("Iconic Silver"-like metallic silver, the single source for every variant) unless a variant deliberately needs another colour. Either `"file.json#dotted.key"` or an inline dict: `base_color` (linear RGBA), `metallic`, `roughness`, `clearcoat`, `clearcoat_roughness`, optional `flake` (0..1), `dirt` (road dust on the truck's lower body, default 0.65). |
| `views` | subset of the views in `config/render.json`. |
| `renders` | optional pose list; each `{"suffix", "set"}` entry is rendered (by `--variant` and `--all`) with its dotted-key overrides to `<name><suffix>_<view>.png`. Default: one pose, no suffix. `pop_top` uses it for `pop_top_closed`. |
| `cameras.<view>` | per-variant overrides merged over `config/render.json` views (any camera key, plus `sun_azimuth_deg`). |

### Truck spec (`truck`)

Defaults in `scripts/lib/proxy_truck.py` `DEFAULTS`. Most useful keys:

| key | default | notes |
| --- | --- | --- |
| `type` | `pickup` | `pickup` only (5.5 ft bed, tailgate). |
| `tailgate` | `closed` | pickup only: `closed` (default, geometry unchanged), `down` (open, level with the bed floor, support cables), `removed` (opening down to the bed floor, as when a slide-in is loaded; `slide_in` uses it). Reported as `truck_info["tailgate"]`. |
| `cab` | `crew` | `crew` (4 doors) or `regular` (2 doors; the front clip moves 0.72 m back, the cab back stays at the origin). |
| `wheelbase` | 3.68 | pickup wheelbase. |
| `frame_top_z` | 0.62 | frame rail top above ground. |
| `frame_hw` | 0.56 | outer face of the rails (half width). |
| `tire_diameter`, `tire_width`, `rim_diameter`, `track`, `spokes`, `wheel_finish` | 0.82, 0.275, 0.508, 1.70, 6, `alloy_dark` | 20 in split-spoke alloys on all-terrain tyres. |

The procedural truck is original, generic and debadged (no logos, ovals or lettering) and is never
exported.

#### Reference truck (`"source": "reference"`)

`{"type": "pickup", "source": "reference"}` swaps the procedural pickup for a downloaded model
(default `tools/reference-truck/2023_ford_f150_lihtning_platinum.glb`, CC BY 4.0, credited in the
README; override with `truck.model`). It is used only for preview renders: gitignored, never
exported or packaged. Every variant uses it (`type: pickup`).

`build_reference_truck()` (in `proxy_truck.py`) imports the .glb with Blender's glTF importer, bakes
the transforms, scales it to `overall_length` (5.89 m), turns it to face +Y, then:

- **debadges**: deletes the badge materials (front oval insert, wheel-centre logos, replaced by plain
  dark centre caps) and the oval ring
  faces (`front_badge` box, chrome/black trim only), covers the oval recess with a plain satin-black
  slat, presses the tailgate script panel (`flatten_objects`) onto a fitted surface with analytic
  normals so no lettering is left, and swaps the licence-plate artwork for a blank plate;
- **repaints**: the body paint material becomes `mats["paint"]` (the shared silver, so campers
  colour-match); every other model material (all flat, roughness 1) is mapped onto the render
  library (`material_map`: glass, trim, chrome/alloy, tyres, lamps);
- **measures** with ray casts and returns the same `truck_info` contract: bed floor (`bed_floor_z`,
  extra key), bed inner length/width, rail top (= mount), `rail_outer_hw`, cab roof, cab back,
  tailgate outer face (`tailgate_y`), axles (from the brake discs), tyre radius, track. Measured on
  the current file: rail 1.337 m, floor 0.776 m, roof 1.905 m, bed 1.650 x 1.632 m inside, wheelbase
  3.70 m.
- `tailgate`: `closed` or `removed` (deletes the gate faces between the bed sides); `down` is
  procedural-only.

Missing file: rendering stops with the download instructions (see `docs/gaming-pc-setup.md`). Drop
`source` (or use `--set truck.source=procedural`) to render on the procedural pickup.

Reference renders of the bare bases: `--variant _ref_pickup` (reference model),
`--variant _ref_pickup_procedural`.

### Module (`scripts/variants/<module>.py`)

```python
TRUCK_TYPES = ("pickup",)          # optional; checked against truck.type (default: both)
DESCRIPTION = "Pop-top camper"     # optional

def build(cfg, collection, mats):
    """Return the list of every object created (may be empty for a bare truck)."""
```

- `cfg`: the variant JSON as a dict, plus
  - `cfg["camper"]`: your parameters;
  - `cfg["truck_info"]`: facts about the truck in the VARIANT frame (metres):
    `type`, `ground_z` (road height, negative), `roof_z` (cab roof top), `cab_back_y` (0.07),
    `front_y`, `front_axle_y`, `rear_axle_y`, `wheelbase`, `body_hw`, `track`, `tire_radius`,
    `spec` (resolved truck spec), `mount_local`;
    pickup adds `rail_z` (0), `bed_length`, `bed_inner_hw`, `rail_outer_hw`, `tailgate_y` (bed end), `tailgate`
    (the reference truck also gives `source`, `bed_floor_z`, `bed_inner_rear_y`, `axle_z`; use
    `ti.get("bed_floor_z", -0.52)`);
- `collection`: link every object you create here (`collection.objects.link(ob)`); the runner
  rejects objects outside it.
- `mats`: `lib.materials.MaterialLibrary` (below).
- Deterministic: no `random` without a fixed seed, no selection/UI state, no saving, no export,
  do not modify or delete truck objects. Prefix object names with your variant name.

### Coordinate frame

+Y forward (toward the cab / direction of travel), +Z up, +X to the right (passenger side), metres.

- **pickup**: origin = top of the bed rails, centred left/right, at the bed's front wall (same frame
  as the V1 shell and config/v1.json). The bed runs to y = -`bed_length`; the cab roof is at
  `roof_z` (~0.50 above the rails, 0.568 on the reference truck); the road is at `ground_z`
  (~-1.44, -1.337 on the reference truck). Never hardcode these: read them from `truck_info`.

## Shared helpers (reuse, do not copy)

`scripts/lib/meshkit.py` (bmesh, deterministic):
`Part(name, mats)` (one object from many primitives, `part.finish(collection, smooth=35, weighted=True)`),
`box`, `oriented_box`, `prism_x/prism_y/prism_z` (extrude 2D profiles), `cylinder_x/y/z`,
`revolve_x`, `arc_band_x`, `sweep_arc_x` (fender flares), `loft` (skin cross-section rings),
`rounded_rect`, `rounded_poly`, `build_prism`, `annulus_prism` (panel-gap grooves), `bevel`
(keeps face materials), `solidify`, `boolean_apply(obj, cutters)` (EXACT, baked),
`cut_openings(obj, [(ring_outside, ring_inside)], mats, collection)` (generic window cutter: hole
or recessed pocket with a glass floor and black gasket walls), `finish_hard_surface(obj)` (auto
smooth + weighted normals), `add_box_uv`, `new_object`.

`scripts/lib/shell_v1.py`: the V1 shell builders (`build_shell`, `ShellFrame`, `window_outlines`,
`cut_windows`, ...): a worked example of a rounded, solidified cap with real window openings.

`scripts/lib/materials.py` `MaterialLibrary`: `mats["paint"]` is the colour-matched body paint
(metallic flake + clearcoat; truck and camper share it). Other keys: `paint_dark`, `glass` (thin
tinted pane on a single face in front of a hollow interior), `glass_light`, `glass_flush` (opaque
dark glazing for pocket floors on solids), `glass_clear`, `interior`, `trim` (satin black textured
plastic), `trim_gloss`, `rubber`, `tire`, `chrome`, `alloy`, `alloy_dark`, `steel`, `lamp_red`
(lit), `lamp_red_lens` (unlit), `lamp_amber`, `lamp_clear`, `led_white`, `reflector`, `plate`,
`underbody`, `frame`, `bed_liner`, `decal_black`, `fabric`, `wood`, `plastic_white`,
`glass_tint` (camper glazing: smoked ~13 % pane with a reflectance floor so the HDRI reads on it),
`curtain` (pleated fabric for the back of a window pocket), `canvas` / `canvas_mesh` (tent canvas
and zip-window mesh), `seal` (window/door rubber).
Factories: `mats.car_paint(name, base_color, ...)` (stripes, two-tone; `clearcoat` > 0.05 adds a
real sharp Fresnel coat layer over the base, flakes vary the base roughness), `mats.principled(name, ...)`,
`mats.thin_glass(name, tint)`, `mats.canvas_material(name, color, wrinkle)`, `mats.add(key, material)`
(so `Part` can use it by key).

Camper windows (all variants): a pocket ~0.16-0.20 m deep is cut behind each opening (`interior`
walls, `curtain` back), a single-face `glass_tint` pane sits 12-14 mm under the skin, with a proud
`seal` lip and a frame. On the hollow V1/overland shells the pane is in front of a simple interior
(headliner, drawer base + sleeping platform, a duffel and a cooler). Eevee shows the interior much
brighter than Cycles (hashed shadows let more sun through the pane); judge glass in Cycles.

Shared paint (`config/v1.json#materials.shell_paint`): render-only keys `flake` 0.6, `dirt` 0.15 and
`render_roughness` 0.17 (base-coat roughness for renders; `roughness` 0.36 still feeds
`build_scene.py`).

`scripts/lib/environment.py`: HDRI world + sun (`setup_world`), road/ground (`add_ground`),
auto-framed cameras (`place_camera`), render profiles (`configure_render`, compositor finishing).

## Render settings (`config/render.json`)

- `hdri`: Poly Haven "Qwantani Late Afternoon" 4k (CC0). The HDRI sun disk is clamped
  (`sun_clamp`) and replaced by a sun lamp along the measured HDRI sun direction carrying the
  removed irradiance, so shadows are crisp and never doubled. `sun_azimuth_deg` rotates world + sun
  together around the vehicle (0 = ahead, 90 = right, 180 = behind, 270 = left); views override it.
- `ground`: two-lane road along Y (yellow dashed centre line, white edge lines, procedural asphalt
  with aggregate, wear tracks and sealed cracks), gravel shoulder blending into dry grass on a
  disk that fades into the HDRI horizon.
- `profiles`: `surface` (Eevee, 32 samples, soft shadows, GTAO, SSR, bloom), `surface-photo`
  (Cycles CPU, 192 adaptive samples, OpenImageDenoise, Filmic High Contrast, DOF, glare /
  chromatic aberration / vignette), `gaming` (Cycles GPU 1080p, for the gaming PC).
- `views`: `rear34`, `side`, `front34`: `azimuth_deg`, `height`, `lens`, `target_height`, `margin`
  (auto-fit to the truck + camper bounding box), `fstop`, `sun_azimuth_deg`. The side camera sits
  9 deg forward of square (279) with the sun low behind-left (205) so the flank is raking-lit; a sun
  behind the camera made paint, dark glass and graphics read washed-out mid-grey.

## Variant notes

- `v1_shell` / `overland_canopy`: on the reference truck the shell is refitted for the render
  (`fit_shell_cfg`: length to the tailgate face, rail-to-rail width, cab-high roof from
  `truck_info`; `config/v1.json` is untouched). Render-only extras: seals, hatch hinge strip + lock
  cylinders, base trim line above the rail seal, interior. The overland rack carries two rounded
  cases, stacked recovery boards and a shovel.
- `bed_rack`: generic overland bed rack (original profile, no maker names or logos). Tube frame on clamp
  feet over the middle of each rail cap (x = mean of `bed_inner_hw` and `rail_outer_hw`), corner uprights
  plus a mid post, MOLLE-style side panels with real through slots, top side rails and three crossbars
  `top_below_roof` (0.02 m) under `roof_z`, so nothing reaches the cab (front uprights 3 cm behind the bed
  front wall, 13 cm clear of the cab back on the reference truck). `loadout: full` adds a closed hard-shell
  rooftop tent on brackets over the crossbars (overhangs the tailgate by ~0.12 m), a light bar above the
  front crossbar, two recovery boards + a jerry can on the driver-side panel (the side the standard views
  show), a packed awning above the driver-side rail, a jerry can + shovel on the passenger side and the
  overland canopy's rotomoulded case on the bed floor (3 cm up, the floor is ribbed). `loadout: bare` is the
  rack alone. Clearance against the truck mesh was checked with BVH overlap tests: no contacts.
- `pop_top`: olive canvas, mesh zip windows, 0.13 m lid with a drip lip; the travel pose
  (`camper.state: closed`) leaves `closed_gap` (3 cm) under the lid filled by the folded canvas,
  with over-centre latches hooked to the lip.
- `slide_in`: camper front wall 4 cm clear of the cab back, cabover floor 0.13 m above the cab roof,
  nose at y = 1.30, wing walls 4.5 cm above the rails on rubber pads, basement floor 5 mm above the
  measured bed floor; frame tie-down receivers + spring turnbuckles just ahead of and behind the
  rear wheel opening.

Measured on the Surface Pro 8 (i7-1185G7, 2026-10-14, `--all`, 6 poses x 3 views, one Blender):
`surface-photo` 116 to 156 s per 1280x720 view, 2394 s (~40 min) for all 18; `surface` (Eevee)
10 to 13 s per view, ~3.7 min for all 18. Per-view seconds are in the `render_variants` log records.
After the reference-truck switch (2026-10-15): `surface-photo` 68 to 103 s per view on the
reference truck (490k faces; import + measure adds ~15 s per pose).
