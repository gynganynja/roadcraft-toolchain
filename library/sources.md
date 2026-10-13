# Sources outside this library

Where RoadCraft modding knowledge lives besides the game's own data (retail-data.md). Surveyed
2026-09-12 across about 48 official documentation pages, the Steam guide, the Focus forums, Nexus,
GitHub and PROS.

## Official documentation

<https://roadcraft-modding.prismray.io/> (MkDocs). Truck pages:

- `truck_modding/creating_3d_model/<naming|bones|wheels|materials|...>/` (lowercase `3d`)
- `truck_modding/creating_textures/`
- `truck_modding/mod_editor/<importing_3D_model|physics_and_collision|lod_setup|material_setup|bro_files|adding_mods|building_mod>/`

Maps and the rest: `tutorial/*`, `scene_components/{terrain,prefabs,objective_system,blueprints/nodes,sounds}/`,
`interface/debug_ui/`, `troubleshooting/`, `mods/{build_and_upload_mods,play_with_mods,mods_faq}/`.

Its rules, as this library grades them:

| Documented rule | Status here |
|---|---|
| Truck faces -Y, +Z up; scale 1, rotation 0; root `BoneChassis_cdt` at the origin; convex `cdt_` collision only | holds (frames.md) |
| Wheel in its own file, rim and tyre meshes, outer face -X | holds only with the sample's per-side slot joints; identity slots need per-side models (suspension-and-wheels.md) |
| Textures uncompressed TGA type 2 with `_nm`, `_spec` (metal / rough / AO) postfixes | holds (textures-and-materials.md) |
| Blender 4.5 or 5.0 | holds |
| Truck mods need the five `auto_*` `.sso.resource` assets in the Mod Manager and the Vehicle category on PROS (co-op breaks otherwise) | not tested here |
| Physics defaults: angular damping 1.5, linear 0.01, restitution 0.01, mass by hand | used; superseded as engine defaults 2026-10-13 (frames.md; physics_semantics.md Q2/F2, code analysis, static) |
| LOD hide distances 800 m vehicle / 350 m wheel; LWI transition off for trucks | used |

The documentation does not cover suspension semantics, the axle controller or visual IK; those
sections of this library come from retail data and drives.

## Community

- Steam guide "RoadCraft Vehicle Modding Guide" by Budster024 (id 3765953568, v0.6, July 2026): the
  only tested end-to-end community workflow for the editor's user interface. Duplicate a vehicle in
  the editor (never in Explorer), change only the UI name, tick Add To Library and Add To Preview
  Library, delete generated TPL data before Reimport Asset, keep the original `.blend` file name,
  Blender 4.5 proven (5.1 broke armatures), replace meshes with Ctrl+P Armature Deform With Empty
  Groups. Aramatsu Crayfish is the fully working base; the TUZ is limited.
- Problems nobody had solved publicly (2026-09-12): winch, scanner and crane UI lost on duplicates;
  suspension constraint setup; a new vehicle from scratch; trailers. The second and third are solved
  here (suspension-and-wheels.md, the mods in case-studies.md).
- No video tutorials existed for the vehicle editor.

## Unofficial route

Editing `.cls` files inside `root/paks/client/default/default_other.pak` (delete
`default_other.pak.cache` afterwards). Tools: Roadcraft Editor Suite (roadcrafteditor.provoid.net,
Nexus 122, active), samu126 Vehicle Editor (Nexus 9 / GitHub, unmaintained), the Reclaim fork (Nexus
105). Local only and fragile across patches; PROS calls these "Manual" installs. Not used here.

## Support

The Saber help desk may not know the tools; the official Discord and the SnowRunner / RoadCraft /
Expeditions Discord are the real channels. PROS was migrating to saber.games.
