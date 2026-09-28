# D11 v2/v3 source-mesh readback — 2026-09-28

The accepted `cat_d11t_v2.blend` and `cat_d11t_v3.blend` files are separate
declared source paths, but both have the same SHA-256 as the accepted base
`cat_d11t.blend`:
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`.
The no-save variant wrapper verifies each variant's own inventory entry,
asset digest, Blend path, repaired `export.usf`, reconstruction worklist and
blocked native-export gate before and after its run. It invokes the existing
pinned base Blender worker to read the byte-identical source scene, then
reinterprets each of its 126 mapped source-fact rows against that variant's
**own** repaired/native worklist row. It does not merely relabel the base gap
result. The worker opens the base Blend path; no variant Blend is separately
opened, and no USF is exported.

| Asset | Repaired USF SHA-256 | Blender 5.0.1 and 5.2.0 variant rows digest |
| --- | --- | --- |
| `cat_d11t_v2` | `096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a` | `8fdee39be1754f81858ab7c20b32a2d00ff1ebbd31caa9a2eec48018bd2014b9` |
| `cat_d11t_v3` | `1346b73da9cf72b6e866a722d929fd5c18305537f9ef3acd369f84ea808993d1` | `490ea3fb48024a6425f61e4462997f59d0a2f1a916d013d46d485ee7760c049d` |

Four separate wrapper invocations ran Blender 5.0.1 and 5.2.0 once for each
variant. Every result was `SOURCE_GAP_INVENTORY`, with 126 mapped and zero
unmapped changed mesh paths. The base source-facts digest inside every run
was `b0600a3d72179da3d793c834fb4b7f1f9860a3da9352c72048be3604310c1efd`.
The variant worklist's 126 paths exactly matched the base path set and order
after sorting; the SDK direct-parent/flat-LOD mapping was therefore reused
only for those paths and those byte-identical Blend bytes. The v2/v3 native
scratch exports have different actual root names, which the worklist records
separately and normalizes to `|@root` for comparison. The normalized path
match is not exporter or asset equivalence.

In each of the four results, all 126 mapped source objects had their first
armature modifier target `D11T_Rig.005`. All 135 repaired-only material-label
occurrences were absent from evaluated source material slots; the worklist
labels end in `_v2` or `_v3` according to the asset. Source-derived material
slot and skin-bone counts matched the retained native export on all 126 rows.
All 36 recorded count gaps across nine mesh rows also matched the retained
native export. No mapped row changed triangle count between raw and evaluated
mesh. These are read-only source facts and SDK count predictions, not a fresh
variant export. They do not establish geometry payload, material/texture
payload, skin weights, inverse binds, animation, compiler output or native
visual parity.

The accepted inventory SHA-256 is
`03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d`;
the reconstruction worklist SHA-256 is
`a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`.
The v2/v3 inventory asset digests are, respectively,
`6f6d47667c5dd24aa18fa1734aa2cbc7c6af48ac28bc57c67e8609f899f22d6f`
and `7c3588072e21e5aa8944d136491ebc26e9dace14ab47929bd8672a75ffbac0e7`.
The wrapper pins the existing base host at
`32db82dd01e40d5808d830564f999489c0f80fc373c34b8665b88fd462fd68e2`
and inherits its worker pin
`e29122c28bbe60a254a7c239fcc84be7d2f05a57c0ce305132069edd5b264113`.
Blender executable and SDK script pins are the reviewed values in
`blender_armature_parity.py` and `blender_left_push_probe.py`. Source, SDK,
base host and worker hashes were checked after every run. The focused base
and variant test modules passed 10 tests.

Run either variant with either reviewed Blender executable. The result is one
bounded JSON object on stdout; the command accepts no save, export or output
path:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_mesh_variant_inventory `
  --asset cat_d11t_v2 `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.0\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

Use `--asset cat_d11t_v3` for v3 and the reviewed Blender 5.2 executable to
repeat the other runs. The accepted build remains `usf-repair`, and
`nativeBlendExportApproved` remains `false` for both assets. Any actual
authoring repair belongs in a separate disposable copy, followed by a full
asset-specific export/parity review.
