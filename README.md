# ATS Road Trip — F-150 Camper Project

Project brief recorded October 14, 2026. Start with [CLAUDE.md](CLAUDE.md), then follow [the roadmap](docs/roadmap.md).

## Design intent

Build an original camper mod for the Ford F-150 available in the intended ATS Road Trip setup. V1 is a removable, color-matched bed camper shell accessory. Later versions explore a pop-top/slide-in camper and other bed accessories. The F-150-cab-based Class C motorhome needs its own chassis, so it moved to its own repo, [ats-f150-class-c](https://github.com/xx-r0ger-xx-gaming/ats-f150-class-c), on October 15, 2026.

Reuse the installed vehicle's drivetrain, interior, controls, and physics through supported references where possible. This is a design goal, not a verified capability.

## Concept reference

User-supplied visual reference from the prior design conversation, added October 14, 2026. It is kept private at `local-reference/f150-camper-concept.png` (gitignored) because it contains third-party logos; copy it there manually on each machine. It shows a color-matched shell, overland canopy, pop-top, slide-in camper, and a small truck-based Class C camper with interior/rear views (the Class C is now in [ats-f150-class-c](https://github.com/xx-r0ger-xx-gaming/ats-f150-class-c)). The project targets a compact F-150-based camper. This is visual inspiration, not measured geometry, proof of game support, or a distributable game asset; it must never be included in a mod package. The overland canopy is an optional future idea, not an additional committed phase.

## Status and source

A working scripted pipeline exists: build (Blender, headless) → export (SCS Blender Tools) → convert (SCS Conversion Tools) → package → deploy, run end to end with `scripts/run_pipeline.ps1`. It was verified on the Surface Pro on October 14, 2026. It has **not been tested in game**: a successful export, conversion or package is not proof the mod loads or works in ATS Road Trip. Details live in [docs/compatibility.md](docs/compatibility.md) (tested version matrix and attachment evidence), [docs/gaming-pc-setup.md](docs/gaming-pc-setup.md) (setting up the gaming PC for rendering and game validation) and [docs/test-results.md](docs/test-results.md) (render/export/conversion results and known issues).

Source: user brief and readable messages from “F150 Mod Design Thoughts” (conversation `6ace9870-c7ec-83e8-8854-8cd86d2efe18`). Retrieved assistant messages were reference placeholders; unavailable details and images have not been reconstructed.

Exact ATS build, Road Trip product/mod identity and version, F-150 asset owner, vehicle definition names, bed dimensions, and permitted attachment mechanisms may still be unresolved; check docs/compatibility.md before relying on any of them.

## Workstations

| Machine | Intended work | Acceptance check |
| --- | --- | --- |
| Surface Pro, Intel integrated graphics | Documentation, scripts, simple geometry, lightweight modeling; Eevee previews at 1280×720 and 32 render samples | Identify GPU and driver, check Blender 3.6 requirements, open a test scene and render successfully |
| Gaming PC | Detailed modeling, high-quality renders, conversion and ATS testing | Record hardware and tool versions; confirm export and game load |

Keep subdivision, textures, lights, and scene complexity low on the Surface. Intel integrated graphics alone does not establish compatibility or Cycles GPU support. If Eevee fails, try Cycles on CPU only after Blender itself can launch; CPU rendering does not bypass Blender's graphics requirements. Move work to the gaming PC if needed.

## Official tools and documentation

- [Blender 3.6 LTS downloads](https://www.blender.org/download/lts/3-6/) and [archived binaries](https://download.blender.org/release/Blender3.6/). Pin the exact patch release. This compatibility baseline reached end of support in June 2025; it is not a currently supported LTS.
- [Blender requirements](https://www.blender.org/download/requirements/) and [version compatibility notes](https://developer.blender.org/docs/release_notes/compatibility/). Check the chosen release against the actual GPU and driver.
- [SCS Blender Tools downloads and compatibility](https://modding.scssoft.com/wiki/Documentation/Tools/SCS_Blender_Tools/Download) and [official repository](https://github.com/SCSSoftware/BlenderTools). The download page checked October 14, 2026 lists 2.4.1 for Blender 3.2.x–3.6.x. Verify installation and export rather than assuming compatibility with newer Blender.
- [SCS Conversion Tools](https://modding.scssoft.com/wiki/Documentation/Tools/Conversion_Tools). Select the release matching the installed ATS version; the page currently lists 2.21 for ATS 1.58+ and older releases for earlier versions. Record the chosen combination and recheck when upgrading.
- [Official Game Archive Extractor](https://modding.scssoft.com/wiki/Documentation/Tools/Game_Archive_Extractor) for permitted local inspection. Use the tool appropriate to the archive format; do not assume any `.scs` file is an ordinary ZIP.
- [SCS modding documentation](https://modding.scssoft.com/wiki/Documentation), [SCS Blender Tools documentation](https://modding.scssoft.com/wiki/Documentation/Tools/SCS_Blender_Tools), and [official tools index](https://modding.scssoft.com/wiki/Documentation/Tools).

## Planned structure

Most of the paths below now exist. `tools/` (portable Blender, SCS Blender Tools, Conversion Tools) is gitignored, as are `build/`, `dist/`, `logs/`, `renders/` output and `config/tools.local.json`. 

```text
CLAUDE.md                 Agent entrypoint and constraints
README.md                 Brief, hardware guidance, official links
docs/roadmap.md           Phases, checklist, pipeline and acceptance
docs/compatibility.md     Tested version matrix and attachment evidence
docs/gaming-pc-setup.md   Gaming PC setup for renders and game validation
docs/test-results.md      Game/render/export results and known issues
config/                   Dimensions, material colors, build settings
src/blender/              Original .blend source
src/textures/             Original or properly licensed textures
src/mod/                  Original definitions and supporting files
scripts/                  Build, export, render, package, validate
build/                    Generated intermediates and converted output
dist/                     Distributable mod and release manifest
renders/                  Preview and final images
logs/                     Blender, conversion and game evidence
tools/                    Portable Blender and SCS tools; gitignored
local-reference/          Private permitted references; excluded from Git
```

Ignore local-reference/, extracted game assets, tool binaries, personal paths/configuration, temporary builds and logs in version control when those directories are introduced. Review releases separately: an ignored file can still accidentally enter a package.

## Asset policy

Create original geometry and textures. Do not commit, upload, or redistribute proprietary SCS assets, extracted vehicle models, interiors, textures, sounds, or third-party Road Trip/F-150 assets without explicit redistribution permission. Keep permitted inspection local and private. Reference installed dependencies where supported; document required versions instead of bundling them. Archive extraction is not permission to redistribute. If supported integration requires shipping protected assets, stop that approach and record the limitation.

## Disclaimer

Unofficial fan-made mod. Not affiliated with, sponsored by, or endorsed by Ford Motor Company or SCS Software. Ford and F-150 are trademarks of Ford Motor Company; American Truck Simulator is a trademark of SCS Software. Names are used only to identify the vehicle this mod fits. No Ford or SCS logos, models, or game assets are included.

## Credits

Preview renders of all variants use a third-party truck model as a stand-in base vehicle. It is used only for those preview renders: it is downloaded by hand into `tools/reference-truck/` (gitignored), never committed, never exported, and not included in the mod or any release package.

"2023 Ford F150 Lihtning Platinum" (https://skfb.ly/pFtDT) by tonielpro520 is licensed under Creative Commons Attribution (http://creativecommons.org/licenses/by/4.0/). Modified: badges removed, repainted, camper added.
