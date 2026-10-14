# Claude Code entrypoint

Read README.md and docs/roadmap.md before implementation. The task is an ATS Road Trip Ford F-150 camper mod: V1 color-matched bed shell, followed by a pop-top/slide-in camper and then an F-150-cab-based Class C RV.

## First actions

1. Inspect existing project files and preserve user work.
2. Resolve the exact ATS/Road Trip/F-150 versions and asset ownership. Record them in docs/compatibility.md.
3. Confirm an accessible accessory slot, locator, definition path, and supported asset reference mechanism. A modding toolchain does not prove Road Trip supports these changes.
4. Pin Blender 3.6 patch, SCS Blender Tools, Conversion Tools, archive tools, and graphics driver versions; perform a tiny original model export/conversion/load test.
5. Proceed to the shell only after the feasibility gate passes. Ask for missing vehicle measurements or product identity when local evidence cannot establish them.

## Automation rules

Claude Code should drive Blender with Python and background command-line runs. Author deterministic scripts for geometry, materials, scene setup, saving, export, rendering, and validation. Explicitly enable/configure the SCS add-on in the background process; do not rely on interactive preferences or selection state. Check operator availability and required context against the pinned add-on. Do not invent an SCS export API.

Use project-relative paths and configurable local executable/tool paths. Fail on missing inputs, unsupported versions, or export errors. Save source .blend files before export. Capture stdout/stderr, exit codes, tool versions, configuration and output hashes. Commands in the roadmap are planned interfaces until the scripts are implemented.

On the Surface Pro use simple geometry and Eevee 1280×720, 32 render samples. Check actual Intel GPU/driver support first. Cycles CPU is a render fallback only when Blender can run. Use the gaming PC for expensive renders and game validation.

## Scope and evidence

- V1 is a bed camper shell accessory with body-color paint matching; determine how the base vehicle exposes paint rather than hardcoding an unverified shader.
- Preserve installed drivetrain/interior/physics references when supported. Do not claim every later RV change is cosmetic.
- Use original geometry and permitted textures. Never include proprietary SCS or third-party dependency assets in Git or release packages.
- Do not modify installed game archives. Use a separate test profile and reversible mod deployment.
- Keep implementation, conversion, rendering and actual in-game validation statuses separate. A render is not proof of a working mod.
- Record limitations and blocked gates; do not silently substitute a different vehicle or claim unsupported Road Trip behavior.
- Finish each phase with the roadmap deliverables, evidence and reproducible instructions. Update docs when tested versions or assumptions change.
