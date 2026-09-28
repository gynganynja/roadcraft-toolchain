# D11 v2 / Blender 5.2 RGBA discriminant — 2026-09-28

The previous pinned mesh-payload readback produced one fresh-process v2/5.2
failure: 2,650 of 59,238 packed colors in
`|@root|D11T_Rig.005|Ripper_vis|Ripper_vis_LOD1` were white in the SDK
projection where the retained native USF had varying grays. Its immediate
same-code repeat matched. The present **no-save** probe was built to separate
call-time Blender color input from SDK cache/packing output if that mismatch
recurred. The historical pair and its compact receipts are documented in
`D11_VARIANT_SOURCE_MESH_PAYLOAD_READBACK_20260928.md`.

The separate host `blender_rgba_discriminant.py` and worker
`blender_rgba_discriminant_worker.py` reused the unchanged pinned 126-row v2
mesh-payload worker. The new worker wrapped
`UsfMeshColorSet.rgba_to_saber` **in memory** for the readback, but collected
extra RGBA detail only while projecting the target LOD1 mesh. It recorded the four
call-time RGBA floats, cache hit and prior value, an independent stateless
implementation of the SDK's clip/truncate/pack expression, and the SDK's
return. The wrapper was restored in `finally`. The one-color-set trace was
compared with the target's retained native packed array, and only aggregate
counts and at most 12 differing samples could leave the Blender process.
The probe also retained the original 126-row payload digest. It did not save a
Blend, export a USF, invoke Painter or the native editor, or modify accepted
assets. No previously pinned host or worker file changed.

All input pins validated before the first Blender launch, including the
accepted v2 Blend, retained native and repaired USFs, worklist, summary, the
14 reviewed SDK files, and the Blender 5.2.0 executable. Three separate
fresh-process runs then completed under identical code, input and executable
pins. The [machine-readable manifest](d11_v2_rgba_discriminant_blender52_manifest_20260928.json)
(SHA-256 `393da98221e0c708eb52f15c40df3bf6b79271b43fc7c26869e13c088e41b833`)
contains paths, SHA-256 pins and each receipt hash.

| Fresh run | Packed-color rows matching native | Target SDK/native differences | Stateless/native differences | SDK/stateless differences | Target cache hits | Cache size immediately before/after LOD1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [1](d11_v2_rgba_discriminant_blender52_run1_20260928.json) | 126/126 | 0/59,238 | 0/59,238 | 0/59,238 | 9,060 | 85,214 / 135,392 |
| [2](d11_v2_rgba_discriminant_blender52_run2_20260928.json) | 126/126 | 0/59,238 | 0/59,238 | 0/59,238 | 9,060 | 85,214 / 135,392 |
| [3](d11_v2_rgba_discriminant_blender52_run3_20260928.json) | 126/126 | 0/59,238 | 0/59,238 | 0/59,238 | 9,060 | 85,214 / 135,392 |

Each target projection produced the retained native packed-color digest
`aa3e170d0a56390032c339a0607d13c1151cbb8c3350abb88fd41873e057d9b7`.
Each complete 126-row digest was
`5965d7327d72a81aa04f7ef1255265b6da6fba14cdd2c737b91f184db1f6a6b0`.
The SDK's RGBA argument had Python type `bpy_prop_array`. The 9,060 cache hits
all returned the same packed value as stateless packing; there were no
cache-hit or cache-miss disagreements. The cache counters in the table bracket
**this target LOD1 projection**. The earlier payload report sampled its cache
immediately before LOD2, after the LOD1 mismatch. Neither set of counters
establishes a causal mechanism.

The three bounded receipt files have identical deterministic JSON bytes and
therefore the same SHA-256:
`85aa1ea500441241ab509bde331fbc0b09c9df46664047d725185b9f022c34c2`.
The manifest records their separate local write times. The execution
transcript shows separate process invocations; the receipts themselves contain
no process identifier or nonce and cannot independently prove three distinct
runs. They do retain the new host/worker, reviewed host/worker and Blender
executable SHA pins, no-write flags, aggregate counts and target color digest.
The manifest supplies the accepted source, native, repaired, worklist,
summary, registry, inventory and SDK file pins. It does not contain full
per-corner RGBA arrays or all 126 per-row results.

Four focused discriminant boundary tests and six existing variant-payload
tests passed. They cover raw-input versus cache-return classification, trace
shape/digest rejection, no-write identity rejection and bounded samples. The
fresh runs **did not reproduce** the intermittent 2,650-color failure, so
this experiment does not identify its cause and does not establish stable
v2/5.2 color parity. The in-memory tracing wrapper itself may affect timing
or memory layout, another reason not to treat non-reproduction as resolution.
A future failing call-time trace could discriminate a
white/raw Blender color input from a cached SDK return that differs from
stateless packing. Native-Blend export approval remains `false`.

The exact repeat command is:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_rgba_discriminant `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```
