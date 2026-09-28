# D11 variant structural targets — 2026-09-29

The three accepted D11 authoring entries each pin the same historical Blend
bytes (SHA-256
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`)
but different repaired USF files. A pinned, read-only SDK parse compared every
meshless structural path beneath `D11T_Rig.005` in those three USFs. It
included each path's stored world matrix, animation presence and sorted child
names. Blender 5.0.1 and 5.2.0 independently returned the same result:

| Asset | Repaired USF SHA-256 | Structural paths | Paths/matrices/flags differing from base |
| --- | --- | ---: | ---: |
| `cat_d11t` | `49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170` | 400 | 0 |
| `cat_d11t_v2` | `096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a` | 400 | 0 |
| `cat_d11t_v3` | `1346b73da9cf72b6e866a722d929fd5c18305537f9ef3acd369f84ea808993d1` | 400 | 0 |

All three maps had the same canonical SHA-256 digest:
`d2694db5513e19b3e6e23527b280f7bb46a4b724c0c3268bf171c95dd92e4369`.
Every one of the 400 base/variant matrix comparisons had zero element error;
there were no base-only or variant-only paths. Input Blend and USF hashes and
reviewed SDK imports were checked before and after each run. The ignored
read-only probe is
`local/variant_structural_target_probe_20260929.py`, SHA-256
`2cafea1b165ca8ffbfbf286a2c15b9389a03c48db16e4fe3a579317f5922a088`.

Run from the RoadCraft development package with either reviewed Blender
version, replacing `5.2` with `5.0` for the second check:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup --disable-autoexec --threads 1 `
  --python-exit-code 1 `
  --python 'RoadCraftToolchain/local/variant_structural_target_probe_20260929.py'
```

The maintained base no-save reconstruction therefore addresses the same
*static structural target* for all three repaired USFs. This comparison did
not run the edits against each variant, save a Blend, export a USF, or compare
variant meshes, materials, binds, animations, collision, compilation or native
appearance. Every asset retains its `usf-repair` build input and separate
`native-blend` parity gate.
