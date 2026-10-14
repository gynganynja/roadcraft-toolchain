# Porting a SnowRunner truck mod (Watcher 61, 2026-10-13)

How to turn a SnowRunner truck mod (its `.pak` meshes recovered into Blender, plus the mod's own XML) into a
RoadCraft vehicle, and how to ship its add-ons as several configurations. Learned on the Watcher 61 (Nissan
Patrol Y61, `C:\RC\watcher61`). Both games run on Saber's engine, so much of the art carries over directly; the
traps are the importer's frames and the parts-browser layout.

## What carries over unchanged

| Finding | Grade |
|---|---|
| The SnowRunner shading map `__sh_d` already has RoadCraft's `_spec` layout: R metallic, G roughness, B occlusion. Chrome reads (1, 0, 1), tyres (0, 0.63, AO). Copy it as `MSCRGHAO` without repacking. | Build (Watcher 61: sampled 13 maps) |
| `__d` is the colour map; `__d_a` carries opacity in alpha (glass, stickers): convert as `MD+MT`. `__em_d` is an emission map (`MEM`). | Build |
| `__n_d` normal maps are mostly DirectX, but not all: measure every map (`roadcraft.normal_maps`) and flip only on a clear OpenGL reading. On the Watcher 61 only the interior map was OpenGL (correlation -0.52). The rest read DirectX or flat. | Build |
| The mod XML gives real hardpoints and tuning intent: wheel `Pos`, `SteeringRack RackHalfSizeZ`, `WinchSocket`, lamp `Flare`/`Light` positions, `Exhaust Origin`, cockpit `ViewPos`, `AutomaticIK` (which links SnowRunner moves by IK). SnowRunner XML positions are X forward, Y up, Z left (relative to `bone_cabin`); in the recovered blend they appear as (x, -z, y). | Build (exhaust and wheel positions checked against the rig) |
| The SnowRunner skin weights carry over: rename each source vertex group to a RoadCraft bone (axle housings to the axle frame, `*springtop` to the chassis, `*springbottom` to the axle frame, shock and link top/bottom groups to the `_Base`/`_Tip` bones of a telescoping chain). Blended link weights then stretch the same way they did in SnowRunner. | Build (exported rig; native motion Open until driven) |
| SnowRunner `AutomaticIK` maps onto the L275 / Roamer live-axle pattern: an `IK_<link>` chain per link (HINGE2 + PRISMATIC along native X), axle frames on `axleControllerSettings.axleSettings`, knuckles as `customSteeringJointObjName` under the front axle frame, and the rack under the axle frame with SnowRunner's half size. | Build |
| A SnowRunner tyre mesh is unit radius (about 1.02-1.04 over the lugs); `CompatibleWheels Scale` gives the size: radius = scale x mesh radius. Rims and tyres share one wheel origin, so any rim fits any tyre of the same `Type`. | Build |

## Traps

| Trap | Remedy | Grade |
|---|---|---|
| The recovered blend is **mirrored left/right**: plate and sticker text reads backwards on its outer face, and a right-hand-drive truck shows its steering wheel on the left. | Render a plate or sticker before anything else. Undo the mirror in the source-to-RoadCraft map (here (x, y, z) -> (-y, -x, z + lift), determinant -1). Then flip the face winding and carry the custom normals over. `Mesh.flip_normals()` keeps each face's first corner and reverses the rest, so reorder the saved corner normals the same way. Check that order on a test quad at the start of every build. | Build (dashboard and "SLOW CAR CLUB" sticker read correctly after the fix) |
| The parts browser moves **and turns** each add-on rig onto its grid cell: ±90 degrees about Z for bars, a compound angle for windscreen stickers, 90 degrees about X for tyres. Subtracting the placement offset alone left a plate on the side window. | Take each add-on mesh relative to its own rig (`rig.matrix_world.inverted() @ obj.matrix_world`). SnowRunner add-ons are modelled in the truck frame (socket `Offset (0; 0; 0)`). | Build |
| The parts browser turns **rims** half a turn about Z but **tyres** a quarter turn about X, so a rim and tyre taken from their grid cells sit 7-9 cm apart sideways: "the tire isnt aligned with the rim" (owner). | Recompose them in the SnowRunner wheel frame: rim centre minus tyre centre along the axle = -(rim's lateral centre) - (tyre's lateral centre) relative to their placements, a few mm toward the rim face. The owner's own assembled display wheels give the same 16 mm on the stock wheel. | Build (Watcher 61 render; owner report) |
| Add-on spare wheels carry the mod's default tyre (KO2), not the wheels the configuration ships with. | Replace each spare with the configuration's own rim and tyre at the fitted radius. Fit the pose from the old spare (centre, the axle from the tyre's smallest principal axis, the rim side as outward) and keep its inner (mounting) face (owner request). | Build |
| The add-ons' **collision** meshes (`cdt*`) are parented to the same rig but sit in the truck frame in world space (their parent inverse cancels the rig). Taking them relative to the rig, like the art, left them 7-14 m off the truck. | Take `cdt*` meshes at their world transform and the art relative to its rig. Guard every hull against lying far from the truck. `roadcraft compare` caught it through a 0.32 m sideways `hkCenterOfMassOffset`. | Build |
| SnowRunner rim sets ship two versions of the same rim: `rim_front*` (with a free-wheeling hub) and `rim_back*` (with an axle cap). Joining both stacks two rim shells and puts hubs on the rear axle (owner: "The rear tyres need the freewheeling hub removed"). | Build a front wheel model from `rim_front` and a separate rear model from `rim_back`. Use the rear model's wheel class on the rear slots' `wheelPool` entries. | Build (Watcher 61 v5) |
| SnowRunner cabs rely on a **single-sided body shell**. From the seats, the pillars, roof edges, door frames, floor pan and footwells are the backs of the paint. RoadCraft culls them, so the cab is see-through to the road and the engine bay (owner: "interior needs major polish"). Blender hides this unless back-face culling is on in the review render. | Review cockpits with `show_backface_culling`. Line the shell: copy the paint/trim faces inside a cab box that face away from the nearest occupant eye, reversed, onto a dark `vehicle_cabin` trim (the roof onto the headliner colour). Add a toe board and firewall where the source has none under the dash. Keep the cabin instances plain: two-sided cabin instances crash retail on spawn (shader cache, Watcher v7). | Build (Watcher 61 `cab_lining`; game look Open) |
| A copied-face lining is not a finished cab: the owner wanted it to look complete ("model properly... like a proper triple A game interior"). Primitive trims were rejected before. | Mould each trim from the shell. Start from a 2D outline (filleted corners; window holes from the glass hulls plus a seal). Fill it with a constrained Delaunay mesh: dense boundary (0.8 x step), sparse interior grid (2.5 x step). Raycast every vertex onto the shell BVH, then median-filter the depth outliers and smooth the depth field. Clamp the smoothed depth to at most half the gap behind a cover depth, the nearest hit of a cross of rays at half a grid cell, so ridges narrower than the grid cannot poke through. Finish with a single-sided surface, a quarter-round rolled edge and a flange toward the shell. Slanted pillars hit by grazing rays need heavy smoothing (40) and a larger gap (20 mm). Add the details as swept and bevelled parts: visors, mirror, dome light, grab handles, pedals, mats, belts. Use one `vehicle_cabin` instance per finish with tiled 512 maps. Budget: about 90k triangles over a 1.2M-triangle body. | Build (Watcher 61 `interior_trim.py`, `trim_kit.py`; game look Open) |
| One of a mirrored pair of cab parts can be authored inside out. The Watcher 61's driver door card had 4 % of its side-facing area toward the cab against 96 % for its twin. | Measure each cab object's normals toward the cab's centre line and reverse the outlier, along with its custom corner normals in `flip_normals` order. | Build |
| Some SnowRunner "plates" are dash plaques (`Watcher61plate` sits behind the windscreen), not number plates. | Keep the mod's placement; check it in a render. | Build |
| The XML's UI strings can be crossed with the meshes (its "Steel Sunraysia" rim is a black beadlock). | Name parts from renders, not strings. | Build |
| SnowRunner glass maps are too opaque for RoadCraft's glass shader (Watcher window film alpha 0.62-1.0). | Thin the film to the 0.5 rule (here alpha x 0.68). Put the window sheet on the outer preset, with a cab-facing twin on `vehicle_interior_glass`. | Build (game look Open) |
| Very dense art: about 0.9-1.2 M triangles at LOD0 with add-ons; each spare wheel alone is about 160 k. The SDK importer's `tplexp` used about 10 GB RAM and 5-6 min per body. | Expect it, and import one body at a time. Optional: lighter spares. | Build |

## Configurations from add-ons

RoadCraft has no garage tuning. Ship each configuration as its own truck in the same mod, the way Goliath D11 ships
three. For each configuration:

- one body `.tpl` (base truck + chosen add-ons) and one truck BRO;
- one wheel `.tpl` per rim / tyre pair, shared between trucks;
- a `wheelPool` scale = the tyre radius;
- a suspension `height` raised by a lift for bigger tyres;
- the engine torque scaled by mass and tyre radius;
- paint by swapping the body's colour map in a per-configuration material instance (SnowRunner paint options are
  flat atlases on the same UVs);
- a shop card and a list icon each (`uiCustomShopIcon`, `uiCustomIcon`, linked in each truck's catalog entry).

One `pak build --stage-classes` packs every truck. Grade: Build. In-game Open until the owner's first drive.

Evidence: `C:\RC\watcher61` (`tools/w61_config.py` VARIANTS / SR_BONE_MAP / CHAINS, `tools/create_models.py`
`bake_object`, `truck_frame`, `corner_order_check`; `source/measured.json`; `reports/textures.json` for the
normal-map readings; `preview/variants_sheet.png`).
