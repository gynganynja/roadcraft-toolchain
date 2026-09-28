# Additional D11 storage review — 28 September 2026

No original file was changed.

The exact review manifest is retained locally as
`storage_expansion_review_20260928.json` (SHA-256
`aa5aad369e601cf9bf076d11101fd3925f396de5898338fc150b4cfed69e7ec7`).
The Git repository carries a verified gzip copy with the same decompressed
SHA-256; decompress it before a future full dry run. The raw 33 MB JSON is
kept out of the code checkout's Git history.

## Read-only preflight receipts

The raw manifest is 33,006,671 bytes. The 1,637,311-byte gzip copy has
SHA-256 `9702561b1a74d2ba579ff2657d36d3db77081640a9d51bb4dd60373c08e2e1f0`;
decompressing it produces byte-for-byte the raw manifest and the pinned
SHA-256 above. The executable preflight uses that exact raw manifest pin.

The refreshed eight-file sample at
`storage_expansion_executor_sample_20260928.json` (SHA-256
`fd16cb7b2d60f8da4d6c49e747e0f8952ffed7d9fd2edba043e6869d54eed0fe`)
is `partialSample: true`, so `applyReady: false` regardless of process state.
It verified eight candidate files, checked one retained package, and removed
zero files. The sandboxed CIM command-line query was denied; the process-name
fallback identified uninspectable Python processes and retained that error as
a hard block.

The full sandboxed dry-run receipt at
`storage_expansion_full_preflight_20260928.json` (SHA-256
`01a620f31dc2db8afc287d2209510cc1df5955539f82942217c5405fd4ea88c6`)
verified all **23,604** candidate files and their counterparts: 21 retained
packages and 166 retained source files. Its current exclusive allocation was
6,368,972,800 bytes (5.93 GiB). Git had zero tracked candidates. No file was
deleted. It records `applyReady: false` and `processInspection.complete: false`
because CIM denied command-line inspection. Toolhelp process-name enumeration
adds concrete uninspectable process identities but does not waive that block.

A separate full **read-only** dry run with elevated process inspection wrote
`storage_expansion_full_preflight_elevated_20260928.json` (SHA-256
`b8046ca22501bdae11510ed4a72ac19292a9d00c965454789ba687f401059601`).
At `2026-09-28T01:35:50Z` it verified the same 23,604 candidate files,
21 packages, 166 source files, and zero tracked candidates; CIM returned 315
process command-line rows, with zero active game/editor/export processes. Its
`applyReady: true` reports that the exact preflight gates passed at that time.
It is not a deletion receipt or authorization, and process ownership can change
after the check. The preflight does not resolve the three unreadable dependency
folders or unknown historical references described below. No `--apply`
command ran.

Identified 23,604 exact generated retail-export files totaling **5.93 GiB** of current exclusive allocation.
This does **not** establish the requested additional 15–20 GiB. Do not broaden deletion to source-bearing report folders to reach a quota.

Every candidate has one hard link, no reparse ancestor, is untracked, and matches either an occurrence in its retained audited PAK or a retained original texture file. Generated projects were created by the inspected retail_export.py recipe. Archive duplicates were inspected by occurrence. All PAK snapshots, outputs, audits, logs, sources, checkpoints, and Git data remain protected.

Only exact files in storage_expansion_review_20260928.json are candidates. Keep every enclosing project/report directory and unlisted file. The elevated read-only run found no active owner at one instant; recheck current processes/jobs, hashes, identity, allocation, links and reparse status before any authorized execution.

| Generated staging project | Candidate allocation GiB | Files |
|---|---:|---:|
| `C:\RC\D11_Development\authoring\D11_retail_repair_20260923\explicit_lighting_owner\build\build\retail_exports\20260923T040525267816Z\project` | 0.360 | 1128 |
| `C:\RC\D11_Development\authoring\D11_retail_repair_20260923\flush_ladder\build\build\retail_exports\20260924T010755838007Z\project` | 0.360 | 1128 |
| `C:\RC\D11_Development\authoring\D11_retail_repair_20260923\inner_lift_lights\build\build\retail_exports\20260924T013918311430Z\project` | 0.360 | 1128 |
| `C:\RC\D11_Development\authoring\D11_retail_repair_20260923\ladder_rollback\build\build\retail_exports\20260923T234848082256Z\project` | 0.360 | 1128 |
| `C:\RC\D11_Development\authoring\D11_retail_repair_20260923\original_ladder_horizontal\build\build\retail_exports\20260924T001510682322Z\project` | 0.360 | 1128 |
| `C:\RC\D11_Development\authoring\D11_retail_repair_20260923\original_ladder_v2\build\build\retail_exports\20260923T231856120894Z\project` | 0.360 | 1128 |
| `C:\RC\D11_Development\authoring\D11_retail_repair_20260923\steady_beacon\build\build\retail_exports\20260923T042403529881Z\project` | 0.360 | 1128 |
| `C:\RC\D11_Development\authoring\D11_retail_repair_20260923\stock_engine_diagnostic\build\build\retail_exports\20260923T035846851786Z\project` | 0.360 | 1128 |
| `C:\RC\D11_Development\authoring\D11_retail_repair_20260923\stock_engine_diagnostic\build\build\retail_exports\20260923T035953644934Z\project` | 0.360 | 1128 |
| `C:\RC\D11_Development\authoring\D11_retail_repair_20260923\visibility_lights\build\build\retail_exports\20260923T050152978841Z\project` | 0.360 | 1128 |
| `C:\RC\D11_Development\port_cat_d11t\build\retail_exports\20260918T011241821442Z\project` | 0.351 | 1104 |
| `C:\RC\D11_Development\port_cat_d11t\build\retail_exports\20260918T013345542379Z\project` | 0.350 | 1104 |
| `C:\RC\D11_Development\port_cat_d11t\build\retail_exports\20260918T044309904548Z\project` | 0.350 | 1104 |
| `C:\RC\D11_Development\port_cat_d11t\reports\blade_hydraulics_audit_20260922\retail_tool_repair_test_20260922_v1\build\retail_exports\20260922T043141653348Z\project` | 0.358 | 1126 |
| `C:\RC\D11_Development\port_cat_d11t\reports\combined_user_fixes_20260923\retail_v2\build\retail_exports\20260923T024946098335Z\project` | 0.360 | 1128 |
| `C:\RC\D11_Development\port_cat_d11t\reports\retail_rough_terrain_repair_20260922_v1\build\retail_exports\20260921T215109810777Z\project` | 0.042 | 1126 |
| `C:\RC\D11_Development\port_cat_d11t\reports\retail_rough_terrain_repair_20260922_v2\build\retail_exports\20260921T215542635720Z\project` | 0.042 | 1126 |
| `C:\RC\D11_Development\port_cat_d11t\reports\retail_service_release_20260922\user_test_build_20260923_v1\build\retail_exports\20260922T202253683001Z\project` | 0.358 | 1128 |
| `C:\RC\D11_Development\port_cat_d11t\reports\retail_user_test_20260921_v1\build\retail_exports\20260921T051849502383Z\project` | 0.042 | 1126 |
| `C:\RC\D11_Development\port_cat_d11t\reports\retail_user_test_20260921_v2\build\retail_exports\20260921T052146369306Z\project` | 0.042 | 1126 |
| `C:\RC\D11_Development\port_cat_d11t\reports\retail_user_test_20260922_v1\build\retail_exports\20260921T201354101144Z\project` | 0.042 | 1126 |

The input CSV covers C:\RC\D11_Development only. Large remaining areas hold authored TGA/Blend/USF data, source-construction JSON, retained fixtures and historical evidence. Temp occupies less than 1 MiB in the snapshot. Prior September 25 project/template cleanup batches were already absent in a fresh check; they are not counted again.

Reference checking searched executable scripts and Markdown for exact export-stage timestamps and found no matches in the readable files. Three local Python dependency folders under `temp/python_packages` returned access denied; the exact errors are recorded in the manifest. JSON and binary content can contain other historical references, so this is a bounded review, not a claim of complete dependency reachability.

Of 22 export stages, 21 had retained audited packages that passed their existing hash pins. The stock-engine stage `20260923T035750311646Z` lacked the complete sealed package inputs and was excluded. The 23,604 selected file identities are unique and all have exactly one hard link. None lies within the 23 retained fixture project roots, checkpoints, or Git. Another 126 generated configuration files were preserved. No packages or snapshots are candidates.
