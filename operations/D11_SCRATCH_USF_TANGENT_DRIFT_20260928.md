# Scratch Blender USF byte drift, 2026-09-28

This is a read-only comparison of retained, **unapproved** native Blender
exports. It does not change or validate the repaired SDK USFs, historical
`.blend` files, or accepted game package. The native `.blend` export route
remains blocked by the structural differences in the authoring parity receipts.

## Comparable retained probes

The base and v2 probes each exported the same pinned historical `.blend`
(SHA-256 `1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731`)
twice with the same Blender executable
(`e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7`)
and identical bundled SDK file hashes. The probe helper changed from
`a091317a5edb4361a222b3e608050fa6129559f48291f4dfe6e4cccf4f25929e`
to `cf5469b31b33d2f33bfdd66d77c6498b6f7cde0e1653c2698ad567ff64e59642`
between each pair while node-path comparison was corrected. Thus these are
comparable retained outputs, **not** a controlled same-helper reproducibility
test. No fresh Blender run was made for this analysis.

| Asset | Earlier scratch USF SHA-256 | Later scratch USF SHA-256 | Size in both | Structural digest in both |
| --- | --- | --- | ---: | --- |
| `cat_d11t` | `189ea7b48b9bdfee9c20909f9c8297b3aec27131fe631c29f29bd23a145e9682` | `80c856b07b3ae1447f2748b5f6f8ec13c688c2594f3ebfaeada9e0d11da21370` | 113,076,211 | `2ed8d46516260907fd249fa44cd98eba4ab0fd675cd90494d496f1a21803da4c` |
| `cat_d11t_v2` | `3cff224fbbcfc3fe49cf7f5ce40de7647e988220c1f1f8478950b4d4aa673dae` | `0e533bbc80a95798824e69e5c6545cc50b9d98f0ba81e7f0e96d9e3a93c2dc3f` | 113,076,217 | `2e7d058fd9fb0d6d74cc22aa5311d21f19c17543679e8ef33a0eed3f8b89f944` |

## Byte-level location

The bundled SDK `saber/blender/lib/usf/mesh.py` (SHA-256
`4ab671128044524524028dbea32a5c7dcaf5274630348de151592c87b08be337`)
writes mesh vertices, normals, color sets, UV coordinates, and tangent arrays
in that order. Its `UsfMesh.b_read` calls Blender's `Mesh.calc_tangents` and
copies each loop's tangent vector and bitangent sign into the USF tangent
array. The comparison located all 210 `UsfMesh` records in each output by
their `0x107` version marker and checked the array lengths and boundaries
against this layout. Every differing byte falls within tangent float32 arrays
of the same three meshes; all other bytes match within each pair.

| Asset | Differing bytes | Differing tangent floats | Changed meshes and differing bytes | Largest absolute float difference |
| --- | ---: | ---: | --- | ---: |
| `cat_d11t` | 15,967 | 15,195 | `Blade_vis` 5,938; `Ripper_vis` 4,995; `Ripper_vis_LOD1` 5,034 | `1.7881393432617188e-7` |
| `cat_d11t_v2` | 13,428 | 12,911 | `Blade_vis` 4,758; `Ripper_vis` 4,723; `Ripper_vis_LOD1` 3,947 | `1.7881393432617188e-7` |

Only tangent components x, y, and z differ; the fourth sign component is
byte-identical. In the base pair, 13,723 of 15,195 differing floats vary by
one or two float32 ULPs; in v2, 11,822 of 12,911 do. Larger ULP distances
occur near zero, while the maximum absolute difference stays below `1.8e-7`.
The byte-level delta therefore explains the unequal SHA-256 hashes without
implying a different node count or mesh topology. The source of the float
variation inside Blender's tangent calculation is **not proven** by these
retained artifacts.

## Same-helper cross-variant check and likely mechanism

A further read-only comparison used the final base, v2, and v3 scratch exports.
All three receipts pin the same Blender 5.2.0 executable, SDK scripts, helper
SHA-256 `cf5469b31b33d2f33bfdd66d77c6498b6f7cde0e1653c2698ad567ff64e59642`,
and byte-identical `.blend` content. The configured `src_filename` and output
root names differ, so this is still **not** a controlled same-command test.
All 210 mesh records in each file have matching array layouts. Across every
pair, vertex, normal, color, and UV arrays match exactly. Only the tangent
arrays of mesh ordinals 102, 147, and 148 differ:

| Compared retained outputs | Differing tangent bytes | Differing float32 values | Maximum absolute difference |
| --- | ---: | ---: | ---: |
| Base / v2 | 16,009 | 15,126 | `1.7881393432617188e-7` |
| Base / v3 | 13,807 | 12,982 | `1.7881393432617188e-7` |
| v2 / v3 | 11,185 | 10,649 | `1.7881393432617188e-7` |

Those ordinals serialize 13,140, 31,962, and 19,746 triangles. The bundled
SDK takes the tangent vectors directly from Blender's `Mesh.calc_tangents`;
its source has not changed. The installed Blender 5.2.0 includes `tbb12.dll`.
[Blender 5.2.0's MikkTSpace source](https://raw.githubusercontent.com/blender/blender/v5.2.0/intern/mikktspace/mikktspace.hh)
selects a parallel path when TBB concurrency exceeds one and a mesh has more
than 10,000 faces; that path sums float tangent contributions into shared
groups with atomic additions. Thread scheduling can change floating-point
addition order and thus low tangent bits. This is a strong explanation for the
observed tiny differences, but it is an **inference**, not a proven runtime
root cause. Four other exported meshes also exceed 10,000 triangles and did
not drift in these retained comparisons. The USF records the *triangulated*
count; these receipts do not record Blender's face count before triangulation,
so they cannot alone prove which meshes crossed MikkTSpace's 10,000-face
parallel threshold.

A bounded confirmation would repeat the exact same pinned `.blend`, helper,
config, and Blender executable into separate disposable directories, first
with its current thread setting and then with Blender's documented
`--threads 1` option (the scratch authoring probe now exposes this as
`--blender-threads 1` and seals the chosen count into its receipts). It must
rehash inputs, compare the entire USF and mesh
arrays, and keep the native-blend export gate blocked regardless of the
determinism result. No new Blender asset run or scratch export was made for this
investigation because the `game-dev` CLI was unavailable. A pinned
`cat_d11t` probe dry run with `--blender-threads 1` returned `DRY_RUN`,
revalidated the `.blend`, repaired USF, Blender executable, and SDK hashes,
and created no scratch or receipt files.

The full scratch USFs and raw probe receipts remain under ignored
`RoadCraftToolchain/local/blend-authoring-parity-*`. The checked-in compact
parity summaries retain the source, SDK, candidate hashes and structural
digests. A future controlled experiment would hold the exact helper binary
constant and repeat in fresh disposable scratch, then trace
`Mesh.calc_tangents`; it should not be used to relax the native-export parity
gate or normalize the authoritative asset.
