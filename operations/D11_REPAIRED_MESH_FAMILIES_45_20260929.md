# D11 repaired-only mesh family expansion — 2026-09-29

The Blender 5.2.0 **no-save** check reconstructs 15 repaired-only flat-LOD
families in one disposable scene. It includes the 21 meshes from the earlier
probe, five dashboard gauge families, rear-flex body, and both beacon states.
All **45 meshes, 16,537 faces and 49,611 corners** have target paths,
positions, normals, UVs, face material/edge pairs, complete material text
and metadata, packed colors, and active skin influences matching the
accepted repaired USF through SDK readback. The scene grows from 210 to 255
meshes; source Blend and accepted USF hashes remain unchanged.

The off beacon has three same-name materials whose text differs from the
inner-lens versions. The importer gives these three Blender datablocks
unique `__rc_` aliases in memory. Only within this readback call, an SDK
material subclass emits and verifies the original target name and text.
The SDK class and packed-color mode are restored afterward. This is a
comparison technique, **not** a persisted material repair or a writer patch.

Remaining discrepancies are explicit: the SDK projects 399 rig bones for
each mesh rather than the accepted per-mesh tables (1, 2, 3, 381 or 382);
378 corners have differing full skin records from zero-weight index slots;
21 meshes have a tangent-component error of at least 1. The nonzero skin
influences match. Texture image names match, but image pixels and engine
appearance have not been checked. The two large `D11_InteriorV1_vis` and
`D11_DashV5_vis` families (six meshes) remain outside this combined run.

The maintained probe is
`operations/probes/repaired_mesh_families_45_check_20260929.py`, SHA-256
`2304ba09844a378837e7eacdf86da21ceabd3b7827b9f6cb8dd1f888951fd13e`. It pins inventory, worklist, source Blend, repaired
USF, Blender executable, SDK and importer SHA-256 values. It checks the
four-stage structural reconstruction before the family reconstruction,
exact 45-row coverage, the known gaps, three alias names and restoration of
both scoped SDK changes. The importer SHA-256 is
`7f86dd84a6867f609d6400a7a17d2c534cf9a62f61f6aaad4e9aa162281b4ad1`.

To replay from the Steam development-package root, copy the probe unchanged
to `RoadCraftToolchain/local/repaired_mesh_families_45_check_20260929.py`,
verify its hash, and invoke:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup --disable-autoexec --threads 1 `
  --python-exit-code 1 `
  --python 'RoadCraftToolchain/local/repaired_mesh_families_45_check_20260929.py'
```

The exploratory run and the maintained probe replay both returned
`IN_MEMORY_FAMILY_PAYLOAD_MATCH_WITH_GAPS` with no Blend save or USF export.
Repository CI is a separate check. This result does not establish an exact USF writer, game compiler, native capture,
visual or campaign acceptance. The pending scratch-export invocation remains
unexecuted.
