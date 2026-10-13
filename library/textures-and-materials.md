# Textures and material instances

## Texture sets

| Rule | Grade |
|---|---|
| Sources are uncompressed TGA (Pillow's default type 2), power of two, named `mod_<prefix>_<set>`, `_nm`, `_spec` | Build (SDK samples, every mod) |
| `_nm` is a Y- (DirectX) normal map; Substance Painter's OpenGL output needs its green inverted. Measure unknown maps with `python -m roadcraft.normal_maps MAP...` (sign of the mixed-derivative correlation; needs Pillow + numpy). File and MTL labels are not evidence: WALL-E's `*_Normal_DirectX` maps measured OpenGL | Build (grader, Warthog, buggy, WALL-E maps measured) |
| `_spec` packs R metalness, G roughness, B ambient occlusion | Build (in-game look) |
| Art without metal/roughness maps: a per-set metalness and roughness following the colour map's brightness is a workable spec | Build (buggy) |
| The TextureConverter takes its mip count from the `.td` template it is given: start from the SDK sample descriptors rather than a fallback one (3 levels), then verify the actual chain at the target resolution (see Lada v9 below) | Build (994 loader) |
| A full chain stops at 4 x 4 (a 256 px map has 7 levels) | Build |
| Glass colour maps carry opacity in alpha (`MD+MT` usage) | Build |
| Budgets in the SDK samples: Lynx body 4096, glass 4096 x 2048, rim 1024, tyre 2048 x 1024; Crayfish sets 4096, rim 2048 | SDK |
| One wheel model is shared by all wheels of a class, so only one wheel needs texture space | Build |
| Store card 368 x 308 (opaque), vehicle list icon 960 x 640 (transparent): one-level BC7 with alpha, `disableStreaming: true`. The `.td` needs `mipmap_level = 0`: any other value makes the converter cut a non-power-of-two width (KGS-25's icon shipped as 512 x 640 with 4 levels) | Build, Game |
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

**Cab presets and the mud "covering" (L275 v31, 2026-10-13; Retail presets read, fix not yet seen in game).** The
game's mud / dust layer on vehicles is the material's `covering`. Decoded `default_materials.pak` presets:
`vehicle_body` = bare `glt_extended_material` (covering on); `vehicle_cabin` = the same plus `covering { forceDisable =
True }` (and `reflection.disableSSR = False`); `vehicle_glass_outer` and `vehicle_glass_inner` force covering off;
`vehicle_interior_glass` (blend, glass combiner, no filter, screen-space shadows off) is the one glass preset that
leaves covering on; `vehicle_rain_wipers` is a separate `combine_material_default` with `shaderType = "shader_wipers"`
(rain layer). A cab interior on `vehicle_body` gets mudded like the bonnet (owner: "the inside still gets covered in
mud"): put every in-cab material instance on `vehicle_cabin`. When a texture is shared with exterior parts, give the
in-cab object its own instance (same texture, `vehicle_cabin`); the exporter keeps one material per texture per object,
so separate objects may differ. Cab glass that is invisible from the cab (v8 inner preset, v23c inner + tint, v28
outer preset culled from behind: all three tried, all invisible in game) moves to `vehicle_interior_glass` in v31.
Retail truck material instances are compiled into the models, not shipped as `.mi` files, so per-truck use cannot be
read from the paks.
`vehicle_lights` explicitly keeps covering on (`params { emissive {...}, covering { forceDisable = False } }`), so a lit
copy inside the cab (instrument cluster shown with the headlamps, radio screen) mudded over in game (owner, L275 v31).
`covering` sits inside `shaders.glt_shader.base.params`, not at the top level; L275 v32 overrides it per instance
(`params.covering = { forceDisable = True }`, Build; game result open). The `.mp.view` schema also lists a hidden
`params.covering.coveringMask` texture. Painted body metal seen from the cab (door-top sills, inner pillars) needs the
same `vehicle_cabin` twin as the trim: split it into its own object (exporter: one material per texture per object).
The override sits inside the params block: `shaders.glt_shader.base.params.covering.forceDisable` (not top level);
the `.mp.view` schema also lists a hidden `covering.coveringMask`. `vehicle_lights` sets `covering.forceDisable = False`
explicitly (emissive intensity 300, adaptiveIntensity, bloom 20, `game_material = "default"`), so lit copies inside
the cab (L275 lit gauges) mud over unless their instance overrides it (L275 v32; not yet seen in game).

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
| With the inner sheet on the stock inner preset (near-clear, reflectance 0.15) the windows vanish from the cockpit: the outer sheet faces out and is culled from behind (owner: "cant see the glass from inside the cab"). Overriding the inner instance with the outer tint and reflectance (L275 v23c: reflectance 0.45, the outer filter at density 1) did NOT work: still invisible in game (owner screenshot, 2026-10-13); the inner preset seems to ignore those params. v28 (peer session) moved the inner sheets onto the outer preset with backface culling; watch the outside view for a double tint (inferred in v8, never seen in game: v1-v7 compiled the windows as the opaque lamp material) | Game (owner reports); v28 result open |
| The glass shader source itself is not shipped (only registers and `mtl_blend.fx`); `density` semantics are unknown, so keep `density` 1 and set the tint with `filter` | Retail |
| A ported mod's constant glass maps read under these semantics make the windows near-opaque: the Roamer 105 port kept the Expeditions masters' black colour map at alpha 0.92 (= 92 % opaque film) and a (128, 0, 128) spec (metalness 0.5, occlusion 0.5) on BOTH window sheets, the outer `vehicle_glass_outer` instance and the cab-facing `vehicle_glass_inner` twin (the sheet the driver looks through); a player reported the windscreen "too dark, makes driving impossible". Check every glass instance's film before shipping: RGB about 0.2 at alpha 0.5 or below, a glass spec (Lynx means (8, 41, 216)), filter [127, 155, 151] at density 1 on the outer instance; the inner instance keeps its preset params (reflectance 0.15, no glass block) and only swaps the maps | Game (player report, Roamer 105, 2026-10-01); cause Build (frozen source of package ed0cf96f); fix (32 x 32 constants (51, 51, 51, 115) / (8, 41, 216)) installed 2026-10-13 as package be7cb530 (rollback receipt in the campaign NOTES.md), result Open until the owner drives |
| Verify which instance a mesh uses from the compiled model before editing it: `<model>.tpl.asset/tpl/obj_list.json` `material_info[].maya_name` gives each object's material slot and the `.tpl_markup` material table maps the slot to the `.mi`. Instance names derived from source material names mislead: the Roamer's `roamer105_glass2_glass_mod` ("glass2" + source material "glass") is the lamp covers (`r105_mod_105_lightglass`), not the windscreen; the window mesh `r105_mod_105_glass` uses `roamer105_glass_glass_2_mod`. Hidden proxies export with an empty material (the cut-off volume sources) and are not rendered | Build (Roamer 105 glass campaign attempt 001, 2026-10-13: the lamp-cover instance was changed first) |

Evidence: L275 `art/glass_v8` (manifest with before/after window statistics, generator), the decode script in
the L275 v8 session (scratchpad), shipped `default_materials.pak` presets and `default_non_retail_resources.pak`
shader sources; L275 v8 build-026 / test-027 (336 static checks).
Roamer 105 window glass: `port_roamer105/campaign/glass_20261013_01` (tools/glass_fit.py `check_bindings`; package_audit.json proves
only the two window sheet instances and the two new textures differ from the installed winch-fit package, that no texture was
dropped and no instance links a missing texture; validation.json; NOTES.md; history/attempt_001_lamp_glass_misassigned).
A shared glass-film texture check is deferred until a drive confirms the convention fixes the report.


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

## Supplied PBR art from a model store (WALL-E, 2026-10-04)

**Build:** a store download (OBJ + 2048 px albedo / metallic / roughness / AO / normal per set, plus an
emissive and an opacity map) converts without baking: colour as `MD`; `_spec` = R metallic, G roughness,
B AO straight from the three grey maps; `_nm` after measuring the convention (all four "DirectX" maps
were OpenGL, correlation -0.12 to -0.29 at 0 and 1.5 px blur; `roadcraft.normal_maps`); `_em` (usage `MEM`,
as the Lynx sample) from the emissive map; glass colour with the opacity map in alpha (`MD+MT`,
1024 px). Decoding the compiled `.pct` back (`TextureConverter.exe X.pct X.tga`) matched the sources to
under one level on average, same orientation. A lit overlay (`vehicle_lights`) can reuse the body atlas
as `texDiff` with the emissive map as `emissiveTex` when the emissive map is dark everywhere else
(WALL-E's solar-charge display: 0.1 % of the atlas). Game look not yet reported. Evidence: WALL-E project
`tools/build_textures.py`, `reports/textures.json`.

## Multi-set texturing of an existing vehicle (CAT 793D RC33, 2026-10-08)

| Rule | Grade |
|---|---|
| Blender's multi-object `uv.pack_islands` with partial face selections (sync select) packs objects at inconsistent scales (7-60 px/m instead of ~300): pack each texture set's faces as temporary standalone meshes, fully selected, and copy the UVs back | Build |
| Set materials must carry a base-colour image named exactly as the texture resource (`mod_<mod>_setNN`): without it every set shares `sc_grey_100` and each object compiles to ONE material (see build-pipeline "One material per texture") | Build (RC32 obj_list) |
| Weathering that reads as real on a mine truck is subtle: even paint, cavity/ledge/ground-gradient dust, small edge wear. Large grunge maps (Grunge Map 00x, wipe smudges, leaks) and strong curvature wear read as "tiger stripes" / fake | Game-adjacent (owner on renders, with a reference photo) |

Evidence: `RoadCraft/cat793d_detail/tools/uv_unwrap.py`, `tools/painter/sp_build_793.py`, `reports/package_audit_rc33.json`.

## Decals, edge normals and wheel texturing (CAT 793D RC34, 2026-10-08)

- **Projected decals.** Each decal is defined by a ray (origin and direction), an up vector and a size in metres.
  - Cast the ray against the painted triangles, excluding the collision boxes (`cdt_*`) and lit lamp copies
    (`*_on`). The collision boxes otherwise catch the ray.
  - For every triangle that faces the decal, lies near the decal's plane and overlaps its box (use overlap, not a
    triangle-centre test), rasterise the triangle in UV space: texel → barycentric → 3D point → decal (u, v) → image.
  - Write per-set colour and alpha bitmaps and use them as Painter fill + bitmap-mask layers.
  - Check placement in renders first: the first attempts landed on grilles, lamps and hose bundles.
- **Edge normals without a high-poly.** Bake the Blender Bevel shader (about 6 mm) to tangent normals, then bake
  any kept original sculpts selected-to-active over it with `use_clear=False`. Flip green for DirectX. Flatten
  texels with blue below 150, which is garbage from overlapping trims. Import as Painter's normal mesh map.
- **Tyres.**
  - A cylindrical (θ, axial) strip collapses lug walls and the bead into streaks. Weld, then use an angle-based
    unwrap rescaled to metre scale (UV area = 3D area); `smart_project` normalises each object to 0..1.
  - Dual tyres that are translated copies can take the front tyre's UVs face by face (KD-tree on face centres).
  - Draw sidewall text in 3D from each side's viewpoint (a = sign(x)·y, b = z, clockwise arc, letters upright
    outward). A single UV strip reads mirrored on one side.
- **Pak resources.** `.pct.resource` files read from a pak are CRLF; normalise before regex edits. A silent
  non-match left 10 mips listed for an 11-mip texture, and only the package audit caught it.


## Audit shader graphs and retain tiny physical labels (Dump Twuck revision 006, 2026-10-10)

**Build, offline source inspection:** the new-cab README's “simple flat Principled only” description is contradicted by the inspected primary `.blend`. No image textures are present, but cockpit black plastic/dark panels use noise, Voronoi, map-range/mix and bump; leather uses Voronoi/bump; fabric uses wave/noise/mix/bump; several metals have procedural roughness and bump, and yellow paint has BrightContrast. Absence of image nodes does not mean a material can be reproduced by copying a Principled default colour. Inspect connected inputs and bake the actual graph, or explicitly limit a uniform-tile route to finishes verified constant.

The revision 006 body route bakes albedo, packed metal/roughness and tangent normal plus emission onto new packed UVs, retaining source-object/source-loop identity. It reserves a uniform-finish strip for genuinely constant finishes: procedural islands occupy the lower 88%, uniform tiles the top 10%, and each physical label/glyph loop samples its tile centre. This keeps a tiny lettering island from relying on a few filtered atlas pixels without replacing the geometry with painted labels. Normal-green conversion follows the existing game convention.

**Inferred visual cause / authored remedy:** a first cockpit bake made very small text/digits weak; loss from tiny packed islands and filtering was suspected. The strip/constant-UV correction is authored, and the subsequent offline dashboard render was reported readable, but a sealed matched before/after was not retained. Do not claim the filtering cause or a native cure confirmed. Atlas mip/renderer behaviour, glyph face placement and cabin lighting need a compiled cockpit capture. Evidence: Dump Twuck pinned `source/revision_006/generated_authoring_inventory.json`, `tools/model_v6.py:bake_body`, `build/physics.json:atlas`, `reports/preview_v6.json` and offline `preview/v6/dashboard_close.png`.

## Alpha-cut parts (mesh guards, gratings, heat shields) - Kanga 25, 2026-10-10

No retail vehicle material instance or preset exposes an alpha-test switch: the glt base layer has `blendMode`
(`none|blend|add|add_no_alpha`), `allowHashedTransparent`, `transpWriteDepth`, `no_backface_culling` and
`doubleSidedLighting`, and the only "alphakill" preset (`pbr_mesh_decal_alphakill`) is a blended decal
(`root/prebuild/meta_descs/meta_desc.ps`, `material_presets/*.mp`; **SDK/Retail**). The Kanga 25 cut-out set
(cab mesh guard, step gratings, exhaust heat shield) uses `vehicle_body` with `blendMode "blend"`,
`allowHashedTransparent True`, `transpWriteDepth True`, `no_backface_culling True`, `doubleSidedLighting "normal"`,
an `MD+MT` colour texture (alpha = opening mask) and the markup `rendParams.allowHashedTransparent True`.
Two-sided `vehicle_body` instances (`no_backface_culling`, `doubleSidedLighting`) are proven on the Roamer 105;
the hashed-alpha look of the cut-out is **Inferred** until seen in game (kanga25_mod `tools/prepare_textures.py`).

**Game (Kanga c7 owner screenshot), cause Build/asset:** the boom-side "mesh guard" showed as an opaque dark slab,
2 cm larger than the window it covers. Its texture region (the two large squares of the cutout atlas) has alpha 1.00
everywhere, and so has the asset's baked `M_MAC25_Cutout_op.png`: the supplied guard has no openings, only the step
gratings and heat-shield slots do. So this report does not test the hashed-blend setup. Before trusting a supplied
cut-out part, sample its alpha per part (kanga25 c8 scan: gratings 94 % open, guard / pod steps / heat shield 0 %).
c8 drops the guard plate (`WINDOW_GUARD`) so the cab glass shows. Whether `vehicle_body` + `blendMode blend` +
hashed transparency cuts holes in game stays **Open** (watch the rear-frame step gratings).


## Weathering: a flat colour atlas reads as a toy (Dump Twuck v8/v9, 2026-10-11)

**Build; public report; Game pending.** Dump Twuck v6 baked its supplied flat Principled materials
into a colour strip and pointed every face of a flat material at one texel; the procedural parts got
smart-project islands at about 14 px/m. 741 of the body's 1216 m2 therefore had no variation at all,
and a public player called the result "a toy from a shop". Look at the UVs (area per object on single
UV points, UV coverage against 3D area) before blaming the shader.

`weather_v8.py` (Dump Twuck tools) re-unwraps body LOD0 (smart project 60 deg; connected components,
area-balanced, into three quadrants of a 4096 atlas; concave packing; 59 px/m against 14), keeps the
old 2048 atlas pixel for pixel in the fourth quadrant (cockpit, lamps, beacons and glyph objects keep
their finish with UVs scaled into it), and transfers the UVs to LOD1-3 by nearest triangle (BVH from
each LOD face's centre, barycentric per corner, clamped to the source quadrant). Data Transfer
modifiers were far too slow on 130k faces, and reordering modifiers with operators in background mode
looped forever. It bakes on the GPU (OptiX; a 4096 pass takes about 5 s): an AO / bevel-edge mask
first, then albedo and spec (R metal, G roughness, B AO) sampled from the old atlas through the old UVs
plus wear, and a bumped tangent normal (green flipped for DirectX). Wear terms: AO darkening and
crevice grime, chipped paint on bright edges only (black stays black), dust on up-facing faces, mud
below 3.4 m and around the wheels, streaks on vertical faces, an abraded and sand-dusted tub. Name the
bake images apart from the model's own `mod_*` images (a clash gave `.001` file names, and a cleanup
by prefix would have deleted the model's texture links). `weather_wheels_v9.py` does the same for each
right-hand wheel master (2048: tyre in the lower 62%, rim above, packed inside each rectangle with
`pack_islands(udim_source='ORIGINAL_AABB')`; dried mud in the tread grooves, sidewall dust, a bead mud
ring, grimy rims; about 130 px/m); the left variants are rebuilt from the new masters by the v7 tool.
Geometry hashes prove nothing else moved (the beacons' lit shell moved from 1 to 4 mm on purpose).


## Launching the Steam edition of Painter by script (2026-10-11)

**Build:** `Adobe Substance 3D Painter.exe --enable-remote-scripting` started directly exited at once (code 0) and
never opened the endpoint; with `SteamAppId=4329260` and `SteamGameId=4329260` in the environment it started and
listened. Steam must be running.

## Baking real props and fabricated parts into a game atlas (L275 v10, 2026-10-11)

**Build (L275 v10 cargo, `C:\RC\l275_cargo\tools\c30_bake.py`).** Owner bar: "everything to look real, not blocky or
chunky ai generated stuff" (permission given to source models). What worked:
- Generic props from **Poly Haven CC0** glTF scans (the API refuses requests without a `User-Agent`); settle loose items
  with Blender rigid bodies (put each origin at its bounds centre first, or long tools pivot about an end and stand up),
  and slump fabric bags with cloth + pressure.
- Build every fabricated part twice: a **high** build (full detail: bolts, welds, bevels) and a **low** game mesh
  (`fab.LOW`: no fasteners/welds/small bevels, fewer segments); decimate the scans for the low. Bake each low piece
  **selected-to-active against its own high only**: one bake over all highs at once pulled colour from neighbours
  (net cords took the colours of the items under them, frames took the lifting-eye yellow).
- The Cycles **DIFFUSE colour pass is black on metals**: zero Metallic for the colour pass, bake metalness separately
  (emission swap), then restore. The first 4K bake had black aluminium shelves.
- Cost on this PC (RTX 5070 Ti, OptiX): ~20 min for two 4096 atlases, 35 pieces, 5 passes at 16 samples.
Evidence: L275 `art/cargo_v10/manifest.json`, build-032 / test-034. Game look: not yet seen by the owner.

**Clear lamp covers on a shared glass atlas (L275 v11, 2026-10-11; Build; Game report).** Owner screenshot: a solid
pale panel beside the round headlamp ("What happened to the headlight glass mesh"). The outer headlamp lens covers
were authored as clear film on the glass atlas (alpha 0.12, opaque 0.7 rim) but sat in the lamp-parts object with the
opaque `vehicle_body` lamp material, so every build since v1 painted them solid (the same exporter rule as the v8
windows: one material per texture per object). Fix: move them to their own object on the exterior glass preset and
darken their film to the retail clean-glass ~0.2 (a bright 0.85 film at alpha 0.12 still looked milky in review).
When a glass atlas carries both lamp parts and lenses, check each lamp-part island's median alpha: islands under ~0.3
are glass. Evidence: L275 tools/glass.py `lens_islands`, art/glass_v11, build-037 / test-039.
Follow-up (L275 v12, owner in game after v11: "dirty glass on the indicator part of the headlight but nothing in front of
the actual headlight"): a lens that keeps its Painter rim/dust texels, over an opaque dusty insert, reads as dirty glass
next to a clean cap. Make a headlamp unit's covers one uniform clean film and its inserts clean (art/glass_v12).
Follow-up (L275 v13, owner: "a slight layer of dirt, or smudges to show that there is a glass there so it doesnt look too
see through"): perfectly clean lamp glass (alpha 0.12-0.25) reads as no glass in game. v13 adds dust from 3D-position
noise (continuous across UV seams; triangles rasterised to per-texel positions): film + smudges + dirtier lower edge +
faint streaks, alpha p50 ~0.28 (lens) / 0.36 (round lamp glass), p90 <= 0.5; only texels with base alpha < 0.6 change.
Blender's preview glass (transmission) under-shows this; judge in game. art/lens_dust_v13, build-044 / test-045.

## Procedural edge wear on low-poly hard-surface parts: bevel mask, not pointiness (L275 v14, 2026-10-12)

**Build (offline bake):** Blender's `Pointiness` is per-vertex and is interpolated across each face. On low-poly
parts (a bracket plate with only its outline vertices), every vertex is a convex corner, so the whole plate reads as
"edge" and the edge-wear colour, broken up by its noise, covers it as camouflage-like blotches. The close-up renders
showed it on hanger plates and hub faces; the albedo crop at the probed UV confirmed it (`uvprobe` ray-cast from the
review camera -> face UV -> crop of albedo/spec/normal). Use a Bevel-node normal compared with the geometry normal
(`1 - dot(bevel, N)`, radius ~4 mm) as the edge mask; it marks only real edges at any vertex density. Also: a
satin-black roughness noise of +-0.06 at ~2 cm scale shows as specular blotches under an HDRI; keep roughness grain
fine (~400/m) and faint (+-0.025). Evidence: C:/RC/l275_chassis tools/uc_mats.py v3, renders check5/check6.
Review tip: a relative output path given to headless Blender may resolve against a different directory (C:\renders
here), so check the "Saved:" lines before judging a re-render.

## Two-sided vehicle materials (L275 v19, Roamer 105; Build, Game symptom)

`vehicle_body` / `vehicle_lights` material instances accept `no_backface_culling = True` and `doubleSidedLighting` (`"normal"`; the Roamer uses `"none"` on `vehicle_lights`, whose skinned emissive shader has no double-sided-lighting split). The Roamer's whole body uses them because its source meshes have open and inside-out shells. When reusing such art, either carry the params over or repair the shells; check the island orientation (signed volume per connected island) before deciding. Keep the body's `enableLwiLodTransition` False and leave the export vertex-compression block out: both made the engine look for prebuilt shader permutations that two-sided skinned materials do not have (Roamer crash 2026-09-13).

## Cockpit interiors that read blurry (L275 v20, 2026-10-12; Build, owner symptom)

Owner: "The interior is super blurry and looks really low quality". Measured: 0.24 px/mm (one texel per 4 mm) with the
UVs covering a quarter of a 2048 atlas, and the 382k source collapse-decimated to 45k. No retail truck uses the
`PropTruckCockpitHighPoly` route (0 of 201 classes), so the interior must improve inside the body model. What worked:

* Reduce to ~120k (planar dissolve, then collapse) and bake **normals and AO from the full source** onto it: the
  decimation dents vanish.
* Re-pack the UVs: keep the source's artist seams, re-unwrap only islands that are slivers or fill less than 35% of
  their box (hollow rings and thin strips wasted most of the atlas: coverage 12% -> 44%), and weight islands seen
  from the seats (ray casts to driver / passenger eyes) 4x linear. Result: 0.87 px/mm seen, 0.23 hidden on a 4096.
* A re-sampled blurry colour map stays blurry: k-means finishes made hard-edged camouflage out of soft dust blotches.
  Assign the colour per **mesh part x value family** (black / mid / light) from the part's own median, keep only
  small high-contrast features (icons, switches) from the original, then add controlled dust and the new AO.
* Real-scale grain from a baked position map (height -> slope with the position map's texel spacing, so islands of
  any density get the same physical grain), kept under ~4 degrees (p99 3.6).

* **Pad after composing (v21):** the v20 compose zeroed everything outside the islands and the owner saw stair-steps along curved seams. Any numpy step that writes a final map must re-pad it (the bake's own margin is lost once you mask). Islands packed 2.5 px apart also leave no room for padding at lower mips: 6 px at 4096 cost 15% density (0.87 -> 0.74 px/mm seen).

* **Do not collapse what the driver sees (v23).** Owner, after v22: "I hope this quality isnt acceptable" (chewed vent
  rims and panel seams). The 120k collapse was within 0.2 mm (p99) of its source, but a millimetre metric hides shading
  damage: solid-mode renders showed dented rims and a melted airbag emblem, and even the supplied 382k was already a
  reduction (faceted rims). Fix: start from the full-detail source (764k), dissolve only flat regions (0.3 degrees,
  delimited by sharp edges and UV seams), ray-cast each face against eyes at the seats, and collapse only vertices
  that no seen face touches (seen faces, their 1-ring, boundaries and >50 degree creases locked). Result: 363k, with
  every visible face at the source topology; the deviation (p99 5 mm) is confined to hidden faces. Judge reductions by
  solid-shaded close-ups against the source, not by distance.
* **AO bake distance (v23b).** A Cycles AO bake uses the world's AO distance (metres by default); inside a closed cab
  with the body in the scene it baked the whole interior ~black (median 0.01). The `_spec` blue channel is AO for the
  engine: the owner saw black blotches over the wheel, dash and gear knob, while the gauge plate (blue 255) stayed
  clean (Game). v23b set a 6 cm distance and the blotches turned grey but stayed (owner screenshots): the real cause
  was a second copy of the interior (the colour-bake source) left renderable on the same surface, a fraction of a
  millimetre off, which occluded the AO in hard-edged facets (14% of texels 0, square two-tone "digital camo" in game).
  Hide every non-source mesh from render during AO bakes; render the raw AO channel on the mesh before shipping.
  Corrected 2026-10-12: the engine is not adding a dirt layer here; the pattern is in our map.
* **Never re-sample your own output as the colour source.** Each rebuild baked colour from the previous build's
  albedo, which already had AO multiplied in: every generation darkened again. Bake from the original supplied maps on
  the mesh their UVs belong to (render it textured first to prove the fit).
* **Strip rules written as tri limits break when the source density changes.** A dial-internals rule (<= 700 tris
  in a box) scaled up for the denser source also deleted the cluster backplate (1344 tris). Re-check the stripped
  list against the previous run, and the area left on the surface being fitted, whenever the source changes.

Workspace C:/RC/l275_interior (r10_interior.py, r12_partmap.py, r20_compose.py, r21_clean_albedo.py, r61_compare.py
side-by-side solid renders); mod `tools/interior_v20.py`, `art/interior_v20`. Not yet seen in game.
