# D11 Blender reconstruction worklist — 2026-09-28

The [machine-readable worklist](d11_blender_reconstruction_worklist_20260928.json)
is SHA-256 `a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`.
It is derived from the three pinned Blender 5.2 scratch-export archives, not
from a new export. `blender_reconciliation.py` rechecked each archive's
compressed and raw hashes, its retained native USF, the currently pinned
authoring inventory, and all 68 declared source files. The worklist includes
exact repaired/native hierarchy paths, per-mesh measurements and missing
material labels, skin/bind differences, animation differences, and source and
archive hashes. All three assets remain `RECONSTRUCTION_REQUIRED` and the
`native-blend` export gate remains blocked.

Each asset has 133 repaired-only hierarchy paths and 76 native-export-only
paths. Sixty-six pairs have the same **unique leaf name** under different
parents. These are *relocation candidates*, not proven equivalent nodes: the
archive has no full mesh data for a missing path. After removing those pairs,
67 repaired-only paths and 10 native-export-only paths remain per asset. The
67 include `BoneAccess_LadderMount` / `BoneAccess_Swivel` /
`BoneAccess_LadderHinge`, `BoneBladeRoll_cdt`, the push-arm IK bases, the five
dash controls, and LOD0–2 visual branches for the interior, dash, ladder
motor, beacons and lenses. The 10 export-only names are `cdt_blade_60`–`63`
and the LOD0–2 `D11_AccessBearingTab_vis` and `D11_AccessBridge_vis` branches.
These findings identify exact places to inspect in a *separate* authoring
copy; a path difference alone cannot establish whether the Blend, SDK
exporter, or both need a change.

All 126 matched mesh nodes have differing inverse-bind-matrix digests and at
least one material label present only in the repaired USF. The worklist names
the exact missing labels per node and variant, including each `_v2`/`_v3`
suffix. For example, `Body_vis` has 141,912 repaired faces and 92 material
slots versus 164,391 native-export faces and 89 slots. Its missing labels are
`mod_cat_d11t_painter_01_l0`, `_02_l0`, and `_03_l0` for the base asset. The
worklist also records mesh vertex, normal, UV/color, skin-entry, skin-bone UID
and material-payload differences separately, so restoring labels alone will
not appear to resolve mesh parity. The native export omits all three
36-key translation, rotation and scale splines on
`|@root|D11T_Rig.005|BoneChassis_cdt|BoneAnim_WiperFront`.

Reconstruction should first determine whether each relocated or missing node
exists in the source Blend and whether the SDK exports its intended parent.
Then reconcile geometry/LOD, material slots and definitions, skin/bind data
and wiper animation in disposable authoring copies. Rerun the pinned
one-thread scratch export and compare the new full diff for *each* asset. Only
after hierarchy, transforms, geometry, normals/tangents, UV/colors,
materials, skin/bind, LOD, metadata and animation match can compilation and
native-view parity be reviewed. An externally reviewed, asset-specific
parity receipt is still required before changing `usf-repair` to
`native-blend`.

To regenerate a new worklist from the retained archives, use a **new** output
path. The command is read-only until that output is written; it does not
launch Blender or touch accepted source assets:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_reconciliation `
  --registry "$tc\project.json" `
  --summary "$tc\operations\d11_base_blend_authoring_parity_summary.json" `
  --summary "$tc\operations\d11_v2_blend_authoring_parity_summary.json" `
  --summary "$tc\operations\d11_v3_blend_authoring_parity_summary.json" `
  --output "$tc\local\new-blender-reconstruction-worklist.json"
```
