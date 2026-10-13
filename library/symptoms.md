# Symptoms: what you see in the game, and why

Look up the symptom; the cause and the fix follow, with the article that has the detail. `lint-bro`
codes are given where the checker catches it before the game does.

When something *stops working* in the game, read the script crash dumps first:
`%LOCALAPPDATA%\Saber\<game folder>\client\ssl_crash_dump\*.ssldmp` (JSON: call stack and object
graph; the folder was `RoadCraft PTS` on the install where it was found). The loader's and the
grader's dead controls were traced there (Game).

| Symptom in the game | Cause | Fix | Grade | More |
|---|---|---|---|---|
| Steering turns the wheels instantly; pedals are all-or-nothing | `maxSteerSpeed`, `backSteerSpeed`, `pedalsResponsiveness` unset: the SDK default of each is 1 | Set them (retail scouts: 0.03, 0.06, 0.35). `RC002` | Game (Warthog), SDK | truck-settings.md |
| Wheels stay on the ground with the body a metre or two in the air; the body rests on its lowest point | `suspensionCollection` without `useSuspensionCollection = True`: the generator drops the whole collection and every axle falls back to min 0 / max 1 m / strength 0 | Set the flag. `RC001`, `RC030` | Game (Warthog), Build | suspension-and-wheels.md |
| Vehicle sits on its bump stops, wheels pushed up into the arches | `height` taken for the rest position; it is the spring's neutral offset, so the vehicle sinks by the whole static sag | height = design sag (+ lift); use `roadcraft suspension`. `RC004`, `RC005` | Game (buggy), Inferred model | suspension-and-wheels.md |
| Belly scrapes; "feels like a collision mesh underneath" | Low ground clearance for the bump travel: soft springs let the body bottom out; convex collision hulls reach the lowest part in their section | Raise the rest (lift), limit bump travel so clearance remains at full compression, floor the hulls above small low parts | Game (buggy) | suspension-and-wheels.md, frames.md |
| Tracked vehicle "like there isn't anything underneath it": lifts one side, gets pushed around, tilts in pivot turns | Only fakes on the ground (the real idler and sprocket are raised) on light track frames: in pivot turns one track sinks or lifts and the hull rolls 3-4 deg | Retail EPEC layout (rigid real wheels at each track end at ground level beside the soft fakes) plus track frames of retail mass (7.5 t). Springs on frame-hung wheels come out far softer than the vehicle-mass formula. `RC046`, `RC047`, `RC005` warn | Game (KGS25 editor bench), Retail survey | tracked-vehicles.md |
| A crawler bounces or wobbles, and parks with a lean, after its support wheels were given springs | Springs on wheels hung on light track frames come out 25-40 times softer than the vehicle-mass formula predicts (seemingly scaled by the frame's mass). **Superseded 2026-10-13** (code analysis, static: `C:\RC_RE\research\physics_semantics.md`, T4/F3): the 25-40x figure came from a frozen bench run and code shows no mass scaling; the cause of the bounce is not established | Do not size them from the vehicle mass: the retail EPEC layout with heavy frames (tracked-vehicles.md recipe), measured on the bench. `RC048` notes it | Game (KGS-25 fix 1, owner: "it does it worse now"; bench: parked at 2.8 deg roll) | tracked-vehicles.md, physics-bench.md |
| A vehicle will not move: the engine runs and shifts into first, rpm sits at idle + pedal x 250, no wheel turns, even downhill | Gear `angularVelocity` scaled far above stock (WALL-E: the Karelian's x 4.9 for small wheels); more torque (x 20) did not help | Keep stock-range angular velocities and accept lower speeds on small wheels; read gear, rpm and wheel spin with the bench probe (lines G and W) | Game (WALL-E editor bench) | truck-settings.md |
| A tracked vehicle's belt shakes at rest though the hull is still | Hidden physics wheels almost on a visible wheel's circle (the belt is drawn round both and swaps between them), or a third rigid ground wheel between rigid end wheels | Make the visible end wheels the real wheels (their own models), keep hidden wheels clear of visible circles, and put nothing rigid between rigid end wheels | Game (WALL-E: owner watching the bench; wheel jitter in the bench data) | tracked-vehicles.md |
| A small vehicle bounces, spins its wheels, digs a hole and rolls over by itself | Too light for the engine's contact and torque model (122 kg on 1.5 kg wheels; stock wheels weigh 120-450 kg) | Raise the mass (WALL-E: 1200 kg body, 40-60 kg wheels, torque 14,000, `maxDeltaAngVel` 0.002), stock digging factors (`terrainDeformationFactor` 0.35-0.5) | Game (WALL-E bench) | truck-settings.md |
| A vehicle with two wheel sizes rests nose- or tail-down on a flat pad | Soft contact (`isSoftContactEnabled`, default on) sinks a small wheel further than a big one | Hard contact on those wheels, or a stiffer `softForceScale` on the small one (4x launched WALL-E) | Game (WALL-E bench) | tracked-vehicles.md |
| A small crawler ploughs ahead instead of pivoting | `sidewaysFrictionMaxVelocity` (default 1 m/s) is the lateral speed where the low sideways friction starts; a small vehicle's pivot slides far slower, so it keeps full grip | 0.1 m/s on WALL-E (pivots 10-28 -> 51-67 deg); much lower made the turns erratic | Game (WALL-E bench) | tracked-vehicles.md |
| A crawler judders, a stick-slip lurch at about 1 Hz, in full-lock pivot turns | Not known: KGS-25 candidate 03 and fix 2 both do it at pedal 0.6 | None yet; bench a retail crawler with `--schedule harsh` to see whether the engine's own do it | Open | tracked-vehicles.md |
| Suspension arms, springs, hubs do not move with the wheels at all | Wheel slot joints only move under `axleControllerSettings` (`independentAxleSettings` / `axleSettings`); chains pinned to an unmoved slot never move | Add the axle controller for every slot the rig pins to. `RC010`, `RC031` | Game (Warthog, buggy), Retail | suspension-and-wheels.md |
| Brake discs / inner wheel faces show outward on one side | Asset handedness disagrees with the final native rim/object frame; slot orientation alone is insufficient | Measure native slot, actor and rim axes before mirroring. Lada left rim has an extra half-turn and needs the same right-facing master as the right | Game (buggy symptom; Lada frame measurement), Build (Lada remedy) | suspension-and-wheels.md |
| Directional tread looks right on one side and backwards on the other | A mirrored tread variant on one side: the engine already mirrors left-slot wheels, so the variant reverses that side's rolling direction | Use one tread master on every slot; reflect it fore-aft (Y) only to reverse all six | Game (Dump Twuck v9 owner drive) | suspension-and-wheels.md |
| Plate or sticker text reads backwards, or the steering wheel is on the wrong side, on art recovered from a SnowRunner mod | The SnowRunner importer mirrors the whole truck left/right | Undo the mirror in the source-to-RoadCraft transform (determinant -1), then flip the winding and reorder the custom corner normals; check a plate in a render first | Build (Watcher 61) | snowrunner-ports.md |
| Knuckles or arm ends thrown outside the wheels on one side | Parts parented under a wheel slot, or pinned to it with offsets, while no axle controller or steering rack drives it | Use the retail pattern: axle controller + steering rack; see the rig recipe | Game (buggy) | suspension-and-wheels.md, ik-visual-rigs.md |
| Joint rotates the wrong way / about the wrong axis | Hinge axis from `childRotation` misunderstood: it turns the constraint's Z onto the hinge axis in the bone frame | `roadcraft.vehicle.child_rotation(axis)`; check with an export audit | Build, editor readouts | frames.md |
| Links or rods gap at their pins as the suspension moves | A rigid link cannot close the loop that the wheel travel asks for | Let the link telescope (two halves with a `PRISMATIC` terminal) or reduce the travel; bones at the pins, X along base -> tip, slide range covering the stroke | Game (Roamer 105, editor play mode: 36 mm gaps, under 5 mm once telescoping) | ik-visual-rigs.md |
| A tool stops before its cylinders are fully extended or retracted | The joint's limits are narrower than the modelled cylinders' stroke | Set the limits from the stroke (pin-to-pin lengths at both ends) | Game (16M3 grader: "raise up to the blade lift cylinders full extraction") | ik-visual-rigs.md |
| Lamps dark in the campaign (fine in the editor) | Deprecated `BlueprintLibraryChangematerial`; lens meshes with `_lp_` names or glass presets; no headlight key in retail | Lit `_on` copies with a `vehicle_lights` material, swapped by show/hide nodes on the engine events | Game (CAT 793D, buggy) | cockpit-and-lamps.md |
| Cab glass looks opaque, like painted panels | Windows and opaque parts share a texture in one object: the exporter keeps one material per texture in an object, and the opaque one won (`obj_list.json` `material_info`) | Give the glass its own object (or texture); guard against mixed presets on one texture at the model stage | Build (obj_list); Game (L275 v7 owner) | build-pipeline.md |
| A flashing lamp's whole lens appears and disappears | v6/v7 L275 beacon: coincident unlit / lit dome objects swapped from two schedule nodes; the mechanism is not established | Never switch the unlit lens: flash only a lit shell over it from a tick-timer pair (CAT 793D strobes) | Game (symptom); fix Build | cockpit-and-lamps.md |
| Brake / reverse lamps never light | Native `prop_vehicle_lights_material` brake/reverse path did not work in the campaign | Drive them with show/hide on brake / reverse events | Game (cause, CAT 793D RC20); the fix is Build (RC21, not yet confirmed) | cockpit-and-lamps.md |
| Gauge needles rest at mid-scale | Needles modelled pointing up; the dashboard rotates from the modelled pose | Turn the needle meshes to the zero mark in the build | Build (buggy); direction awaits a drive | cockpit-and-lamps.md |
| Garage "deploy" does nothing (you can leave the screen and then get in); afterwards the game will not save | A cargo bed (`prop_cargo_constraint`, CONSTRAINT_CARGO action, CargoConstraintSavablePropDesc) synced into a generated class without `TruckCargoConstraintUnit` in `auto_<truck>_replicated.sso`: the input controller's `cargoConstraint` is null and the HUD crashes in `PlayerInputTruckController.GetToggleableActionReactive(30)` from `HandleOnCurrentTruckChanged` (script dump) | Add `TruckCargoConstraintUnit = { }` to the replicated entity (retail: all 42 trucks with the class block carry it, none without); sync it wherever the cargo bed is synced | Game (L275 v10-v15 owner report, dump 2026-10-12); retail survey; fix Build | truck-settings.md "Cargo beds and tie-downs" |
| Parts of an accessory reused from another mod are see-through from some angles | The source mod rendered open / inside-out shells with a two-sided material (`no_backface_culling = True`, `doubleSidedLighting = "normal"` in its `.mi`); the copy got a plain single-sided `vehicle_body`, so those faces are culled (Roamer ARB bar on the L275: 82 of 306 islands, ~3k faces, negative or open) | Carry the source's two-sided params into the new material instance, or fix the shells. Two-sided skinned materials crashed the Roamer with LOD crossfade or vertex compression on: keep both off | Game (L275 v18 owner screenshot); fix Build (v19) | textures-and-materials.md |
| Interior "super blurry", low quality in the cockpit | Texel density far below the view distance (L275: 0.24 px/mm, UVs on 25% of a 2048) and a collapse-decimated interior (smeared shading) | Re-pack visibility-weighted UVs on a 4096, bake normals/AO from the full source, clean colour per part (not by colour clusters) | Game (owner report), fix Build (L275 v20) | textures-and-materials.md "Cockpit interiors" |
| Stair-stepped / "pinching, aliasing" lines along curved edges of a re-textured part | Texels outside the UV islands were left black (albedo) or flat (normal) by a numpy compose step, discarding the bake margin: bilinear filtering and mips pull them into every diagonal seam | Pad every map outward from the islands (dilate, then push-pull fill) after composing; give islands a 6+ px margin at 4096; mask-normalise blurs used near seams | Game (L275 v20 owner screenshot); fix Build (v21) | textures-and-materials.md "Cockpit interiors" |
| A seam flickers like two meshes intersecting (L275 toolbox rear edge) | Exact duplicate faces (identical vertices, same facing) in the source mesh; invisible while both copies shared material and UVs, flicker once a material / texture split puts them on different texels | Scan each mesh for same-facing exact-duplicate face groups and keep one (prefer the outer material); leave opposite-facing pairs (two-sided sheets). Also lift up-facing faces lying exactly in another mesh's plane (deck) by ~1.5 mm | Game (owner, L275 v41), Build diagnosis | - |
| Mud / dust covers the cab interior while driving | In-cab materials on `vehicle_body` receive the vehicle mud `covering` | Put in-cab instances on the retail `vehicle_cabin` preset (covering forceDisable); cabin twins for textures shared with exterior parts | Game (owner report L275 v30), fix Build v31 | textures-and-materials.md "Cab presets and the mud covering" |
| Mud on the instrument cluster / door-top paint after the cab fix | Lit cluster copy on `vehicle_lights` (covering on); in-cab painted body faces still on `vehicle_body` | `params.covering.forceDisable` on in-cab lit instances; in-cab body faces split to a `vehicle_cabin` twin object | Game (owner report L275 v31), fix Build v32 | textures-and-materials.md "Cab presets and the mud covering" |
| A new lamp lens draws as an opaque black disc | Its glass albedo was compiled without alpha (usage MD instead of MD+MT); the film's alpha is the opacity | Compile every glass / lens albedo with `MD+MT` (check `reports/textures.json` usage) | Game (owner screenshot, L275 v33), fix Build v33b | textures-and-materials.md |
| A BRO engine / gearbox change never reaches the game | The project patches its generated class instead of regenerating it, so `prop_truck_rb` keeps the old torque and gears | Write the drivetrain into the compiled class too (L275 `patch_compiled_features.patch_drive`), then confirm with `roadcraft physics report` / `compare` on the built pak | Build (L275 v34: the test caught torque 85000 in the class) |
| The game loads forever after a mod update | A savable prop gained state the existing save lacks: the L275 v35 added a `constraintSequentialChains` 'Toolboxes' chain, and `PropTruckConstraintView.RestoreFromSave` -> `dict.Get('Toolboxes')` crashed on the old save | Read `%LOCALAPPDATA%/Saber/RoadCraft*/client/ssl_crash_dump/*.ssldmp` (JSON callstack); roll back with `roadcraft rollback --receipt`; a change to savable state must load a save made before it. Fix (Build, L275 v35b): `PropSavableObject.SetSavedProps` only loads saved descs whose type the class still lists (`prop_savable_object.ssc` l.50), so drop `TruckConstraintsSavablePropDesc` from `prop_savable_object.savablePropDescs` (state is then not saved), and never re-add it while the chain exists | Game (owner, L275 v35, 2026-10-13); fix Build v35b, not yet loaded |
| Windows invisible from inside the cab | Every glass preset tried forces covering off and the cab-side sheet reads as clear (inner preset, inner + tint, outer culled) | Try `vehicle_interior_glass` on the cab-facing sheets (L275 v31; result open) | Game (owner, L275 v22-v30) | textures-and-materials.md |
| Windscreen too dark to see through, "makes driving impossible" (player) | The source mod's constant glass maps were ported unchanged on both window sheets: a black colour map at alpha 0.92 is a 92 % opaque film here (alpha = opacity), on the outer instance and on the cab-facing `vehicle_glass_inner` twin the driver looks through; the half-metal spec darkens it further | Find the sheets' instances from the compiled model's object list (not from instance names), then author the retail clean-glass film (RGB about 0.2 at alpha 0.5 or below) and a glass spec (Lynx (8, 41, 216)) on both; filter [127, 155, 151] at density 1 on the outer instance only | Game (player report, Roamer 105, 2026-10-01); cause Build; fix installed 2026-10-13 (be7cb530), owner drive pending | textures-and-materials.md "Glass film convention" |
| Black or grey square "camo" blotches over a cockpit (wheel, dash, roof lining) in game, faint in lit Blender renders | The `_spec` blue channel (AO) is broken: a coincident copy of the mesh (here the colour-bake source) left renderable occluded the AO bake in hard-edged facets; the world's default AO distance had also darkened it all (L275 v20-v23b) | Hide every other copy from render during the AO bake, use a contact distance (~6 cm), and render the raw AO channel unlit on the mesh before shipping | Game (owner screenshots v22, v23b), cause Build | textures-and-materials.md "Cockpit interiors that read blurry" |
| Cockpit vent rims / panel seams look wavy or chewed, emblems melted | The interior was collapse-decimated (even within 0.2 mm of its source the shading is damaged) or the supplied source was already a reduction | Rebuild from the full-detail source: flat-region dissolve plus a collapse limited to faces hidden from the seats; compare solid-shaded close-ups with the source | Build (L275 v23) | textures-and-materials.md "Cockpit interiors that read blurry" |
| First person sits in the passenger seat / looks down on the cluster hood | Source cab of the other hand of drive, and/or the cockpit camera locator placed ahead of the steering wheel | Compare wheel and camera x; mirror the interior to the vehicle's hand; put the eye ~0.4 m behind the wheel | Build (L275 v22 audit) | cockpit-and-lamps.md "Finishing a supplied cockpit" |
| Vehicle bought under an older build is dead / controls do nothing | A controllable joint was added or renamed; saved vehicles keep the old joint set and the script crashes (`dict.Get("level")`, `SetConstraintTarget("blade_lift")` in the dumps) | Keep joint names stable; sell and buy again after such a change | Game (loader, grader) | truck-settings.md |
| The truck does not move, or drives on one axle only | `torqueType` wrong: `full` wheels are driven only with all-wheel drive engaged, and `default` is not a value | `defaults` on the always-driven axle, `full` on the switchable one | Game (Roamer 105, editor play mode) | truck-settings.md |
| Stays in first gear at a low top speed | Gear table from a vehicle with bigger wheels: a gear's road speed scales with the wheel radius | Scale every gear's `angularVelocity` by the radius ratio | Game (Roamer 105, editor play mode) | truck-settings.md |
| Slows down hard mid-acceleration, "between gear changes" | Donor gear table not scaled for smaller wheels and a gap between gear bands (2nd to 20 km/h, 3rd from 22): 2nd topped out at 22, the box dropped 2 -> 1 at 21 km/h and lost 6 km/h | Scale every forward gear's `angularVelocity` by the radius ratio (and the speed stretch) and keep the bands continuous; check with a full-throttle trace of `GetGear()` | Game (Kanga 25, editor bench vs retail Baikal) | truck-settings.md |
| Rolls back when the brake is released on a slope after a stop | `neutralGearSwitchingDelay` dropped the gearbox to neutral while stopped | Raise it (60 held the Roamer in gear) | Game (Roamer 105, editor play mode) | truck-settings.md |
| After a full stop (even on the handbrake) the truck first carries on in its old direction; "it keeps driving backwards" | `neutralGearSwitchingDelay` 60 (the Roamer rollback fix above) keeps the old gear for a minute at a standstill; the Dump Twuck also reversed at 33 km/h at full pedal | Retail values: 0.5 s (Baikal 65206), 0-3 s elsewhere, with the handbrake for slopes; slow the reverse gear. `RC049` | Inferred (two public Dump Twuck reports on the 60 s build; retail values; v5 bench reverse trace); fix not yet driven | truck-settings.md "Heavy hauler drive" |
| A big truck is "slow and gets stuck even in a little mud and on rocks" | Drive force per kg far below retail heavy trucks (Dump Twuck v5/v6: torque / (wheel radius x gross mass) = 1.9 against the retail Baikal 65206's 6.25 loaded), scout tyre friction (mud 2.5 vs the Baikal's 4), rear drive only | Scale torque from a retail heavy truck's force per kg; copy its tyre friction table; all-wheel drive | Inferred (public reports, retail data); fix not yet driven | truck-settings.md "Heavy hauler drive" |
| The vehicle looks "like a toy from a shop": flat plastic colours | Flat-colour materials baked to single texels of a colour strip (Dump Twuck v6: 61% of the body area had no variation; the rest about 14 px/m) | Unwrap the large surfaces and bake AO, edge wear, dust and mud into the atlas (Dump Twuck `weather_v8.py`) | Build; public report | textures-and-materials.md "Weathering" |
| Shallow puddles raise the high-water / engine warning | No `propUnderwaterSettings` position: `prop_truck_under_water_cheker.ssc` then tests the truck origin (ground level for a model built on the ground), so any water depth floods the "engine". It warns when the water is within `warningLevel` ("offset down from drowning point") of the point and floods after `floodTime` once the point is submerged | `chekerAttachBody` + `rootOffsetPosition` at the engine bay (Dump Twuck v9: 4.85 m up, ahead of the front axle; retail Baikal 1.2 m on its front body); `warningLevel` 0.75 | SDK script (cause); author report; fix not yet driven | truck-settings.md "Heavy hauler drive" |
| Turn-signal lenses glow all the time | They were given a light role; the lights material groups follow the engine running | No light role for indicators | Game (Roamer 105, editor play mode) | cockpit-and-lamps.md |
| Every session crashes at scene load after a model change | A material needs a shader permutation the game does not ship (LOD crossfade + vertex compression on a skinned, double-sided material); the editor cannot compile shaders | Turn LOD crossfade off (retail trucks have none) and drop the export compression block | Game (Roamer 105, editor play mode) | textures-and-materials.md |
| The engine asserts at scene load right after class generation | The editor hot-reloads freshly generated classes | Start a run no sooner than about three minutes after generation | Build (Roamer 105) | build-pipeline.md |
| The vehicle rides higher and stiffer than designed | beta nearer the measured 105 than the retail 58, or the wheels rest on their top stops (next row) | Calibrate (`roadcraft suspension --calibrate --geometry measured`) and scale `strength` | Open (predicted for the buggy and the Warthog) | suspension-and-wheels.md |
| Wheels sit at spring travel 0 (on their top stops); the vehicle stands higher than designed and rides harsh | Limits from the earlier design formula (min = lift - bump): the engine puts the stops at `height + min` and `height + max`, so with bump < height the top stop lies above the designed rest | Redesign with `roadcraft suspension --geometry measured` (min = -(sag + bump), max = droop - sag) and check with `native_suspension.rest_report` | Game (Lada v2 front at travel 0.0006; stop geometry measured on the KGS-25 bench); the design rule Inferred | suspension-and-wheels.md "Stop geometry" |
| Model is 2.5 times too large or lies on its side | FBX in centimetres tagged as inches; FBX axes differ | Scale 0.3937 (0.01 / 0.0254) and rotate into the truck frame; measure the tyres | Build (buggy) | frames.md |
| Wheels 2-3 cm low or high against the rig | Skinned source taken from raw vertices, not the armature's rest pose | Evaluate the mesh through its armature | Build (buggy) | frames.md |
| Textures blurry at distance / shimmer | Converter template with few mips | Use a texture descriptor template with the full chain (checked by the build) | Build (loader) | textures-and-materials.md |
| Class generation fails with `ModelDisallowedTypeException` | Race in the batch generator's class database refresh | Retry with the previous generated files left in place (up to five times; each retry gets further) | Build | build-pipeline.md |
| tplexp: `Object with vertices with zero weight` though every vertex looks weighted | A copied mesh kept its vertex group (Blender 3+ stores the names on the mesh); skinning again made `<bone>.001`, which the armature does not know | Clear vertex groups before skinning; audit one group per mesh, weight 1, no loose vertices | Build (WALL-E; L275 had another cause) | build-pipeline.md |
| A 960 x 640 vehicle icon shows squashed or cropped | The icon `.td` kept a non-zero `mipmap_level`; the converter cut the width to a power of two (512 x 640) | `mipmap_level = 0`, check `sx`/`sy` in the `.pct.resource` | Build (KGS-25's shipped icon) | textures-and-materials.md |
| Packaging fails on `res://td/<name>.tga.td.resource` | The exporter links textures by Blender image name, and the image is not named as the resource | Name every image exactly as its texture resource | Build (16M3 grader) | textures-and-materials.md |
| Packaging fails on a shipped material or resource | `mod_pak_builder` resolves references only inside the mod project | Copy the shipped resource into the mod under a mod name | Build (Roamer 105) | build-pipeline.md |
| The SDK exporter never finishes | A mesh without a UV map | Give every mesh a UV map; the builds refuse to export without one | Build (EX5600) | build-pipeline.md |
| Blender: "Cannot change old file (file saved with @)" | A stale `<file>.blend@` blocked the rename after saving (OneDrive sync is a suspect) | Delete the stale file and save again, with retries | Build (Roamer 105) | build-pipeline.md |

## Follow-up: Apoc buggy, 2026-09-30

For partial motion (some suspension pieces move but detach; others stay still), an axle
controller presence check is insufficient. Check whether fixed-length arms can reach all
wheel positions, whether visible uprights follow the same joints the arm chains solve, and
whether meshes have weights on the terminal slider as well as the hinge. The Apoc follow-up
found faults in these checks after its controller had already been added (**Game** report,
**Build** diagnosis). Candidate motion remains to be verified in the game.

The belly-scraping row above records an earlier hypothesis, not an isolated cause. In the
Apoc follow-up, the rear convex hull demonstrably filled open space beneath the engine and
frame. Inspect the actual exported collision and its underside before increasing ride height
again. The repair decomposes the rear while retaining the suspension tune; contact behavior
still awaits a drive. See `ik-visual-rigs.md` and `case-studies.md`.

## Apoc buggy still feels stiff after the linkage repair (2026-09-30)

The owner reported that the suspension still felt stiff after `apb-link-clearance-20260930`
and requested softer springs, more flex and smaller body CDT (**Game** report). That build
retained the old spring settings; an attachment repair is not evidence of soft handling.
The next candidate reduces spring strength/damping, increases usable travel and shrinks the
collision core. Check both compiled main/preview suspension arrays, link reach at the new
stops and exported collision clearance. Drive acceptance remains **Open**.

## A wide mud patch under the Apoc buggy's rear (2026-09-30)

After the soft-flex/CDT repair the owner still saw a wide mud-deformation patch underneath
the rear, without a matching visible part (**Game**). Physical CDT inspection alone missed
separate body VFX volumes. Two copied donor boxes enabled mud (systems bit 16) and reached
2.354 m and 2.0925 m below the buggy's identity chassis frame (**SDK**, **Build**).
Inspect `propVFX.vfxSkeleton.vfxBones` in the BRO and `vfx` in the packaged class as well as
collision. These misplaced volumes match the reported location; runtime resolution remains
**Open**. The next candidate fits environment boxes to the compact body and retains wheel mud.

## Rapid wheel chatter with a fairly level body (Apoc, 2026-09-30)

The owner described shopping-trolley-like rapid wheel bouncing over some terrain and
clarified that mostly the wheels chatter while the body stays fairly level (**Game**).
The installed mud-proxy candidate retained 0.085 suspension damping from the soft-flex
tune. That is below comparable retail scouts: Don 71 0.15, Armiger scout 0.16, Minuteman
scout 0.20 (**Retail**). Insufficient wheel damping is a working diagnosis (**Inferred**),
not established by the earlier static rest/rig checks. Trial 0.16 front / 0.18 rear while
keeping the soft springs, ride height and travel, then repeat the same terrain drive.

## Springs look like two sliding meshes (Apoc, 2026-09-30)

The owner reported that the coil-over springs appear as two meshes moving up and down,
rather than a spring compressing (**Game**). The previous overlapping, rigid spring halves
only prevented a gap; they did not deform the winding pitch. The mixed-source-weight
classifier also mistakenly treated the exposed piston as a spring (**Build**).

The replacement separates the narrow piston from the outer winding, creates one connected
round-wire helix per corner and LOD, and blends each complete wire section between the
existing spring endpoint bones. End turns remain with their seats; the active turns change
pitch continuously. Validate exported weights and mesh connectivity, seat attachment,
wire thickness and turn clearance through travel (**Build**). Native runtime appearance
still requires a drive (**Open**). This report does not accept the preceding damping tune.

## Wheel jitter persists after a damping-only change (Apoc, 2026-09-30)

The owner reports that the wheels still jitter and the buggy does not feel like a vehicle
after `apb-coil-animation-20260930`; throttle dependence is unknown (**Game**). That candidate
retained the damping trial's physics, so 0.16/0.18 damping is not a confirmed remedy. Check
the compiled wheel classes as well as suspension arrays. Normalized wheel BRO dimensions
can conceal absolute contact offsets, inertia choices and native-only options (**Build**).

The comprehensive audit found 35 kg wheels, an unchanged donor radiusOffset of 0.085 on
0.398/0.416 m tyres, and greater engine torque per body mass and tyre radius than the stock
Armiger. These are verified differences, not an isolated cause of jitter. A balanced
candidate and native visual stabilization are a trial (**Inferred**, runtime **Open**).

**Candidate cause from the measured stop geometry (2026-10-02, Inferred):** with the stops at
`height + min` and `height + max` (suspension-and-wheels.md "Stop geometry"), the soft-flex axles
(min -0.18, max 0.40, height 0.36, strength 0.0126 front / 0.0182 rear) put the top stop 0.18 m
below the modelled place. With even wheel shares the front springs would rest above that stop at
every beta from 34.8 to 105, the rear at beta 58 and below, so the wheels ride on their top stops:
a rigid contact that fits both "stiff" and wheels chattering under a level body. Before another
tune, read the wheels' spring travel (0 means on the top stop; `series_probe.ps1` or
`roadcraft bench`), or redesign with `roadcraft suspension --geometry measured`.


## Deformable wheel startup failure / no suspension reserve (Lada, 2026-09-30)

**Game:** `failed to find deforming geom obj with name 'tire'` at
`truck_wheel_prop.cpp:527` means a required wheel geometry object is absent.
Split the source tyre and rim, name them `tire_LOD0` / `rim_LOD0` and import
again. The `vehicle_tire_material` assignment alone does not supply that name.
Lada v1 failed; v2 spawned and drove after this correction.

**Game:** front spring travel within 2 mm of zero at rest exposed an extension
limit despite a passing static report. Native wheel bounds must be reversed
when compared with positive body-lift estimates; see the suspension article.
Lada's tested -0.22/+0.12 range restored roughly 9 cm front reserve without
changing spring strength/damping. Do not infer this from a level body alone.


## Stationary wheel shake above worked ruts (Lada, 2026-09-30)

**Game report:** Owner reports stationary front-wheel oscillation and apparent floating above dozer-cut ruts in Lada v3 (`cd79217eâ€¦`); see `revisions/rut_contact_v4/feedback.json` and supplied image. The earlier flat-pad/ramp pass did not validate this terrain. The fresh stone-terrain baseline rests without visible sample-to-sample movement, which does not reproduce the fault. Check physical and visual wheel positions, terrain material/extrusion, droop reserve, body CDT and VFX volumes. High-speed visual stabilization cannot establish a stationary contact fix. V4 wheel mass/damping/soft-force and tyre-deformation changes remain a coordinated handling trial until matched terrain evidence or owner feedback supports a cure; do not label the screenshot as proof of a specific force/collision cause.

### Compact scout makes huge ruts or leaves the donor's tyre pattern

Lada v4 owner report, 2026-09-30: driving/contact much better, but heavy-looking
ruts and oversized incorrect tracks. Inspect terrain-deformation coefficients
and VFX cylinders separately from mass, and inspect BOTH trail descriptors.
Mod initialization can reset the authored trail if defaultTrailSfxDesc is absent.
Check TRAIL_DIFF texture aspect: renaming normal/height/mask maps alone does not
set repeat. V6 source-tread bake, 18.1 cm contact mask and smaller relief pass
compiled checks while v4 handling remains unchanged. Native editor movement and
effects passed, but zero-extrusion fixture samples do not validate reduced
campaign rut depth. Evidence: v5 owner_feedback, build-007/test-008, v6
effects_result; shared native_trails helper. Exact campaign terrain remains open.

### An exhaust effect starts but no plume appears at the tailpipe

**Game (Lada v5/v6 native editor):** stock parent-area emission plus a fitted
hidden face did not establish visible smoke. V6's fitted point locator, directed
small flow and disabled second large emitter produced a visible tailpipe plume.
The root amountScale getter still read zero: use captures and child-emitter
state before inferring suppression. See cockpit-and-lamps for the tested scope.

### Compiled hidden-effect geometry crashes when Play loads markup

**Game (Lada v5):** unresolved `invisible` visibility brand with absent dependency
crashed in native scene TPL markup. Inline concrete visibility flags restored
startup in an isolated trial; v6 source and package audit include that fix.
Do not claim every visibility brand is invalid. A printed automation ready marker
after a crash is insufficient: confirm the live truck identity and simulation
response. Evidence: preserved native_diagnostic_result and v6 effects_result.

## Scout has sockets/scanners but no usable utility controls (Lada v7)

**Build/Game, 2026-09-30:** v6's source-defined winch/sockets survived generation,
but its action mapper lacked attach/pull/detach, scanner and exploration actions;
objective radius was also absent. Add the native named/axis action mappings and
the actual enabled utility settings together, then inspect compiled gameplay CLS.
The shared opt-in native_utilities report catches this component/control mismatch;
Lada v7 wires it into validation. Native pulls and both scan effects passed.
See truck-settings and the v7 utilities_result for scope and evidence pins.

## Explorer radar refuses a funded scan in an editor fixture

**Game, isolated editor (Lada v7):** the scene-placed radar cached an empty
`levelName` in Init before GameSession adopted niva_drive. The profile query for
the current test level showed one token, but the controller looked in its cached
empty-level balance and refused. Read the cached field before diagnosing the
vehicle settings. A fresh Lada spawned after level initialization cached the
correct name, consumed the token and completed the scan. The original failures
remain preserved; no package change or private-field override was needed.
This is an editor fixture ordering finding, not evidence of a retail radar bug.



### Cockpit static or wipers missing (Lada v8)

**SDK/Build:** check compiled prop_cockpit_dashboard target names and enter the
high-poly cockpit before judging motion. Wipers require paired exported actions,
animation-controller entries and prop_wipers_controller references. Check the
actual `.tpl` name metadata and exporter manifest; a `.tpl_data`-only scan gives
a false missing-clip result for the current native exporter. Opaque needle cards
can hide otherwise correct dial art: preserve their source silhouette or use a
verified opacity material. See cockpit-and-lamps.md and the shared opt-in
native_cockpit validator; static checks do not establish native motion.


### Missing generated .ssc.resource during editor startup

**Game (Roamer and Lada):** if a fresh source fixture hot-reloads brands during
engine initialization, let source creation/write/seal timestamps settle for
at least the observed 100 seconds before relaunching. Lada uses 110 seconds.
Unchanged baseline fixtures can fail too. Renaming descriptors, deleting
aggregate catalogs, or flipping data-brand flags did not cure this race.
See build-pipeline.md and the sealed Lada v8 diagnostic runs. Confirm live truck
state; an automation ready marker alone can be emitted after a crash.

### Import passes but package misses a sample tyre-track resource (L275)

**Build, 2026-09-30:** missing mod_tuz_119lynx_trails_hdetm.pct.resource was a
dependency-closure fault in the isolated mod, not a failed body import. Copy
the SDK sample trail nm/hdetm/mask PCT/TD payloads and descriptors (12 files)
and pin them. Failed job 20260930T091227Z-3e46ea489971 is preserved; builds
005 and 007 package successfully. See build-pipeline.md for the tested scope.

### Functional vehicle still has implausible cab/tray proportions (L275)

**User report/Build:** passing native controls and contacts did not validate
the supplied 79 single-cab appearance. Measure deck length and bare roof height
against vehicle-specific references, retain cab/door shape, and refit collision
and locators after moving geometry. Lowering the cab initially made the broad
bonnet hull cross the tyre envelope; selecting upper bonnet panels fixed the
sampled overlap. See frames.md. Revised loaded stance remains an estimate until
a later native measurement; the owner stopped focus-taking tests.

## L275 Blender materials v3 (2026-09-30)

### Baked powdercoat looks like coarse stone

**Blender review, L275:** inspect the mask, roughness and bump separately.
Interpolated Pointiness on the supplied large flat panels gave broad patchy
wear. A Bevel-normal edge mask and finer 18Âµm orange peel produced the reviewed
smooth finish. Preserve before/after previews; a successful bake does not
establish finish quality. See textures-and-materials.md for the scoped values.

### Blender normal bake fails a unit-vector check

**Build, L275:** eight of ten raw maps contained shortened averaged vectors
at small geometry/edges. Normalize vectors during export, set near-zero pixels
to neutral, then flip green for DirectX. Keep the original PNGs and the failed
audit. Verify packed normals independently instead of relaxing the check.
See reports/normal_validation_before.json and blender_texture_packing_v3.json.

### Background bake stalls alongside read-only GPU-cache errors

**Blender authoring, current Windows setup:** configure workspace-local cache
paths. L275's successful route used CUDA and less repeated ray-traced shader
work; backend/cache timing causality was not isolated. Do not infer a general
OptiX defect from this one attempt. See build-pipeline.md and preserved logs.

## L275 final lighting and installation (2026-10-01)

### Installation stops while writing the rollback journal

**Installed transaction, L275:** Windows error 5 at the pre-swap SWAP_READY
journal replacement left durable STAGED_VERIFIED and the live slot empty.
Recover the exact receipt through the shared API before retrying installation.
The bounded 5/32/33 writer retry now follows the existing job-journal policy;
persistent access errors still fail. See build-pipeline.md and the original
failed/recovered receipt. No manual package/lock deletion or acceptance edit.

### New emissive textures seem missing after a passing retail export

**Build, L275 checker correction:** inspect the actual retail resource/mip names,
not TextureConverter's intermediate .pct file. Compare compiled class properties
between the same native/retail roles; suffix rewrites otherwise appear as unrelated
replication/drivetrain changes. Failed test-012 is retained; passing test-013
uses actual mip payloads and confirms all non-light gameplay settings are equal.

## Roamer scout startup and misleading test success

**Game, SDK 7.3 (2026-10-01):** the installed Roamer reference also crashed at
TPL_MARKUP with unresolved `invisible` visibility aliases. An isolated replacement
with concrete hidden flags restored Play, independently confirming the Lada fix.
The shared opt-in native visibility check now guards the exported body/wheel
markup; resolved custom aliases remain permitted when explicitly declared.

A separate candidate01 fixture crashed because its scene resource referenced an
absent autogen prefab. Copying the established scene's prefab support, overlaying
the exact candidate package, and confirming the live Play truck corrected that
fixture fault. Both failed engine dumps and automation-ready messages remain
preserved. Editor exit zero and a ready echo alone never prove a live scene.
Evidence: Roamer `campaign/scout_20260930_01/runtime/{baseline01,visibility02,
candidate01,candidate02}` and their fixture seals/crash records.

### Packager succeeds but emits earlier source bytes (Roamer scout)

**Build, 2026-10-01:** check absolute documents-dir, ModsSourceLocal and
ProjectPath in the copied native project and every tool config. The Roamer
differential repack read an earlier project despite an isolated --project path.
Its exit zero was rejected by an exact resource-byte audit. Rebind the isolated
copy before packaging, preserve the failed artifact and receipt, and keep any
recovery/approval boundary intact. See build-pipeline.md for the evidence and
pending final verification scope.

### Differential selector says off but physical input stays on

**SDK/Game, Roamer 2026-10-01:** inspect prop_truck_rb.diffLockType as well as
the gearbox controller mode. ALWAYS/NONE force the physical input in native
SetState. DEFAULT let the Roamer's existing CONTROLLED selector reach actual
off/on states in final_diff04. See truck-settings.md for scope and exact evidence;
permanent modes are valid when explicitly intended.

### The Mod Browser fails and a local .pak cannot be enabled

**Retail/Build, 2026-10-01:** copying a .pak does not itself establish that its
local ID appears in `UserSettings.enabledMods`. The packed retail
`user_settings.cfg` does contain activation state; the launcher INI does not.
The [offline helper](../integrations/windows-offline-mods/README.txt) can edit
that list while the game/editor is closed and keep exact backups. Select the
actual installed game and user profile. See [retail-data.md](retail-data.md) for
the codec, evidence and tested scope. **Open:** retail startup acceptance and
account/save/multiplayer gating still need runtime evidence; the helper does not
repair the online browser or download missing packages.


### Winch functions but front/rear rope starts inside the vehicle

**User observation + Authoring/Build, Roamer 2026-10-01:** inherited socket offsets
were valid in the correct chassis frame but belonged to unfitted positions about
1 m from the front fairlead and 0.85 m from the rear bar. Earlier side-pull proof
missed this fault. Measure the actual fairlead and recovery-loop geometry, update
both gameplay source and target arrays plus the maintained source overlay, and
verify each endpoint in the live native chassis frame. Keep the tow ball out of
the rear recovery locations. Preserve the previous functional proof with its
narrower scope. Evidence: Roamer `winch_fit_20261001_01/hardware_fit.json` and its
geometry captures; native front/rear pulling is a separate delivery gate.


### Varied source materials bake to a nearly uniform color

**Authoring/Build, Dump Twuck 2026-10-01:** bounded UV coordinates can overlap
across faces. Preserve the failed bake, pack a separate bake layout, keep source
tiling UVs in the shader, and export the geometry with the exact new layout.
Geometry fingerprints and expected palette variation provide scoped checks.
See textures-and-materials.md and dumptwuck_mod/reports/toolchain_learning.md.


### A dump truck compiles but crashes loading PropLoadVolumeController

**SDK/Native startup, Dump Twuck 2026-10-01:** check the crash report before
changing geometry. `PropRouteFollowing ... can't be resolved` means the generated
truck lacks the route component required by its load controller. Enable
aiRouteFollowingSettings, rebuild and rerun native loading. RC033 checks complete
generated truck_view property tables. See truck-settings.md for evidence and scope.


### Native play crashes in BlueprintNodeOnWinchStateChanged

**SDK/Native startup, Dump Twuck 2026-10-01:** a copied donor sound blueprint
may subscribe to a winch component the new truck lacks. Remove its winch event
and sound branch, or author a complete usable winch. RC034 checks generated
truck_view subscriber types against explicit prop_winch declarations. Read the
native SSL stack; compiling and loading the edit scene do not prove play works.
See truck-settings.md and history/runtime_002_failed.


### Native test truck has six wheels but no ground contacts

**Native fixture, Dump Twuck 2026-10-01:** check world position and collision-pad
coverage before changing a vehicle. A borrowed 60 x 100 m pad with a spawn at
Z=-180 let the truck fall to the -4000 m world floor. Resting spring values there
were meaningless for suspension tuning. The corrected 300 x 300 m pad has a
bounded spawn and room for the drive checks; prepare_runtime.py asserts coverage.
Evidence: history/runtime_003_fixture_failed/004_baseline.json and fixture.json.

### Automation ready/exit-zero does not establish a playable native scene

**Native fixture, Dump Twuck 2026-10-01:** the editor's ready echo can precede
the restarted play engine's scene load. Wait for post-Play resource completion
and initialization, then prove a correlated smoke/data response against the
exact owned engine PID. Preserve probe timeouts and crash stacks. The wrapper
can also exit zero after an engine crash; inspect engine results separately.
Dump Twuck's numbered early timeouts and startup failures remain retained.

## L275 front-end feedback and supplied texture update (2026-10-01)

**Game report / Build diagnosis:** L275 owner rejected v4's headlight appearance and reported a box above the grille and a loose steering joint. The radiator's chassis skin escaped the 350mm cab lowering, placing its top around 1.33m in the authored model. Fit the complete forward radiator/fittings to the lowered front end and recess them behind the grille, while preserving collision, frame/axle placement and handling. The source lamps shared the windshield glass atlas, and front-face selection also captured internal bulb/reflector parts. Use dedicated smooth lens surfaces and a separate restrained emission mask. For a displaced steering end, check explicit IK constraint count (RC014), not only valid skin weights or axle-controller presence.

Evidence: L275 reports/front_end_v5/geometry_before.json, build/front_end_fit.json, revisions/front_end_v5/owner_game_front.png, tools/front_end_geometry.py, audit_front_end.py and patch_compiled_ik.py. Source geometry and typed-class checks support the proposed fixes; final game appearance and linkage behavior remain **Open** until the owner's drive.


## Sand pours from a lowered tray / a cap stops unloading

**Dump Twuck owner report, SDK and private native fixture, 2026-10-01:**
verify full-load retention over time and after driving/braking; observe native
pour emission separately. Treating large loss as settlement masked v1's
fault. A fixed rear boundary retained the load but blocked most discharge.
Use a supported dynamic cap/closing-joint controller and test substantial
unloading plus cap return after lowering. Inspect explicit markup visibility
if a hidden border renders as a panel. See truck-settings.md for preserved
failed evidence and limits.

## Chase camera shows the truck but blocks the road

**Dump Twuck owner report/native fixture, 2026-10-01:** check the compiled
attachment marker, preset focus and orbit together. A distant source locator
can compound the orbit; a corrected anchor can still have too low a follow
angle. Inspect post-cockpit and moving-camera captures. Whole-truck visibility
and focus alignment alone are insufficient. See cockpit-and-lamps.md.


### A tan slab before filling can be actual startup sand

**Native private fixture, Dump Twuck 2026-10-01:** the first slab diagnosis
blamed a new rear border. Native GetCurrentVolume instead reported a full
170.377 m3 startup load and Geom.IsObjHidden(backWall)==true. Explicitly
clearing the fixture through the load controller produced zero volume and an
empty rendered bed without hiding any shipping geometry. Do not confuse a
full load with an exposed helper mesh, and do not assume a test scene starts
empty. Preserve the observed starting state, clear it as explicit test setup,
and measure empty/full/discharged states separately. See truck-settings.md
and cockpit-and-lamps.md for the final carrying and camera regressions.


### Sand hangs below the tray or behind the tail

**Shared check (2026-10-02):** run `roadcraft.blender_load.grid_report` on the saved model: it emulates
the native grid over the authored volume and borders and reports cells at the pivot height (RC040),
misplaced borders (RC042) and a grid leaving the tub (RC044). See truck-settings.md, "Dump truck loads
with `roadcraft.load_volume`".

**Disassembly / Game, Dump Twuck revision 4, 2026-10-01:** check the load borders
first. The native grid spans the four `bodySettings` border meshes, and the back
border is composed with its parent's transform: hung under the bed body it pushed
the grid 3.7 m past the tail, and the cells beyond the heap fell to the bed pivot
height (a curtain behind the tail when full, a slab past the tail while tipping).
Hang it from the tail-lid body, keep all borders inside the tub and give their
tops the sand height beside them (RC036; truck-settings.md, Correction 2). The
revision 3 notes below still apply to the hull itself.

**SDK shader / native captures re-measured, Dump Twuck revision 3, 2026-10-01:**
do not shift the load volume by the dump pivot; the engine draws it where it is
authored (builds 021-023 moved the dirt into the front wall and kept the fault).
Measure first: reproject a native capture with its logged fly-camera eye/target
and compare the authored volume's silhouette (dumptwuck_mod/reports/revision_003_refit/scripts).
Then check two geometric causes. A hull floor below the visible floor (v2's flat
box under a 13.7 deg tail ramp) draws partial loads beneath the tray. A thick
load edge with open grid cells beyond it draws a steep sheet down to the grid
minimum, a curtain under a thin-shell tray; thin the heap to nothing at such
edges and keep the floor on the steel. See truck-settings.md, Payload.

### Refill sand falls under the truck

**SDK script / Retail, 2026-10-01:** without `sfxMovableDumpPositionBone` the
refill stream is placed at `sfxRefillLocalPosition` in truck space and does not
follow the bed (Dump Twuck v2: 2 m off the ground under the tray). Name the load
volume and give an offset above the heap, as the Aramatsu Bowhead does. RC035.

## Lamps that never light (L275 v9, 2026-10-01)

| Symptom in the game | Cause | Fix | Grade | More |
|---|---|---|---|---|
| No lamp ever glows although the light graph runs (a default-visible unlit lens is seen switching) | Lit `_on` copies marked `visibleDefault = False` in the model markup's `objSettings` (`lint-bro` RC037) | Leave lit copies default-visible; hide them from the graph's init (the Lada way) | Inferred from L275 v7/v8 drives; fix Build | cockpit-and-lamps.md |
| A strobing or flashing lamp does not glow: its whole mesh disappears and reappears | The flash swaps the unlit lens with a lit copy that does not render (here a markup-hidden one): the lens itself blinks out (RC039, with RC037 when the markup hides the copy) | Never switch the unlit lens: flash a lit overlay over it (`roadcraft.lamps.flasher`, `blender_lamps.lit_shell`) and keep lit copies default-visible | Game (L275 v7 and Dump Twuck v4 owners); cause Inferred; fix Build | cockpit-and-lamps.md "start here" |


## Interior textures look soft despite high-resolution source (Lada v9)

**Build / inspected Blender render, 2026-10-02:** inspect source, packed and
compiled sizes independently. Lada's original 4K atlases had been packed to 1K;
restoring all six interior colour/normal/scalar maps retained the original art
and improved on-model detail. Its AI drafts changed markings and were 1254px,
so they were rejected with the owner's approval. Do not call restored originals
AI-upscaled assets. A second check caught a normal-map TD limit of ten levels:
requesting at least eleven produced the native 4K-to-4x4 chain. Verify actual
headers and packaged mip bytes. See [textures-and-materials](textures-and-materials.md)
and Lada build-013 failure, build-015/test-015, v9 `texture_result.json`.
In-game appearance and performance remain an owner check.


## No driver visible in a completed vehicle (Lada v10)

**SDK / Game in isolated editor, 2026-10-02:** inspect BRO `hideDriver`, the
generated `prop_driver`, a valid driver anchor and resolved offset. Lada's
conversion explicitly set `hideDriver=True`; enabling it and fitting the native
seated character added the driver without changing geometry or vehicle physics.
An omitted generated `boneName` uses the stock `_cockpit_camera` default and
does not mean the anchor is missing. If the actor exists but is hidden, inspect
first-person cockpit, global hide-driver, photo mode, occupancy and phantom
state before editing the vehicle. Only first-/third-person visibility was
tested in this case. See [driver placement](cockpit-and-lamps.md#native-seated-driver-placement-lada-v10-2026-10-02)
and Lada v10 native trial/parity evidence; no retail campaign claim.

## Crane conversion builds but retains donor movement-sound references (KGS25)

**SDK / Build, 2026-10-02:** a native generation/package pass does not catch
missing `rootBodyName`, `hookBodyName` or axis joint names in
`BlueprintNodeOnCraneArrowPositionChanged`. The TC305 graph still named its
Cabin/CraneSeg2/cabin after KGS25 used Turret/Tip/Slew. Inspect the source graph,
generated class and compiled model; map the references together. RC045 covers
the mechanically checkable mismatch. Runtime symptoms remain unobserved in
this case because the owner deferred editor tests. See
[crane reference checks](ik-visual-rigs.md#crane-movement-sound-references-after-a-donor-conversion-kgs25-2026-10-02).

## Detached crane parts and explosive tracked driving (KGS25, 2026-10-02)

**Game:** the owner reported detached boom parts, glitching tracks and a flying
vehicle for candidate01. A bounded native pad test reproduced flight after
reverse/braking: chassis Y rose from about 60.0 to 70.57 m, pitch reached 104.45
degrees, and a track body exceeded 123 m/s. Correct static rest did not establish
driving stability. Its 450 kg track bodies used spring 12,000,000 and damping
4,400,000 hinges. Those values were borrowed from a different tracked rig.

The repair fits fixed track frames to this crane's rigid undercarriage, retains
wheel-contact suspension and redistributes mass without increasing total body
mass. Treat excessive hinge feedback as a working diagnosis; the live softened
motor trial was contaminated by the already-diverged pose and cannot isolate
the cause. Driving proof requires a fresh native spawn of the repaired files.
Separately, child transform freezing displaced the telescope, hook and piston
geometry. See ik-visual-rigs.md for that proven source conversion fault.

Evidence: KGS25 reports/owner-failure-candidate01.json, runtime/baseline03_graph_shakers,
runtime/drive_115725, native physics samples and the owner's screenshot. No
retail acceptance is inferred from a subsequent editor pass.


## Counterweight stays fixed; stabilizers never finish opening (KGS25, 2026-10-02)

**Game report / native editor:** a rigid part can appear assembled at rest while
being bound to the chassis instead of the rotating upperworks. Audit every LOD,
collision body and attached lamp/locator. KGS25's rear_box chassis fallback
caused its counterweight symptom; turret binding plus fixed-cab clearance
corrected it in the native slew review.

Feet touching the ground does not guarantee native anchor completion. In the
first KGS25 support test the commanded 0.40 m stroke exceeded the available
travel against the pad by about 0.021 m; the stock 0.01 m completion tolerance
kept anchors opening. Fit the stroke to ground contact and verify both
IsAnchorsOpened and IsAnchorsClosed on a fresh build. KGS25's corrected 0.37 m
stroke passed; preserve the first failure and live diagnostic separately.
Evidence: reports/runtime/supports02 and supports-review.json,
counterweight-articulation.json and native-build-009. Retail acceptance is open.


## Crane rocks onto one track and gets pushed around while driving (KGS25, 2026-10-02)

**Owner report (candidate 02/03 rig):** "almost like there isn't something underneath it, it
starts lifting up weirdly on one side, and being pushed around as it's driving".
**Game (editor bench):** in pivot turns one track's wheels sank up to 19 cm into a flat static
pad while still reporting ground contact. The hull rolled 3-4 deg, then popped back after the
turn. Parked and in straight driving it stayed level.
**Fix 1, withdrawn:** sprung support wheels sized from the vehicle mass came out far too soft.
The owner reported "it does it worse now" ("bounces or wobbles"); on the bench it sat parked
at 2.8 deg roll.
**Fix 2 (bench passed, owner drive pending):** the retail EPEC track layout with 7.5 t track
frames and the hull centre of mass lowered held roll to 0.2 deg in the same turns. Detail and
values: [tracked-vehicles.md](tracked-vehicles.md); `lint-bro` flags the layout (RC046) and light
welded frames (RC047), and [physics-bench.md](physics-bench.md) measures a change before it is
installed.

## Static validator findings on shipped mods (2026-10-13)

**Build (static check, `roadcraft.validate`):** run `python -m roadcraft.validate <pak or source>` before a drive.
It found idler wheel markups in Goliath D11 RC5 that name `mod_goli_d11_idler_front_restored` /
`_rear_restored` material instances, which neither the pak nor retail contains (RC070). The engine substitutes
a missing material, so the idlers are expected to render with a placeholder; this has not been confirmed in
game. In the SDK TUZ sample, the marker lamp's slot defines `lights_emmissive` while the lamp switches
`lights_emissive` (RC066), and the BRO omits `useSuspensionCollection` (RC001). Rules, retail tuning and
per-mod results: [validator.md](validator.md).

## Truck initially continues its old direction after switching (Dump Twuck public report, 2026-10-08)

**Open / public user report:** Dmitriy311 reports incorrect forward/reverse
switching even after a complete stop and handbrake application. Reproduce empty
and loaded while recording requested direction, selected gear, pedal and brake
states, and actual chassis velocity. Cause and remedy are unverified; increasing
torque is not evidence of a fix. The comment does not identify an installed build,
and the published Version 2 has not been matched to a local package.

Evidence: Dump Twuck `reports/public_comments_2026-10-08/comments_page_000.json`,
comment `861394e1-f92e-4d2e-8e93-bf3afedc4584`; source pins and classification in
`audit.json`. See [case-studies.md](case-studies.md) for the complete feedback audit.
No static rule or shared behavioral change is justified until reproduction.

### Dump Twuck public reversal follow-up (2026-10-10)

**Open:** a second public player reports continual backward travel; preserve
this as a different symptom from the earlier stopped forward/reverse switch.
Do not assume a common cause. Source: `reports/feedback_2026-10-10/assessment.json`
and comment `e25505bf-cae1-4d4c-ade4-93a70c774b2f` in the pinned raw response.

### High-water warning in shallow puddles (Dump Twuck author screenshot, 2026-10-10)

**Open / author report:** zombie213 attributes a puddle-triggered water warning
to engine placement in the axles. The screenshot is text feedback, not a capture
of engine coordinates or warning state. Check the effective engine locator and
water-warning/damage configuration on the affected package at measured depths;
physical engine relocation is not yet a validated remedy. Evidence: Dump Twuck
`reports/feedback_2026-10-10/author_feedback.png` and source-pinned assessment.
No cause, fix or universal static check is established.



## New cab remains at 888 or the replacement digits occupy the wrong panel (Dump Twuck revision 006, 2026-10-10)

**Offline source inspection / SDK; native Open:** first separate an exported static placeholder from a controller failure. The new archive's `888` has no RoadCraft runtime driver; its README's Blender-only limitation is not an SDK limitation. Stock velocity/arithmetic/switch/show-hide nodes support three-place speed digits, as recorded in [cockpit-and-lamps.md](cockpit-and-lamps.md). Schema and synthetic-state tests passing do not establish correct display geometry or native rendering.

**Failed authoring choice, offline visual review:** the first bounded removal selected two three-component red-glow groups near the speed/RPM dials, rather than the main central dark `888`. Matching component counts, coordinates and seven-segment-like shapes was insufficient to identify the intended panel. Keep legends/needle meshes, inspect the actual cockpit view, locate the central placeholder components, and align replacement glyphs plus `km/h` to that face. The corrected driver-eye Blender render now shows central `000` unobscured (Visual, offline only). Guarded removal identifies the actual central `body_ci_darkpanel` components 109–129 (21 bars/756 vertices), preserves the backing, and fits 30 independent glyphs plus authored `km/h`. Live updates, native pixels and usability remain Open.

## New model loses procedural finishes or tiny cockpit lettering after baking

**Build / Inferred; native Open:** a material-only colour atlas cannot preserve linked noise/wave/Voronoi/bump inputs even when the source has no image textures. Inspect the actual `.blend` rather than treating its “flat Principled” README as a factual material inventory. For verified uniform labels, centre-sample reserved uniform tiles while retaining actual text geometry; for procedural finishes bake the connected shader inputs. Tiny-island filtering is a suspected cause in revision 006, not confirmed by a preserved matched before/after. See [textures-and-materials.md](textures-and-materials.md).

## Offline COM predictions look plausible but the truck still leans or bounces

**Build / Open native:** verify whether the author's bone heads are absolute or parent-relative before summing body centres. Revision 006 uses absolute heads, so add only the selected head once; a double-counted bed/cap head corrupts load moments. Its new volume/mass/stop checks establish internal authoring consistency, not heavy-truck suspension beta, damping or a handling fix. Measure empty/full settled travel and roll/bounce in the final compiled candidate. See [frames.md](frames.md).

Evidence for these revision 006 entries: Dump Twuck `source/revision_006/generated_authoring_inventory.json`, `tools/model_v6.py`, `tools/digital_dashboard.py`, `tests/test_digital_dashboard.py`, `build/physics.json` and `reports/gameplay_v6_audit.json`; all current authoring snapshot references, with native acceptance still open.

## BRO generation fails during wheel-resource saves while a VFX warning precedes it

**Build, native generation attempt; functional acceptance Open:** revision 006 candidate 01 attempts 1–2 fail with `System.IO.IOException` while `WheelGenerator`/`SaveTo` writes a `.sso.resource` already held by another process; attempt 2 reaches preview-wheel generation before the same failure. The fatal stack establishes a file-access failure, not a faulty speed-digit graph. Preserve logs and inspect the class database/resource lifecycle before changing unrelated graph nodes or rerunning without a bounded recovery. The holder was not identified by this evidence.

A separate nonfatal warning says “Values size greater that array size” at `vfxSkeleton/vfxBones/item0/boneOffset`. **SDK:** `boneOffset` is `vec3` with fixedSize=3, and the authored value contains exactly three floats. The digital hide list instead uses dynamic `array<string>` with no fixedSize. The warning therefore does not justify deleting glyphs or truncating a supposed matrix; its source/model conversion remains Open. Evidence: Dump Twuck `build/generation_attempts/attempt_1_20261010_085925/{batch.log,bro.stderr.log}`, `attempt_2_20261010_090004/{batch.log,bro.stderr.log}`, current truck BRO and `build/schema/meta_desc*.json`. No compile or runtime pass follows from these failed attempts.


### The carried load looks like a broad flat slab despite a crown (revision 006, 2026-10-10)

**Owner report / offline arithmetic; native Open:** check the surface profile and sampling before raising the apex. A quadratic longitudinal fall of 0.012 m per square metre loses only 4.8 cm at 2 m from the crown, so a wide tray can look flat even when its hidden hull has a numerical maximum. A higher apex may exceed the native under-4 m height range. The shared load helper now has an optional pointed `elliptic_cone` profile with independent longitudinal slope, while preserving the default paraboloid.

Sample the exact peak, fit the sides and real floor, and rerun the saved load-grid audit; changing the footprint can expose border/pivot cells. Recompute capacity, centroid and density-based payload. An offline preview must show the requested silhouette before its source is handed over, with native retained/tipped appearance still separate. Evidence: Dump Twuck owner feedback dated 2026-10-10 and `reports/revision_006/mound_refinement`, plus eight numeric tests in `tests/test_blender_load_heap_top.py`. See [truck-settings.md](truck-settings.md) for the profile API and limits.


**Saved grid can pass shared findings while drawing below a raised rear floor.** A lowered 6.5 m rear border filled four cells outside the hull at x=+/-3.874375 m, y=6.801352/7.086921 m; the measured steel there was 6.667592-6.733335 m. Shared findings and pivot-cell counts were empty, but the direct saved-grid-versus-floor check found up to 0.233335 m below steel. Survey every emulated cell at the engine's nudged coordinates, comparing both heights with the real floor, especially border-only corners. A hull-only floor check cannot cover cells outside that hull. Preserve the failed report and require a new completed saved audit after restoring the measured rear ramp. Evidence: Dump Twuck `tools/audit_mound_v6.py` and `reports/revision_006/mound_refinement/failed_lowered_rear_border`. Native compilation/retention/discharge remain open and outside the exhausted three-iteration budget.

## Articulated vehicle: steering ram rod leaves its barrel or pokes out of the back at full lock

**Build (Kanga 25):** the articulation limit exceeds what the modelled cylinder pins allow. Compute the pin distance
over the whole lock (with the oscillation roll) against barrel length plus the rod's hidden length, and lower the
steering limit or remodel the cylinder. See [articulated-steering.md](articulated-steering.md).

## Crane boom tail sinks into the chassis when luffed up

**Build (Kanga 25):** the boom section behind the foot pin swings down as the boom rises. Sweep luff x articulation
for mesh overlap at the model stage (kanga25_mod `tools/audit_rig.py`), limit the luff, and keep boom and chassis
in one collision group so the physics cannot jam. See [cranes.md](cranes.md).

## Crane mod: script crash dump on deploy in BlueprintNodeOnAnchorsStateChanged

**Build (Kanga 25 c1, owner's crash dump 2026-10-10):** a donor crane graph (Baikal 5916 ForceFeedback and Addon)
kept its outrigger listener on a crane without outriggers. The node asserts `PropTruckAnchorsController` in
`HandleBlueprintInited`, so blueprint init stops at that graph. Remove `BlueprintNodeOnAnchorsStateChanged` nodes
and their links when `isAnchorsEnabled` is False; check every donor node type for `TryGet<...>` asserts against the
class's properties. See [cranes.md](cranes.md).

## Crane shakes violently with the boom extended and raised

**Owner report (Kanga 25 c1); cause Inferred, fix Build (c2), drive Open:** c1 drove three light telescope sections
(350-700 kg) with 1.5 MN, damping 0.6 motors, hung the boom on a 1.5 t hidden slew body with a 0.05 m3 box, and let a
250 kg hook pendulum load the tip. c2 uses the retail Baikal 5916 telescope motor (tau 0.8, damping 0.99, 0.8 MN),
heavier sections (900/700/500 kg), a 2.2 t tower with a real-sized box, luff 6 MN, and the hook as secondary physics
(`massFactor = 0` on its ball joint, 60 kg, as retail dangling parts). See [cranes.md](cranes.md).

**Owner on c2: "still shakes but not as bad"; cause Measured (editor bench, kanga25_mod `tools/bench`), fix Build (c3):**
the luff position motor (tau 0.8, damping 0.99, the Baikal value) self-excites against the suspension once the crane
drives with the boom raised: pitch/roll of +-3 degrees and a 13 cm hop that persists after stopping (front body
angular rate 1.2 rad/s in the settle window). Telescope, steering and suspension changes alone did not stop it; luff
tau 0.4, damping 1.0 (6 MN) settled at 0.07-0.10 rad/s in every carry run. Bench a crane with a raised-boom carry (raise,
drive, brake, full-lock turn, reverse), not only stationary crane moves: the rocking needs the wheels.

## Crane boom oscillates with a load and keeps going until the boom is retracted

**Owner report (Kanga 25 c4); cause Inferred, fix Build (c5), drive Open:** three telescope prismatics in the crane IK
chain, one more than any retail crane. Reduce to one (Baikal) or two (Forester) IK telescopes and let extra sections
follow visually. See [cranes.md](cranes.md).

## Step treads or boxes float below a frame (Kanga 25 c4)

**Owner report; cause Build (asset defect):** the supplied asset's rear-frame step column had treads but no stringers;
the bottom tread and a light box hung free in both the source low poly and high poly. Render the area from the source
collections before blaming the export (kanga25_mod `art/review/src_*_lstep.png`); fix with added geometry on the same
body at one texel of an adjacent painted part (kanga25_mod `create_models.step_stringers`).

