# RoadCraft storage review — 28 September 2026

`storage_review_20260928.json` is the read-only, exact-file inventory used for
the approved cleanup. The scanner hashes each selected file against the retained SDK
original, checks that it is a regular file with one hard link, and measures its
allocated size. The inventory must be refreshed before any later removal.

## Completed first batch

The manifest identifies 159 copied editor scene-template ZIPs beneath old
native run `editor_data/Templates` directories. Their three permitted names
are `mod_scene_1x1.fct.zip`, `mod_scene_2x2.fct.zip`, and
`mod_scene_500x500.fct.zip`. Every copy matches the corresponding original in
`RoadCraft/tools/bin/ModEditor/Templates` by SHA-256. Their exclusive
allocation totals **6,763,810,816 bytes (6.30 GiB)**.

The exact review manifest SHA-256 is
`07e05d4a89e57edfdfd77cab9a92d086d6f13fafdc16e22ea325f48be984d756`.
The `roadcraft.cleanup_commit` preflight rechecked all 159 files against this
manifest and their retained SDK originals before deletion. Its `--apply`
operation was used only for the approved file list and wrote a per-file
receipt; it excluded the Git temporary pack.

The user approved only the exact file paths listed in `templateCopies`. All
159 were removed on 28 September 2026, with a completed per-file receipt at
`RoadCraftToolchain/local/cleanup_runs/20260927T234450Z-fdf34dd933ff/receipt.json`.
Post-check found zero listed copies remaining and all three retained SDK
originals present. C: free space rose to **13,073,088,512 bytes**. Keep their
enclosing run directories and all captures, reports, logs, project sources,
packages, and receipts. The active `D11_Interior_AAA_20260928` directory is
excluded.

## Separate Git candidate

The manifest records one file at
`C:\RC\D11_Development\.git\objects\pack\tmp_pack_vOMJaY`, occupying
**4,014,342,144 bytes (3.74 GiB)**. Git `count-objects -v` currently reports
this temporary pack as garbage; repository connectivity passed a read-only
check. This is a separate review item. Before removing it, recheck its exact
identity and Git state. Connectivity alone cannot establish whether it has
recoverable objects outside current refs. Keep every normal pack, index, and
working file.

## Storage gate

The completed template batch freed 6.30 GiB. The separate Git temporary pack
remains untouched. Substance 3D Painter 2026 is installed through Steam, but
current free space is still below the 30 GiB target for asset checkout and
staged builds. The next
cleanup inventory must inspect
individual generated children and account for file identities and hard links.
Historical September 25 cleanup manifests list paths that have already been
removed and cannot be counted as current savings.

Protect the accepted standalone interior project, its source and rollback
packages and receipts, the active AAA project and capture journal, authored
Blender sources, historical Git repository, checkpoints, and the 23 retained
tool-referenced report fixtures until source migration and dependency checks
are complete.
