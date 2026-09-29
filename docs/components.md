# Components and boundaries

## Shared mod lifecycle

| Capability | Implementation | Scope |
|---|---|---|
| Project selection | `project_context.py` | Explicit registry, environment or nearest mod; no implicit historical checkout registry |
| Create/adopt workspace | `mod_workflow.py`, `onboard.py` | General, vehicle, material and tuning contracts; preserve existing files and acceptance |
| Vehicle extension | `vehicle_workflow.py`, `bro_lint.py`, `vehicle.py` | Shared truck/rig checks and compatibility with existing adapters |
| Parse/inspect | `core.py`, `ps_format.py`, `tpl_reader.py`, `retail.py` | Identity, duplicate archive occurrences, BRO/TPL and shipped reference data |
| Build/test/capture | `jobs.py`, `incremental.py` | Pinned declared commands, process gates, per-project jobs and verified reuse |
| Install/rollback/recover | `transaction.py` | Exact live hash or explicit absence, durable receipts and reversible prior state |
| Source provenance | `source.py`, `manifest.py` | Ordered source declarations and asset-specific export gates |
| Evidence | `review.py`, `regression.py` | Pinned comparison context; distinct capture/numerical/visual/campaign conclusions |
| Knowledge | `library/`, both skills | Evidence-graded reusable findings integrated during each task |

## Recovery and storage

`jobs-status` inspects the selected mod's durable lock and receipt. Use
`jobs-recover` only for a reviewed failed/interrupted native job with the required
live package, registry, config, lock and receipt pins. Its default is preflight;
`--apply` records a recovery receipt before releasing the shared job lock.
Never delete a lock just to make a run proceed. The separate package `recover`
command uses the exact transaction receipt and refuses unknown live state.

`python -m roadcraft.migrate --manifest PATH --manifest-sha256 SHA256
--source-root PATH --destination PATH --receipt PATH` previews a verified copy.
`--run` requires sufficient space including the configured reserve. Preserve
the source; a copy receipt does not prove a new authoring route has parity.

`cleanup.build_review` and the read-only storage MCP tool report exact files.
`expansion_cleanup` and `cleanup_commit` support specifically reviewed cleanup
contracts; their existence does not authorize deletion. Historical retail-export
cleanup findings must not be generalized to Git objects or ignored assets.

## Integrations

`roadcraft.mcp_server` has 11 read-only tools. It does not build, install, export,
recover, delete or launch applications; reports remain in memory. A configured
server entry is not proof of a connected integration. Check actual availability.

The separate `roadcraft.blender_mcp_server` requires a selected mod registry and
an explicitly pinned Blender executable/SDK parser. Its `blender_status` and
`usf_roundtrip` methods are bounded scratch diagnostics. The caller's inventory
must match that mod's accepted inventory and live source. Scratch and explicitly
requested diagnostic receipts stay under the toolchain's ignored `local/` roots;
this specialized boundary is retained. It never opens/saves a `.blend` or approves
native export. The plain evidence MCP remains read-only.

`integrations/SubstancePainterMCP` retains recovered Painter integration source
and provenance. It requires a separately configured live Painter connection.
The skills-only plugin does not install servers or native applications.

## Specialized investigations

The `blender_*`, `native_*` and capture-protocol modules include both reusable
mechanics and experiments tied to particular pinned sources/scenes. They remain
available with their tests and operation records. They are not the new-mod
starter path and their hard-coded cases are not universal mod requirements.

Use [the D11 case study](case-studies/d11.md) to locate historical repair,
reconstruction and capture results. Adapt a specialist probe only after reviewing
its assumptions, pins, source route and output boundaries. Record newly supported
general rules in the shared library with their scope and evidence.
