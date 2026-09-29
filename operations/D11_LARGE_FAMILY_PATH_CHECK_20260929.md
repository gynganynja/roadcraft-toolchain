# D11 large-family path check — 2026-09-29

The pinned no-save Blender 5.2.0 probe attempted to compose each remaining
large flat-LOD family with its three **real** target meshes under the
reconstructed rig. It used the existing resource guard: stop its own Blender
child at 0.30 GiB free physical memory, 6 GiB free commit, 7 GiB C: free
space, or 600 seconds. The accepted source Blend and repaired USF were read
only and retained their SHA-256 pins after both attempts.

`interior_full` exited zero. All three `D11_InteriorV1_vis` meshes appeared
in one scene, covering 153,597 faces and 460,791 corners. Their predicted
SDK paths, positions, normals, UVs, face metadata, full material text and
metadata, colors, and full skin records matched the accepted USF. The
projected bone table still has 399 entries versus one in each target mesh;
the maximum tangent-component error is about 0.0173. The lowest sampled
headroom was 0.45 GiB physical memory, 9.14 GiB free commit and 9.55 GiB
C: free space. No Blend was saved and no USF was exported.

`dash_full` reached the resource floor and stopped after 152.3 seconds,
before printing a mesh result. The guard recorded 0.23 GiB free physical
memory, 8.90 GiB free commit and 9.55 GiB C: free space; it terminated only
its own Blender child. This attempt proves **no full-family payload or path
result** for `D11_DashV5_vis`. Its three isolated LOD payloads passed the
separate guarded checks in `D11_REPAIRED_LARGE_MESHES_20260929.md`, but the
LOD1 and LOD2 nested paths were subsequently verified separately alongside
the real LOD0 in paired scenes. The guard floor was not reduced or bypassed.

`dash_lod02` exited zero with real LOD0 and LOD2 in one scene (161,634 faces).
`dash_lod01` exited zero with real LOD0 and LOD1 (177,279 faces). Both matched
the predicted SDK paths and the checked mesh payload fields; their lowest
sampled free physical memory was 0.52 and 0.59 GiB respectively. These runs
prove both child paths in their LOD0 context, but not all three dashboard LODs
simultaneously. Their log SHA-256 values are
`7c85b08a4df2769b4bccaecf13b6f2b5262558d1f91ea210210558bdea763145`
and `d088d6ad4fdceb7c38a8ba6160d77b4c2becaf74bd7e070aeb7f85c12293cf47`.
The paired probe is `operations/probes/repaired_dash_lod_pairs_20260929.py`,
SHA-256 `319169ee8db1580ffc7d58e1354207e043565c42cac8dc149d44bf4231cd2eb7`.

The exact full-family probe is
`operations/probes/repaired_large_full_families_20260929.py`, SHA-256
`e59a2eb3d58c43c39bd9cf190789bfc039cb813afda5e741525fbc8cdcbef7e9`.
The resource guard is
`operations/probes/guarded_blender_probe_20260929.py`, SHA-256
`7ce332df1854ef360bc4eea08c6e4a73d578f2b6fbd2d5e2c4b546d95cc8b3cb`.
The passing interior log SHA-256 is
`ab41de143271e0e2ec34c35771b142fe959b2edb122102b437473080a4f525f1`.
The updated coverage verifier and receipt are described in
`D11_REPAIRED_LARGE_MESHES_20260929.md`; they count all 51 skinned mesh paths
verified, with the dashboard pair-scene scope recorded separately.

To replay, copy the full-family probe unchanged to
`RoadCraftToolchain/local/repaired_large_full_families_20260929.py`, verify
its hash, set `D11_FULL_FAMILY_CASE=interior_full` or `dash_full`, and invoke
the already pinned guard with the Blender executable, copied probe and a
distinct local log path. The dashboard case needs more physical-memory
headroom before a safe all-three-LOD replay. No scratch export or native editor
run is implied by this diagnostic.
