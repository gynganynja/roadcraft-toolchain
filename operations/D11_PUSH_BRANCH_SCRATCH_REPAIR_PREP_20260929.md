# D11 push-arm scratch repair preparation — 2026-09-29

The pinned no-save Blender 5.0.1 and 5.2.0 probe reconstructed the missing
left and right push-arm base/tip bones in memory and reparented the existing
tilt branches. It matched 386 shared static hierarchy paths within `2.27e-6`.
That result did not produce a USF or prove skin, bind, animation or game parity.
The complete measurements and source pins are in
`D11_PUSH_BRANCH_IN_MEMORY_20260928.md`.

The authoring diagnostic now accepts `--push-branch-scratch-repair` only for the
accepted base `cat_d11t` source, reviewed Blender version and reviewed SDK.
Before starting Blender it verifies the historical Blend, repaired USF,
push-branch host and worker, and the worker's two Python dependencies. The
Blender helper rechecks those module pins, validates the full in-memory result,
and would record whether all eight target hierarchy paths appear in its
scratch USF. It would then compare the full USF with the repaired build input;
the native-Blend export gate remains closed. The helper never saves the Blend
or overwrites the repaired USF.

The command below passed **without `--run`**: `DRY_RUN`, one Blender thread,
`pushBranchRepairRequested: true`, `nativeBlendExportApproved: false` and no
output files. Its exact source Blend is
`C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\D11_Interior_Standalone_20260927\p\mods_source\models\mods\cat_d11t.tpl.asset\cat_d11t.blend`;
the sibling `export.usf` is the repaired reference. The listed scratch root
would contain `candidate.usf`, `helper_result.json` and `blender.log`. The
receipt and archive would be the two listed `operations` files. The
file-writing invocation shown here has **not** been run and requires its
separate exact-command authorization.

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_authoring `
  --asset cat_d11t `
  --inventory "$tc\operations\d11_authoring_inventory.json" `
  --inventory-sha256 03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --blender-sha256 e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7 `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script' `
  --scratch-root "$tc\local\push-branch-base-scratch-01" `
  --receipt "$tc\operations\d11_push_branch_base_probe_01.json" `
  --archive "$tc\operations\d11_push_branch_base_probe_01.json.gz" `
  --push-branch-scratch-repair --run
```

If authorized and run later, success would establish only that the scratch
export completed and its observed USF differences were measured. Acceptance
still requires independent review of geometry, skin/bind, material, animation
and native behavior, plus the separate visual and campaign gates.
