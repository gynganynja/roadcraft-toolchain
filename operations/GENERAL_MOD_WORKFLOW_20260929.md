# General RoadCraft mod workflow — 2026-09-29

The product target is a toolchain for any RoadCraft mod the user makes, already
has, or obtains from another creator. A package-only mod must be inspectable
without access to its source. D11 is a difficult fixture, not the workflow's
required schema, asset layout or completion target.

## Supported now

- The core registry, package hashing/inspection, archive comparison, source
  inventories, receipts and read-only RoadCraft MCP accept caller-supplied
  paths and project names. Duplicate package members retain their occurrences.
- `roadcraft onboard` previews a new empty registry or hashes an existing PAK
  into an **unreviewed candidate**; `--output` creates a new registry and
  refuses to overwrite one. It never infers acceptance, authorship, source
  lineage or the game's installed target.
- CLI and read-only MCP select the machine configuration beside an overridden
  registry unless a config is explicitly supplied. A non-D11 registry no
  longer loads D11's installed-package and transaction history by default.
- D11 authoring/export diagnostics remain separate. Existing repaired USF
  inputs and their acceptance gates are unchanged.

## Next implementation slices

1. **Project isolation and discovery.** Extend the selected-registry rule to
   the Blender scratch MCP and every recipe/config helper. Add a read-only
   package discovery command that reports package identity, archive layout and
   likely mod namespace without assigning ownership or acceptance. Prove
   inspection on a real, non-D11 package.
2. **Source availability.** Support three explicit cases: new mod with source,
   existing mod with source, and package-only third-party mod. Capture ordered
   source inventories only when files are actually available; allow package
   inspection, comparison and evidence review without a source inventory.
   Provide an import report for supplied files and document unknown lineage.
3. **Build and install.** Define project-scoped recipe templates and adapter
   inputs rather than D11 path names. Add a reviewed first-install transaction
   flow for a genuinely absent target, with namespace collision checks, a
   saved rollback state and explicit package identity. The current installer
   requires a known prior installed package and an accepted baseline; do not
   reuse it as if it supports first install.
4. **Review and acceptance.** Make capture protocols and required views
   project-declared. Keep technical, visual and campaign decisions distinct.
   A third-party package can be inspected and tested without being promoted to
   an accepted package or treated as a modifiable source tree.
5. **Cross-mod proof.** Run the complete CLI/MCP read-only flow on a real
   non-D11 package-only mod, then build/test/capture/recover on a separate
   source-backed mod in a safe fixture. Add CI coverage for switching two
   registries in one process and for missing source/config paths. Only then
   call the general workflow complete.

Current D11 mesh coverage is 51/51 path-verified in memory, with the two
dashboard child paths checked in separate LOD0 pair scenes. It does not prove
generic authoring, USF writer parity, native compilation or campaign behavior.
Further D11-specific reconstruction should follow the reusable workflow work
unless it is needed to validate a generic capability.
