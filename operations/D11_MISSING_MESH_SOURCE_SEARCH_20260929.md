# D11 repaired-only mesh profile and source search — 2026-09-29

The maintained base reconstruction worklist, pinned SHA-256
`a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3`,
lists 67 repaired-only paths after its same-leaf relocation candidates are
separated. A read-only Blender 5.2 parse of the accepted base repaired USF
classified them as **52 mesh nodes and 15 non-mesh nodes**. The 52 meshes
contain 351,577 faces, 1,213 material-slot occurrences and 1,054,695 skin
entries. Fifty-one have skin entries; only `cdt_blade_roll_pivot` is unskinned.
The 52 repaired-only nodes and 10 native-only mesh paths explain the **net**
252-versus-210 mesh-node count gap in the older scratch export. Counts alone
do not establish object equivalence.

The largest repaired-only object, `D11_DashV5_vis`, has 157,482 faces and
472,446 skin entries at LOD0. Other missing families include dashboard gauges,
the V1 interior, access motor mount, rear-flex body/ripper, beacon and lens
states. The existing push/roll/ladder/seven-bone edits reconstruct structural
paths but do not add these meshes or their payloads. A native authoring route
therefore needs actual geometry, material and skin/bind work in a disposable
source copy, followed by fresh export and parity checks.

Three plausible alternate historical Blends were opened read-only. The
`central_hose_sockets_v2` and `blade_flex_hoses_v1` review files each had 90
scene mesh objects, and the `combined_user_fixes_20260923/export_v1` SDK-import
Blend had 210. None contained any of the 52 repaired-only mesh names, allowing
the base `_vis` object to appear as `_vis_LOD0` in Blender. The three file
SHA-256 values are respectively
`1e897b139bd8b43237db441f4b74aa88c3d4abf4ec1d6ff187ce27e54405362d`,
`948aa4d65026ce5afdef9cdf5493109289a9419e3072a34d2cc78320118fe338`,
and `9b112b53e064224c4a29200110d5d1119f384c25c612d2baf2a6e083ff015fa1`.

The supplied `WholeDrive.csv`, SHA-256
`0af10a3066d01780c5e9d4a0f7146646a3acd1d5701d6fe25767937b2f535fdc`,
listed 639 paths containing `cat_d11t` and ending in `.blend`. A second
read-only Blender 5.2 search read the object-name catalog of **all 639**:
none was missing or unreadable, and none contained any of the 52 target mesh
names (again allowing `_vis_LOD0`). This is a name search over that snapshot,
not proof that differently named equivalent geometry does not exist elsewhere.
No source Blend or USF was saved or exported.

The exact probe sources are versioned under `operations/probes/` and execute
from ignored `local/` copies. Their SHA-256 values are:

| Probe | SHA-256 |
| --- | --- |
| `repaired_only_mesh_profile_20260929.py` | `496f6f151bb1a1c6ffa87a526e1a4cab119f25ae9427c76316da5455aa4f4d22` |
| `alternate_blend_mesh_inventory_20260929.py` | `85015b4dadc6984d8468554aec60e09517225ec977263613ed33a65242763bf7` |
| `drive_blend_name_search_20260929.py` | `f117f362bfabba8bb66c2e22bec47f7655a7a02cf8e11419d1d635de03bfa8f5` |

To rerun from the Steam development-package root, copy one probe to
`RoadCraftToolchain/local/` without changing its name, verify its listed hash,
then invoke Blender 5.2 with
`--background --factory-startup --disable-autoexec --threads 1 --python-exit-code 1 --python`
and the local script path. The first probe also checks the reviewed SDK pins,
accepted inventory and repaired USF; the drive search checks its CSV hash
before and after the catalog scan. These are source-discovery diagnostics, not
native-Blend export approval.
