# Animated parts: model clips and blueprint graphs

How a mod makes parts move on their own or on a key press — a head that looks around, eyes, antennas,
wipers — without custom script code. Source: WALL-E, 2026-10-11 (SDK sources, the 1126 shipped truck
classes, an offline compile test, two editor-bench runs of the built mod; candidate walle-r6 installed,
not yet seen by the owner in the game).

## Custom SSL code: not a distributable route yet

The Mod Editor contains a working SSL compiler: an isolated new class loaded and ran in editor play mode
once its resource tag was registered, but normal binary loading asserted on the missing `_debug.sslbin`
and no tool produced one (Game, editor probes 2026-10-05; build-pipeline.md "SSL source loading is separate
from distributable script output"). Shipped scripts are compiled `.sslbin`. Use the data-driven routes
below; do not ship editor-only source loading or change global script settings.

## Route 1: clips in the model, played by the truck's blueprint

| Rule | Grade |
|---|---|
| The SDK Blender exporter writes object and bone animation: each Blender Action becomes one clip named after the Action (text before a `|`), sampled at 30 fps; Blender 5 layered actions are read. It runs only with `anim_on = True` in the export options' `fbx` block (WALL-E's compile script had `False`) | SDK (`blender_to_usf_script/.../usf/misc.py`, `animation.py`, `node.py`) |
| `tplexp` keeps them: the compiled folder gains `anim_list.json` (clip names) and the `.tpl` holds the clip and bone names | Build (2026-10-11: a 3-bone test rig with `look_left` / `look_right` through the WALL-E export route) |
| The class gets `prop_animation_controller = { controller = { animations = [ { animation = { tplAnimationName = "<clip>", __type = "AnimationInfoTpl" }, loop = False, playing = False, speed = 1, blend = "ADDITIVE" }, ... ], updateEvents = True, __type = "AnimationController" } }`. `blend` is `INTERPOLATED` (default) or `ADDITIVE`; `weight`, `speed`, `loop` (default true) and `onEnd` (`Stop`, which removes the clip's influence, or `Pause`, which holds the last pose) per clip | SDK (`animation_controller.ssl`), Retail (Minuteman K370 explorer: wipers, `antena_fold`/`antena_unfold` additive, looping `radar_spin`) |
| Clips in shipped trucks: `wipers_forward` / `wipers_backward` (181 trucks), mixer drums, antenna fold/unfold, radar spin, outrigger legs, the Alces PL30C `hummer_anim` | Retail (survey of 1126 classes) |
| Play a clip from the blueprint with `BlueprintNodeTplAnimStart` (`animUidRef = { def = "<clip>", __type = "StringRefParamTplAnimationController" }`, optional `actorRef = { def = "<OWNER>" }`); listen with `BlueprintNodeTplAnimOnBegin` / `OnEnd` (by animation index). All three are `typemask("$mods")` | SDK, Retail |
| Class resource links of a truck that does this (K370): `ssl/animation/prop_animation_controller.prop`, `ssl/animation/animation_controller.ssl`, the four `ssl/ssl/lib/blueprint/animation/blueprint_node_tpl_anim_*.sso` and the libraries its graph uses | Retail |

## Triggers and logic available to a mod graph

| Need | Node (all mod-usable; `$mods` where the source marks it) | Grade |
|---|---|---|
| Player key | `BlueprintInputLibraryInputcheck` with `input = { cmd = { devices = [ { deviceType = "keyboard", shortcuts = [ { keys = [ N ] } ] } ] }, __type = "InputActionHold" }`, output `IsOn` (K370 antenna, Alces hummer, wipers) | Retail |
| Vehicle events | `OnEngineStarted`, `OnEngineShutdown`, `OnHornStateChanged`, `OnWinchStateChanged`, `OnLookIntoCockpit` ... (each in 100-200 trucks) | Retail |
| Vehicle values | `BlueprintNodeTruckAngularVelocity` (turn rate, 113 trucks), `TruckVelocity`, `TruckInputPedals` | Retail |
| Time | `Delay`, `Schedule` (first delay, then every period), `Retriggerable Delay` (restarts on each event: "N s after the last ..."), `Wait One Frame` (`blueprint_time_library.ssolib`); `Tick Timer` (every frame, `Progress` 0-1) | SDK |
| Logic and maths | `If`, `Switch By Int`, `Int Random`, `Float Random`, `Float Lerp`, `Float Remap`, `Float Clamp`, `Spline Value`, `Float Compare`, bool ops, `Vector3d Create` / `Scale` | SDK |
| Move an object directly | `Set Geom Rotation` / `Set Geom Position` (`$mods`): sets a named model object's local transform each time it fires | SDK; **no shipped truck uses it** |
| Continuous spinning parts | `PropTruckRotatorNativeController` + `Start/Stop Rotators` (66 trucks have rotators) | Retail |

## Measured on the editor bench (WALL-E r6, 2026-10-11)

| Finding | Grade |
|---|---|
| A mod's model clips play: `BlueprintNodeTplAnimStart` started each listed clip and the bones followed (head yaw to +-55 deg, eye tilts), and a bone's world position moved with it | Game (editor play mode; WALL-E `bench_runs/anim1_normal_154846`, `anim2_normal_155315`) |
| `Set Geom Rotation` with `useSpecificObj`, `isLocalTransformRef = true` on a bone holds that pose until set again; no clip is needed, so a held pose (asleep) lives on bones no clip keys, driven by a `Tick Timer` -> `Float Lerp` -> `Float Multiplication` -> `Vector3d Create` chain | Game (editor bench) |
| Its rotation is Euler **degrees** in the native frame; on a bone built with zero native rest rotation (tail +Y, roll +Z in Blender, like `BoneChassis_cdt`) a positive X angle tips the part forward/down; read-back via `Geom.GetObjModelTransform(name).GetEulerAngles()` returns the set values | Game (editor bench) |
| Clips must not key a bone the graph sets, and should start and end at the rest pose: no blueprint node stops, pauses or seeks a clip, and a clip ending with `Stop` removes its influence | SDK (no such node among the shipped blueprint sources) |
| Two INTERPOLATED clips on the same bones at once blend (WALL-E: a 34 deg glance during a tilt read -13 deg); they do not simply override | Game (editor bench) |
| `GetTurnAngularVelocity` (`Get Truck Angular Velocity`) is **deg/s**, positive turning left; WALL-E pivots 20-29, straight-line jitter up to 7.5, so a turn trigger needs about 12 | Game (editor bench) |
| `Retriggerable Delay` + `Float Random` duration + `Int Random` -> `Switch By Int` gave varied idle clips after quiet spells | Game (editor bench, idle shortened to 4 s for the test) |
| Several bones in one rigid-skinned mesh: tag each source part with its bone's vertex group before joining; decimated LOD copies keep the groups (snap any mixed vertex to its strongest group) | Build (WALL-E head/eyes, tplexp accepted) |

Read bones during a bench run with ExecSsl: `truck.owner.TryGet<Geom>()` for `GetObjModelTransform(name)` /
`GetTransformObj(name)`, `truck.owner.TryGet<PropAnimationController>()` for each sampler's `IsStarted()` /
`GetCurrentTime()` (WALL-E `tools/series_probe_anim.ps1`, `tools/anim_report.py`).

**Open:** the owner's view in the game; a keyboard trigger (`InputCheck`, Ctrl+K on WALL-E) cannot be pressed by
the bench; lamp beams following an animated bone (their anchors ride on the eye bones); `ADDITIVE` clips.

## Recipe used for WALL-E

Bones `BoneChassis_cdt > head_sleep > head > eye_X_sleep > eye_X`; head parts and each eye unit skinned to them;
lamp anchors on the eye bones; the cockpit camera stays on the chassis. Clips (Blender Actions on head / eye
bones, compiled with `anim_on = True`): wake_up, look_around, glance_left, glance_right, curious. Graph: engine
off / at spawn -> ease the *_sleep bones to the asleep pose; engine on -> ease back, then wake_up; a key ->
look_around; `Retriggerable Delay` 7-14 s after the last driving -> a random clip; turn rate beyond +-12 deg/s ->
glance into the turn with a 3 s cooldown. Source: WALL-E `tools/walle_animation.py` (shared by the Blender build
and the class build). A shared helper is deferred until a second vehicle needs the same graph.
