# Loaded-scene and capture-origin API audit (2026-09-28)

The current D11 capture contract correctly leaves `loadedSceneVerified` and
`captureProcessAuthenticated` false. This read-only audit looked for a native
scene identity stronger than a path in the runner's `open` command or
`EngineControl.GetLevelName()`. It did not launch the editor or Painter, send
SSL, create a screenshot, or change an accepted scene, PAK, or receipt.

## Pinned evidence and what it says

The installed `root/bin/pc/Roadcraft ModEditor.exe` is 126,773,216 bytes,
SHA-256 `ce6a48b1c73bea0876376d3251a6810b4a9913a7d500226e42bb2c605f3810b7`.
Its ASCII SSL name table contains these adjacent entries (file offsets):

| Binding/name | Offset | Interpretation limited to the evidence |
| --- | ---: | --- |
| `EngineControl`, `LoadLevel`, `GetLevelName` | `0x05244a38`, `0x05244a60`, `0x05244a98` | Candidate runtime level label. The five-probe transport already covers `GetLevelName`, but its SSL signature and result remain untested. A label cannot identify source bytes. |
| `iactor`, `GetSceneName` | `0x05072018`, `0x050720c8` | Candidate scene-name property of an editor actor, not a getter for the active scene's resource digest. No scoped actor query or return shape has been demonstrated. |
| `GameEditor`, `FindGameObjectByName`, `GetGameObjects`, `GetSceneBbox` | `0x05073ad8`, `0x05073b50`, `0x05073cb0`, `0x05073c88` | Candidate editor-object inspection surface. The name table alone does not establish a callable global, method signatures, which scene(s) are enumerated, or loaded-byte identity. |

An exact ASCII scan of this pinned executable found `GetActiveScene` only in
an RTTI type name (`scnGetActiveSceneErrorLog`, offset `0x073cffa1`), not in an
observed SSL method table. It found no literal `GetSceneGuid`, `GetSceneGUID`,
`GetSourcePath`, or `GetSourceInfo`. This is a bounded negative search, **not**
proof that the engine has no other internal API or logging channel. The
shipped `D11_Full_Rig_Audit_20260925/native/sdk_sources/` SSL source is three
animation/controller files and provides no working call to these scene
identity methods.

The maintained runner `D11_Interior_AAA_20260928/capture_candidate_native.py`
(SHA-256 `369b8a5c472ec4966ac589d3fae9545cfde9570e68f42b7705b1597a36b1f025`)
writes a scenario that opens the selected `.scn`, waits for scene loading, and
checks a ready marker and the process's `mods_source` resource mount. The
maroon source `.scn` currently hashes to
`9481bca1db96dd5c3c0c201f9d7f84e0b16fd7e683905c286060b16e9d53dfa1`.
Those are command, process-log, mount, and **on-disk** source facts. They do
not report which resource bytes the renderer actually loaded.

The historical generated capture helper
`native/runs/aaa_maroon_bd58bce0ma/native_controls.ps1` (under
`D11_Interior_AAA_20260928`, SHA-256
`febe294bc940ca53bbbe0a0850dfc1bb75358fdc72ba196ed609a7e32241a975`)
issues `SaveScreenshot` with a named target, then constructs its reply. The
current runner checks a new screenshot target, copies the resulting PNG, and
hashes it. `native_capture_partial` binds the request, response, action
windows, process ID, helper, scene-source hash, and PNG consistently. The
reply is post-trigger and contains neither an engine-reported loaded-scene
digest nor an engine-reported PNG digest. The receipt chain is useful
consistency evidence; it is not independent authentication of the producer.

## Next native experiment and acceptance rule

First run the existing five exact, pinned, read-only probes separately in an
already-open **disposable** editor session after a validation scene loads.
Inspect the `GetLevelName` response and editor's visible scene tab. This tests
the method and label meaning only. The independent actor/editor names above
are **not** executable probes yet: establish a demonstrated SSL global,
signature, scope, and null behavior before adding any transport fragment.

For `loadedSceneVerified: true`, require native evidence bound to the same
process and capture interval that identifies the loaded validation resource
and links it to the exact pinned scene source or compiled resource bytes.
A matching level or actor label, scenario command, mounted source directory,
and on-disk SHA do not meet that rule separately or together. For
`captureProcessAuthenticated: true`, require an independently verified
engine-origin response bound to the exact screenshot request and image bytes,
in addition to the existing action/PNG hash chain. Keep both fields false and
keep the baseline/candidate pair gate blocked until those native proofs and
complete renderer readback have been demonstrated and reviewed.
