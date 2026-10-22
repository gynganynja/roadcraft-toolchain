"""Effective physics values of a truck mod, and a side-by-side comparison with a retail donor.

``report(target)`` reads a built ``.pak`` or a mod source tree (``mods_source`` or a folder laid out
like one) and lists, for every truck class in it, the value the engine will use for each physics field:

* bodies of the model markup (``tpl_markup_object_property_physics``) with the constraint joining
  each to its parent and that constraint's motor;
* wheel classes (``wheelPool``), with their friction tables flattened per surface;
* wheel slots (class, side, parent body, suspension axle, track membership);
* the suspension axles the slots use (``suspensionAxleCollection`` or the ``suspensionSet`` fallback);
* tracks (section height, tension, parentTracker, real/fake wheel counts);
* truck-level drivetrain, steering, soft-contact and track-steering curves;
* derived quantities that need no unknown law: total mass, wheel / parent-body mass ratio, frame
  share, physics wheels per track, a centre-of-mass height proxy against the track width;
* each body's inertia estimated from its cdt_ shapes (the ``.tpl`` per-mesh bounds, solid boxes, mass by
  volume; :func:`body_inertia`), and ``inertia_distribution`` gives its retail spread per body role;
* each prismatic / limited hinge child body's sweep over its travel: the first contact of its shapes (and of the
  bodies and wheels below it) with an unfiltered shape of the truck, per side (:func:`joint_sweeps`).

Every value is ``{"value", "source", "evidence"}``.  ``source`` is ``explicit`` (set in the file),
``inherited`` (set in a base class reached through ``__type``), ``engine-default`` (the engine's own
default, confirmed from code in C:\\RC_RE\\research\\physics_semantics.md), ``schema-default`` (the
Mod Editor schema default; :mod:`roadcraft.schema`, or a built-in copy of it when no SDK is
installed), ``absent`` (not set and no default applies) or ``derived`` (computed here from other
values; the evidence names the inputs).

``compare(mod, donor)`` matches the two reports by role (truck, hull, track frame, idler/drive wheel,
contact wheel, wheel, their axles, track, derived) and adds the distribution of each field over every
retail truck of the same kind (tracked / wheeled) from the installed game, flagging values outside
the retail min..max and entries every retail truck has but the mod lacks.

Deliberately not computed: static sag or spring rate (the T4 sag law is withdrawn, F3), body mass for
``massFromDensity`` bodies (600 kg/m^3 x the cdt_ convex volume; the .tpl gives boxes, which over-fill it),
soft-contact force (law not decompiled).  library/physics-report.md documents fields, sources and
limits.  Read-only and standard library only.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import statistics
import sys
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable

from . import joint_sweep
from . import ps_format
from . import retail as retail_mod
from . import schema as schema_mod
from .tpl_reader import TplFormatError, TplNodes, find_parents, read_tpl_bytes

SOURCES = ("explicit", "inherited", "engine-default", "schema-default", "absent", "derived")
SOURCE_LETTER = {"explicit": "E", "inherited": "I", "engine-default": "D", "schema-default": "S",
                 "absent": "-", "derived": "~"}
SURFACES = ("default", "asphalt", "sand", "ground", "grass", "gravel", "mud_sand", "mud_grass", "sub_mud")
FRICTION_KEYS = ("frictionValue", "terrainDeformationFactor", "substanceFriction", "likeAsphalt")
RESEARCH = "physics_semantics.md"
RETAIL_TRUCKS = "ssl/autogen_designer_wizard/trucks/auto_*/auto_*.cls"

# ---- evidence (C:\RC_RE\research\physics_semantics.md section ids; ME = Roadcraft ModEditor.exe)
EV_BODY = f"ME FUN_1430811e0 body constructor, per missing key ({RESEARCH} F2a)"
EV_DENSITY = (f"massFromDensity: mass = density x cdt_ convex volume (Havok buildMassProperties); the volume is not "
              f"decoded from .tpl ({RESEARCH} Q2)")
EV_FRICTION_INIT = (f"ssl/game/truck/friction/prop_truck_friction_updater.ssc Init: no 'default' entry -> "
                    f"bodyFriction 2.0, substanceFriction 0, terrainDeformationFactor 1 ({RESEARCH} Q4)")
EV_STICKY = (f"prop_truck_friction_updater.ssc per frame: mapped entry missing -> return, the wheel keeps the "
             f"previous surface's friction ({RESEARCH} Q4)")
EV_AXLE_FALLBACK = (f"ME FUN_140dc7f80: suspensionCollectionAxleIndex < 0 -> suspensionSet.front (.rear when "
                    f"rearDiffers and the slot isRear) ({RESEARCH} T4)")
EV_WHEEL_MASS = f"ME FUN_140dc4eb0: wheel mass clamped >= 0.1 kg, x rearMassMultiplier on rear slots ({RESEARCH} Q2)"
EV_RADIUS = (f"ME FUN_140dc8520 SetTrackHeight: physical radius = radius - radiusOffset + section.height + "
             f"extraPhysicalRadius ({RESEARCH} T1)")
EV_TRACKED = f"section.height != 0 marks every track wheel as tracked; 0 disables track steering ({RESEARCH} headline 4)"
EV_TRACK_CTRL = (f"ME FUN_140e0aef0/FUN_140e0ac00: spline absent -> inner-track torque mult 1, no inner-track "
                 f"velocity brake ({RESEARCH} T3, section 4)")
EV_SOLVER = (f"editor.cfg Physics.Substep.fixedFps 60 and Havok.Physics.SolverType 4_iterations_medium; ME "
             f"FUN_14154cc00 = RT FUN_140ea6580; no per-vehicle field; retail game.cfg unverified ({RESEARCH} Q7)")
EV_TRAVEL = f"ME FUN_140dc80d0 GetMaxSpringTravelDistance = max - min, travel measured from the bump stop ({RESEARCH} F3)"
EV_FAKE = f"used only with prop_truck useFakeWheels (hkpRaycastWheel, FUN_140cac870); no retail truck sets it ({RESEARCH} T1)"
EV_MOTOR = f"ME FUN_141594b60: only declared motor members are read ({RESEARCH} T5)"
EV_PARENT_TRACKER = f"TruckTrack.parentTracker absent: belt frame is the truck ({RESEARCH} T2, section 4)"
EV_LOWRANGE = f"lowRangeMultiplier is not a TruckGearboxParams member; never read ({RESEARCH} F1)"
EV_COM = ("mass-weighted height of body bone origins (+ boneCenterOfMassOffset where havokMassCenter is False) and "
          "physics wheel nodes from the compiled .tpl node table. NOT the centre of mass: Havok puts a body's COM at "
          "its cdt_ hull centroid (+ hkCenterOfMassOffset), and the hull is not decoded")

# Engine defaults confirmed from code (override the schema where both exist).
BODY_ENGINE = {"angularDamping": 0.05, "linearDamping": 0, "massFromDensity": True, "density": 600, "mass": 1,
               "havokMassCenter": True, "hkCenterOfMassOffset": [0, 0, 0], "boneCenterOfMassOffset": [0, 0, 0],
               "friction": 0.5, "restitution": 0.4, "allowedPenetrationDepth": 0.05, "nonConvexShape": False}
BODY_FIELDS = ("massFromDensity", "mass", "density", "angularDamping", "linearDamping", "friction", "restitution",
               "allowedPenetrationDepth", "havokMassCenter", "hkCenterOfMassOffset", "boneCenterOfMassOffset",
               "nonConvexShape", "fixed", "disable", "collisionLayer")
WHEEL_FIELDS = ("mass", "radius", "radiusOffset", "width", "rearMassMultiplier", "sidewaysFrictionMultiplier",
                "sidewaysFrictionMaxVelocity", "isSoftContactEnabled", "isSoftContactEnableForStaticOnly",
                "softForceScale", "softForceScaleStatic", "substanceFriction", "substanceLinearResistance",
                "isWheelStabilizationEnabled", "activateAntiTunnelingModificatorOnInit",
                "activateCriticalCollisionTypeOnInit", "deformEnable", "collisionLayer")
AXLE_FIELDS = ("min", "max", "height", "strength", "damping", "linearLimitsStiffness", "linearLimitsDamping",
               "highPriorityConstrain", "fakeStrength", "fakeDampingCompression", "fakeDampingRelaxation")
TRUCK_FIELDS = ("useFakeWheels", "maxSteerSpeed", "backSteerSpeed", "pedalsResponsiveness", "isBackSteerIgnored",
                "diffLockType", "fakeWheelsFrictionMultiplier", "isUnlockDiffAvrVelocity",
                "isNeutralGearWheelResistanceEnabled", "isReverseWheelResistanceEnabled")
ENGINE_PARAMS = ("torque", "responsiveness", "brakesDelay", "maxDeltaAngVel", "jerkingScale", "jerkingPeriod")
GEARBOX_PARAMS = ("finalDriveRatio", "defaultGearSwitchDelay", "isLowRangeModeReverseEnabled",
                  "isLowRangeModeClutchingEnabled")
TRACK_CTRL_SPLINES = ("steeringInputToInnerTrackTorqueMult", "neutralSteeringInputToInnerTrackTorqueMult",
                      "linearVelocityToInnerTrackTorqueMult")
MOTOR_MEMBERS = {"tpl_markup_position_motor": ("tau", "damping", "maxForce", "proportionalRecoveryVelocity",
                                               "constantRecoveryVelocity"),
                 "tpl_markup_spring_motor": ("spring", "damping")}
CONSTRAINT_KEYS = ("limited", "angleStart", "angleEnd", "isMinLimit", "minLimit", "isMaxLimit", "maxLimit",
                   "strengthFactor", "dampingFactor", "massFactor", "isMalleable", "malleableStrength",
                   "isBreakable", "breakThreshold", "enabled")

# Built-in copy of the SDK schema defaults used here (roadcraft.schema, 2026-10-13 SDK), for machines without it.
BUILTIN_DEFAULTS: dict[str, dict[str, Any]] = {
    "PropTruckWheel": {"activateAntiTunnelingModificatorOnInit": True, "activateCriticalCollisionTypeOnInit": False,
                       "collisionLayer": "physics", "deformEnable": False, "isSoftContactEnableForStaticOnly": False,
                       "isSoftContactEnabled": True, "isWheelStabilizationEnabled": False, "mass": 0, "radius": 0,
                       "radiusOffset": 0, "rearMassMultiplier": 1, "sidewaysFrictionMaxVelocity": 1,
                       "sidewaysFrictionMultiplier": 1, "softForceScale": 1, "softForceScaleStatic": 1,
                       "substanceFriction": 0, "substanceLinearResistance": 0, "width": 0, "geomRadius": -1},
    "FrictionMaterial": {"frictionValue": 2, "likeAsphalt": False, "substanceFriction": 0,
                         "terrainDeformationFactor": 1},
    "TruckTrack": {"trackTensionDefault": 0.04, "trackTensionDrive": 0.16},
    "TruckTrackSection": {"height": 0.1, "segmentLength": 0.2, "tpl": ""},
    "TruckTrackControls": {"hasNeutralSteering": True},
    "tpl_markup_object_property_physics": {"allowedPenetrationDepth": 0.05, "angularDamping": 0.05,
                                           "boneCenterOfMassOffset": [0, 0, 0], "collisionLayer": "default",
                                           "density": 600, "disable": False, "fixed": False, "friction": 0.5,
                                           "havokMassCenter": True, "hkCenterOfMassOffset": [0, 0, 0],
                                           "linearDamping": 0, "mass": 1, "massFromDensity": True,
                                           "nonConvexShape": False, "restitution": 0.4},
    "tpl_markup_position_motor": {"constantRecoveryVelocity": 0.15, "damping": 0.95, "maxForce": 100,
                                  "proportionalRecoveryVelocity": 1, "tau": 0.23},
    "tpl_markup_spring_motor": {"damping": 0, "spring": 0},
    "tpl_markup_constraint_wheel": {"dampingFactor": 0, "maxLimit": 0, "minLimit": 0, "strengthFactor": 0,
                                    "massFactor": 1},
    "physTRUCK_SUSPENSION_AXLE_DESC": {"damping": 0, "fakeDampingCompression": 3, "fakeDampingRelaxation": 3,
                                       "fakeStrength": 50, "height": 0, "highPriorityConstrain": True,
                                       "linearLimitsDamping": -1, "linearLimitsStiffness": -1, "max": 1, "min": 0,
                                       "strength": 0},
    "physTRUCK_SOFT_CONTACT_DESC": {"forceScale": 1, "forceScaleStatic": 1, "maxPenetrationDepth": 0.1},
    "prop_truck_rb": {"backSteerSpeed": 1, "diffLockType": "DEFAULT", "fakeWheelsFrictionMultiplier": 1,
                      "isNeutralGearWheelResistanceEnabled": True, "isReverseWheelResistanceEnabled": False,
                      "isUnlockDiffAvrVelocity": False, "maxSteerSpeed": 1, "pedalsResponsiveness": 1,
                      "useFakeWheels": False},
    "TruckWheelSlotWithDesc": {"extraPhysicalRadius": 0, "handbrakeStrength": 0.05, "isConnectedToHandbrake": False,
                               "isRear": False, "isRightSided": False, "parentFrame": "", "radiusOverride": -1,
                               "suspensionCollectionAxleIndex": -1, "torqueType": "none"},
    "TruckEngineParams": {"brakesDelay": 0, "jerkingPeriod": 0.2, "jerkingScale": 2, "maxDeltaAngVel": 0,
                          "responsiveness": 0, "torque": 0},
    "TruckGearboxParams": {"defaultGearSwitchDelay": 0.5, "finalDriveRatio": 3.9, "isLowRangeModeClutchingEnabled": True,
                           "isLowRangeModeReverseEnabled": False},
    "TruckSingleGearParams": {"angularVelocity": 0, "gearRatio": 1},
}

ROLE_ORDER = ("truck", "hull", "track frame", "track", "axle: idler/drive wheel", "idler/drive wheel",
              "axle: contact wheel", "contact wheel", "axle: wheel", "wheel", "axle: untracked wheel",
              "untracked wheel", "derived")
# Fields whose values are names, not quantities: no retail distribution, compared only for presence.
NAME_FIELDS = {"class", "slot.class", "slot.parentBody", "slot.axle", "section.tpl", "joint.target", "parentTracker",
               "visual", "collisionLayer", "name", "slot.track", "slot.geomName", "friction.entries"}
# Always shown in the text form (the fields behind the tracked-vehicle jank diagnosis, library/physics-report.md).
KEY_FIELDS = ("mass", "slot.massRatio", "softForceScale", "softForceScaleStatic", "isSoftContactEnabled",
              "isSoftContactEnableForStaticOnly", "sidewaysFrictionMultiplier", "sidewaysFrictionMaxVelocity",
              "friction.entries", "friction.*.frictionValue", "friction.*.terrainDeformationFactor", "section.height",
              "parentTracker", "trackTensionDefault", "trackControls.*", "joint.type", "strength", "damping",
              "physicsWheels", "totalMass", "effectiveMass")
PRESENCE_FIELDS = {"parentTracker"}
# Keys the engine never reads: shown, never flagged against retail.
IGNORED_FIELDS = {"gearbox.lowRangeMultiplier", "joint.motor.ignoredKeys"}
OUTLIER_FLAGS = {"outside-retail", "missing", "absent-in-mod", "unseen-in-retail"}


class PhysicsReportError(RuntimeError):
    """The target or donor cannot be read."""


# ------------------------------------------------------------------------------------------------ values

def _clean(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        out = float(f"{value:.6g}")
        return int(out) if out.is_integer() and abs(out) < 1e15 else out
    if isinstance(value, dict):
        if "spline" in value and isinstance(value["spline"], list):
            return _clean(value["spline"])
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def V(value: Any, source: str, evidence: str, note: str | None = None) -> dict[str, Any]:  # noqa: N802
    out = {"value": _clean(value), "source": source, "evidence": evidence}
    if note:
        out["note"] = note
    return out


def _kp(path: Iterable[Any]) -> str:
    out = ""
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


_MISSING = object()


def _dig(doc: Any, path: Iterable[Any]) -> Any:
    for key in path:
        if isinstance(doc, dict) and key in doc:
            doc = doc[key]
        elif isinstance(doc, list) and isinstance(key, int) and 0 <= key < len(doc):
            doc = doc[key]
        else:
            return _MISSING
    return doc


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


# ------------------------------------------------------------------------------------------------ stores

class Store:
    """Files of one place (a pak, a folder, the retail paks), by lower-case path."""

    def __init__(self, label: str, kind: str, readers: dict[str, tuple[str, Callable[[], bytes]]],
                 sha256: str | None = None) -> None:
        self.label, self.kind, self.sha256 = label, kind, sha256
        self.readers = readers
        self.stems: dict[tuple[str, str], str] = {}
        for lower in sorted(readers):
            base = lower.rsplit("/", 1)[-1]
            stem, dot, ext = base.partition(".")
            if dot:
                self.stems.setdefault((stem, "." + ext), lower)
        self._cache: dict[str, bytes] = {}

    def names(self) -> list[str]:
        return sorted(self.readers)

    def has(self, name: str) -> bool:
        return name.lower() in self.readers

    def read(self, name: str) -> bytes:
        key = name.lower()
        if key not in self._cache:
            self._cache[key] = self.readers[key][1]()
        return self._cache[key]

    def display(self, name: str) -> str:
        real = self.readers[name.lower()][0] if name.lower() in self.readers else name
        return {"pak": f"{self.label}!{real}", "retail": f"retail:{real}"}.get(self.kind, real)

    def find_stem(self, stem: str, ext: str) -> str | None:
        return self.stems.get((stem.lower(), ext.lower()))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_store(target: str | Path) -> Store:
    path = Path(target)
    if path.is_dir():
        root = path / "mods_source" if (path / "mods_source").is_dir() else path
        readers: dict[str, tuple[str, Callable[[], bytes]]] = {}
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in {".git", ".venv", "__pycache__", "intermediate"})
            for filename in sorted(filenames):
                full = Path(dirpath) / filename
                rel = full.relative_to(root).as_posix()
                readers.setdefault(rel.lower(), (rel, (lambda f=full: f.read_bytes())))
        return Store(root.as_posix(), "folder", readers)
    if path.is_file() and zipfile.is_zipfile(path):
        archive = zipfile.ZipFile(path)
        readers = {}
        for info in archive.infolist():
            if not info.is_dir():
                name = info.filename.replace("\\", "/")
                readers.setdefault(name.lower(), (name, (lambda i=info: archive.read(i))))
        return Store(path.name, "pak", readers, sha256=_sha256_file(path))
    raise PhysicsReportError(f"not a mod folder or a .pak: {target}")


# ------------------------------------------------------------------------------------------------ context

class Context:
    """Schema defaults and the retail paks of an installation (both optional)."""

    def __init__(self, game_root: str | Path | None = None) -> None:
        root = Path(game_root) if game_root else schema_mod.default_game_root()
        self.game_root: Path | None = root if (root / retail_mod.PAK_DIR).is_dir() else None
        self._schema: Any = None
        self._schema_tried = False
        self._retail: Store | None = None
        self._docs: dict[tuple[int, str], Any] = {}
        self.retail_cache: dict[str, dict[str, Any]] = {}
        self.retail_names: dict[str, str] | None = None
        self.notes: list[str] = []

    def schema(self) -> Any:
        if not self._schema_tried:
            self._schema_tried = True
            try:
                self._schema = schema_mod.load(self.game_root) if self.game_root else None
            except (schema_mod.SchemaError, OSError, ps_format.PsSyntaxError):
                self._schema = None
        return self._schema

    def default(self, type_name: str, field: str) -> tuple[bool, Any, str]:
        sch = self.schema()
        if sch is not None:
            key = sch.find(type_name)
            fld = sch.field(key, field) if key else None
            if fld is not None and fld.get("default") is not None:
                return True, schema_mod._plain(fld["default"]), f"schema {key}.{field}"
        builtin = BUILTIN_DEFAULTS.get(type_name, {})
        if field in builtin:
            return True, builtin[field], f"schema {type_name}.{field} (built-in copy; SDK schema not loaded)"
        return False, None, ""

    def retail(self) -> Store | None:
        if self._retail is None and self.game_root is not None:
            index = retail_mod._index(self.game_root)
            archives: dict[Path, zipfile.ZipFile] = {}

            def reader(name: str, pak: Path) -> Callable[[], bytes]:
                def read() -> bytes:
                    if pak not in archives:              # one open handle per pak, not one per member
                        archives[pak] = zipfile.ZipFile(pak)
                    return archives[pak].read(name)
                return read
            readers = {name.lower(): (name, reader(name, pak)) for name, pak in index.items()}
            self._retail = Store("retail", "retail", readers)
        return self._retail

    def stores(self, own: Store | None) -> list[Store]:
        out = [own] if own is not None else []
        r = self.retail()
        if r is not None and r is not own:
            out.append(r)
        return out

    def find(self, stores: list[Store], stem: str, ext: str) -> tuple[Store, str] | None:
        for store in stores:
            name = store.find_stem(stem, ext)
            if name is not None:
                return store, name
        return None

    def ps(self, store: Store, name: str) -> Any:
        key = (id(store), name.lower())
        if key not in self._docs:
            text = store.read(name).decode("utf-8-sig", errors="replace")
            try:
                self._docs[key] = ps_format.editor_loads(text, lines=False)
            except ps_format.PsSyntaxError:
                self._docs[key] = None
        return self._docs[key]


def pick(ctx: Context, cands: list[tuple[Any, str, tuple]], key: str, type_name: str | None = None,
         engine: tuple[Any, str] | None = None, label: str | None = None) -> dict[str, Any]:
    """The effective value of ``key``: the first candidate container holding it (the first candidate is the
    entity's own file: explicit; later ones are base classes: inherited), else the engine default, else the
    schema default of ``type_name``, else absent."""
    for depth, (container, where, base) in enumerate(cands):
        if isinstance(container, dict) and key in container:
            return V(container[key], "explicit" if depth == 0 else "inherited", f"{where}:{_kp(base + (key,))}")
    if engine is not None:
        return V(engine[0], "engine-default", engine[1])
    if type_name:
        ok, value, evidence = ctx.default(type_name, key)
        if ok:
            return V(value, "schema-default", evidence)
    return V(None, "absent", f"{label or key} not set; no default applies")


# ------------------------------------------------------------------------------------------------ classes

def class_layers(ctx: Context, stores: list[Store], store: Store, name: str, depth: int = 0) -> list[tuple[Any, str]]:
    """(document, display) of a class and its ``__type`` base classes, most derived first."""
    doc = ctx.ps(store, name)
    if not isinstance(doc, dict):
        return []
    layers = [(doc, store.display(name))]
    parent = doc.get("__type")
    if isinstance(parent, str) and depth < 8:
        hit = ctx.find(stores, parent, ".cls")
        if hit is not None and not (hit[0] is store and hit[1] == name.lower()):
            layers += class_layers(ctx, stores, hit[0], hit[1], depth + 1)
    return layers


def _cands(layers: list[tuple[Any, str]], path: tuple) -> list[tuple[Any, str, tuple]]:
    return [(_dig(doc, path), where, path) for doc, where in layers]


def _first(layers: list[tuple[Any, str]], path: tuple) -> tuple[Any, str | None, tuple]:
    for doc, where in layers:
        value = _dig(doc, path)
        if value is not _MISSING:
            return value, where, path
    return None, None, path


def _is_truck(doc: Any) -> bool:
    rb = _dig(doc, ("properties", "prop_truck_rb"))
    return isinstance(rb, dict) and bool(rb.get("wheelSlotWithDescs"))


def truck_classes(ctx: Context, store: Store) -> list[str]:
    out = []
    for name in store.names():
        base = name.rsplit("/", 1)[-1]
        if not name.endswith(".cls") or "preview" in base:
            continue
        if b"prop_truck_rb" not in store.read(name):
            continue
        doc = ctx.ps(store, name)
        if _is_truck(doc) and "preview" not in str(doc.get("__type", "")):
            out.append(name)
    return out


# ------------------------------------------------------------------------------------------------ report

def _entity(eid: str, kind: str, role: str, fields: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"id": eid, "kind": kind, "role": role, "fields": fields, **extra}


def _cdt_under_bodies(bodies: set[str]) -> Callable[[TplNodes, tuple[int, ...]], tuple[int, int]]:
    """Parent-array tie-break: the candidate that hangs the most cdt_ meshes directly under markup bodies, then
    the one with the most parents stored before their children (the two-byte shifted copy of the real array
    ties on everything else; the real one is the more nearly pre-ordered: the retail Baikal crane trucks,
    the kanga25 mod)."""
    def score(nodes: TplNodes, parents: tuple[int, ...]) -> tuple[int, int]:
        names = {index: name for name, index in nodes.index.items()}
        direct = sum(1 for i, p in enumerate(parents)
                     if names.get(i, "").lower().startswith("cdt") and p >= 0 and names.get(p) in bodies)
        return direct, sum(1 for i, p in enumerate(parents) if p < i)
    return score


def _load_nodes(ctx: Context, stores: list[Store], tpl: str | None, anchor: str | None,
                need_parents: bool, bodies: set[str] | None = None) -> tuple[TplNodes | None, str | None]:
    hit = ctx.find(stores, tpl, ".tpl") if tpl else None
    if hit is None:
        return None, None
    data = hit[0].read(hit[1])
    for a in (anchor, None):
        try:
            nodes = read_tpl_bytes(data, anchor=a, parents=False, bounds=True)
            if need_parents:
                find_parents(data, nodes, tiebreak=_cdt_under_bodies(bodies) if bodies else None)
            return nodes, hit[0].display(hit[1])
        except Exception:  # noqa: BLE001 - a model that does not decode (TplFormatError, struct errors)
            continue
    return None, hit[0].display(hit[1])


def _markup(ctx: Context, stores: list[Store], tpl: str | None) -> tuple[list[Any], str | None]:
    """objectInfos of the model markup (tpl_markup over tpl/<x>.lods_base; arrays replace, schema.md 4.1)."""
    if not tpl:
        return [], None
    for ext in (".tpl_markup", ".lods_base"):
        hit = ctx.find(stores, tpl, ext)
        if hit is None:
            continue
        doc = ctx.ps(*hit)
        infos = doc.get("objectInfos") if isinstance(doc, dict) else None
        if isinstance(infos, list):
            return infos, hit[0].display(hit[1])
    return [], None


def _bodies(ctx: Context, infos: list[Any], where: str | None) -> list[dict[str, Any]]:
    out = []
    for oi, info in enumerate(infos):
        if not isinstance(info, dict):
            continue
        name = _dig(info, ("objectId", "name"))
        props = info.get("properties") or []
        pidx = next((i for i, p in enumerate(props) if isinstance(p, dict)
                     and p.get("__type") == "tpl_markup_object_property_physics"), None)
        if pidx is None or not isinstance(name, str):
            continue
        phys = props[pidx]
        base = ("objectInfos", oi, "properties", pidx)
        fields: dict[str, Any] = {}
        for key in BODY_FIELDS:
            engine = (BODY_ENGINE[key], EV_BODY) if key in BODY_ENGINE else None
            fields[key] = pick(ctx, [(phys, where or "markup", base)], key, "tpl_markup_object_property_physics",
                               engine)
        if fields["massFromDensity"]["value"] is False:
            fields["effectiveMass"] = V(fields["mass"]["value"], "derived", f"mass ({fields['mass']['evidence']})")
        else:
            fields["effectiveMass"] = V(None, "derived", EV_DENSITY,
                                        note=f"massFromDensity: {fields['density']['value']} kg/m^3 x cdt_ volume (not decoded)")
        joint = None
        for ei, ent in enumerate(info.get("entities") or []):
            kind = str(ent.get("__type", "")) if isinstance(ent, dict) else ""
            if kind.startswith("tpl_markup_constraint_"):
                joint = (ei, ent)
                break
        if joint is not None:
            ei, ent = joint
            jbase = ("objectInfos", oi, "entities", ei)
            jw = where or "markup"
            fields["joint.type"] = V(ent["__type"][len("tpl_markup_constraint_"):], "explicit",
                                     f"{jw}:{_kp(jbase + ('__type',))}")
            fields["joint.target"] = pick(ctx, [(ent, jw, jbase)], "target", ent["__type"],
                                          engine=None)
            if ent["__type"] == "tpl_markup_constraint_wheel":
                for key in ("minLimit", "maxLimit", "strengthFactor", "dampingFactor"):
                    fields[f"joint.{key}"] = pick(ctx, [(ent, jw, jbase)], key, "tpl_markup_constraint_wheel")
            for key in CONSTRAINT_KEYS:
                if key in ent and f"joint.{key}" not in fields:
                    fields[f"joint.{key}"] = V(ent[key], "explicit", f"{jw}:{_kp(jbase + (key,))}")
            motor = ent.get("motor")
            if isinstance(motor, dict):
                mtype = str(motor.get("__type", ""))
                mbase = jbase + ("motor",)
                fields["joint.motor.type"] = V(mtype or None, "explicit" if mtype else "absent",
                                               f"{jw}:{_kp(mbase + ('__type',))}")
                members = MOTOR_MEMBERS.get(mtype)
                if members is None:
                    fields["joint.motor.note"] = V("unknown motor type: no motor is created", "explicit", EV_MOTOR)
                else:
                    for key in members:
                        fields[f"joint.motor.{key}"] = pick(ctx, [(motor, jw, mbase)], key, mtype)
                    ignored = sorted(k for k in motor if k not in members and k != "__type")
                    if ignored:
                        fields["joint.motor.ignoredKeys"] = V(ignored, "explicit", f"{jw}:{_kp(mbase)}; {EV_MOTOR}",
                                                              note="keys the engine never reads")
        out.append(_entity(name, "body", "body", fields, root=joint is None, objectIndex=oi,
                           explicitInertia=_explicit_inertia(phys, where or "markup", base)))
    return out


def _markup_groups(ctx: Context, stores: list[Store], tpl: str | None) -> tuple[list[list[str]], list[str]]:
    """Member lists and names of the model markup's Collision Groups (``collisionGroups.<name>.objects``)."""
    hit = ctx.find(stores, tpl, ".tpl_markup") if tpl else None
    if not hit:
        return [], []
    doc = ctx.ps(*hit)
    return joint_sweep.collision_groups(doc), joint_sweep.collision_group_names(doc)


def _slot_axle(ctx: Context, rb_layers: list[tuple[Any, str]], slot: dict, si: int, slot_where: str
               ) -> tuple[str, dict[str, Any], str]:
    """(axle id, axle container, evidence) for a slot."""
    idx = slot.get("suspensionCollectionAxleIndex", -1)
    rb_path = ("properties", "prop_truck_rb")
    if isinstance(idx, int) and idx >= 0:
        coll, where, path = _first(rb_layers, ("suspensionAxleCollection",))
        path = rb_path + path
        if isinstance(coll, list) and idx < len(coll):
            return f"axle[{idx}]", {"container": coll[idx], "where": where, "path": path + (idx,)}, \
                f"{slot_where}.suspensionCollectionAxleIndex = {idx}"
        return f"axle[{idx}] (missing)", {"container": None, "where": where or "class", "path": path + (idx,)}, \
            f"{slot_where}.suspensionCollectionAxleIndex = {idx}, no such suspensionAxleCollection item"
    sset, where, path = _first(rb_layers, ("suspensionSet",))
    path = rb_path + path
    sset = sset if isinstance(sset, dict) else {}
    key = "rear" if sset.get("rearDiffers") and slot.get("isRear") else "front"
    return f"suspensionSet.{key}", {"container": sset.get(key), "where": where or "class", "path": path + (key,)}, \
        EV_AXLE_FALLBACK


def _wheel_class(ctx: Context, stores: list[Store], pool_key: str, cls_name: str | None) -> dict[str, Any]:
    eid = f"class:{pool_key}"
    if not cls_name:
        return _entity(eid, "wheelClass", "", {"class": V(None, "absent", f"wheelPool.{pool_key} has no class")})
    hit = ctx.find(stores, cls_name, ".cls")
    if hit is None:
        return _entity(eid, "wheelClass", "", {"class": V(cls_name, "explicit", f"wheelPool.{pool_key}",
                                                          note="class file not found")})
    layers = class_layers(ctx, stores, *hit)
    fields: dict[str, Any] = {"class": V(cls_name, "explicit", f"wheelPool.{pool_key}")}
    wheel_path = ("properties", "prop_truck_wheel")
    if _first(layers, wheel_path)[1] is None:
        visual = _first(layers, ("properties", "prop_truck_visual_wheel"))[1] is not None
        fields["visual"] = V(visual, "explicit", hit[0].display(hit[1]),
                             note="visual wheel: no rigid body (truck_visual_wheel_prop.cpp, T1)" if visual else
                             "no prop_truck_wheel")
        return _entity(eid, "wheelClass", "", fields, physics=False)
    for key in WHEEL_FIELDS:
        fields[key] = pick(ctx, _cands(layers, wheel_path), key, "PropTruckWheel")
    mass = _num(fields["mass"]["value"])
    if mass is not None and mass < 0.1:
        fields["mass"]["note"] = f"clamped to 0.1 kg by the engine ({EV_WHEEL_MASS})"
    table_path = ("properties", "prop_truck_friction_updater", "frictionMaterialsList")
    tables = _cands(layers, table_path)
    present = sorted({k for t, _, _ in tables if isinstance(t, dict) for k in t if not k.startswith("__")})
    first_table = next(((t, w, p) for t, w, p in tables if isinstance(t, dict)), None)
    fields["friction.entries"] = V(present if first_table else None, "explicit" if first_table else "absent",
                                   f"{first_table[1]}:{_kp(table_path)}" if first_table else
                                   "no frictionMaterialsList: every surface keeps bodyFriction 2.0 " + EV_FRICTION_INIT)
    for surface in list(SURFACES) + [s for s in present if s not in SURFACES]:
        entry_cands = [(_dig(t, (surface,)) if isinstance(t, dict) else _MISSING, w, p + (surface,))
                       for t, w, p in tables]
        has_entry = any(isinstance(c, dict) for c, _, _ in entry_cands)
        for key in FRICTION_KEYS:
            name = f"friction.{surface}.{key}"
            if has_entry:
                fields[name] = pick(ctx, entry_cands, key, "FrictionMaterial")
            elif surface == "default" and key != "likeAsphalt":
                fields[name] = V({"frictionValue": 2.0, "substanceFriction": 0, "terrainDeformationFactor": 1}[key],
                                 "engine-default", EV_FRICTION_INIT)
            else:
                fields[name] = V(None, "absent", EV_STICKY if surface != "default" else EV_FRICTION_INIT,
                                 note=f"no '{surface}' entry: the wheel keeps the previous friction on this surface"
                                 if surface != "default" else None)
    return _entity(eid, "wheelClass", "", fields, physics=True)


def _track(ctx: Context, track: dict, ti: int, where: str, base: tuple) -> dict[str, Any]:
    section = track.get("section") if isinstance(track.get("section"), dict) else {}
    sbase = base + ("section",)
    fields = {
        "section.height": pick(ctx, [(section, where, sbase)], "height", "TruckTrackSection"),
        "section.segmentLength": pick(ctx, [(section, where, sbase)], "segmentLength", "TruckTrackSection"),
        "section.tpl": pick(ctx, [(section, where, sbase)], "tpl", "TruckTrackSection"),
        "trackTensionDefault": pick(ctx, [(track, where, base)], "trackTensionDefault", "TruckTrack"),
        "trackTensionDrive": pick(ctx, [(track, where, base)], "trackTensionDrive", "TruckTrack"),
    }
    tracker = track.get("parentTracker")
    if isinstance(tracker, dict):
        fields["parentTracker"] = V(tracker.get("locator"), "explicit", f"{where}:{_kp(base + ('parentTracker',))}")
    else:
        fields["parentTracker"] = V(None, "engine-default", EV_PARENT_TRACKER)
    height = _num(fields["section.height"]["value"])
    fields["tracked"] = V(height is not None and height != 0, "derived", f"section.height; {EV_TRACKED}")
    real = [i for i in track.get("wheelIds") or [] if isinstance(i, int)]
    fake = [i for i in track.get("fakeWheelIds") or [] if isinstance(i, int)]
    fields["realWheels"] = V(len(real), "derived", f"{where}:{_kp(base + ('wheelIds',))}")
    fields["fakeWheels"] = V(len(fake), "derived", f"{where}:{_kp(base + ('fakeWheelIds',))}")
    fields["physicsWheels"] = V(len(real) + len(fake), "derived",
                                f"wheelIds + fakeWheelIds: fake wheels are full physics wheels ({RESEARCH} T1)")
    fields["visualWheels"] = V(len(track.get("visualWheelSlots") or []), "derived",
                               f"{where}:{_kp(base + ('visualWheelSlots',))} (no rigid body)")
    return _entity(f"track[{ti}]", "track", "track", fields, wheelIds=real, fakeWheelIds=fake)


def _truck_fields(ctx: Context, layers: list[tuple[Any, str]]) -> dict[str, Any]:
    rb = ("properties", "prop_truck_rb")
    fields: dict[str, Any] = {}
    for key in TRUCK_FIELDS:
        fields[key] = pick(ctx, _cands(layers, rb), key, "prop_truck_rb")
    for key in ENGINE_PARAMS:
        fields[f"engine.{key}"] = pick(ctx, _cands(layers, rb + ("engine", "params")), key, "TruckEngineParams")
    gb = rb + ("gearbox", "params")
    for key in GEARBOX_PARAMS:
        fields[f"gearbox.{key}"] = pick(ctx, _cands(layers, gb), key, "TruckGearboxParams")
    gears, where, path = _first(layers, gb + ("gears",))
    gears = gears if isinstance(gears, list) else []
    fields["gearbox.gears"] = V(len(gears), "derived", f"{where}:{_kp(path)}" if where else "no gears")
    for gi in (0, len(gears) - 1) if gears else ():
        label = "first" if gi == 0 else "top"
        fields[f"gearbox.{label}Gear.angularVelocity"] = pick(
            ctx, [(gears[gi], where or "", path + (gi,))], "angularVelocity", "TruckSingleGearParams")
        fields[f"gearbox.{label}Gear.gearRatio"] = pick(
            ctx, [(gears[gi], where or "", path + (gi,))], "gearRatio", "TruckSingleGearParams")
    for gear in ("lowRangeGear", "reverseGear"):
        sub, w, p = _first(layers, gb + (gear,))
        fields[f"gearbox.{gear}.angularVelocity"] = pick(ctx, [(sub, w or "", p)], "angularVelocity",
                                                         "TruckSingleGearParams") if isinstance(sub, dict) else \
            V(None, "absent", f"no {gear}")
    low, w, p = _first(layers, gb + ("lowRangeMultiplier",))
    if w is not None:
        fields["gearbox.lowRangeMultiplier"] = V(low, "explicit", f"{w}:{_kp(p)}", note=EV_LOWRANGE)
    tc = rb + ("trackControls",)
    for key in TRACK_CTRL_SPLINES:
        fields[f"trackControls.{key}"] = pick(ctx, _cands(layers, tc), key,
                                              engine=None) if _first(layers, tc + (key,))[1] else \
            V(None, "engine-default", EV_TRACK_CTRL)
    fields["trackControls.hasNeutralSteering"] = pick(ctx, _cands(layers, tc), "hasNeutralSteering",
                                                      "TruckTrackControls")
    soft = rb + ("softContactSettings",)
    for key in ("maxPenetrationDepth", "forceScale", "forceScaleStatic"):
        fields[f"softContactSettings.{key}"] = pick(ctx, _cands(layers, soft), key, "physTRUCK_SOFT_CONTACT_DESC")
    for key in ("slopeAngleFrictionMult", "wheelsSubstanceResistanceMult"):
        fields[key] = pick(ctx, _cands(layers, rb), key, label=key)
    fields["physics.stepHz"] = V(60, "engine-default", EV_SOLVER)
    fields["physics.solverIterations"] = V(4, "engine-default", EV_SOLVER)
    return fields


def build_truck(ctx: Context, stores: list[Store], store: Store, name: str) -> dict[str, Any]:
    layers = class_layers(ctx, stores, store, name)
    if not layers:
        raise PhysicsReportError(f"cannot parse {store.display(name)}")
    own_where = layers[0][1]
    rb_path = ("properties", "prop_truck_rb")
    rb_layers = [(_dig(doc, rb_path), where) for doc, where in layers]
    rb_layers = [(d if isinstance(d, dict) else {}, w) for d, w in rb_layers]
    tpl, _, _ = _first(layers, ("properties", "geom", "nameTpl"))
    slots, slots_where, slots_path = _first(layers, rb_path + ("wheelSlotWithDescs",))
    slots = [s if isinstance(s, dict) else {} for s in (slots or [])]
    pool, _, _ = _first(layers, rb_path + ("wheelPool",))
    pool = pool if isinstance(pool, dict) else {}
    tracks_doc, tracks_where, tracks_path = _first(layers, ("properties", "prop_truck_track", "tracks"))
    tracks_doc = [t if isinstance(t, dict) else {} for t in (tracks_doc or [])]
    kind = "tracked" if tracks_doc else "wheeled"

    entities: list[dict[str, Any]] = [_entity("truck", "truck", "truck", _truck_fields(ctx, layers))]
    infos, markup_where = _markup(ctx, stores, tpl)
    bodies = _bodies(ctx, infos, markup_where)
    tracks = [_track(ctx, t, i, tracks_where or own_where, tracks_path + (i,)) for i, t in enumerate(tracks_doc)]
    membership: dict[int, tuple[int, str]] = {}
    for t in tracks:
        ti = int(t["id"][6:-1])
        for i in t["wheelIds"]:
            membership.setdefault(i, (ti, "real"))
        for i in t["fakeWheelIds"]:
            membership.setdefault(i, (ti, "fake"))

    need_parents = bool(bodies) or any(not s.get("parentFrame") for s in slots)   # bodies: their cdt_ shapes
    anchor = next((s.get("geomName") for s in slots if s.get("geomName")), None)
    nodes, tpl_where = _load_nodes(ctx, stores, tpl, anchor, need_parents, {b["id"] for b in bodies})

    # wheel classes used by slots
    classes: dict[str, dict[str, Any]] = {}
    for slot in slots:
        key = slot.get("editableWheel")
        if isinstance(key, str) and key not in classes:
            entry = pool.get(key)
            cls_name = entry.get("__value") if isinstance(entry, dict) else entry
            classes[key] = _wheel_class(ctx, stores, key, cls_name if isinstance(cls_name, str) else None)

    # roles of classes (tracked: contact = used by any fake slot; idler/drive = only real track slots)
    class_role: dict[str, str] = {}
    for key in classes:
        used = [membership.get(i, (None, "none"))[1] for i, s in enumerate(slots) if s.get("editableWheel") == key]
        if kind == "wheeled":
            class_role[key] = "wheel"
        elif "fake" in used:
            class_role[key] = "contact wheel"
        elif "real" in used:
            class_role[key] = "idler/drive wheel"
        else:
            class_role[key] = "untracked wheel"
        classes[key]["role"] = class_role[key]

    body_by_name = {b["id"]: b for b in bodies}
    axles: dict[str, dict[str, Any]] = {}
    axle_roles: dict[str, list[str]] = {}
    slot_entities = []
    for si, slot in enumerate(slots):
        where = f"{slots_where}:{_kp(slots_path + (si,))}" if slots_where else own_where
        sbase = slots_path + (si,)
        sc = [(slot, slots_where or own_where, sbase)]
        key = slot.get("editableWheel")
        wclass = classes.get(key) if isinstance(key, str) else None
        fields: dict[str, Any] = {
            "slot.geomName": V(slot.get("geomName"), "explicit" if slot.get("geomName") else "absent", where),
            "slot.class": V(_dig(wclass, ("fields", "class", "value")) if wclass else None,
                            "explicit" if wclass else "absent", f"{where}.editableWheel"),
        }
        for k in ("isRightSided", "isRear", "torqueType", "handbrakeStrength", "isConnectedToHandbrake",
                  "extraPhysicalRadius", "radiusOverride"):
            fields[f"slot.{k}"] = pick(ctx, sc, k, "TruckWheelSlotWithDesc")
        ti, member = membership.get(si, (None, "none"))
        fields["slot.track"] = V(None if ti is None else f"track[{ti}].{member}", "derived",
                                 "prop_truck_track.tracks[].wheelIds / fakeWheelIds")
        # parent body
        if slot.get("parentFrame"):
            fields["slot.parentBody"] = V(slot["parentFrame"], "explicit", f"{where}.parentFrame")
        else:
            body = None
            geom = slot.get("geomName")
            if nodes is not None and nodes.parents is not None and geom in nodes.index:
                body = next((a for a in _ancestors(nodes, geom) if a in body_by_name), None)
            fields["slot.parentBody"] = V(body, "inherited" if body else "absent",
                                          f"{tpl_where}: nearest body above {geom} in the node tree" if body else
                                          "parentFrame empty and the model node tree did not resolve")
        # axle
        axle_id, axle_ref, axle_ev = _slot_axle(ctx, rb_layers, slot, si, where)
        fields["slot.axle"] = V(axle_id, "explicit" if axle_id.startswith("axle[") else "engine-default", axle_ev)
        if axle_id not in axles:
            cont = axle_ref["container"] if isinstance(axle_ref["container"], dict) else {}
            afields = {}
            for k in AXLE_FIELDS:
                afields[k] = pick(ctx, [(cont, axle_ref["where"], axle_ref["path"])], k,
                                  "physTRUCK_SUSPENSION_AXLE_DESC")
                if k.startswith("fake"):
                    afields[k]["note"] = EV_FAKE
            lo, hi = _num(afields["min"]["value"]), _num(afields["max"]["value"])
            afields["travelRange"] = V(None if lo is None or hi is None else hi - lo, "derived", EV_TRAVEL)
            if axle_id.startswith("axle["):
                cmap, _, _ = _first(rb_layers, ("suspensionCollectionMap",))
                idx = int(axle_id[5:].split("]")[0])
                names = sorted(k for k, v in (cmap or {}).items()
                               if (v.get("__value") if isinstance(v, dict) else v) == idx) if isinstance(cmap, dict) else []
                afields["name"] = V(names[0] if names else None, "explicit" if names else "absent",
                                    "prop_truck_rb.suspensionCollectionMap")
            axles[axle_id] = _entity(axle_id, "axle", "", afields)
        role = class_role.get(key, "wheel" if kind == "wheeled" else "untracked wheel")
        axle_roles.setdefault(axle_id, []).append(
            "wheel" if kind == "wheeled" else {"real": "idler/drive wheel", "fake": "contact wheel"}.get(member, "untracked wheel"))
        # radius and mass
        wf = wclass["fields"] if wclass and wclass.get("physics") else None
        if wf:
            radius = _num(wf["radius"]["value"])
            offset = _num(wf["radiusOffset"]["value"]) or 0.0
            extra = _num(fields["slot.extraPhysicalRadius"]["value"]) or 0.0
            height = _num(tracks[ti]["fields"]["section.height"]["value"]) if ti is not None else 0.0
            fields["slot.physicalRadius"] = V(None if radius is None else radius - offset + (height or 0.0) + extra,
                                              "derived", EV_RADIUS)
            mass = _num(wf["mass"]["value"])
            mult = _num(wf["rearMassMultiplier"]["value"]) if fields["slot.isRear"]["value"] else 1.0
            eff = None if mass is None else max(mass, 0.1) * (mult if mult is not None else 1.0)
            fields["slot.effectiveMass"] = V(eff, "derived", EV_WHEEL_MASS)
            parent = body_by_name.get(fields["slot.parentBody"]["value"])
            pmass = _num(parent["fields"]["effectiveMass"]["value"]) if parent else None
            fields["slot.parentBodyMass"] = V(pmass, "derived", "effectiveMass of slot.parentBody" if parent else
                                              "parent body unknown or not a markup body")
            fields["slot.massRatio"] = V(None if eff is None or not pmass else eff / pmass, "derived",
                                         "slot.effectiveMass / slot.parentBodyMass")
        slot_entities.append(_entity(f"slot[{si}]", "wheel", role, fields, physics=bool(wf)))

    for aid, roles in axle_roles.items():
        # by track membership: wheelIds (belt-outline rollers) vs fakeWheelIds (ground support)
        top = max(sorted(set(roles)), key=roles.count)
        axles[aid]["role"] = f"axle: {top}"
        axles[aid]["usedBy"] = sorted(set(roles))

    # body roles
    roots = [b for b in bodies if b.get("root")]
    hull = max(roots, key=lambda b: _num(b["fields"]["effectiveMass"]["value"]) or 0.0, default=None)
    if hull is not None:
        hull["role"] = "hull"
    track_parents = {s["fields"]["slot.parentBody"]["value"] for s in slot_entities
                     if s["fields"]["slot.track"]["value"]}
    for b in bodies:
        if b is not hull and b["id"] in track_parents:
            b["role"] = "track frame"

    for b in bodies:
        if b["role"] == "body":
            carries = any(s["fields"]["slot.parentBody"]["value"] == b["id"] for s in slot_entities)
            b["inertiaRole"] = "wheel carrier" if carries else ("jointed body" if not b.get("root") else "other root")
        else:
            b["inertiaRole"] = b["role"]
    body_inertia(bodies, slot_entities, nodes, tpl_where)
    groups, group_names = _markup_groups(ctx, stores, tpl)
    joint_sweeps(bodies, slot_entities, classes, nodes, tpl_where, infos, groups, group_names)
    derived = _derived(bodies, slot_entities, tracks, nodes, tpl_where)
    entities += bodies + tracks + [axles[k] for k in sorted(axles)] + \
        [classes[k] for k in sorted(classes)] + slot_entities + [derived]
    return {"class": store.display(name), "tpl": tpl, "kind": kind, "model": tpl_where, "markup": markup_where,
            "nodeNotes": list(nodes.notes) if nodes is not None else ["no compiled model node table"],
            "entities": entities}


def _ancestors(nodes: TplNodes, name: str) -> Iterable[str]:
    index, seen = nodes.index.get(name), set()
    while index is not None and nodes.parents and 0 <= index < len(nodes.parents) and index not in seen:
        seen.add(index)
        parent = nodes.parents[index]
        if parent < 0:
            return
        yield nodes.name_of(parent)
        index = parent


INERTIA_AXES = ("x", "y", "z")
EV_INERTIA = ("solid boxes of each cdt_ mesh's oriented bounds (.tpl bounds table, tpl_reader.find_bounds), the "
              "body mass shared by volume, parallel-axis about the shapes' centroid, in the body bone's axes; the "
              "engine derives inertia from the collision shapes x mass, not from mass alone "
              f"({RESEARCH} Q2; library/suspension-and-wheels.md 'First working series spring')")
NOTE_INERTIA = ("boxes over-fill convex hulls, so this is an upper estimate of the shapes' own inertia; Havok's "
                "optimizeInertiasOfConstraintTree may raise light chained bodies further")
EV_INERTIA_COM = ("the same tensor moved to the centre of mass (centroid + hkCenterOfMassOffset, or bone + "
                  "boneCenterOfMassOffset when havokMassCenter is False) by the parallel-axis theorem")
NOTE_INERTIA_COM = ("not what the engine uses (Inferred): Havok keeps the shapes' tensor when only the centre of "
                    "mass moves, and the Mammoth RC68 carrier (0.3 m cube, COM offset 2.05 m) behaved like its "
                    "135 kg*m^2 centroidal value, not like this one (Game)")
EV_WHEEL_INERTIA = "sum over the wheel slots whose parentBody is this body of 0.5 x effectiveMass x physicalRadius^2"


def _vec(v: Any) -> tuple[float, float, float] | None:
    if isinstance(v, (list, tuple)) and len(v) == 3 and all(_num(x) is not None for x in v):
        return (float(v[0]), float(v[1]), float(v[2]))
    return None


def _explicit_inertia(phys: dict, where: str, base: tuple) -> dict[str, Any] | None:
    """An inertia key in the markup body (no retail markup has one; physics_semantics.md Q2 finds no inertia
    override field): ``{"value": [x, y, z], "evidence": ...}``."""
    for key, value in phys.items():
        if "inertia" in str(key).lower():
            vec = _vec(value)
            if vec is None and _num(value) is not None:
                vec = (float(value),) * 3
            if vec is not None:
                return {"value": list(vec), "evidence": f"{where}:{_kp(base + (key,))}"}
    return None


def _mat_dir(m: tuple[float, ...], v: tuple[float, ...]) -> tuple[float, float, float]:
    return (v[0] * m[0] + v[1] * m[4] + v[2] * m[8], v[0] * m[1] + v[1] * m[5] + v[2] * m[9],
            v[0] * m[2] + v[1] * m[6] + v[2] * m[10])


def _mat_point(m: tuple[float, ...], p: tuple[float, ...]) -> tuple[float, float, float]:
    d = _mat_dir(m, p)
    return (d[0] + m[12], d[1] + m[13], d[2] + m[14])


def _unit(v: tuple[float, ...]) -> tuple[tuple[float, float, float], float]:
    n = sum(c * c for c in v) ** 0.5
    return ((v[0] / n, v[1] / n, v[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)), n


def body_shapes(nodes: TplNodes, body: str, bodies: set[str]) -> list[dict[str, Any]]:
    """The cdt_ meshes of ``body`` (the body node itself and the nodes whose nearest body above is ``body``),
    as model-space boxes: ``center``, unit ``axes``, edge ``size``, ``volume`` and the mesh ``node``."""
    out = []
    if not nodes.bounds:
        return out
    names = {index: name for name, index in nodes.index.items()}
    for index, box in sorted(nodes.bounds.items()):
        name = names.get(index)
        if name is None or not name.lower().startswith("cdt"):
            continue
        owner = name if name in bodies else next((a for a in _ancestors(nodes, name) if a in bodies), None)
        if owner != body or index >= len(nodes.matrices):
            continue
        m = nodes.matrices[index]
        axes, size = [], []
        for a in range(3):
            unit, scale = _unit(_mat_dir(m, box.axes[a]))
            axes.append(unit)
            size.append(box.size[a] * scale)
        out.append({"node": name, "center": _mat_point(m, box.center()), "axes": axes, "size": size,
                    "volume": max(size[0], 0.01) * max(size[1], 0.01) * max(size[2], 0.01)})
    return out


def shapes_inertia(shapes: list[dict[str, Any]], mass: float
                   ) -> tuple[tuple[float, float, float], list[list[float]]]:
    """(centroid, 3x3 inertia tensor about it) of solid boxes sharing ``mass`` by volume, model axes."""
    total = sum(s["volume"] for s in shapes)
    c = tuple(sum(s["volume"] * s["center"][i] for s in shapes) / total for i in range(3))
    tensor = [[0.0] * 3 for _ in range(3)]
    for s in shapes:
        mi = mass * s["volume"] / total
        a, b, d = s["size"]
        principal = (mi * (b * b + d * d) / 12, mi * (a * a + d * d) / 12, mi * (a * a + b * b) / 12)
        r = [s["center"][i] - c[i] for i in range(3)]
        r2 = sum(x * x for x in r)
        for i in range(3):
            for j in range(3):
                tensor[i][j] += sum(principal[k] * s["axes"][k][i] * s["axes"][k][j] for k in range(3))
                tensor[i][j] += mi * ((r2 if i == j else 0.0) - r[i] * r[j])
    return c, tensor  # type: ignore[return-value]


def _about(tensor: list[list[float]], axis: tuple[float, float, float]) -> float:
    return sum(axis[i] * tensor[i][j] * axis[j] for i in range(3) for j in range(3))


def body_inertia(bodies: list[dict], slots: list[dict], nodes: TplNodes | None, tpl_where: str | None) -> None:
    """Add the inertia fields to every body entity (library/physics-report.md 'Body inertia')."""
    names = {b["id"] for b in bodies}
    model = tpl_where or "no compiled model (.tpl)"
    for b in bodies:
        f = b["fields"]
        mass = _num(f["effectiveMass"]["value"])
        carried = [s for s in slots if s.get("physics") and s["fields"]["slot.parentBody"]["value"] == b["id"]]
        explicit = b.pop("explicitInertia", None)
        shapes: list[dict[str, Any]] = []
        why = None
        if nodes is None:
            why = "no compiled model (.tpl) found"
        elif not nodes.bounds:
            why = f"{model}: per-mesh bounds table not found"
        elif b["id"] not in nodes.index:
            why = f"{model}: no node named {b['id']}"
        elif nodes.parents is None:
            why = f"{model}: node tree (parent array) not resolved"
        else:
            shapes = body_shapes(nodes, b["id"], names)
            if not shapes:
                why = f"{model}: no cdt_ mesh under {b['id']}"
        f["inertia.shapes"] = V(len(shapes), "derived", f"{model}: cdt_ meshes whose nearest body is {b['id']}"
                                if not why else why)
        per_mass: dict[str, float] = {}
        if shapes:
            bm = nodes.matrix(b["id"])
            axes = [_unit(_mat_dir(bm, e))[0] for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
            centroid, unit_tensor = shapes_inertia(shapes, 1.0)
            corners = []
            for s in shapes:
                for sx in (-0.5, 0.5):
                    for sy in (-0.5, 0.5):
                        for sz in (-0.5, 0.5):
                            p = [s["center"][i] + sum(s["axes"][k][i] * s["size"][k] * h
                                                      for k, h in enumerate((sx, sy, sz))) for i in range(3)]
                            corners.append([sum(p[i] * ax[i] for i in range(3)) for ax in axes])
            extent = [max(c[a] for c in corners) - min(c[a] for c in corners) for a in range(3)]
            length = max(extent)
            com = list(centroid)
            offset = _vec(f["hkCenterOfMassOffset"]["value"]) or (0.0, 0.0, 0.0)
            bone_offset = _vec(f["boneCenterOfMassOffset"]["value"]) or (0.0, 0.0, 0.0)
            if f["havokMassCenter"]["value"] is False:
                origin = (bm[12], bm[13], bm[14])
                com = [origin[i] + sum(bone_offset[k] * axes[k][i] for k in range(3)) for i in range(3)]
            else:
                com = [centroid[i] + sum(offset[k] * axes[k][i] for k in range(3)) for i in range(3)]
            delta = [com[i] - centroid[i] for i in range(3)]
            d2 = sum(x * x for x in delta)
            f["inertia.shapeVolume"] = V(sum(s["volume"] for s in shapes), "derived",
                                         f"{model}: sum of the cdt_ oriented-box volumes")
            for a, ax in zip(INERTIA_AXES, axes):
                per_mass[a] = _about(unit_tensor, ax)
                f[f"inertia.extent.{a}"] = V(extent[INERTIA_AXES.index(a)], "derived",
                                             f"{model}: extent of the cdt_ boxes along the body's {a} axis")
            f["inertia.extent"] = V(length, "derived", f"{model}: largest extent L of the cdt_ boxes")
            for a, ax in zip(INERTIA_AXES, axes):
                k2 = per_mass[a]
                f[f"inertia.{a}"] = V(None if mass is None else mass * k2, "derived", EV_INERTIA,
                                      note=NOTE_INERTIA if mass is not None else
                                      "massFromDensity: no mass here; inertiaPerMass still holds")
                f[f"inertiaPerMass.{a}"] = V(k2, "derived", "inertia / mass (radius of gyration squared, m^2)")
                f[f"inertiaRatio.{a}"] = V(k2 / (length * length) if length > 0 else None, "derived",
                                           "inertia / (mass x inertia.extent^2), dimensionless")
                shifted = k2 + d2 - sum(delta[i] * ax[i] for i in range(3)) ** 2
                f[f"inertiaAboutCom.{a}"] = V(None if mass is None else mass * shifted, "derived", EV_INERTIA_COM,
                                              note=NOTE_INERTIA_COM)
            f["inertia.comFromCentroid"] = V(d2 ** 0.5, "derived", "distance from the cdt_ centroid to the centre "
                                             "of mass (hkCenterOfMassOffset / boneCenterOfMassOffset)")
        if explicit is not None:
            for a, value in zip(INERTIA_AXES, explicit["value"]):
                f[f"inertia.{a}"] = V(value, "explicit", explicit["evidence"])
                if mass:
                    per_mass[a] = value / mass
                    f[f"inertiaPerMass.{a}"] = V(value / mass, "derived", "explicit inertia / mass")
        if per_mass:
            f["inertiaPerMass.min"] = V(min(per_mass.values()), "derived", "smallest of inertiaPerMass.x/y/z")
            f["inertiaPerMass.mid"] = V(sorted(per_mass.values())[1], "derived",
                                        "middle of inertiaPerMass.x/y/z (at least two axes are this soft)")
        if carried:
            wm = [_num(s["fields"].get("slot.effectiveMass", {}).get("value")) for s in carried]
            wr = [_num(s["fields"].get("slot.physicalRadius", {}).get("value")) for s in carried]
            wheel_i = sum(0.5 * m * r * r for m, r in zip(wm, wr) if m is not None and r is not None)
            f["wheels.count"] = V(len(carried), "derived", "physics wheel slots whose parentBody is this body")
            f["wheels.mass"] = V(sum(m for m in wm if m is not None), "derived", "sum of their effectiveMass")
            f["wheels.radius"] = V(max((r for r in wr if r is not None), default=None), "derived",
                                   "largest physicalRadius of those wheels")
            f["wheels.inertia"] = V(wheel_i or None, "derived", EV_WHEEL_INERTIA)
            if per_mass and mass is not None and wheel_i:
                f["inertiaToWheelInertia"] = V(mass * sorted(per_mass.values())[1] / wheel_i, "derived",
                                               "middle body inertia (of x/y/z) / wheels.inertia")


EV_SWEEP = ("cdt_ oriented boxes (.tpl bounds table) and wheel cylinders (physicalRadius, class width, axle along "
            "the wheel node's X) of the child body, the bodies jointed below it and their wheels, swept along the "
            "joint (prismatic: childRotation's Z in the child bone frame, + as the constraint position; hinge: "
            "about that axis through childTranslation, + right-handed) against every shape the engine does not "
            f"filter from them ({RESEARCH} 'Jointed-body collision filtering'); pairs touching at rest are left out")


def joint_sweeps(bodies: list[dict], slots: list[dict], classes: dict[str, dict], nodes: TplNodes | None,
                 tpl_where: str | None, infos: list[Any], groups: list[list[str]],
                 group_names: list[str] | None = None) -> None:
    """Add the ``sweep.*`` fields to every prismatic / hinge child body (library/physics-report.md 'Joint
    sweep'): the first contact going towards each limit, with the hit pair."""
    joints = [b for b in bodies if b["fields"].get("joint.type", {}).get("value") in ("prismatic", "hinge")]
    if not joints:
        return
    model = tpl_where or "no compiled model (.tpl)"
    why = None
    if nodes is None:
        why = "no compiled model (.tpl) found"
    elif not nodes.bounds:
        why = f"{model}: per-mesh bounds table not found"
    elif nodes.parents is None:
        why = f"{model}: node tree (parent array) not resolved"
    if why:
        for b in joints:
            b["fields"]["sweep.status"] = V("not checked", "derived", why)
        return
    names = {b["id"] for b in bodies}
    layers = {b["id"]: b["fields"].get("collisionLayer", {}).get("value") for b in bodies}

    def parent_of(node: str) -> str | None:
        if node not in nodes.index:
            return None
        return next((a for a in _ancestors(nodes, node) if a in names), None)

    constraints, total = joint_sweep.constraint_list(infos, names, parent_of)
    shapes = {b: [joint_sweep.box_shape(s["node"], b, s["center"], s["axes"], s["size"])
                  for s in body_shapes(nodes, b, names)] for b in sorted(names) if b in nodes.index}
    wheels, wheel_body = [], {}
    for s in slots:
        f = s["fields"]
        geom, carrier = f["slot.geomName"]["value"], f["slot.parentBody"]["value"]
        radius = _num(f.get("slot.physicalRadius", {}).get("value"))
        wclass = next((c for c in classes.values() if c["fields"].get("class", {}).get("value") ==
                       f["slot.class"]["value"]), None)
        width = _num(wclass["fields"].get("width", {}).get("value")) if wclass and wclass.get("physics") else None
        if not s.get("physics") or geom not in nodes.index or carrier not in names or not radius or not width:
            continue
        m = nodes.matrix(geom)
        wid = f"{s['id']} ({geom})"
        # axle along the truck's X, not the node's: retail wheel nodes often point X forward (Mammoth RC76 duals)
        wheels.append(joint_sweep.cylinder_shape(wid, wid, (m[12], m[13], m[14]), (1.0, 0.0, 0.0), radius, width))
        wheel_body[wid] = carrier
    results = joint_sweep.sweep_truck(constraints, total, groups, layers, shapes, wheels, wheel_body, nodes.matrix,
                                      group_names)
    capped = total >= joint_sweep.CONSTRAINT_CAP
    for b in joints:
        f = b["fields"]
        res = results.get(b["id"])
        if res is None:
            f["sweep.status"] = V("not checked", "derived", "not a constraint child in the markup's constraint list")
            continue
        if res.get("skipped"):
            f["sweep.status"] = V("not checked", "derived", res["skipped"])
            continue
        unit = "m" if res["kind"] == "prismatic" else "deg"
        findings = {x["side"]: x["severity"] for x in joint_sweep.judge(res)}
        status = "contact within travel" if "warning" in findings.values() else             "contact near limit" if "info" in findings.values() else "clear"
        f["sweep.status"] = V(status, "derived", EV_SWEEP,
                              note=f"{total} constraints: no sub-id filtering (>= 31)" if capped else None)
        f["sweep.parent"] = V(res["parent"], "derived", "constraint parent (target, or nearest body above)")
        f["sweep.movingWheels"] = V(res["wheels"], "derived", "wheels carried by the swept bodies (RC082 judges "
                                    "only joints that carry wheels)")
        if res["posedSkipped"]:
            f["sweep.posedPartsSkipped"] = V(res["posedSkipped"], "derived", "bodies under a position-motor joint "
                                             "that carries no wheels (crane, boom, grapple): left out of a "
                                             "wheel-carrying joint's sweep, their pose varies in play")
        f["sweep.pairs"] = V(res["pairs"], "derived", "shape pairs that may collide, not touching at rest")
        rest = res["restOverlaps"]
        f["sweep.restOverlaps"] = V(len(rest), "derived", "unfiltered shape pairs already touching at rest "
                                    "(left out of the sweep)",
                                    note="; ".join(f"{joint_sweep.describe(a)} x {joint_sweep.describe(c)}"
                                                   for a, c in rest[:3]) or None)
        if unit == "deg":
            f["sweep.nearLimitMargin"] = V(res["margin"], "derived", "degrees that move the farthest moving "
                                           f"shape {joint_sweep.NEAR_LIMIT} m")
        for side in ("low", "high"):
            r = res.get(side)
            if not r:
                continue
            f[f"sweep.{side}.limit"] = V(r["limit"], "derived", f"joint limit ({unit})")
            contact = r["contact"]
            f[f"sweep.{side}.firstContact"] = V(contact, "derived", f"first contact position ({unit}); none up to "
                                                f"{r['sweptTo']:.3g}" if contact is None else
                                                f"first contact position ({unit}), swept to {r['sweptTo']:.3g}")
            if contact is not None:
                f[f"sweep.{side}.clearance"] = V(abs(contact) - abs(r["limit"]), "derived",
                                                 f"|firstContact| - |limit| ({unit}); < 0: contact within travel")
                f[f"sweep.{side}.pair"] = V(f"{joint_sweep.describe(r['moving'])} x "
                                            f"{joint_sweep.describe(r['static'])}", "derived",
                                            "moving shape x the shape it hits")


def _derived(bodies: list[dict], slots: list[dict], tracks: list[dict], nodes: TplNodes | None,
             tpl_where: str | None) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    known = [(b, _num(b["fields"]["effectiveMass"]["value"])) for b in bodies]
    body_mass = sum(m for _, m in known if m is not None)
    unknown = [b["id"] for b, m in known if m is None]
    wheels = [(s, _num(s["fields"].get("slot.effectiveMass", {}).get("value"))) for s in slots if s.get("physics")]
    wheel_mass = sum(m for _, m in wheels if m is not None)
    note = f"lower bound: massFromDensity bodies {unknown} not counted" if unknown else None
    fields["bodyMass"] = V(body_mass, "derived", "sum of body effectiveMass", note=note)
    fields["wheelMass"] = V(wheel_mass, "derived", "sum of physics wheel slot effectiveMass")
    fields["totalMass"] = V(body_mass + wheel_mass, "derived", "bodyMass + wheelMass", note=note)
    fields["wheelShareOfTotal"] = V(wheel_mass / (body_mass + wheel_mass) if body_mass + wheel_mass else None,
                                    "derived", "wheelMass / totalMass")
    fields["physicsWheels"] = V(len(wheels), "derived", "slots whose class has prop_truck_wheel")
    for b in bodies:
        if b["role"] == "track frame":
            m = _num(b["fields"]["effectiveMass"]["value"])
            fields[f"frameShare.{b['id']}"] = V(m / body_mass if m and body_mass else None, "derived",
                                                "track frame effectiveMass / bodyMass (tracks.py RC047)")
    for t in tracks:
        fields[f"{t['id']}.physicsWheels"] = t["fields"]["physicsWheels"]
    # COM proxy and track width
    com = width = ground = None
    if nodes is not None:
        num = den = 0.0
        for b, m in known:
            if m and b["id"] in nodes.index:
                y = nodes.position(b["id"])[1]
                off = b["fields"]["boneCenterOfMassOffset"]["value"]
                if b["fields"]["havokMassCenter"]["value"] is False and isinstance(off, list) and len(off) == 3 \
                        and all(_num(v) is not None for v in off):
                    y += float(off[1])
                num, den = num + m * y, den + m
        lefts, rights, bottoms = [], [], []
        for s, m in wheels:
            name = s["fields"]["slot.geomName"]["value"]
            if name not in nodes.index:
                continue
            x, y, _ = nodes.position(name)
            if m:
                num, den = num + m * y, den + m
            r = _num(s["fields"].get("slot.physicalRadius", {}).get("value"))
            if r is not None:
                bottoms.append(y - r)
            (rights if s["fields"]["slot.isRightSided"]["value"] else lefts).append(x)
        if den and bottoms:
            ground = min(bottoms)
            com = num / den - ground
        if lefts and rights:
            width = abs(sum(lefts) / len(lefts) - sum(rights) / len(rights))
    model = tpl_where or "no compiled model (.tpl) found"
    fields["boneOriginHeight"] = V(com, "derived", f"{model}: {EV_COM}; above the lowest wheel bottom", note=note)
    fields["trackWidth"] = V(width, "derived", f"{model}: mean X of left minus right physics wheel nodes")
    fields["boneOriginHeightToTrackWidth"] = V(com / width if com is not None and width else None, "derived",
                                               "boneOriginHeight / trackWidth (a proxy, not a COM ratio)")
    return _entity("derived", "derived", "derived", fields)


def report(target: str | Path, *, game_root: str | Path | None = None, ctx: Context | None = None,
           truck: str | None = None) -> dict[str, Any]:
    """Effective physics values of every truck class in a ``.pak`` or source tree."""
    ctx = ctx or Context(game_root)
    store = open_store(target)
    stores = ctx.stores(store)
    names = [n for n in truck_classes(ctx, store) if not truck or truck.lower() in n.lower()]
    trucks = [build_truck(ctx, stores, store, n) for n in names]
    return {"target": str(target), "label": store.label, "kind": store.kind, "sha256": store.sha256,
            "gameRoot": str(ctx.game_root) if ctx.game_root else None,
            "schema": "SDK" if ctx.schema() is not None else "built-in copy",
            "trucks": trucks, "limits": LIMITS}


LIMITS = [
    "Static sag and spring rate are not computed: the T4 sag law is withdrawn (physics_semantics.md F3).",
    "massFromDensity bodies have no mass here: 600 kg/m^3 x the cdt_ convex volume; the .tpl bounds give boxes, "
    "which over-fill it.",
    "Body inertia is a solid-box estimate from the .tpl mesh bounds (an upper bound on the shapes' own inertia), "
    "about the shapes' centroid: hkCenterOfMassOffset moves the centre of mass, not the tensor (Inferred).",
    "boneOriginHeight is a mass-weighted height of bone origins, not the centre of mass (hull centroids are not "
    "decoded); compare it only between models built the same way.",
    "Soft-contact force law and sideways friction law are not decompiled; values are reported, not interpreted.",
    "The prop_truck_friction_updater.prop base table (default 2.2, asphalt 3) is not merged: the research reads "
    "a missing 'default' entry as bodyFriction 2.0 (Q4).",
    "Physics step and solver iterations are editor.cfg values; the retail game.cfg is unverified (Q7).",
    "Only compiled .cls/.tpl_markup/.tpl are read; a source tree without generated classes reports no trucks.",
]


# ------------------------------------------------------------------------------------------------ retail

def retail_trucks(ctx: Context) -> dict[str, str]:
    """Retail truck name -> class member path."""
    store = ctx.retail()
    if store is None:
        return {}
    if ctx.retail_names is None:
        out = {}
        prefix = RETAIL_TRUCKS.split("*", 1)[0]
        for lower in store.names():
            if lower.startswith(prefix) and lower.endswith(".cls") and fnmatch.fnmatchcase(lower, RETAIL_TRUCKS):
                folder, base = lower.split("/")[-2:]
                if folder + ".cls" == base and "preview" not in base:
                    out[folder[len("auto_"):]] = lower
        ctx.retail_names = out
    return ctx.retail_names


def resolve_retail(ctx: Context, name: str) -> str:
    trucks = retail_trucks(ctx)
    if not trucks:
        raise PhysicsReportError("no retail installation found (pass --game-root or set ROADCRAFT_GAME_ROOT)")
    norm = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if norm in trucks:
        return norm
    tokens = [t for t in norm.split("_") if t]
    hits = [t for t in trucks if all(tok in t for tok in tokens)]
    if not hits:
        raise PhysicsReportError(f"no retail truck matches {name!r}")
    hits.sort(key=lambda t: (t.startswith("base_"), not t.endswith("_new"), len(t), t))
    return hits[0]


def retail_report(ctx: Context, truck: str) -> dict[str, Any]:
    if truck not in ctx.retail_cache:
        member = retail_trucks(ctx)[truck]
        store = ctx.retail()
        ctx.retail_cache[truck] = build_truck(ctx, [store], store, member)
    return ctx.retail_cache[truck]


def role_values(truck: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """(role, field) -> the Values of every entity with that role (physics wheel classes and slots only)."""
    out: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for ent in truck["entities"]:
        role = ent.get("role")
        if role not in ROLE_ORDER:
            continue
        if ent["kind"] in ("wheelClass", "wheel") and not ent.get("physics"):
            continue
        if ent["kind"] == "track" and ent["id"] != "track[0]":
            continue
        for field, value in ent["fields"].items():
            if field.startswith("frameShare.") or field.startswith("track["):
                continue
            out.setdefault((role, field), []).append(value)
    return out


def distribution(ctx: Context, kind: str) -> dict[str, Any]:
    """Per (role, field): every retail value of that role over the retail trucks of one kind."""
    values: dict[tuple[str, str], list[Any]] = {}
    with_role: dict[str, int] = {}
    with_value: dict[tuple[str, str], int] = {}
    trucks = []
    store = ctx.retail()
    for name, member in sorted(retail_trucks(ctx).items()):
        doc = ctx.ps(store, member)
        tracked = bool(_dig(doc, ("properties", "prop_truck_track", "tracks")) not in (_MISSING, None, []))
        if not _is_truck(doc) or ("tracked" if tracked else "wheeled") != kind:
            continue                                   # cheap kind check before building the report
        try:
            rep = retail_report(ctx, name)
        except PhysicsReportError:
            continue
        if rep["kind"] != kind:
            continue
        trucks.append(name)
        rv = role_values(rep)
        for role in {r for r, _ in rv}:
            with_role[role] = with_role.get(role, 0) + 1
        for key, vals in rv.items():
            present = [v["value"] for v in vals if v["source"] != "absent" and v["value"] is not None]
            values.setdefault(key, []).extend(present)
            if present:
                with_value[key] = with_value.get(key, 0) + 1
    return {"kind": kind, "trucks": trucks, "values": values, "withRole": with_role, "withValue": with_value}


INERTIA_SCHEMA = 1
INERTIA_ROLES = ("hull", "wheel carrier", "track frame", "jointed body", "other root")
INERTIA_METRICS = ("inertiaPerMass.mid", "inertiaPerMass.min", "inertiaToWheelInertia")
_INERTIA: dict[str, dict[str, Any]] = {}


def default_cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    return Path(base) / "roadcraft-toolchain" / "retail-cache"


def _retail_key(game_root: Path) -> list[list[Any]]:
    base = game_root / retail_mod.PAK_DIR
    return [[p.relative_to(base).as_posix(), p.stat().st_size, p.stat().st_mtime_ns]
            for p in sorted(base.rglob("*.pak"))]


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    pos = q * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    return {"n": len(values), "min": _clean(min(values)), "p5": _clean(_quantile(values, 0.05)),
            "median": _clean(statistics.median(values)), "max": _clean(max(values))}


def inertia_rows(truck: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """One row per body with an inertia estimate: role, mass, the INERTIA_METRICS."""
    rows = []
    for ent in truck["entities"]:
        if ent["kind"] != "body" or ent["fields"].get("inertiaPerMass.mid") is None:
            continue
        f = ent["fields"]
        row = {"truck": name, "body": ent["id"], "role": ent.get("inertiaRole", ent.get("role")),
               "mass": f["effectiveMass"]["value"], "extent": f.get("inertia.extent", {}).get("value")}
        for metric in INERTIA_METRICS:
            row[metric] = f.get(metric, {}).get("value")
        rows.append(row)
    return rows


def inertia_distribution(ctx: Context, cache_dir: str | Path | None | bool = None) -> dict[str, Any] | None:
    """Per body role, the retail spread of the inertia metrics over every retail truck class (all masses and
    bodies of >= 1 t), with every row.  Cached in-process and, unless ``cache_dir`` is False, as JSON in
    ``cache_dir`` (default :func:`default_cache_dir`), keyed by the retail paks' sizes and times."""
    if ctx.game_root is None:
        return None
    key = _retail_key(ctx.game_root)
    digest = hashlib.sha256(json.dumps([INERTIA_SCHEMA, key]).encode()).hexdigest()[:16]
    if digest in _INERTIA:
        return _INERTIA[digest]
    cache = None
    if cache_dir is not False:
        folder = Path(cache_dir) if cache_dir else default_cache_dir()
        try:
            folder.resolve().relative_to(ctx.game_root.resolve())
            raise PhysicsReportError("the retail inertia cache must not live inside the game folder")
        except ValueError:
            pass
        cache = folder / f"retail-inertia-v{INERTIA_SCHEMA}-{digest}.json"
        if cache.is_file():
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
                if data.get("schemaVersion") == INERTIA_SCHEMA and data.get("key") == key:
                    data["cache"] = {"path": str(cache), "hit": True}
                    _INERTIA[digest] = data
                    return data
            except (OSError, ValueError):
                pass
    rows: list[dict[str, Any]] = []
    trucks = 0
    for name in sorted(retail_trucks(ctx)):
        try:
            rep = retail_report(ctx, name)
        except PhysicsReportError:
            continue
        trucks += 1
        rows += inertia_rows(rep, name)
    roles: dict[str, Any] = {}
    for role in INERTIA_ROLES:
        mine = [r for r in rows if r["role"] == role]
        roles[role] = {}
        for label, sel in (("all", mine), (">=1t", [r for r in mine if (_num(r["mass"]) or 0) >= 1000])):
            roles[role][label] = {m: _stats([r[m] for r in sel if _num(r[m]) is not None]) for m in INERTIA_METRICS}
    data = {"schemaVersion": INERTIA_SCHEMA, "key": key, "trucks": trucks, "roles": roles, "rows": rows}
    if cache is not None:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache.with_name(f".{cache.name}.{os.getpid()}.partial")
            temporary.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
            os.replace(temporary, cache)
            data = dict(data, cache={"path": str(cache), "hit": False})
        except OSError:
            data = dict(data, cache={"path": str(cache), "hit": False, "error": "not written"})
    _INERTIA[digest] = data
    return data


def format_inertia(dist: dict[str, Any]) -> str:
    lines = [f"retail body inertia over {dist['trucks']} truck classes (inertiaPerMass in m^2; "
             "inertiaToWheelInertia dimensionless)"]
    for role, by in dist["roles"].items():
        for label, metrics in by.items():
            for metric, s in metrics.items():
                if s.get("n"):
                    lines.append(f"{role:13s} {label:5s} {metric:22s} n {s['n']:4d}  min {_fmt(s['min'])}  "
                                 f"p5 {_fmt(s['p5'])}  median {_fmt(s['median'])}  max {_fmt(s['max'])}")
    return "\n".join(lines) + "\n"


def _summary(dist: dict[str, Any] | None, role: str, field: str) -> dict[str, Any] | None:
    if dist is None:
        return None
    vals = dist["values"].get((role, field), [])
    out: dict[str, Any] = {"trucksWithRole": dist["withRole"].get(role, 0),
                           "trucksWithValue": dist["withValue"].get((role, field), 0), "n": len(vals)}
    nums = [_num(v) for v in vals]
    if vals and all(n is not None for n in nums):
        out.update(min=_clean(min(nums)), median=_clean(statistics.median(nums)), max=_clean(max(nums)))
    elif vals and field not in NAME_FIELDS:
        counts: dict[str, int] = {}
        for v in vals:
            k = json.dumps(v, sort_keys=True)
            counts[k] = counts.get(k, 0) + 1
        out["values"] = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5])
        out["distinct"] = len(counts)
    return out


def _side(vals: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not vals:
        return None
    distinct: list[Any] = []
    for v in vals:
        if v["value"] not in distinct:
            distinct.append(v["value"])
    return {"values": distinct, "sources": sorted({v["source"] for v in vals}),
            "evidence": vals[0]["evidence"], **({"note": vals[0]["note"]} if vals[0].get("note") else {})}


def _field_selected(field: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return True
    low = field.lower()
    return any((fnmatch.fnmatch(low, p.lower()) if any(c in p for c in "*?[") else p.lower() in low) for p in patterns)


def compare_trucks(mod: dict[str, Any], donor: dict[str, Any], dist: dict[str, Any] | None,
                   fields: list[str] | None = None) -> list[dict[str, Any]]:
    mv, dv = role_values(mod), role_values(donor)
    keys = sorted(set(mv) | set(dv), key=lambda k: (ROLE_ORDER.index(k[0]), k[1]))
    rows = []
    for role, field in keys:
        if not _field_selected(field, fields):
            continue
        m, d = _side(mv.get((role, field))), _side(dv.get((role, field)))
        summary = _summary(dist, role, field)
        flags = []
        mvals = m["values"] if m else []
        dvals = d["values"] if d else []
        if field in PRESENCE_FIELDS:
            if bool([v for v in mvals if v]) != bool([v for v in dvals if v]):
                flags.append("differs")
        elif (field not in NAME_FIELDS or field == "friction.entries") and m is not None and d is not None \
                and sorted(map(json.dumps, mvals)) != sorted(map(json.dumps, dvals)):
            flags.append("differs")
        if m is not None and d is not None and field not in PRESENCE_FIELDS and role != "derived" \
                and all(v is None for v in mvals) and any(v is not None for v in dvals):
            flags.append("absent-in-mod")
        if m is not None and summary and summary["n"] and field not in NAME_FIELDS | IGNORED_FIELDS:
            nums = [_num(v) for v in mvals if v is not None]
            if "min" in summary and nums and any(n is not None and not summary["min"] <= n <= summary["max"]
                                                 for n in nums):
                flags.append("outside-retail")
            elif "values" in summary and summary.get("distinct", 0) <= 12:
                seen = set(summary["values"])
                if any(v is not None and json.dumps(v, sort_keys=True) not in seen for v in mvals):
                    flags.append("unseen-in-retail")
        if summary and m is not None and all(v is None for v in mvals) and summary["trucksWithRole"] \
                and summary["trucksWithValue"] == summary["trucksWithRole"]:
            flags.append("missing")
        rows.append({"role": role, "field": field, "mod": m, "donor": d, "retail": summary, "flags": flags})
    return rows


def compare(mod: str | Path, donor: str, *, game_root: str | Path | None = None, fields: list[str] | None = None,
            truck: str | None = None, donor_truck: str | None = None, ctx: Context | None = None) -> dict[str, Any]:
    """Side-by-side effective values of a mod and a donor (retail truck name, or a pak / source tree)."""
    ctx = ctx or Context(game_root)
    mod_rep = report(mod, ctx=ctx, truck=truck)
    if not mod_rep["trucks"]:
        raise PhysicsReportError(f"no truck class in {mod}")
    if Path(donor).exists():
        donor_rep = report(donor, ctx=ctx, truck=donor_truck)
        if not donor_rep["trucks"]:
            raise PhysicsReportError(f"no truck class in {donor}")
        donor_truck_rep = donor_rep["trucks"][0]
        donor_info = {"target": str(donor), "kind": donor_rep["kind"], "sha256": donor_rep["sha256"],
                      "class": donor_truck_rep["class"]}
    else:
        name = resolve_retail(ctx, donor)
        donor_truck_rep = retail_report(ctx, name)
        donor_info = {"target": f"retail:{name}", "kind": "retail", "sha256": None, "class": donor_truck_rep["class"]}
    dists: dict[str, Any] = {}
    pairs = []
    for t in mod_rep["trucks"]:
        if ctx.retail() is not None and t["kind"] not in dists:
            dists[t["kind"]] = distribution(ctx, t["kind"])
        dist = dists.get(t["kind"])
        pairs.append({"mod": t["class"], "donor": donor_truck_rep["class"], "kind": t["kind"],
                      "donorKind": donor_truck_rep["kind"],
                      "retailTrucks": dist["trucks"] if dist else None,
                      "rows": compare_trucks(t, donor_truck_rep, dist, fields)})
    return {"mod": {"target": str(mod), "kind": mod_rep["kind"], "sha256": mod_rep["sha256"]},
            "donor": donor_info, "schema": mod_rep["schema"], "gameRoot": mod_rep["gameRoot"],
            "fields": fields, "pairs": pairs, "limits": LIMITS}


# ------------------------------------------------------------------------------------------------ text

def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, list) and len(value) > 3 and all(_num(v) is not None for v in value):
        return "[" + ",".join(_fmt(v) for v in value) + "]"
    if value is None:
        return "-"
    return json.dumps(value) if isinstance(value, (list, dict)) else str(value)


def _fmt_side(side: dict[str, Any] | None) -> str:
    if side is None:
        return "(no such role)"
    vals = " | ".join(_fmt(v) for v in side["values"])
    return f"{vals} ({''.join(SOURCE_LETTER[s] for s in side['sources'])})"


def _fmt_retail(summary: dict[str, Any] | None) -> str:
    if not summary:
        return ""
    if "min" in summary:
        return (f"{_fmt(summary['min'])}..{_fmt(summary['max'])} med {_fmt(summary['median'])} "
                f"[{summary['trucksWithValue']}/{summary['trucksWithRole']}]")
    if "values" in summary:
        top = next(iter(summary["values"]), "")
        return f"{summary['distinct']} distinct, top {top[:30]} [{summary['trucksWithValue']}/{summary['trucksWithRole']}]"
    return f"[{summary['trucksWithValue']}/{summary['trucksWithRole']} set]"


def format_compare(result: dict[str, Any], show_all: bool = False) -> str:
    lines = [f"mod:   {result['mod']['target']}" + (f"  sha256 {result['mod']['sha256']}" if result['mod']['sha256'] else ""),
             f"donor: {result['donor']['target']}  ({result['donor']['class']})",
             "sources: E explicit, I inherited, D engine-default, S schema-default, - absent, ~ derived; "
             "retail: min..max med [trucks with value/trucks with role]"]
    for pair in result["pairs"]:
        n = len(pair["retailTrucks"]) if pair["retailTrucks"] is not None else 0
        lines += ["", f"== {pair['mod']}  vs  {pair['donor']}  kind {pair['kind']} (donor {pair['donorKind']}; "
                      f"retail {pair['kind']} trucks: {n})"]
        rows = pair["rows"]
        outliers = [r for r in rows if set(r["flags"]) & OUTLIER_FLAGS]
        if show_all or result.get("fields"):
            sections = [("rows", rows)]
        else:
            key = [r for r in rows if r not in outliers and any(fnmatch.fnmatchcase(r["field"], p) for p in KEY_FIELDS)]
            differs = [r for r in rows if r not in outliers and r not in key and r["flags"]]
            sections = [("outliers (outside the retail range, missing, absent or unseen in retail)", outliers),
                        ("key fields (shown even when equal)", key), ("other differences from the donor", differs)]
        width = max((len(f"{r['role']} {r['field']}") for _, rs in sections for r in rs), default=20)
        shown = 0
        for title, section in sections:
            lines.append(f"-- {title}: {len(section)}")
            for row in section:
                label = f"{row['role']} {row['field']}".ljust(width)
                lines.append(f"{label}  mod {_fmt_side(row['mod'])}  donor {_fmt_side(row['donor'])}  "
                             f"retail {_fmt_retail(row['retail'])}  {','.join(row['flags'])}".rstrip())
            shown += len(section)
        lines.append(f"-- {len(rows)} fields compared, {len(outliers)} outliers, "
                     f"{sum(1 for r in rows if r['flags'])} flagged, {shown} shown")
    return "\n".join(lines) + "\n"


def format_report(result: dict[str, Any]) -> str:
    lines = [f"target: {result['target']}" + (f"  sha256 {result['sha256']}" if result["sha256"] else ""),
             f"schema: {result['schema']}; sources: E explicit, I inherited, D engine-default, S schema-default, "
             "- absent, ~ derived"]
    for t in result["trucks"]:
        lines += ["", f"== {t['class']}  tpl {t['tpl']}  kind {t['kind']}", f"   model {t['model']}  markup {t['markup']}"]
        for note in t["nodeNotes"]:
            lines.append(f"   node table: {note}")
        for ent in t["entities"]:
            lines.append(f"-- {ent['kind']} {ent['id']}" + (f"  [{ent['role']}]" if ent.get("role") else ""))
            for field, value in ent["fields"].items():
                extra = f"  ({value['note']})" if value.get("note") else ""
                lines.append(f"   {field} = {_fmt(value['value'])} {SOURCE_LETTER[value['source']]}  "
                             f"{value['evidence']}{extra}")
    lines += ["", "limits:"] + [f" - {x}" for x in result["limits"]]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------------------------ CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roadcraft physics",
                                     description="Effective physics values of a mod, and a donor comparison.")
    sub = parser.add_subparsers(dest="command", required=True)
    rep = sub.add_parser("report", help="effective physics values of every truck in a .pak or source tree")
    rep.add_argument("target")
    cmp_ = sub.add_parser("compare", help="compare a mod with a retail truck or another pak/tree")
    cmp_.add_argument("mod")
    cmp_.add_argument("--donor", required=True, help="retail truck name (e.g. 'EPEC TC305') or a .pak / folder")
    cmp_.add_argument("--fields", help="comma-separated field filters (substring, or glob with * ?)")
    cmp_.add_argument("--donor-truck", help="donor truck class filter when the donor is a pak/tree")
    cmp_.add_argument("--all", action="store_true", help="text: show every row, not only flagged ones")
    ine = sub.add_parser("inertia", help="retail spread of body inertia per body role (cached)")
    ine.add_argument("--cache", help="cache directory (default %%LOCALAPPDATA%%/roadcraft-toolchain/retail-cache)")
    ine.add_argument("--rows", action="store_true", help="JSON: include every retail body row")
    for p in (rep, cmp_, ine):
        p.add_argument("--json", action="store_true", help="JSON output")
        p.add_argument("--game-root", help="RoadCraft installation (schema and retail data)")
    for p in (rep, cmp_):
        p.add_argument("--truck", help="only truck classes whose path contains this text")
    args = parser.parse_args(argv)
    game_root = args.game_root or schema_mod.default_game_root()
    try:
        if args.command == "inertia":
            dist = inertia_distribution(Context(game_root), args.cache)
            if dist is None:
                raise PhysicsReportError("no retail installation found (pass --game-root or set ROADCRAFT_GAME_ROOT)")
            out = dist if args.rows else {k: v for k, v in dist.items() if k != "rows"}
            text = json.dumps(out, indent=1, sort_keys=True) + "\n" if args.json else format_inertia(dist)
        elif args.command == "report":
            result = report(args.target, game_root=game_root, truck=args.truck)
            text = json.dumps(result, indent=1, sort_keys=True) + "\n" if args.json else format_report(result)
        else:
            fields = [f.strip() for f in args.fields.split(",") if f.strip()] if args.fields else None
            result = compare(args.mod, args.donor, game_root=game_root, fields=fields, truck=args.truck,
                             donor_truck=args.donor_truck)
            text = json.dumps(result, indent=1, sort_keys=True) + "\n" if args.json else \
                format_compare(result, show_all=args.all)
    except (PhysicsReportError, OSError, zipfile.BadZipFile, retail_mod.RetailDataError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
