# Reading the retail game's own data

When a rule is unclear, the shipped vehicles are the best evidence: they work. Everything here is
read-only; `roadcraft retail ...` and `roadcraft.retail` read it directly from the installation.

| What | Where (under the game root) | Form | Grade |
|---|---|---|---|
| Retail BROs (trucks, wheels, ...) | `root/prebuild/bro/Bro.Compiled.pak` -> `designer_wizard/<kind>/<name>.bro` | PS text; `roadcraft retail bro <name>` | Retail |
| Compiled truck classes | `root/paks/client/default/default_other.pak` -> `ssl/autogen_designer_wizard/trucks/auto_<truck>/auto_<truck>.cls` | text | Retail |
| Model markups | `root/paks/client/default/default_tpl_*.pak` -> `models/database/vehicles/<tpl>.tpl.asset/<tpl>.tpl_markup` | PS text (masses, constraints, collision groups) | Retail |
| Compiled models | same folder -> `.../tpl/<tpl>.tpl` | binary; `roadcraft tpl-nodes` | Retail |
| SDK type descriptions | `root/prebuild/meta_descs/meta_desc_bro.ps` (and `meta_desc*.ps`) | PS text: members, defaults, hints | SDK |
| SDK samples | `root/mods_source` (TUZ 119 Lynx scout, Aramatsu Crayfish) | editable sources | SDK |

A truck BRO's `tpl` field names its model; the class and markup are found from the truck and model
names. `roadcraft retail find "*armiger*"` lists members by glob.

## Compiled model node table (`.tpl`)

Decoded 2026-09-29 against models whose bone positions were known, and confirmed on the ZiKZ 605E,
Armiger Thunder and the SDK's Lynx sample:

1. `uint32 count`, `uint8 flag`, then `count` names, each `uint32 length` + ASCII (printable; the
   SDK sample has a name with a space);
2. `uint32 n` (= count) and `n` x `uint16` node index;
3. `uint32 nodes`, then `nodes` x 16 `float32`: row-major 4x4 **world** transforms in native axes,
   translation in the last row; rows 0-2 are the node's local X, Y, Z;
4. parent links: an `int16` per node (-1 for the root) earlier in the file, at an offset that varies;
   `tpl_reader.find_parents` finds the array that forms one tree and best matches the IK naming.

Unnamed nodes exist (LOD copies): `nodes` can exceed the name count.

## Surveys worth repeating

- `roadcraft retail survey`: implied suspension beta of light 4-wheel retail vehicles
  (see suspension-and-wheels.md).
- Effector kinds over all retail IK chains (ik-visual-rigs.md).
- Which retail trucks have `axleControllerSettings` (84) and in which form.
