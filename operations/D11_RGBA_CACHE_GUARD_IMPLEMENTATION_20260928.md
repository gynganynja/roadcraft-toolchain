# D11 opt-in RGBA cache guard implementation — 2026-09-28

The reviewed SDK `saber/blender/lib/usf/mesh.py` (SHA-256
`4ab671128044524524028dbea32a5c7dcaf5274630348de151592c87b08be337`)
uses a live Blender `bpy_prop_array` as the key in a module-global RGBA cache.
The no-save v2 readback documented in `D11_V2_RGBA_LIVE_DISCRIMINANT_20260928.md`
recorded one intermittent run where the SDK packed 1,200 of 59,238 target
colors differently from the retained native USF, while stateless packing of
the live raw RGBA matched all 59,238 native values. The disposable-mesh
diagnostic in `D11_RGBA_CACHE_LIFETIME_20260928.md` reproduced reuse of a
cleared color wrapper as a stale key in Blender 5.0.1 and 5.2.0.

The new scratch-only guard is **opt-in** through `blender_authoring.py
--rgba-cache-guard`. It accepts only the pinned `cat_d11t_v2` Blend, repaired
USF, Blender 5.2 executable, reviewed SDK mesh module and guard module. The
host checks those fixed pins before creating scratch output, and the Blender
helper checks them again before opening the Blend. During `export_to_usf`
only, it snapshots each
four-channel RGBA value into a tuple and passes that tuple to the original SDK
`rgba_to_saber` function. That function still performs its own clipping,
truncation and ARGB packing. The process-local cache is cleared before and
after export, and the original method is restored in `finally`. The helper
records the pack-call count, restoration and cache-clear result; the host
requires that attestation and re-hashes the guard module and SDK afterward.
The installed SDK is unchanged. Without `--rgba-cache-guard`, the Blender
command and compact receipt fields remain as before.

| File | SHA-256 |
| --- | --- |
| `src/roadcraft/blender_rgba_cache_guard.py` | `9a8454527dde123a7f6fdcc4daf55b53662c570b844b2a9614a01a1e53b5813c` |
| `src/roadcraft/blender_authoring.py` | `b4bf093e503737d00eac7752e8dc604fd0f93c0d3250b7d06ff11f22032c79d1` |
| `src/roadcraft/blender_authoring_helper.py` | `9e15cd104af4f352c78f94e827d0ba49e1619737629df4f799b865dfa0c055c7` |
| `src/roadcraft/blender_parity_evidence.py` | `3953c9272b7462a2a85d6034c8c9730b2d12a4b2ef4ef9901b2ef9bdb79461f8` |
| `tests/test_blender_rgba_cache_guard.py` | `e920c03e0ccf8c16090aef636344d4dac7a878867cfa6afff179eefb745619a8` |
| `tests/test_blender_authoring.py` | `6ecec54c7f1670606918422d1a5919fb26f4d56efe9e83a93e84a0bd18a16648` |

The focused synthetic tests passed: 20 tests in the guard and authoring
modules. They cover a reused-wrapper white/gray collision, unchanged numeric
packing and clipping for representative colors, restoration after an export
exception, invalid RGBA and FAST_PACK rejection, exact input pins, preflight
with no scratch creation (including a changed guard module), command and
receipt opt-in, missing helper attestation and the closed native-export gate.
The full local suite passed: 339 tests, four machine-specific skips. No
Blender process was launched for
this implementation checkpoint, no Blend was saved, no USF was exported, and
neither Painter nor the native editor was started.

This is a guarded implementation, not a demonstrated v2 export fix. A future
scratch run needs its own exact source/destination authorization and must
verify the candidate's packed colors and full mesh/rig/animation parity.
The existing pending approval request was not changed; adding the new opt-in
flag would be a different invocation. `nativeBlendExportApproved` remains
`false`, and the accepted `usf-repair` build route remains in force.
