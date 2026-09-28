# D11 base source material payload readback — 2026-09-28

The pinned, **no-save** Blender diagnostic compared the 126 changed mesh paths
in the reconstruction worklist. For each mapped historical Blend object it
called the reviewed Saber SDK's `UsfMesh.b_read(obj)` in memory, then called
each projected `BlenderToUsfSimpleMaterial.build_string()`. It parsed the
retained scratch native USF and accepted repaired USF through `usf_read` for
the corresponding material structs. It did not call a USF writer, export,
Blender save, texture export, Painter, or a game editor. Its CLI has no output
path and emits one bounded JSON object on stdout.

Blender **5.0.1 and 5.2.0** both returned
`SOURCE_NATIVE_MATERIAL_PAYLOAD_READBACK`, with the same complete 126-row
digest `25d2f53b866aa932ffe8312dc06bbc85d022ed7b616c8f6a86c8f25a3db47214`.
Both runs found:

| Comparison | Matching rows or count |
| --- | ---: |
| Source/retained-native ordered material structs and full generated text | 126/126 rows |
| Source/native ordered material labels | 126/126 rows |
| Source/native ordered nonempty texture-name references | 126/126 rows |
| Source/native ordered per-face material-slot indices | 126/126 rows |
| Source/repaired full material payload | 0/126 rows |
| Source/repaired per-face material-slot indices | 0/126 rows |
| Source/native material-slot occurrences | 711 / 711 |
| Repaired material-slot occurrences | 846 |
| Repaired-only material-label occurrences absent from source | 135 |

The source/repaired face-index figure was calculated from the emitted rows as
the count whose `source.faceMaterialIndices` summary equals the corresponding
`repaired.faceMaterialIndices` summary. It was 0 in the 5.2.0 run; the 5.0.1
run returned the identical complete rows digest, so its emitted rows agree.
This index difference also reflects the known geometry changes and must not
be attributed solely to material-slot changes.

The per-slot SHA-256 covers the complete SDK material text string; the ordered
slot digest also includes struct version and vertex-color-usage fields. Thus
the result includes the SDK's generated material name, ordered layer texture
names, albedo tints, UV-set name, material type, and all other textual shader
defaults and parameters in those strings. The per-face digest covers material
indices in stored triangle order, with range checks against slot count.
Extracted labels, texture references and albedo tints help classify a mismatch;
the full-string hash supplies the comparison. These are hashes of decoded
material text and semantic fields, **not** literal serialized USF bytes.

The 135 repaired-only labels equal the earlier count-only source readback and
the worklist's label gap. The source's 711 nonempty texture-name references
are names that the SDK picks from Blender image-texture nodes (or its
`sc_grey_100` fallback). This diagnostic did **not** compare image pixels,
packed data, external texture paths, Painter outputs, or whether shader graph
links render as intended. The SDK material conversion itself reads only image
node names and Principled BSDF Base Color; its other generated material fields
come from a fixed template. Source/native agreement therefore establishes
parity of this SDK projection and retained native export at the mapped paths,
not complete source shader semantics or native rendering.

Inputs were pinned before and after both runs: source Blend SHA-256
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`,
accepted repaired USF
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`,
retained native USF
`80c856b07b3ae1447f2748b5f6f8ec13c688c2594f3ebfaeada9e0d11da21370`,
worklist `a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`,
and accepted authoring inventory
`03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d`.
Both runs returned `sourceUnchanged`, `sdkUnchanged`,
`nativeExportUnchanged`, and `repairedUsfUnchanged` as true. Blender 5.0.1
and 5.2.0 executable hashes were respectively
`f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c`
and `e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`.
The SDK's 14 reviewed source pins and mapped-path worker pin were checked by
the host and worker. The material worker SHA-256 is
`26020a54b4278dc0285784668eddb83fc62b86182642408c3998e04c514c7bcc`;
the material host SHA-256 at this review is
`681f70389f424e342d66d9f3bd392d59ca1d9c33368a0c3106decda692f39ad7`.
Five synthetic tests passed: parameter and texture mutation, ordered slots,
face-to-slot changes, invalid face references, complete coverage and forged
payload rejection.

To rerun with either reviewed Blender version (substitute `Blender 5.0` for
`Blender 5.2`):

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_material_payload `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

This result closes the source-to-retained-native material-text question for
the 126 mapped base meshes. It does **not** resolve their differences from the
accepted repaired USF, the 84 other source meshes, hierarchy, animation,
inverse bind, shader-graph behavior, texture bytes, compilation, or native
viewing. The accepted `usf-repair` route remains in place and
`nativeBlendExportApproved` remains `false`.
