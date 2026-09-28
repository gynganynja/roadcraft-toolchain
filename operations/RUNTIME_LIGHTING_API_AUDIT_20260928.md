# Runtime lighting readback API audit (2026-09-28)

This read-only audit checked whether the shipped SDK and pinned editor expose a
callable way to seal complete lighting and renderer state immediately before a
native screenshot. It did not start the editor or Painter, send SSL, create a
capture, or change an asset, installed PAK, or receipt.

## Pinned evidence

The installed `C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\root\bin\pc\Roadcraft ModEditor.exe`
is 126,773,216 bytes, SHA-256
`ce6a48b1c73bea0876376d3251a6810b4a9913a7d500226e42bb2c605f3810b7`.
Offsets below are file offsets of ASCII names in **that exact executable**;
a name does not prove an SSL signature, return type, scope, or successful call.
The installed `tools/bin/ModEditor/predefined_types.ssl`, SHA-256
`501d4df0e9a6b91aa4b1763bdba75e29517ba82e04305679e5adba06cac171d2`,
contains only generic type/container declarations and no lighting or renderer
query interface.

| Surface | Exact observation | Limit |
| --- | --- | --- |
| `WeatherManagerSys`, `0x051bd168` | `GetCurrentSunDirection` at `0x051bd180`; `GetWeatherState` at `0x051bd198`. The adjacent `WeatherState` fields include rain and `sunDirection`, not ambient RGB or exposure. | `GetWeatherState().rainEnabled` and `.rainPower` are actually used by `D11_Full_Rig_Audit_20260925/native/sdk_sources/prop_wipers_controller.ssl` (SHA-256 `cac82830f516d45e791a8948cf72f90eb75f037962b12893f2a9508542b66f8b`, lines 124 and 134). The sun getter still lacks a tested SSL call. |
| `PresetSys`, `0x05258cb0` | `GetCurrentActive` at `0x05258da8`, `GetDayTime` at `0x05258ee0`, and `GetSpacetimeConfig` at `0x05258ef0`. Nearby color-grade methods are setters. | Active preset identity and daytime might provide diagnostics; no demonstrated return schema gives measured ambient RGB, exposure, or tonemap. `GetDayTime` is an unexecuted candidate. |
| `EngineControl`, `0x05244a38` | `GetVideoApiName` at `0x05244cd8`, `GetVideoConfig` at `0x05244f28`, `GetCurrentConfig` at `0x05244f38`, and `GetVideoPreset` at `0x05244f50`. `VideoConfig` fields at `0x052454d8` through `0x052457a0` include resolution, `lightingQuality`, and `postprocessQuality`. | The historical helper proves `$sslEngineCtrl.GetVideoConfig().windowSizeX/Y` works, but these settings are not a capture-time ambient/exposure/tonemap readback. A video API or preset label alone is not complete renderer state. |
| `GameEditor`, `0x05073ad8` | `GetGameObjects` at `0x05073cb0` and `GetGameObjectsInFrustum` at `0x05073cc0`. | No demonstrated global, signature, scene scope, or way to prove this enumerates *all* contributing local lights. Frustum objects would not prove a complete scene roster. |

An exact case-sensitive ASCII scan of this executable found **no**
`GetExposure`, `GetAmbient`, `GetTonemap`, `GetToneMap`,
`GetRendererMode`, `GetSceneLights`, `GetLights`, or `GetAllLights` string.
This is a bounded name-table search, not proof that an internal or differently
named API cannot exist. Several apparent matches are misleading:

- `SetExposure` at `0x051bc1b0` is beside
  `ScreenshotPipCameraRenderer`, `EnablePIPCam`, and `TakeScreenshots`, plus an
  error specifically about PIP exposure. It is a setter, not an active-camera
  exposure readback.
- `SetAmbientParameter` at `0x04fe2858` is beside `MuteAmbient`, `PostEvent`,
  and sound-volume functions; it is an audio interface.
- `getRendererFloat` and `getRendererString` at `0x05f3d560` and `0x05f3d548`
  are beside `DisplayObjectEx` and Flash UI names, not a RoadCraft renderer
  state interface.
- `GetLightColor` appears at `0x072c6e07` inside RTTI for
  `uiBEVEL_FILTER`; `GetNumLightsPushed` at `0x054039eb` is part of an
  internal `rend_shadowmap.cpp` assertion string. Neither establishes a
  callable SSL roster query. The `ambientLight` string at `0x0520b620` is
  beside material/texture parameters, not measured global ambient light.

## Historical capture constraint

The prior native helper
`D11_Interior_AAA_20260928/native/runs/aaa_maroon_bd58bce0ma/native_controls.ps1`
(SHA-256 `febe294bc940ca53bbbe0a0850dfc1bb75358fdc72ba196ed609a7e32241a975`)
enumerates the current truck's Sfx groups and each group's optional `light`.
That is a **truck-local** list, not a complete scene-light roster. In the
sealed `camera_front_seat.json` (SHA-256
`fdb450f84c7f98b76c93bdc49caf95539111ac7b71c68567727750b90893b3b2`),
all 11 reported `spotStarted` flags are false; in the later
`capture_front_seat.json` (SHA-256
`6618d44d7d9f5b77a19d8e5ba95e46d149ef7cd634b8b0e7deeaa2224f1da694`),
eight are true. Moreover, the helper's `CaptureCab` path triggers
`SaveScreenshot` before it appends the shared light readback. Neither reply is
a complete lighting observation sealed immediately before the image trigger.

## Consequence for the prepared probes

The five fragments in [NATIVE_EDITOR_RUNTIME_API_PROBE.md](NATIVE_EDITOR_RUNTIME_API_PROBE.md)
remain useful **separate, unexecuted diagnostics** for rain state, camera up,
sun direction, daytime, and level name. No sixth lighting fragment is justified
by this evidence. Even if all five compile and return values in a disposable
editor session, ambient RGB, complete local-light identities and states,
exposure, tonemap, renderer mode, and capture-time linkage would still be
missing. Keep `pairProtocolEligible: false` and the matched
baseline/candidate capture gate blocked. A future probe needs an independently
demonstrated read-only SSL signature and scope for each missing field; source
scene defaults, video-quality settings, and method-name strings cannot fill
them.
