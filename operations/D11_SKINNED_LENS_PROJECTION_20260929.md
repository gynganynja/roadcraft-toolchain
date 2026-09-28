# D11 front-lens skinned LOD2 projection — 2026-09-29

The accepted repaired USF contains
`|@root|D11T_Rig.005|d11t_lenses_front_on_vis|d11t_lenses_front_on_vis_LOD2`,
which is absent from the historical source Blend. It is a 16-face, 48-corner
mesh with one UV set, two material slots and 48 skin entries. Each corner is
fully weighted to `IK_lift_left_base` or `IK_lift_right_base` by one of the
381 recorded skin bones. The mesh has no color set.

The pinned Blender 5.2.0 no-save probe first runs the maintained four-stage
structural reconstruction. It then uses the reviewed SDK USF importer to
create a disposable mesh, converts its positions and UV convention into
Blender space, authors the two materials' names, texture reference and tint,
assigns the two vertex groups, and projects the result through the SDK's
`UsfMesh.b_read`. Its armature modifier is disabled in the viewport to avoid
deforming already posed target geometry; the SDK still reads its skin groups.
The object is attached to the live rig for this payload test, but its
accepted LOD parent hierarchy and transforms are **not** reconstructed.

The SDK projection matched all 48 positions, normals, UVs and skin entries
after mapping the live bone indices by name to the accepted order. All 16
face material/edge-index pairs matched. Both complete material strings matched
the accepted strings, whose SHA-256 values are
`1f6a1a66db23973db4ab6421a35802ff1c20432fc43ca58b126cee7f249a8b92`
and `7f5ce2c81cd909e9cf313fc6877bf51a77fb4c060518e1f5b4f1e16275755742`.
These materials use an in-memory image datablock with the accepted texture
name, not proof of actual rendered texture content.

This is **not** full mesh parity. The maximum tangent component difference is
`0.00011141225695610046`. The SDK emits all 399 live rig bones rather than
the accepted 381. Removing the 18 new bones still leaves five list positions
reordered by blade reparenting. Of the 381 accepted inverse binds, 380 are
within `1e-5` of the live rig; `d11t_beacon` differs by
`1.0105905532836914`. That beacon is not among the two bones with nonzero
weights on this lens, but the serialized bind table would still differ.
Material, weight and geometry readback therefore cannot authorize a USF
writer call, route promotion or native acceptance.

The exact probe is
`operations/probes/skinned_lens_projection_20260929.py`, SHA-256
`8aea7b60bc945e98fde29bbdffb9819e36c69a0dbda9db3293d66a817d91a930`.
To replay from the Steam development-package root, copy it unchanged to
`RoadCraftToolchain/local/skinned_lens_projection_20260929.py`, verify that
hash, then run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup --disable-autoexec --threads 1 `
  --python-exit-code 1 `
  --python 'RoadCraftToolchain/local/skinned_lens_projection_20260929.py'
```

The passing run returned `IN_MEMORY_SKINNED_LENS_PAYLOAD_MATCH_WITH_GAPS` and
exited zero. It checked the accepted inventory, source Blend, repaired USF,
SDK files and Blender executable pins, and rechecked the source, USF and SDK
afterward. The source Blend and repaired USF were unchanged. No Blend was
saved, no USF was exported, and no accepted asset was modified. The existing
pending scratch-export command is unchanged and does not include this lens.
