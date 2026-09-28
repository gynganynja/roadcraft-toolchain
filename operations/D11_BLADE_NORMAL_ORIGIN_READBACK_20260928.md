# D11 blade normal-origin readback — 2026-09-28

The 24 retained native/repaired stored-normal differences above 0.1° are
exactly three corners on each of eight triangles in five `cdt_blade_*` meshes.
They were selected from the earlier complete 60-leaf, 6,486-corner readback;
the [JSON receipt](d11_blade_normal_origin_readback_20260928.json) records
their exact IDs, measurements and input paths/hashes.

| Leaf | Triangle | Corner indices | Native/repaired angle | Native area (m²) |
| --- | ---: | --- | ---: | ---: |
| `cdt_blade_6` | 35 | 105–107 | 0.114506° | 5.96494e-5 |
| `cdt_blade_6` | 36 | 108–110 | 0.185323° | 1.34930e-8 |
| `cdt_blade_6` | 37 | 111–113 | 1.440533° | 2.96237e-7 |
| `cdt_blade_31` | 23 | 69–71 | 0.107082° | 4.61803e-6 |
| `cdt_blade_37` | 3 | 9–11 | 0.231248° | 1.34614e-5 |
| `cdt_blade_37` | 38 | 114–116 | 13.240520° | 6.47725e-8 |
| `cdt_blade_41` | 11 | 33–35 | 0.640289° | 1.58976e-6 |
| `cdt_blade_57` | 20 | 60–62 | 0.112365° | 9.97429e-7 |

In a fresh Blender 5.2 no-save process, the SDK's `UsfMesh.b_read` projected
all three positions and normals of every listed source triangle **exactly**
to the retained native USF. All eight source polygons are flat, have
`has_custom_normals=false`, and lack named `saber_normals` and `custom_normal`
attributes. The reviewed SDK therefore
selects `Mesh.corner_normals` for these triangles. Native/repaired positions
differ by at most 1.075e-7 m within these eight triangles; the earlier full
readback bounded all 6,486 corners by 4.815e-7 m. The triangles' minimum
altitudes range from 2.610e-6 to 2.874e-4 m. The repaired stored normal is
within 0.145° of its triangle's geometric normal on every listed face; the
native stored normal can differ by 13.241°.

Separate Blender 5.0.1 and 5.2.0 stage probes agreed on three witnesses
(`cdt_blade_6` triangle 37, `_37` triangle 38, `_41` triangle 11). Each had
`has_custom_normals=false`; its raw and evaluated corner normals matched.
After the SDK's `TO_SABER_CONVERT` mesh transform, the sampled corner normal
changed, while the polygon and triangle normals stayed aligned with the
geometric face normal. Mesh update and tangent calculation left that changed
corner normal in place. On `_37` triangle 38, the raw corner normal was
`[1,0,0]`, the transformed/retained native normal was
`[0.973417,-0.229039,0]`, and the repaired normal and both USF geometric
face normals were `[1,0,0]`. This locates where the **native SDK path**
introduces the largest stored-normal mismatch; it does not identify the
internal Blender normal algorithm or the operation that produced the accepted
repaired USF.

Inputs were SHA-256 checked before and after the no-save readbacks: source
Blend `1eadf10a…15731`, retained native USF `80c856b0…d21370`, accepted
repaired USF `49bfc77c…49e170`; Blender 5.0.1
`f81d3bca…f8f7c`, Blender 5.2.0 LTS `e27fbfea…a1074adf7`; SDK
`mesh.py` `4ab67112…be337` and `transform.py` `c79cd094…7d0101`.
The JSON receipt has the full hashes and exact paths. It is SHA-256
`5d7a31bf26020a7b69c4fafd73743a25aae7ebb070166ecb96d0e776a3f83b67`.
Prior full-readback manifests remain
[`blade geometry`](d11_blade_geometry_readback_manifest_20260928.json) and
[`blade payload`](d11_blade_payload_readback_manifest_20260928.json).

The next bounded proof is a no-save disposable-source projection: set a
corner-domain `saber_normals` attribute from the accepted repaired USF for
exactly these mapped blade corners, then verify all 60 emitted normal arrays
against the accepted repaired USF and prove all other source fields unchanged.
Do not blanket-recalculate: four repaired outlier faces still differ from
their geometric face normal. Any later scratch Blend save or USF export needs
its exact source/destination invocation authorization. This diagnostic does
not prove collision/physics behavior, bone/material parity, engine-loaded
geometry or the native-Blend export gate. Neither accepted input was saved or
exported.
