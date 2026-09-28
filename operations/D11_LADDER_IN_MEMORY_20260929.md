# D11 access-ladder in-memory diagnostic — 2026-09-29

The pinned historical base Blend has one `BoneAccess_Ladder` bone directly
under `BoneChassis_cdt`. It has no constraints, connected parent, child bones,
bone-parented scene objects or ladder-named action. The accepted repaired USF
instead has a meshless, unanimated chain:
`BoneAccess_LadderMount` → `BoneAccess_Swivel` →
`BoneAccess_LadderHinge` → `BoneAccess_Ladder`. A pinned read-only shape probe
checked those exact nodes before any edit.

A disposable no-save Blender experiment first created the three intermediate bones
in order, then reparented and retargeted the existing ladder bone. Each rest
matrix was solved from the newly realized parent pose and the repaired USF
world target. The new edit bones use an arbitrary 0.25-unit length because
USF does not encode Blender edit-bone length.

Blender 5.0.1 and 5.2.0 independently returned the same standalone result:

| Static measure | Before | After |
| --- | ---: | ---: |
| Source pose bones | 384 | 387 |
| Shared repaired structural paths | 378 | 382 |
| Source-only / repaired-only paths | 6 / 22 | 5 / 18 |
| Shared paths beyond `1e-5` matrix tolerance | 0 | 0 |
| Maximum shared matrix element error | 0 | `3.3527612686157227e-7` |

All four ladder target paths matched within `3.3527612686157227e-7`. A second
no-save experiment ran the maintained push and blade-roll workers before the
same ladder edit. Both Blender versions then returned **392/400 shared
structural paths**, zero source-only paths, eight repaired-only paths and zero
shared paths outside `1e-5`. The maximum shared matrix error, including the
earlier push branches, was `2.2687017917633057e-6`. The eight missing paths
are two inner lights, five dash controls and `sfx`.

The result is now reproducible with the maintained, source-pinned diagnostic:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_ladder `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

The host pins the accepted inventory, both inputs, Blender executable and
version, SDK scripts, worker and comparison dependencies; it rechecks them
after the run. The worker opens the pinned Blend in background Blender, checks
the repaired ladder shape and source baseline, makes only in-memory edits,
and reports exact residual paths and matrix errors. Blender 5.0.1 and 5.2.0
both returned `IN_MEMORY_LADDER_MATCH` in the standalone mode. The maintained
worker SHA-256 is
`526768b392678b705c0d82687cbb76bd0bad1f1a41a9ad29ee0163cdb50ddf54`.
Focused validation tests reject missing target paths, high matrix error,
saved-Blend claims and a combined result interpreted as standalone.

The ignored original local probes are pinned by these SHA-256 values:

| Probe | SHA-256 |
| --- | --- |
| `local/ladder_shape_probe_20260929.py` | `85d49e358a15ed9a867b9e97479f37d81e3fc7db84ee0bfe03d92b3d4e6ad3e2` |
| `local/ladder_reconstruct_probe_20260929.py` | `acf87435ff0dfda6bc7a534ff7f82d4d27ade6136deb21c4b0b14d57a5bbc57f` |
| `local/push_roll_ladder_probe_20260929.py` | `a5dad7e10c724ac9607c85326cf144fd95b78afd5f9ff9511f302d99efa831bc` |

The source Blend remained SHA-256
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`;
the repaired USF remained
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`.
No Blend was saved and no USF was exported. This is static hierarchy/transform
evidence only: it does not prove SDK export, skin/bind data, animation,
collision, compilation or native appearance. The ladder edit is a maintained
no-save diagnostic, not yet an opt-in scratch export repair. The accepted repaired USF
remains authoritative and the `native-blend` gate stays blocked.
