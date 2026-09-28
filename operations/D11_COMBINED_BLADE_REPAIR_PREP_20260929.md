# D11 combined push, roll and blade-normal scratch preparation — 2026-09-29

The accepted repaired `cat_d11t` USF remains the build input. A new opt-in
`--blade-roll-scratch-repair` stage now runs after the pinned push-arm repair
and before blade-normal installation and the wiper hook. The wrapper requires
the push-arm option whenever blade roll is requested. The blade-normal
installer checks the exact repaired blade lineage when roll is present; its
default old-path check remains for standalone normal diagnostics.

Blender 5.0.1 and 5.2.0 independently completed a disposable **no-save,
no-export** sequence with the maintained push and roll workers plus the
blade-normal installer. Both reported 389 bones, 388/400 shared repaired
structural paths, 1 source-only access-ladder path, 12 repaired-only paths,
zero blade mesh world-matrix error and maximum local-matrix error
`2.384185791015625e-7`. Both installed all 60 normal attributes and returned
the same complete projection digest as the earlier standalone check:
`533058ffdaa47a8aa064c284c7f717096dc27282a3dd300fab7330d50b00fa23`.
The ignored combined probe is
`local/combined_roll_worker_probe_20260929.py`, SHA-256
`1b962bb63a43172434e0108a867b0408fb01c0835fdbf53ba010b39737f8c62d`.
The final Blender 5.2 no-save run also installed the wiper bake hook in that
same scene. Its `actionOrder` was empty because no SDK export called the hook;
animation output is still unverified.

The wrapper's **dry run** passed with all four repairs requested, the reviewed
Blender 5.2 executable and source pins, and no output files. The scratch root,
receipt and archive named below were absent after the dry run. Its authoring
host SHA-256 is
`b84d4afe08c23ecf1b76847f571c258e1e9a10f5cfb4868600f29563d7f8fd3d`;
helper SHA-256 is
`041c921f91e0a4c93fe72deacf8d52722719fd6d47c691f9ac39c3a5a1663e86`.
The blade-roll host/worker pins are
`24d4b9513617d0638af52dac95238199a2bfd880c6926d68f7a230adf1bc4d89`
and `ced27a3f52a0a80764eecbd07edce6e9c6b32d6f5f6b77a5f35e57be1b2399be`;
the normal installer pin is
`9f1461a3aa24077f77fcef831f8abf96101fd89a60457c3fee4912a85bc3b1cf`.

The following exact **file-writing** invocation is prepared but unexecuted.
It would export a diagnostic `candidate.usf` only into a new scratch root and
write its receipt/archive; it would not save the source Blend or replace the
accepted USF. It requires separate authorization before `--run` is used:

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
  --scratch-root "$tc\local\d11-push-roll-normal-wiper-scratch-01" `
  --receipt "$tc\operations\d11_push_roll_normal_wiper_probe_01.json" `
  --archive "$tc\operations\d11_push_roll_normal_wiper_probe_01.json.gz" `
  --push-branch-scratch-repair --blade-roll-scratch-repair `
  --blade-normal-scratch-repair --wiper-scratch-repair --run
```

The accepted repaired USF stays authoritative even if that diagnostic export
eventually succeeds. The candidate would still need full node, mesh, bind,
animation, compilation, collision and native-view parity review. The current
no-save result does not establish any of those export or gameplay claims.
