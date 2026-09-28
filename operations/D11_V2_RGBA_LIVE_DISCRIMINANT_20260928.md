# D11 v2 / Blender 5.2 live RGBA discriminant — 2026-09-28

The prior unwrapped source-mesh readback intermittently projected white SDK
packed colors for `|@root|D11T_Rig.005|Ripper_vis|Ripper_vis_LOD1` where the
retained native USF had grays. A later call-time tracing worker did not
reproduce that result, while a disposable-mesh test independently reproduced
the reviewed SDK's stale `RGBA_CACHE` behavior. This diagnostic keeps the
installed `UsfMesh.b_read` and `UsfMeshColorSet.rgba_to_saber` functions
**unwrapped** and tests the live evaluated color input only if the target
packed-color digest differs from native.

The new worker reads the same pinned native and repaired USFs, opens the
accepted v2 Blend read-only in pinned Blender 5.2.0, and projects all 126
mapped mesh paths in sorted worklist order. It uses the reviewed SDK's
`UsfMesh().b_read(obj)`, summarizes the same six mesh fields, and calls
`evaluated_object.to_mesh_clear()` after each path. At the target, a digest
mismatch alone enables the extra read: before `to_mesh_clear()`, it walks
`projected.b_mesh.loop_triangles` and each triangle's `.loops` in the exact
order used by SDK `b_read_face`, reads the live color attribute's RGBA, and
packs it with the SDK's clip/truncate/ARGB expression **without** the cache.
The raw array stays in process; only digests, counts and at most 12 samples
leave Blender. If the target digest matches native, no live raw colors are
read. The SDK functions were checked against the pinned installed `mesh.py`
and for unchanged function identity after projection. The existing
`BinaryIO.read_bytearray` compatibility workaround was used only during USF
reads and restored before source projection.

The [execution manifest](d11_v2_rgba_live_discriminant_manifest_20260928.json)
pins exact Python and Blender commands, input paths and SHA-256 values,
the reviewed 14 SDK files, UTC invocation times and both receipt hashes.
Its SHA-256 is
`5b94cbb0ca4d7347c8c3a661db012a70a0021c2f03d0cb4db1a327a90b307fa9`.
The host, worker and focused test SHA-256 values are respectively
`311fee930e4f9057c3d44b9f4561d4f841c7242fd7386bfaf8c70e433f80cef5`,
`99cbb46fd054ab0bd9e0e2dba895d40e03fd23ce684d2fd766ff6fc302041eba`,
and `9de8b4b779fe8f77022ad350bd2898d91825de3a92bba87c99f9e3fe7114248c`.
The Blender executable SHA-256 is
`e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`;
SDK `saber/blender/lib/usf/mesh.py` is
`4ab671128044524524028dbea32a5c7dcaf5274630348de151592c87b08be337`.
The accepted v2 Blend, native USF and repaired USF pins are
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`,
`0e533bbc80a95798824e69e5c6545cc50b9d98f0ba81e7f0e96d9e3a93c2dc3f`,
and `096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a`.

| Fresh process | Target packed result | Conditional raw read | LOD1 cache before/after | Receipt SHA-256 |
| --- | --- | --- | --- | --- |
| [Run 1](d11_v2_rgba_live_discriminant_run1_20260928.json), `10:01:24.343350Z`–`10:02:55.078336Z` | Native match; all 126 rows' packed colors match | No | 85,214 / 135,392 | `7162cc61cf97e2744c01bcd0c592b86266554af7b2027bf33cea661d41893b78` |
| [Run 2](d11_v2_rgba_live_discriminant_run2_20260928.json), `10:02:55.843129Z`–`10:04:30.893934Z` | **1,200 / 59,238** target packed values differ; 125/126 rows match | Yes | 85,214 / 85,214 | `1c582ac64f499ca6454d6ba650266f315f8b76dcc7b7cbeac7715a93971c98f1` |

Run 2's SDK projected target digest was
`f7f579c6faeed4bef6ca0243047c98080c9a85e6df93f5b925ef611fa13926dc`.
The statelessly packed **live raw RGBA matched every one of the 59,238
native values**, with shared digest
`aa3e170d0a56390032c339a0607d13c1151cbb8c3350abb88fd41873e057d9b7`.
Thus source/native and source/stateless each differed at 1,200 entries;
stateless/native differed at zero. The first differing entry, index 3,621,
had raw RGBA approximately `(0.956, 0.956, 0.956, 1)`, stateless/native
packed `4294177779`, and SDK projected white `4294967295`. The 12 retained
samples all show SDK white versus distinct native grays. The earlier
historical mismatch also began at index 3,621, but had 2,650 different
values and a different source digest. These are separate fresh-process
outcomes, not byte-identical reproductions. This run's complete 126-row
digest was `b6730e7b0d2411749c2df110a4ad6e9a0e06c1a13d909b83267ed4c66c9af199`;
run 1's was the matching
`5965d7327d72a81aa04f7ef1255265b6da6fba14cdd2c737b91f184db1f6a6b0`.

The raw/native agreement localizes run 2's discrepancy between the live
evaluated color data and the SDK's packed output. The unchanged target cache
size during the mismatching projection, compared with the growing cache in
run 1, is consistent with stale cache hits; the earlier disposable-mesh
diagnostic demonstrated that mechanism in both Blender versions. This
unwrapped worker did **not** record the SDK's call-time color wrapper or a
specific cache lookup. It reads raw color after `b_read` returns, while the
evaluated mesh remains live, so it cannot by itself prove which cache key
caused each white return or exclude every possible mid-call color change.
Run 1's match also shows the failure remains intermittent; two runs do not
establish its frequency. The bounded plan allowed three fresh processes but
stopped at two when run 2 reproduced the target mismatch.

Four no-Blender synthetic boundary tests passed. They verify that raw
readback is conditional on an exact pinned target shape, triangle-loop order
and stateless clipping/packing, mismatch classification with a 12-sample
limit, and rejection of contradictory or unsafe receipts. Both process
receipts passed the host's input and no-write checks, and the manifest pins
the unchanged inputs. No Blend was saved, no USF was exported, and neither
Painter nor the native editor was launched. The accepted `usf-repair` route
and `nativeBlendExportApproved: false` gate remain unchanged.

To repeat the bounded host readback with the pinned inputs:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_v2_rgba_live_discriminant `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```
