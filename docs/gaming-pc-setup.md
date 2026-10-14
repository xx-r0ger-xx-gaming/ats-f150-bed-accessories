# Gaming PC setup and first in-game test

Nothing here has run against the real game yet. Items marked UNVERIFIED are assumptions to confirm on the gaming PC; write what you find into `docs/compatibility.md`.

## 1. Clone and configure

```powershell
git clone https://github.com/xx-r0ger-xx-gaming/ats-f150-camper.git   # adjust to the real remote
cd ats-f150-camper
copy config\tools.example.json config\tools.local.json
```

Edit `config/tools.local.json`: set `"machine": "gaming-pc"`, and the real `ats_mod_dir` / `ats_game_log` (normally `C:/Users/<you>/Documents/American Truck Simulator/mod` and `.../game.log.txt`). Leave the `tools/...` entries as they are.

## 2. Fetch the pinned tools

```powershell
powershell -ExecutionPolicy Bypass -File scripts\fetch_tools.ps1
```

Downloads into `tools/` (gitignored), sha256-verified: Blender 3.6.23 portable (`e3296eba...c54f3b`), SCS Blender Tools v2.4.1 (`c38df76f...226649`), SCS Conversion Tools 2.21 and the SCS Game Archive Extractor 1.55 (`scs_extractor_1_55.zip`, from modding.scssoft.com/wiki/Documentation/Tools/Game_Archive_Extractor). SCS publishes no hashes for the last two; the pinned values are what we downloaded on 2026-10-14.

Check: `python scripts\preflight.py --stage deploy` (all PASS except possibly the game log, which only exists after the first launch).

## 3. Extract the Road Trip DLC definitions (private)

The extracted data is proprietary: it stays in `local-reference/` (gitignored, and `package.py` refuses any file whose hash matches something in there). Never commit or copy it elsewhere.

```powershell
mkdir local-reference\roadtrip
copy "<ATS install>\dlc_*.scs" ...   # find the Road Trip: Ford archive (UNVERIFIED name; look for dlc_ files in the install dir)
tools\scs_extractor.exe "<ATS install>\<roadtrip archive>.scs" local-reference\roadtrip
```

Read-only on the install: do not modify the game archives.

## 4. Find the facts needed to fill the TODOs

Record each answer in `docs/compatibility.md` with the file it came from.

| Need | Where to look in `local-reference/roadtrip` |
|---|---|
| F-150 unit / def path | `def/vehicle/truck/*` (find the F-150 folder and its `.sii`) -> replaces `TODO_F150_UNIT` and `TODO_F150_UNIT_NAME` |
| Accessory slot types and locators | the truck's `accessory/` subfolders, and the model `.pmd`/`.pit` locators for the bed (replace `TODO_SLOT`) |
| How stock paintable addons take body color | open a stock painted accessory `.sii` and its model's `.mat` files; note the material effect and paint/look tokens. Adjust `config/scs_materials.json` to match; do not hardcode a guess |
| DLC package name for `dlc_dependencies` | the `dlc_*.scs` file name in the install dir (UNVERIFIED pattern `dlc_<name>`); replace `TODO_ROADTRIP_DLC_ID` in `src/mod/manifest.sii` |
| Bed dimensions | inspect the stock bed model (extractor output) only for measurement, or measure in game with a known-size reference. Update `config/v1.json` `bed.*`. Do not import or copy the stock mesh into the project |

## 5. Fill the templates

1. Rename `src/mod/def/vehicle/truck/TODO_F150_UNIT/accessory/TODO_SLOT/` to the real paths.
2. Edit `f150_camper_shell.sii`: unit type/name, `suitable_for`, `icon`, `look`, `variant`, price, etc. (attribute meanings: modding.scssoft.com `accessory_data` and `accessory_addon_data`).
3. Edit `src/mod/manifest.sii`: replace the DLC id.
4. `python scripts\package.py` will refuse to run until no `TODO` markers remain; `--allow-todo` is for dry runs only.

## 6. Run the pipeline

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_pipeline.ps1 -Profile gaming
```

Stops on the first failure; logs in `logs/pipeline-*.log`, run records in `logs/*.json`, hashes in `dist/SHA256SUMS` and `dist/inventory.json`. Output: `dist/f150_camper_shell.zip` (local install) and `dist/f150_camper_shell/` (Workshop layout, not uploaded).

## 7. In-game test (separate profile)

1. In ATS create a NEW profile (no shared saves/mods with the main one).
2. `python scripts\deploy.py` (or `run_pipeline.ps1 -Deploy`) installs `f150_camper_shell.zip` into the mod dir and records it in `logs/deploy-manifest.json`.
3. Start ATS, enable the mod in the Mod Manager of the test profile, load a game, buy/select the F-150, open the accessory shop.
4. Work through the acceptance checklist in `docs/roadmap.md`.
5. `python scripts\deploy.py --collect-log` copies `game.log.txt` into `logs/` and lists mod/error lines (nonzero exit if the mod appears with an error).
6. `python scripts\deploy.py --uninstall` removes exactly what was installed (hash-verified).
7. Fill in `docs/test-results.md`. A render or a clean log is not proof; the accessory must visibly appear, match paint, and survive save/reload.
