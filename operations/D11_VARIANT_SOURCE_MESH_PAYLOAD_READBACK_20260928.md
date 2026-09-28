# D11 v2/v3 source-mesh payload readback — 2026-09-28

The pinned, **no-save** diagnostic opened each variant's own accepted Blend
path in Blender 5.0.1 and 5.2.0. For each of the 126 mapped mesh paths, it
compared the reviewed Saber SDK's in-memory `UsfMesh.b_read(obj)` projection
with that variant's retained scratch native USF. It also read the variant's
accepted repaired USF to characterize ordered payload differences. The native
roots are `cat_d11t_v2` and `cat_d11t_v3`; the repaired root is `cat_d11t`.
Path normalization maps these to `|@root` for corresponding mesh lookup.

The worker did not save a Blend, export a USF, invoke Painter or an editor, or
write accepted assets. Its digests encode ordered semantic arrays at the SDK's
float32 wire precision, including lengths, layer names and packed colors;
they are **not** hashes of literal serialized USF mesh bytes. Tangents are
excluded because prior retained native exports showed low-bit,
thread-sensitive drift. The six fields are triangle-corner positions and
normals, face material/edge indices, UV names and coordinates, packed vertex
colors, and per-corner skin indices/weights.

The table below uses unchanged final diagnostic files: host SHA-256
`f2cc1e997b8458e8fe279050a59dcdff7c9e20143d8fbfa0700da4147d6572fb`,
worker SHA-256
`cfef0c5e5cdc6ed033c704a769b0c53d466bd1f79b77746343472f50f786bda0`.
Each entry is a fresh Blender process. `Other five` means positions, normals,
face material/edge indices, UV coordinates/names, and skin indices/weights.

| Variant | Blender | Packed-color matches | Other five matches | Complete rows | Rows SHA-256 |
| --- | --- | ---: | ---: | ---: | --- |
| v2 | 5.0.1 | 126/126 | 126/126 each | 126/126 | `5965d7327d72a81aa04f7ef1255265b6da6fba14cdd2c737b91f184db1f6a6b0` |
| v2 | 5.2.0, first run | **125/126** | 126/126 each | **125/126** | `f37ec3d6544af2605afa640e805da367b5549754058f79bdfe42f8fa00f1ca3f` |
| v2 | 5.2.0, immediate repeat | 126/126 | 126/126 each | 126/126 | `5965d7327d72a81aa04f7ef1255265b6da6fba14cdd2c737b91f184db1f6a6b0` |
| v3 | 5.0.1 | 126/126 | 126/126 each | 126/126 | `5965d7327d72a81aa04f7ef1255265b6da6fba14cdd2c737b91f184db1f6a6b0` |
| v3 | 5.2.0, first run | 126/126 | 126/126 each | 126/126 | `5965d7327d72a81aa04f7ef1255265b6da6fba14cdd2c737b91f184db1f6a6b0` |
| v3 | 5.2.0, immediate repeat | 126/126 | 126/126 each | 126/126 | `5965d7327d72a81aa04f7ef1255265b6da6fba14cdd2c737b91f184db1f6a6b0` |

The final-code v2/5.2 pair has retained compact stdout records:
`d11_v2_mesh_payload_blender52_mismatch_compact_20260928.json` (SHA-256
`909cf1e289573851ddd40ca3b56b0089299c3028bd0c9c5b5269b09f71b50a00`)
and `d11_v2_mesh_payload_blender52_repeat_compact_20260928.json` (SHA-256
`44f4d42905d35a5296fd894a451cabdb41d4ad30df500c5f980349883c1499d4`).
They preserve the reported field counts, row digests, bounded packed-color
details, cache observations, and unchanged-input flags. They do not retain
all 126 per-row results or embed the host, worker and Blender binary pins;
those pins are recorded above and in the input table below. The aggregate
counts and row digests are therefore retained diagnostic outputs, not
independently recomputable from these compact records alone.
The other four table rows are contemporaneous run observations without
retained compact per-run JSON.

The final-code v2/5.2 first run localized its only mismatch to
`|@root|D11T_Rig.005|Ripper_vis|Ripper_vis_LOD1`:
**2,650 of 59,238** values in its one packed-color set differed. The source
summary SHA-256 was
`5421bc767baed6072e8016223018009d2541d199ead5f5ce34bab2187ce339fa`;
the native summary SHA-256 was
`aa3e170d0a56390032c339a0607d13c1151cbb8c3350abb88fd41873e057d9b7`.
At the first differing entry (set 0, index 3,621), source was `4294967295`
(`0xffffffff`) and native was `4294177779`. The next eleven sampled source
entries were also `4294967295`; the worker records their native integers.
The repeated v2/5.2 run matched all 126 rows under the same pinned code,
assets, SDK and Blender executable. Thus the packed-color projection is
**intermittent in fresh Blender 5.2 processes**, and stable 126/126 v2/5.2
parity is not established. Both v3/5.2 final-code runs matched, but the
bounded repetition does not prove v3/5.2 is immune.

The SDK's module-global `RGBA_CACHE` was empty after USF reads in these
runs. Its size immediately before the `Ripper_vis_LOD2` probe was 85,214 in
the v2/5.2 mismatch run, versus 135,392 in the matching runs; sizes after all
mapped projections were 116,763 and 166,941 respectively. This is a
process-state observation after the differing `Ripper_vis_LOD1` row had
already been projected, **not pre-mismatch evidence or an isolated causal
explanation**. Earlier
diagnostic revisions also produced 125/126 packed-color outcomes (one at
`Ripper_vis_LOD2`), but their complete host/worker pins were not captured;
those cross-revision outcomes remain unresolved history and are not evidence
of same-code repeatability. The final-code v2/5.2 pair above is the direct
same-code repeatability evidence.

The accepted repaired USF differs substantially from each source/native
projection. Across **all six final-code runs**, strict ordered-digest equality
with the repaired USF was 111/126 positions, 3/126 normals, 0/126 face
material/edge indices, 0/126 UV data, 123/126 packed colors, and 78/126
skin indices/weights. Equal element counts were 117/126 for each field except
packed colors, which had 123/126. On the 111 rows with identical ordered
positions, all 111 had comparable normal, UV and color shapes; 3 normals,
0 UV arrays and 111 packed-color arrays matched. These are count and ordered
digest observations only. A face material index can denote a different
material under the repaired root, and skin indices require bone-identity
mapping. Consequently the diagnostic claims **no repaired semantic mesh
parity**, even where an ordered digest happens to match.

Input pins are:

| Input | SHA-256 |
| --- | --- |
| Accepted authoring inventory | `03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d` |
| Reconstruction worklist | `a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3` |
| Each accepted variant Blend (separate paths) | `1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731` |
| v2 source asset digest | `6f6d47667c5dd24aa18fa1734aa2cbc7c6af48ac28bc57c67e8609f899f22d6f` |
| v2 repaired USF | `096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a` |
| v2 retained native USF | `0e533bbc80a95798824e69e5c6545cc50b9d98f0ba81e7f0e96d9e3a93c2dc3f` |
| v2 parity summary | `ffcc6bb774911f0f1e7a1d865cb2b113f88305a07a2e4aef2f4e5aff07814dc0` |
| v3 source asset digest | `7c3588072e21e5aa8944d136491ebc26e9dace14ab47929bd8672a75ffbac0e7` |
| v3 repaired USF | `1346b73da9cf72b6e866a722d929fd5c18305537f9ef3acd369f84ea808993d1` |
| v3 retained native USF | `bdd562bafeef47644e998cad413e246f10ff0d13bf172cf18d75cdf032e6cc13` |
| v3 parity summary | `c7d28c2f630eadd51cb042150c3162c4f5da811d02e59897e9c0314d6ae058a0` |
| Blender 5.0.1 executable | `f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c` |
| Blender 5.2.0 executable | `e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7` |

The host additionally pins the published base mesh host, variant inventory
host, mapped-path worker, and the 14 reviewed SDK files. It checks all
inputs before and after each run. Every final run returned
`sourceUnchanged`, `sdkUnchanged`, `nativeExportUnchanged` and
`repairedUsfUnchanged` as true. Six focused boundary tests passed, including
wrong-variant rejection, an empty source-object rejection, input hash
tampering and bounded packed-color mismatch details.

To repeat a run, use `cat_d11t_v3` or `cat_d11t_v2` with either reviewed
Blender executable:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_mesh_variant_payload `
  --asset cat_d11t_v2 `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

This readback does not compare material labels/strings or texture references,
skin bone identities and inverse-bind matrices, animation, hierarchy,
compilation, native-view behavior or tangent arrays. It does not replace the
accepted `usf-repair` route. `nativeBlendExportApproved` remains `false`.
