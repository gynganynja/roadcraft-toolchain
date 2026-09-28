# D11 push-arm branch reconstruction — 2026-09-28

The pinned no-save `blender_push_branches` diagnostic reconstructed both
blade push-arm branches in memory for the accepted base `cat_d11t.blend`. It
opened the accepted historical Blend and repaired USF, inserted the missing
left and right `IK_push_arm_*_base` and `IK_push_arm_*_tip` bones, and
reparented the existing tilt bases beneath the new push bases. It preserved
the existing tilt edit-bone matrices and compared the resulting static pose
world matrices with all 400 meshless repaired USF structural nodes. The Blend
was not saved and no USF was exported.

The host pins the accepted authoring inventory, Blend, repaired USF, Blender
executables, SDK imports and worker before launch, then rechecks source and
tool bytes after Blender exits. Host SHA-256:
`f0a684c03983cd9d89b739bc7f5aa48b503cd2831b9de6f5a5f1d06d34a523f7`.
Worker SHA-256:
`974df2d86d1045a57acf392ad8367a2db19a0367a1a717fe3b04baf9e7ca63d0`.
The source Blend remained
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`;
the repaired USF remained
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`.

| Static measure | Before | After, Blender 5.0.1 | After, Blender 5.2.0 |
| --- | ---: | ---: | ---: |
| Source pose bones | 384 | 388 | 388 |
| Exact shared hierarchy paths | 378 | 386 | 386 |
| Source-only / repaired-only paths | 6 / 22 | 2 / 14 | 2 / 14 |
| Shared paths above `1e-5` matrix error | 0 | 0 | 0 |
| Maximum shared matrix element error | 0 | `2.2687017917633057e-6` | `2.2687017917633057e-6` |
| Eight push/tilt target paths within `1e-5` | 0 | 8 | 8 |

The largest target error is the left tilt tip's
`2.2687017917633057e-6`. Both existing tilt branches retain their pose
matrices within the same bound. The remaining 2 source-only paths are the
original `BoneAccess_Ladder` and `BoneBlade_cdt`; the 14 repaired-only paths
are the access-ladder chain, blade-roll branch, two inner lights, five dash
controls and `sfx`. The host requires this exact residual roster and all
eight target paths before accepting the result. A different residual, missing
right tip, changed source, or reported Blend save fails the gate.

The conversion uses the shipped SDK's Blender-to-Saber basis and inverts it
for the repaired target matrices. The new edit bones use an arbitrary
0.25-unit length because USF matrices do not encode edit-bone length. The
test establishes only static hierarchy and transform reproducibility in a
disposable Blender process. It does not establish skin/bind identity, animated
motion, mesh/material parity, persistence after saving, a native USF export,
compiled package parity or gameplay behavior. The `native-blend` gate remains
blocked; accepted builds still use the repaired USF.

Reproduce from the Steam toolchain directory with the verified Python
environment. Use Blender 5.0 or 5.2 at the shown executable path; the command
has no save or output-file argument:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
.\.venv\Scripts\python.exe -B -m roadcraft.blender_push_branches `
  --registry .\project.json `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```
