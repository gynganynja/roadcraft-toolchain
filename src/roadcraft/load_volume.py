"""Dump-truck loads: the tub's load volume, its four borders, the native sand grid and the BRO settings.

Proven parts (library/truck-settings.md, "Dump truck loads with roadcraft.load_volume"):

* The load is a hidden mesh (``volumeMesh``) under the dump body (``bodySettings.parentBody``). The engine
  convex-hulls it and draws the carried sand as one height sheet at the authored model position: no pivot
  offset, sheet heights relative to the grid minimum times 4 m (SDK shader; Dump Twuck captures reprojected).
* The grid's rectangle is the union of the four border meshes' bounds, not the volume's. Left, right and
  front borders and the volume are read through their own node's local-to-parent transform; the back
  border's transform is composed with its parent's as well, so it must hang from a child of the dump body
  (the tail lid), as the shipped Aramatsu Bowhead hangs ``_load_border_rear`` from ``BoneLid_cdt``
  (disassembled Roadcraft ModEditor.exe; retail TPL).
* Each grid column takes its floor and surface from vertical rays through the hull. A column the hull misses
  takes the height where the ray meets a border, else the dump body's pivot height: open grid cells beyond
  the heap hang a curtain (Dump Twuck revision 3, owner's retail screenshots).

Coordinates are Blender model coordinates as projects author them: x left, y rear (front is -y), z up, in
metres. Bodies and borders are assumed axis-aligned at rest (translation-only frames), as dump rigs are.

Stdlib only. ``blender_load`` holds the matching Blender helpers (floor sampling, heap hull, borders,
``grid_report``).
"""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping, Sequence

Vec = tuple[float, float, float]
Tri = tuple[Vec, Vec, Vec]

# Decoded from the editor's load-volume setup (Dump Twuck revision 4, 2026-10-01).
CELLS_PER_METRE = 4
CELL_LIMITS = (2, 32)
INSET = {"min_x": .01, "max_x": -.01, "rear": .2, "front": -.01}  # native minZ = Blender rear
RAY_HEIGHT = 16.0
NUDGE, NUDGE_FROM = 1 / 64, .125
SHEET_RANGE = 4.0           # shader LOAD_VOLUME_MAX_HEIGHT
CLIP_THICKNESS = .1         # pixel shader: saturate(thickness / 0.1)
EDGE_STEP_WARNING = .5      # a heap cell meeting a border cell this much higher or lower shows a ledge
BORDER_THICKNESS = .05      # samples move 1/64 m inward: a 2 cm slab at the grid edge can be missed (Dump Twuck v5)
ROLES = ("left", "right", "front", "back")
WALL_KEYS = {"left": "leftWall", "right": "rightWall", "front": "frontWall", "back": "backWall"}


# ---------------------------------------------------------------- frames

def composition_shift(role: str, mesh_parent: str, parent_body: str,
                      frames: Mapping[str, tuple[str | None, Vec]]) -> Vec:
    """Model-space offset the engine adds to a border or volume, relative to where it is authored.

    ``frames`` maps a body to (its parent body, its model-space origin). Walls and the volume are read relative
    to their own parent body; the back border relative to its parent's parent. The result is zero when that
    reference is ``parent_body`` (correct); otherwise the difference of the two frames."""
    ref = mesh_parent if role != "back" else (frames.get(mesh_parent, (None, (0, 0, 0)))[0] or "")
    origin = lambda name: frames.get(name, (None, (0.0, 0.0, 0.0)))[1]  # noqa: E731
    return tuple(p - r for p, r in zip(origin(parent_body), origin(ref)))  # type: ignore[return-value]


def shifted(tris: Iterable[Tri], offset: Sequence[float]) -> list[Tri]:
    if not any(offset):
        return list(tris)
    return [tuple(tuple(c + o for c, o in zip(v, offset)) for v in tri) for tri in tris]  # type: ignore[misc]


# ---------------------------------------------------------------- grid

def grid_rect(borders: Mapping[str, Sequence[Tri]]) -> dict[str, Any]:
    """The native grid over the border meshes (already in the engine's view, see ``composition_shift``)."""
    pts = [v for tris in borders.values() for tri in tris for v in tri]
    if not pts:
        raise ValueError("the grid needs border meshes")
    min_x = min(p[0] for p in pts) + INSET["min_x"]
    max_x = max(p[0] for p in pts) + INSET["max_x"]
    front = min(p[1] for p in pts) - INSET["front"]
    rear = max(p[1] for p in pts) - INSET["rear"]
    lo, hi = CELL_LIMITS
    nx = max(lo, min(hi, int((max_x - min_x) * CELLS_PER_METRE + .5)))
    ny = max(lo, min(hi, int((rear - front) * CELLS_PER_METRE + .5)))
    return {"minX": min_x, "maxX": max_x, "frontY": front, "rearY": rear, "nx": nx, "ny": ny,
            "cellX": (max_x - min_x) / (nx - 1), "cellY": (rear - front) / (ny - 1)}


def _vertical_hits(tris: Sequence[Tri], x: float, y: float) -> list[float]:
    """Heights where the vertical line through (x, y) crosses the triangles (projected point-in-triangle)."""
    hits = []
    for a, b, c in tris:
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            continue                     # vertical or degenerate triangle: no unique crossing
        u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / d
        v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / d
        w = 1 - u - v
        if u >= -1e-9 and v >= -1e-9 and w >= -1e-9:
            hits.append(u * a[2] + v * b[2] + w * c[2])
    return hits


def _nudge(value: float, origin: float) -> float:
    c = value - origin
    return value - NUDGE if c > NUDGE_FROM else value + NUDGE if c < -NUDGE_FROM else value


def emulate(volume: Sequence[Tri], borders: Mapping[str, Sequence[Tri]], pivot: Sequence[float] = (0, 0, 0)) -> dict:
    """Emulate the native sand grid. ``volume`` and ``borders`` are model-space triangles in the engine's view
    (apply ``composition_shift`` first); ``pivot`` is the dump body's model-space origin.

    Each cell is ``(kind, floor, surface)``: ``hull`` (inside the hull), ``border`` (missed the hull, met a
    border) or ``pivot`` (fell to the dump body's pivot height)."""
    rect = grid_rect(borders)
    walls = [t for tris in borders.values() for t in tris]
    cells = []
    for j in range(rect["ny"]):
        y = rect["frontY"] + j * rect["cellY"]
        yn = _nudge(y, pivot[1])         # samples move 1/64 m toward the body origin on both axes
        row = []
        for i in range(rect["nx"]):
            x = _nudge(rect["minX"] + i * rect["cellX"], pivot[0])
            hits = _vertical_hits(volume, x, yn)
            if hits:
                row.append(("hull", min(hits), max(hits)))
                continue
            wall = _vertical_hits(walls, x, yn)
            if wall:
                row.append(("border", max(wall), max(wall)))
            else:
                row.append(("pivot", pivot[2], pivot[2]))
        cells.append(row)
    counts: dict[str, int] = {}
    for row in cells:
        for kind, _, _ in row:
            counts[kind] = counts.get(kind, 0) + 1
    steps = []
    for j, row in enumerate(cells):
        for i, (kind, floor, top) in enumerate(row):
            if kind != "hull":
                continue
            for jj, ii in ((j + 1, i), (j - 1, i), (j, i + 1), (j, i - 1)):
                if 0 <= jj < rect["ny"] and 0 <= ii < rect["nx"] and cells[jj][ii][0] == "border":
                    steps.append(top - cells[jj][ii][2])   # pivot cells are RC040's
    floors = [c[1] for row in cells for c in row]
    tops = [c[2] for row in cells for c in row]
    pivot_cells = [(round(rect["minX"] + i * rect["cellX"], 3), round(rect["frontY"] + j * rect["cellY"], 3))
                   for j, row in enumerate(cells) for i, c in enumerate(row) if c[0] == "pivot"]
    return {"grid": rect, "counts": counts, "cells": cells, "pivotCells": pivot_cells,
            "sheetRange": max(tops) - min(floors), "maxEdgeStep": max((abs(s) for s in steps), default=0.0)}


def grid_findings(report: Mapping[str, Any], shifts: Mapping[str, Sequence[float]] | None = None,
                  tub: Mapping[str, Sequence[float]] | None = None) -> list[tuple[str, str, str]]:
    """(code, severity, message) for an ``emulate`` report. ``shifts`` are the ``composition_shift`` offsets
    by role; ``tub`` is an optional interior box ``{"min": (x, y, z), "max": (x, y, z)}``."""
    out = []
    n = len(report["pivotCells"])
    if n:
        out.append(("RC040", "error", f"{n} grid cells miss the hull and every border and fall to the dump body's pivot "
                    f"height (first {report['pivotCells'][:3]}): the sand sheet drops there, a curtain behind or below "
                    "the tub. Keep the borders inside the tub and give them the sand height beside them"))
    if report["sheetRange"] >= SHEET_RANGE:
        out.append(("RC041", "error", f"the sheet spans {report['sheetRange']:.2f} m; the shader stores heights over 4 m "
                    "from the grid minimum"))
    for role, offset in (shifts or {}).items():
        if any(abs(c) > 1e-3 for c in offset):
            out.append(("RC042", "error" if role == "back" else "warning",
                        f"the engine reads the {role} {'border' if role in ROLES else 'mesh'} {tuple(round(c, 3) for c in offset)} "
                        "m from where it is authored: hang the back border from the tail lid, the rest from the dump body"))
    if report["maxEdgeStep"] > EDGE_STEP_WARNING:
        out.append(("RC043", "warning", f"the heap meets a border cell with a {report['maxEdgeStep']:.2f} m step: set "
                    "border tops nearer the sand height beside them"))
    if tub:
        g = report["grid"]
        lo, hi = tub["min"], tub["max"]
        if g["minX"] < lo[0] or g["maxX"] > hi[0] or g["frontY"] < lo[1] or g["rearY"] > hi[1]:
            out.append(("RC044", "warning", f"the grid x {g['minX']:.2f}..{g['maxX']:.2f}, y {g['frontY']:.2f}.."
                        f"{g['rearY']:.2f} leaves the tub interior; its outer cells draw outside the steel"))
    return out


def hidden_markup(names: Iterable[str]) -> dict[str, Any]:
    """Model-markup ``objSettings.settings`` entries that hide load helpers (volume, borders) in game. Concrete
    visibility flags: an unresolved ``invisible`` brand crashed scene loading (Lada v5)."""
    flags = {"visibleDefault": False, "visibleInReflectionCubemap": False, "__type": "tpl_markup_visibility_flags"}
    return {n: {"visibility": dict(flags), "__type": "TplObjSettingsGeom"} for n in names}


# ---------------------------------------------------------------- settings

LOAD_TEMPLATE: dict[str, Any] = {
    # Shape of the shipped Aramatsu Bowhead / Baikal 65206 blocks; names and amounts are filled in.
    "isEnabled": True, "isRefiller": False, "refillSpeed": 1, "openingDelay": 1, "volumeChangeMult": .25,
    "pourMultiplier": 1.5, "upliftConstraintName": "dump", "canBeUplifted": True, "upliftConstraintAllowedState": "close",
    "volumeScale": 1, "horizontAngleScalar": 1,
    "particleLoadVolumeSettings": {"sfxPourActor": "gpu_sand_pour", "sfxRefillActor": "sfx_sand_refill",
                                   "__type": "ParticleLoadVolumeSettings"},
    "loadVolumeWarningSettings": {"warningDuration": 3000, "fadeOutAnimationDelay": 2700,
                                  "markerLocatorOffset": {"y": .1, "__type": "Vector3d"},
                                  "planeCurrentStateDesc": {"type": {"__type": "machine_tilt_red"}, "__type": "IactorDesc"},
                                  "planeDesiredStateDesc": {"type": {"__type": "machine_tilt_green"}, "__type": "IactorDesc"},
                                  "__type": "LoadVolumeWarningSettings"},
    "__type": "LoadVolumeSettings",
}


def load_settings(*, volume: str, parent_body: str, borders: Mapping[str, str], capacity: float, mass: float,
                  lid: Mapping[str, Any] | None = None, refill_offset: Sequence[float] = (0, 4.5, -1.5),
                  template: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A ``loadVolumeSettings`` block. ``borders`` maps left/right/front/back to mesh names (an open-backed
    tub, like the EPEC LT200, omits ``back``); ``capacity`` is the hull volume in m3 and ``mass`` the full
    payload in kg (``volumeMass`` is the native maximum mass; density follows). ``lid`` =
    ``{"constraint", "open", "closed"}`` adds the hydraulic tail lid (Bowhead pattern). ``refill_offset`` is
    native (x, y up, z forward) from the volume: the refill stream follows the volume (RC035)."""
    if capacity <= 0 or mass <= 0:
        raise ValueError("capacity and mass must be positive")
    missing = [r for r in ("left", "right", "front") if r not in borders]
    if missing:
        raise ValueError(f"a tub needs left, right and front borders; missing {missing}")
    doc = copy.deepcopy(dict(template or LOAD_TEMPLATE))
    doc.update(isEnabled=True, volumeMesh=volume, dumpBodyName=volume, volumeMass=mass,
               sandQuantity=round(capacity, 4), density=round(mass / capacity, 4))
    body = {"parentBody": parent_body, "__type": "BodyLoadVolumeSettings"}
    body.update({WALL_KEYS[r]: name for r, name in borders.items()})
    doc["bodySettings"] = body
    particles = dict(doc.get("particleLoadVolumeSettings") or {"__type": "ParticleLoadVolumeSettings"})
    particles.update(sfxMovableDumpPositionBone=volume,
                     sfxRefillLocalPosition=dict(zip(("x", "y", "z"), refill_offset), __type="Vector3d"))
    doc["particleLoadVolumeSettings"] = particles
    warning = dict(doc.get("loadVolumeWarningSettings") or {})
    if warning:
        warning["markerLocator"] = volume
        doc["loadVolumeWarningSettings"] = warning
    if lid:
        if "back" not in borders:
            raise ValueError("a hydraulic lid closes the back of the tub: give it the back border")
        doc.update(canBeDynamicallyOpened=True, volumeClosingConstraintName=lid["constraint"],
                   volumeClosedState=lid["closed"], volumeOpenedState=lid["open"],
                   hydraulicLid={"isEnabled": True, "lidConstraint": lid["constraint"], "lidOpenState": lid["open"],
                                 "lidCloseState": lid["closed"], "__type": "LoadVolumeHydraulicLidSettings"})
    else:
        doc["canBeDynamicallyOpened"] = False
    return doc


def settings_findings(load: Mapping[str, Any], names: Iterable[str] | None = None) -> list[tuple[str, str, str]]:
    """Static checks on a ``loadVolumeSettings`` block (and the model's node names, when known)."""
    out = []
    if not load.get("isEnabled"):
        return out
    body = load.get("bodySettings") or {}
    if names is not None:
        names = set(names)
        wanted = [load.get("volumeMesh"), body.get("parentBody"), *(body.get(k) for k in WALL_KEYS.values())]
        missing = sorted({w for w in wanted if w and w not in names})
        if missing:
            out.append(("RC036", "error", f"loadVolumeSettings names nodes the model lacks: {missing}"))
    if load.get("canBeDynamicallyOpened") and not body.get("backWall"):
        out.append(("RC036", "warning", "a dynamically opened tub has no back border: the lid closes nothing"))
    return out
