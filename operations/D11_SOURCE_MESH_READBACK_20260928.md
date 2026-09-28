# D11 base source-mesh readback — 2026-09-28

The pinned, **no-save** Blender diagnostic inspected the historical
`cat_d11t.blend` at scene frame 1. It matched all 126 changed mesh-node paths
in the retained reconstruction worklist to unique source mesh objects by the
SDK's direct-parent and flat-LOD naming rules. For example, the source object
`Body_vis_LOD0` maps to the worklist node
`|@root|D11T_Rig.005|Body_vis`; LOD1/2 objects map beneath that node. This
is a checked source-object mapping for this readback, **not** proof that the
source mesh equals the repaired USF mesh, has equivalent binds, or exports
correctly.

Blender 5.0.1 and 5.2.0 each returned `SOURCE_GAP_INVENTORY`, with the same
complete 126-row source-facts digest
`b0600a3d72179da3d793c834fb4b7f1f9860a3da9352c72048be3604310c1efd`.
Both reported 210 scene mesh objects, 126 mapped gap rows, zero unmapped rows,
and zero rows where raw versus evaluated vertex or triangle counts changed.
All 126 source objects were visible, all 126 first armature modifiers targeted
`D11T_Rig.005`, and all 126 had group assignments on every raw vertex. The
diagnostic emits bounded JSON on stdout and
accepts no save, export, or output-file argument. Source Blend, repaired USF,
worklist, Blender binary, worker and SDK pins were checked before and after.
The source/SDK pins remained unchanged; no USF was exported.

| Worklist difference | Source readback in both Blender versions | Interpretation |
| --- | --- | --- |
| Repaired-only material labels | 135 label occurrences across all 126 changed mesh rows were absent from the corresponding evaluated source material slots. | Those labels are missing in the pinned historical Blend at the mapped mesh objects. This observation does not establish material payload or texture parity. |
| Material-slot count | The SDK-derived source count matched the retained native export, rather than the repaired USF, on all 126 rows. | The documented slot-count gap is already visible in the historical source. |
| Skin-bone UID count | The first armature modifier targeted `D11T_Rig.005` on all 126 rows; its source pose-bone count matched the retained native export, rather than the repaired USF. | The source-rig count predicts this native-export count gap. Bone identities, weights, inverse binds and behavior were not compared. |
| Recorded face/vertex/normal/skin-entry count gaps | On all nine affected rows, the SDK-derived counts from the evaluated source matched the retained native export. | The read-only source projection reproduces these native-export count gaps. It does not trace the actual exporter write, and no evaluated triangle-count change appeared between Blender 5.0.1 and 5.2.0. |

The nine count-gap rows belong to `Blade_vis`, `Body_vis` and `Ripper_vis` at
LOD0–2. The evaluated source and native-export face counts were identical:

| Source object | Source/native faces | Repaired faces |
| --- | ---: | ---: |
| `Blade_vis_LOD0` / `LOD1` / `LOD2` | 13,140 / 6,570 / 3,285 | 13,132 / 6,566 / 3,281 |
| `Body_vis_LOD0` / `LOD1` / `LOD2` | 164,391 / 95,063 / 59,933 | 141,912 / 87,844 / 55,337 |
| `Ripper_vis_LOD0` / `LOD1` / `LOD2` | 31,962 / 19,746 / 12,999 | 29,562 / 17,946 / 11,799 |

The diagnostic reads the **raw** mesh and a temporary dependency-graph
**evaluated** mesh separately. It records raw/evaluated vertex, polygon and
triangle counts; evaluated material names, UV layers, color attributes and
custom Saber color attributes; the first armature modifier target, its pose
bone count, vertex groups and the number of raw vertices with a group. The
SDK-derived count fields follow the pinned SDK's `scene.py` direct-parent/LOD
mapping and `mesh.py` unwelded face, normal, UV/color and skin rules. The
`material.py` rule uses the evaluated material's name. No geometry payload,
texture bytes or skin weights are emitted. The complete output has at most
126 rows and 512 KiB of canonical JSON; an incomplete or oversized result
fails closed.

The `sdkExpected*` fields are **predictions computed from read-only source
facts and the pinned SDK rules**, compared with values in the retained native
export archive. This run did not call the SDK exporter. Agreement on counts
and names does not establish exporter byte parity or explain inverse-bind
matrix differences.

Inputs are pinned by `project.json` and
`d11_blender_reconstruction_worklist_20260928.json` (SHA-256
`a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`).
The source Blend SHA-256 is
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`;
the repaired USF SHA-256 is
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`.
The reviewed Blender 5.0.1 and 5.2.0 executable hashes are respectively
`f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c`
and `e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`.
The host pins the worker SHA-256 as
`e29122c28bbe60a254a7c239fcc84be7d2f05a57c0ce305132069edd5b264113`;
`.gitattributes` preserves that worker's LF bytes on Windows. SDK hashes are
the reviewed `SDK_PINS` in `blender_left_push_probe.py`.

Run either installed Blender version; the command prints a single JSON object
and does not create a receipt or scratch export:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_mesh_inventory `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

This maps a significant part of the existing parity gap to source-observable
differences in the historical Blend. It does **not** assess the other 84
source meshes, exact geometry bytes, material payloads, inverse-bind matrices,
per-vertex weights, animation, compilation, native viewing or the v2/v3
assets. The accepted build remains `usf-repair`; `nativeBlendExportApproved`
remains `false`. Any repair belongs in a separate disposable authoring copy,
followed by full asset-specific parity and review.
