# Compatibility and evidence log

Recorded October 14, 2026 from web research only. Nothing here has been tested in game. Statuses: VERIFIED-DOCS (stated by an official or first-party page), INFERRED (reasoned from documents, needs proof), UNKNOWN (no source found).

## Target

| Item | Value | Status | Source |
| --- | --- | --- | --- |
| DLC | American Truck Simulator - Road Trip: Ford | VERIFIED-DOCS | https://store.steampowered.com/app/3793200/ |
| Steam app ID | 3793200 | VERIFIED-DOCS | https://blog.scssoft.com/2026/09/road-trip-ford-release-date-video.html |
| Release | September 29, 2026; $7.99; requires base ATS | VERIFIED-DOCS | https://store.steampowered.com/app/3793200/ |
| Vehicle | 2023 Ford F-150, Lariat trim | VERIFIED-DOCS | https://blog.scssoft.com/2026/01/ats-road-trip-ford-car-pack-f-150.html |
| Cab / bed variant | Not stated by SCS | UNKNOWN | - |
| Required ATS version | Not stated; 1.61+ | INFERRED | https://blog.scssoft.com/2026/09/american-truck-simulator-161-update-release.html |
| Current ATS | 1.61.x (stable mid-September 2026; no 1.62 post found) | INFERRED | https://blog.scssoft.com/2026/09/ |
| Steam Workshop | Store page lists Workshop support | VERIFIED-DOCS | https://store.steampowered.com/app/3793200/ |

## Tool matrix

| Tool | Version / pin | Status |
| --- | --- | --- |
| Blender (Surface) | 3.6.23 portable, sha256 `e3296eba7eab32c2e5182459ec7614af32224eee2bd32c9d0a08ffd751c54f3b` | Pinned |
| SCS Blender Tools | 2.4.1, zip sha256 `c38df76fbdb4f703fdd72493eda30bdac32b56e50052ec8b3c5f5767ee226649`; supports Blender 3.2.x-3.6.x (https://modding.scssoft.com/wiki/Documentation/Tools/SCS_Blender_Tools/Download) | Pinned; latest found |
| Conversion Tools | 2.21, ETS2/ATS 1.58+, 64-bit (https://modding.scssoft.com/wiki/Documentation/Tools/Conversion_Tools) | Planned; Road Trip asset support UNKNOWN |
| Surface GPU | Intel Iris Xe, driver 32.0.101.6737 | Recorded |
| Surface Eevee test | 1280x720, 32 samples, 6.3 s, 2026-10-14 | Passed |
| Gaming PC | GPU, driver, Blender, add-on, ATS build | TBD |

## Accessory and attachment evidence

- **Accessory unit syntax, VERIFIED-DOCS:** `accessory_data` carries name, icon, price (0 hides it), unlock, part_type, suitable_for, conflict_with, defaults, overrides, require (https://modding.scssoft.com/wiki/Documentation/Engine/Units/accessory_data). `accessory_addon_data` adds exterior_model/interior_model (.pmd), coll (.pmc), look, variant, hide_in; located at `def/vehicle/truck/<brand.model>/accessory/<type>/*.sii` (https://modding.scssoft.com/wiki/Documentation/Engine/Units/accessory_addon_data).
- **F-150 def path:** superseded by the OBSERVED-IN-MODS section below (car layout, `def/vehicle/car/ford.f150_23/`). Still not confirmed against the DLC archive.
- **Mods can add accessory types to the F-150, INFERRED:** the Pickup Load Pack adds a `load_bed` accessory positioning cargo in the bed, and invites other pickups to do the same (https://steamcommunity.com/sharedfiles/filedetails/?id=3811097362). Its file structure is not published; user comments report interior breakage and an "Index outside array boundaries: 36 >= 36" crash (unverified).
- **Other F-150 mods:** Expanded Factory Options edits vanilla chassis/engine files and warns of load-order conflicts (https://atsmods.lt/ford-f-150-bronco-expanded-factory-options/); Skinpack is paint jobs only (https://atsmods.lt/ford-f-150-skinpack/). Prefer new files over overriding vanilla ones.
- **Locator naming, UNKNOWN:** no wiki page fetched. Leads: https://forum.scssoft.com/viewtopic.php?t=320864 and https://forum.scssoft.com/viewforum.php?f=172.
- **Official Road Trip / car modding docs or templates:** none found (https://modding.scssoft.com/wiki/Main_Page). UNKNOWN.
- **Bed-cover or shell slot on the F-150:** UNKNOWN.

## Observed in community mod defs (2026-10-14)

Status: OBSERVED-IN-MODS. Read from the text definitions of two community mods for the Road Trip F-150 ("Ford F-150 & Bronco Expanded Factory Options" and "Ford F-150 Skinpack", atsmods.lt). Facts only; no file contents copied. Not verified in game, and the mods' files were not checked against the DLC archive.

- **Vehicle type is a car, not a truck:** def root `def/vehicle/car/ford.f150_23/` with subfolders `chassis`, `engine`, `transmission`, `cabin`, `interior`, `paint_job`, `head_light`, `accessory/<slot>`, plus `data.sii` and `lamp_setup.sii`.
- **Unit naming:** `<id>.ford.f150_23.<type>`.
- **Chassis:** only 4-door, 5.5 ft bed, AWD is present: unit `4d55_awd.ford.f150_23.chassis` (chassis file `4doors_55_awd.sii`). No regular cab or chassis cab.
- **Cabin:** unit `pckup4d_55.ford.f150_23.cabin` (cabin file `pickup_4doors_55.sii`).
- **Interior:** Lariat.
- **Dealer def:** `def/vehicle/car_dealer/ford/ford_f150_23.sii`. Lists `vehicle : .car` with `vehicle_accessory`, `vehicle_addon_accessory` and `vehicle_wheel_accessory` units, each with `data_path`, `slot_name`, `slot_hookup`.
- **Existing accessory slots seen:** steering_w, mirror, rv_mirror, codrv_seat, doorhndl, doorstep, exhaust, f_bumper, r_bumper, f_light, r_light, hood, grill, s_vent, trunk, windowtrim, f_logo, r_logo, windows, bullbar. **No bed, load_bed or cargo slot** in vanilla as seen; `trunk` (variant `standard_paint`) is the nearest.
- **Variant convention:** `standard_paint` suggests a body-paint variant convention for accessories (INFERRED).
- **Models:** model root `/vehicle/car/ford_f150_23/` (e.g. `chassis/chs_4doors_55_awd.pmd`). Car upgrades live under `/vehicle/car/upgrade/`.
- **Paint:** car `paint_job` system at `def/vehicle/car/ford.f150_23/paint_job/`. Uses `accessory_paint_job_data` with `paint_job_mask`, `base_color`, `mask_r/g/b_color`, `suitable_for` pointing at the cabin unit. Stock colours are `color<N>.sii`. No truckpaint evidence either way.
- **DLC identifier:** none visible; neither manifest has `dlc_dependencies`.
- **Still unknown:** cabin def contents, locator names, accessory def format for addons on this car, cab/bed model files.

Consequences for this project:
- Template moved to `src/mod/def/vehicle/car/ford.f150_23/accessory/TODO_SLOT/`; `suitable_for` set to the cabin unit (INFERRED; cabin vs chassis is open).
- `config/v1.json` `scs.model_path` = `vehicle/car/upgrade/f150_bed_shell`.
- No vanilla bed slot, so the shell likely needs a new slot type declared by this mod (Pickup Load Pack precedent), which means editing or overriding the dealer or cabin def. **Conflict risk:** another mod that edits the same cabin/dealer defs or declares the same slot name will collide; test with other F-150 mods disabled.

## Paint mechanism

Status: car `paint_job` system observed (OBSERVED-IN-MODS above). How an addon follows body colour is still OPEN; the mechanism for non-paint-job accessories is UNKNOWN.

- Documented: `accessory_paint_job_data` (paint_job_mask .tobj, mask_r/g/b_color, base_color, base_texture_override for the "truckpaint" material, flipflake, airbrush; colormask applies blue, green, red) https://modding.scssoft.com/wiki/Documentation/Engine/Units/accessory_paint_job_data and `vehicle_paint_job_accessory` (data_path, wear, colour overrides) https://modding.scssoft.com/wiki/Documentation/Engine/Units/vehicle_paint_job_accessory.
- Not documented: how an addon (mirror, fender, shell) follows body colour; the material name or flags. A community hint places accessory paint info under `paint_job/accessory/` (https://steamcommunity.com/app/227300/discussions/0/1640915206449027184/).
- Resolve: unpack the DLC archive, find an F-150 addon that matches body colour (mirrors, bumper, roof rack on the Bronco), and copy its material and paint-job wiring pattern for the shell. Test two body colours in game.
- Unconfirmed skeleton (INFERRED from attribute tables only): `accessory_addon_data : <name> { name, price, part_type: aftermarket, suitable_for[]: "<f150 unit>", exterior_model: "<.pmd>", look, variant }`.

## Bed dimensions

Dealer data for the 2023 F-150 (https://www.greghublerford.com/2023-ford-f-150-bed-sizes2023-ford-f-150-bed-size/), not Ford:

| Bed | Length | Width | Height |
| --- | --- | --- | --- |
| 5.5 ft | 67.1 in (1.70 m) | 50.6 in (1.29 m) | 21.4 in (0.54 m) |
| 6.5 ft | 78.9 in | 50.6 in | 21.4 in |
| 8 ft | 97.6 in | 50.6 in | 21.4 in |

- 50.6 in is stated as the wheel-well width by https://offroadtents.com/blogs/news/ford-f150-bed-sizes-complete-guide-to-truck-bed-dimensions; the dealer page does not say. Inside vs outside length and rail height are unspecified.
- Which bed the DLC models is UNKNOWN. A Lariat is probably a SuperCrew with the 5.5 ft bed (INFERRED).
- `config/v1.json` currently uses 1.70 m length x 1.95 m outer rail-to-rail width (cab height above rails 0.50 m, rail height 1.44 m). UNVERIFIED. 1.65 m (≈ 65.2 in) is the published inside box width; the outer width the shell base sits on adds the rail caps (estimated ~0.15 m per side against a 2.03 m body). `bed.inside_width_published` keeps the 1.65 m figure. Replace all of these with in-game measurements.

## Workshop packaging facts

- Structure: one or more packages plus `versions.sii`; each package needs `manifest.sii`, a description file, an icon file and the mod data. `base` always mounts; `dlc_`-prefixed folders mount only with that DLC; extra DLC dependencies go in the manifest `dlc_dependencies` array (https://modding.scssoft.com/wiki/Documentation/Tools/SCS_Workshop_Uploader/Workshop_mod_structure). The F-150 is DLC content, so a dependency is likely needed (INFERRED).
- `versions.sii`: unit `package_version_info` with `package_name`, optional `compatible_versions[]`, `informational`; only one unit may omit versions (universal fallback) (https://modding.scssoft.com/wiki/Documentation/Engine/Units/package_version_info).
- Upload: Workshop Uploader installs via `steam://install/421800`; type tag required, description 50+ bytes, visibility Private/Friends/Public, validation errors block upload, first upload requires Workshop terms (https://modding.scssoft.com/wiki/Tutorials/SCS_Workshop_Uploader/How_to_upload_new_mod%3F).
- manifest.sii field list, mod icon size, preview image size: UNKNOWN (not found on the wiki pages read).

## Open gates

| # | Unknown | Resolve on gaming PC by |
| --- | --- | --- |
| 1 | F-150 def path and unit names | resolved-pending-DLC-confirmation: `def/vehicle/car/ford.f150_23/`, cabin `pckup4d_55.ford.f150_23.cabin`, chassis `4d55_awd.ford.f150_23.chassis`. Confirm in the extracted DLC archive |
| 2 | Bed slot: no vanilla slot seen | Likely need to declare a NEW slot, which means editing or overriding the dealer or cabin def. Conflict risk with other mods touching those defs. Confirm in extracted defs; compare with the `load_bed` precedent |
| 3 | How `load_bed` and new accessory types are declared | Subscribe to the Pickup Load Pack for reference, inspect only structure, do not copy |
| 4 | Body-colour matching for addons: car `paint_job` system observed; how addons follow body colour open | See Paint mechanism; match a vanilla addon under `paint_job/`, then test two colours |
| 5 | Real bed dimensions and origin/axes | Measure the F-150 bed model or locators in Blender after import; update `config/v1.json` |
| 6 | Blender Tools 2.4.1 and Conversion Tools 2.21 handle Road Trip assets | Import the vehicle model, export a tiny original mesh, convert, load in game |
| 7 | manifest.sii fields, icon and preview sizes, ATS build | Check a working Workshop mod's manifest, the Uploader validator output, and the in-game version string |
| 8 | Animated accessories on cars (Phase 2b pop-top): supported at all, and which triggers (parking brake, beacon, speed) | Search the extracted F-150 and other car defs for animated addons and their controller/trigger fields; compare with an animated truck-accessory mod |
