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
- `class_c` renders on a reference cab-chassis built for previews only: the crew-cab model cut behind the cab plus procedural frame, axle and copied dual rear wheels (a render construct, not a measured chassis cab).
- Reference truck `tailgate: down` is not supported (closed / removed only).
