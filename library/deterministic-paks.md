# Deterministic mod paks

Two SDK builds of the same inputs differ only in per-member header stamps. `roadcraft.pak_determinism`
rewrites those stamps in a copy so that rebuilds become byte-identical and a package hash can pin
content rather than build time. Scope: `mod_pak_builder.exe` from the current SDK (PyInstaller, CPython
3.7 `zipfile`) and its outputs as of 2026-10-13. Evidence grades are defined in
[README.md](README.md#evidence-grades).

## What the builder writes

| Fact | Grade |
|---|---|
| `mod_pak_builder.exe` is a PyInstaller bootloader around Python 3.7 bytecode; the archive is written by stdlib `zipfile` with `ZipFile(out, 'w', compresslevel=1)`, `ZIP_DEFLATED` except `no-compression` masks (`*.pct`, `*.tpl_data`, `*.bnk`, `*.wem`, `*/sounds/*/*.zip`) which are stored | SDK (bytecode disassembly, `main.py` L26 and L122-142; `root/prjenv/mod_pak_builder.prjenv`) |
| Member order is the LIFO resource-graph walk seeded by the roots (last root first), then the `.mod` appended last at the archive root; it does not depend on `PYTHONHASHSEED` | SDK (`_graph.py` L161-176) and Build (identical order across every rebuild pair) |
| `*.tpl_markup` is normally written twice with identical bytes (listed by both the `.tpl.asset` and the `.tpl_markup.resource`); keep both occurrences | SDK and Build (2-18 duplicate tags per installed pak) |
| Plain PKZIP: no prefix, no extras, no comment, local and central headers agree, version 20, host 0 | Build |

## What differs between rebuilds

| Field | Why it varies | Grade |
|---|---|---|
| DOS time/date, local header +10 and central record +12 | `ZipInfo.from_file` stamps the source file's mtime. Copied sources keep their own mtime, regenerated `.resource`/`.cls` get export time, and `pct/*_<n>.pct_mip`/`_tile` slices plus the rewritten `.pct.resource` are temp files written during the build, so touching inputs to a fixed time is not enough | SDK (`slice_pct.py` L67-110) and Build |
| `external_attr` (`st_mode << 16`: `0x81B60000` writable, `0x81240000` read-only) and the central host byte | depends on the source file's read-only bit and the OS that ran the packer | Inferred from CPython 3.7; all SDK builds seen are `0x81B60000`/host 0. Non-SDK `mammoth.pak` has 929 members with `0x01800000` |
| Everything else (names, order, sizes, CRCs, level-1 deflate streams) | deterministic given the same roots order, `.mod`, `paks-dir` contents and source bytes | Build |

Measured pairs (Build, `C:\RC_RE\research\pak_and_assets.md` §2.1): Jimny
`revisions/jimny-polished-v3/jimny.pak` vs `jimny-static-installed-v4/jimny.pak` (22,864,494 bytes each,
854 members) differ only in 2 x 854 timestamp fields; Goliath RC3 vs RC4 and the two Watcher builds
differ only in timestamps plus the intended content edits.

## Normalizing

```
PYTHONPATH=src python -m roadcraft.pak_determinism normalize <built.pak> <normalized.pak>
PYTHONPATH=src python -m roadcraft.pak_determinism check <pak>...
```

`normalize` copies the pak and overwrites in place only: DOS time/date -> 1980-01-01 00:00:00 in every
local and central header, central `external_attr` -> `0x81B60000` (directories `0x41FF0010`), central
host byte -> 0, and the time values of `0x5455`/`0x000A`/`0x5855` extra fields -> 0. Nothing is
recompressed and no offset moves, so duplicates, order and ZIP64 records survive. It then proves the
copy: bytes outside the patched fields equal the source, every member CRC is checked on read and its
decompressed SHA-256 equals the source member's. It refuses an existing destination and publishes
atomically. `check` exits 0 only when a pak would not change.

Results (Build, 2026-10-13):

- Jimny v3 and v4 both normalize to SHA-256 `ff37bf9aca8d9b241362c2cc250da8fe32cf0b073684b0b8d0f54327abec1852`
  (1,708 timestamp fields patched each), matching the research prototype. Regression:
  `tests/test_pak_determinism.py` `RealRebuildPairTests` (skips without the SDK folder).
- No installed (`root/mods`, 7) or share (17) pak is normalized today; every one varies only in
  `dosTimestamp`, except `mammoth.pak` (also `externalAttr` on 929 members).
- `goliath_d11.pak` (447 MB, 3,689 members) normalizes and verifies in about 8 s locally;
  `mammoth.pak` (658 MB) streamed from the share in about 16 s.

## Why the game still loads a normalized pak

**Inferred** until a normalized pak is loaded in game: retail paks under `root/paks` carry DOS
date/time 0 in every header, so the engine's pak layer cannot rely on member timestamps; the retail
`.pak.cache` index records only offset, sizes, method and CRC; the Jimny v6 repack (level-6 deflate,
editor timestamps) is installed and loads. Normalization changes none of the fields those readers
use. To settle it, install a normalized candidate through the usual transaction and drive it.

## Using it in a build

Keep the roots file order, `.mod` bytes and `paks-dir` set fixed, build with the SDK, normalize, then
pin the normalized hash as the candidate. Normalizing does not grant acceptance and does not make a
different input reproduce an earlier package. A fully headless packer would need the
`saber.lib.resources` descriptor schemas (`iter_refs`/`iter_blobs`); its output should equal
`normalize(SDK output)` (Open until implemented).
