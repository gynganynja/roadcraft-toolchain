"""Check a truck BRO, and optionally its compiled class and model, for pitfalls that have cost real
time on earlier mods.  Every finding names the library article that explains it.

Each check comes from something that went wrong in a drive or a build (library/symptoms.md):

* RC001  suspensionCollection without useSuspensionCollection: the generator drops the collection.
* RC002  maxSteerSpeed / backSteerSpeed / pedalsResponsiveness unset: SDK default 1 = instant.
* RC003  a wheel slot names a missing editable wheel or suspension item.
* RC004  suspension height 0: height is the spring's neutral offset, not the rest position.
* RC005  predicted rest on a stop (beta model of vehicle.py).
* RC010  IK chain pinned to a wheel slot the axle controller does not move: it never moves.
* RC011  IK chain pinned to a steering joint no steering rack drives.
* RC012  IK chain pinned to a bone of a chain listed after it.
* RC013  ikSettings without useNamedChains (every retail truck sets it).
* RC020-RC024  names the model lacks; wheel slots with children that nothing moves.
* RC030-RC032  settings the compiled class lost.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from . import ps_format, vehicle
from .tpl_reader import TplNodes, read_tpl

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
DRIVING_KEYS = tuple(vehicle.RETAIL_SCOUT_DRIVING)


def _finding(code: str, severity: str, message: str, where: str, article: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message, "where": where,
            "library": f"library/{article}"}


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


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


def lint_truck(doc: dict[str, Any], *, compiled_class: str | None = None,
               model: TplNodes | Iterable[str] | None = None, beta: float = vehicle.SUSPENSION_BETA,
               weight_shares: dict[str, float] | None = None) -> list[dict[str, str]]:
    """Findings for one truck BRO document.  ``weight_shares`` maps a suspension item to one wheel's
    fraction of the vehicle's weight (default: an even split over all wheels)."""
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
    for item, axle in collection.items():
        where = f"truckSettings.suspensionCollection.{item}"
        strength = float(axle.get("strength", 0) or 0)
        if strength > 0 and float(axle.get("height", 0) or 0) == 0:
            out.append(_finding("RC004", "warning",
                                "height 0: height is the spring's neutral offset, so the vehicle settles below its "
                                "modelled stance by the whole static sag (often onto the bump stops)", where,
                                "suspension-and-wheels.md"))
        travel = float(axle.get("max", 1) or 0) - float(axle.get("min", 0) or 0)
        if strength > 0 and slots and travel < 0.03:
            out.append(_finding("RC005", "info", f"rigid axle ({travel:.3f} m of travel): rest prediction skipped",
                                where, "suspension-and-wheels.md"))
        elif strength > 0 and slots:
            share = (weight_shares or {}).get(item, 1.0 / len(slots))
            report = vehicle.axle_report(axle, share, beta)
            expected = report["cases"]["expected"]
            if expected["onBumpStop"]:
                out.append(_finding("RC005", "warning",
                                    f"predicted to rest on its bump stop (rest {expected['rest']:+.3f} m, range "
                                    f"{axle.get('min', 0)}..{axle.get('max', 1)}; wheel share {share:.3f}, beta {beta}): "
                                    "the body sits low with no bump travel", where, "suspension-and-wheels.md"))
            elif expected["onDroopStop"]:
                out.append(_finding("RC005", "info",
                                    f"predicted to rest topped out on its droop stop (rest {expected['rest']:+.3f} m, "
                                    f"max {axle.get('max', 1)}): no droop at rest; retail does this too (Armiger)",
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

    # ---- model
    if model is not None:
        nodes = model if isinstance(model, TplNodes) else None
        names = set(nodes.names) if nodes else set(model)
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
    return sorted(out, key=lambda f: (SEVERITY_ORDER[f["severity"]], f["code"], f["where"]))


def lint_files(bro: str | Path, compiled_class: str | Path | None = None, tpl: str | Path | None = None,
               beta: float = vehicle.SUSPENSION_BETA) -> dict[str, Any]:
    doc = ps_format.load(bro)
    class_text = Path(compiled_class).read_text(encoding="utf-8", errors="replace") if compiled_class else None
    model = None
    if tpl:
        anchor = next((s.get("geomName") for s in (doc.get("truckSettings") or {}).get("wheelSlots") or []), None)
        model = read_tpl(tpl, anchor=anchor)
    findings = lint_truck(doc, compiled_class=class_text, model=model, beta=beta)
    return {"bro": str(bro), "compiledClass": str(compiled_class) if compiled_class else None,
            "model": str(tpl) if tpl else None, "findings": findings,
            "errors": sum(1 for f in findings if f["severity"] == "error"),
            "warnings": sum(1 for f in findings if f["severity"] == "warning")}
