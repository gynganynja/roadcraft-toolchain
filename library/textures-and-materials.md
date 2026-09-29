# Textures and material instances

## Texture sets

| Rule | Grade |
|---|---|
| Sources are uncompressed TGA (Pillow's default type 2), power of two, named `mod_<prefix>_<set>`, `_nm`, `_spec` | Build (SDK samples, every mod) |
| `_nm` is a Y- (DirectX) normal map; Substance Painter's OpenGL output needs its green inverted. Measure unknown maps (correlation of the curl of R/G decides Y+ vs Y-) | Build (grader, Warthog, buggy maps measured) |
| `_spec` packs R metalness, G roughness, B ambient occlusion | Build (in-game look) |
| Art without metal/roughness maps: a per-set metalness and roughness following the colour map's brightness is a workable spec | Build (buggy) |
| The TextureConverter takes its mip count from the `.td` template it is given: use the SDK sample's descriptors (full chain), not a fallback one (3 levels) | Build (994 loader) |
| A full chain stops at 4 x 4 (a 256 px map has 7 levels) | Build |
| Glass colour maps carry opacity in alpha (`MD+MT` usage) | Build |
| Budgets in the SDK samples: Lynx body 4096, glass 4096 x 2048, rim 1024, tyre 2048 x 1024; Crayfish sets 4096, rim 2048 | SDK |
| One wheel model is shared by all wheels of a class, so only one wheel needs texture space | Build |
| Store card 368 x 308 (opaque), vehicle list icon 960 x 640 (transparent): one-level BC7 with alpha, `disableStreaming: true` | Build, Game |
| The exporter links textures by Blender image **name**: name each image exactly as its resource (`mod_x_body`), or packaging fails on `res://td/<name>.tga.td.resource` | Build (16M3 grader) |
| A trail height map (`MH`, texture type `hdetm`) compiles to half a byte per pixel (format 37); use the shipped trail descriptor | Build (Roamer 105: sizes then matched the TUZ's) |
| Spec values used after "looks like it's made of plastic" (source maps had paint at roughness 0), metalness / roughness: paint 0.25 / 0.35, chrome 1.0 / 0.12, painted steel 0.55 / 0.5, rubber 0 / 0.88, fabric 0 / 0.85, plastics 0 / 0.65 | Build (Roamer 105; not re-judged by the owner) |
| A very dark source colour (navy at 8 % luminance) read too dark; x2.2 was "too vivid", the owner chose x1.6 | Game (Roamer 105) |

## Material instances (`material_instances/<name>.mi` + `.mi.resource`)

| Preset | Use | Params | Grade |
|---|---|---|---|
| `vehicle_body` | paint, metal, rims, unlit lamp lenses | `glt_shader.base.params { texDiff, texNM, texSpec }`, `game_material = "metal"` | Build, Game |
| `vehicle_tire_material` | tyres | `combine_material_shader.external_textures.textures [ { albedo, NM, spec } ]` | Build, Game |
| `vehicle_glass_outer` | glass | `texDiff/texNM/texSpec`, `reflectance`, `glass { filter, density }` | Build, Game |
| `vehicle_lights` | lit lamps | `texDiff`, `texSpec`, `emissive { intensity, bloomIntensity }`, `tex { emissiveTex }` | Build, Game |
| `cutoff_volume_surface` | the cab's water cut-off volume | `game_material = "default"` | Build |

Presets shipped in `default_materials.pak`: `vehicle_body`, `vehicle_glass_outer` / `_inner`,
`vehicle_cabin`, `vehicle_lights`, `vehicle_tire_material`, `pbr_mesh_decal_*`,
`cutoff_volume_surface` (Retail). `mod_pak_builder` resolves references only inside the mod project,
so a shipped material *instance* is copied into the mod under a mod name (Build, Roamer 105).

A skinned, double-sided material with LOD crossfade and vertex compression needs a shader permutation
the game does not ship: every session crashed at scene load, and the editor cannot compile shaders.
Retail trucks have no LOD crossfade (Game, Roamer 105 in the editor's play mode).

The `.mi.resource` lists the `.pct.resource` of every texture it uses in `links` and the preset's
`.mp.resource` in `parents`. The model's markup `materials` block keys on the Blender material slot
names, which are free-form.

## Substance Painter by script

Proven on the 994 loader's art (2026-09-29): project creation, baking, layers, export and saving,
all from Python over Painter's remote scripting. (Build)

| Rule | Grade |
|---|---|
| Start Painter with `--enable-remote-scripting`; the endpoint is `http://localhost:60041/run.json`. Steam must be running for the Steam edition. Do not start it while the game runs | Build |
| Projects saved by Painter 12.x do not open in 11.x | Build |
| `project.create()` returns at once: poll `is_in_edition_state()` and `not is_busy()` | Build |
| After a scripted bake Painter stays on the baking screen, where every `set_source(channel, Color)` fails ("Can't use a non legacy color space with a legacy color managed project"): call `ui.switch_to_mode(ui.UIMode.Edition)` first. Legacy colour management works; `Color(r, g, b)` without a colour space is the form that works | Build |
| `baking.bake_async` works in ordinary (non-UDIM) projects although `get_enabled_uv_tiles()` is empty; keep the stop source and the `BakingProcessEnded` handler referenced, and poll | Build |
| A grab of the main window shows a black viewport (Vulkan): review by exporting the maps and rendering them in Blender, never by screen capture | Build |
| Bake settings that worked (17 m machine, 4K sets): low as high, 2 x 2 subsampling, dilation 16, AO max distance 0.25 (relative), 96 rays, curvature radius 0.0015; AO and curvature "only same mesh name" for moving parts | Build |
| Layers: one group per finish with a geometry mask listing mesh names (`<object>__<finish>`), fills masked by starter smart masks whose parameters are set through `node.get_source().set_parameters` | Build |
| Export: create the project with `NormalMapFormat.DirectX` and export `Normal_DirectX` without a flip; map names `basecolor`, `metallic`, `roughness`, `opacity`, `emissive`, `AO_Mixed` | Build |
| The API reference is the module sources under `<Painter>/resources/python/modules/substance_painter/` and `resources/python-doc/` (the export JSON format is in `export.html`) | Build |
