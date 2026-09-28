# D11 blade-collision payload readback — 2026-09-28

Two separate, pinned, no-save Blender processes compared the 60 relocated
`cdt_blade_0`–`cdt_blade_59` meshes. Blender 5.0.1 and 5.2.0 LTS returned the
same complete 60-row digest, `9bb95eb979bbe4c5baeaea90cd57d8f08ef515af8023c9eae38c2d8131b479d4`.
The source Blend's in-memory SDK projection matched the retained native USF
on every compared field and row. The repaired USF differs in ordered positions
on 58 meshes and normals on all 60, despite the previously measured 60/60
world-matrix and mesh-count matches.

| Ordered payload field | Source/native | Native/repaired |
| --- | ---: | ---: |
| Positions | 60/60 | 2/60 |
| Normals | 60/60 | 0/60 |
| Face material and edge indices | 60/60 | 60/60 |
| UV layer names and coordinates | 60/60 | 60/60 |
| Packed colors | 60/60 | 60/60 |
| Skin indices and weights | 60/60 | 60/60 |

Only `cdt_blade_49` and `cdt_blade_50` matched repaired positions. Source/repaired
counts equal native/repaired counts. The SDK color packer was unwrapped, and
its process-local RGBA cache was empty before and after the 60 source meshes
in both runs. Both hosts attested unchanged accepted source, SDK and retained
native USF hashes. Five focused synthetic boundary tests and an independent
prelaunch source review passed.

[The manifest](d11_blade_payload_readback_manifest_20260928.json) pins both
full receipts, Blender binaries, host, worker and source inputs. The normalized
LF receipt hashes are `d00fb4fa0135e5846b5d0274587ecf980b15b8c40f4358d7661c6fa45a975846`
for 5.0.1 and `8a7f20c166f8c510a32ecdb991729fdd614a77c7a7e69b4620d8f3dc477a752f`
for 5.2.0 LTS. Each process reported `blendSaved: false`, `usfExported: false`
and `nativeBlendExportApproved: false`; no Painter, native editor, package or
accepted-asset mutation occurred.

This is ordered in-memory payload evidence at two different hierarchy paths,
not proof of collision or physics behavior. Face and skin indices refer to
different material and bone tables; their matching digests do not establish
material-text, bone-identity or inverse-bind parity. Tangents, animation and
the four native-only `cdt_blade_60`–`63` meshes remain outside this diagnostic.
The repaired geometry/normals need reconciliation before a native-Blend export
can be considered; the accepted `usf-repair` build route and blocked export
gate remain unchanged.
