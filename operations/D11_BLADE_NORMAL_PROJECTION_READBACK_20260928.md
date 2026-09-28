# D11 blade normal projection readback — 2026-09-28

Two independent, pinned Blender 5.0.1 and 5.2.0 LTS no-save processes tested
a narrowly scoped normal-authoring mechanism on the 60 historical
`cdt_blade_0`–`cdt_blade_59` collision meshes. Each process opened the
accepted Blend in memory, assigned the accepted repaired USF's ordered normal
vectors to a temporary corner-domain `saber_normals` attribute, called the
reviewed SDK's `UsfMesh.b_read`, and removed the attribute. The vectors must
be supplied directly in Saber coordinates; a one-leaf inverse-axis trial did
not reproduce the repaired normal array.

| Check | Both Blender versions |
| --- | ---: |
| Mapped leaves / triangles / ordered corners | 60 / 2,162 / 6,486 |
| Unmodified source projection matching retained native on all six measured fields | 60/60 leaves |
| Projected normal arrays matching accepted repaired USF exactly | 60/60 leaves, 6,486/6,486 corners |
| Projected positions, face material/edge indices, UVs, packed colors and skin indices/weights unchanged from source/native | 60/60 leaves per field |
| Complete ordered row digest | `533058ffdaa47a8aa064c284c7f717096dc27282a3dd300fab7330d50b00fa23` |

The source inventory check established that all 60 meshes are triangles with
unique mesh data and no pre-existing `saber_normals` or custom-normal data.
The worker required an exact one-to-one source-loop to repaired-corner mapping,
source/native baseline equality, exact projected/repaired normal arrays, and
unchanged non-normal field digests on every row. Both processes checked the
accepted source, retained native/repaired USFs, reviewed SDK and diagnostic
code before and after use. Neither saved a Blend nor exported a USF.

[The manifest](d11_blade_normal_projection_readback_manifest_20260928.json)
pins the inputs, code and both full receipts. It is SHA-256
`6c997b7e57b30c82ad8381d3a8540a2fc28390a1eaec76fb4037d56c4f7b80aa`.
The Blender 5.0.1 and 5.2.0 receipt hashes are respectively
`305704d1b6c6fab188898f8c637e63b804083141e0c03ac469352fda26cb13f8`
and `ded6b8fe1f6683dde9850104f8dd4639981a99b250898e50841c90f1c701c929`.
The host and worker hashes are respectively
`69c839ccc693c570e4b82c32ecd39741f9d6f2786d27042d0ed2d77ece3b0e0c`
and `5cbccc066898089906fe766a8ce2f6e040cd925257ae236674bdaeda3382b3b4`.
Four focused receipt-boundary tests passed.

Reproduce a no-save process with:

```powershell
$env:PYTHONPATH='C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain\src'
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_blade_normal_projection `
  --registry 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain\project.json' `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

This establishes a feasible **in-memory normal-payload mapping**, not an
authored source repair. It does not prove attribute persistence after a Blend
save/reload, a fresh USF export, accepted geometry parity, collision/physics
behavior, bind/material identity, animation or game-loaded appearance. The
accepted source and repaired USF remain unchanged, the `usf-repair` build route
remains authoritative, and the native-Blend export gate remains blocked.
