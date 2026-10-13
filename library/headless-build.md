# Headless package build

`roadcraft pak build` packs a mod without opening the Mod Editor, never shows a window, and gives
the same bytes for the same input. Module: `src/roadcraft/pak_build.py`.

```text
roadcraft pak build --project <staged project> --mod-file <mod>.mod --output <new>.pak [--roots-file roots.txt] --json
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
| Temporary project | copies `.project`/`*.cfg` into `%TEMP%\mod<guid>` with paths rewritten | uses the staged project as is |
| Asset renaming | copies every used asset and renames it `<name>_<guid>`; the guid is random per editor launch | not done: released mods are already named (`auto_..._gd11`) |
| Scene export | `furnace scene -p <tmp> -s <scene> -d <tmp>\scenes\<name>_<guid>.scn` | not wired; a `.mod` with scenes is refused |
| Sound bundle | `mod_sounds_gen repack-external-sources` (scenes only) | not needed for `scenes: []` |
| Pack | `mod_pak_builder --project --resource-roots <tags> --output --mod_file` | same packer, `--resource-roots-file`, TEMP redirected |

Roots default to the `.mod` file's `scenes` + `assets` with `res://` prepended, which is what the
editor passes. A blank line in a roots file is refused: the packer reads the file with
`splitlines()` and turns it into an empty tag.

## Class staging (not done yet)

Every installed mod (all 17 on the desktop) ships its generated truck classes only under
`ssl/` as `ssl/auto_<truck>_<suffix>.cls`, `ssl/auto_wheel_<x>_<suffix>.cls`,
`ssl/auto_preview_...`, never under `autogen_dw/` (Build, 2026-10-13 desktop survey). The
editor's Build Mod / Mod Manager export moves and renames them and retags their links before
packing. `pak build` does not do that yet: on an ordinary editor project (KGS-25 `final\p`) it
packed the classes under `autogen_dw/`, a pak the game most likely cannot load the truck from
(Inferred). Preflight now refuses such a project. The released Goliath route stages `ssl/` with its
own scripts first, which is why its rebuild matched.

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
prints its sub-tool commands), the asset renamer for mods authored inside the editor, and the
sound repack. See `C:\RC_RE\research\build_pipeline.md` for the recovered editor behaviour.
