"""Check a truck BRO, and optionally its compiled class and model, for pitfalls that have cost real
time on earlier mods.  Every finding names the library article that explains it.

Each check comes from something that went wrong in a drive or a build (library/symptoms.md):

* RC001  suspensionCollection without useSuspensionCollection: the generator drops the collection.
* RC002  maxSteerSpeed / backSteerSpeed / pedalsResponsiveness unset: SDK default 1 = instant.
* RC003  a wheel slot names a missing editable wheel or suspension item.
* RC004  suspension height 0: height is the spring's neutral offset, not the rest position.
* RC005  predicted rest on a stop (beta model of vehicle.py; stops at height + min / height + max,
         native_suspension.rest_report).
* RC010  IK chain pinned to a wheel slot the axle controller does not move: it never moves.
* RC011  IK chain pinned to a steering joint no steering rack drives.
* RC012  IK chain pinned to a bone of a chain listed after it.
* RC013  ikSettings without useNamedChains (every retail truck sets it).
* RC014  driven IK bone count differs from explicit constraint count (review implicit defaults).
* RC020-RC024  names the model lacks; wheel slots with children that nothing moves.
* RC025  effects parented to nodes the model lacks (wildcards such as sfx_exhaust_* allowed): the nameParents
         of the BRO's own effects block, and of the visible emitters of every stock effect the truck lists or
         starts (ssl/sfx/<name>.sfx with the truck's override merged on; apoc buggy, Warthog: no exhaust, no haze).
* RC026  the blueprint starts or stops effects the truck does not declare (a donor's SFX graph
         copied without its effects block shows nothing).
* RC027  a visible local__parentArea emitter (it emits from its node's faces) bound to a node with no mesh
         (CAT 793D sfx_exhaust_02/03 and haze empties; no emission is inferred, not seen in game).
* RC028  a wheel vfx cylinder (local__cylinder on _wheel) whose axis, boneRotation turned by the wheel model's
         _wheel frame, is not along native X: wheel particles and grass lie fore-aft (grader 16M3, 994).
* RC030-RC032  settings the compiled class lost.
* RC033-RC034  generated components missing the properties they require.
* RC035  load-volume refill stream fixed in truck space (no sfxMovableDumpPositionBone).
* RC036  load border hung from the wrong body: the native sand grid composes the back border with
         its parent's transform (hang it from the tail-lid body); the others belong to parentBody. Also
         load volume, body or borders the model lacks.
* RC037  the lamp graph shows an object the model markup hides by default: no such lit copy was ever
         seen lit (L275 v4-v8, Dump Twuck v4); keep lit copies default-visible, hidden at init (needs the markup).
* RC038  a lit copy starts visible because init neither shows nor hides it (needs the markup).
* RC039  a timer-driven strobe hides the unlit lens: the lamp vanishes whenever its lit copy does not render
         ("the mesh disappears and reappears"); flash only a lit overlay (roadcraft.lamps.flasher).
* RC045  explicit crane movement-sound subscriber bodies or joints missing from the selected model/markup.
* RC075  a BRO key the generator drops (no field on the generator's C# class, or never read) or whose class key
         the engine never reads (library/bro-passthrough.md, data/bro_passthrough.json from bro_passthrough.py).
* RC049  gearbox `neutralGearSwitchingDelay` over 5 s: the box keeps its old gear that long after a stop, so the
         next pedal first carries on in the old direction (Dump Twuck at 60 s; retail 0-3, Baikal 65206 0.5).
* RC046-RC048  tracked vehicles (roadcraft.tracks, tracked-vehicles.md): a track carried only by fakes on
         their top stops; wheels on a welded (fixed-joint) track frame under 10 % of the body mass; sprung
         wheels on a light jointed body (measure on the bench; mass-scaling rationale unsupported). RC046 needs the model, RC047/RC048
         the markup.
* RC040-RC044  load-grid geometry from roadcraft.load_volume (cells at the pivot height, sheet over
         4 m, misplaced borders, ledges, grid outside the tub): run in Blender via blender_load.grid_report;
         this linter cannot see meshes.
"""

from __future__ import annotations

import copy
import json
import math
import posixpath
import zipfile
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Callable, Iterable

from . import lamps, load_volume, native_suspension, ps_format, tracks, vehicle
from .schema import saber_merge
from .tpl_reader import TplNodes, read_tpl

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
DRIVING_KEYS = tuple(vehicle.RETAIL_SCOUT_DRIVING)


def _finding(code: str, severity: str, message: str, where: str, article: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message, "where": where,
            "library": f"library/{article}"}


def wheel_model_references(settings: dict[str, Any], model: TplNodes | Iterable[str], *, tire_name: str = "tire") -> list[dict[str, str]]:
    """Native default deformation requires a named tyre mesh (Jimny startup assertion).

    A supported custom deforming-object contract can supply its explicit name.
    Disabled deformation does not require this object. This checks presence only,
    not deformation quality or native acceptance.
    """
    names = set(model.names) if isinstance(model, TplNodes) else set(model)
    if settings.get("deformEnable") and tire_name not in names:
        return [_finding("RC049", "error", f"wheel deformation requires model object {tire_name!r}", "wheel model", "suspension-and-wheels.md")]
    return []


WHEEL_BONE = "_wheel"
AXLE_COS = math.cos(math.radians(10))   # a cylinder axis within 10 degrees of native X lies on the axle


def _axis_label(v: tuple[float, ...]) -> str:
    for i, name in enumerate(("X (axle)", "Y (up)", "Z (fore-aft)")):
        if abs(v[i]) >= AXLE_COS:
            return ("-" if v[i] < 0 else "+") + name
    return str([round(c, 3) for c in v])


def wheel_vfx_findings(vfx: dict[str, Any] | None, model: TplNodes | Iterable[str] | None,
                       where: str = "propVFX") -> list[dict[str, str]]:
    """RC028: a ``local__cylinder`` vfx bone on ``_wheel`` (wheel dust and water, grass) whose axis is not along the
    axle.  The cylinder axis is the bone's local Z turned by ``boneRotation`` (:func:`vehicle.euler_axis`,
    R = Rz.Ry.Rx) and then by the wheel model's ``_wheel`` frame (rows = local axes in native space); the axle is
    native X.  Retail pairs its rotated ``_wheel`` with no boneRotation (181 of 181 cylinders), the SDK TUZ Lynx an
    identity ``_wheel`` with ``[90, 0, 90]``; identity + no rotation lies fore-aft.  ``vfx`` is the wheel BRO's
    ``propVFX`` or the class's ``properties.vfx``; needs the wheel model's node table."""
    nodes = nodes_of(model)
    bones = ((vfx or {}).get("vfxSkeleton") or {}).get("vfxBones") if isinstance(vfx, dict) else None
    if nodes is None or WHEEL_BONE not in nodes.index or not isinstance(bones, list):
        return []
    frame = nodes.axes(WHEEL_BONE)
    identity = all(abs(frame["xyz"[i]][j] - (i == j)) < 1e-3 for i in range(3) for j in range(3))
    out: list[dict[str, str]] = []
    for index, bone in enumerate(bones):
        if not isinstance(bone, dict) or bone.get("bone") != WHEEL_BONE or \
                (bone.get("geom") or {}).get("__type") != "local__cylinder":
            continue
        rotation = bone.get("boneRotation")
        try:
            local = vehicle.euler_axis([float(a) for a in (rotation or (0, 0, 0))])
        except (TypeError, ValueError):
            continue
        axis = tuple(sum(local[k] * frame["xyz"[k]][i] for k in range(3)) for i in range(3))
        length = math.sqrt(sum(c * c for c in axis)) or 1.0
        axis = tuple(c / length for c in axis)
        if abs(axis[0]) >= AXLE_COS:
            continue
        fix = ("give it boneRotation [90, 0, 90] (SDK TUZ Lynx)" if identity and not rotation else
               "drop its boneRotation (retail)" if not identity and rotation else
               "pair the frame and boneRotation as retail (rotated _wheel, none) or the SDK (identity, [90, 0, 90])")
        kind = "identity" if identity else "rotated"
        out.append(_finding("RC028", "warning",
                            f"vfx cylinder {bone.get('name')!r} on {WHEEL_BONE} (frame {kind}, "
                            f"boneRotation {list(rotation) if rotation else 'none'}) lies along native "
                            f"{_axis_label(axis)}, not the axle: its wheel particles and grass footprint are turned "
                            f"90 degrees; {fix}, and never change the _wheel frame without the boneRotation",
                            f"{where}.vfxSkeleton.vfxBones[{index}]", "suspension-and-wheels.md"))
    return out


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _effects_started(blueprint: Any) -> set[str]:
    names: set[str] = set()
    for node in _walk(blueprint):
        if node.get("__type") in ("BlueprintNodeVfxRestart", "BlueprintNodeVfxStop"):
            names.update(v for v in node.get("vfxList") or [] if isinstance(v, str) and v)
            ref = (node.get("vfxUidRef") or {}).get("def")
            if isinstance(ref, str) and ref:
                names.add(ref)
    return names


STOCK_SFX_PAK = Path("root/paks/client/default/default_other.pak")
PARENT_AREA = "local__parentArea"


def stock_sfx_reader(game_root: str | Path | None = None) -> Callable[[str], dict[str, Any] | None] | None:
    """Stock effect definitions by name: ``ssl/sfx/<name>.sfx`` in the installation's ``default_other.pak``,
    parsed and cached; None when the installation has no such pak."""
    from .project_context import game_root as default_game_root
    pak = (Path(game_root) if game_root else default_game_root()) / STOCK_SFX_PAK
    if not pak.is_file():
        return None
    with zipfile.ZipFile(pak) as archive:
        members = {posixpath.basename(n).lower()[:-4]: n for n in archive.namelist() if n.lower().endswith(".sfx")}
    cache: dict[str, dict[str, Any] | None] = {}

    def read(name: str) -> dict[str, Any] | None:
        key = name.lower()
        if key not in cache:
            member = members.get(key)
            cache[key] = None
            if member is not None:
                with zipfile.ZipFile(pak) as archive:
                    doc = ps_format.loads(archive.read(member).decode("utf-8", errors="replace"))
                cache[key] = doc if isinstance(doc, dict) else None
        return cache[key]
    return read


def _short(names: list[str], shown: int = 4) -> str:
    return ", ".join(names[:shown]) + (f" (+{len(names) - shown} more)" if len(names) > shown else "")


def effect_emitter_findings(listed: dict[str, Any], started: Iterable[str], model: TplNodes | Iterable[str],
                            stock_sfx: Callable[[str], dict[str, Any] | None], *, where: str = "sfx.list",
                            reported: Iterable[str] = ()) -> list[dict[str, str]]:
    """RC025 / RC027 on the emitters of the effects a truck lists (``listed``: the class's ``sfx.list`` or the BRO's
    ``effects.propSfx.list``) or starts (``started``, from the blueprints).

    Each effect is its stock definition (``stock_sfx(name)``: the parsed ``ssl/sfx/<name>.sfx``, or None) with the
    truck's entry merged on top (SaberMerge).  Only effects the blueprints start or stop, or that start themselves
    (``isAutoStart``), are checked, and only their visible emitters (``isVisible`` absent or True); an emitter
    binds to its own ``nameParent``, else the effect's.  RC025: the pattern matches no model node (patterns in
    ``reported`` are already reported).  RC027: a ``local__parentArea`` emitter, which emits from its node's
    faces, on a node with no mesh (needs ``model`` read with bounds; skipped when the bounds are unknown)."""
    nodes = nodes_of(model)
    names = list(nodes.names) if nodes is not None else list(model)
    bounds = nodes.bounds if nodes is not None else None
    started, reported = set(started), set(reported)
    out: list[dict[str, str]] = []
    for effect in list(listed) + sorted(started - set(listed)):
        stock = stock_sfx(effect)
        merged = copy.deepcopy(stock) if isinstance(stock, dict) else {}
        if isinstance(listed.get(effect), dict):
            saber_merge(merged, listed[effect])
        if effect not in started and merged.get("isAutoStart") not in (True, "True"):
            continue
        emitters = merged.get("emitters2")
        lost: dict[str, list[str]] = {}
        empty: dict[str, list[str]] = {}
        for emitter_name, emitter in emitters.items() if isinstance(emitters, dict) else ():
            if not isinstance(emitter, dict) or emitter.get("isVisible", True) in (False, "False"):
                continue
            pattern = emitter.get("nameParent") or merged.get("nameParent")
            if not isinstance(pattern, str) or not pattern or pattern.startswith("<"):
                continue
            matches = [name for name in names if fnmatchcase(name, pattern)]
            if not matches:
                if pattern not in reported:
                    lost.setdefault(pattern, []).append(emitter_name)
                continue
            emission = emitter.get("emission")
            source = emission.get("source") if isinstance(emission, dict) else None
            if bounds is not None and isinstance(source, dict) and source.get("__type") == PARENT_AREA:
                for node in matches:
                    if nodes.index[node] not in bounds:
                        empty.setdefault(node, []).append(emitter_name)
        how = "started by the blueprint" if effect in started else "isAutoStart"
        origin = f"stock ssl/sfx/{effect}.sfx" if stock is not None else "the truck's own entry"
        for pattern, emitter_names in lost.items():
            out.append(_finding("RC025", "error",
                                f"{effect} ({how}): visible emitters {_short(emitter_names)} ({origin}) emit from "
                                f"nameParent {pattern!r}, which matches no model node, so they show nothing; add the "
                                "node (retail: a hidden face mesh, origin at the shape, under its body bone) or "
                                "override the emitters' nameParent", f"{where}.{effect}", "cockpit-and-lamps.md"))
        if empty:
            emitter_names = sorted({e for found in empty.values() for e in found})
            out.append(_finding("RC027", "warning",
                                f"{effect} ({how}): visible {PARENT_AREA} emitters {_short(emitter_names)} emit from the "
                                f"faces of {sorted(empty)}, which have no mesh, so they probably show nothing "
                                "(inferred from the effect definition, not seen in game); make each a small hidden face "
                                "mesh at the same place under the same bone (retail: a 63 mm disc facing along the "
                                "pipe, a quad facing up for haze) or override those emitters with a local__point source",
                                f"{where}.{effect}", "cockpit-and-lamps.md"))
    return out


def _crane_references(blueprint, names, markup, where):
    """Explicit crane movement-sound body/joint references must fit this model."""
    constraints = {n.get("name") for n in _walk(markup)
                   if str(n.get("__type", "")).startswith("tpl_markup_constraint_") and n.get("name")}
    for node in _walk(blueprint):
        if node.get("__type") != "BlueprintNodeOnCraneArrowPositionChanged":
            continue
        for key in ("rootBodyName", "hookBodyName"):
            value = node.get(key)
            if isinstance(value, str) and value and value not in names:
                yield _finding("RC045", "error", f"crane movement subscriber {key} targets a body absent from the model: {value}",
                               where + "." + key, "ik-visual-rigs.md")
        if markup is not None:
            for key in ("xConstraintName", "yConstraintName", "zConstraintName", "wConstraintName"):
                value = node.get(key)
                if isinstance(value, str) and value and value not in constraints:
                    yield _finding("RC045", "error", f"crane movement subscriber {key} targets a joint absent from the markup: {value}",
                                   where + "." + key, "ik-visual-rigs.md")


def nodes_of(model: TplNodes | Iterable[str] | None) -> TplNodes | None:
    return model if isinstance(model, TplNodes) else None


def slot_rides_moving_body(nodes: TplNodes | None, slot: str) -> bool | None:
    """True when a wheel slot's nearest rigid body (``*_cdt`` ancestor) is not the root body, i.e. the slot
    moves with a suspension body such as a rocker; None when the model hierarchy is unknown."""
    if nodes is None or nodes.parents is None or slot not in nodes.index:
        return None
    body = nodes.parent(slot)
    while body is not None and not body.endswith("_cdt"):
        body = nodes.parent(body)
    if body is None:
        return False
    above = nodes.parent(body)
    while above is not None:
        if above.endswith("_cdt"):
            return True
        above = nodes.parent(above)
    return False


NEUTRAL_DELAY_MAX = 5.0  # seconds; retail 0-3 (truck-settings.md "Heavy hauler drive")


def lint_truck(doc: dict[str, Any], *, compiled_class: str | None = None,
               model: TplNodes | Iterable[str] | None = None, beta: float = vehicle.SUSPENSION_BETA,
               weight_shares: dict[str, float] | None = None,
               markup: dict[str, Any] | None = None,
               stock_sfx: Callable[[str], dict[str, Any] | None] | None = None) -> list[dict[str, str]]:
    """Findings for one truck BRO document.  ``weight_shares`` maps a suspension item to one wheel's
    fraction of the vehicle's weight (default: an even split over all wheels). ``markup`` is the body
    model's parsed ``.tpl_markup`` (lamp visibility checks RC037 / RC038).  ``stock_sfx`` resolves stock effect
    definitions by name (:func:`stock_sfx_reader`); with it and the model, the emitters of started effects are
    checked too (RC025, and RC027 when the model was read with bounds)."""
    out: list[dict[str, str]] = []
    settings = doc.get("truckSettings") or {}
    slots = settings.get("wheelSlots") or []
    collection = settings.get("suspensionCollection") or {}
    pool = doc.get("wheelPool") or {}
    slot_names = {slot.get("geomName") for slot in slots if slot.get("geomName")}
    axles = doc.get("axleControllerSettings") or {}
    moved = {row.get("frameName") for row in axles.get("independentAxleSettings") or []}
    axle_frames = {row.get("frameName") for row in axles.get("axleSettings") or []}
    racked = set()
    for rack in axles.get("steeringRackSettings") or []:
        racked.update({rack.get("rightWheelFrameName"), rack.get("leftWheelFrameName")})
    steer_joints = {slot.get("customSteeringJointObjName") for slot in slots if slot.get("customSteeringJointObjName")}

    # ---- suspension
    if collection and settings.get("useSuspensionCollection") is not True:
        out.append(_finding("RC001", "error",
                            "suspensionCollection without useSuspensionCollection = True: the generator drops the "
                            "collection and every axle gets the engine default (min 0, max 1 m, strength 0), so "
                            "the wheels hang up to a metre below a body resting on its bump stops",
                            "truckSettings.useSuspensionCollection", "suspension-and-wheels.md"))
    for key in DRIVING_KEYS:
        if key not in settings:
            out.append(_finding("RC002", "warning",
                                f"{key} unset: the SDK default is 1 (instant); retail scouts use "
                                f"{vehicle.RETAIL_SCOUT_DRIVING[key]}", f"truckSettings.{key}", "truck-settings.md"))
    neutral = ((settings.get("gearbox") or {}).get("params") or {}).get("neutralGearSwitchingDelay")
    if isinstance(neutral, (int, float)) and neutral > NEUTRAL_DELAY_MAX:
        out.append(_finding("RC049", "warning",
                            f"neutralGearSwitchingDelay {neutral:g} s: the gearbox keeps the old gear that long after "
                            "a stop and the truck first carries on in its old direction; retail uses 0-3 s "
                            "(Baikal 65206 0.5) and the handbrake for slopes",
                            "truckSettings.gearbox.params.neutralGearSwitchingDelay", "truck-settings.md"))
    for slot in slots:
        name = slot.get("geomName", "?")
        wheel = slot.get("editableWheel")
        if wheel and wheel not in pool:
            out.append(_finding("RC003", "error", f"editableWheel {wheel!r} is not in wheelPool",
                                f"wheelSlots[{name}]", "suspension-and-wheels.md"))
        item = slot.get("suspensionCollectionItem")
        if collection and item and item not in collection:
            out.append(_finding("RC003", "error", f"suspensionCollectionItem {item!r} is not in suspensionCollection",
                                f"wheelSlots[{name}]", "suspension-and-wheels.md"))
    counts: dict[str, int] = {}
    for slot in slots:
        item = slot.get("suspensionCollectionItem")
        if item:
            counts[item] = counts.get(item, 0) + 1
    by_design = tracks.stop_fake_axles(doc, nodes_of(model)) if settings.get("tracks") else set()
    for item, axle in collection.items():
        where = f"truckSettings.suspensionCollection.{item}"
        if item in by_design:
            out.append(_finding("RC005", "info",
                                "track stop fakes beside a rigid real ground wheel rest on their stops by design "
                                "(retail EPEC TC305); RC004/RC005 rest predictions do not apply", where, tracks.ARTICLE))
            continue
        strength = float(axle.get("strength", 0) or 0)
        travel = float(axle.get("max", 1) or 0) - float(axle.get("min", 0) or 0)
        # A rigid axle (EPEC TC305 track ends: min = max = 0) has no travel for height to matter.
        if strength > 0 and float(axle.get("height", 0) or 0) == 0 and travel >= 0.03:
            out.append(_finding("RC004", "warning",
                                "height 0: height is the spring's neutral offset, so the vehicle settles below its "
                                "modelled stance by the whole static sag (often onto the bump stops)", where,
                                "suspension-and-wheels.md"))
        if strength > 0 and slots and travel < 0.03:
            out.append(_finding("RC005", "info", f"rigid axle ({travel:.3f} m of travel): rest prediction skipped",
                                where, "suspension-and-wheels.md"))
        elif strength > 0 and slots:
            share = (weight_shares or {}).get(item, 1.0 / len(slots))
            # stops at height + min / height + max (measured, suspension-and-wheels.md "Stop geometry")
            report = native_suspension.rest_report(axle, share, beta)
            expected, stops = report["cases"]["expected"], report["stops"]
            if expected["onBumpStop"]:
                out.append(_finding("RC005", "warning",
                                    f"predicted to rest on its top (bump) stop (spring rest {expected['rest']:+.3f} m below "
                                    f"modelled, stops {stops['top']:+.3f}..{stops['bottom']:+.3f} = height + min/max; wheel "
                                    f"share {share:.3f}, beta {beta}): no bump travel at rest", where,
                                    "suspension-and-wheels.md"))
            elif expected["onDroopStop"]:
                out.append(_finding("RC005", "info",
                                    f"predicted to rest on its droop stop (spring rest {expected['rest']:+.3f} m, bottom "
                                    f"stop {stops['bottom']:+.3f} = height + max): no droop at rest",
                                    where, "suspension-and-wheels.md"))
            elif any(case["onBumpStop"] or case["onDroopStop"] for case in report["cases"].values()):
                out.append(_finding("RC005", "info",
                                    "rests on a stop at an edge of beta's uncertainty (retail +-40 %, or the "
                                    f"measured {vehicle.SUSPENSION_BETA_MEASURED:g}); consider more margin",
                                    where, "suspension-and-wheels.md"))

    # ---- IK chains
    ik = doc.get("ikSettings") or {}
    chains = ik.get("chains") or {}
    if chains and ik.get("useNamedChains") is not True:
        out.append(_finding("RC013", "info", "ikSettings.useNamedChains is not True (every retail truck sets it)",
                            "ikSettings", "ik-visual-rigs.md"))
    for name, chain in chains.items():
        driven = max(0, len(chain.get("ikChainBodies") or []) - 1)
        constraints = len(chain.get("ikConstraints") or [])
        if driven and constraints != driven:
            out.append(_finding("RC014", "warning",
                                f"{driven} driven IK bones have {constraints} constraints: review one entry per "
                                "bone; implicit constraints exist in a few retail cable chains",
                                f"ikSettings.chains.{name}", "ik-visual-rigs.md"))
    order = list(chains)
    owner: dict[str, int] = {}
    for position, name in enumerate(order):
        for body in (chains[name].get("ikChainBodies") or [])[1:]:
            owner.setdefault(body, position)
    for position, name in enumerate(order):
        for effector in chains[name].get("effectors") or []:
            target = effector.get("bodyPhysName")
            where = f"ikSettings.chains.{name}"
            if target in slot_names and target not in moved:
                on_moving_body = slot_rides_moving_body(nodes_of(model), target)
                if on_moving_body is None:
                    out.append(_finding("RC010", "warning",
                                        f"pinned to wheel slot {target} that no axle controller moves: it follows the "
                                        "wheel only if the slot hangs under a moving body (pass the model to check)",
                                        where, "suspension-and-wheels.md"))
                elif not on_moving_body:
                    out.append(_finding("RC010", "error",
                                        f"pinned to wheel slot {target} on the chassis, which no axle controller moves "
                                        "(axleControllerSettings.independentAxleSettings): the chain will not follow "
                                        "the wheel", where, "suspension-and-wheels.md"))
            if target in steer_joints and target not in racked:
                out.append(_finding("RC011", "warning",
                                    f"pinned to steering joint {target} that no steeringRackSettings entry drives",
                                    where, "suspension-and-wheels.md"))
            if target in owner and owner[target] > position:
                out.append(_finding("RC012", "info",
                                    f"pinned to {target}, a bone of chain {order[owner[target]]} listed after it "
                                    "(retail does this too, e.g. the Crayfish harvester; listed for review)",
                                    where, "ik-visual-rigs.md"))

    # ---- load volume effects
    # Dump Twuck v2, 2026-10-01: without a movable bone the refill stream sits at
    # sfxRefillLocalPosition in truck space -- (0, 2, -1.5) put it under the tray --
    # and does not follow the tipping body. The shipped Bowhead names its volume.
    load = doc.get("loadVolumeSettings") or {}
    particles = load.get("particleLoadVolumeSettings") or {}
    if load.get("isEnabled") and particles.get("sfxRefillActor") and not particles.get("sfxMovableDumpPositionBone"):
        position = particles.get("sfxRefillLocalPosition") or {}
        origin = tuple(position.get(axis, 0) for axis in ("x", "y", "z"))
        out.append(_finding("RC035", "warning",
                            f"refill stream origin {origin} is fixed in truck space; name the load volume in "
                            "sfxMovableDumpPositionBone (shipped Bowhead) or confirm the origin sits above the heap",
                            "loadVolumeSettings.particleLoadVolumeSettings", "truck-settings.md"))

    # Dump Twuck v1-v3, 2026-10-01: the TUZ Lynx sample's SFX graph was copied without the Lynx's
    # effects block, so its exhaust and haze never showed. A retail effects module (WheelBigVfx01,
    # WheelExtraBigVfx01, ...) supplies names this document cannot see: report those as info only.
    effects = doc.get("effects")
    declared = set(((effects or {}).get("propSfx") or {}).get("list") or {})
    module = isinstance(effects, dict) and effects.get("__type") not in (None, "EffectsSettings")
    unknown = sorted(_effects_started(doc.get("blueprint")) - declared)
    if unknown:
        if module:
            out.append(_finding("RC026", "info", f"effects outside the inline list {unknown}: confirm the "
                                f"{effects.get('__type')} module provides them", "blueprint", "cockpit-and-lamps.md"))
        else:
            out.append(_finding("RC026", "warning", "the blueprint starts or stops effects the truck does not declare: "
                                f"{unknown}" + ("" if effects else " (no effects block)"), "blueprint", "cockpit-and-lamps.md"))

    # ---- tracks: KGS25 c02/c03 (2026-10-02) sank a track up to 19 cm in pivot turns with only stop fakes on
    # the ground and 2.5 t welded frames; the retail EPEC layout plus 7.5 t frames held. Retail-clean (33 crawlers).
    if settings.get("tracks"):
        for code, severity, message, where in tracks.track_findings(doc, nodes_of(model), markup):
            out.append(_finding(code, severity, message, where, tracks.ARTICLE))

    # ---- lamps: lit copies hidden by the markup (RC037), lit copies left visible at init (RC038) and
    # strobes that hide the unlit lens (RC039). L275 v4-v8 and Dump Twuck v4 strobes blinked out instead of
    # glowing; the Lada (lamps seen lit) hides lit copies at init only. See roadcraft.lamps.
    hidden = lamps.markup_hidden(markup) if markup is not None else None
    for code, severity, message, where in lamps.lamp_findings(doc.get("blueprint"), hidden):
        out.append(_finding(code, severity, message, where, "cockpit-and-lamps.md"))

    # ---- model
    if model is not None:
        nodes = model if isinstance(model, TplNodes) else None
        names = set(nodes.names) if nodes else set(model)
        out.extend(_crane_references(doc.get("blueprint"), names, markup, "blueprint"))
        for slot in slots:
            geom = slot.get("geomName")
            if geom and geom not in names:
                out.append(_finding("RC023", "error", f"wheel slot {geom} is not in the model",
                                    f"wheelSlots[{geom}]", "suspension-and-wheels.md"))
        for name, chain in chains.items():
            wanted = list(chain.get("ikChainBodies") or [])
            wanted += [e.get("bodyPhysName") for e in chain.get("effectors") or []]
            wanted += [e.get("bodyIKName") for e in chain.get("effectors") or []]
            missing = sorted({w for w in wanted if w and w not in names})
            if missing:
                out.append(_finding("RC020", "error", f"model lacks {missing}", f"ikSettings.chains.{name}",
                                    "ik-visual-rigs.md"))
        for node in _walk(doc.get("blueprint")):
            if node.get("__type") == "BlueprintNodeShowHideGeomObjects":
                refs = (node.get("objNameRef") or {}).get("def") or []
                missing = sorted(r for r in refs if r not in names)
                if missing:
                    out.append(_finding("RC021", "error", f"show/hide node targets meshes the model lacks: {missing}",
                                        "blueprint", "cockpit-and-lamps.md"))
        dashboard = doc.get("dataDashboard") or {}
        for group in ("dashboard", "steering", "switcher", "gearStick"):
            for element in (dashboard.get(group) or {}).values():
                bone = element.get("nameBone")
                if bone and bone not in names:
                    out.append(_finding("RC022", "error", f"dashboard bone {bone} is not in the model",
                                        f"dataDashboard.{group}", "cockpit-and-lamps.md"))
        if nodes is not None and nodes.parents is not None:
            for geom in sorted(slot_names & names):
                kids = nodes.children(geom)
                if kids and geom not in moved and geom not in axle_frames:
                    out.append(_finding("RC024", "warning",
                                        f"wheel slot {geom} has children {kids} but no axle controller moves it",
                                        f"wheelSlots[{geom}]", "suspension-and-wheels.md"))
        # Lamp beams and stock effects attach by node name (retail patterns such as sfx_exhaust_*).
        parents = sorted({n["nameParent"] for n in _walk(doc.get("effects"))
                          if isinstance(n.get("nameParent"), str) and n["nameParent"] and not n["nameParent"].startswith("<")})
        missing = [p for p in parents if not any(fnmatchcase(name, p) for name in names)]
        if missing:
            out.append(_finding("RC025", "error", f"effects are parented to nodes the model lacks: {missing}",
                                "effects", "cockpit-and-lamps.md"))
        # Installed-mod audit, 2026-10-23: the apoc buggy and Warthog start the stock exhaust and haze with no
        # sfx_exhaust_* / sfx_radiator_haze node (no nameParent in their own block to catch), and the CAT 793D binds
        # parentArea smoke to empties. Resolve the stock emitters of what the blueprints start.
        if stock_sfx is not None:
            out.extend(effect_emitter_findings(dict(((effects or {}).get("propSfx") or {}).get("list") or {}),
                                               _effects_started(doc.get("blueprint")),
                                               nodes if nodes is not None else names,
                                               stock_sfx, where="effects.propSfx.list", reported=missing))
        # Dump Twuck v3 -> v4, 2026-10-01 (disassembled ModEditor): the sand grid spans the four border
        # meshes in the parentBody frame, and the back border is composed with its parent's transform.
        # Hung under parentBody itself, that body's pivot is applied twice: v3's grid ran 3.7 m past the
        # tail and its far cells hung a curtain at the pivot height. Shipped trucks use the lid body.
        borders = load.get("bodySettings") or {}
        parent_body = borders.get("parentBody")
        for code, severity, message in load_volume.settings_findings(load, names):
            out.append(_finding(code, severity, message, "loadVolumeSettings", "truck-settings.md"))
        if load.get("isEnabled") and nodes is not None and nodes.parents is not None and parent_body in names:
            back = borders.get("backWall")
            if back in names and nodes.parent(back) == parent_body:
                above = nodes.parent(parent_body)
                origin = nodes.position(above) if above in names else (0.0, 0.0, 0.0)
                offset = tuple(round(a - b, 3) for a, b in zip(nodes.position(parent_body), origin))
                if max(abs(v) for v in offset) > 1e-3:
                    out.append(_finding("RC036", "error",
                                        f"back wall {back} hangs from {parent_body}, whose pivot {offset} the native sand "
                                        "grid applies twice; hang it from the tail-lid body (shipped dump trucks)",
                                        "loadVolumeSettings.bodySettings.backWall", "truck-settings.md"))
            for key in ("leftWall", "rightWall", "frontWall"):
                wall = borders.get(key)
                if wall in names and nodes.parent(wall) != parent_body:
                    out.append(_finding("RC036", "warning",
                                        f"{key} {wall} hangs from {nodes.parent(wall)}, not {parent_body}; the native "
                                        "grid reads it in its own parent's frame", f"loadVolumeSettings.bodySettings.{key}",
                                        "truck-settings.md"))

    # ---- compiled class
    if compiled_class is not None:
        if collection and settings.get("useSuspensionCollection") is True and \
                "suspensionAxleCollection" not in compiled_class:
            out.append(_finding("RC030", "error", "the compiled class has no suspensionAxleCollection",
                                "compiled class", "suspension-and-wheels.md"))
        if axles and "prop_truck_axles_controller" not in compiled_class:
            out.append(_finding("RC031", "error", "the compiled class has no prop_truck_axles_controller",
                                "compiled class", "suspension-and-wheels.md"))
        for key in DRIVING_KEYS:
            if key in settings and key not in compiled_class:
                out.append(_finding("RC032", "warning", f"{key} is in the BRO but not in the compiled class",
                                    "compiled class", "truck-settings.md"))
        # Native Dump Twuck startup, 2026-10-01: the load controller requires
        # route-following even for player-driven trucks. Inspect declarations,
        # not text mentions. Other class bases can inherit their own properties.
        try:
            native = ps_format.loads(compiled_class)
        except ps_format.PsSyntaxError:
            native = {}
        props = native.get("properties")
        if model is not None and isinstance(props, dict):
            model_names = set(model.names) if isinstance(model, TplNodes) else set(model)
            out.extend(_crane_references(props.get("prop_blueprints"), model_names, markup, "compiled blueprint"))
        if isinstance(props, dict) and isinstance(props.get("prop_blueprints"), dict):
            have = set(((props.get("sfx") or {}).get("list")) or {})
            lost = sorted(_effects_started(props["prop_blueprints"]) - have)
            if lost:
                out.append(_finding("RC026", "error", f"the compiled class lacks effects its blueprints start or stop: {lost}",
                                    "compiled class", "cockpit-and-lamps.md"))
        if native.get("__type") == "truck_view" and isinstance(props, dict) and \
                "prop_load_volume_controller" in props and "prop_route_following" not in props:
            out.append(_finding("RC033", "error",
                                "the load-volume controller requires prop_route_following; enable aiRouteFollowingSettings",
                                "compiled class", "truck-settings.md"))
        if native.get("__type") == "truck_view" and isinstance(props, dict) and \
                "prop_winch" not in props and "prop_truck_view_winch_controller" not in props and \
+                any(n.get("__type") == "BlueprintNodeOnWinchStateChanged" for n in _walk(props)):
            out.append(_finding("RC034", "error",
                                "a winch-state blueprint subscriber requires a native winch controller; remove the donor branch or author a usable winch",
                                "compiled class", "truck-settings.md"))
    out.extend(passthrough_findings(doc))
    return sorted(out, key=lambda f: (SEVERITY_ORDER[f["severity"]], f["code"], f["where"]))


PASSTHROUGH_TABLE = Path(__file__).with_name("data") / "bro_passthrough.json"
_PASSTHROUGH: dict[str, Any] | None = None


def passthrough_table() -> dict[str, Any]:
    """RC075 table written by ``bro_passthrough.py --lint-table`` (empty when absent)."""
    global _PASSTHROUGH
    if _PASSTHROUGH is None:
        try:
            _PASSTHROUGH = json.loads(PASSTHROUGH_TABLE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _PASSTHROUGH = {}
    return _PASSTHROUGH


def passthrough_findings(doc: dict[str, Any], table: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """RC075: a BRO key the generator drops (no C# field, or never read), warning; or one whose class key the
    engine never reads, info.  Typed nodes only (``__type``, resolved through ``typeChains``)."""
    table = passthrough_table() if table is None else table
    dropped, ignored = table.get("dropped") or {}, table.get("engineIgnored") or {}
    chains = table.get("typeChains") or {}
    if not dropped and not ignored:
        return []
    out: list[dict[str, str]] = []

    def visit(node: Any, where: str) -> None:
        if isinstance(node, list):
            for i, item in enumerate(node):
                visit(item, f"{where}[{i}]")
            return
        if not isinstance(node, dict):
            return
        t = node.get("__type")
        types = chains.get(t, [t]) if isinstance(t, str) else []
        for key, value in node.items():
            if key.startswith("__"):
                continue
            here = f"{where}.{key}" if where else key
            for name in types:
                tf = f"{name}.{key}"
                if tf in dropped:
                    out.append(_finding("RC075", "warning", f"{t}.{key} never reaches the compiled class: {dropped[tf]}",
                                        here, "bro-passthrough.md"))
                    break
                if tf in ignored:
                    out.append(_finding("RC075", "info", f"{t}.{key} {ignored[tf]}", here, "bro-passthrough.md"))
                    break
            visit(value, here)

    visit(doc, "")
    return out


def lint_files(bro: str | Path, compiled_class: str | Path | None = None, tpl: str | Path | None = None,
               beta: float = vehicle.SUSPENSION_BETA, markup: str | Path | None = None,
               game_root: str | Path | None = None) -> dict[str, Any]:
    """Lint files. Without an explicit ``markup``, the body markup beside the compiled model
    (``X.tpl.asset/X.tpl_markup``) is read when present, so the shared vehicle checks cover lamp visibility.
    Stock effects come from ``game_root`` (default: the configured installation) when it has them."""
    doc = ps_format.load(bro)
    class_text = Path(compiled_class).read_text(encoding="utf-8", errors="replace") if compiled_class else None
    model = None
    if tpl:
        anchor = next((s.get("geomName") for s in (doc.get("truckSettings") or {}).get("wheelSlots") or []), None)
        model = read_tpl(tpl, anchor=anchor, bounds=True)
    if markup is None and tpl:
        markup = lamps.markup_beside(tpl)
    markup_doc = ps_format.load(markup) if markup else None
    if "truckWheel" in doc:
        settings, vfx = doc["truckWheel"], doc.get("propVFX")
        if class_text:
            props = ps_format.loads(class_text).get("properties", {})
            settings, vfx = props.get("prop_truck_wheel", settings), props.get("vfx", vfx)
        findings = wheel_model_references(settings, model) if model is not None else []
        findings += wheel_vfx_findings(vfx, model, "properties.vfx" if class_text else "propVFX")
    else:
        findings = lint_truck(doc, compiled_class=class_text, model=model, beta=beta, markup=markup_doc,
                              stock_sfx=stock_sfx_reader(game_root))
    return {"bro": str(bro), "compiledClass": str(compiled_class) if compiled_class else None,
            "model": str(tpl) if tpl else None, "markup": str(markup) if markup else None, "findings": findings,
            "errors": sum(1 for f in findings if f["severity"] == "error"),
            "warnings": sum(1 for f in findings if f["severity"] == "warning")}
