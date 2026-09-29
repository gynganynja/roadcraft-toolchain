# Build pipeline and SDK tools

How the vehicle mods here are built without the editor's user interface, and the traps met on the way.
The mod projects (`<project>/tools/build.py`, `prepare.py`, `create_models.py`, `truck_bro.py`,
`validate.py`, `install.py`, `toolchain.py`) follow one layout; copy the newest one (the buggy) when
starting a vehicle. Every step is bound to a toolchain recipe (`run build|test --apply`, `pin`), so a
candidate carries receipts for what built and checked it.

## Stages

| Stage | Tool | Success check | Grade |
|---|---|---|---|
| Textures | `tools/bin/TextureConverter/TextureConverter.exe <tga> <pct> --usage <MD, MNM, MSCRGHAO, MD+MT, MH>` with `converter.config.ps` = the descriptor | output exists; header mip count | Build |
| Models | Blender 5.0 in the background (`--factory-startup`) builds the body and wheel `.blend` files (rig, LODs, collision, locators) | the script's completion marker | Build |
| Import | `tools/bin/editor_build_tools/asset_importer/asset_importer.exe -p <project> -s <blend> --output <mods_source>/models/mods --exp_opt export_options.ps --blender_exe <blender>` | log line `Asset importing successfully finished` | Build |
| Classes | the batch editor (a private copy of IntegrationStudio with a batch plug-in, hidden) generates `autogen_dw/...` from the BROs | `Task <name> was successfully finished`, generated files present, not the exit code | Build |
| Package | `tools/bin/ModPakBuilder/mod_pak_builder.exe --project <p> --resource-roots-file <roots> --output <pak> --mod_file <mod>` | exit 0 and the pak exists | Build |
| Retail export | the editor package's `autogen_dw/` brands re-exported as the flattened `ssl/<brand>_<suffix>` brands the retail game discovers (the Mod Manager's export naming) | the export audit | Build, Game (the mods appear in the store) |
| Install | copy to `<game>/root/mods/<mod>.pak`; game and editor closed; keep the previous bytes and a receipt | hash of the installed file | Build |

A project for the tools is a relocatable SDK project folder (`.project` referencing the game's
`root/.project`, `mods-dir`, configs); build into it, never into the editor's own working copy.

## Traps

| Trap | Grade |
|---|---|
| The undocumented CLI tools (`pct_resource_gen`, `tpl_asset_import`, ...) open a modal crash dialog on wrong arguments: do not probe them with `--help` | Build |
| Batch class generation can fail with `ModelDisallowedTypeException` (class database refresh race); retrying with the previous generated files left in place succeeds, sometimes only after several attempts (each gets further; allow five with a pause); check the success line, not the exit code | Build |
| The hidden batch steps refuse to run while an IntegrationStudio session of the owner's is open | Build |
| An editor run started within about 40 s of class generation hot-reloads the fresh classes and the engine asserts; wait about three minutes | Build (Roamer 105) |
| The generator accepts unknown or incomplete settings silently (e.g. a suspension collection without its flag): read the compiled class (`lint-bro --class`) | Build |
| `mod_pak_builder` resolves references only inside the mod project: copy any shipped resource the mod uses into it under a mod name | Build (Roamer 105) |
| The SDK asset exporter hangs on meshes without a UV map (the EX5600 source had 614 such objects): the builds refuse a mesh without exactly one UV map, and drop colour attributes | Build |
| Blender's "Cannot change old file (file saved with @)": a stale `<file>.blend@` blocked the rename after a save; delete it and save again, with retries | Build (Roamer 105) |
| The editor's Documents folder may be OneDrive-redirected: its working copy and built mods live there, and sync is a suspect in file-lock failures | Build |
| Blender: the SDK accepts 4.5 / 5.0; a community guide reports 5.1 breaking armatures; do not point the SDK at 5.2 | SDK, community |
| The toolchain's native-process gate matches any process with "blender" in its name, including MCP helpers; headless build steps are declared `native: false` and check for the game and editor themselves | Build |
| Class generation launches IntegrationStudio (hidden): it counts as an editor run, so it waits until the owner is not using the PC (queue it for when the game closes) | Owner's instruction |

## Checks before installing

The shared recipe helper `roadcraft.vehicle_workflow.enhance_recipe` now wires
source, compiled and final checks into the adapter pipeline. New projects can
start with `roadcraft vehicle-init`, fill their explicit source/adapter contract,
and use `vehicle-recipe` to generate a new pinned recipe. It is a workflow
starter; source art and vehicle-specific rig generation still belong to the project.

Reviewed isolated steps can opt into `--incremental` with complete output
trees for compiler sidecars. Receipt hashes and existing output bytes must
verify before reuse. The first successful incremental build establishes the
cache; shared checks continue running. `jobs-summary` reports actual elapsed
times and reused stages. These commands do not establish driving acceptance.

**Build:** When adding or merging a CLI dependency, include its shared module
in `vehicle_workflow.RUNTIME_FILES`, even if a vehicle build does not call its
subcommand: importing the CLI loads it. The onboarding integration required
adding `onboard.py`. The regression test
`VehicleWorkflowTests.test_new_cli_dependency_change_requires_recipe_regeneration`
checks that a change to that module rejects the old recipe before execution.
Generate a new pinned recipe after shared runtime changes; passing preflight
does not mean the vehicle has been rebuilt or driven.

1. `roadcraft lint-bro <bro> --class <auto_mod.cls> --tpl <body.tpl>`: no errors.
2. The project's rig audit on the exported model (bone positions, parents, axes).
3. The project's static validation: authored files current, compiled class carries the settings,
   package members equal the built files, textures and mips.
4. `roadcraft suspension --axle ... --share ...` for each axle: off the stops in every case, including
   `measured`.
5. Nothing above proves how it drives; the owner's drive is the acceptance.

## Testing in the editor (when the owner allows it)

The Roamer 105 project drove its candidates in the editor's play mode without the owner (its
`tools/WORKFLOW_TOOLS.md` describes the runner). What that taught (Build):

- Engine-side input override (the input `State` method) drives engine, parking brake, low range,
  pedal and steering; key presses went to the wrong window when the viewport lost focus.
- A connected wheel controller overrides the engine-side requests: keep it centred or unplugged.
- Re-assert the parking brake off with every input; a speed plateau was once a re-engaged brake.
- The suspension probe's `travel` / `maxTravel` are constants; use `liftAlongSuspensionMetres`.
- Screenshots come from the engine's `SaveScreenShot` (BMP under `root/bin/pc`); window grabs were
  refused or showed the editor.
- Editor play mode is not the retail campaign: lamps, store registration and saves still need a
  retail drive.
