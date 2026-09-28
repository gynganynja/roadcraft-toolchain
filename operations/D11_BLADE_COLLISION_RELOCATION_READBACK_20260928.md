# D11 base blade-collision relocation readback — 2026-09-28

The pinned, no-save Blender diagnostic inspected all 60 `cdt_blade_0`–
`cdt_blade_59` mesh leaves that the reconstruction worklist pairs by unique
name under **different** hierarchy paths. The historical Blend has each mesh
parented to `D11T_Rig.005` bone `BoneBlade_cdt`. Its SDK-derived source path
matches the retained native scratch USF path. The repaired USF path inserts
`BoneBladeRoll_cdt` before `BoneBlade_cdt`. `equivalenceVerified` remains
`false` on every row: a matching leaf name, world transform or mesh count does
not prove that the relocated nodes or their payloads are equivalent.

Blender 5.0.1 and 5.2.0 independently returned
`SOURCE_BLADE_RELOCATION_INVENTORY` and the identical complete 60-row digest
`28312d0a77022f1bfd3b77e6c5d6ee9cb9ccdb18f1f22e030be12701e0102ead`.
The readback checked the source armature's direct scene-root membership and
visibility before predicting each SDK path. All source objects were visible
meshes in the current scene at frame 1. The readback compared their
SDK-converted **world** matrices with each pinned USF node's world matrix; it
compared **local** matrices only between the two USFs, not directly against
Blender's bone-parented `obj.matrix_local`.

| Static observation | Rows in both Blender versions |
| --- | ---: |
| Source, native scratch USF and repaired USF world matrices agree within `1e-5` elementwise | 60/60 |
| Native and repaired USF local matrices differ by more than `1e-5` | 60/60 |
| Largest native/repaired local-matrix element difference | `0.8908867835998535` |
| Native/repaired USF mesh-count maps agree (vertices, faces, normals, material slots, UV/color sets, skin entries and bones) | 60/60 |
| Evaluated source face count matches the retained native USF face count | 60/60 |
| Raw and evaluated source triangle counts agree | 60/60 |

The changed parent path with preserved world placement and differing USF local
matrices is a concrete hierarchy/transform reconciliation target. It does not
show behavior under blade animation, physics or a native game view. The
diagnostic does not compare vertex positions, normals, collision payloads,
material definitions, weights, inverse binds or animations. It does not
assess the other repaired-only/native-only nodes or the three asset variants.
No fresh SDK export, Blend save, package compilation or game capture ran.
The accepted build input remains the repaired USF, and the `native-blend`
export gate remains blocked.

The source Blend SHA-256 is
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`;
the repaired USF SHA-256 is
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`.
The worklist SHA-256 is
`a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`.
Its base asset pins `d11_base_blend_authoring_parity_summary.json` at SHA-256
`b116ea18837df190eec539b1173deb55926f79ad9b14339f3217c1b86128c87f`;
that summary pins the retained native scratch `candidate.usf` at SHA-256
`80c856b07b3ae1447f2748b5f6f8ec13c688c2594f3ebfaeada9e0d11da21370`.
Both USFs report root `cat_d11t`; the readback uses `|@root` solely as a
common path-index placeholder. It checks the summary and native USF chain
before reading and rechecks their bytes afterward.

The Blender 5.0.1 and 5.2.0 executable hashes are respectively
`f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c`
and `e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`.
The exact worker SHA-256 is
`f8edd2fb82f3264386fd262541e3e686b7389206c71acbb0fcfb5a0d1fd1c6a7`;
`.gitattributes` retains its LF bytes in a Windows checkout. The worker
verifies the reviewed SDK file pins from `blender_left_push_probe.py` before
and after readback. Four focused synthetic tests passed; the two real runs
reported source, SDK and retained native USF unchanged.

Run either installed Blender version. The command prints one bounded JSON
object and accepts no save, export or output-file argument:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_blade_relocation `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

Repeat with `Blender 5.2\blender.exe` to verify the second reviewed runtime.
