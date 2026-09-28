# D11 blade-roll pivot in-memory reconstruction — 2026-09-29

The repaired USF has one unskinned mesh absent from the historical Blend:
`|@root|D11T_Rig.005|BoneChassis_cdt|BoneBladeLift_cdt|BoneBladeRoll_cdt|cdt_blade_roll_pivot`.
The other 51 repaired-only meshes carry skin entries. The pivot is a narrow
first reconstruction target, not a substitute for the remaining geometry,
material and bind work.

The maintained `src/roadcraft/blender_pivot_mesh_repair.py` now reconstructs
that pivot **in memory** after the existing four-stage structural worker has
matched all 400 repaired paths. It parses the pinned repaired USF, requires the
12-face / 36-corner, one-UV, zero-colorset, zero-skin pivot shape, converts its
mesh coordinates and V-axis into Blender authoring space, removes the SDK
importer's placeholder material slot so the SDK emits the target default
material, and bone-parents the object under `BoneBladeRoll_cdt`. It then
projects the new object through the reviewed SDK's `UsfMesh.b_read` without
calling a USF writer.

The Blender 5.2.0 LTS no-save check exited zero with
`IN_MEMORY_STRUCTURAL_MATCH` and `IN_MEMORY_PIVOT_MESH_MATCH`. It found:

| Field | Result |
| --- | --- |
| Hierarchy/world transform | Target path; world matrix maximum error `0` |
| Local transform | Maximum matrix-element error `2.384185791015625e-7` |
| Faces | 12/12 material and edge-index pairs matched |
| Positions, normals, UVs | 36/36 exact in each array; UV-set name matched |
| Tangents | 28/36 exact; all 36 within `5.960464477539063e-8` |
| Material | Complete SDK text SHA-256 `61c091034b813dd12ffa0973c5dda7555281a1b83e4868f7b2b7d00879e7c42c` matched; struct version and color-usage field matched |
| Skin/color | Both absent in target and projection |
| Live mesh count | 210 source meshes plus one pivot = 211 |

The module is SHA-256
`38ad41a614cde117447308a7af5740ff5d04538837642147dd256748c46e60bb`.
The exact launcher source is versioned at
`operations/probes/pivot_mesh_repair_check_20260929.py`, SHA-256
`b561d5db4d2898484c28ca13baf4e00532e7c1b9d2e142446e9fe533be5e3065`.
From the Steam development-package root, the verified no-save invocation was:

```powershell
Copy-Item 'RoadCraftToolchain/operations/probes/pivot_mesh_repair_check_20260929.py' `
  'RoadCraftToolchain/local/pivot_mesh_repair_check_20260929.py'
if ((Get-FileHash 'RoadCraftToolchain/local/pivot_mesh_repair_check_20260929.py' -Algorithm SHA256).Hash.ToLowerInvariant() -ne `
    'b561d5db4d2898484c28ca13baf4e00532e7c1b9d2e142446e9fe533be5e3065') { throw 'Probe bytes differ' }
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup --disable-autoexec --threads 1 `
  --python-exit-code 1 `
  --python 'RoadCraftToolchain/local/pivot_mesh_repair_check_20260929.py'
```

The source Blend, repaired USF, SDK imports and Blender executable were
hash-checked; the source and USF were unchanged afterward. The temporary scene
was discarded when Blender exited. No Blend was saved, no USF was exported,
and no accepted asset was changed. Exact future SDK writer bytes, persistence,
remaining 51 skinned meshes, native compilation and visual/campaign acceptance
remain unproved. The existing pending scratch-export command is unchanged and
does not request this pivot stage.
