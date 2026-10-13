# Static validator: `roadcraft.validate` and the editor schema

`roadcraft.validate` reads a mod and reports what will fail or silently break at runtime, before a build or a
drive. It is read-only and standard-library only. The target can be a source tree (a staged project `p/`, a
`mods_source` tree, or any folder laid out like one) or a built `.pak`. Pak members are read in memory and
kept by (name, occurrence). `roadcraft.schema` supplies the Mod Editor's own type schema: every type, field,
default, range, unit and enum value, with inheritance resolved.

```text
python -m roadcraft.validate <target>... [--json] [--rules r1,r2] [--fail-on error|warning|info] [--game-root DIR]
                                         [--read-fields fields.json]
python -m roadcraft.schema dump --output schema.json
python -m roadcraft.schema show prop_truck_wheel.deformEnable     (Type, Type.field or <family>::Type[.field])
python -m roadcraft.schema search suspension
```

Exit codes are:

- **0:** clean;
- **1:** a finding at or above `--fail-on` (default `error`);
- **2:** a tool error, such as an unreadable target or an unknown rule.

Every finding carries a stable `code`, the `rule`, its `severity`, the file `path` (`pak!member` for paks) and
`line`, the `key` path inside the file, the `message`, and its `evidence` with the library grade. Severity
`error` means it will fail or silently break at runtime. `warning` means it is likely wrong. `info` is for
review. Type, range and enum findings quote the schema default.

Context comes from the installation (`--game-root`, `ROADCRAFT_GAME_ROOT` or the Steam path):

- the meta descs, for the schema;
- the retail pak index (`roadcraft.retail`). It uses the override-manifest approach: a tag is `res://` plus the
  lower-case member path.
- retail classes, models and markup presets.

Without an installation, the schema and retail checks are skipped and the report's `notes` say so.

## Schema (`roadcraft.schema`)

The schema is built the way the editor builds it. The sources are `meta_desc.ps`, `meta_desc_ssl.ps` (each SSL
class is also registered under its brand, for example `PropTruckWheel` becomes `.prop::prop_truck_wheel`) and
`meta_desc_bro.ps`. `tools/bin/ModEditor/meta_desc_ssl_overrides.ps` is deep-merged into the SSL descriptions,
and the project override and user files are merged too when present. Descriptor blobs and links come from
`resources_schema.yaml` inside `resources.pak`. The full derivation is in `C:\RC_RE\research\schema.md`
section 1 (**SDK**, from the decompiled editor).

`dump` writes deterministic JSON: sorted keys and no timestamp. Its layout is that of the research prototype
`C:\RC_RE\research\dump_schema.py`, and on the 2026-10-13 SDK it is identical type for type. The counts are:

- 24,382 types;
- 27,763 declared fields, and 264,406 with inheritance;
- 98 resource descriptor types.

`tests/test_schema.py` asserts these counts when the SDK is installed. The schema is cached in-process until a
source file changes. A load takes about 1.6 s.

`show` and `search` print a field's type, default, range, units, enum values and caption. They also print
`serialisedTo`, the file where values of the type are written. For example:

- `.prop` types are component sections under a `.cls` `properties` block;
- `.ssl` types are sections nested by `__type`;
- `.tpl_markup` types are written to markup files (constraints, motors and bodies under `objectInfos[]`).

Ranges and units are UI hints. The editor does not enforce them on load (**SDK**).

The editor-faithful PS reader is `ps_format.editor_loads`. The lenient `ps_format.loads` accepts exponents and
reads `.5` as 0.5. The editor reader does neither: it reproduces the editor parser's quirks and records the line
of every key.

## Rules and codes

The codes continue `lint-bro`'s RC001-RC048. `.bro` truck files in a source tree are also passed through
`bro_lint.lint_truck` (rule `bro-lint`, which keeps its own codes) with their model and markup.

| Code | Rule | Severity | Catches | Evidence (grade) |
|---|---|---|---|---|
| RC049 | ps-parse | error | file the Mod Editor cannot parse | Ps.Parser (SDK, schema.md 2) |
| RC050 | ps-numbers | error | exponent `1e-05` (parse error; in `[ ]` it becomes `[1, "e", -5]`), number followed by letters | SDK |
| RC051 | ps-numbers | error | leading dot: `.5` is read as 0, `.25` as 0.5 | SDK |
| RC052 | ps-numbers | warning | bare `on/off/yes/no` read as a bool | SDK |
| RC053 | unknown-keys | warning | key not in the schema, with "did you mean"; the editor keeps it as a removed-field hint | SDK; that the engine ignores it is Inferred |
| RC054 | unknown-keys | error | `__type` or `.cls` component not found | SDK |
| RC055 | unknown-keys | error | enum value not allowed (for example `torqueType = "default"`) | SDK; Game (Roamer 105, truck-settings.md) |
| RC056 | unknown-keys | error | value type mismatch (a bare word became a bool in a string field) | SDK |
| RC057 | unknown-keys | info | value outside the UI range | SDK |
| RC058 | wheel-frames | error | `geomName`/`parentFrame`/`customSteeringJointObjName` not a model node | Build (lint-bro RC023) |
| RC059 | wheel-frames | error | mirrored (left-handed) slot frame | SDK (tplexp right-handed assert); Retail: none in 306 trucks |
| RC060 | wheel-frames | error | `isRightSided` disagrees with the slot side for some slots but not others (wheels inside out) | Game (buggy, Lada; symptoms.md); Retail: 279 trucks consistent, 8 uniformly reversed, none mixed |
| RC061 | wheel-frames | error | steering knuckle outside or across its wheel | Game (buggy; suspension-and-wheels.md); Retail: kingpins 0.16-0.37 m inboard, none outboard |
| RC062 | wheel-frames | error | `deformEnable` wheel model without a `tire` object | Game (Lada v1 crash, symptoms.md) |
| RC063 | suspension | error | wheel slots with neither `suspensionAxleCollection` nor `suspensionSet`; axle index or `suspensionCollectionMap` out of range | Game (Warthog; suspension-and-wheels.md); Retail (below) |
| RC064 | joints | error / info | prismatic or wheel limits that exclude the rest pose, min > max, invalid six-dof angular combination, ragdoll ranges; info when a position motor drives a hinge with a zero range | SDK (schema.md 7.3); Retail survey |
| RC065 | joints | error / info | joint or IK body with a mirrored frame (wrong-handed axes), a `target` or body the model lacks; info for a duplicate joint name | Game (KGS25 sideways telescope, frames.md); SDK; Retail |
| RC066 | lamps | error | lamp state with no material: a misspelt markup state (`lights_emmissive`), or a lamp object whose slot lacks the state (per object when `tpl/obj_list.json` is present) | SDK/Retail (cockpit-and-lamps.md) |
| RC067 | lamps | error / warning | lit and unlit states use the same material, or `.mi` files with identical contents; warning when no lamp uses the state | Build (D11 beacon) |
| RC068 | lamps | error / info | lamp object hidden by the markup (error); lamp object missing from the model (info: retail ships 10) | Game (L275 v4-v8, cockpit-and-lamps.md) |
| RC037, RC039 | lamps | error, warning | the existing `lamps.lamp_findings` on the compiled blueprint: lit copy shown by the graph but hidden by the markup, or a strobe that hides the unlit lens | Game; cause Inferred |
| RC069 | materials | warning | `advanced.merge_materials = True`; a slot missing from `obj_list.json` while a slot with another preset on the same texture survives (one material per texture per object) | Build/Game (L275 glass, build-pipeline.md); pak_and_assets.md 4.3 |
| RC070 | references | error | link, blob, `.mod` asset, markup `materialName`, `.mi` texture, `nameTpl` or `wheelPool` class that is neither in the mod nor in retail | Build (silent skip by mod_pak_builder; build-pipeline.md) |
| RC071 | duplicates | warning | duplicate pak members with different bytes | Build; Open (which copy loads) |
| RC072 | ignored-fields | warning | a field the component's loader does not read. This is a hook only: pass `--read-fields {type: [fields]}` | Needs code evidence (C:\RC_RE\research\physics_semantics.md) |

`--rules` takes the rule names: `ps-parse`, `ps-numbers`, `unknown-keys`, `wheel-frames`, `suspension`,
`joints`, `lamps`, `materials`, `references`, `duplicates`, `ignored-fields` and `bro-lint`.

## How the rules were tuned against retail (2026-10-13)

The bar was zero warnings on content shaped like retail. Each rule was run over every retail truck class in
`default_other.pak` (306 with wheel slots, 1,126 classes), every vehicle markup and model (3,208 markups) and
the retail BRO pak (1,336 files).

- **Unknown keys.** The SDK meta descs lag the game build. Retail ships 54 class and markup keys and 542 BRO
  keys that the schema lacks, among them `TruckGearboxParams.lowRangeMultiplier`,
  `WheelParticleMaterialSettings.spreadAngle`, `tpl_markup_position_motor.spring`, the spring motor's `tau` and
  `maxForce`, `RbVehicleCameraParams.elasticBoostX/Z`, and `TplObjSettingsGeom.collision`/`render`. They are listed
  in `src/roadcraft/data/retail_unknown_keys.json` and not reported. This corrects schema.md 8, which took
  `lowRangeMultiplier`, `spreadAngle` and the position motor's `spring` for D11-only keys (**Retail**).
  Regenerate the list after a game update.
- **Local types.** `local__xxx` types (a field's own `__types`) and builtin kinds resolve as opaque, not as
  "Type not found".
- **Hinge limits.** Retail ships hinge limits with `angleEnd < angleStart` (146 constraints), intervals under
  5 deg (49) and zero ranges (8, among them motor-driven locks such as the tree crusher's stump grinder). So the
  Y61 "min interval 5" story is not a general rule. The hinge check only reports a zero range driven by a
  position motor, as info.
- **Joint names.** Duplicate joint names occur once in retail (Junttan PM20 `frame_piston_l`), so they are info.
- **Lamps.** Retail models carry their lamp states inside the compiled `.tpl` and have no markup `materials`
  block, so the lamp-state check applies only to markups that use `dynamicMaterials` (the Blender route).
  RC038 (a lit copy that init leaves visible) is left out because retail ships it (ZiKZ 605E scalper). Missing
  lamp objects are info because retail ships 10.
- **Suspension.** Only 106 of 306 retail truck classes have `suspensionAxleCollection`. The rest use
  `suspensionSet` (tracked). The only classes with neither are the SDK sample `auto_tuz_119lynx_mod` and
  `auto_simplest_vehicle`, so RC063 has two expected retail hits, both errors.
- **Merged materials.** A built pak has no `obj_list.json`, and the compiled `.tpl` strings are not a reliable
  material list: the Goliath model lacks names that its source `obj_list.json` lists. RC069's per-texture check
  therefore runs on source trees only. Unused slots in copied markups are harmless and are not reported.

Result: retail gives 0 warnings. The only errors are the 2 SDK sample classes (RC063). There are 150 info
findings: 133 RC057, 10 RC068, 6 RC064 and 1 RC065.

## What it found on the owner's mods (2026-10-13)

The run covered 7 installed paks (`root\mods`), 17 paks on `\\192.168.0.129\mods` and two source trees: D11
Goliath RC5 `p/` and the SDK's `root\mods_source`. Each pak took 0.6-5 s (650 MB `mammoth.pak` over the share:
2.8 s). Only the members that are needed are read.

| Target | Errors | Warnings | What |
|---|---|---|---|
| goliath_d11.pak (installed, share), D11 RC5 `p/` | 6 | 6 | **RC070**: the idler wheel markups (`gd11_wheel_front/rear`, all three variants) name `mod_goli_d11_idler_front_restored` / `_rear_restored`, but no such `.mi` is in the pak, the source or retail. The engine substitutes a missing material (`Materials.AllowMissingMaterials`). **RC067**: `d11_beacon_on`/`_off` are identical in 82 slots of each body markup (no lamp uses them). **RC039**: the automatic beacon's timer hides `d11t_beacon_off_vis`, the unlit lens. |
| roamer105_expedition.pak (share) | 0 | 286 | RC053: 26 `objSettings.settings.<object>.lighting` blocks per markup, in 11 variant markups. `lighting` is not a `TplObjSettingsGeom` field and neither retail nor the SDK sample uses it, so it is probably ignored (**Open**: no member references `tplMARKUP_OBJ_SETTINGS_LIGHTING`). |
| walle.pak | 0 | 4 | RC053: `prop_truck_wheel.bodyFriction` is not a wheel field (4 wheel classes). |
| apoc_buggy.pak | 0 | 1 | RC039: the Engine graph's timer hides `gauge_lights`, `reflector_headlights` and `tail_lights`, which init leaves visible. |
| SDK `root\mods_source` (TUZ sample) | 3 | 6 | **RC066** (twice): the `marker_lights` lens is on slot `marker_lights_mat`, whose state is `lights_emmissive`, while the lamp switches `lights_emissive`. **RC001** (lint-bro): `suspensionCollection` without `useSuspensionCollection`. Plus RC002 and 3 RC053 that the sample ships. |
| jimny, kgs25, roamer105ute, watcher_y61, dumptwuck, grader_16m3, hitachi_ex5600, kanga25, l275_minespec, lada_niva, mammoth, red_forklift_35, t80bvm, test_crawler, warthog_m12, wl994_loader | 0 | 0 | info only: RC057 (a camera distance of 0.01 m under the UI minimum of 1; retail ships it); kanga25 has RC064 info (`BoneTower_cdt` locked hinge driven by a motor) |

Totals:

- installed paks: 6 errors, 11 warnings, 9 info;
- share paks: 6 errors, 297 warnings, 30 info;
- source trees: 9 errors, 12 warnings, 3 info.

None of the wheel-frame, suspension or joint-limit errors fire on the owner's current paks. The Warthog and
Lada faults those rules encode were fixed in earlier builds. The SDK sample still carries both the
missing-flag fault and the misspelt lamp state, so a mod copied from it is caught.

## Library failures and how far the rules reach

- **Inside-out wheels** (symptoms.md, suspension-and-wheels.md). RC059 and RC060 catch mirrored slot frames
  and side flags that disagree between slots. The Lada showed that handedness is decided by the wheel model's
  native rim frame, which needs runtime measurement. A static check cannot prove the rim faces out, so a wheel
  asset authored the wrong way round with consistent slots is not caught (**Open**).
- **Knuckles outside the wheel.** RC061 checks the geometry. That a missing steering rack is the cause is
  **Open** in the library, so it is not checked.
- **Missing `useSuspensionCollection`.** RC001 checks the BRO and RC063 the compiled class.
- **Lit lamp copies hidden by the markup.** RC068 checks the lamps' own objects. RC037 checks the blueprint's
  shown objects (`lamps.lamp_findings` composed).
- **Wrong-handed joint frames.** RC065 checks for a negative determinant on the jointed or IK body. The KGS25
  fault, a valid rotation about the wrong axis (`childRotation [0,-90,0]` on a prismatic), cannot be judged
  without the intended axis. Retail gives no basis for an angle threshold, so that case is not checked
  (**Open**).
- **RC54 spawn/save failure and the L275 cargo-unit fix.** Neither is documented in this library, in
  `C:\RC_RE\research` or in the development package (searched 2026-10-13), so no rule implements them. The
  closest documented spawn/save failure is "Vehicle bought under an older build is dead" (a joint added or
  renamed; truck-settings.md). Catching it needs a comparison of joint names against the previous release,
  which is not implemented. Record the two stories in the library before encoding them.

## False positives and limits

- RC053 depends on the retail allow-list. A key that only non-truck retail content uses (scenes, props) can
  still be reported. Add it to `data/retail_unknown_keys.json` with its retail evidence.
- Instance types are opaque, and their members are not checked. This covers types defined by mod or retail
  files that carry SSL code (`#ssl_begin`), and mod `.sso` classes found by their brand name.
- The node tables come from `tpl_reader`. Six retail models do not decode, and the wheel and joint checks skip
  them.
- RC069 needs the source tree's `tpl/obj_list.json`.
- No rule decides whether a field is read at runtime. Fields "present but ignored" need the per-component
  read-field table from code (RC072 hook).

Evidence: scratch runs of 2026-10-13 (retail calibration, `final.json` for the owner's mods). The tests are
`tests/test_validate.py` (one synthetic fixture per rule, a pak, the CLI contract, SDK-gated checks on the TUZ
sample) and `tests/test_schema.py`.

## Code changes in the vehicle-authoring-library merge

Merging `origin/vehicle-authoring-library` (dea0605, 3649aa4) into `feature/headless-editor`
(2026-10-13) renumbered **no** lint codes. The desktop branch's code (`bro_lint.py`, `ps_format.py`,
`vehicle.py`, `library.py`, `retail.py`, `tpl_reader.py`, `cli.py`) is the same as the version this
branch already carried from origin/main, and it assigns only RC001-RC005, RC010-RC013, RC020-RC024 and
RC030-RC032, each with the same meaning here. Nothing on the desktop side uses RC033-RC072, so its
references stay valid unchanged. RC048 keeps its code and severity; only its rationale and message
changed (superseded mass-scaling claim, see tracked-vehicles.md).
