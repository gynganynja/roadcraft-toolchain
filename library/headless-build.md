# Headless package build

`roadcraft pak build` packs a mod without opening the Mod Editor, never shows a window, and gives
the same bytes for the same input. Module: `src/roadcraft/pak_build.py`.

```text
roadcraft pak build --project <project> --mod-file <mod>.mod --output <new>.pak [--roots-file roots.txt] [--stage-classes --suffix S] --json
roadcraft pak build ... --apply --json
```

Without `--apply` it only checks the inputs. With `--apply` it runs the SDK packer through the quiet
launcher ([quiet-launch.md](quiet-launch.md)), checks the packer's log, normalizes the package
([deterministic-paks.md](deterministic-paks.md)) and writes the receipt `<output>.build/build.json`.
It never overwrites a package and never installs one; use `roadcraft install` for that.

## What the editor's Build Mod does

Recovered from the decompiled editor (`ModEditorPlugin`, `ModEditorCommands.ExecuteBuildMod`) and
the packer's Python bytecode (`mod_pak_builder.exe` is a PyInstaller Python 3.7 program):

| Step | Editor | This command |
|---|---|---|
| Temporary project | copies `.project`/`*.cfg` into `%TEMP%\mod<guid>` with paths rewritten | uses a staged project as is; `--stage-classes` copies an editor project into `<work>/staged` with `documents-dir` rewritten |
| Asset renaming | copies every used asset and renames it `<name>_<guid>`; the guid is random per editor launch | `--stage-classes --suffix S`: the generated classes only, as `ssl/<stem>_S` (see Class staging); other assets keep their names, as in every installed mod |
| Scene export | `furnace scene -p <tmp> -s <scene> -d <tmp>\scenes\<name>_<guid>.scn` | not wired; a `.mod` with scenes is refused |
| Sound bundle | `mod_sounds_gen repack-external-sources` (scenes only) | not needed for `scenes: []` |
| Pack | `mod_pak_builder --project --resource-roots <tags> --output --mod_file` | same packer, `--resource-roots-file`, TEMP redirected |

Roots default to the `.mod` file's `scenes` + `assets` with `res://` prepended, which is what the
editor passes. A blank line in a roots file is refused: the packer reads the file with
`splitlines()` and turns it into an empty tag.

## Class staging

Every installed mod (the 17 on the desktop share and the 7 in `root/mods`) ships its generated truck
classes only under `ssl/` as `ssl/auto_<truck>_<suffix>.cls`, `ssl/auto_wheel_<truck>_<w>_<suffix>.cls`,
`ssl/auto_preview_...`, never under `autogen_dw/`. An editor project keeps them in
`mods_source/autogen_dw/trucks/[preview/]auto_<truck>/`. Packing that unchanged most likely gives a pak
the game cannot load the truck from (Inferred), so `pak build` refuses it unless staging is asked for:

```text
roadcraft pak build --project <editor project> --mod-file <mod>.mod --output <new>.pak --stage-classes --suffix kgs25 [--apply]
roadcraft pak stage --project <editor project> --mod-file <mod>.mod --out <new folder> --suffix kgs25 [--apply] --json
```

`pak build` stages into `<work>/staged`, packs from there, writes the full report to
`<work>/staging.json` and a summary under `staging` in `build.json`. `--suffix S` on an unstaged project
stages without `--stage-classes`. Module: `src/roadcraft/class_staging.py`. The source project is never
written; the staging folder must be new or empty and outside the project.

### Rules

From `BatchAssetRenamer` (decompiled `ModEditorCommands.cs`: `Prebuild`, `RenameTo`, `RenameBrands`,
`RenameMod`, `ProcessString`/`ProcessSection`, `PatchGenericResource`; the failed methods are in
`C:\RC_RE\scratch\renamer_failed.cs`) and `SSLUtils.ConvertBrandToClassName` (IntegrationCommon2):

| What | Rule | Grade |
|---|---|---|
| Which files | brand files (`.cls .sso .prop .lwi .prefab`) reachable from the `.mod` assets (or `--root`s) through `res://` links, limited to `autogen*/`. Unlinked generated files (`auto_truck_library.sso`, `auto_trucks_preview_library.sso`, `auto_wheels_library.sso`, `<truck>_prefab.prefab`) stay, and no installed pak ships them | Build (`CollectAllUsedAssets`; 24 paks) |
| Names | `<dir>/<stem><ext>` and its `.resource` -> `ssl/<stem>_<suffix><ext>`, flat | Build (`Prebuild`, `RenameMod`) |
| Brand identifiers | every whole-word `<stem>` -> `<stem>_<suffix>` (wheel pool entries, `sso:`/`cls:` blob names, `truck = "auto_x"`) | Build |
| Class names | `.sso` brands only: `ConvertBrandToClassName(stem)` -> `ConvertBrandToClassName(stem_suffix)` (`AutoKgs25TruckInfo` -> `AutoKgs25TruckInfoKgs25`, in `brandName` and `__type`). Words are capitalised, the rest lower-cased, and two digits meeting keep their `_` (`auto_r105_2` -> `AutoR105_2`). `.cls` class names are not renamed | Build (`_classRenames`; all 24 installed paks contain the converted names) |
| Links | every `res://autogen.../<stem><ext>[.resource]` and bare `.mod` asset path -> the `ssl/` name, in every text resource of the copy | Build |
| Bytes | token renaming only: CRLF, spacing and order are kept. The editor itself re-serialises through its type system (`PsSystem.SavePsToFile`), but no installed mod was built that way | Build |
| Project files | `.project`/`*.cfg`/`*.prjenv`: `documents-dir` and every absolute path to the source project (also folded over two YAML lines) are pointed at the copy, as `GenerateTempProject` does; otherwise the packer reads the original `mods_source` | Build |

Not renamed: textures, materials, models, sounds. The editor renames those too (`<name>_<guid>`), but
every installed mod keeps them (`pct/mod_kgs25_*`, `models/mods/kgs25.tpl.asset`).

**Suffix.** The editor's suffix is `ModData.ModScenesGUId`, a random GUID per editor launch. The decompiled
editor has no other export: `ModManagerView` only lists `.mod` files, and no "Mod Manager export" code exists
in ModEditorPlugin, Pros or the class/tpl plug-ins. The short suffixes come from each mod's own release
script and are chosen per mod: `kgs25`, `walle`, `jimny`, `kanga25` (the `.mod` stem), `apb`, `gd11`,
`r105ute`, `y61`, `dtw`, `g16m3`, `lnv`, `wh12`, ... (2026-10-13 survey). For an update, reuse the suffix
of the installed pak: the game finds the truck by these brand names, so a new suffix is a new truck.

The report lists `renames`, `identifiers`, `rewritten` (per file: path and identifier counts, new
SHA-256), `projectFiles` (old and new `documents-dir`; `documentsDirWasElsewhere` when it named a
different project), `notStaged`, `skipped` (`.blend`/`.blend1` authoring files are not copied),
`unmapped` (links that still point into `autogen*/`, missing generated files, dangling suffixed links,
project files still naming the source) and `problems` (bad suffix, duplicate brand names, which the
editor's `Prebuild` refuses too, an existing `ssl/` target, a non-empty staging folder). The build stops
on any problem or unmapped link.

### Evidence

| Project | Installed pak | Result | Grade |
|---|---|---|---|
| Jimny `Jimny_RoadCraft_20261005\project` + `jimny.mod`, suffix `jimny` | `root/mods/jimny.pak` | `pak build --stage-classes --apply`: all 828 members have the same names, order and bytes, the 18 `ssl/` classes and `jimny.mod` included. The package differs only in compression level and timestamps: the installed pak is the release script's level-6 repack | Build |
| KGS-25 `C:\RC\KGS25_RoadCraft_Mod\interior_2026-10-05\p`, suffix `kgs25` | `root/mods/kgs25.pak` (r4) | staging: 36 of 36 `ssl/` members byte-identical (18 classes + resources, `ramp` included) | Build |
| Roamer 105 Ute `Roamer105Ute_20261005\project`, suffix `r105ute`, the five `auto_*` roots | `root/mods/roamer105ute.pak` | staging: 18 of 18 equal after one newline translation. The installed members have `\r\r\n`: its `build_native.py` decoded CRLF text and wrote it with `Path.write_text`, which turned each `\n` into `\r\n` on Windows. The staged files keep the generated CRLF, which is correct | Build |

Found on the way: the KGS-25 `interior_2026-10-05\p\.project` has `documents-dir` pointing at
`repair_2026-10-03\p`, so any packer run on it read another project's `mods_source`. The staging report
flags that as `documentsDirWasElsewhere` and corrects it in the copy.

## Traps the command handles

| Trap | Evidence | Grade |
|---|---|---|
| The packer exits 0 when a blob is missing; `There isn't blob '<tag>' in layers.` is only logged. The build fails on that line | packer bytecode (`main`) | Build |
| `.pct` slices are written to `NamedTemporaryFile(delete=False)` and never deleted, stamped with the build time | packer bytecode (`slice_pct`) | Build |
| Member timestamps are the only bytes that differ between rebuilds of the same input | 4 rebuild pairs compared member by member | Build |
| `Duplicate name: '...tpl_markup'` warnings are normal: the graph adds the resource and a blob with the same tag | packer bytecode, every released pak | Build |
| The editor's Build Mod renames assets with a random GUID per launch, so editor builds are never repeatable | `BatchAssetRenamer` (decompiled) | Build |

## Evidence

Goliath D11 RC5 (2026-10-13): `--project D11_Goliath_RC5_20261012\p` with the release `roots.txt`
and `goliath_d11.mod` rebuilt in 45 s on the laptop, no window on the user's desktop, no dialog.
The package has the same 3,689 members, CRCs, sizes, compression and order as the shipped
`D11_Goliath_RC5_20261012\build\goliath_d11.pak`; two consecutive builds have the same SHA-256
(`e9dde432...`). Grade: Build. Whether the game loads normalized (zero-timestamp) packages is
Inferred from retail paks using zero timestamps, not yet tested in game.

## Not covered yet

Scene export through `furnace scene` (furnace is a console Python tool; `--only-print-cmd-lines`
prints its sub-tool commands), the editor's GUID renaming of textures, materials and models (no
installed mod uses it), and the sound repack. See `C:\RC_RE\research\build_pipeline.md` for the recovered editor behaviour.
