# D11 Blender authoring parity diagnostic — 2026-09-28

The three historical `.blend` references are byte-identical (SHA-256
`1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`).
They do **not** reproduce any of the three pinned repaired build USFs when
exported with the bundled Saber SDK in Blender 5.2. The declared `usf-repair`
route remains authoritative. No scratch export was adopted as build source,
and `require_export_allowed(..., "native-blend", parity_receipt=diagnostic)`
returned `BLOCKED` for each asset. The accepted source files and SDK scripts
were rehashed after each run and were unchanged.

| Asset | Repaired USF SHA-256 | Scratch native USF SHA-256 | Root names, repaired/native | Gate |
| --- | --- | --- | --- | --- |
| `cat_d11t` | `49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170` | `80c856b07b3ae1447f2748b5f6f8ec13c688c2594f3ebfaeada9e0d11da21370` | `cat_d11t` / `cat_d11t` | blocked |
| `cat_d11t_v2` | `096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a` | `0e533bbc80a95798824e69e5c6545cc50b9d98f0ba81e7f0e96d9e3a93c2dc3f` | `cat_d11t` / `cat_d11t_v2` | blocked |
| `cat_d11t_v3` | `1346b73da9cf72b6e866a722d929fd5c18305537f9ef3acd369f84ea808993d1` | `bdd562bafeef47644e998cad413e246f10ff0d13bf172cf18d75cdf032e6cc13` | `cat_d11t` / `cat_d11t_v3` | blocked |

The three repaired USFs each parse as 654 nodes, 252 mesh nodes, 749,578
faces, 2,133 material slots, 2,241,366 skin entries, and one animated node.
The scratch native exports each parse as 597 nodes, 210 mesh nodes, 438,087
faces, 795 material slots, 1,306,017 skin entries, and zero animated nodes.
The base native export is 113,076,211 bytes versus 192,935,318 bytes for its
repaired USF; the v2/v3 native exports are 113,076,217 bytes versus
192,935,831 bytes for their repaired USFs. Blender also logged nine
`calc_tangents failed and skipped` warnings per export.

Three exploratory base exports had the same 113,076,211-byte length and the
same bounded parsed structural digest, but different whole-file SHA-256 values.
The final retained candidate is the one pinned in the table; the earlier two
remain in ignored `local/` scratch. Pairwise byte comparison found roughly
14,500–16,000 differing bytes across seven 1 MiB blocks, beginning near
offset 4,101,763. The cause is not isolated, so matching counts or bounded
structural digests must not be treated as full equivalence.

For a path-aware comparison, the diagnostic aligns only the root component
as `|@root`; the actual root names above are recorded separately. Under that
normalization each comparison has 133 repaired-only paths, 76 native-only
paths, and 132 matched paths with changed indexed fields. These counts refer
to full hierarchy paths: reparenting or renaming can yield one missing and
one extra path without proving a physical object was deleted and recreated.
The full machine-readable diff records each path and per-node mesh material,
skin, transform, and animation fields. The repaired blade-roll branch
(`BoneBladeRoll_cdt`) and access-ladder hierarchy are absent at their accepted
paths. At `Body_vis`, the repaired USF has 141,912 faces and 92 material slots;
the native export has 164,391 faces and 89 slots and lacks the three
`mod_cat_d11t_painter_0{1,2,3}_l0` material labels. This is a reconstruction
target, not an automatically approved equivalence mapping.

Each compact summary is under `operations/d11_{base,v2,v3}_blend_authoring_parity_summary.json`.
Its `archiveSha256` pins a deterministic `.json.gz` sibling holding every
node-field difference; `fullRawSha256` pins the decompressed JSON retained
under ignored `local/` scratch. Each summary also pins the retained scratch
candidate USF and includes `nativeBlendExportApproved: false` and the actual
source export-gate rejection. The exact failed first helper import attempt
(`ModuleNotFoundError: blender_parity_diff`) is retained only in
`local/blend-authoring-parity-base/failed_receipt.json`; it is superseded by
the successful Blender export receipts above.

To reproduce one asset from the maintained toolchain, choose **new, empty**
scratch and receipt paths, and substitute `cat_d11t_v2` or `cat_d11t_v3` for
the other variants. Omit `--run` first for a pinned dry run. A successful
diagnostic can exit zero while reporting `PARITY_DIFFERENT`; the JSON status
and `exportGate.status` determine the result.

The runner calls
`require_export_allowed(sourceRoot, inventory, asset, "native-blend", parity_receipt=result)`
before sealing each receipt. A separate direct call using each compact summary
as `parity_receipt` also returned `BLOCKED` for base, v2 and v3.

```powershell
$tc = 'C:\RC\RoadCraftDev\toolchain'
$env:PYTHONPATH = "$tc\src"
& "$tc\.venv\Scripts\python.exe" -m roadcraft.blender_authoring `
  --asset cat_d11t `
  --inventory "$tc\operations\d11_authoring_inventory.json" `
  --inventory-sha256 03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d `
  --blender 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --blender-sha256 e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7 `
  --sdk-script-root 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script' `
  --scratch-root "$tc\local\new-blend-authoring-probe" `
  --receipt "$tc\operations\new-blend-authoring-probe.json" --run
```

The focused diagnostic/linkage tests run with
`python -m unittest discover -s tests -p test_blender_authoring.py -v`.
The full source suite passed 133 tests with 3 skips after these changes.
An actual summary/archive/raw/candidate rehash check also passed for all
three results.

The bundled USF importer can create Blender mesh objects and carry normals,
UVs and colors, but its `UsfNode._self_load` does not reconstruct an armature,
skin weights, inverse-bind matrices or animation, and `UsfMesh._load_materials`
creates placeholder material names. Saving/reopening such an imported scene
would therefore lose essential authoring information. No scratch `.blend`
was created or promoted. The shortest path to native authoring parity is to
reconcile the existing `.blend` against the path/material/rig diff, establish
missing animation and skin/bind data, then rerun SDK export, compilation and
native-view comparison. Only an asset-specific reviewer-supported receipt
covering every `source.py` check can open the native export gate.
