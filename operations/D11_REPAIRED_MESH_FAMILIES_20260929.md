# D11 combined repaired-only mesh families — 2026-09-29

`src/roadcraft/blender_repaired_mesh_families.py` is a reusable **in-memory**
authoring and SDK-readback module for repaired-only flat-LOD families. It
reads the accepted USF in RAM, creates three sibling Blender meshes per
family under the reconstructed D11 rig, restores the stored positions,
normals, UVs, material slots, packed colors and vertex groups, and projects
each mesh through the reviewed SDK. Its packed-color context restores the
SDK setting even if a readback raises. It saves no Blend and writes no USF.
Callers are responsible for pinning all inputs; the maintained probe below
does so before calling it.

The pinned Blender 5.2.0 no-save probe composed seven families in one live
scene: five lens families, `RearFlex_Ripper_vis` and
`D11_AccessMotorMount_vis`. The scene grew from 210 to 231 meshes. Across
**21 meshes, 9,829 faces and 29,487 triangle corners**, all predicted SDK
paths and all projected positions, normals, UVs, face material/edge pairs,
complete material strings/metadata, packed color arrays and **active** skin
influences matched the accepted repaired USF. The three ripper LODs account
for 16,200 packed color entries; every value matched. The access-motor
family's three-bone skin arrays matched in full.

The gaps remain visible in the probe result:

- The SDK emits all 399 live rig bones for each mesh, while these accepted
  families store 2, 3 or 381. Bone-index remapping in the comparison is not
  an export-time bind-table repair.
- The three ripper meshes differ in 324 corner skin records because some
  zero-weight slots contain a target bone index of 1 where the SDK emits 0.
  All nonzero bone-index/weight pairs match. No inactive-index writer patch
  has been made.
- Six lens meshes have tangent handedness differences; other tangent fields
  also drift. The access-motor base mesh has a maximum tangent-component
  error of about 0.621. Tangent parity remains unproved.
- The accepted `d11t_beacon_off_vis` materials reuse three names with
  different text from `d11t_lenses_inner_vis`. This original 21-mesh probe
  uses the default collision rejection. A later opt-in, scoped alias check
  covers the beacon family; see `D11_REPAIRED_MESH_FAMILIES_45_20260929.md`.

The material image datablocks created in RAM preserve accepted texture
**names**, but do not prove texture pixels or native appearance. No SDK USF
writer, game compiler, engine capture, campaign or visual acceptance ran.
The source Blend and accepted USF were hash-checked before and after and
remained unchanged. The existing pending scratch-export command is unchanged.

The module SHA-256 is
`f20ae1d82a47875dc6ac63709d85a089e5c2814b1c0a756bd42c7c3913f474c3`.
The exact probe is
`operations/probes/repaired_mesh_families_check_20260929.py`, SHA-256
`b53c963503c13acbedc3bf51c1674228cdb141312b2d9f729d1b64d86b1220a9`.
To replay from the Steam development-package root, copy the probe unchanged
to `RoadCraftToolchain/local/repaired_mesh_families_check_20260929.py`,
verify its hash, and invoke:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup --disable-autoexec --threads 1 `
  --python-exit-code 1 `
  --python 'RoadCraftToolchain/local/repaired_mesh_families_check_20260929.py'
```

The live run returned `IN_MEMORY_FAMILY_PAYLOAD_MATCH_WITH_GAPS` and exited
zero. The probe checks the accepted inventory, 67-path worklist, source
Blend, repaired USF, module, Blender executable and SDK pins, the prior
four-stage structural result, all 21 family paths and payloads, the known
remaining gaps, and restored color mode. This is an authoring-space proof,
not an exact writer or native-acceptance receipt.
