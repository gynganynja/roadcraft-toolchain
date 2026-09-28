# D11 residual structural nodes — no-save experiment, 2026-09-29

The maintained push, blade-roll and ladder workers leave eight repaired-only
paths in the pose-bone comparison. A pinned read-only inspection separated
their source representations:

| Repaired path below `BoneChassis_cdt` | Historical Blend | Retained native USF |
| --- | --- | --- |
| `IK_lift_left_base|d11t_light_inner_L` | No same-name bone or scene object | Absent |
| `IK_lift_right_base|d11t_light_inner_R` | No same-name bone or scene object | Absent |
| `ctrl_dash_v5_coolant` | No same-name bone or scene object | Absent |
| `ctrl_dash_v5_fuel` | No same-name bone or scene object | Absent |
| `ctrl_dash_v5_hyd_temp` | No same-name bone or scene object | Absent |
| `ctrl_dash_v5_tach` | No same-name bone or scene object | Absent |
| `ctrl_dash_v5_trans_temp` | No same-name bone or scene object | Absent |
| `sfx` | Bone-parented Empty under `BoneChassis_cdt` | Present, exact repaired world matrix |

The repaired seven absent nodes are meshless, unanimated leaves. The source
`sfx` Empty also has no children. The retained native scratch USF is pinned to
SHA-256 `80c856b07b3ae1447f2748b5f6f8ec13c688c2594f3ebfaeada9e0d11da21370`.
The repaired `sfx` and native `sfx` world matrices have zero element error.
Blender 5.0.1 and 5.2.0 independently returned the same shape classification.

A separate disposable, **no-save and no-export** probe then ran the maintained
push, roll and ladder workers in one Blender process. It added only the seven
missing bones in memory under their exact repaired parents. Their rest
matrices were solved from the already evaluated parent poses and repaired USF
world matrices. It included the existing source `sfx` Empty when comparing
structural paths, rather than inventing an eighth bone. Both pinned Blender
versions returned:

| Static measure | Result |
| --- | ---: |
| Pose bones after edits | 399 |
| Source structural paths, including `sfx` Empty | 400 |
| Shared repaired structural paths | 400 / 400 |
| Source-only / repaired-only paths | 0 / 0 |
| Shared paths over `1e-5` matrix tolerance | 0 |
| Maximum shared matrix element error | `2.2687017917633057e-6` |
| Source `sfx` Empty versus repaired `sfx` matrix error | 0 |
| Source mesh world-matrix drift | 0 |

The exact disposable probe is
`local/residual_bones_probe_20260929.py`, SHA-256
`ca1963f396276b1a28e981dd1c23b8ceb0f6742059b1298aee489edaa4f068a9`.
Run it from the RoadCraft development package with either pinned Blender
version, replacing `5.2` with `5.0` for the second check:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup --disable-autoexec --threads 1 `
  --python-exit-code 1 `
  --python 'RoadCraftToolchain/local/residual_bones_probe_20260929.py'
```

The historical Blend remained SHA-256
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`;
the repaired USF remained
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`.
The experiment used arbitrary 0.25-unit new edit-bone lengths because the USF
does not encode Blender edit-bone length. It proves a static in-memory path and
transform construction, **not** Blender save persistence, SDK export, bind or
animation parity, collision, compilation, native appearance or gameplay. The
accepted repaired USF remains the build input and `native-blend` stays blocked.
