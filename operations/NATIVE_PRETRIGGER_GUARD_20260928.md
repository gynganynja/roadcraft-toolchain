# Offline D11 pre-trigger guard (2026-09-28)

The maintained AAA runner now checks the exact `ReadPreCapture` request and its
partial camera response before sending `CaptureCab`. This is a code-only safety
and diagnostic change. No editor, game, Painter, package swap, screenshot or
native transport was run for this change.

Within the existing six-action view sequence, the `ReadPreCapture` callback
now runs the pinned `native_precapture_request.audit` against the generated
helper and the actual sent Read transport. It then checks the SetCab and Read
transport IDs, owned engine PID, helper SHA-256, native workspace, ordered UTC
response times, active camera transform, active-camera and video-window
resolution, and a maximum 10-second age for the Read reply. The check repeats
inside the `CaptureCab` callback to catch changed files or a stale reply. The
retained engine handle is sampled again immediately before the native send.
If either check fails, the existing action event records `FAIL` and no capture
request is sent. A silent engine exit during camera settling now fails the
settle action itself instead of being labeled as a successful settle followed
by a failure at the next action.

The partial-link postcheck also rejects a CaptureCab transport whose recorded
request-send time is more than 10 seconds after the pre-screenshot reply. The
runner's optional `left_hvac_detail` view is explicitly accepted by the same
partial and pre-trigger validators; the full postflight roster remains the
standard 3×15 views. Each completed view embeds two `preTriggerChecks` in its
variant report, with phases `afterRead` and `beforeCapture`. No seventh action
event or new required output file was added.

## Pinned files

All paths are relative to the Steam SDK root. The existing 2026-09-28
`c0de2026` no-write plan and failed `bd58bce0` receipts remain historical;
their old runner SHA-256 `6449ddc0…` was not rewritten. A new reviewed-copy
manifest and unified patch preserve the exact runner delta.

| File | SHA-256 |
| --- | --- |
| `D11_Interior_AAA_20260928/capture_candidate_native.py` | `78e2f3634cbfde8d2b64b15652275474646338efe7f1f25a760a2140cfdc73dc` |
| `RoadCraftToolchain/src/roadcraft/native_capture_partial.py` | `26020bf75341c2ac72b8096145076e538a3cddfdb0f8f5113539106c16b2a6bc` |
| `RoadCraftToolchain/src/roadcraft/native_precapture_request.py` | `31a1831c3cf899933b5d490c95de0508f8b0b80f250897f7696b08b009f34e80` |
| `RoadCraftToolchain/src/roadcraft/native_capture_postflight.py` | `ad81fa466f1cde0d2e1b963b222fccd67014d211f630c1b20160e54631d81c5f` |
| `RoadCraftToolchain/operations/d11_aaa_native_preflight_recipe.json` | `bfe76b5514f13f91f1b8d46d7183021695ca93ae4677984ff394df4921042bae` |
| `RoadCraftToolchain/operations/patches/capture_candidate_native.pretrigger_20260928.py` | `78e2f3634cbfde8d2b64b15652275474646338efe7f1f25a760a2140cfdc73dc` |
| `RoadCraftToolchain/operations/patches/capture_candidate_native.pretrigger_20260928.patch_manifest.json` | `e7b7756a9e2a76974cfdc8ab0cfce11b65a47d5375ece4b960395796bace1115` |
| `RoadCraftToolchain/operations/patches/capture_candidate_native.6449ddc0_to_78e2f363.patch` | `be14e65a80e98da111874c930bedee36bca0d33a23526eef306d76f5a039f875` |
| `RoadCraftToolchain/tests/test_native_capture_contract.py` | `41382da4ce514c7285af207ac368ad78eae23ea6d4d8dbc275742d41b09d0b2c` |
| `RoadCraftToolchain/tests/test_native_capture_partial.py` | `050d25a3a8d7b40870cf2fa188034ec95f2b529daa11a9d9ea779520eb4b8854` |
| `RoadCraftToolchain/tests/test_native_capture_postflight.py` | `d88c8ab83c45b75fad327df143a6f77845ca2fe30fbc982e642ba8e89e5d2a86` |
| `RoadCraftToolchain/.gitattributes` | `4d48ac3a26e96ebcb1c36080c2fbb483b388113069f907a80f0f2caead69428d` |

The preflight recipe now pins the new runner in both capture steps and the new
verifier in its Read-source step. Its verifier path is in the dedicated
`C:\RC\RoadCraftDev\toolchain` checkout, which must receive these reviewed
files before applying the recipe. The runner's `PARTIAL_LINKER_MODULES` and
postflight validator both expect seven source modules, including
`native_precapture_request.py`. `.gitattributes` now preserves LF for those
statically pinned source files across Windows checkouts. A fresh no-write
capture plan must replace `c0de2026` for any later reviewed native invocation.

## Offline validation

- Focused runner, partial-link and request-verifier suite: **36 passed**.
- Full-capture postflight suite: **18 passed**.
- Actual source-only `python -m roadcraft.native_precapture_request --config
  local/machine.json`: `PINNED_PRECAPTURE_REQUEST_VERIFIED`, with
  `transportRequestVerified: false` and all native proof flags false.
- Actual runner `--plan --run-id c0de2027`: no-write status
  `CAPTURE_OUTPUTS_DECLARED_NO_SWAP`, 383 required files, seven pinned linker
  modules, runner SHA-256 `78e2f363…`, verifier SHA-256 `31a1831c…`, contract
  SHA-256 `32d53165c5d8bac941172f521f6c02e774b91c61618bab8b7b847092a35c8689`.
  The no-write plan was retained as `operations/d11_aaa_native_capture_plan_c0de2027.json` (SHA-256 `64a470ba99945394b922cf3d019cd1c3c37f5bda5511f31d1e3846cb83a878f1`); it is a reviewed contract, not execution evidence.

- The integrated 325-test suite passed in both the Steam mirror and dedicated checkout, with four machine-specific skips each. The dedicated `capture --recipe operations/d11_aaa_native_preflight_recipe.json --json` returned `dry_run`, three ready steps, `writesPerformed: false` and recipe SHA-256 `bfe76b5514f13f91f1b8d46d7183021695ca93ae4677984ff394df4921042bae`.

This guard verifies an internally consistent request and partial camera
observation. It does not authenticate the editor as producer, report camera up
or complete runtime lighting, prove loaded scene-resource bytes, acknowledge
the completed PNG bytes from the engine, or make a capture pair comparable.
`loadedSceneVerified`, `captureProcessAuthenticated` and
`pairProtocolEligible` stay false. The prior failed capture remains failed.
