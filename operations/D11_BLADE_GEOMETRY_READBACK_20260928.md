# D11 blade-collision geometry readback — 2026-09-28

Two separate pinned Blender 5.0.1 and 5.2.0 processes parsed the retained
native and accepted repaired USFs without opening a Blend or running an exporter.
Both compared the same 60 `cdt_blade_*` leaves and 6,486 ordered triangle
corners. The source Blend, SDK, both USFs, host, worker and Blender binaries
were checked against SHA-256 pins before and after each readback.

| Measurement | Result in both versions |
| --- | ---: |
| Stored node world-matrix maximum element difference | 0 |
| Maximum local and world position difference | 4.814712530792806e-7 |
| RMS local and world position difference | 1.0170290968075304e-7 |
| Parent-compensated position rows within `1e-5` | 60/60 |
| Maximum proper rigid-fit residual | below 5.506e-7 |
| Stored normal corners differing by over 0.1° | 24/6,486, across five leaves |
| Stored normal corners differing by over 1° | 6/6,486 |
| Maximum stored normal angle | 13.240519621865587° |
| Maximum pairwise normal-dot change | 0.22903932874220842 |

The earlier ordered position digests differed on 58/60 leaves. This numeric
readback shows the difference is small float32-scale drift, not evidence of a
meaningful blade displacement. A proper rigid fit was checked independently;
it was not used to erase the measured residuals. The five normal-outlier leaves
are `cdt_blade_6`, `_31`, `_37`, `_41` and `_57`. On `_37`, corner 114 has
native normal `[0.973417,-0.229039,0]` and repaired normal `[1,0,0]`;
the corresponding triangle areas are about `6.48e-8` and `6.36e-8`.
Different pairwise normal dot products rule out one rigid rotation as the
explanation for that normal payload. Recalculation or precision sensitivity
around thin triangles is a hypothesis, not an established repair mechanism.

[The manifest](d11_blade_geometry_readback_manifest_20260928.json) pins the
two full 60-row receipts, inputs, host and worker. Receipt SHA-256s are
`c7becd55adfa8999189cf1062d74d41676942eb82f75a4fed4e21a35558234b3`
for 5.0.1 and `11e4908e150a269d24d778393755d98aec249f09c0f8d1aef15441a195465441`
for 5.2.0 LTS. Four focused numeric tests and the 359-test local suite passed,
with four machine-specific skips. Each receipt reports `blendSaved: false`,
`usfExported: false` and `equivalenceVerified: false`.

The comparison covers retained USF mesh-local positions, world positions,
stored normals and transform invariants. It does not establish collision or
physics behavior, tangents, material/bone identity, animation, or engine-loaded
geometry. The four native-only `cdt_blade_60`–`63` leaves remain outside the
60-leaf comparison. The accepted source and blocked native-Blend export gate
remain unchanged.

Reproduce a summary without writing an accepted asset:

```powershell
$env:PYTHONPATH='C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain\src'
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_blade_geometry `
  --registry 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain\project.json' `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script' `
  --summary-only
```
