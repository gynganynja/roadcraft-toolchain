# BRO pass-through: what reaches the compiled class

The class generator (the Mod Editor's "Bro Generator") does not copy a truck BRO into the compiled `.cls` key for key. It is C# code, compiled into `root/prebuild/bro/Bro.Compiled.dll`: `TruckGenerator`, `WheelGenerator` and `BroGeneratorUtils`. Each class value is written by an explicit statement. Some values are renamed, some scaled, some gated, and the rest are ignored.

This article says what that means for a modder. The data is in `src/roadcraft/data/bro_passthrough.json`, used by lint **RC075**. The full per-field table comes from `roadcraft/bro_passthrough.py` (see Reproduce).

Evidence:

- The 121 retail truck/class pairs, compared field by field.
- The decompiled generator code.
- The engine-read tables (`read_fields.json`, the SSL schema and the SSL source).

All of it is static. Nothing was launched.

## Rules

1. **Keys that are not BRO fields are silently dropped, along with everything under them.**
   - The BRO loader keeps an unknown key as an untyped node. The editor shows it and the build does not fail.
   - The generator reads C# fields (`FieldsSerializer.LoadFields` → `FindChild(field.Name)`), so it never sees the key.
   - `meta_desc_bro.ps` matches the DLL exactly. A key that `schema.json` does not declare for a `.bro` type is dead.
2. **Raw sections are copied verbatim, unknown keys included.**
   - These are the C# fields typed `ModelWrapper`: SSL/prop subtrees such as `gearbox`, `trackControls`, camera presets, blueprints, `propVFX` and `effects.propSfx`.
   - The engine still decides what it reads. For example, `gearbox.params.lowRangeMultiplier` lands in the class and is read by nothing (`read_fields.json`).
3. **Values equal to the class default are not written.**
   - The `ModelWrapper.Value` setter skips an unchanged value, and the `.cls` keeps changed values only. The engine falls back to the same default.
   - This is why `softForceScale = 1` (the default of `prop_truck_wheel`) never appears in a class. It is not a bug.
4. **Typed fields are copied one by one.** Many are renamed (`suspensionCollection` → `prop_truck_rb.suspensionAxleCollection`, `wheelSlots` → `wheelSlotWithDescs`), and some are transformed or gated (below).

## Dropped keys donors carry (RC075 warning)

These retail keys have no field on the generator's class, so copying a retail BRO brings them along for nothing:

- `UiInfo.uiMediumIcon`, `UiInfo.parkingSlotSize`, `UiInfo.price`
- `FuelSettings.isEnabled`. A fuel tank cannot be disabled this way.
- `TruckWheel.trackOverlay`
- `Truck.propSfx`. Use `effects.propSfx`.
- `Wheel.isCaterpillarWheel`. The field is `isCaterpillar`.
- `Wheel.shouldCreateTrail`
- `WinchSettings.modifyDamping`
- `ConstraintsControllerSettings.isNewController`
- `CargoConstraint.beltsOffset` / `constraintLinearLimit` / `constraintAreaOffset`
- `LoadVolumeSettings.sandQuantity` / `density` / `volumeScale` / `canBeUplifted`
- `CraneSettings.isAnchorsEnabled` / `isMultiWinch` / `amountOfWinches`
- `UniversalAction.type` / `constraintName` / `stateName`
- `Truck.rentSettings` and everything inside it
- the `Chassis*` `towing*` keys

## Generator switches and gates

- **`useSuspensionCollection`.**
  - Without `useSuspensionCollection = True`, `suspensionCollection` is dropped, together with the slots' `suspensionCollectionItem` indices. Lint RC001 catches this.
  - The flag itself is never written.
  - A slot gets `suspensionCollectionAxleIndex` only when its `suspensionCollectionItem` names an existing item.
- **`isPhysicsWheel`.** With `truckWheel.isPhysicsWheel = False`, the whole `prop_truck_wheel` block is skipped: radius, width, mass, friction and soft contact.
- **Module `isEnabled` flags.** A module's settings are written only while its `isEnabled` is true: `craneSettings.isEnabled`, `loadVolumeSettings…`, `trenchDiggerSettings.isEnabled` and so on. Keys of a disabled module look dropped in the class.
- **`staticTruckAxisControls[]`.**
  - `actionType`, `strenghtFactor` (BRO spelling) → `actionData.strengthFactor`, `canWorkWithEngineOff` and `canWorkUnderWater` are written only when `actionType` is set.
  - `inputLink` and `axisDirectionType` are copied raw.

## Transforms

| BRO field | class value |
|---|---|
| `TruckWheel.width`, `radius`, `rimRadius` | × `wheelPool.<pool>.scale` (`geomRadius` = unscaled radius; trail width also × `trailWidthScale`) |
| `HarvesterFindTreeSettings.treeAttachAngle` | × 0.5 (retail pairs) |
| `TruckMobileSandScreenSettings.allowedPercent` | / 100 |
| `SelfMaintenance.selfMaintenancePeriodSec` | × 1000, int (ms) |
| `RoadPlanning.showPlanRadius`, `showZonesRadius` | squared |
| `TrailSettings.trailHeight` | −h / 2 |
| `CargoConstraint.beltBonesOffset` | ≤ 0 becomes 0.1 |
| `TruckSettings.diffLock` | `"ALWAYS"` / `"DEFAULT"` |
| `TruckSettings.enableLateralForce` | per slot, `enableLateralForceOverride` wins when `isEnableLateralForceOverride` |
| `LwiActorPoiSettings.poiRadius`, `interactiveActivationRadius` | replaced by `baseTruck*` when that is ≥ 0 |

## In the class, never read by the engine (RC075 info)

- `LoadVolumeSettings.maxHeightFromTerrain` / `openingDelay`
- `LoadVolumeHydraulicLidSettings.lidOpenState` / `lidCloseState`
- `CargoConstraint.left/rightMidpointBoardXOffset`
- `DamageDispatcherSettings.truckCabinBone`

Each is an SSL `var` that nothing references. `lowRangeMultiplier` and wheel-particle `spreadAngle` are already RC072.

## Reproduce

```
python -m roadcraft.bro_passthrough --schema C:\RC_RE\research\schema.json ^
    --generator-src C:\RC_RE\bro_passthrough\decomp_bro --ssl-src C:\RC_RE\physics\ssc\ssl ^
    --reference bro_ref.json --out passthrough.json --lint-table src\roadcraft\data\bro_passthrough.json
```

`--generator-src` is the safedecomp output of `root\prebuild\bro\Bro.Compiled.dll`. Without it, only the empirical comparison runs. The output is deterministic.

To check a mod: `roadcraft lint-bro <truck.bro>`. RC075 findings name the key and the reason.
