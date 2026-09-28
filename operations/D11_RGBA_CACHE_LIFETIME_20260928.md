# D11 SDK RGBA cache lifetime diagnostic — 2026-09-28

The reviewed Saber SDK keeps a module-global `RGBA_CACHE` keyed directly by
Blender `bpy_prop_array` color wrappers (`mesh.py` lines 206–215). The existing
source mesh probe obtains those wrappers from a temporary evaluated mesh and
calls `to_mesh_clear()` after each projection. A cleared mesh's wrapper can
remain as a cache key. This new **no-save** diagnostic reproduces that
cache-key lifetime fault using two disposable in-memory Blender meshes only;
it never opens an accepted Blend or USF, changes the installed SDK, saves a
file, exports an asset, or launches Painter or the native editor.

The worker first asks the SDK to pack white `(1, 1, 1, 1)`, filling its cache
with `0xffffffff`. It clears that evaluated mesh, obtains a gray
`(0.2, 0.3, 0.4, 1)` color from another evaluated mesh, and looks for a
wrapper that hashes and compares equal to the retained white cache key. A
hard limit of 4,096 gray `to_mesh` attempts fails to a non-reproduced result
instead of making an unbounded claim. At a collision it records the SDK's
cached return, clears only the disposable process's in-memory `RGBA_CACHE`,
and packs the **same** gray wrapper again as a control.

| Pinned Blender executable | Collision attempt | Gray raw RGBA | SDK before cache clear | SDK after cache clear | Result |
| --- | ---: | --- | --- | --- | --- |
| 5.0.1 | 0 | `(0.20000000298, 0.30000001192, 0.40000000596, 1)` | `0xffffffff` | `0xff334c66` | `SDK_RGBA_STALE_CACHE_REPRODUCED` |
| 5.2.0 LTS | 0 | `(0.20000000298, 0.30000001192, 0.40000000596, 1)` | `0xffffffff` | `0xff334c66` | `SDK_RGBA_STALE_CACHE_REPRODUCED` |

Both independent background processes reported `bpy_prop_array` keys, equal
hash and key comparison at the collision, a single cached white entry before
and after the stale return, one newly cached gray entry after the clear, and
`inputsUnchanged: true`. Four focused boundary tests passed. The complete
single-line host results from separate fresh invocations are preserved as
[Blender 5.0.1 JSON](d11_rgba_cache_lifetime_blender50_20260928.json) and
[Blender 5.2.0 JSON](d11_rgba_cache_lifetime_blender52_20260928.json).
The [execution manifest](d11_rgba_cache_lifetime_manifest_20260928.json)
records each exact host and Blender command, UTC start and finish times,
the Python and Blender executable hashes, host and worker hashes, and all
14 reviewed SDK file hashes.

| Receipt | Invocation UTC | Receipt SHA-256 |
| --- | --- | --- |
| Blender 5.0.1 | `2026-09-28T09:40:37.473918Z`–`09:40:40.701037Z` | `18af1ee3572bbec1e5effc4b4bf8171f1c313c3d24c49e4692bdcb2bb1bed3fa` |
| Blender 5.2.0 | `2026-09-28T09:40:40.892391Z`–`09:40:45.087035Z` | `56f24e49c745f1c3c48087a13c1f811c8307a619b22f62a4e1a68ff0cf9cfb1f` |

The manifest SHA-256 is
`8674b9ecb1070260ba5e4fef71e0281e8e0fb1eef09365bf56d8571ec14bc351`.
The new host/worker hashes are respectively
`e5183f6bc218ddf0a1466f6d36b5922b4773c7f94d5ab51cc9a93c507368b568`
and
`54d5805321b57fd263ad35016706611ef627a703c2ebadee9bb32a21f19b8037`.

| Reviewed input | SHA-256 |
| --- | --- |
| Blender 5.0.1 executable | `f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c` |
| Blender 5.2.0 executable | `e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7` |
| SDK `saber/blender/lib/usf/mesh.py` | `4ab671128044524524028dbea32a5c7dcaf5274630348de151592c87b08be337` |
| Historical v2 Blend, contextual accepted-source pin only, **not opened** here | `1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731` |

The host verified the full reviewed 14-file SDK pin set from
`blender_left_push_probe.SDK_PINS`, both executable pins, and its own worker
before and after each run. The disposable test creates no disk source; the
worker's exact source bytes are pinned by its hash above. The installed SDK
and accepted assets were not edited.

Repeat with either pinned Blender executable:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_rgba_cache_lifetime `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

These fresh disposable-mesh runs demonstrate a **reachable SDK mechanism**.
They do not establish that the historical v2/Blender-5.2 first-run
2,650-white-color mismatch took this path: neither receipt opens that Blend,
and the original mismatch receipt contains only packed outputs. The later
call-time wrapper did not reproduce the historical mismatch. A discriminating next
readback should leave `UsfMesh.b_read` unwrapped; only if the target LOD1 row
differs, it should statelessly pack the raw RGBA from `projected.b_mesh` in
triangle-loop order **before** `to_mesh_clear()`. A raw-packed/native match
with stale white projected values would implicate the SDK cache/packing path;
raw-packed white would point to Blender's evaluated color input. Record only
digests, counts and a bounded sample of raw, cached and native values. The
accepted `usf-repair` route and `nativeBlendExportApproved: false` gate remain
unchanged.
