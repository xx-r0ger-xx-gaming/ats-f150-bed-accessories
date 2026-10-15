# Roadmap and reproducible workflow

All checklist items start unverified. This roadmap records intent, not completed implementation.

## Phase 0 — Feasibility and toolchain

- [ ] Identify exact ATS build, Road Trip distribution/version, F-150 source/version, required dependencies and permissions.
- [ ] Establish whether this vehicle is player-drivable and exposes mod-accessible accessory slots, locators and definitions. Record evidence and relevant paths privately where necessary.
- [ ] Validate dependency load order, model reference rules, material/paint mechanism, collision behavior and any Road Trip-specific restrictions.
- [ ] Determine whether a shell can be added without replacing or distributing protected vehicle assets. If no usable slot exists, document supported alternatives and their scope before choosing one.
- [ ] Measure bed width/length/rails, cab clearance, tailgate travel, origin, axes and units from permitted references. Do not guess a production fit.
- [ ] Install/pin Blender 3.6 LTS patch and compatible SCS Blender Tools; select Conversion Tools for the installed ATS version and archive tooling for the actual format.
- [ ] Record versions, download URLs, hashes, machine/GPU/driver and private tool paths. Check licenses.
- [ ] Confirm Blender launches, SCS add-on enables in background mode, and a tiny original mesh exports, converts and loads in the intended game setup.
- [ ] Run a Surface Eevee 720p/32-sample preview; record time and failures. Check CPU Cycles fallback if needed.

Deliverables: docs/compatibility.md, measured configuration, tool manifest, small integration proof, logs/screenshots and a go/no-go decision. If unsupported, stop production modeling and record the exact blocker.

## Phase 1 — V1 bed shell

- [ ] Build original shell geometry: rails, roof, side panels/windows and rear opening; fit the measured bed and cab.
- [ ] Establish color matching using the vehicle's verified paint/material mechanism; compare at least two body colors in game.
- [ ] Create UVs, materials, original/licensed textures, suitable detail levels and collision only as required by the validated workflow.
- [ ] Configure SCS root/parts/locators and accessory definitions using actual supported identifiers.
- [ ] Validate normals, transforms, scale, missing texture paths and unique names. Check no cab/tailgate/wheel clipping.
- [ ] Run full export/conversion/package/test pipeline. Compare vehicle behavior with and without the accessory.

Deliverables: reproducible .blend source, scripts/configuration, V1 mod package, dependency/version manifest, preview images, test report and asset provenance list.

## Phase 2 — Pop-top / slide-in camper

- [ ] Choose pop-top, slide-in, or separate variants after V1 passes.
- [ ] Check supported animations/state switching before promising a deployable roof; use a documented static variant if necessary.
- [ ] Design original camper body, windows, entry and roof; validate bed clearance, overhang and collision.
- [ ] Assess weight/handling implications; reuse base physics only when tests support the result.

Deliverables: design decision, new source/configuration, tested variants, renders and updated compatibility/provenance reports.

## Phase 2b — Animated pop-top (after V1)

Goal: park, set the parking brake, and the pop-top lid rises over a few seconds; release the brake and it lowers before driving, so the roof is never up on the road. Rudimentary is fine: one lid part moving vertically with the canvas walls scaling/unfolding underneath (the existing open and closed poses are the end states).

- [ ] Gate (gaming PC): confirm whether car accessories (`def/vehicle/car/`) in Road Trip support animated accessories, and which triggers exist (parking brake, beacon/light switch, speed). UNVERIFIED; truck mods commonly use parking brake or beacon triggers, but cars may differ.
- [ ] If supported: author the lid animation, tie open to parking brake on, close on release; add a speed > 0 close as a backstop if speed is an available input.
- [ ] If not supported: ship open and closed as separate accessory variants swapped in the garage, and document the limitation.
- [ ] Test: no clipping through the cab or rack at any frame, closed state on load, behaviour after save/reload.

Deliverables: trigger evidence from the extracted defs, animation source, in-game test notes or the documented static fallback.

## Phase 2c — Overland bed rack (optional accessory)

Preview exists (`bed_rack`, render-only): generic, unbranded bed rack fitted to the measured reference bed (rail 1.337 m, bed 1.650 x 1.632 m inside, crossbars 0.02 m below the cab roof at 0.568 m above the rails), with a rooftop tent and overlanding gear.

- [ ] Multi-accessory stacking on one slot (rack + tent + boards + cans as separately selectable items) is UNVERIFIED for Road Trip cars. Plan: ship **fixed combinations** as separate accessories in the same slot, e.g. bare rack, and rack + tent + gear (`camper.loadout`: `bare` / `full`), swapped in the garage.
- [ ] If the gaming-PC check shows cars support several addon slots or `require`/`conflict_with` chains, revisit separate gear items; until then do not promise mix-and-match.
- [ ] Same gates as V1: bed slot, paint (rack is fixed black, no body-colour match needed), export/convert/load, no cab or tailgate clipping in game.

## Class C motorhome (moved)

Class C motorhome lives in [ats-hd-class-c-rv](https://github.com/xx-r0ger-xx-gaming/ats-hd-class-c-rv).

## Pipeline contract

Implement scripts with the following interfaces; these examples do not work until the scripts exist. In PowerShell, set $blenderExe to the pinned local Blender executable. Scripts parse their arguments after `--`.

```powershell
& $blenderExe --background --factory-startup --python-exit-code 1 --python scripts/build_scene.py -- --config config/v1.json --output build/v1.blend
& $blenderExe --background build/v1.blend --python-exit-code 1 --python scripts/export_scs.py -- --output build/mid
& $blenderExe --background build/v1.blend --python-exit-code 1 --python scripts/render_preview.py -- --profile surface --output renders/v1-preview.png
```

1. **Preflight:** Validate required inputs, pinned versions, add-on availability, output paths and permissions. Keep private assets outside distributable trees.
2. **Build:** Generate the same scene from the same configuration: explicit units, transforms, object names, material setup, fixed random seeds and saved .blend source.
3. **Export:** Use the pinned SCS add-on's verified operators to write SCS intermediate formats. Include only original project resources and minimal supported dependency references.
4. **Convert:** Use a project-specific staging area and the selected Conversion Tools' documented convert.cmd workflow. The official documentation describes input under base/ and output under rsrc/base/@cache; verify those paths for the selected version. Preserve the conversion log and fail on errors or missing output. Never clean shared tool/game directories blindly.
5. **Render:** Surface profile uses Blender 3.6 Eevee, 1280×720, 32 render samples and simple lighting. Gaming profile uses explicitly recorded quality settings and a supported renderer/device. Record camera, lighting, color management and resolution. Headless Eevee still needs a working graphics environment.
6. **Package:** Stage converted content at the mod archive root with correct relative paths, manifest and any required definitions. Use the archive format/tool supported by the target game; an ordinary mod ZIP/.scs may be sufficient where supported, while game HashFS extraction is a separate operation. Never package raw extracted dependencies. Produce a SHA-256 manifest and content inventory.
7. **Test:** Install reversibly into the actual test profile's mod location, record load order and launch the target version. Save relevant game.log.txt evidence and screenshots. Do not infer success solely from process exit status.
8. **Release:** Rebuild from documented inputs on the gaming PC; compare output inventories/hashes. If archive timestamps cause differences, normalize them or document why byte-for-byte identity is not yet achieved. Include known issues, dependency requirements, tested versions and provenance.

## In-game acceptance checklist

- [ ] Mod appears/enables and accessory can be selected, removed and reloaded after saving.
- [ ] Existing interior, drivetrain and controls behave correctly; no new relevant errors in game.log.txt.
- [ ] Paint matches under multiple lighting conditions and body colors; textures are present.
- [ ] Exterior/interior cameras, mirrors, windows and attachment alignment work at near/far distances.
- [ ] No unwanted collision or clipping; test tailgate/other animations if exposed.
- [ ] Drive, steer, brake, reverse, traverse bumps and check clearance; compare stock baseline.
- [ ] Record performance and stability with the intended dependencies/load order.
- [ ] Fresh package contains only project-authored or redistribution-permitted content.

## Release evidence

Each test report should record date, machine, ATS/Road Trip/F-150 versions, Blender/add-on/converter versions, source revision, configuration hash, package hash, steps, expected/actual outcome, relevant logs, screenshots and unresolved limitations. Keep personal paths and proprietary asset content out of public reports.
