# D11 v2/v3 source material payload readback — 2026-09-28

The pinned, **no-save** variant diagnostic opened each variant's own accepted
Blend path and compared its SDK-projected material payload with that variant's
own retained scratch native USF and accepted repaired USF. It ran four
independent readbacks: `cat_d11t_v2` and `cat_d11t_v3` under Blender 5.0.1 and
5.2.0. Every run parsed its own variant worklist row, parity summary, and two
USFs; it did not infer material equality merely from the identical source
Blend hashes or reuse a base-asset readback result. It called
`UsfMesh.b_read(obj)` and `BlenderToUsfSimpleMaterial.build_string()` only in
memory. It did not call a USF writer or export, Blender save, Painter, or a
game editor. It emits bounded JSON on stdout and accepts no output path.

| Asset | 5.0.1 and 5.2.0 complete rows digest | Source/native exact material rows | Source/repaired exact material rows |
| --- | --- | ---: | ---: |
| `cat_d11t_v2` | `9870f3ac9cd785a0fc3857d640960aba4a27b8156d2b139dc43df6d1534a0ec0` | 126/126 | 0/126 |
| `cat_d11t_v3` | `43f03149db24f7f3dfe5a309d5991c591e61596f7793a779ae1b760e4b56ba2f` | 126/126 | 0/126 |

Every result was `SOURCE_NATIVE_VARIANT_MATERIAL_PAYLOAD_READBACK`. Within
each variant, all 126 mapped paths agreed source-to-native on ordered
material struct metadata and full SDK-generated text, ordered material
labels, nonempty texture-name references, and per-face material-slot indices.
Source and native each contained 711 material-slot occurrences; repaired USF
contained 846. The repaired asset had 135 material-label occurrences absent
from the source, matching the prior source inventory. Source-to-repaired
per-face material-index summaries agreed on 0/126 mapped paths, a result
derived directly by the host from each run's emitted rows. Known geometry
changes also affect this index comparison, so it is not attributed solely to
material changes.

The worklist records a meaningful root-name difference. Each retained native
USF root is its variant name (`cat_d11t_v2` or `cat_d11t_v3`), while each
accepted repaired USF root is `cat_d11t`. The diagnostic requires those
exact names and normalizes corresponding mesh paths to `|@root` only for this
readback. The first v2 attempt failed closed on the repaired root before it
loaded a Blend; the checker was corrected to the worklist's pinned root names
and all four subsequent runs passed. No USF bytes changed.

The per-slot SHA-256 covers each full decoded SDK material text string, and
the ordered slot digest includes struct version and vertex-color usage.
The full text includes the SDK's generated material names, layer texture
names, albedo tints, UV-set name, type, and its other shader template fields.
This is semantic material-text parity with the retained native exports, not a
hash of literal serialized USF bytes. The SDK conversion reads image-node
names and Principled BSDF Base Color; it does not prove that Blender node
links, image pixels, packed textures, external paths, Painter assets, or a
native renderer produce equivalent appearances. It does not reconcile the
accepted repaired material definitions.

The accepted authoring inventory SHA-256 was
`03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d`
and the reconstruction worklist SHA-256 was
`a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`.
Each accepted variant Blend has SHA-256
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`;
its **own path** was verified and opened in each run. Variant-specific pins:

| Asset | Accepted asset digest | Repaired USF SHA-256 | Retained native USF SHA-256 | Parity summary SHA-256 |
| --- | --- | --- | --- | --- |
| `cat_d11t_v2` | `6f6d47667c5dd24aa18fa1734aa2cbc7c6af48ac28bc57c67e8609f899f22d6f` | `096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a` | `0e533bbc80a95798824e69e5c6545cc50b9d98f0ba81e7f0e96d9e3a93c2dc3f` | `ffcc6bb774911f0f1e7a1d865cb2b113f88305a07a2e4aef2f4e5aff07814dc0` |
| `cat_d11t_v3` | `7c3588072e21e5aa8944d136491ebc26e9dace14ab47929bd8672a75ffbac0e7` | `1346b73da9cf72b6e866a722d929fd5c18305537f9ef3acd369f84ea808993d1` | `bdd562bafeef47644e998cad413e246f10ff0d13bf172cf18d75cdf032e6cc13` | `c7d28c2f630eadd51cb042150c3162c4f5da811d02e59897e9c0314d6ae058a0` |

Blender 5.0.1 and 5.2.0 executable hashes were respectively
`f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c`
and `e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`.
The SDK's 14 reviewed file pins and mapped-path worker pin were rechecked.
The variant material host SHA-256 is
`6006e819ae9913ca5bae8bab5f4a09a1bc1bfaa12023f372a1ebf361cfc50f63`;
its worker SHA-256 is
`74fe12860d15bf7d6237b40945aec79decff23a865031121707863f68545d2a0`.
Four focused synthetic tests passed, including wrong-variant identity,
incomplete rows, a native material mutation with an identical Blend pin, and
a forged material slot digest. Every real run reported source, SDK, native USF
and repaired USF unchanged after readback.

To repeat with either reviewed Blender executable, choose `--asset
cat_d11t_v2` or `--asset cat_d11t_v3`:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_material_variant_payload `
  --asset cat_d11t_v2 `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

This closes the source-to-retained-native material-text question for the 126
mapped meshes in each variant. It does not assess the other 84 source meshes,
texture bytes, shader-graph behavior, repaired-USF parity, hierarchy,
animation, inverse binds, compilation, or native viewing. The accepted
`usf-repair` build route and `nativeBlendExportApproved=false` remain in place.
