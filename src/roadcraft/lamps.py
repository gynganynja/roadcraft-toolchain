"""Exterior lamps that light in the retail game: lens states, beams, strobes and beacons, and their materials.

Proven parts (library/cockpit-and-lamps.md, "Exterior lamps and beacons with roadcraft.lamps"):

* Lens states (Lada Niva, Game): every lamp has an unlit mesh on an opaque ``vehicle_body`` instance and a
  coincident lit copy ``<name>_on`` on a ``vehicle_lights`` instance; ``BlueprintNodeShowHideGeomObjects`` nodes
  switch them on the engine, brake and reverse events. The lit copies stay default-visible in the model markup and
  the graph's init hides them.
* Beams (Lada): ``sfx_group`` / ``sfx_light_base`` lights parented to fitted anchors, started and stopped with the
  lens states.
* Strobes (CAT 793D, Game): one-shot ``BlueprintNodeTickTimer`` nodes that restart each other show and hide an
  emitter object while the lamp body stays.
* Native material groups (retail, 110 classes): ``vehicle_light_materials`` writes the BRO ``vehicleLightMaterials``
  block and ``dynamic_material`` the markup slot states it switches. Retail has no turn signals, hazards or
  headlight switch (research/lamps_semantics.md).

Two faults this module cannot produce, and ``bro_lint`` reports (RC037-RC039):

* A lit copy hidden by the markup (``objSettings``, ``visibleDefault = False``) never appeared when the graph showed
  it: no L275 lamp lit in v4-v8, and the Dump Twuck's strobing beacons blinked out instead of glowing (Inferred from
  both owners' drives; the markup flag is the one difference from the Lada).
* A strobe that hides the unlit lens makes the lamp vanish whenever its lit copy does not render ("the entire mesh
  appears then disappears", L275 v7 and Dump Twuck v4). Flash only a lit overlay over a lens that stays.

Stdlib only. ``blender_lamps`` holds the matching Blender geometry helpers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

BLUEPRINT_TYPE = "BlueprintActiveByProjectCondition"

# Lit vehicle_lights instance: (emissive intensity, bloomIntensity, tint A,R,G,B).
EMISSION: dict[str, tuple[float, float, list[int]]] = {
    "head": (80, 4, [255, 255, 255, 255]),        # Lada (Game); L275 v5-v8 used 12 / 1 and looked unlit
    "tail": (8, 1, [255, 255, 12, 3]),            # Lada dim running lamp; the red tint fixed pink/white lenses (Game)
    "brake": (45, 2, [255, 255, 12, 3]),          # Lada (Game)
    "reverse": (45, 2, [255, 255, 255, 255]),     # Lada (Game)
    "beacon_amber": (30, 2, [255, 255, 140, 0]),  # L275 v8/v9 (Build)
}

# sfx_light_base presets: (lightType, radius m, intensity, colour A,R,G,B, spotAngle, shadows).
LIGHTS: dict[str, tuple[str, float, float, list[int], float, bool]] = {
    "head": ("spot", 38, 20, [255, 255, 241, 211], 65, True),         # Lada (daylight native states)
    "reverse": ("spot", 8, 1.2, [255, 255, 245, 227], 100, False),    # Lada; L275 light-bar floods
    "tail": ("point", 1.3, .14, [255, 255, 8, 2], 100, False),        # Lada
    "beacon_amber": ("point", 7, .6, [255, 255, 150, 20], 100, False),  # L275 v6-v9 glow
}

# Flash patterns: (lit?, seconds) steps, repeated while the engine runs.
SINGLE_FLASH: tuple[tuple[bool, float], ...] = ((True, .4), (False, .4))                        # L275 v8/v9
DOUBLE_FLASH: tuple[tuple[bool, float], ...] = ((True, .08), (False, .10), (True, .08), (False, .55))  # Dump Twuck v4


# ---------------------------------------------------------------- nodes

def show(names: Sequence[str], visible: bool = True) -> dict[str, Any]:
    """``BlueprintNodeShowHideGeomObjects`` for model objects named without their ``_LODn`` suffix."""
    return {"objNameRef": {"def": list(names), "__type": "GeomStringArrayRefParam"},
            "showRef": {"def": bool(visible), "__type": "BoolRefParam"},
            "__type": "BlueprintNodeShowHideGeomObjects"}


def vfx(names: Sequence[str], start: bool = True) -> dict[str, Any]:
    return {"quantityType": "PACK", "vfxList": list(names), "vfxUidRef": {"__type": "SfxStringRefParam"},
            "__type": "BlueprintNodeVfxRestart" if start else "BlueprintNodeVfxStop"}


def branch(on_true: Iterable[str], on_false: Iterable[str] = ()) -> dict[str, Any]:
    return {"condition": {"__type": "BoolRefParam"}, "OnTrue": list(on_true), "OnFalse": list(on_false),
            "__type": "BlueprintNodeIf"}


def tick_timer(seconds: float, on_finish: Iterable[str]) -> dict[str, Any]:
    """One-shot timer (CAT 793D strobes): ``<node>/Restart`` starts it, ``<node>/Stop`` cancels it."""
    if seconds <= 0:
        raise ValueError("timer needs a positive time")
    return {"OnFinish": list(on_finish), "timeRef": {"def": seconds, "__type": "FloatRefParam"},
            "isStartOnInitRef": {"def": False, "__type": "BoolRefParam"},
            "isLoopedRef": {"def": False, "__type": "BoolRefParam"}, "__type": "BlueprintNodeTickTimer"}


def light_effect(anchor: str, role: str, **overrides: Any) -> dict[str, Any]:
    """``sfx_group`` holding one ``sfx_light_base`` parented to ``anchor`` (an empty at the lens, aimed along its
    native +Z; Blender -Y). Not auto-started: the lamp graph restarts and stops it."""
    kind, radius, intensity, colour, spot, shadows = LIGHTS[role]
    light = {"isAutoStart": True, "nameParent": anchor, "lightType": kind, "spotAngle": spot, "spotInnerAngleFactor": .5,
             "useInverseSquaredFalloff": False, "falloffStrength": 2,
             "RadiusCtrl": {"value": radius, "__type": "anim_const_ctrl"},
             "Intensity": {"value": intensity, "__type": "anim_const_ctrl"},
             "ColorCtrl": {"value": list(colour), "__type": "anim_const_color_ctrl"},
             "enableSM": shadows, "fogAmount": .08, "isStatic": False,
             "distanceControlParams": {"fadeOutEnable": True, "turnOffBegin": 70, "turnOffEnd": 100},
             "__type": "sfx_light_base"}
    light.update(overrides)
    return {"isAutoStart": False, "nameParent": anchor, "list": {"light": light}, "__type": "sfx_group"}


def lit_material(texture: str, role: str, *, spec: str | None = None, emissive: str | None = None,
                 intensity: float | None = None, bloom: float | None = None, tint: Sequence[int] | None = None) -> dict:
    """Lit lens instance (``vehicle_lights``). ``texture`` is the lens atlas; the emission mask defaults to
    ``<texture>_em`` and must be bright under the lens UVs."""
    i, b, t = EMISSION[role]
    params = {"texDiff": texture, "texSpec": spec or texture + "_spec",
              "emissive": {"intensity": i if intensity is None else intensity,
                           "bloomIntensity": b if bloom is None else bloom, "tint": list(tint or t)},
              "tex": {"emissiveTex": emissive or texture + "_em"}}
    return {"shaders": {"glt_shader": {"base": {"params": params}}}, "__type": "vehicle_lights"}


def unlit_material(texture: str, *, normal: str | None = None, spec: str | None = None) -> dict[str, Any]:
    """Unlit lens instance: opaque ``vehicle_body`` like every lit retail truck (never a glass preset)."""
    params = {"texDiff": texture, "texNM": normal or texture + "_nm", "texSpec": spec or texture + "_spec"}
    return {"game_material": "metal", "shaders": {"glt_shader": {"base": {"params": params}}}, "__type": "vehicle_body"}


# ---------------------------------------------------------------- native material groups (the retail route)

# Retail's own lamps (110 truck classes) are material swaps, not graphs: the BRO module ``vehicleLightMaterials``
# compiles to ``prop_vehicle_lights_material``, whose SSL (game/truck/truck_vehicles_headlights) calls
# ``Geom.SetMaterial(state, object)`` when its condition changes: Headlights and CockpitLights follow
# ``IsEngineRunning``, BrakeHeadlights ``IsBrakePull`` (movement state BRAKE_PULL), ReverseHeadlights gear -1 with the
# engine running. There is no turn-signal, hazard or headlight-switch group and no input action for one.
# role: (BRO key, light type, lit state the retail majority uses). research/lamps_semantics.md.
NATIVE_GROUPS: dict[str, tuple[str, str, str]] = {
    "head": ("Headlights", "Headlights", "lights"),            # reflector_headlight(s), 119 entries
    "marker": ("Marker", "Headlights", "lights_emissive"),     # marker_lights, beacons (steady), 58 entries
    "brake": ("Brake", "BrakeHeadlights", "lights"),           # stop_lights, 65 of 80 entries
    "reverse": ("Reverse", "ReverseHeadlights", "lights"),     # reverse_lights, 65 of 79 entries
    "cockpit": ("Cockpit", "CockpitLights", "lights_emissive"),  # _hp_cab_interior_gauges, 101 entries
}


def vehicle_light_materials(groups: Mapping[str, Sequence[str]], *, default: str = "default",
                            states: Mapping[str, str] | None = None) -> dict[str, Any]:
    """The BRO ``vehicleLightMaterials`` block retail trucks use (Alces C400 shape): ``groups`` maps a role of
    ``NATIVE_GROUPS`` to the model objects it switches; ``states`` overrides a role's lit state name. Every object's
    material slot needs markup ``dynamicMaterials`` with ``default`` and the lit state (``dynamic_material``).

    Retail has no indicator, hazard or headlight-switch driver: such roles are refused, since a lens given a
    Headlights role glows whenever the engine runs (Roamer 105). For brake and reverse in a mod prefer the graph
    (``lamp_states``): the native brake/reverse states did not light on the CAT 793D in the campaign."""
    unknown = sorted(set(groups) - set(NATIVE_GROUPS))
    if unknown:
        raise ValueError(f"no native lamp group for {unknown}: retail drives only {sorted(NATIVE_GROUPS)} "
                         "(no turn signals, hazards or headlight switch); flash such lamps with lamps.flasher")
    lights: dict[str, Any] = {}
    for role, names in groups.items():
        if not names:
            continue
        key, kind, state = NATIVE_GROUPS[role]
        data: dict[str, Any] = {"defaultName": default}
        lit = (states or {}).get(role, state)
        if lit != "lights":                       # "lights" is the SSL default; retail omits it
            data["lightName"] = lit
        data.update({"geomNames": list(names), "__type": kind})
        lights[key] = {"lightData": data, "__type": "VehicleLightMaterialDatas"}
    return {"isEnabled": True, "lights": lights}


def dynamic_material(unlit: str, lit: str, state: str = "lights", *, default: str = "default") -> dict[str, Any]:
    """Markup ``materials.<slot>`` entry whose ``default`` state is ``unlit`` and whose ``state`` is ``lit`` (the SDK
    Lynx sample's shape). Spell the state exactly as the lamp group does: the Lynx's ``lights_emmissive`` never
    lights (validator RC066)."""
    if unlit == lit:
        raise ValueError("lit and unlit materials are the same: the lamp shows no change (RC067)")
    return {"materialName": unlit, "dynamicMaterials": {default: {"materialName": unlit}, state: {"materialName": lit}}}


# ---------------------------------------------------------------- graphs

def _state(nodes: dict[str, Any], label: str, on: Sequence[str], off: Sequence[str],
           start: Sequence[str] = (), stop: Sequence[str] = ()) -> list[str]:
    """Show ``on``, hide ``off``, start / stop effects. Returns the inputs that enter the state. Show/hide nodes
    are created only for non-empty name lists (a lamp without that lens keeps its effects)."""
    chain = []
    if on:
        nodes[label] = show(on, True)
        chain.append(label)
    if off:
        nodes[label + "Hide"] = show(off, False)
        chain.append(label + "Hide")
    effects = []
    if start:
        nodes[label + "Fx"] = vfx(start, True)
        effects.append(label + "Fx")
    if stop:
        nodes[label + "Stop"] = vfx(stop, False)
        effects.append(label + "Stop")
    if not chain:
        return [e + "/Input" for e in effects]
    nodes[chain[0]]["OnExit"] = [n + "/Input" for n in chain[1:] + effects]
    return [chain[0] + "/Input"]


def lamp_states(*, head: tuple[str, str] | None = ("head_lights", "head_lights_on"),
                tail: tuple[str, str] | None = ("tail_lights", "tail_lights_on"),
                brake: str | None = "brake_lights_on",
                reverse: tuple[str, str] | None = ("reverse_lights", "reverse_lights_on"),
                driving: Sequence[str] = (), braking: Sequence[str] = (), reversing: Sequence[str] = (),
                running: Sequence[str] = (), stopped: Sequence[str] = ()) -> dict[str, Any]:
    """The Lada's engine / brake / reverse graph (Game). Lenses are (unlit, lit) object names; ``driving``,
    ``braking`` and ``reversing`` are effect names started with the head, brake and reverse states. ``running`` /
    ``stopped`` are extra inputs for the engine-running and stopped branches (flasher start / stop); ``stopped``
    also runs at init. Init leaves every lit copy hidden, so keep them default-visible in the markup."""
    nodes: dict[str, Any] = {}
    head_on = _state(nodes, "HeadsOn", [head[1]] if head else [], [head[0]] if head else [], driving)
    head_off = _state(nodes, "HeadsOff", [head[0]] if head else [], [head[1]] if head else [], stop=driving)
    tail_lit = [tail[1]] if tail else []
    tail_unlit = [tail[0]] if tail else []
    stop_lit = [brake] if brake else []
    dim = _state(nodes, "TailDim", tail_lit, tail_unlit + stop_lit, stop=braking)
    bright = _state(nodes, "TailBright", stop_lit or tail_lit, tail_unlit + (tail_lit if stop_lit else []), braking)
    tail_off = _state(nodes, "TailOff", tail_unlit, tail_lit + stop_lit, stop=braking)
    rev_on = _state(nodes, "ReverseOn", [reverse[1]] if reverse else [], [reverse[0]] if reverse else [], reversing)
    rev_off = _state(nodes, "ReverseOff", [reverse[0]] if reverse else [], [reverse[1]] if reverse else [], stop=reversing)
    nodes.update({
        "Running": {"GetValue": ["Apply/condition/cb", "ApplyTail/condition/cb", "ApplyReverse/condition/cb"],
                    "__type": "BlueprintNodeBoolSwitch"},
        "Braking": {"GetValue": ["TailSelect/condition/cb"], "__type": "BlueprintNodeBoolSwitch"},
        "Reversing": {"GetValue": ["ReverseSelect/condition/cb"], "__type": "BlueprintNodeBoolSwitch"},
        "Apply": branch([*head_on, "ApplyTail/Input", "ApplyReverse/Input", *running], [*head_off, *tail_off, *rev_off, *stopped]),
        "ApplyTail": branch(["TailSelect/Input"], tail_off),
        "TailSelect": branch(bright, dim),
        "ApplyReverse": branch(["ReverseSelect/Input"], rev_off),
        "ReverseSelect": branch(rev_on, rev_off),
        "Init": {"OnExit": [*head_off, *tail_off, *rev_off, *stopped], "__type": "BlueprintCommonLibraryOninit"},
        "Start": {"OnEngineStarted": ["Running/SetTrue", "Apply/Input"], "__type": "BlueprintNodeOnEngineStarted"},
        # A vehicle loaded with its engine running applies the states after the blueprint's own init.
        "LoadedRunning": {"OnEngineRunning": ["Running/SetTrue", "LoadDelay/Start"], "__type": "BlueprintNodeOnEngineRunningOnInit"},
        "LoadDelay": {"startDelay": {"def": .5, "__type": "FloatRefParam"}, "period": {"def": 1, "__type": "FloatRefParam"},
                      "OnPeriod": ["Apply/Input", "LoadDelay/Stop"], "__type": "BlueprintTimeLibrarySchedule"},
        "Shutdown": {"OnEngineShutdown": ["LoadDelay/Stop", "Running/SetFalse", "Braking/SetFalse", "Reversing/SetFalse", "Apply/Input"],
                     "__type": "BlueprintNodeOnEngineShutdown"},
        "BrakePull": {"OnBrakePulled": ["Braking/SetTrue", "ApplyTail/Input"], "__type": "BlueprintNodeOnBrakePull"},
        "BrakeRelease": {"OnBrakeReleased": ["Braking/SetFalse", "ApplyTail/Input"], "__type": "BlueprintNodeOnBrakeRelease"},
        "Reverse": {"OnEngineReverse": ["Reversing/SetTrue", "Braking/SetFalse", "ApplyTail/Input", "ApplyReverse/Input"],
                    "OnReleased": ["Reversing/SetFalse", "ApplyReverse/Input"], "__type": "BlueprintNodeOnEngineReverse"},
    })
    return nodes


def flasher(prefix: str, lit: Sequence[str], *, effects: Sequence[str] = (),
            pattern: Sequence[tuple[bool, float]] = SINGLE_FLASH) -> tuple[dict[str, Any], list[str], list[str]]:
    """Strobe or beacon that shows and hides ONLY the lit overlay ``lit`` (and starts / stops ``effects``), in a
    repeating ``pattern`` of (lit?, seconds) steps, from one-shot tick timers that restart each other.

    The unlit lens is never switched, so the lamp cannot vanish: give the overlay its own object (a lit shell just
    outside the lens, ``blender_lamps.lit_shell``) and leave it default-visible in the markup. Returns
    ``(nodes, start, stop)``: run ``start`` from the engine-running branch, ``stop`` from the stopped branch and init
    (``lamp_states(running=start, stopped=stop)``)."""
    if not lit:
        raise ValueError("a flasher needs the lit overlay object it shows and hides")
    steps = [(bool(state), float(seconds)) for state, seconds in pattern]
    if len(steps) < 2 or len(steps) % 2 or not steps[0][0] or \
            any(steps[i][0] == steps[i - 1][0] for i in range(len(steps))):
        raise ValueError("a flash pattern alternates lit and dark steps, starting lit")
    nodes: dict[str, Any] = {prefix + "Show": show(lit, True), prefix + "Hide": show(lit, False)}
    lit_in, dark_in = [prefix + "Show/Input"], [prefix + "Hide/Input"]
    if effects:
        nodes[prefix + "Glow"] = vfx(effects, True)
        nodes[prefix + "GlowStop"] = vfx(effects, False)
        lit_in.append(prefix + "Glow/Input")
        dark_in.append(prefix + "GlowStop/Input")
    timers = [f"{prefix}Step{i}" for i in range(len(steps))]
    for i, (_, seconds) in enumerate(steps):
        nxt = (i + 1) % len(steps)
        nodes[timers[i]] = tick_timer(seconds, [*(lit_in if steps[nxt][0] else dark_in), timers[nxt] + "/Restart"])
    halt = [t + "/Stop" for t in timers]
    return nodes, [*halt, *lit_in, timers[0] + "/Restart"], [*halt, *dark_in]


def exterior_lights(anchors: Mapping[str, str], *, lenses: Mapping[str, Any] | None = None,
                    flashers: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """A complete exterior-light block: ``anchors`` maps each light anchor to a ``LIGHTS`` role (head, tail,
    reverse, brake, beacon_amber...); ``lenses`` overrides ``lamp_states`` lens names; each flasher is
    ``{"prefix", "lit", "roles" or "effects", "pattern"}``. Returns the blueprint, the effect list, the lit
    objects and the markup objects to hide by default (always none)."""
    unknown = sorted({role for role in anchors.values() if role not in LIGHTS})
    if unknown:
        raise ValueError(f"no light preset for {unknown}; known roles: {sorted(LIGHTS)}")
    effects = {anchor + "_fx": light_effect(anchor, role) for anchor, role in anchors.items()}
    by_role: dict[str, list[str]] = {}
    for anchor, role in anchors.items():
        by_role.setdefault(role, []).append(anchor + "_fx")
    nodes: dict[str, Any] = {}
    running: list[str] = []
    stopped: list[str] = []
    flashed: set[str] = set()
    lit_objects: list[str] = []
    for spec in flashers:
        roles = spec.get("roles") or ()
        names = list(spec.get("effects") or [n for r in roles for n in by_role.get(r, [])])
        flashed.update(names)
        made, start, stop = flasher(spec["prefix"], spec["lit"], effects=names, pattern=spec.get("pattern", SINGLE_FLASH))
        nodes.update(made)
        running += start
        stopped += stop
        lit_objects += list(spec["lit"])
    options = dict(lenses or {})
    nodes.update(lamp_states(driving=[n for r in ("head", "tail") for n in by_role.get(r, []) if n not in flashed],
                             braking=[n for n in by_role.get("brake", []) if n not in flashed],
                             reversing=[n for n in by_role.get("reverse", []) if n not in flashed],
                             running=running, stopped=stopped, **options))
    for key, default in (("head", "head_lights_on"), ("tail", "tail_lights_on"), ("brake", "brake_lights_on"),
                         ("reverse", "reverse_lights_on")):
        value = options.get(key, default)
        if value:
            lit_objects.append(value if isinstance(value, str) else value[1])
    return {"blueprint": {"nodes": nodes, "__type": BLUEPRINT_TYPE}, "effects": effects,
            "litObjects": lit_objects, "markupHidden": []}


# ---------------------------------------------------------------- checks

def _target(ref: str) -> tuple[str, str]:
    node, _, port = ref.partition("/")
    return node, port


def _blueprints(blueprint: Any) -> dict[str, dict[str, Any]]:
    """Node tables by blueprint name, from a BRO ``blueprint`` block or a class ``prop_blueprints``."""
    graphs = (blueprint or {}).get("blueprints") if isinstance(blueprint, dict) else None
    return {name: g["nodes"] for name, g in (graphs or {}).items() if isinstance(g, dict) and isinstance(g.get("nodes"), dict)}


def _run(nodes: dict[str, Any], refs: Iterable[str], state: dict[str, bool], seen: set[str]) -> None:
    """Follow show/hide chains from ``refs`` (``Node/Input`` only), recording the last visibility of each object.
    Conditional and delayed nodes (If, timers, schedules) are not followed."""
    for ref in refs:
        name, port = _target(ref)
        node = nodes.get(name)
        if port != "Input" or not isinstance(node, dict) or name in seen:
            continue
        if node.get("__type") != "BlueprintNodeShowHideGeomObjects":
            continue
        seen.add(name)
        visible = (node.get("showRef") or {}).get("def") is True
        for obj in (node.get("objNameRef") or {}).get("def") or []:
            state[obj] = visible
        _run(nodes, node.get("OnExit") or [], state, seen)


def simulate(nodes: Mapping[str, Any], refs: Iterable[str], start: Mapping[str, bool] | None = None) -> dict[str, bool]:
    """Object visibility after firing ``refs`` (``Node/Input``) through the show/hide chains, from ``start``.
    For audits: ``simulate(nodes, nodes["Init"]["OnExit"])``, then ``simulate(nodes, ["HeadsOn/Input"], after)``."""
    state = dict(start or {})
    _run(dict(nodes), refs, state, set())
    return state


def graph_visibility(blueprint: Any) -> dict[str, dict[str, Any]]:
    """Per blueprint: objects the graph shows or hides, their visibility after init, and the objects that timer-
    driven steps (strobes, schedules) hide."""
    report = {}
    for name, nodes in _blueprints(blueprint).items():
        shown, hidden = set(), set()
        for node in nodes.values():
            if isinstance(node, dict) and node.get("__type") == "BlueprintNodeShowHideGeomObjects":
                target = shown if (node.get("showRef") or {}).get("def") is True else hidden
                target.update((node.get("objNameRef") or {}).get("def") or [])
        init: dict[str, bool] = {}
        has_init = False
        for node in nodes.values():
            if isinstance(node, dict) and node.get("__type") == "BlueprintCommonLibraryOninit":
                has_init = True
                _run(nodes, node.get("OnExit") or [], init, set())
        strobed: dict[str, bool] = {}
        for node in nodes.values():
            if isinstance(node, dict) and node.get("__type") in ("BlueprintNodeTickTimer", "BlueprintTimeLibrarySchedule"):
                for ref in (node.get("OnFinish") or []) + (node.get("OnPeriod") or []):
                    trace: dict[str, bool] = {}
                    _run(nodes, [ref], trace, set())
                    strobed.update({obj: False for obj, visible in trace.items() if not visible})
        if shown or hidden:
            report[name] = {"shown": sorted(shown), "hidden": sorted(hidden), "hasInit": has_init,
                            "afterInit": dict(sorted(init.items())), "strobeHidden": sorted(strobed)}
    return report


def markup_hidden(markup: Mapping[str, Any] | None) -> set[str]:
    """Objects a model markup hides by default (``objSettings``)."""
    settings = (((markup or {}).get("objSettings") or {}).get("settings")) or {}
    out = set()
    for name, entry in settings.items():
        visibility = (entry or {}).get("visibility") if isinstance(entry, dict) else None
        if isinstance(visibility, dict) and (visibility.get("__type") == "invisible" or visibility.get("visibleDefault") is False):
            out.add(name)
    return out


def markup_beside(tpl: str | Path) -> Path | None:
    """The markup of a compiled model: ``X.tpl.asset/tpl/X.tpl`` -> ``X.tpl.asset/X.tpl_markup``."""
    path = Path(tpl)
    candidate = path.parent.parent / (path.stem + ".tpl_markup")
    return candidate if candidate.is_file() else None


def lamp_findings(blueprint: Any, hidden_by_markup: set[str] | None = None) -> list[tuple[str, str, str, str]]:
    """(code, severity, message, where) for lamp graphs. RC039 needs only the graph; RC037 and RC038 need the
    model markup (``hidden_by_markup``)."""
    out = []
    for name, graph in graph_visibility(blueprint).items():
        where = f"blueprint.{name}"
        after = graph["afterInit"]
        vanish = sorted(o for o in graph["strobeHidden"] if after.get(o) is True)
        if vanish:
            out.append(("RC039", "warning", f"a timer-driven step hides {vanish}, which init leaves visible (the unlit "
                        "lens): the lamp vanishes whenever its lit copy does not render (L275 v7, Dump Twuck v4). Flash "
                        "only a lit overlay (roadcraft.lamps.flasher)", where))
        if hidden_by_markup is None:
            continue
        masked = sorted(set(graph["shown"]) & hidden_by_markup)
        if masked:
            out.append(("RC037", "warning", f"the graph shows {masked}, but the model markup hides them by default "
                        "(visibleDefault = False): no such lit copy was ever seen lit (L275 v4-v8, Dump Twuck v4). Leave "
                        "lit copies default-visible and hide them at init, as the Lada does", where))
        loose = sorted(o for o in graph["shown"] if o not in after and o not in hidden_by_markup)
        if loose and not graph["hasInit"]:
            out.append(("RC038", "warning", f"no BlueprintCommonLibraryOninit: {loose} start visible until an event "
                        "switches them", where))
        elif loose:
            out.append(("RC038", "warning", f"init neither shows nor hides {loose}: lit copies start visible over "
                        "their unlit lenses until an event switches them; hide them at init", where))
    return out


def material_conflicts(objects: Mapping[str, Iterable[tuple[str, str, str]]]) -> list[dict[str, Any]]:
    """The exporter keeps one material per texture in an object: report objects whose materials share a texture
    but not a preset. ``objects`` maps an object to (material, texture, preset) rows. The L275 windows (glass)
    and lamp parts (vehicle_body) shared one atlas and every window compiled opaque (v1-v7)."""
    out = []
    for obj, rows in objects.items():
        by_texture: dict[str, dict[str, str]] = {}
        for material, texture, preset in rows:
            by_texture.setdefault(texture, {})[material] = preset
        for texture, materials in sorted(by_texture.items()):
            if len(set(materials.values())) > 1:
                out.append({"object": obj, "texture": texture, "materials": dict(sorted(materials.items()))})
    return out
