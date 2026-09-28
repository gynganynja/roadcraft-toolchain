# D11 blade-roll hierarchy experiment — 2026-09-29

A disposable, no-save experiment reconstructed the missing `BoneBladeRoll_cdt`
bone between `BoneBladeLift_cdt` and `BoneBlade_cdt` in the accepted base
`cat_d11t.blend`. The source has no blade-bone children or constraints; all 60
`cdt_blade_0`–`59` meshes are bone-parented to `BoneBlade_cdt`. The repaired
USF's roll bone is meshless and has no animation. The experiment solved the
new roll and reparented blade rest matrices against the repaired USF's static
world transforms. Blender's edit operation initially moved the 60 meshes, so
it restored each captured mesh world matrix in the disposable scene.

Blender 5.0.1 and 5.2.0 independently exited 0 with the same result:

| Static measure | Before | After |
| --- | ---: | ---: |
| Source pose bones | 384 | 385 |
| Exact shared structural paths with repaired USF | 378 | 380 |
| Source-only / repaired-only structural paths | 6 / 22 | 5 / 20 |
| Shared paths beyond `1e-5` matrix tolerance | 0 | 0 |
| Maximum shared matrix element error | — | `2.384185791015625e-7` |
| Largest blade mesh world drift before / after restoration | — | `0.8908867835998535` / `0` |
| Maximum restored mesh world / derived local error against repaired USF | — | `0` / `2.384185791015625e-7` |

The two added shared paths are the roll and relocated blade bone. Every one
of the 60 restored meshes matches its repaired USF world transform exactly;
its world transform relative to the relocated blade bone matches the repaired
USF local matrix within the same tolerance. This is **static matrix evidence**,
not proof of exported mesh payload, skin/bind identity, animation, collision,
or native behavior. The new edit bone uses an arbitrary 0.25-unit length
because the USF does not encode Blender edit-bone length.

The ignored, disposable script is
`local/blade_roll_reconstruct_probe_20260929.py`, SHA-256
`7301bf519221195363ac6d0499abd35cdb794f0178941009886d2e8de4c8500f`.
It verifies the pinned source Blend
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`,
repaired USF
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`
and reviewed SDK imports before and after the run. It is currently a local
experiment, not a published or source-pinned toolchain command. A maintained
command still needs portable inventory input, exact worker pinning, bounded
result validation and tests before use in an export wrapper.

The existing normal scratch installer expects the old blade hierarchy. If a
future combined repair inserts the roll first, its path mapping must be
updated and revalidated for all 60 meshes. Neither Blender process saved a
Blend or exported a USF. The accepted repaired USF remains the build input;
the `native-blend` gate remains blocked.
