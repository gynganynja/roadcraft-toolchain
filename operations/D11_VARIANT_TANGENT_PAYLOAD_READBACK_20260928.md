# D11 v2/v3 source, native, and repaired tangent readback — 2026-09-28

This is a pinned, source-only diagnostic. Each of `cat_d11t_v2` and
`cat_d11t_v3` was opened separately from its accepted historical Blend path
under Blender 5.0.1 and 5.2.0 LTS. The worker projected each of the 126
worklisted meshes through the reviewed SDK's `UsfMesh.b_read(obj)` in memory
and parsed that variant's retained native USF and accepted repaired USF through
the SDK. It accounted for the native root name (`cat_d11t_v2` or
`cat_d11t_v3`) and repaired root name (`cat_d11t`) without treating that root
name difference as a mesh-path change.

All four runs returned `SOURCE_VARIANT_TANGENT_ARRAY_READBACK`, with identical
row digests and measured side summaries between Blender versions for each
variant. Every side mapped
all 126 paths. The ordered per-UV-layer tangent arrays were compared at
little-endian float32 bit precision after SDK projection; a signed-zero bit
change counts as a difference even when its absolute numeric difference is
zero. The row digests below are canonical diagnostic summaries, **not**
hashes of literal serialized USF mesh bytes.

| Variant and side | Comparable rows | Exact rows | Shape gaps | Different x / y / z / sign values | Row digest SHA-256 |
| --- | ---: | ---: | ---: | --- | --- |
| v2 source → retained native | 126 | 123 | 0 | 4,215 / 5,032 / 4,065 / 0 | `124becb17f7bd13daaea9b95021729cb3098734f63b3d9c2f44c58b85d32f83a` |
| v2 source → accepted repaired | 117 | 0 | 9 | 84,355 / 84,373 / 84,383 / 44,078 | `e790381f8392fa1bf97761d103ad27100aa6394ebbbb39d9e7de0639c136516a` |
| v3 source → retained native | 126 | 123 | 0 | 4,153 / 4,986 / 4,250 / 0 | `8ddc2362e101325511b6d7dff8992fcb2910e7c2b20144cb8b4ca3bfadad7489` |
| v3 source → accepted repaired | 117 | 0 | 9 | 84,355 / 84,373 / 84,383 / 44,078 | `e790381f8392fa1bf97761d103ad27100aa6394ebbbb39d9e7de0639c136516a` |

The native/source tangent differences occur on the same three paths in both
variants: `|@root|D11T_Rig.005|Blade_vis`,
`|@root|D11T_Rig.005|Ripper_vis`, and
`|@root|D11T_Rig.005|Ripper_vis|Ripper_vis_LOD1`. All remaining 123 native
rows have equal UV-layer names, shapes, and float32 tangent values. Native
maximum absolute component differences were at most
`1.7881393432617188e-7` (and signs matched throughout).

The nine repaired/source shape gaps are LOD0, LOD1, and LOD2 of each of
`Blade_vis`, `Body_vis`, and `Ripper_vis`. Their different-length tangent
arrays have no one-to-one ordered component correspondence, so they are
**excluded** from the repaired component counts. None of the 117 comparable
repaired rows matched exactly. Among those comparable rows, there were no
UV-layer-name mismatches. The maximum absolute difference in each component
was `2.0`. The equal repaired-side row digest across v2 and v3 reflects the
same diagnostic comparison result; it does not establish byte identity between
the two repaired files.

The source Blend bytes were pinned at SHA-256
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`.
The accepted authoring inventory and worklist were pinned at
`03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d`
and `a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`,
respectively. Variant-specific source asset digests and USF pins were:

| Variant | Source asset digest | Retained native USF SHA-256 | Accepted repaired USF SHA-256 | Accepted summary SHA-256 |
| --- | --- | --- | --- | --- |
| v2 | `6f6d47667c5dd24aa18fa1734aa2cbc7c6af48ac28bc57c67e8609f899f22d6f` | `0e533bbc80a95798824e69e5c6545cc50b9d98f0ba81e7f0e96d9e3a93c2dc3f` | `096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a` | `ffcc6bb774911f0f1e7a1d865cb2b113f88305a07a2e4aef2f4e5aff07814dc0` |
| v3 | `7c3588072e21e5aa8944d136491ebc26e9dace14ab47929bd8672a75ffbac0e7` | `bdd562bafeef47644e998cad413e246f10ff0d13bf172cf18d75cdf032e6cc13` | `1346b73da9cf72b6e866a722d929fd5c18305537f9ef3acd369f84ea808993d1` | `c7d28c2f630eadd51cb042150c3162c4f5da811d02e59897e9c0314d6ae058a0` |

The pinned Blender executable SHA-256 values were
`f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c`
for 5.0.1 and
`e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`
for 5.2.0. Fourteen reviewed SDK file hashes and the source, both USFs,
Blender executable, worker, host, mapping code, worklist, and summary pins
were checked before and after readback. Every run reported
`sourceUnchanged`, `sdkUnchanged`, and `nativeExportUnchanged` as true. The
source projection was also checked for equality between the native and
repaired phases.

The diagnostic used one background Blender worker thread with auto-execution
disabled, no asset output argument, no `UsfMesh.write`, `usf_save`,
`export_to_usf`, or Blender save. It did not start Painter or the native
editor, perform a scratch repair/export, or modify the accepted package.
`nativeBlendExportApproved` remains `false`. Four focused synthetic tests
passed for float32 comparison, shape/name handling, complete row coverage,
and contradiction/approval rejection.

To repeat one variant with either pinned Blender version, set `$asset` to
`cat_d11t_v2` or `cat_d11t_v3` and `$version` to `5.0` or `5.2`:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$asset = 'cat_d11t_v2'
$version = '5.2'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_tangent_variants `
  --asset $asset `
  --registry "$tc\project.json" `
  --blender "C:\Program Files\Blender Foundation\Blender $version\blender.exe" `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

This establishes source-projection differences against the two pinned USF
files at tangent-array level only. It does not identify the runtime cause of
the native three-row drift or the repaired array differences. It does not
establish repaired parity, native-view parity, fresh export behavior,
materials, skin bone identity, inverse binds, animation, compilation, or
in-game appearance.
