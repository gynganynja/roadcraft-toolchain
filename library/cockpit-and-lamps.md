# Cockpit instruments and lamps

## Steering wheel and gauges: `dataDashboard`

```text
dataDashboard = {
   isEnabled = True
   dashboard = {
      Speed = { nameBone = "ctrl_dashboard_speed", axis = "Y", minRotationAngle = 0, maxRotationAngle = 270,
                dashboardSubtype = "SPEED", damping = 0.5, scale = 1.5, __type = "DashboardElementCockpit" }
      RPM = { nameBone = "ctrl_dashboard_rpm", axis = "Y", maxRotationAngle = 240, dashboardSubtype = "RPM",
              damping = 0.1, __type = "DashboardElementCockpit" }
   }
   steering = { steering_wheel = { nameBone = "ctrl_steering_wheel", axis = "Y", minRotationAngle = -360,
                maxRotationAngle = 360, steeringSubtype = "WHEEL", __type = "SteerigElementCockpit" } }
   __type = "CockpitDashboardSetting"
}
```

| Rule | Grade |
|---|---|
| Each element turns its bone about the bone's local `axis` from the modelled pose; subtypes seen: SPEED, RPM, FUEL, ENGINE_ENABLED; switchers DIFFLOCK, ENGINE_ENABLED; steering WHEEL | Retail (Armiger) |
| The Armiger's instrument bones have native Y pointing forward, away from the driver (along the column / out of the dial) | Retail |
| `scale` looks like degrees per km/h (Armiger 2.3 with max 240) | Inferred |
| Model needles at the dial's zero mark, or turn them there in the build: a needle modelled pointing up rests at mid-scale | Build (buggy); rotation direction awaits a drive |
| Keep only the steering wheel rim and hub on `ctrl_steering_wheel`; a lower column that is not coaxial wobbles | Build (buggy) |
| The compiled class carries it as `prop_cockpit_dashboard` | Retail, Build |

## Lamps that work in the retail campaign

The method proven on the CAT 793D (RC20) and the Apocalypse Buggy (headlights seen lit, Game):

1. Lamp meshes named as the game's own trucks name them, without the `_lp_` prefix
   (`reflector_headlights`, `tail_lights`, `marker_lights`, ...), on an opaque `vehicle_body`
   material instance (unlit state).
2. A coincident copy of each, named `<name>_on`, with a `vehicle_lights` material instance:

   ```text
   shaders = { glt_shader = { base = { params = {
      texDiff = "mod_x_lights"  texSpec = "mod_x_lights_spec"
      emissive = { intensity = 120  bloomIntensity = 8 }      headlights; tail lamps ~30 / 2
      tex = { emissiveTex = "mod_x_lights_em" }
   } } } }
   __type = "vehicle_lights"
   ```

3. Four `BlueprintNodeShowHideGeomObjects` nodes (show / hide the lit set, show / hide the unlit set)
   in the engine blueprint, wired to: `BlueprintNodeOnEngineStarted.OnEngineStarted` (lit on),
   `BlueprintNodeOnEngineShutdown.OnEngineShutdown` (lit off), `BlueprintCommonLibraryOninit.OnExit`
   (lit off), and `BlueprintNodeOnEngineRunningOnInit.OnEngineRunning` -> a `BlueprintTimeLibrarySchedule`
   (`startDelay` 0.5 s, stops itself) -> lit on, so a vehicle loaded with its engine running lights up
   after the blueprint's own init.

| Rule | Grade |
|---|---|
| The deprecated `BlueprintLibraryChangematerial` never renders (editor captures identical) | Build (CAT 793D) |
| Retail has no headlight key (only an editor debug hotkey), so lamps that follow the engine cannot rely on the `Headlights` light type | Game (CAT 793D) |
| Native `prop_vehicle_lights_material` brake / reverse states did not light in the campaign | Game (CAT 793D RC20) |
| RC21 drives brake and reverse lamps by show/hide on the brake pull / release events and `BlueprintNodeOnEngineReverse` (`OnEngineReverse` / `OnReleased`, the retail Bowhead's pattern) | Retail (pattern), Build (RC21 not yet confirmed in the game) |
| All 108 lit retail truck classes name lamp meshes without `_lp_` and give the unlit state an opaque `vehicle_body` instance; the SDK TUZ sample's lamp material is misspelt `lights_emmissive`: do not copy it | Retail, SDK |
| The engine's `Headlights` / `CockpitLights` material groups follow the engine running, not a switch: turn-signal lenses given a light role glow all the time, so leave indicators without one | Game (Roamer 105, editor play mode) |
| `BlueprintNodeShowHideGeomObjects` works in retail (the 793D's strobes, then its engine lamps) | Game (CAT 793D RC20) |
| No real light projection (beams) has been authored yet | Open |
