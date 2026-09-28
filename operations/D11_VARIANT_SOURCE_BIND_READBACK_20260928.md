# D11 v2/v3 source skin identity and inverse-bind readback — 2026-09-28

The no-save variant diagnostic opened the accepted `cat_d11t_v2.blend` and
`cat_d11t_v3.blend` **at their own declared source paths** under each pinned
Blender version. The two Blends are byte-identical to the base historical
Blend, but each run separately verified its variant inventory entry, asset
digest, repaired `export.usf`, retained scratch native USF, parity summary and
blocked export gate. The reviewed Saber SDK's `UsfMeshSkin.b_read(obj)`
provided the ordered source bone IDs; the worker reconstructed the SDK's
later UID/inverse-bind resolution in memory and compared it with each
variant's own parsed USFs. It normalizes only the USF tree's root path to
`|@root` for the 126 mapped mesh paths. The actual native roots are
`cat_d11t_v2` and `cat_d11t_v3`; both repaired roots are `cat_d11t`.

Four separate runs completed: v2 and v3 under Blender 5.0.1, then each under
5.2.0 LTS. All returned `SOURCE_VARIANT_USF_BIND_IDENTITY_READBACK` with
126/126 mapped rows and the same complete row digest
`d4b4fc4230deb8be935ba8c08ffb048382ec3a836dee1310f5c4c49fc49a620e`.
The digest agrees with the independently opened base Blend readback because
the three source Blend files have identical bytes and the compared bind rows
in these retained USFs have the same identities and matrix measurements.

| Measurement | v2, both versions | v3, both versions |
| --- | ---: | ---: |
| Source → own retained native ordered bone identity match | 126/126 | 126/126 |
| Source → own retained native inverse matrices within `1e-5` | 126/126 | 126/126 |
| Maximum source/native inverse element error | `0` | `0` |
| Own retained native inverse versus referenced node's inverse world matrix, maximum error | `0` | `0` |
| Source → own repaired ordered bone identity match | 0/126 | 0/126 |
| Source → own repaired shared inverse matrices within `1e-5` | 3/126 | 3/126 |
| Own repaired inverse versus referenced node's inverse world matrix, maximum error | `1.0105905532836914` | `1.0105905532836914` |

Each source/native row has 384 ordered skin-bone identities. Each variant's
repaired rows break down identically: 66 have 381 bones and 376 source IDs in
common, 54 have 383 bones and 376 in common, three `Body_vis` LOD0–2 rows
have 23 bones and 14 in common, and three `Blade_vis` LOD0–2 rows have five
bones and **zero** in common. The three `Body_vis` rows are the only
source/repaired shared inverse comparisons within tolerance. The three
zero-overlap `Blade_vis` rows are not counted as matrix matches. The maximum
source/repaired shared inverse element error is
`1.0105905532836914`. This is a source-side diagnostic of the current
retained bytes, not a verdict on engine behavior.

The accepted inventory SHA-256 is
`03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d`;
the worklist SHA-256 is
`a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`;
each accepted Blend is
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`.

| Asset | Source asset digest | Repaired USF SHA-256 | Own retained native USF SHA-256 | Parity summary SHA-256 |
| --- | --- | --- | --- | --- |
| `cat_d11t_v2` | `6f6d47667c5dd24aa18fa1734aa2cbc7c6af48ac28bc57c67e8609f899f22d6f` | `096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a` | `0e533bbc80a95798824e69e5c6545cc50b9d98f0ba81e7f0e96d9e3a93c2dc3f` | `ffcc6bb774911f0f1e7a1d865cb2b113f88305a07a2e4aef2f4e5aff07814dc0` |
| `cat_d11t_v3` | `7c3588072e21e5aa8944d136491ebc26e9dace14ab47929bd8672a75ffbac0e7` | `1346b73da9cf72b6e866a722d929fd5c18305537f9ef3acd369f84ea808993d1` | `bdd562bafeef47644e998cad413e246f10ff0d13bf172cf18d75cdf032e6cc13` | `c7d28c2f630eadd51cb042150c3162c4f5da811d02e59897e9c0314d6ae058a0` |

Blender executable pins are
`f81d3bca0af0d917e03fdf09255981b2ed0750d3a2815da991ea5425a87f8f7c`
for 5.0.1 and
`e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`
for 5.2.0. The new host SHA-256 is
`ae9236f29f7899bfcf5955198dcd42b43b5bc9a1893bca7616197a02b5cd2edb`;
the new worker is
`967f08b9c46509b9fc7b3491fa4b5ec69b96267645435bc6637a60199ff38c66`.
The host pins the previously reviewed base bind host, base bind worker,
variant inventory host, mapped-path worker, and all 14 SDK files. Every run
rehashed its variant source, own USFs, summary, worklist, Blender executable,
host/worker dependencies and SDK files afterward. All four reported source,
SDK and retained native USF unchanged; seven focused base/variant boundary
tests passed.

To repeat a run, choose `cat_d11t_v2` or `cat_d11t_v3` and one reviewed
Blender executable. The command emits bounded JSON on stdout and accepts no
save, export or output-file argument:

```powershell
$tc = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\Roadcraft Development Package\RoadCraftToolchain'
$env:PYTHONPATH = "$tc\src"
& 'C:\RC\RoadCraftDev\toolchain\.venv\Scripts\python.exe' -B -m roadcraft.blender_bind_variant `
  --asset cat_d11t_v2 `
  --registry "$tc\project.json" `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script'
```

The readback covers the 126 exact mapped mesh paths and static frame-1 bind
state only. It does not compare unmapped meshes, numeric UIDs across separate
USF trees, tangents, material payload, animation, full hierarchy, compiled
package bytes or native game view. It does not execute the Blender exporter,
save a Blend, write a USF, or approve native Blend export. The accepted
`usf-repair` route and `nativeBlendExportApproved: false` gate remain intact.
