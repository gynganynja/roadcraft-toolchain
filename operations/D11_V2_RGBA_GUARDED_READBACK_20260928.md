# D11 v2 guarded RGBA readback — 2026-09-28

The prior pinned, unguarded Blender 5.2 source readback intermittently packed
white for 1,200 of 59,238 colors in `Ripper_vis_LOD1`, while the same live
evaluated mesh's raw RGBA packed statelessly matched the retained native USF
at every position. A separate scratch-mesh diagnostic reproduced a stale
`RGBA_CACHE` key after an evaluated mesh was freed. This readback tests the
opt-in immutable-key guard against the complete 126-row v2 mesh worklist.

The [execution manifest](d11_v2_rgba_guarded_readback_manifest_20260928.json)
has SHA-256
`6161ab347f37ec470b87a2c32343b4c47fec5d9c25940d4e12037d85d0ba3a45`.
It pins the exact command, 14 SDK files, Blender, accepted Blend, repaired and
retained native USFs, reviewed workers, guard, tests, installed PAK, receipt
hashes, and the two distinct UTC invocation intervals. The guarded host,
worker, test and guard module hashes are respectively
`902a904ebee0978d1c997a69636704cbbe0d2bc9bfa7cf9a7e5603cddad3ec13`,
`902ab34cbffed884831cf2a8c272291f34188fcb2c7395c07dcf231743b3a612`,
`89b7cdf0cd7e937b250e304b0bb5703b2f59969b80669bb8ee706db64ccf5e52`,
and `9a8454527dde123a7f6fdcc4daf55b53662c570b844b2a9614a01a1e53b5813c`.

The new worker calls the previously reviewed 126-row projection worker
without changing its pinned files. Before the accepted v2 Blend opens, an
instance `UsfMesh.b_read` lookup returns the installed SDK method unchanged;
native and repaired USF parsing occur in that phase. The worker requires an
unopened startup scene and the exact pinned Blend path before it counts a
source mesh call. At the first source call it enters **one**
`immutable_rgba_cache` context. The SDK's numeric clipping and ARGB packing
expression still performs every conversion, but receives immutable RGBA tuple
keys. That same cache remains active across all 126 source projections and is
cleared when the context closes immediately after the 126th call. The
temporary class hook and packer restore in `finally` paths, including an
exception. Three synthetic boundary tests passed for pre-open pass-through,
cross-row tuple-key behavior and restoration after failures. The reused
worker's boundary identity checks passed, but the SDK packer **was temporarily
guarded** during source projection; the guarded receipt states that explicitly.

| Fresh Blender process | UTC interval | Native color rows | Guard calls | Receipt |
| --- | --- | ---: | ---: | --- |
| [Run 1](d11_v2_rgba_guarded_readback_run1_20260928.json) | 10:33:32.5123128–10:35:05.4713536 | 126 / 126 | 194,121 pack calls across 126 mesh reads | `2f46525b05f059f447c21198bb605ce478c0c08bea50c5d95aef15468fb4a636` |
| [Run 2](d11_v2_rgba_guarded_readback_run2_20260928.json) | 10:35:20.1563231–10:36:53.2635367 | 126 / 126 | 194,121 pack calls across 126 mesh reads | `2f46525b05f059f447c21198bb605ce478c0c08bea50c5d95aef15468fb4a636` |

Both separate processes produced the same compact JSON receipt and therefore
the same receipt hash. **The receipt omits invocation time**; the manifest
records the distinct UTC intervals. Every mapped row's packed colors matched
the retained native USF in each run. The target's 59,238 colors shared native
SHA-256
`aa3e170d0a56390032c339a0607d13c1151cbb8c3350abb88fd41873e057d9b7`,
and the complete 126-row digest was
`5965d7327d72a81aa04f7ef1255265b6da6fba14cdd2c737b91f184db1f6a6b0`.
No conditional raw target read was needed. The guard reported exactly one
context, 126 source reads, packer and class-hook restoration, and an empty
cache afterward. Input and SDK hashes remained pinned. The installed accepted
PAK stayed at
`3e3d21b877ad6e52c61de7665a90fe3a9e4dd3761c0f3115fc734938caf4aa16`.

These two no-save, no-export readbacks support the guard as a way to avoid the
observed source color discrepancy. They do **not** prove writer serialization
parity, full USF export parity, material or animation parity, or behavior in
the native editor. The historical unguarded failure remains intermittent; a
two-run match does not measure its frequency. Neither Blender source assets
nor SDK files were edited, no Blend was saved, no USF was exported, and the
`nativeBlendExportApproved: false` gate remains in force. Painter and the
native editor were not launched.
