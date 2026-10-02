# Textures and material instances

## Texture sets

| Rule | Grade |
|---|---|
| Sources are uncompressed TGA (Pillow's default type 2), power of two, named `mod_<prefix>_<set>`, `_nm`, `_spec` | Build (SDK samples, every mod) |
| `_nm` is a Y- (DirectX) normal map; Substance Painter's OpenGL output needs its green inverted. Measure unknown maps (correlation of the curl of R/G decides Y+ vs Y-) | Build (grader, Warthog, buggy maps measured) |
| `_spec` packs R metalness, G roughness, B ambient occlusion | Build (in-game look) |
| Art without metal/roughness maps: a per-set metalness and roughness following the colour map's brightness is a workable spec | Build (buggy) |
| The TextureConverter takes its mip count from the `.td` template it is given: start from the SDK sample descriptors rather than a fallback one (3 levels), then verify the actual chain at the target resolution (see Lada v9 below) | Build (994 loader) |
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


## Glass template resampling and compiled dimensions (L275, 2026-09-30)

**SDK/Build, installed TextureConverter:** the stock `MD+MT` glass descriptor
uses `resample=1`. With an already-budgeted 1024px L275 source TGA this produced
a 512px PCT; overriding `resample=0` retained 1024px and nine mip levels. Inspect
compiled PCT dimensions and mips as well as source image sizes. A matching source
size and a valid stock descriptor do not prove the compiled texture's resolution.

Evidence: shipped `td/mod_tuz_119lynx_glass.td`, L275 `tools/prepare.py` and
`reports/asset_validation.json` (actual PCT header checks). This is the observed
installed SDK behavior, not a promise for future converter versions. The project
checks every authored texture's compiled size; shared enforcement is deferred
because the generic BRO linter has no texture-budget contract.

## Compile readiness is not texture-authoring readiness (L275, 2026-09-30)

**Build/read-only source inspection:** L275 v2's successful texture/material
compile established resource dimensions and bindings, not a complete high-quality
UV/bake setup. All seven body LOD0 mesh objects have one UV layer. The existing
cab/chassis/interior maps have 4K/2K/2K budgets, while the tray/toolbox/hardware
finishes are ten 64px uniform PBR sets with flat normals. They can render a clean
finish but do not contain detailed authored wear, roughness or baked normals.
The revised tray also changes surface proportions without repacking its UVs.

Before claiming a final texture-authoring asset, separately review UV overlap,
padding, distortion and texel density, give the detailed surfaces appropriate
atlases, and rebake supporting mesh maps on the final geometry. Exact repeated
UV triangles are only one overlap test; their absence does not establish unique
islands. The read-only audit flags nine cab UV triangles below 1e-12 area, but
has no complete island/bake-quality analysis. Intentional mirrored/tileable UVs
are valid, so no universal no-overlap rule is added. Existing dimension/UV-layer
checks stay scoped to compile readiness. Evidence: L275 v2
reports/texture_readiness.json, build/material_contract.json and pack_textures.py;
revisions/proportions_v2/inspect_texture_readiness.py. No source/package changed,
no game/editor launched, and no new texture/bake completion is asserted.


## Preserve compiled textures during unrelated changes

**Build, Lada v8:** a full texture rebuild changed 217 of 614478 bytes in the
BC7 shop icon although the cockpit update did not change that artwork. Do not
assume re-encoding is byte-deterministic or accept unrelated asset churn without
inspection. When source artwork and material settings are unchanged, retain
verified compiled PCT/TD/material inputs and rebuild only the affected stages.
Declare and pin all reused inputs and compare packaged bytes to the baseline.

The Lada restored the prior icon from its sealed v7 fixture and used its
`--interior-only` recipe adapter for final model/animation work. This is a local
adapter option, not a generic CLI flag. It still runs prepare, generation and
package checks. Never substitute an old compiled texture when its source or
settings intentionally changed. Evidence: `revisions/interior_v8/icon_preservation.json`,
build-012/test-014 and the v8 result; the 374 checked assets outside the body
animation payload matched v7. See [new-mod-creation](new-mod-creation.md).

## L275 Blender materials v3 (2026-09-30)

**Blender review/Build:** the earlier L275 v2 compile-readiness entry remains
historical. V3 replaces its flat 64px tray finishes with actual procedural
Blender/Cycles shaders and bakes. Two 4K atlases (body/tray paint), eight 2K
atlases, 61 PNG channels and 30 native TGAs retain 17 material bindings. No
Substance or paid provider was used. Cab/interior/wheel source art is preserved
within the new shaders; this is not a new high-poly vehicle mesh.

Bake albedo as sRGB emission, scalar metallic/roughness/AO/curvature as
Non-Color emission, and normals as tangent NORMAL (Blender OpenGL Y+). Export
R metal/G rough/B AO without rescaling. Normalize averaged normal vectors,
replace near-zero vectors with neutral, then explicitly flip G for RoadCraft
DirectX Y-. An initial independent unit-vector audit failed in eight sets;
preserve it rather than weakening the check. V3 normalized 122145 materially
short vectors and replaced 3953 near-zero pixels, then passed the independent
0.03 unit-length error bound and pixel-exact packing/convention checks. Raw
bakes remain unchanged. Numbers are this asset's export, not general thresholds.

The first white-paint preview was too granular. Curvature/Pointiness across
large flat source panels spread the wear mask. The reviewed refinement uses
a Bevel-vs-geometry-normal edge mask (1.5mm, four samples), fine 18µm bump and
restrained roughness/dust. Those values are L275 art choices, not a universal
paint recipe. Editable shader studio and game-map studio are both preserved;
the engine receives preset materials and baked maps, not arbitrary node graphs.

Four new finish atlases span the tray and both moving doors. Geometry-pinned
UV patches are applied before native lower-LOD generation. A strict-interior
512px raster audit found zero overlaps for those four atlases; it does not
certify absent subpixel intersections or complete distortion quality. Existing
source sharing is retained. V2's nine near-zero cab UV triangles cover only
3.656319101e-9 m² (0.003656 mm²) of geometry, so the old flag does not establish
a visible texturing defect. Packing margin 0.008 and dilation 8px are recorded.

Evidence: L275 tools/blender_materials.py, texture_processing.py,
pack_blender_bakes.py, audit_blender_materials.py (106 actual artifact checks,
wired into validate.py), reports/artist_uv_audit_v3.json,
blender_texture_packing_v3.json, normal_validation_before.json, final shader
and baked previews, art/materials_v3/manifest.json. Download receipt pins
official Poly Haven CC0 references. Original source manifest is immutable;
new ART_ROOT routes and the legacy packer guard prevent overwriting it. Shared
generic UV enforcement is deferred because source sharing can be intentional;
the vehicle's geometry/map contracts supply the meaningful checks here.


## Bounded source UVs can still collapse a bake (Dump Twuck, 2026-10-01)

**Authoring/Build:** the supplied Blender 5.1 model has a bounded `UVMap`, but
its faces overlap. An initial Blender 5.0 Cycles bake collapsed the varied source
palette to nearly uniform RGB (31,31,33). Naming/bounds alone do not establish a
usable atlas. Keep the failure and inspect actual images before native compilation.

Pack a new bake UV layout while retaining the source tiling UVs in shader nodes.
Apply that exact layout to export geometry before material splits and LOD creation.
Tie the UV patch to a vertex/loop geometry fingerprint, and check color variation
where the source palette is known to vary. Do not reject intentionally uniform
materials or shared/tiled UVs through a universal entropy/nonoverlap rule.

Evidence: `dumptwuck_mod/history/overlapping_source_uv`,
`reports/material_bakes.json`, `art/uv/*.npz`, `tools/bake_source.py`,
`tools/create_models.py`, and assembled Blender previews. These establish repaired
authoring bakes, not retail/campaign acceptance. The local validation checks source
hashes, geometry-bound UV restoration and expected palette variation. A generic
overlap/entropy gate is deferred because intentional sharing and uniform finishes
need an asset-specific contract.

Integration destinations: `library/textures-and-materials.md`,
`library/symptoms.md`, `library/case-studies.md` in the maintained toolchain.

## L275 front-end feedback and supplied texture update (2026-10-01)

**Build, L275 supplied update:** A newly supplied source Blender can contain external images on the original UV layout, while the installed mod has decimated meshes, repacked tray atlases and mirrored/normalized wheel assets. Check both routes before swapping maps. Here all twelve cab/chassis/wheel LOD0 source geometry and UV fingerprints matched the preserved original, but the provider also delivered thirty TGAs transferred onto the exact revised mod model (sealed fit reference equals the 2741f82b… draft Blender bytes). Use those fitted maps, preserve the provider manifest/files and their resolution choices (chassis raised from 2K to 4K). Existing DirectX game normals must not receive another green flip. Supplied textures are not attributed to the agent's earlier Blender shader bakes; retain both provenances independently.

Evidence: L275 tools/adopt_supplied_textures.py, reports/front_end_v5/supplied_textures.json, texture_geometry_parity.json and source/updates/20261001_new_textures/texture_fit_reference.blend. The dedicated new headlamp shader stays a separate Blender bake and game set. Provider README is provenance/reference, not authority to run its authoring tools. No Substance/Painter or Mod Editor was launched.


## Shop card and icon go stale after visual changes (L275 v6, 2026-10-01)

**Build:** the shop card (368 x 308) and vehicle icon (960 x 640) are ordinary
source images compiled once into UI textures; nothing rebuilds them when the
model changes. L275 shipped v3 to v6 with its v1/v2 renders (radiator box above
the bonnet, old dark wheels, no accessories) because they existed and passed the
dimension checks. Re-render them from the built model after any visual change
(L275 `tools/render_preview.py --ui-only`), record what they show and check it:
L275 writes the rendered model's per-LOD triangle counts to
`preview/ui_render.json`, and `validate.py` fails when they differ from
`build/physics.json`. Only the images' pixels change; the catalog's texture
names stay the same, so no class or catalog regeneration is needed.

Evidence: L275 `revisions/accessories_v6/before_ui/` (old art), build-023 /
test-024. A shared check is deferred: other projects store their UI renders
and model reports differently.

## Glass film convention and the two glass presets (L275 v8, 2026-10-01)

**Retail / SDK (decoded):** shipped cab glass colour maps (`MD+MT`, BC7) author clean windows as a dark
blue-grey film, RGB about 0.2, at alpha 0.5 (127) with nothing lower; dirt raises alpha towards 1 (Karelian,
Malamute, Scout, Invictus and Alces scouts, the SDK Lynx). Clean lamp covers go lower (about 0.27 on the Lynx
Mutt add-ons), and the shader source (`mtl_blend.fx`: `baseColor.a = diff.a * tint.a`, "opacity is increased by
dirtness") treats alpha as opacity, so lower alpha is clearer. A bright film reads as frosted glass: the v5 L275
map had a teal film (0.40-0.49) and a tan dust film (alpha 0.35-0.73) on the windscreen and rear window.

| Rule | Grade |
|---|---|
| Read retail textures: `default_pct_*.pak` hold `pct/<name>_<level>.pct_mip` files (no header); 16-byte 4x4 blocks, so bytes = pixels of that level; wrap one in a DDS DX10 header as BC7 (DXGI 98) and Pillow decodes it | Retail |
| Clean cab glass: dark film (about 0.18-0.21 RGB) at alpha 0.5 or below; dirt only at the seals and outside the wiper sweep | Retail, SDK |
| `vehicle_glass_outer`: double-sided lighting, `filter` [50, 101, 94] at `density` 1.5 by default (dark green); the SDK Lynx overrides [127, 155, 151] / 1 | Retail, SDK |
| `vehicle_glass_inner`: reflectance 0.15, filter [229, 255, 251], no density: the near-clear surface facing the cab. The Lynx puts it on its `hp_` glass and the outer preset on `_lp_` glass | Retail, SDK |
| A window modelled as a slab (outer and inner sheet) on the outer preset is tinted and hazed twice per pane: put the inner sheet on the inner preset | Build (L275 v8; owner check open) |
| The glass shader source itself is not shipped (only registers and `mtl_blend.fx`); `density` semantics are unknown, so keep `density` 1 and set the tint with `filter` | Retail |

Evidence: L275 `art/glass_v8` (manifest with before/after window statistics, generator), the decode script in
the L275 v8 session (scratchpad), shipped `default_materials.pak` presets and `default_non_retail_resources.pak`
shader sources; L275 v8 build-026 / test-027 (336 static checks).


## Restore source detail before regenerating an atlas (Lada v9, 2026-10-02)

**Build / inspected Blender 5.0 renders:** compare original source dimensions,
packing resolution and actual compiled PCT dimensions before choosing an upscale.
The Lada's supplied interior/interior_shell maps were already 4096 square, but
the mod packed them at 1024. Its two AI drafts were only 1254 square and altered
gauge marks, island borders and upholstery pattern scale despite preservation
instructions. The owner chose original 4K maps. Treat generation output as a
candidate to inspect on the actual UVs; a prompt is not proof of alignment,
faithful markings or output resolution. This observation concerns those two
drafts, not a universal AI resolution/quality limitation.

Restore colour, normal and packed metal/roughness/AO together at the selected
budget. Keep the existing tested normal convention (Lada source OpenGL G flipped
for DirectX), original atlas layout and source hashes. Do not overwrite an
immutable manifest's earlier packed maps: write the new variant under an art
root and route packing, Blender material setup and compilation to it. Keep
unchanged compiled textures to avoid unrelated encoder churn.

**SDK / Build correction to the descriptor-template shortcut above:** sample
descriptors are a starting point, not a guarantee of a complete chain at a new
resolution. This SDK's Lynx MNM descriptor capped the Lada 4K normal at ten
levels; MD requested eleven and MSCRGHAO twelve. The native compiler emitted
eleven through 4x4 once MNM's minimum request was raised to eleven. Build-013
failed its actual-header check and remains preserved. Derive/check the desired
chain for the map format and dimensions; do not impose eleven on every texture.

Retail PAKs split textures into `pct/<name>_<level>.pct_mip` members plus
`.pct.resource`, not a raw `.pct`. The six 1K-to-4K replacements add twelve
members (levels 9 and 10); exact inventory equality would incorrectly reject
them. Verify expected additions, duplicate occurrence counts, header sizes and
each mip's bytes against the compiled PCT offsets. Permit only the intended mip
chains/resources and changed TD settings; compare every other member to the
pinned baseline. Raw channel pixel equality checks complement this native
compression/payload audit.

Evidence: Lada `revisions/interior_4k_v9/request.json`, failed build-013,
build-015/test-015, `art/interior_ai_v9/` rejected drafts and on-model comparisons,
`art/interior_4k_v9/preview/`, and v9 `texture_result.json`. The local
`pack_interior_4k.py` and `audit_interior_textures.py` are wired into its
`--textures-only` adapter and validation. Exact pixel and package-delta contracts
remain project-specific; a new universal 4K/eleven-mip gate is not justified.
No v9 native editor/retail run or memory/performance measurement is claimed.
