# D11 base source-mesh payload readback — 2026-09-28

The pinned, **no-save** diagnostic compared all 126 changed mesh paths in the
reconstruction worklist with the retained base scratch native USF. It used the
reviewed Saber SDK's `UsfMesh.b_read(obj)` on each mapped historical Blend
object, which creates the export projection **in memory** from the evaluated
mesh. It did not call `UsfMesh.write`, `usf_save`, `export_to_usf`, a Blender
save, or any accepted-asset writer. A read-only SDK parse supplied the
corresponding native USF mesh. The process emits bounded JSON on stdout and
accepts no output or export path.

Blender 5.0.1 and 5.2.0 each returned
`SOURCE_NATIVE_MESH_PAYLOAD_READBACK`: 126/126 source paths mapped, 126/126
rows matched every compared component, and the same complete rows digest
`b647996315d34497755fbba20455da933e6c1b3dcce8c63f5826546eb80f6501`.
The result is an exact SHA-256 match of canonically encoded semantic values:
float components are quantized to the SDK's float32 wire precision, and array
lengths, layer order and UV names are included. The digests are not hashes of
literal serialized USF mesh bytes.

| Compared component | Matching rows, Blender 5.0.1 | Matching rows, Blender 5.2.0 |
| --- | ---: | ---: |
| Triangle-corner positions | 126/126 | 126/126 |
| Triangle-corner normals | 126/126 | 126/126 |
| Face material and edge indices | 126/126 | 126/126 |
| UV layer names and triangle-corner coordinates | 126/126 | 126/126 |
| Packed vertex colors | 126/126 | 126/126 |
| Per-corner skin bone indices and float32 weights | 126/126 | 126/126 |

The worker digests the actual `UsfMesh.b_read` arrays in their stored order,
with float components rounded to the SDK's `BinaryIO.write_float` precision.
It uses a canonical comparison encoding for array lengths, names and face
material/edge fields; the SDK's face writer packs the latter into one integer.
It does not serialize a USF. Each native mesh is parsed with the same pinned
SDK and digested by the same comparison code.
The comparison is therefore stronger than the prior count-only inventory: it
checks payload values at the 126 exact source/native paths, not just their
lengths. The 5.0.1 and 5.2.0 row digests agree. Each real run took about 50
seconds with one Blender worker thread.

The worklist (SHA-256
`a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`)
pins the source Blend
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`,
repaired USF
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`,
base parity summary
`b116ea18837df190eec539b1173deb55926f79ad9b14339f3217c1b86128c87f`,
and retained native USF
`80c856b07b3ae1447f2748b5f6f8ec13c688c2594f3ebfaeada9e0d11da21370`.
The accepted authoring inventory is
`03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d`.
The Blender 5.0.1 and 5.2.0 executable hashes are respectively
`f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c`
and `e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`.
The 14 SDK file pins and the mapped-path worker pin are inherited from the
earlier no-save inventory. The new host pins the payload worker SHA-256
`f34d24f4c29628adc51e6483d002a602c11948205ee5b282b94912c379a9a553`.
The host SHA-256 at this review is
`2ec3051322517d68b07c99bd94710402bb32d2157e540996814e66e5925a1a4e`.
Every input, including the native USF and both workers, was hashed before and
after; the registry, inventory, source root and SDK were also rechecked. Both
readbacks reported `sourceUnchanged`, `sdkUnchanged` and
`nativeExportUnchanged` as true. Four synthetic boundary tests passed.

To repeat with either reviewed Blender version (substitute `Blender 5.0` for
`Blender 5.2`), run:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_mesh_payload `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

This **does not** establish full native-authoring parity. Tangent arrays are
excluded because the retained native exports showed low-bit
thread-sensitive tangent drift. Material payload strings and texture bytes,
skin bone identities and inverse-bind matrices, animation, hierarchy,
repaired-USF equivalence, compilation and native-view behavior are not
compared here. Matching source and native geometry at these 126 paths does
not repair their already documented differences from the accepted repaired
USF. The accepted `usf-repair` build route remains in place, and
`nativeBlendExportApproved` remains `false`.
