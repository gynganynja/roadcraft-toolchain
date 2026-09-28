# D11 blade-normal scratch repair preparation — 2026-09-29

The accepted base `cat_d11t` repaired USF remains the build input. Prior
no-save projection proved that its 6,486 blade-collision corner normals can be
supplied directly in Saber coordinates through temporary `saber_normals`
attributes on the historical Blend's 60 `cdt_blade_0`–`59` meshes. Both pinned
Blender versions reproduced the accepted normal arrays and left the other five
measured mesh fields unchanged. See
`D11_BLADE_NORMAL_PROJECTION_READBACK_20260928.md`.

`blender_blade_normal_scratch_repair.py` now installs those attributes on the
**live, disposable scene**, rather than removing them after projection. It
pins the historical Blend, repaired USF, retained native scratch USF, Blender,
reviewed SDK and six projection dependencies. For each exact-path blade mesh
it verifies the source/native payload and the temporary projected/repaired
normal array before installing the attribute. An exception removes all
attributes it already installed. The authoring helper then keeps them through
the SDK scratch export and would compare all 60 resulting native normal arrays
directly with the repaired USF. Its wrapper still compares the full asset and
keeps the `native-blend` gate blocked.

No-save installation ran in Blender 5.0.1 and 5.2.0 with 60 attributes left
in memory, 2,162 triangles, 6,486 corners, and the same complete row digest
`533058ffdaa47a8aa064c284c7f717096dc27282a3dd300fab7330d50b00fa23`.
Both processes exited 0, reported `blendSaved: false` and
`usfExported: false`, and rechecked accepted source hashes. The disposable
preflight script in the Steam mirror's ignored `local` directory is
`local/blade_normal_install_preflight_20260929.py`, SHA-256
`4e514013d3d410045e33e2d6fff3a864d53514322346c6139efd00fcc5eb486e`.

A separate no-export Blender 5.2 sequence applied the push-arm reconstruction,
installed the 60 blade-normal attributes, and installed the wiper bake hook on
the same live scene. It reported 388 bones and unchanged source hashes. The
wiper `actionOrder` was empty because no SDK export was called; the sequence
does not prove animation output. Its ignored script in the Steam mirror is
`local/d11_combined_repair_preflight_20260929.py`, SHA-256
`17dbd5f108077c7b747eb3c5654089413dc883d0bbc85f59f112d5f745d15e09`.

The standalone blade-normal command below passed **without `--run`** as
`DRY_RUN`, one Blender thread and zero output files. It pinned the retained
native scratch USF to SHA-256
`80c856b07b3ae1447f2748b5f6f8ec13c688c2594f3ebfaeada9e0d11da21370`.
The source Blend is
`C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\D11_Interior_Standalone_20260927\p\mods_source\models\mods\cat_d11t.tpl.asset\cat_d11t.blend`;
its sibling `export.usf` is the accepted repaired reference. The new scratch
root would contain `candidate.usf`, `helper_result.json` and `blender.log`;
the separate receipt/archive paths are listed below. None existed at review.
This exact file-writing command has **not** been run and requires separate
authorization:

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
  --scratch-root "$tc\local\blade-normal-base-scratch-01" `
  --receipt "$tc\operations\d11_blade_normal_base_probe_01.json" `
  --archive "$tc\operations\d11_blade_normal_base_probe_01.json.gz" `
  --blade-normal-scratch-repair --run
```

The three-repair combination also passed its no-write wrapper dry run. Its
unexecuted scratch root is `local/d11-combined-repair-scratch-01` with
`operations/d11_combined_repair_probe_01.json` as receipt. The earlier pending
push-arm command authorizes only its own exact invocation if approved; it
cannot be treated as authorization for the blade-normal or combined command.
Even a successful scratch export would establish diagnostic USF facts, not
accepted native-Blend equivalence, collision behavior or visual/campaign
approval.
