# D11 native runtime readback: candidate API probe (2026-09-28)

This is a read-only follow-up to
[the earlier API audit](NATIVE_EDITOR_OBSERVATION_API_AUDIT.md). The five SSL
fragments in [probes/](probes/) are **proposed, unexecuted** queries for a
disposable editor session. Neither the editor nor Painter was launched for
this audit. No installed PAK, source scene, capture, or historical receipt was
changed. The failed AAA capture remains failed.

## Pinned local evidence

| Evidence | Exact source | What it proves |
| --- | --- | --- |
| Installed native executable | C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\root\bin\pc\Roadcraft ModEditor.exe, 126,773,216 bytes, SHA-256 ce6a48b1c73bea0876376d3251a6810b4a9913a7d500226e42bb2c605f3810b7 | Its ASCII SSL name table places weather_manager_sys, WeatherState, WeatherManagerSys, GetCurrentSunDirection, and GetWeatherState together at file offsets 0x51bd0b8–0x51bd198. A separate PresetSys name table at 0x5258cb0 contains GetDayTime at 0x5258ee0. These are candidate names, not a tested signature or a successful editor query. |
| Shipped SDK script copy | D11_Full_Rig_Audit_20260925/native/sdk_sources/prop_wipers_controller.ssl, SHA-256 cac82830f516d45e791a8948cf72f90eb75f037962b12893f2a9508542b66f8b | Lines 124 and 134 use $weather_manager_sys.GetWeatherState() and read .rainEnabled and .rainPower. This is actual SSL source usage of the rain-state getter. It does not reveal the active named weather preset or complete renderer state. |
| Historical camera control | D11_Interior_AAA_20260928/native/runs/aaa_maroon_bd58bce0ma/native_controls.ps1, SHA-256 febe294bc940ca53bbbe0a0850dfc1bb75358fdc72ba196ed609a7e32241a975 | Lines 177–184 call GetActivePlayCamera().GetTransform(), then read its position and forward vector. |
| Camera seat authoring helper | D11_Interior_Repair_20260926/capture_cab_survey.py, SHA-256 083652fc56cf6d0bcc54ab139c7100f126427f9a5d2da9df5fb29dbf3eeec2ef | Lines 51–67 call GetUp() on the seat transform. The active camera's transform has not been tested with GetUp(). |
| Installed editor EngineControl name table | Same pinned executable, offsets 0x05244a38 (`EngineControl`), 0x05244a98 (`GetLevelName`), and 0x05244f28 (`GetVideoConfig`) | `GetLevelName` is a candidate read-only EngineControl SSL method. The historical helper demonstrates `$sslEngineCtrl.GetVideoConfig()` but not the signature, return value, or scene meaning of `GetLevelName()`. |

The [official RoadCraft debug UI](https://roadcraft-modding.prismray.io/interface/debug_ui/)
shows live controls for Sky System time of day and exposure, Weather Manager
presets, and camera transform. The [official lighting and weather
guide](https://roadcraft-modding.prismray.io/scene_components/prefabs/lighting_and_weather/)
explains that a scene's weather manager owns these controls. The
[official Blueprint node reference](https://roadcraft-modding.prismray.io/scene_components/blueprints/nodes/)
documents rain/sandstorm state and sun-angle readback. These document UI and
Blueprint capabilities, **not** callable SSL getter signatures.

## Five independent scratch probes

| Fragment | SHA-256 | Native evidence level | Proposed result |
| --- | --- | --- | --- |
| probes/d11_weather_state.ssl | c39033a632e0ec8e3f36bf6e6dda1f0602d67bdd12d6a77b364461982d43b809 | Exact getter and two fields appear in SDK SSL source | Rain enabled and rain power only |
| probes/d11_camera_up.ssl | 086a93e10c29f97bd5dd215e7a0f155c4f0588618178480105f9d1a50ad9f09b | Active camera transform and seat-transform GetUp() are separately observed; their combination is untested | Active camera position, forward, up |
| probes/d11_sun_direction.ssl | 2ebd5914d635fae2ff603e73721f0c649fd5de927a50bd7a9aad46f4a1bff6fe | WeatherManagerSys.GetCurrentSunDirection appears only as adjacent native name-table strings | Current sun-direction vector, if callable |
| probes/d11_daytime.ssl | be7b9db66ce6a1df6a8ee3e1ed597f9cf6ccebddeb7ec2797c965e7b279ddd86 | PresetSys.GetDayTime appears only in the native name table; numeric return type/unit is unverified | Raw daytime number, if callable |
| probes/d11_level_name.ssl | bd5f7fe6e81dec9cc374c04f58ce3ae134a240431342a47d055714e5ca4fc61e | EngineControl.GetLevelName appears in the pinned native name table; its SSL signature and result are untested | Runtime level label, if callable |

Each fragment returns its own D11R_... result. They are separate so a
signature or compilation failure in one does not hide the outcome of the
others. The camera fragment returns D11R_CAMERA_UP_NO_CAMERA when no active
camera exists. A compilation error, null global, timeout, unexpected response,
missing field, or non-finite value is a failed probe, never a defaulted
observation. The read-only roadcraft.native_runtime_probe parser accepts only
one exact success record and always reports pairProtocolEligible: false.
The level-name result uses the distinct `LEVEL_NAME_DIAGNOSTIC` status. Its
transport verifier reports whether the returned label equals the pinned source
scene's basename, but **never** marks `loadedSceneVerified`: the label could name
an engine level rather than the active xscene, and a matching label cannot
authenticate the loaded scene bytes.

The probe deliberately does not claim a weather-preset name, ambient RGB,
exposure, tonemap, renderer mode, complete local-light roster, or capture-time
linkage. The native binary has renderer strings, but this audit found no
demonstrated SSL getter for those fields. The existing capture_pair_protocol
requires all of them as fresh observations immediately before each screenshot.
Neither scene defaults nor F5 settings labels can fill that gap.

## Smallest native experiment remaining

In one disposable editor session, with no installed PAK swap or production
capture, use the bounded Automation/ExecSsl transport and its five allowlisted
read-only modes. Send **each exact fragment separately**
after a validation scene and active fly camera have loaded. Preserve the full
request script, editor response or compile error, PID, request/response UTC
times, scene and executable hashes, and a fresh SHA-256 of each transport.
Check the reply with parse_probe_reply, then compare the queried values with
the editor's F5 Sky System and Weather Manager display. This is a method smoke
test, not matched baseline/candidate evidence. Do not attach these replies to
the capture-pair gate until all missing renderer and local-light fields have
native readback and the runner seals them before each screenshot.

Synthetic parser tests exercise exact success records, wrong marker, duplicate
or malformed response, missing camera, zero vectors, and out-of-range rain
power. They cannot prove any fragment compiles or returns real editor state.
