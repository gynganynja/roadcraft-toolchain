# Save compatibility: updating a mod without breaking existing saves

A campaign save stores a few pieces of each truck's state, keyed by names and indices taken from the truck's
class. When an update renames, adds or removes one of those names, the old save may restore its state onto the
wrong joint, lose it, or crash the load. In the L275 v35 case the load never finished. This article lists what
is saved, how it is matched, and the rules for an update that loads old saves. Lint **RC077**
(`roadcraft validate <candidate> --baseline <installed>`) checks a candidate against the installed version.

The engine-side detail, with file and method references, is in `C:\RC_RE\research\save_semantics.md`. The
evidence there is static (base-game SSL source), except for the L275 and grader crashes, which are Game.

## How a save is applied

- A save is `dict<priority, dict<uid, array<SavablePropDesc>>>`. Each truck is one actor. Its saved descs are the
  `prop_savable_object.savablePropDescs` its class listed **when the save was written**.
- On load, a truck that is not in the level is recreated from its **origin**, `truck_manager_rb_<name>`. `<name>`
  comes from `auto_<name>_truck_info_<suffix>.sso.resource`, the truck library key. If no truck is registered
  under that origin, the truck silently disappears from the save.
- `PropSavableObject.SetSavedProps` walks the descs the class lists **now**. For each one, it applies the first
  saved desc of the same type, then calls `ReplaceData` and `LoadData`. A saved desc whose type the class no
  longer lists is ignored. A listed desc missing from the save keeps the class defaults. These two behaviours
  make removing a desc the safe escape hatch. (Code)
- Per-desc data is matched by name or by index, as below. Any lookup of a key the save lacks
  (`dict.Get(key)` or `dict[key]`) fails with "key '%s' is not found in dictionary" (Retail string). In the game
  this shows up as an endless load or a script crash dump. (Code; Game: L275 v35)

## What is saved, and how it is matched

| State | Saved by (desc) | Matched by | Missing in save | Extra in save |
|---|---|---|---|---|
| Joint targets of `prop_truck_constraint_view` | `TruckConstraintsSavablePropDesc` | the saved state **replaces** the one built from the class | see below | see below |
| - `powerConstraints` | array | **index** | index out of range (crash) | index out of range (crash) |
| - `controllableConstraints` | dict | joint **name** | no target until moved; a `constraintChains` link using it crashes (`controlledConstrains.Get`) | target still applied by name; crash if the model lost the joint |
| - `constraintSequentialChains` | dict of chains, list of stages, dict of addon, dict of joint | chain **name**, stage **index**, (addon, joint) **name** | new chain: `RestoreFromSave` `data.Get(chain)` (crash at load). New stage or joint: crash when the chain runs | still applied by name at load |
| Body poses, wheel positions, joint targets | `TruckPhysSystemSavablePropDesc` (native) | body/wheel **index**, joint **name** (layout) | Open | Open |
| Position | `TruckGeomSavablePropDesc` | none (terrain-local position + rotation) | n/a | n/a |
| Fuel | `TruckFuelSavablePropDesc`, `ReserveTankSavablePropDesc` | none (litres) | n/a | clamped to the new capacity (`MinFloat`) |
| Cargo in the body | `TruckStorageSavablePropDesc` | first/second **slot**, cargo key | n/a | removed slot holding cargo: assert / null slot |
| Load volume (dump body) | `TruckLoadVolumeSavablePropDesc` | none (volume, isFull) | n/a | n/a |
| Tie-down cargo | `CargoConstraintSavablePropDesc` | attached actors' save uids | n/a | n/a |
| Steering, handbrake, gear, diff lock, AWD | `TruckInputsSavablePropDesc` | none (`GearState` enum) | n/a | n/a |
| Anchors, grader, log crane, asphalter... | their own desc | one state struct each | n/a | n/a |
| Paint (unique customization) | `TruckCustomizationPropDesc` | the customization desc | n/a | n/a |
| Not saved | lamps, winch connection, damage, wheel wear, blueprint variables, the state of non-sequential `constraintChains` | | | |

Addons are their own savable actors, with the origin `truck_manager_rb_<addon library name>`.

## Rules for an update

**Free to change:** joint speeds, angles, limits, inertia and sounds; stage names, which are matched by index;
physics values; materials, models and lamps; fuel capacity; any blueprint graph. A body or wheel added at the
end of the markup is probably safe; that is Open.

**Must keep its name or position, or the truck must be sold and bought again:**

- the truck identity `<name>` in `auto_<name>_truck_info_<suffix>.sso.resource`. The class file suffix may change;
- the joint name of every controllable constraint and sequential-chain constraint. Renaming one killed the grader
  in the owner's save (Game, case-studies.md);
- the number and order of `powerConstraints`;
- the chain names and the stage count of each sequential chain, and each stage's (addon, joint) set;
- the cargo slots, while `TruckStorageSavablePropDesc` is listed.

**Add only defensively:**

- A new controllable constraint is acceptable on its own. It has no saved target until moved (warning). Do not
  reference it from a `constraintChains` link (error).
- A new sequential chain, a new stage, or a new joint in a stage crashes old saves while
  `TruckConstraintsSavablePropDesc` is listed. Either:
  1. drop `TruckConstraintsSavablePropDesc` from `prop_savable_object.savablePropDescs`. Old saves then load and
     the joints start at their model pose; from then on joint state is not saved (the L275 v35b fix, Build). Or:
  2. ship the change as a new truck identity (a new `auto_<name>_...`). Old saves keep the old truck if it is
     still installed. Otherwise that truck disappears from the save.
- Re-adding `TruckConstraintsSavablePropDesc` later is safe only for saves written while it was absent. A save
  older than the removal still carries the old desc and crashes again.
- A new desc type is fine. Old saves give it the class defaults.

**Never:** remove a savable desc to "clean up" (that state is lost for every save), or reorder `powerConstraints`.

## Check before installing

```text
python -m roadcraft.validate candidate.pak --baseline <installed>.pak --rules save-compat
```

RC077 errors are crashes on existing saves. Warnings mean state that is dropped or that lands on a different
joint. Info lists new descs. The rule runs only with `--baseline`. With a baseline, the exit code counts new
findings only, and every RC077 finding is new. On the L275, a simulated v35 (pre-v35 fixture as the baseline)
gives one error, the new 'Toolboxes' chain, and two warnings for the removed toolbox controllables. The
installed v35b gives one warning: the constraint desc was dropped. (Build)
