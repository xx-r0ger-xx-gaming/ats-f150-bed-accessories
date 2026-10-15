# Test results

One block per test run. Keep personal paths and any proprietary asset content out of this file.

## Run record

| Field | Value |
|---|---|
| Date | |
| Machine (surface / gaming-pc) | |
| ATS version | |
| Road Trip DLC / F-150 version | |
| Blender / SCS Blender Tools / Conversion Tools | 3.6.23 / v2.4.1 / 2.21 |
| Source git revision | |
| Config hash (`config/v1.json` sha256) | |
| Package hash (`dist/SHA256SUMS`) | |
| Load order / other mods | |
| Profile used | |

## Status by phase (keep separate)

| Phase | Status (not run / pass / fail / blocked) | Evidence (log, screenshot) | Notes |
|---|---|---|---|
| Build (.blend) | | | |
| Export (SCS intermediate) | | | |
| Render preview | | | A render is not proof of a working mod |
| Convert | | | |
| Package | | | |
| In-game load | | | |

## In-game checklist

| Check | Result | Evidence | Notes |
|---|---|---|---|
| Mod appears and enables in Mod Manager | | | |
| Accessory selectable, removable, survives save/reload | | | |
| No new relevant errors in game.log.txt | | | |
| Existing interior, drivetrain, controls unaffected | | | |
| Paint matches in multiple lighting and body colors | | | |
| Textures present | | | |
| Cameras, mirrors, windows, alignment near/far | | | |
| No unwanted collision or clipping | | | |
| Drive/steer/brake/reverse/bumps, clearance vs stock | | | |
| Performance and stability | | | |
| Package contains only original or redistributable content | | | |

## Unresolved limitations

- Preview renders only (not in-game evidence): the pickup variants now render on a downloaded CC BY reference truck (render-only, gitignored, not packaged; README "Credits"). Its scale comes from an assumed 5.89 m overall length, so the measured bed/rail/roof figures (rail 1.337 m, bed 1.650 x 1.632 m inside, roof 0.568 m above the rails) are model measurements, not Road Trip F-150 measurements; the V1 shell is refitted to them for renders only and `config/v1.json` stays UNVERIFIED.
- 2026-10-15 bed fit: all bed-mounted variants now fit to one dense ray-cast measurement of the reference bed (`config/bed.json`, `scripts/measure_bed.py`; tapering rail caps 1.853 -> 1.748 m, bowed tailgate face -1.844 centre / -1.762 at x 0.80, bed front wall 2 cm above the rail cap, cab back +0.096 leaning 0.037 m/m). `scripts/check_fit.py --all`: no rigid camper part intersects the truck mesh in any of the 6 poses (only rail seals / rubber pads, 1-8 mm into the rail cap ribs); shell, canopy and pop-top sides 0-11 mm inside the rail-cap edge (pop-top 5 mm proud over the last 5 cm where the cap rolls off), cab gap 4.0-4.1 cm on the centreline, rear within ~1 cm of the tailgate face. Still reference-model numbers, not the in-game truck (`profiles.ats_f150_ingame` is empty).
- Reference truck `tailgate: down` is not supported (closed / removed only).
