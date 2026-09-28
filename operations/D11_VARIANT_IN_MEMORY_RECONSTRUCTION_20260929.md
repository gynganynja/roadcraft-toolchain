# D11 variant in-memory structural reconstruction — 2026-09-29

The accepted `cat_d11t_v2` and `cat_d11t_v3` authoring entries point to
separate historical Blend paths. Those files have the same SHA-256 bytes as
the base Blend (`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`).
Their repaired USFs have different bytes but the same 400-path structural
target, established in `D11_VARIANT_STRUCTURAL_TARGETS_20260929.md`.

A pinned, no-save Blender experiment opened **each variant's own Blend path**,
applied the maintained push-arm, blade-roll, ladder and seven-bone edits in
memory, and then compared the resulting 399 pose-bone paths plus the existing
bone-parented `sfx` Empty with **that variant's repaired USF**. The existing
repair workers use the base repaired USF as their edit target; this experiment
separately parses the variant repaired USF for the final comparison. It does
not claim that the workers were retargeted to variant USF bytes.

| Asset | Blender | Variant repaired USF SHA-256 | Shared structural paths | Changed paths | Max shared matrix element error |
| --- | --- | --- | ---: | ---: | ---: |
| `cat_d11t_v2` | 5.2.0 LTS | `096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a` | 400/400 | 0 | `2.2687017917633057e-6` |
| `cat_d11t_v3` | 5.2.0 LTS | `1346b73da9cf72b6e866a722d929fd5c18305537f9ef3acd369f84ea808993d1` | 400/400 | 0 | `2.2687017917633057e-6` |
| `cat_d11t_v2` | 5.0.1 | `096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a` | 400/400 | 0 | `2.2687017917633057e-6` |
| `cat_d11t_v3` | 5.0.1 | `1346b73da9cf72b6e866a722d929fd5c18305537f9ef3acd369f84ea808993d1` | 400/400 | 0 | `2.2687017917633057e-6` |

All runs returned `IN_MEMORY_VARIANT_STRUCTURAL_MATCH` with zero source-only
and repaired-only paths. They validated the 400-path base reconstruction,
including its source mesh world-matrix tolerance, before the variant
comparison. The inventory, reviewed SDK imports, source Blend files and both
repaired USFs were hash-checked; input hashes and SDK pins were rechecked
afterward. No Blend was saved, USF exported, or accepted asset changed.

The exact experimental source is retained at
`operations/probes/variant_in_memory_reconstruction_probe_20260929.py` and its
disposable execution copy is
`local/variant_in_memory_reconstruction_probe_20260929.py`; both have SHA-256
`1237402df7e3f5414e698cd9513f185b781529162b377fd503270761f24e5271`.
The script derives its toolchain root from its location under `local`, so for
a fresh checkout first copy the versioned source to that ignored location and
verify the hash. From the RoadCraft development package, then run with either
reviewed Blender version and either `--asset cat_d11t_v2` or
`--asset cat_d11t_v3`:

```powershell
New-Item -ItemType Directory -Force 'RoadCraftToolchain/local' | Out-Null
Copy-Item 'RoadCraftToolchain/operations/probes/variant_in_memory_reconstruction_probe_20260929.py' `
  'RoadCraftToolchain/local/variant_in_memory_reconstruction_probe_20260929.py'
$probeSha = (Get-FileHash 'RoadCraftToolchain/local/variant_in_memory_reconstruction_probe_20260929.py' -Algorithm SHA256).Hash.ToLowerInvariant()
if ($probeSha -ne '1237402df7e3f5414e698cd9513f185b781529162b377fd503270761f24e5271') { throw 'Probe bytes differ' }
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup --disable-autoexec --threads 1 `
  --python-exit-code 1 `
  --python 'RoadCraftToolchain/local/variant_in_memory_reconstruction_probe_20260929.py' `
  -- --asset cat_d11t_v2
```

This verifies static hierarchy and transforms for the variant source paths.
It does not verify USF writer output, variant meshes, materials, binds,
animation payloads, collision, compilation, native appearance, or campaign
acceptance. Both variants retain `usf-repair` build inputs and separate
`native-blend` parity gates.
