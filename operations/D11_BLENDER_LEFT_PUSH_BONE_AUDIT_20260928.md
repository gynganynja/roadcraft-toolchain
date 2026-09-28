# D11 left push-arm bone audit — 2026-09-28

This was an **in-memory, file-read-only experiment** for `cat_d11t`. It did
not save a Blend, export a USF, or change an accepted asset. The Blender 5.2
process exited after printing its result. The Python probe was passed inline
through `blender.exe -b <pinned Blend> --disable-autoexec --python-expr
<inline probe>`; the temporary expression was not retained as a script.

The historical source Blend is
`D11_Interior_Standalone_20260927/p/mods_source/models/mods/cat_d11t.tpl.asset/cat_d11t.blend`
(SHA-256 `1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`).
Its sibling repaired `export.usf` is SHA-256
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`.
The Blender executable matches the parity diagnostic pin
`e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`.
The SDK's `saber/blender/lib/usf/transform.py` was SHA-256
`c79cd0947590abf36bd23c590e642ee69d2c93fb9d042f944b7a2bdc857d0101`.

The source armature `D11T_Rig.005` lacks `IK_push_arm_left_base`; its
`IK_tilt_left_base` is directly parented to `BoneBladeLift_cdt`, and
`IK_tilt_left_tip` is parented to the base. Neither existing IK bone had a
constraint. The repaired USF instead contains a unique, meshless,
non-animated `IK_push_arm_left_base` node under `BoneBladeLift_cdt`, with the
left tilt base beneath it. This is the smallest useful hierarchy difference
in the reconstruction worklist: one missing intermediate bone moves the
base and tip paths. The source Blend's missing bone explains this particular
native-export path difference; it does not explain the other differences.

The probe parsed the repaired node's full-precision world matrix with the
bundled SDK, inverted the SDK's basis conversion as
`FROM_SABER_CONVERT @ repaired_world @ TO_SABER_CONVERT`, then transformed it
into armature space with `arm.matrix_world.inverted()`. In Blender edit mode
it created the intermediate bone under `BoneBladeLift_cdt`, assigned that
matrix, and reparented the existing tilt base while restoring the tilt base's
edit-bone matrix. The new bone used an arbitrary 0.25-unit length; USF node
matrices do not encode Blender edit-bone length. The process then returned to
object mode and compared pose/world matrices before exiting.

| In-memory check | Result |
| --- | ---: |
| Left tilt base parent chain | `BoneChassis_cdt` → `BoneBladeLift_cdt` → `IK_push_arm_left_base` → `IK_tilt_left_base` |
| New bone world matrix versus repaired USF after SDK conversion, maximum element error | `3.5762786865234375e-7` |
| Existing left tilt base pose matrix, maximum change | `1.0766088962554932e-6` |
| Existing left tilt tip pose matrix, maximum change | `2.2687017917633057e-6` |
| Source Blend and repaired USF hashes after probe | Unchanged; equal to pins above |

This proves only that the **static left-branch path and transforms** can be
reconstructed in a disposable Blender process to floating-point precision.
The arbitrary edit-bone length is an authoring ambiguity, and no scratch USF
was exported or compared. Skin bone UID/order, inverse binds, animation,
other hierarchy branches, mesh and material data, native viewing, and
gameplay parity remain unverified. The `native-blend` export gate stays
`BLOCKED`; the accepted build continues to use `usf-repair`.
