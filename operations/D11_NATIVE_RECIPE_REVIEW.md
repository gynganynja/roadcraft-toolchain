# D11 native recipe review (2026-09-28)

The [pinned AAA recipe](d11_aaa_native_preflight_recipe.json) is **preflight
only**. Its `build` phase runs `package_and_audit.py --check`; its `inspect`
phase runs `package_and_audit.py --audit-package` against the existing AAA
candidate; its `capture` phase repeats the source check and runs
`capture_candidate_native.py` without `--execute`. Every command uses an
explicit Python executable, argv array, AAA working directory, SHA-256 input
pins, 8 GiB free-space gate, and bounded timeout. It does not build a PAK,
open an editor, swap the installed PAK, or capture an image. Job logs from an
applied preflight are the generated output; the recipe's `outputs` are
unchanged, pinned files that the runner verifies after each step. A no-write
`jobs.run_recipe(..., dry_run=True)` passed all three phases on 2026-09-28.

The existing AAA `package_and_audit.py --build` cannot be replayed in place:
it derives all paths from its own `__file__`, refuses to proceed while the
current audited candidate and package receipt exist, writes a pending PAK and
builder log, then moves the pending PAK into the fixed retail output. It
internally invokes ModPakBuilder with a 1,800-second limit and a 4 GB disk
guard. A future build recipe needs a separately prepared, immutable project
clone with fresh output paths and a complete source inventory; copying this
command into the current project would either fail or threaten existing
evidence.

The AAA `capture_candidate_native.py --execute` is a transaction over the
installed `root/mods/cat_d11t.pak`, not a pure capture command. It requires a
predeclared run ID, writes a baseline backup and lock, swaps the candidate into
the live game path, launches native editor sessions, and attempts restoration
in `finally`. Its receipt and per-view outputs have run-ID-dependent paths,
which the guarded `--plan` declares with a contract SHA-256 before any swap.
This preflight recipe still does not call `--execute`.
The latest AAA receipt is `FAIL_ROLLBACK_PENDING`, with nested
`BASELINE_RESTORED`; that does not make the capture successful. Before an
executable capture recipe is admitted, the guarded runner still needs a
successful authorized native run and an evidence check that treats failure
and missing views as failure even when the installed baseline was restored.

The preserved `C:\RC\D11_Development\build.ps1` route is also unsuitable as a
drop-in native step. `dependencies/run_isolated.py build` imports six `.blend`
files, regenerates the project, and overwrites package and report paths;
`build.ps1 -ValidateOnly` still writes `model_validation.json`. Its old
`port_cat_d11t/tools/capture_final_views.py` accepts an arbitrary PID and
uses a fixed `F:` screenshot path unavailable on this host, without a
reliable project-ownership gate or bounded timeouts for all probes. The more
guarded `authoring/D11_retail_repair_20260923/visibility_lights/run_native_visibility.py`
requires over 14 GiB free; this volume had about 12 GiB free at review time.
Its sampled receipt still requires independent visual and campaign review.

Keep `--build`, `--execute`, `--recover`, and the C:\RC runners out of this
preflight recipe. The accepted installed hash remains
`3e3d21b877ad6e52c61de7665a90fe3a9e4dd3761c0f3115fc734938caf4aa16`;
the audited AAA candidate hash is
`3b4129d22b8a79bf1969ee7effd8d92b699beae1aa6a33deebb658cd2ade6031`.
These are observed, receipt-pinned identities at review time, not a claim that
the AAA candidate was accepted.
