# Painter MCP live read-only capability check

Date: 28 September 2026, Australia/Brisbane.

The dedicated toolchain environment at `C:\RC\RoadCraftDev\toolchain\.venv`
started the recovered `substance_painter_mcp.server` over stdio. Its live MCP
inventory exposed 79 tools. Both `painter_status` and `get_capabilities`
returned successfully with `isError=false`. The connected app reported
Substance 3D Painter 12.1.5, Python API 0.3.5, and `project_open=false`.

Available capabilities include the BaseColor, Roughness, Metallic, Normal and
AO channels, layer blend modes, and projections. The live capability response
reported `baking_presets=false`, `auto_rebake_control=false`, and
`skew_painting_control=false`; future recipes must not assume those controls.

No project was open, so no `get_project_info`, layer inspection, authoring,
bake or export was attempted. The maintained toolchain contains no disposable
`.spp` or mesh. The drive inventory found no `.spp`. The Steam SDK contains
two existing FBX authoring inputs, neither designated disposable:

- `D11_Painter_Handoff_20260924/D11_Painter_Transfer/D11_Painter.fbx`
  (17,209,468 bytes)
- `D11_Dash_Integration_20260926/source_v5/D11_Dash_v5.fbx`
  (5,793,372 bytes)

The next project-level check requires a copied mesh and a disposable Painter
project with its own verified path and backup. This probe made no filesystem
or Painter project changes.
