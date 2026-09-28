# D11 base skin identity and inverse-bind readback — 2026-09-28

The new pinned, no-save diagnostic compared all 126 exact source mesh paths
from the reconstruction worklist with the retained scratch native USF and the
accepted repaired USF. It used the Saber SDK's `UsfMeshSkin.b_read(obj)` to
read the historical Blend's ordered skin-bone source IDs in memory. The SDK
normally resolves those IDs to USF node UIDs and fills inverse binds in its
later `_resolve_skin_uids_and_inv_matrices` pass. This diagnostic reconstructed
that mapping from the Blender armature world matrices and the same SDK basis
conversion, without running the exporter or writing a USF. It parsed the two
retained USFs with the pinned SDK and resolved each stored skin-bone UID to
the parsed node's source ID. Inverse matrices are compared elementwise at
`1e-5` tolerance; identity lists retain their original order.

Blender 5.0.1 and 5.2.0 each returned
`SOURCE_USF_BIND_IDENTITY_READBACK` with the same full rows digest
`d4b4fc4230deb8be935ba8c08ffb048382ec3a836dee1310f5c4c49fc49a620e`.

| Measurement | Both versions |
| --- | ---: |
| Exact mapped source mesh paths | 126/126 |
| Source → retained native ordered bone identity match | 126/126 |
| Source → retained native shared inverse matrices within `1e-5` | 126/126 |
| Maximum source/native inverse element error | `0` |
| Retained native inverse versus its referenced node's inverse world matrix, maximum error | `0` |
| Source → repaired ordered bone identity match | 0/126 |
| Source → repaired shared inverse matrices within `1e-5` | 3/126 |
| Repaired inverse versus its referenced node's inverse world matrix, maximum error | `1.0105905532836914` |

Every mapped source/native row has 384 ordered skin-bone identities. In the
repaired USF, 66 rows have 381 skin bones and 376 source identities in common;
54 rows have 383 bones and 376 in common; three `Body_vis` LOD0–2 rows have
23 bones and 14 in common; three `Blade_vis` LOD0–2 rows have five bones and
zero in common. The three `Body_vis` rows are the only source/repaired rows
whose **shared** inverse matrices fit the tolerance. The three `Blade_vis`
rows have no common identities and are explicitly *not* counted as a matrix
match. Every repaired row has a changed ordered identity list. The maximum
source/repaired shared inverse element error is
`1.0105905532836914`.

The repair-side inverse/self comparison checks the stored inverse bind
against the inverse of the *current parsed node world matrix* at its referenced
UID. Its maximum error shows that the current repaired records differ under
this SDK-defined relationship; it does not by itself establish a gameplay or
rendering defect. The diagnostic reports path-level counts and the exact
missing/extra source IDs for each mapped mesh in bounded JSON, with no output
file argument. It never calls `usf_save`, `UsfMesh.write`, `export_to_usf`, or
Blender save, and never touches Painter.

Input pins: historical Blend SHA-256
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`;
repaired USF
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`;
retained native USF
`80c856b07b3ae1447f2748b5f6f8ec13c688c2594f3ebfaeada9e0d11da21370`;
worklist
`a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`;
accepted inventory
`03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d`.
The Blender 5.0.1 and 5.2.0 executables are respectively pinned to
`f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c`
and `e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`.
The host reuses the reviewed 14 SDK file pins and mapped-path worker pin.
Its new Blender worker SHA-256 is
`b8444c389bfbae5efd0c74ca68623e96db82c144511c65a9584fbe1169f31181`.
The host SHA-256 at this review is
`58e2491b5a00b0537cdb658a2b7e455b954cadda5f688b87796fe40f1949bb78`.
Both runs rehashed all source, SDK, worker, Blender, worklist, summary and USF
inputs afterward and reported source, SDK and retained native export unchanged.
Four focused boundary tests passed.

To repeat with either reviewed Blender version (substitute `Blender 5.0` for
`Blender 5.2`), run:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_bind_identity `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

This proves a source/native identity and inverse-bind readback at the 126
mapped paths only. It is not a full native-export rerun and does not establish
matching numeric UIDs across distinct USF trees, material payloads, animation,
unmapped meshes, hierarchy repair, compilation, or native game view. It does
not change the accepted `usf-repair` build route or the blocked
`nativeBlendExportApproved: false` gate.
