# Install and override manifest

What each member of a mod pak does once installed: whether it adds a resource, shadows or repeats a
retail one, or collides with another mod, and whether the engine probably honours it. Scope: retail
game and installed/shared mods as of 2026-10-13. Evidence grades are defined in
[README.md](README.md#evidence-grades); deterministic builds are in
[deterministic-paks.md](deterministic-paks.md).

## Command

```
PYTHONPATH=src python -m roadcraft.overrides manifest <pak|mods-dir>... --game <RoadCraft folder>
    [--cache <dir>] [--installed <pak|dir>]... [--transactions <dir>] [--json] [--output <file>]
```

- Folders expand to their `*.pak`. All targets form one install set; `--installed` adds paks that are
  checked for conflicts without rows of their own (a candidate against an installed folder).
- `--cache` keeps the retail index (66 paks, 227,349 tags) keyed by every retail pak's path, size,
  mtime and layer order; it is rebuilt automatically after a game update and refused inside the
  game folder. A cold index takes about 3 s, a cached run of 7 local mods about 0.7 s, and 17 share
  paks (3.3 GB) about 2 s, because only central directories are read.
- Equal CRC-32 and size are confirmed by streaming SHA-256 of both members (`--no-hash` skips that).
- `--transactions` adds the latest `roadcraft.transaction` receipt for each pak installed at that path
  and whether the current bytes still match its candidate.
- JSON output has sorted keys and no timestamps; two runs over unchanged inputs are byte-identical
  (`tests/test_overrides.py`).

## Statuses and engine effect

| Status | Meaning | Effect | Grade |
|---|---|---|---|
| `new` | no retail pak or other mod has the tag | effective | Game (installed SDK mods load their own tags) |
| `identical-to-retail` | retail has the tag with identical content | effective in cached dirs, else probably ignored (no visible difference either way) | Inferred |
| `shadows-retail` | retail has the tag with different content; `retail.target` is `pak:member` | effective in cached dirs, else probably ignored | Inferred |
| `conflicts-with-mod` | no retail copy; another mod ships the tag (`modConflicts`, each identical or different) | order-dependent | Inferred; mod load order is Open |

- Tag = `res://` + member path with `\` -> `/`, lowercased (`ResourceTag.MakeFrom`). Grade: Retail
  (decompiled editor/game code).
- Mod paks are added as layers with index mode 1 (`Roadcraft - Retail.exe` `FUN_14282adc0`). For a tag
  whose immediate directory is one of `TagDirsToCache` (`res://`, `res://ssl/`, `res://pct/`,
  `res://td/`, `res://sounds/events/`, `root/config/editor/convert.cfg`) the mod entry replaces the
  existing one; elsewhere (`models/`, `material_instances/`, nested `ssl/...` folders) the earlier
  retail entry is kept. Grade: Inferred from decompilation, not tested in game. A test would install
  a pak that shadows one retail `td/` and one `material_instances/` member and observe which takes.
- The game logs "Resource %s also exists in mod %s" for both sides of a mod-vs-mod conflict
  (`FUN_14280f090`). Grade: Retail (decompiled); log text not yet captured from a run.
- SDK builds cannot shadow retail descriptors: the builder removes retail tags from the resource graph
  and skips retail blobs (`_graph.py` L93-95, L125-126). Grade: SDK. Shadowing appears only in
  hand-built or repacked paks.
- 172 retail tags exist in more than one retail pak, all identical copies (e.g. `font_main/*`); the
  manifest reports the first pak in `convert.cfg` `TagLayers` order and counts the rest. Grade: Retail.

## Findings on real mods (Build, 2026-10-13)

- `root/mods` (7 paks: apoc_buggy, goliath_d11, jimny, kgs25, roamer105ute, walle,
  watcher_y61_expedition; 8,416 members): every member is `new`; no cross-mod conflicts. Duplicate
  tags per pak are only the expected `.tpl_markup` pairs (goliath 18, kgs25 6, walle 5, others 2).
- `\\192.168.0.129\mods` (17 paks): 36 conflicting tags, all between `dumptwuck.pak` and
  `l275_minespec.pak`, all byte-identical by SHA-256: 27 `pct/mod_tuz_119lynx_trails_{nm,mask,hdetm}_<n>.pct_mip`,
  6 `.pct.resource`/`.td.resource` and 3 `.td`. They come from the SDK sample's
  `root/mods_source/pct|td/mod_tuz_119lynx_trails_*` that both projects reference. Every one is in a
  cached directory (`pct/`, `td/`), so whichever loads wins, but with identical bytes the result is the
  same; expect the conflict log lines in game. To silence them, rename the copied resources per mod
  (Inferred remedy).
- No mod on either folder shadows or repeats a retail tag. `mammoth.pak` and `t80bvm.pak` (non-SDK
  packer) have no duplicate tags; all SDK-built paks have 2-18.
- A hand-built member named `Master_Materials\Combine_Material_Default.mm` resolves to the retail tag
  `res://master_materials/combine_material_default.mm` (shipped in `client/default/default_materials.pak`)
  and is reported `shadows-retail`, `probably ignored`; the regression uses synthetic paks
  (`tests/test_overrides.py`).

Prototype and earlier demo output: `C:\RC_RE\research\override_manifest.py` and
`C:\RC_RE\research\manifests\` (superseded by `roadcraft.overrides`, same counts).
