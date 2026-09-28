# D11 full armature readback — 2026-09-28

The retained no-save diagnostic compares **all 384 Blender pose bones** in
the pinned historical `cat_d11t.blend` with **all 400 meshless structural USF
nodes** beneath `D11T_Rig.005` in the pinned repaired `export.usf`. The SDK's
two bone affixes classify 396 of the USF nodes; the other four form the
repaired access-ladder branch. They are compared as structural nodes, not
asserted to be Blender bones. Mesh children are outside this diagnostic.

Both pinned Blender 5.0.1 and 5.2.0 produced the same sorted hierarchy and
world-matrix comparison. The full static digest covers every source and
repaired 4×4 matrix plus the USF node classification; it was
`3759cb88040b2d1054b0d9377e3e250cee96f4e9f23c218fb223f10a79657684`
in both runs. The result is `STATIC_ARMATURE_DIFFERENT`:

| Measurement | 5.0.1 | 5.2.0 |
| --- | ---: | ---: |
| Source pose bones | 384 | 384 |
| Repaired meshless structural nodes | 400 | 400 |
| Repaired nodes with SDK bone affixes | 396 | 396 |
| Shared exact paths | 378 | 378 |
| Shared paths with world-matrix error > `1e-5` | 0 | 0 |
| Maximum matrix element error on shared paths | 0 | 0 |
| Same-name relocation candidates with world-matrix error > `1e-5` | 2 | 2 |
| Maximum matrix element error on relocation candidates | `0.8908867835998535` | `0.8908867835998535` |
| Source-only paths / repaired-only paths | 6 / 22 | 6 / 22 |
| Sorted path-difference rows / unique-leaf relocation candidates | 28 / 6 | 28 / 6 |

Every shared static world matrix matches exactly after the SDK's Blender-to-
Saber basis conversion. This does **not** mean the rigs or exports match: the
28 different paths include missing intermediate nodes, changed parentage,
dash controls and lights. A unique leaf name under another parent is only a
relocation candidate, not proof of equivalent skinning or behavior.
The `BoneAccess_Ladder` candidate differs by a maximum matrix element of
`0.8289909362792969`; `BoneBlade_cdt` differs by
`0.8908867835998535`. The four relocated tilt-node matrices match exactly.

The complete path-difference list is in the CLI JSON as sorted
`pathDifferences` rows (hard bound: 128 rows; an overflow fails rather than
truncates). The host rejects partial readbacks unless the exact pinned
384/400/396/4 source/repaired/affix-classified/unclassified counts are present.
The following relative notation states all 28 exact paths:
`R = |@root|D11T_Rig.005|BoneChassis_cdt`. Every row below has prefix `R|`.

| Source-only path suffix (6) | Repaired-only path suffix (22) |
| --- | --- |
| `BoneAccess_Ladder` | `BoneAccess_LadderMount` |
| `BoneBladeLift_cdt|BoneBlade_cdt` | `BoneAccess_LadderMount|BoneAccess_Swivel` |
| `BoneBladeLift_cdt|IK_tilt_left_base` | `BoneAccess_LadderMount|BoneAccess_Swivel|BoneAccess_LadderHinge` |
| `BoneBladeLift_cdt|IK_tilt_left_base|IK_tilt_left_tip` | `BoneAccess_LadderMount|BoneAccess_Swivel|BoneAccess_LadderHinge|BoneAccess_Ladder` |
| `BoneBladeLift_cdt|IK_tilt_right_base` | `BoneBladeLift_cdt|BoneBladeRoll_cdt` |
| `BoneBladeLift_cdt|IK_tilt_right_base|IK_tilt_right_tip` | `BoneBladeLift_cdt|BoneBladeRoll_cdt|BoneBlade_cdt` |
| | `BoneBladeLift_cdt|IK_push_arm_left_base` |
| | `BoneBladeLift_cdt|IK_push_arm_left_base|IK_push_arm_left_tip` |
| | `BoneBladeLift_cdt|IK_push_arm_left_base|IK_tilt_left_base` |
| | `BoneBladeLift_cdt|IK_push_arm_left_base|IK_tilt_left_base|IK_tilt_left_tip` |
| | `BoneBladeLift_cdt|IK_push_arm_right_base` |
| | `BoneBladeLift_cdt|IK_push_arm_right_base|IK_push_arm_right_tip` |
| | `BoneBladeLift_cdt|IK_push_arm_right_base|IK_tilt_right_base` |
| | `BoneBladeLift_cdt|IK_push_arm_right_base|IK_tilt_right_base|IK_tilt_right_tip` |
| | `IK_lift_left_base|d11t_light_inner_L` |
| | `IK_lift_right_base|d11t_light_inner_R` |
| | `ctrl_dash_v5_coolant` |
| | `ctrl_dash_v5_fuel` |
| | `ctrl_dash_v5_hyd_temp` |
| | `ctrl_dash_v5_tach` |
| | `ctrl_dash_v5_trans_temp` |
| | `sfx` |

The source-only `BoneAccess_Ladder`, `BoneBlade_cdt`, and four tilt nodes
have same-name repaired nodes under different parents. The four unclassified
meshless repaired paths are the ladder mount, swivel, hinge and ladder under
the new ladder branch. The diagnostic records their full paths separately
from the 396 affix-classified nodes.

The source Blend SHA-256 was
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`
before and after **each** version run. The repaired USF SHA-256 was
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`
before and after **each** run. Independent PowerShell `Get-FileHash` checks
agreed with the host and worker guards. Blender 5.0.1 was pinned to
`f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c`;
5.2.0 was pinned to
`e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`.
The host checks the accepted inventory, lexical path ancestry, source/USF,
Blender executable, worker and all SDK import pins before/after. It includes
the two SDK package initializers loaded by the parser. The reviewed worker
SHA-256 is pinned in the host as
`899dad8810372c64de15bda3239a07311b19ce4231c5f34264796336cbace976`.

Run from the RoadCraft toolchain with either `5.0` or `5.2` in the Blender
path. This prints one bounded JSON result and accepts no save/export/output
path:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_armature_parity `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

The readback is a current-frame static transform check at scene frame 1.
It does not evaluate rest-bone geometry, bone length, constraints over time,
inverse binds, skin weights, animation, meshes, materials, native export,
native viewing, or gameplay. The Blender 5.0/5.2 agreement narrows a possible
version explanation for **static hierarchy readback only**. It does not test
either version's USF exporter. `nativeBlendExportApproved` remains `false`;
the accepted build retains `usf-repair`.
