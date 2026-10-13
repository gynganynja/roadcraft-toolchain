"""Tracked vehicles: which wheels carry a track, the bodies they hang on, and the retail patterns.

library/tracked-vehicles.md is the article ("start here" for crawlers).  A track lists real wheels
(``wheelIds``: the idler, sprocket and any rigid or sprung road wheel), fake wheels (``fakeWheelIds``:
invisible support wheels) and visual-only slots.  Every retail crawler with readable geometry puts a
real wheel within a few centimetres of its lowest wheel, or springs its ground fakes; near-zero
"stop" fakes (min >= 0 or strength ~0.001) only ever sit beside rigid real ground wheels.

Checks wired into :mod:`roadcraft.bro_lint` (need the compiled model; RC047/RC048 also the markup):

* RC046  a track's ground-level wheels are all fakes resting on their top stops (no real wheel, none
         sprung).  KGS25 c02/c03: one track sank up to 19 cm into a pad in pivot turns.
* RC047  a body carrying a track's wheels (a track frame) is welded on with a fixed joint, at any mass
         share, or hangs on a hinge/slide without a motor (an unsprung joint flops).  Retail springs its
         frames: Greenway HT500 ``BoneTrackSusp_L/R_cdt`` 7.5 t on a hinge, childRotation [0,90,0],
         limited -5..5 deg, ``tpl_markup_spring_motor`` 1e7 / 1.1e7.  The owner on the vanilla HT500:
         "the track frames have springyness" (Game).  KGS25: welded 2.5 t frames (6 %) sank or lifted a
         track; light frames (under ``FRAME_SHARE_WARNING``) are named in the message.
* RC048  sprung wheels on such a body: measure their rest on the bench. The original rationale (springs
         scale with the parent body's mass; KGS25 fix 1 "25-40x softer") is unsupported: that bench run
         was frozen and code shows no mass scaling (library/tracked-vehicles.md).
"""

from __future__ import annotations

from typing import Any, Iterable

from . import ps_format, retail
from .tpl_reader import TplNodes, read_tpl_bytes

GROUND_TOLERANCE = 0.06      # m; retail real ground wheels sit within 0.05 m of the track's lowest wheel
SPRUNG_STRENGTH = 0.01       # retail sprung ground wheels use 0.01-0.085, stop fakes 0.001-0.0013
FRAME_SHARE_WARNING = 0.10   # KGS25 6 % failed, 18 % passed; Greenway HT500 frames 12.5 %
RIGID_TRAVEL = 0.005         # m of travel below which an axle counts as rigid
ARTICLE = "tracked-vehicles.md"


def axle_for(slot: dict[str, Any], settings: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    """(axle name, SuspensionAxle) of a wheel slot: the suspension collection item when the slot names
    one, otherwise the suspension set's front axle, or its rear for ``isRear`` slots when rear differs."""
    collection = settings.get("suspensionCollection") or {}
    item = slot.get("suspensionCollectionItem")
    if collection and item:
        return item, collection.get(item)
    sset = settings.get("suspensionSet") or {}
    if sset:
        key = "rear" if sset.get("rearDiffers") and slot.get("isRear") else "front"
        return key, sset.get(key)
    return None, None


def _num(axle: dict[str, Any] | None, key: str, default: float) -> float:
    value = (axle or {}).get(key)
    return default if value is None else float(value)


def axle_kind(axle: dict[str, Any] | None) -> str:
    """``rigid`` (no travel), ``sprung`` (compressible above its neutral: min < 0 and a real strength)
    or ``stops`` (rests on its top stop under load: min >= 0 or near-zero strength). No axle is the
    engine default (min 0, max 1, strength 0): ``stops``."""
    low, high = _num(axle, "min", 0.0), _num(axle, "max", 1.0)
    if high - low < RIGID_TRAVEL:
        return "rigid"
    if low < 0 and _num(axle, "strength", 0.0) >= SPRUNG_STRENGTH:
        return "sprung"
    return "stops"


def wheel_radius(doc: dict[str, Any], slot: dict[str, Any]) -> float | None:
    """EditableWheel scale x the inline wheel radius (1 when the wheel is a type reference)."""
    entry = (doc.get("wheelPool") or {}).get(slot.get("editableWheel"))
    if not isinstance(entry, dict) or entry.get("scale") is None:
        return None
    inline = ((entry.get("wheel") or {}).get("truckWheel") or {}) if isinstance(entry.get("wheel"), dict) else {}
    return float(entry["scale"]) * float(inline.get("radius", 1) or 1)


def hanging_body(nodes: TplNodes | None, slot: dict[str, Any], track: dict[str, Any]) -> str | None:
    """Body a wheel slot hangs on: its parentFrame, else its nearest ``*_cdt`` ancestor in the model
    (compiled retail classes leave parentFrame empty and still attach wheels to the body bone above
    them), else the track's parentTracker locator."""
    frame = slot.get("parentFrame")
    if frame:
        return frame
    name = slot.get("geomName")
    if nodes is not None and nodes.parents is not None and name in nodes.index:
        for ancestor in _ancestors(nodes, name):
            if ancestor.endswith("_cdt"):
                return ancestor
    return ((track.get("parentTracker") or {}).get("locator")) or None


def _ancestors(nodes: TplNodes, name: str) -> Iterable[str]:
    """Names above a node (unnamed nodes as ``#index``), walked by index so unnamed links do not stop it."""
    index, seen = nodes.index.get(name), set()
    while index is not None and 0 <= index < len(nodes.parents) and index not in seen:
        seen.add(index)
        parent = nodes.parents[index]
        if parent < 0:
            return
        yield nodes.name_of(parent)
        index = parent


def body_joints(markup: dict[str, Any] | None) -> dict[str, str]:
    """Constraint kind (``fixed``, ``hinge``, ``prismatic``, ...) joining each jointed body to its parent;
    bodies without one are roots."""
    joints: dict[str, str] = {}
    for info in (markup or {}).get("objectInfos") or []:
        name = (info.get("objectId") or {}).get("name")
        for entity in info.get("entities") or []:
            kind = str(entity.get("__type", ""))
            if kind.startswith("tpl_markup_constraint_"):
                joints[name] = kind[len("tpl_markup_constraint_"):]
    return joints


def body_motors(markup: dict[str, Any] | None) -> dict[str, str | None]:
    """The motor type (``tpl_markup_spring_motor``, ...) on each jointed body's constraint, ``None`` if it has none."""
    motors: dict[str, str | None] = {}
    for info in (markup or {}).get("objectInfos") or []:
        name = (info.get("objectId") or {}).get("name")
        for entity in info.get("entities") or []:
            if str(entity.get("__type", "")).startswith("tpl_markup_constraint_"):
                motor = entity.get("motor")
                motors[name] = str(motor.get("__type")) if isinstance(motor, dict) and motor.get("__type") else None
    return motors


HT500_FRAME_HINT = ("retail Greenway HT500: tpl_markup_constraint_hinge, childRotation [0,90,0], limited -5..5 deg, "
                    "motor tpl_markup_spring_motor { spring = 10000000, damping = 11000000 }, pivot at the frame bone")


def body_masses(markup: dict[str, Any] | None) -> dict[str, float]:
    """Explicit rigid-body masses of a parsed ``.tpl_markup`` (objectInfos with physics properties)."""
    masses: dict[str, float] = {}
    for info in (markup or {}).get("objectInfos") or []:
        name = (info.get("objectId") or {}).get("name")
        for prop in info.get("properties") or []:
            if prop.get("__type") == "tpl_markup_object_property_physics" and prop.get("mass") is not None:
                masses[name] = float(prop["mass"])
    return masses


def track_layout(doc: dict[str, Any], nodes: TplNodes | None = None) -> list[dict[str, Any]]:
    """Per track: every real and fake wheel with its axle, kind, radius, modelled bottom height
    (native Y of the slot minus the radius; None without the model) and the body it hangs on."""
    settings = doc.get("truckSettings") or {}
    slots = settings.get("wheelSlots") or []
    out = []
    for index, track in enumerate(settings.get("tracks") or []):
        wheels = []
        for role, ids in (("real", track.get("wheelIds") or []), ("fake", track.get("fakeWheelIds") or [])):
            for i in ids:
                if not isinstance(i, int) or not 0 <= i < len(slots):
                    wheels.append({"slot": i, "role": role, "error": "slot index out of range"})
                    continue
                slot = slots[i]
                name = slot.get("geomName")
                axle_name, axle = axle_for(slot, settings)
                radius = wheel_radius(doc, slot)
                bottom = None
                if nodes is not None and name in nodes.index and radius is not None:
                    bottom = round(nodes.position(name)[1] - radius, 4)
                wheels.append({"slot": i, "geomName": name, "role": role, "axle": axle_name,
                               "kind": axle_kind(axle), "radius": radius, "bottom": bottom,
                               "body": hanging_body(nodes, slot, track)})
        bottoms = [w["bottom"] for w in wheels if w.get("bottom") is not None]
        lowest = min(bottoms) if bottoms else None
        for w in wheels:
            w["ground"] = None if lowest is None or w.get("bottom") is None else w["bottom"] - lowest <= GROUND_TOLERANCE
        out.append({"track": index, "wheels": wheels, "lowestBottom": lowest})
    return out


def stop_fake_axles(doc: dict[str, Any], nodes: TplNodes | None = None) -> set[str]:
    """Suspension items used only by stop fakes in tracks that also have a rigid real wheel at ground
    level: the retail EPEC TC305 layout, where those fakes rest on their stops by design (RC004/RC005
    report them as info). Empty without the model."""
    layout = track_layout(doc, nodes)
    used: dict[str, set[bool]] = {}
    for track in layout:
        anchored = any(w["role"] == "real" and w["kind"] == "rigid" and w.get("ground") for w in track["wheels"])
        for w in track["wheels"]:
            if w.get("axle"):
                used.setdefault(w["axle"], set()).add(anchored and w["role"] == "fake" and w["kind"] == "stops")
    settings = doc.get("truckSettings") or {}
    tracked = {i for t in settings.get("tracks") or [] for i in (t.get("wheelIds") or []) + (t.get("fakeWheelIds") or [])}
    for i, slot in enumerate(settings.get("wheelSlots") or []):   # an axle also used outside the tracks
        if i not in tracked and slot.get("suspensionCollectionItem"):
            used.setdefault(slot["suspensionCollectionItem"], set()).add(False)
    return {axle for axle, flags in used.items() if flags == {True}}


def track_findings(doc: dict[str, Any], nodes: TplNodes | None = None,
                   markup: dict[str, Any] | None = None) -> list[tuple[str, str, str, str]]:
    """(code, severity, message, where) for RC046-RC048."""
    found: list[tuple[str, str, str, str]] = []
    layout = track_layout(doc, nodes)
    masses = body_masses(markup) if markup is not None else {}
    joints = body_joints(markup) if markup is not None else {}
    total = sum(masses.values())
    for track in layout:
        where = f"truckSettings.tracks[{track['track']}]"
        ground = [w for w in track["wheels"] if w.get("ground")]
        if ground and not any(w["role"] == "real" for w in ground) and all(w["kind"] == "stops" for w in ground):
            raised = sorted({w["geomName"] for w in track["wheels"] if w["role"] == "real" and w.get("bottom") is not None})
            found.append(("RC046", "warning",
                          f"only fake wheels resting on their top stops carry this track ({len(ground)} at ground level); "
                          f"its real wheels {raised} sit above them. Retail pairs stop fakes with rigid real wheels at "
                          "ground level (EPEC TC305) or springs the fakes; KGS25 sank a track 19 cm in pivot turns",
                          where))
        bodies = {w.get("body") for w in track["wheels"] if w.get("body")}
        motors = body_motors(markup) if markup is not None else {}
        for body in sorted(bodies):
            if body not in joints:
                continue          # a root body (no joint to a parent), or no markup
            share = masses[body] / total if body in masses and total > 0 else None
            weight = (f" at {masses[body]:g} kg ({share:.0%} of {total:g} kg of bodies)" if share is not None else "")
            light = (f"; it is also light (under {FRAME_SHARE_WARNING:.0%}: KGS25 frames at 6 % sank or lifted a track)"
                     if share is not None and share < FRAME_SHARE_WARNING else "")
            if joints[body] == "fixed":
                found.append(("RC047", "warning",
                              f"the track's wheels hang on {body}, welded on with a fixed joint{weight}: the frame "
                              f"cannot spring, so every bump goes straight into the hull{light}. Fix: {HT500_FRAME_HINT}",
                              where))
            elif joints[body] in ("hinge", "prismatic") and motors.get(body) is None:
                found.append(("RC047", "warning",
                              f"the track's wheels hang on {body}, on a {joints[body]} with no motor{weight}: an unsprung "
                              f"frame flops between its limits. Fix: {HT500_FRAME_HINT}", where))
            if share is None or share >= FRAME_SHARE_WARNING:
                continue
            sprung = [w["geomName"] for w in track["wheels"] if w.get("body") == body and w["kind"] == "sprung"]
            if sprung:
                found.append(("RC048", "info",
                              f"sprung wheels {sprung} hang on {body} ({share:.0%} of the body mass): the sag law is "
                              "unknown, so measure the rest on the physics bench (the earlier mass-scaling rationale is "
                              "unsupported, tracked-vehicles.md)", where))
    return found


def retail_track_survey(game_root, names: Iterable[str] | None = None) -> dict[str, Any]:
    """Every retail crawler: its tracks' wheel layout, and whether RC046/RC047 would flag it."""
    rows = []
    wanted = set(names) if names else None
    for name, doc in retail.iter_retail_bros(game_root):
        settings = doc.get("truckSettings") or {}
        if not settings.get("tracks") or (wanted and name not in wanted):
            continue
        nodes = markup = None
        notes = []
        tpl = doc.get("tpl")
        try:
            anchor = next((s.get("geomName") for s in settings.get("wheelSlots") or [] if s.get("geomName")), None)
            nodes = read_tpl_bytes(retail.retail_tpl_bytes(game_root, tpl), anchor=anchor)
        except Exception as exc:  # noqa: BLE001 - a survey row records why geometry is missing
            notes.append(f"model: {type(exc).__name__}")
        try:
            markup = ps_format.loads(retail.retail_markup_text(game_root, tpl))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"markup: {type(exc).__name__}")
        layout = track_layout(doc, nodes)
        flags = sorted({f[0] for f in track_findings(doc, nodes, markup)})
        rows.append({"truck": name, "tpl": tpl, "tracks": layout, "flags": flags, "notes": notes})
    return {"vehicles": len(rows), "flagged": {r["truck"]: r["flags"] for r in rows if r["flags"]}, "rows": rows}
