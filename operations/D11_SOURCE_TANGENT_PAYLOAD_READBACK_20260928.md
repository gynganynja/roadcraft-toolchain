# D11 base source/native tangent readback — 2026-09-28

The pinned, no-save diagnostic projected each of the 126 mapped historical
Blend meshes through the reviewed Saber SDK's `UsfMesh.b_read(obj)` **in
memory**, then compared its ordered per-UV-layer tangent arrays with the SDK's
read-only parse of the retained base scratch native USF. It ran with one
Blender worker thread, with no asset output argument. The worker did not call
`UsfMesh.write`, `usf_save`, `export_to_usf`, or a Blender save. It did not run
the native editor or Painter.

Blender 5.0.1 and 5.2.0 LTS independently returned
`SOURCE_NATIVE_TANGENT_PAYLOAD_READBACK`: 126/126 mapped paths, 123/126 exact
tangent matches, and the identical full row digest
`029ab2cc99ab614815a3bab384c18931977d9d8a0b6308e557fbc2830c2994c5`.
Across 1,305,801 ordered tangent vectors, each float was rounded to the SDK's
float32 precision before comparison. Equality means equal float32 bit patterns
in the SDK's in-memory projection and parsed USF values; these digests are
**not** hashes of literal serialized USF mesh bytes. A signed-zero bit change
counts as a difference even if its numeric absolute difference is zero.

| Component | Differing values, 5.0.1 | Differing values, 5.2.0 | Maximum absolute difference |
| --- | ---: | ---: | ---: |
| Tangent x | 5,328 | 5,328 | 1.7881393432617188e-7 |
| Tangent y | 6,343 | 6,343 | 1.1920928955078125e-7 |
| Tangent z | 5,652 | 5,652 | 1.7881393432617188e-7 |
| Handedness sign | 0 | 0 | 0 |

The 17,323 differing float32 values are limited to the same three mesh paths
in both Blender versions. All other 123 tangent rows match completely:

| Native/source path suffix | Tangent vectors | Differing x | Differing y | Differing z | Differing signs |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Blade_vis` | 39,420 | 1,972 | 2,933 | 2,371 | 0 |
| `Ripper_vis` | 95,886 | 1,391 | 1,409 | 1,402 | 0 |
| `Ripper_vis|Ripper_vis_LOD1` | 59,238 | 1,965 | 2,001 | 1,879 | 0 |

The paths are respectively
`|@root|D11T_Rig.005|Blade_vis`,
`|@root|D11T_Rig.005|Ripper_vis`, and
`|@root|D11T_Rig.005|Ripper_vis|Ripper_vis_LOD1`.
Each has one tangent/UV layer. The source/native layer lengths matched at all
126 paths. The comparison includes layer order, array lengths, and all four
components. It rejects missing paths, duplicate mapped objects, changed pins,
non-finite floats, incomplete worker results, and contradictory match flags.

The source Blend SHA-256 is
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`,
the accepted repaired USF SHA-256 is
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`,
the reconstruction worklist SHA-256 is
`a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`,
and the retained native scratch USF SHA-256 is
`80c856b07b3ae1447f2748b5f6f8ec13c688c2594f3ebfaeada9e0d11da21370`.
The accepted authoring inventory SHA-256 is
`03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d`.
The Blender 5.0.1 and 5.2.0 executable SHA-256 values are respectively
`f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c`
and `e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`.
The 14 reviewed SDK file pins are rechecked before and after. The new host
SHA-256 is `16f391d31a02f0e55d10f87fa7ae6d3f4ab36011db01d8ea708dca2d3ddcd029`;
its Blender worker SHA-256 is
`12fe33903af200229f989f7ca707b786bad5b8fd0e869aa9645ca99a062a3058`.
Both final runs reported `sourceUnchanged`, `sdkUnchanged`, and
`nativeExportUnchanged` as true. Four focused synthetic tests passed.

To repeat with either reviewed Blender version, set `$version` to `5.0` or
`5.2` and run:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$version = '5.2'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_tangent_payload `
  --registry "$tc\project.json" `
  --blender "C:\Program Files\Blender Foundation\Blender $version\blender.exe" `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

This corroborates the earlier retained-export tangent-only drift and narrows
the source/native tangent difference to three meshes, but does not establish the
runtime cause inside Blender's tangent calculation. It does not compare
material payload, skin bone identities, inverse-bind matrices, animation,
the accepted repaired USF's tangent arrays, a new serialized native export,
compilation, or native in-game appearance. The accepted `usf-repair` route
remains in place and `nativeBlendExportApproved` remains `false`.
