# D11 large repaired-only meshes — 2026-09-29

The two remaining large skinned families contain six flat-LOD meshes:
`D11_InteriorV1_vis` (65,844 / 63,468 / 24,285 faces) and
`D11_DashV5_vis` (157,482 / 19,797 / 4,152 faces). Together they contain
**335,028 faces and 1,005,084 triangle corners**. The pinned Blender 5.2.0
no-save checks reconstruct them in five separate disposable processes:
`lod2_pair`, `dash_lod1`, `interior_lod1`, `interior_lod0` and `dash_lod0`.
The resource guard stops only its own Blender child if free physical memory
falls to 0.30 GiB, free commit to 6 GiB, C: free space to 7 GiB, or elapsed
time exceeds 600 seconds. All five maintained replays exited zero without
hitting a stop condition. The lowest sampled headroom across them was
0.57 GiB physical memory, 8.79 GiB free commit and 9.55 GiB C: free space.

All six SDK readbacks matched the accepted repaired USF exactly for positions,
normals, UVs, face material/edge pairs, complete material text and metadata,
packed colors, and full skin index/weight records. Each target mesh stores
one skin bone; the SDK projects all 399 live rig bones. The three interior
LODs have a maximum tangent-component error of about 0.0173; each dashboard
LOD reaches 2.0. The two isolated LOD0 runs also matched their predicted
root paths. The four isolated LOD1/2 runs intentionally lack an LOD0 peer,
so the path predictor returns `null`; their payloads pass, but their nested
SDK path is **not proven by these isolated runs**.

Combined with `D11_REPAIRED_MESH_FAMILIES_45_20260929.md`, all **51
skinned repaired-only mesh nodes, 351,565 faces and 1,054,695 corners** now
have in-memory evidence for those payload fields. The separate unskinned
`cdt_blade_roll_pivot` has its own earlier no-save reconstruction receipt.
The combined result does not establish exact tangents, per-mesh bone tables,
zero-weight skin slots (378 mismatching corners in the 45-mesh run), bind
matrices, animation, writer output, game compilation, visual appearance or
campaign acceptance. No Blend was saved and no USF was exported.

The case probe is
`operations/probes/repaired_large_mesh_cases_20260929.py`, SHA-256
`22339f1dbf9ba74ef1c9ed5fc2d6c518881164ac60506efb660f63610bfb9ca9`.
The resource guard is
`operations/probes/guarded_blender_probe_20260929.py`, SHA-256
`7ce332df1854ef360bc4eea08c6e4a73d578f2b6fbd2d5e2c4b546d95cc8b3cb`.
The importer SHA-256 is
`7f86dd84a6867f609d6400a7a17d2c534cf9a62f61f6aaad4e9aa162281b4ad1`.
The case probe also pins the accepted inventory, 67-path worklist, source
Blend, repaired USF, Blender executable and SDK. It checks the four-stage
structural reconstruction, case roster and exact face counts, restored SDK
settings, and unchanged source/USF bytes before printing a result.

To replay from the Steam development-package root, copy both probe files
unchanged to `RoadCraftToolchain/local`, verify each SHA-256, then run each
case name through the guard with a distinct local log path:

```powershell
$env:D11_LARGE_MESH_CASE = 'lod2_pair'
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B `
  'RoadCraftToolchain/local/guarded_blender_probe_20260929.py' `
  'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  'RoadCraftToolchain/local/repaired_large_mesh_cases_20260929.py' `
  'RoadCraftToolchain/local/repaired_large_lod2_pair_20260929.log'
```

Repeat with `dash_lod1`, `interior_lod1`, `interior_lod0` and `dash_lod0`.
The scratch-export invocation in
`D11_COMBINED_BLADE_REPAIR_PREP_20260929.md` remains unexecuted.

The post-run coverage verifier
`operations/probes/repaired_mesh_coverage_20260929.py` (SHA-256
`00f928a90405823601d97122c2fb8568b18920d87fc952532a66717281014b54`)
matched the 45-mesh and five large-case result paths against the accepted
52-mesh survey, excluding only the unskinned pivot. Its compact receipt is
`operations/d11_repaired_mesh_coverage_20260929.json` (SHA-256
`d4b1b58b624a7eb905980bf734a757a2f1fe64928d85005302c11d21e38adde8`).
The receipt pins each input log SHA-256 and reports 47 predicted paths,
four unresolved isolated LOD paths, 378 full-skin slot mismatches and 24
meshes with tangent-component error at least 1.
