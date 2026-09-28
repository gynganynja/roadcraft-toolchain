# D11 combined in-memory repair check — 2026-09-29

The separately reviewed scratch USF export is still unexecuted. Before any
export, a pinned Blender 5.2.0 LTS run composed the base D11 push-arm,
blade-roll, ladder, seven-bone, blade-normal and wiper-hook steps in a single
live scene. It saved no Blend and exported no USF.

The structural worker matched all 399 pose-bone paths plus the source `sfx`
Empty against the 400 repaired USF structural paths. The blade-normal step
installed 60 reviewed blade mesh normal attributes, covering 2,162 triangles
and 6,486 corners; its row digest was
`533058ffdaa47a8aa064c284c7f717096dc27282a3dd300fab7330d50b00fa23`.
Because Blender mesh data is shared, 93 scene mesh objects saw those 60
installed data attributes. Binding the forward wiper action and installing the
inclusive bake hook left all 400 frame-one structural paths unchanged: zero
matrix differences, maximum element error zero, and no missing paths. The
hook's action order and sample counts were empty because no SDK export or
animation bake was invoked.

The exact no-save probe source is
`operations/probes/full_in_memory_repair_probe_20260929.py`, SHA-256
`d814d98496344f9b3ea7b2831df990becec1638545506d6f1f54325461f0c0ef`.
It derives its toolchain root from an ignored `local` execution copy and
requires the retained, read-only native scratch USF at
`local/blend-authoring-parity-base-normalized/candidate.usf`, SHA-256
`80c856b07b3ae1447f2748b5f6f8ec13c688c2594f3ebfaeada9e0d11da21370`.
From the Steam development-package root, the verified invocation was:

```powershell
Copy-Item 'RoadCraftToolchain/operations/probes/full_in_memory_repair_probe_20260929.py' `
  'RoadCraftToolchain/local/full_in_memory_repair_probe_20260929.py'
if ((Get-FileHash 'RoadCraftToolchain/local/full_in_memory_repair_probe_20260929.py' -Algorithm SHA256).Hash.ToLowerInvariant() -ne `
    'd814d98496344f9b3ea7b2831df990becec1638545506d6f1f54325461f0c0ef') { throw 'Probe bytes differ' }
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup --disable-autoexec --threads 1 `
  --python-exit-code 1 `
  --python 'RoadCraftToolchain/local/full_in_memory_repair_probe_20260929.py'
```

The final run exited zero and returned `IN_MEMORY_STRUCTURAL_MATCH`,
`IN_MEMORY_BLADE_NORMALS_INSTALLED`, `STATIC_ARMATURE_MATCH`, 400 shared
post-hook paths, zero changed matrices, `blendSaved: false` and
`usfExported: false`. This establishes in-memory compatibility only. It does
not establish the future USF writer's output, wiper animation samples,
mesh/material/bind payload parity, native compilation or visual acceptance.
The existing exact scratch export command and the `native-blend` route gate
remain unchanged.
