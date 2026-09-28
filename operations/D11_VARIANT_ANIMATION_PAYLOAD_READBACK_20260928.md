# D11 v2/v3 animation readback — 2026-09-28

The pinned, no-save diagnostic extended the base D11 animation readback to
`cat_d11t_v2` and `cat_d11t_v3`. Each variant uses its own accepted repaired
USF, retained **unapproved** native Blend scratch USF, reconstruction-worklist
row and authoring-parity summary. The two historical Blend paths have the same
pinned file content, but each is independently resolved through the accepted
authoring inventory. The variant native roots are named `cat_d11t_v2` and
`cat_d11t_v3`; the accepted repaired roots remain `cat_d11t`.

Blender 5.0.1 and 5.2.0 LTS each returned
`SOURCE_REPAIRED_NATIVE_VARIANT_ANIMATION_READBACK` for both variants. The
full parsed record digest was identical across Blender versions for a given
variant:

| Variant | Repaired USF SHA-256 | Retained native USF SHA-256 | Record digest, both Blender versions |
| --- | --- | --- | --- |
| `cat_d11t_v2` | `096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a` | `0e533bbc80a95798824e69e5c6545cc50b9d98f0ba81e7f0e96d9e3a93c2dc3f` | `95352e70215d263b0461c563f607b69c11fa4079f9da92cc94353da2e6b01bbb` |
| `cat_d11t_v3` | `1346b73da9cf72b6e866a722d929fd5c18305537f9ef3acd369f84ea808993d1` | `bdd562bafeef47644e998cad413e246f10ff0d13bf172cf18d75cdf032e6cc13` | `292c295e5a873b23873f513dedc4d521269becc5dca81f2d67e47522436915ee` |

Both source Blends contain the same two wiper actions, six Euler-rotation
tracks and 18 sparse keyframe points targeting
`pose.bones["BoneAnim_WiperFront"].rotation_euler`. Each repaired USF has one
animated node at
`|@root|D11T_Rig.005|BoneChassis_cdt|BoneAnim_WiperFront` and 36 decoded
float32 samples in each translation, rotation and scale spline. Source actions
were assigned and evaluated **in memory** at 36 inclusive frames, converted
using the SDK's animation basis and parent-local conventions, and aligned with
the repaired clips by name and frame order. For each variant and Blender
version, maximum translation and scale component errors were zero; maximum
sign-invariant quaternion rotation error was
`4.2146848510894035e-8` radians, below the `1e-5` diagnostic tolerance.

Both native variant USFs carry the same two root clip metadata entries as
their repaired counterparts: `d11_wipers_backward` at frames 1–18 and
`d11_wipers_forward` at frames 19–36. **Neither native variant USF contains an
animated node or wiper transform spline.** Clip metadata matching therefore
does not establish animation-track preservation. The diagnostic does not
assert equivalent runtime playback from these files.

The source Blend SHA-256 is
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`.
The accepted authoring inventory SHA-256 is
`03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d`,
and the reconstruction worklist SHA-256 is
`a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`.
The variant authoring-parity summary SHA-256 values are respectively
`ffcc6bb774911f0f1e7a1d865cb2b113f88305a07a2e4aef2f4e5aff07814dc0`
and `c7d28c2f630eadd51cb042150c3162c4f5da811d02e59897e9c0314d6ae058a0`.
The Blender executable SHA-256 values are
`f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c`
(5.0.1) and
`e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`
(5.2.0). All 14 reviewed SDK file pins, source assets, USFs, source modules
and receipts were checked before and after. Every final run reported
`sourceUnchanged`, `sdkUnchanged` and `nativeExportUnchanged` as true.

The new variant host SHA-256 is
`d5a9a3cf75bac45f1a92d818614f4b83b3bf2e9e06ad9377ff6e111582832ae9`;
its worker SHA-256 is
`b830e8089c748d6724eddf107e3c2feb276e76457f625d36169320aee62cd1ec`.
The base animation host and worker used for the source evaluator are pinned to
`729c5a9ca1056b58044dd7497cc2b48d30bda0a37af6ed7127be56360725d997`
and `d464ccf0656ed848bb49df1640fa54d31644c0bccf1f2f11ad17caff536769ab`.
Three synthetic variant-gate tests passed.

To repeat a readback, set `$asset` to `cat_d11t_v2` or `cat_d11t_v3` and
`$version` to `5.0` or `5.2`:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$asset = 'cat_d11t_v2'
$version = '5.2'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_animation_variants `
  --asset $asset `
  --registry "$tc\project.json" `
  --blender "C:\Program Files\Blender Foundation\Blender $version\blender.exe" `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

This is a parsed-value and source-frame comparison, not a hash of serialized
USF animation bytes. The current SDK's exporter uses an end-exclusive bake
range; this diagnostic intentionally samples inclusive action ranges to align
with each retained 18-frame clip. It does not establish that a fresh native
export would retain all 36 repaired samples, explain the native track
omission, prove engine playback, compile a package, or show in-game appearance.
No scratch repair/export, Blend save, Painter or native editor ran.
`nativeBlendExportApproved` remains `false` for both variants; the accepted
`usf-repair` route remains in place.
