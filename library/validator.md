# Static validator: `roadcraft.validate` and the editor schema

`roadcraft.validate` reads a mod and reports what will fail or silently break at runtime, before a build or a
drive. It is read-only and standard-library only. The target can be a source tree (a staged project `p/`, a
`mods_source` tree, or any folder laid out like one) or a built `.pak`. Pak members are read in memory and
kept by (name, occurrence). `roadcraft.schema` supplies the Mod Editor's own type schema: every type, field,
default, range, unit and enum value, with inheritance resolved.

```text
python -m roadcraft.validate <target>... [--json] [--rules r1,r2] [--fail-on error|warning|info] [--game-root DIR]
                                         [--baseline OLDER.pak|tree] [--expand] [--read-fields read_fields.json]
python -m roadcraft.schema dump --output schema.json
python -m roadcraft.schema show prop_truck_wheel.deformEnable     (Type, Type.field or <family>::Type[.field])
python -m roadcraft.schema search suspension
```

Exit codes are:

- **0:** clean: no finding at or above `--fail-on`;
- **1:** a finding at or above `--fail-on` (default `error`). **With `--baseline`, only NEW findings count**:
  a build that still carries old errors but adds none exits 0;
- **2:** a tool error, such as an unreadable target or baseline, an unknown rule or a bad read-fields table.

Every finding carries a stable `code`, the `rule`, its `severity`, the file `path` (`pak!member` for paks) and
`line`, the `key` path inside the file (also emitted as `keyPath`), the `message`, and its `evidence` with the
library grade. Severity `error` means it will fail or silently break at runtime. `warning` means it is likely
wrong. `info` is for review. Type, range and enum findings quote the schema default.

## Output: ids, groups, fix hints and baselines

- **`id`**: 12 hex digits of `sha1(code | member | keyPath)`. `member` is the path inside the mod root, lower
  case, without the pak name or tree prefix. A finding therefore keeps its id across builds, line shifts, pak
  renames and pak-versus-tree targets. The line number and message are not part of it. Findings that share
  all three (several RC051 in one file, rules without a key path) get `-2`, `-3`... in file order.
- **`groups`**: text and JSON group findings by (code, keyPath with list indices normalised: `a[3].b` becomes
  `a[].b`). Each group has its `count`, the number of `members`, the worst severity, the first message and fix
  hint, and the first 3 `locations`. `--expand` lists all of them; `more` counts the rest. JSON also keeps
  the flat `findings` list for tools.
- **`fixHint`** is set where the fix is mechanical: the did-you-mean key (RC053), the enum value (RC055), the
  decimal spelling (RC050/RC051), True/False or quoting (RC052/RC056), and the RC072 replacements.
- **`--baseline <older pak or tree>`** validates both and labels each current finding `status: new` or
  `unchanged` by id. The JSON `baseline` section has `counts` (`new`, `unchanged`, `fixed`),
  `newBySeverity`, the `fixed` findings and their groups. The exit code then follows `--fail-on` on NEW
  findings only.

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
`bro_lint.lint_truck` (rule `bro-lint`, which keeps its own codes) with their model and markup. `lint-bro`'s
**RC075** (warning: a BRO key the generator drops; info: a key that lands in the class where the engine never reads
it) comes from `data/bro_passthrough.json`, see [bro-passthrough.md](bro-passthrough.md). RC076 is `spring-motors`
RC077 is `save-compat` (below; it runs only with `--baseline`), RC078 is `material-type`, RC079 is `wheel-trail`
and RC080 is `body-inertia`; the next free code is RC081.

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
| RC067 | lamps | error / warning | a lamp's lit and unlit states use the same material, or `.mi` files with identical contents; an `<x>_on`/`<x>_off` pair only when NO slot of the pair differs (slots with on = off = base are copied no-ops); warning when no lamp uses the state | Build (D11 beacon); the RC6 fix showed 82 of 83 Goliath beacon slots are no-ops and the real one differs |
| RC068 | lamps | error / info | lamp object hidden by the markup (error); lamp object missing from the model (info: retail ships 10) | Game (L275 v4-v8, cockpit-and-lamps.md) |
| RC037, RC039 | lamps | error, warning | the existing `lamps.lamp_findings` on the compiled blueprint: lit copy shown by the graph but hidden by the markup, or a strobe that hides the unlit lens | Game; cause Inferred |
| RC069 | materials | warning | `advanced.merge_materials = True`; a slot missing from `obj_list.json` while a slot with another preset on the same texture survives (one material per texture per object) | Build/Game (L275 glass, build-pipeline.md); pak_and_assets.md 4.3 |
| RC070 | references | error | link, blob, `.mod` asset, markup `materialName`, `.mi` texture, `nameTpl` or `wheelPool` class that is neither in the mod nor in retail | Build (silent skip by mod_pak_builder; build-pipeline.md) |
| RC071 | duplicates | warning | duplicate pak members with different bytes | Build; Open (which copy loads) |
| RC072 | ignored-fields | warning / info | a key present but never read, or ignored because of a sibling switch (see "Present but ignored" below); info when only an exhaustive reader's `reads` list lacks it | code analysis, static (read_fields.json) |
| RC073 | engine-defaults | info | one per markup: physics bodies that omit `restitution`, `friction`, `angularDamping` or (with `massFromDensity`) `density` get 0.4, 0.5, 0.05, 600 | code analysis, static: `FUN_1430811e0` (physics_semantics.md F2); Retail crawlers omit restitution |
| RC074 | objsettings-gate | info / warning | one info per markup: `objSettings.settings` entries that `exportedVersion` gates off, and entries naming no node of the compiled model (stale); a warning per node with `visibleDefault = False` that renders because the visibility gate is closed and no exporter prefix hides it | code analysis, static; in-game check pending (read_fields.md 3a, `gated`) |
| RC076 | spring-motors | warning | a prismatic `tpl_markup_spring_motor` between two bodies of >= 200 kg whose k·dt²/m and c·dt/m exceed the retail load-bearing maximum 0.38 / 0.68. m is the reduced mass of the two bodies, an upper bound on the row's virtual mass, so the values are lower bounds; dt = 1/60. The message says when the solver's clamp to 1 caps the delivered rate (m/dt²) or damping (m/dt). `__parent` targets are resolved through the `.tpl` tree; hinge springs (inertia not decoded) and `massFromDensity` bodies are skipped | code analysis, static: `FUN_1442406f0`, `FUN_14423aa80`, `FUN_141594b60` (physics_semantics.md 'Spring-motor stability'); Retail: 0 of 62 prismatic springs flagged (9 load-bearing, all TUZ Lynx); Game: Mammoth RC62 (0.86 / 4.0 at the rear heave) shook while parked |
| RC077 | save-compat | error / warning / info | only with `--baseline <installed>`: the candidate's savable descriptors against the baseline's, the names and indices restore looks up. Error: a new `constraintSequentialChains` chain (`RestoreFromSave` `data.Get`), a changed stage count, a joint added to a stage, a changed `powerConstraints` count, a new controllable constraint used by a `constraintChains` link, a removed cargo slot, all while both versions list `TruckConstraintsSavablePropDesc` (or `TruckStorageSavablePropDesc`). Warning: a removed or renamed truck identity (`auto_<name>_truck_info_`), savable desc, controllable constraint, chain or stage joint, a new controllable constraint, a reordered `powerConstraints`. Info: a new savable desc. See [save-compatibility.md](save-compatibility.md) | code analysis, static: `PropSavableObject.SetSavedProps`, `TruckConstraintsSavablePropDesc.LoadData`, `PropTruckConstraintView.RestoreFromSave`, `PropTruckConstraintController` (C:/RC_RE/research/save_semantics.md); Retail: 'key not found in dictionary'; Game: L275 v35 'Toolboxes' hang, grader joint rename |
| RC078 | material-type | error | a `.mi` (pak member or source file) with no `__type` line, an empty `__type`, or a `__type` that names no material template: the retail material library (stems of `material_presets/*.mp`, `master_materials/*.mm`, `.mtl` in the client paks, `retail.material_templates`, cached per installation) or the mod's own `.mp`/`.mm`/`.mtl`. Retail loads **every** `.mi` in a mod pak at startup, linked or not, so one bad instance crashes the game at the main menu (about 40-90 s after launch) with no message. The fix hint names the preset the `.mi.resource` `parents` line gives, else the presets the mod's other MIs use; a near miss gets 'did you mean'. Without retail paks only a missing or empty `__type` is checked (a note says so). An unparsable `.mi` is read for a raw `__type =` line | code analysis, static: `.mi` load job `FUN_14214f0f0` -> `FUN_142979fa0` lookup returns null -> read at +0x48, AV exe+0x214f223; the `.mtl` loader `FUN_14214f880` falls back to `mtl` (C:/RC_RE/research/retail_crash_0x214f223.md); Game: Goliath RC7a's three beacon `.mi` without `__type` (bisected); Retail: retail ships no `.mi` in its paks, the SDK's 37 `root/mods_source` instances (all 14 presets) pass |
| RC079 | wheel-trail | warning | a slot named in `prop_truck_rb.wheelsWithTrail` whose wheel class (via `wheelPool`, parents merged) has a caterpillar trail (`prop_wheel_trail_rb.isCaterpillar = True`) but no model (`geom.nameTpl` absent or empty). Retail puts crawler trails on the sprocket and idler. Non-caterpillar trails on modelless wheels (N&S rail cranes) are not flagged. Hits: KGS-25 x4 (every variant), T-80BVM x4; 0 on the other 15 installed mods | code analysis, static: `prop_truck_rb.ssc` starts caterpillar trails only for `wheelsWithTrail` slots; the native trail update `FUN_1404d56b0` has a branch that runs only on deformable terrain and reads the wheel geom's bounds and tracker (C:/RC_RE/research/physics_semantics.md 'Terrain deformation under wheels'); Retail: 144 of 144 caterpillar trail wheels have a model; Game: every KGS-25 variant crashed the editor engine on deformable terrain only (link to this trait Inferred, not proven) |
| RC080 | body-inertia | warning | a markup body in the mod's own `.tpl_markup` that is a **wheel carrier** (a non-hull body that wheel slots hang on: sprung carrier, axle or bogie body) or **track frame** of any mass, or any body of >= 1 t, whose inertia estimated from its cdt_ shapes (`physics_report` "Body inertia") is far below retail for its role: inertia / mass on the middle body axis (`inertiaPerMass.mid`) below the role floor (hull 0.03, wheel carrier 0.02, track frame 0.01, other bodies 0.003 m^2; about half the retail minimum 0.072 / 0.045 / 0.029 / 0.0067), or, for a carrier, middle-axis inertia below 0.1x the spin inertia (0.5 m r^2) of the wheels it carries (retail minimum 0.447x, the TUZ Lynx steer axles). The message gives the x/y/z inertia, the shape count and extent; the fix hint: enlarge the shapes to the body's real extent (inboard of the wheel keep-out), or keep a COM offset with real-sized shapes. Bodies without a compiled model, bounds table or cdt_ mesh are not judged | code analysis, static: inertia comes from the collision shapes x mass (Havok `buildMassProperties`; physics_semantics.md Q2), `hkCenterOfMassOffset` only moves the centre of mass; Retail: 0 of 481 retail bodies in scope (1,840 bodies with shapes, 124 truck classes, `roadcraft physics inertia`); Game: Mammoth RC68's 9 t front carriers on a 0.3 m cube (135 kg·m², 0.015 m^2, 0.018x the wheel) were "super janky" and a front wheel almost rolled over; RC69 (0.22 x 1.2 x 1.8 m, 0.27 m^2, 0.33x) passes. Hits: RC68 x2 (the front carriers); 0 on the 27 installed paks |

`--rules` takes the rule names: `ps-parse`, `ps-numbers`, `unknown-keys`, `wheel-frames`, `suspension`,
`joints`, `lamps`, `materials`, `references`, `duplicates`, `ignored-fields`, `engine-defaults`,
`objsettings-gate`, `spring-motors`, `save-compat`, `material-type`, `wheel-trail`, `body-inertia` and `bro-lint`.

Not added (2026-10-14): a check for a wheel overlapping its parent body's hulls. It needs per-hull
extents, which were not decoded from `.tpl`/`.tpl_data` then (they are now: the bounds table, RC080 run). A test on hull-node origins inside the wheel
cylinder (with the steering sweep) hits 33 slots on 12 retail trucks, for example roller forks whose
centroid sits at the drum centre without touching it
(`C:\RC_RE\research\springmotor\wheel_hull_survey.py`).

## Present but ignored (RC072)

RC072 reads its tables from `src/roadcraft/data/`:

- `read_fields.json` is a verbatim copy of the research table `C:\RC_RE\research\read_fields.json` (43
  readers, 221 read keys, 24 known-ignored; static analysis of the ModEditor exe and base-game SSL, explained in
  `C:\RC_RE\research\read_fields.md`). Re-copy it when the research file changes; do not edit it here.
- `read_fields_local.json` holds validator-side additions merged on top: fix hints, and wheel
  `substanceFriction` (overwritten by the friction updater, from the coordinator's read of the SSL). Drop an
  entry once the research table carries it.
- `--read-fields FILE` or `ROADCRAFT_READ_FIELDS` replaces both. A legacy `{type key: [fields read]}` mapping is
  still accepted and is treated as exhaustive.
- `read_fields_table.json` in the research folder is only the flat `validatorTable`; it has no ignored or
  conditional sections, so the validator does not use it.

The loader reads these parts of the research schema (`schemaVersion` 1):

- `readers[]`: `typeKey` names the type (`context` and `match` are descriptions; only a `match` written
  `glob:<pattern>` restricts by key path). A reader applies to its type and every subtype (schema chain).
  `reads` keys are known and read: a key the schema lacks but a reader reads (`TplObjSettingsGeom.lighting`,
  `collision`, `render`) is no longer RC053.
- `ignoredKnown` and top-level `ignoredKeys`: RC072 **warning** with the reader's `why`, `evidence`, address
  and grade. This runs before RC053 and before `retail_unknown_keys.json`, which only silences RC053: retail
  carrying a dead key does not make it live.
- `conditional` (reader-level and top-level): the key is ignored only when `ignoredWhen` holds, for example
  `mass` when `massFromDensity` is true, or hinge `angleStart`/`angleEnd` when `limited` is false. A gate key
  that is absent takes the reader's default for it. RC072 **warning** (an entry may set `severity`). Gates
  may also name a root path (`"/objSettings.exportedVersion"`) with operators `eq`, `ne`, `in`, `notIn`,
  `lt`, `le`, `gt`, `ge` and a `default`; `aggregate: "file"` reports one finding per file.
- `gated` (objSettings thresholds) drives RC074, below.
- A key that a reader's `reads` list lacks gives RC072 **info**, but only for readers whose lists are
  exhaustive: the generated native `tplMARKUP` readers (`.tpl_markup::`, `.obj_settings::`, `!global::`), or a
  reader marked `"exhaustive": true`. `.ssl`/`.prop` readers come from native binding tables only; SSL code
  reads the rest, so the first run gave 90 false infos per pak on track-particle keys before this limit.

Three cases are also built in, so they run without the table: position-motor `spring` (`FUN_141594b60`;
fix: move it to a `tpl_markup_spring_motor {spring, damping}`), `lowRangeMultiplier` anywhere (typed walk plus
a raw scan of every class, prop, BRO and markup, with or without the SDK; fix: low range is `lowRangeGear`),
and `spreadAngle` under `WheelParticleMaterialSettings` (`FUN_140cbbfe0`; valid under
`TrackParticleMaterialSettings`; fix: `spreadAngleProb`). When the table is absent, the table-driven part is off and the report's `notes` say so. An
explicit `--read-fields` path that does not exist is a tool error (exit 2).

**Severity against retail.** A dead key that retail carries at the same type key is **info**, with "retail
carries it too (N retail occurrences); harmless unless you expected it to do something": retail's own value is
equally inert, so the author lost nothing. The counts are in `data/retail_ignored_counts.json`, made by
`roadcraft.validate.count_retail_ignored()` over every retail `.cls`, `.prop` and `.tpl_markup` (5,921
members, about 6 minutes). The 2026-10-13 counts include 2,263 wheel-particle `spreadAngle`, 523 wheel
`substanceFriction`, 92 position-motor `spring`, 51 `lowRangeMultiplier` and 100 `density` with
`massFromDensity = False`. A key retail never uses there stays a **warning**. A spec with `keepWarning`
also stays a warning: the position-motor `spring` does, because the author clearly expected a spring. Re-run
the count after a game update or a `read_fields.json` change. Text and JSON group RC072 by key (`*.spreadAngle`)
and severity, so each dead key is one line with its count.

Fix hints the tables supply include: wheel `bodyFriction` and `substanceFriction` ->
`prop_truck_friction_updater.frictionMaterialsList.<material>.frictionValue` / `.substanceFriction`;
spring-motor `tau`/`maxForce`/recovery velocities -> drop them (a spring motor reads only spring and damping);
conditional keys -> set the switch (`massFromDensity`, `limited`, `isMinLimit`, `isBreakable`...) or remove
the key.

## objSettings gate (RC074)

Per read_fields.md 3a (code, consumer `0x1431e6c60`), every per-object `objSettings.settings` entry applies
only when the markup sets `objSettings.exportedVersion`: at least 1 (`CDT`) for any entry and `collision`, 2
(`VISIBILITY`) for `visibility`, and 3 (`MOD_EDITOR`) for `lighting`, `sorting` and `render`. Absent means 0,
nothing sets it implicitly, and 0 of 3,212 retail markups and 0 owner markups set it. Visible effects in mods
come from exporter name prefixes (`cdt_`, `hidden_` add `visibility_hidden`; `name_convention_config.json`).

- One **info** per markup: "objSettings per-object entries are parsed but inert", the count per sub-block, the
  thresholds, and the entries that name no node of the compiled `.tpl` (stale). Fix hint: add the
  `exportedVersion` the entries need, after checking that prefixes do not already give the result.
- One **warning** per node with `visibility { visibleDefault = False }` while the gate is below 2, when the
  node exists in the `.tpl` node table and its name has no hiding prefix. The prefixes come from the game's
  `name_convention_config.json` (`cdt_`, `hidden_`) plus `hp_`, `sfx_` and a leading `_`, which the desktop
  treats as hidden helpers (no exporter rule found for them).
- The rule needs the `gated` table; without it the report's `notes` say it was skipped. The in-game check of
  the gate (a plain mesh with `visibleDefault = False`, without and with `exportedVersion`) is still pending.
- **Game observation (KGS-25, owner drive 2026-10-14):** an 0.8 x 0.62 m dark-material quad named
  `sfx_radiator_haze`, markup `visibleDefault = False` with no `exportedVersion`, was not visible on the rear grille.
  Consistent with the `sfx_` helper prefix hiding it; it does not test the gate, because both would hide it.

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
findings: 133 RC057, 10 RC068, 6 RC064 and 1 RC065. This calibration predates RC072-RC074. Retail now
also gets RC072 warnings for its dead keys (F1 counts 2,235 wheel `spreadAngle` and 52 `lowRangeMultiplier`)
and RC073 info on its crawler markups. Retail sets no `exportedVersion` either, so RC074 would report its
objSettings entries too. The retail run has not been repeated.

## What it found on the owner's mods (2026-10-13)

The run covered 7 installed paks (`root\mods`), 17 paks on `\\192.168.0.129\mods` and two source trees: D11
Goliath RC5 `p/` and the SDK's `root\mods_source`. Each pak took 0.6-5 s (650 MB `mammoth.pak` over the share:
2.8 s). Only the members that are needed are read.

| Target | Errors | Warnings | What |
|---|---|---|---|
| goliath_d11.pak (installed, share), D11 RC5 `p/` | 6 | 6 | **RC070**: the idler wheel markups (`gd11_wheel_front/rear`, all three variants) name `mod_goli_d11_idler_front_restored` / `_rear_restored`, but no such `.mi` is in the pak, the source or retail. The engine substitutes a missing material (`Materials.AllowMissingMaterials`). **RC067** (withdrawn by the state-pair fix): `d11_beacon_on`/`_off` are identical in 82 slots of each body markup, but those are no-ops and the one real beacon slot differs. **RC039**: the automatic beacon's timer hides `d11t_beacon_off_vis`, the unlit lens. |
| roamer105_expedition.pak (share) | 0 | 286 | RC053: 26 `objSettings.settings.<object>.lighting` blocks per markup, in 11 variant markups. Superseded: the exe reads `lighting`, but the objSettings gate leaves it inert (RC074, below). |
| walle.pak | 0 | 4 | RC053: `prop_truck_wheel.bodyFriction` is not a wheel field (4 wheel classes). |
| apoc_buggy.pak | 0 | 1 | RC039: the Engine graph's timer hides `gauge_lights`, `reflector_headlights` and `tail_lights`, which init leaves visible. |
| SDK `root\mods_source` (TUZ sample) | 3 | 6 | **RC066** (twice): the `marker_lights` lens is on slot `marker_lights_mat`, whose state is `lights_emmissive`, while the lamp switches `lights_emissive`. **RC001** (lint-bro): `suspensionCollection` without `useSuspensionCollection`. Plus RC002 and 3 RC053 that the sample ships. |
| jimny, kgs25, roamer105ute, watcher_y61, dumptwuck, grader_16m3, hitachi_ex5600, kanga25, l275_minespec, lada_niva, mammoth, red_forklift_35, t80bvm, test_crawler, warthog_m12, wl994_loader | 0 | 0 | info only: RC057 (a camera distance of 0.01 m under the UI minimum of 1; retail ships it); kanga25 has RC064 info (`BoneTower_cdt` locked hinge driven by a motor) |

Totals:

- installed paks: 6 errors, 11 warnings, 9 info;
- share paks: 6 errors, 297 warnings, 30 info;
- source trees: 9 errors, 12 warnings, 3 info.

### Re-run with RC072 tables, RC073, RC074, the RC067 fix and the new output (2026-10-13)

The same 24 paks were re-run with `data/read_fields.json` (research copy with the `gated` table, sha256
4906b3ed...), `read_fields_local.json`, `retail_ignored_counts.json`, RC073, RC074 and the RC067 state-pair
fix. Counts are errors/warnings/info:

| Set | Before | After | Groups after |
|---|---|---|---|
| installed paks (7) | 6/11/9 | 6/20/155 | 32 |
| share paks (17) | 6/297/30 | 6/55/456 | 80 |

By code after (installed + share):

| Code | Error | Warning | Info |
|---|---|---|---|
| RC070 | 6 + 6 | | |
| RC039 | | 4 + 4 | |
| RC072 | | 16 + 29 | 131 + 379 |
| RC074 | | 0 + 22 | 6 + 18 |
| RC057, RC064, RC073 | | | 18 + 59 |

Errors are unchanged. The changes:

- **RC053 drops by 294.** Roamer 105 Expedition's 286 `lighting` warnings are gone (the exe reads
  `lighting`), and WALL-E's 4 `bodyFriction` warnings per copy become RC072 with the friction-updater fix hint.
- **RC067 drops by 6.** The Goliath beacon warnings are gone: each body markup has one beacon slot that differs.
- **RC072 warnings** (45) are the keys retail does not carry: position-motor `spring` 37 (Goliath 12 per copy,
  grader 10, t80bvm 2, mammoth 1) and WALL-E `bodyFriction` 8. **RC072 info** (510) are retail-carried dead
  keys: 336 wheel-particle `spreadAngle`, 142 wheel `substanceFriction`, 26 `lowRangeMultiplier` and 3 mammoth
  `density`, plus 3 `overrideCenterOfMass` on mammoth bodies, which the body reader `0x1430812a0` never looks up.
- **RC074** (24 info, 22 warnings): one info per markup that has objSettings entries (Roamer 105 Expedition
  11, Goliath 3 per copy, and 1 each for jimny, roamer105ute, watcher_y61, dumptwuck, kanga25, lada_niva and
  the share copy of kgs25). The warnings are all Roamer 105 Expedition: `r105_mod_105_cockpit` and
  `r105_mod_105_windshield` in each of 11 markups are meant hidden but render. Its stale entries are
  `marker_lights`, `mirror_left_case`, `mirror_right_case`, `reflector_headlights`, `stop_lights` and three
  `hp_` helpers.
- **RC073**: one info per markup with physics bodies.

Grouping turns Goliath's 144 findings into 10 groups and Roamer's 77 into 6. Per-pak JSON in the new format
is in `\\192.168.0.129\Downloads\roadcraft_laptop_research\validate\`: `<pak>.json` for the share paks and
`installed_<pak>.json` for `root\mods`.

None of the wheel-frame, suspension or joint-limit errors fire on the owner's current paks. The Warthog and
Lada faults those rules encode were fixed in earlier builds. The SDK sample still carries both the
missing-flag fault and the misspelt lamp state, so a mod copied from it is caught.

### RC078 run (2026-10-14)

`roadcraft validate --rules material-type` over the 7 installed paks (apoc_buggy, goliath_d11, jimny, kgs25, roamer105ute, walle, watcher_y61_expedition; 392 `.mi`), the 20 paks on `\\192.168.0.129\mods` (749 `.mi`) and the SDK's `root/mods_source` (37): 0 hits. The RC7a pak (`ba3f2ded...`) is deleted; the RC7 source tree with the three beacon `__type` lines removed (the RC7a state) gives exactly 3 errors, `mod_goli_d11_beacon_{body,lens,lit}.mi`, with fix hints `vehicle_body`, `vehicle_glass_outer`, `vehicle_lights` from their `.mi.resource` parents. Every `__type` in all of those paks names a retail preset (none names a master material, another `.mi`, or a mod-defined preset). Whether the library also accepts another instance's name is not known (Open): such a `.mi` is reported.

### RC080 run (2026-10-14)

Calibration: `roadcraft physics inertia` (all 124 retail truck classes, 1,840 bodies with cdt_ shapes) puts
the lowest retail values per role at: hull 0.072 m^2 (the `scout_pz14_prot` chassis; the next is 0.41),
wheel carrier 0.045 (Menzi A91 wheel segments), track frame 0.029 (EPEC LT200 rockers, 500 kg), jointed
bodies of >= 1 t 0.0067 (Vostok ATM53 dumper spring, Invictus Type-A cabin); carried-wheel ratio 0.447x (TUZ
Lynx steer axles). Each floor is at most half of that minimum, so retail gives 0 hits; a guard test
(`tests/test_body_inertia.py`) re-checks this on the installed game.

The middle axis is used, not the smallest: a rod-like body legitimately has almost no inertia about its own
length (the MTK 2006 front suspension is 0.033x its wheels on that axis, 0.0065 m^2), while a token cube is
soft about every axis. The retail 5th percentile was considered as the floor, but it would flag about 5 %
of retail by construction.

| Target | RC080 |
|---|---|
| `mammoth_rc68_twostage_5be91383.pak` (bench share) | 2: `BoneSuspFrontLeft_cdt`, `BoneSuspFrontRight_cdt` (135 kg·m², 0.015 m^2, 0.018x the wheel) |
| `mammoth_rc69_seriesspring_6cfd86f5.pak` (bench share) | 0 (front carriers 3510 / 2466 / 1116 kg·m², 0.27 m^2, 0.33x) |
| the 20 paks on `\\192.168.0.129\mods` and the 7 in `root\mods` | 0 |

Per-hull extents are now decoded (the `.tpl` bounds table, physics-report.md "Body inertia"), so the
wheel-against-hull check listed as not added under "Rules and codes" no longer lacks its input (not built).

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
- RC072 is as complete as `read_fields.json`. Keys of `.ssl`/`.prop` types outside its `ignoredKnown` lists
  are not judged, because those reads lists are partial.
- RC073 judges the markup as written plus its `.lods_base`. Bodies the engine creates (wheels) have no markup
  block and are not counted.

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
