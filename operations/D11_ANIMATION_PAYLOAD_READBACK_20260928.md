# D11 base animation readback — 2026-09-28

The pinned, no-save diagnostic compared the historical `cat_d11t.blend`,
accepted repaired `export.usf`, and retained **unapproved** native Blend
scratch `candidate.usf`. It read the two USFs through the reviewed Saber SDK,
decoded their node animation splines as little-endian float32 values, and
opened the historical Blend in background Blender with auto-execution disabled.
It did not call a USF writer, save a Blend, open Painter, or run the native
editor. In-memory action assignment and frame evaluation were restored before
Blender exited.

Both pinned Blender 5.0.1 and 5.2.0 LTS returned
`SOURCE_REPAIRED_NATIVE_ANIMATION_READBACK` with identical record digest
`f933ad1e865653a13bcccb9503fbd6c219b6dd289a0f2b6fa2a5c3e5e8bc752c`.
The historical Blend contains two actions, six Euler-rotation tracks and 18
sparse keyframe points, all targeting
`pose.bones["BoneAnim_WiperFront"].rotation_euler`. The accepted repaired USF
has one animated node at
`|@root|D11T_Rig.005|BoneChassis_cdt|BoneAnim_WiperFront`, with 36 samples in
each translation, rotation and scale spline. The retained native scratch USF
has **zero** animated nodes and no transform splines. Its two root clip names
and metadata nevertheless match the repaired USF, so clip metadata alone is
not proof that the wiper animation survived native export.

| Clip | Blend action frame range | Repaired/native USF clip window | Source tracks | Sparse keyframe points | Evaluated frames compared |
| --- | --- | --- | ---: | ---: | ---: |
| `d11_wipers_backward` | 20–37 | 1–18 | 3 | 9 | 18 |
| `d11_wipers_forward` | 1–18 | 19–36 | 3 | 9 | 18 |

The diagnostic assigned each action to the source armature **in memory** and
evaluated its wiper bone over the inclusive action range. It applied the SDK's
animation basis conversion, parent-local transform and inverse-rotation
convention, rounded each component to float32, then aligned each action with
the repaired clip of the same name by sample order. Across all 36 aligned
frames, maximum translation and scale component errors were exactly zero; the
maximum sign-invariant quaternion rotation error was
`4.2146848510894035e-8` radians. Both versions passed the `1e-5` translation,
scale and rotation tolerance. The tiny angular value is the normalized-dot/
`acos` measurement error at float precision, not evidence of a visible
rotation difference.

The accepted repaired USF SHA-256 is
`49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170`;
the retained native scratch USF SHA-256 is
`80c856b07b3ae1447f2748b5f6f8ec13c688c2594f3ebfaeada9e0d11da21370`.
The source Blend SHA-256 is
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`,
the reconstruction worklist SHA-256 is
`a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`,
and the accepted inventory SHA-256 is
`03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d`.
The reviewed Blender executables have SHA-256 values
`f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c`
(5.0.1) and
`e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`
(5.2.0). The 14 reviewed SDK files were checked before and after each run.
The host and worker SHA-256 values are respectively
`729c5a9ca1056b58044dd7497cc2b48d30bda0a37af6ed7127be56360725d997`
and `d464ccf0656ed848bb49df1640fa54d31644c0bccf1f2f11ad17caff536769ab`.
Both runs reported `sourceUnchanged`, `sdkUnchanged`, and
`nativeExportUnchanged` as true. Four synthetic fail-closed tests passed.

To repeat with either pinned Blender version, set `$version` to `5.0` or
`5.2` and run:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$version = '5.2'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_animation_payload `
  --registry "$tc\project.json" `
  --blender "C:\Program Files\Blender Foundation\Blender $version\blender.exe" `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

This is a comparison of parsed values and source evaluation, not a hash of
serialized USF animation bytes. The current SDK exporter bakes action frames
with an end-exclusive Python range; this diagnostic deliberately samples the
inclusive action ranges to align with the retained 18-frame clips. It does not
prove that a new native export would retain the 36 repaired samples. It does
not compare animation interpolation at arbitrary subframes, engine playback,
the cause of the native spline omission, compilation, or in-game appearance.
The accepted `usf-repair` route remains in place and
`nativeBlendExportApproved` remains `false`.
