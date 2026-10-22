"""Hull contact over a joint's travel: sweep a prismatic or hinge child body (with everything jointed below it and
the wheels it carries) along its axis and find the first position where one of its collision shapes touches a
shape of the same truck that the engine does not filter from it.

Shapes are the cdt_ meshes' oriented boxes from the compiled model's per-mesh bounds table (tpl_reader.find_bounds,
physics_report.body_shapes) and wheel cylinders (physical radius and class width at the wheel node, axle along the
node's X).  Pairs are tested with a separating-axis test.  Filtering follows the engine
(research physics_semantics.md "Jointed-body collision filtering"; library/validator.md RC081):

* constraints are walked in markup order, keeping a constraint only while one of its bodies is new; only with fewer
  than 31 constraints in the markup are sub-system ids assigned (child first, counter from 0; the child's
  dontCollideWith is its parent's id, or, if it already has one, the parent's dontCollideWith becomes the child's);
* a pair is blocked when ``idA & dontB`` or ``idB & dontA`` is non-zero after bit 0 is cleared (so the
  first-listed constraint's child, id 0, is not filtered against its own children);
* members of one markup Collision Group never collide with each other and lose their constraint filtering;
* a body on ``no_collision`` collides with nothing; a wheel copies its carrier's layer and id bits, so it is
  filtered only against its carrier's constraint parent (and that parent's other filtered pairs).

Everything here is read-only and stdlib-only.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

from .vehicle import euler_axis

Vec = tuple[float, float, float]

CONSTRAINT_CAP = 31            # FUN_14153cb90: >= 31 constraints in a markup -> no sub-system ids at all
CONTACT_EPS = 0.005            # penetration (m) below which touching shapes do not count as contact
PRISMATIC_STEP = 0.01          # m per sweep step
HINGE_STEP = 0.5               # degrees per sweep step
PRISMATIC_BEYOND = 0.10        # sweep this far past each prismatic limit, to report the clearance there
HINGE_MAX = 180.0              # hinge limits beyond a half turn are swept to it
HINGE_BEYOND = 10.0            # degrees past each hinge limit
NEAR_LIMIT = 0.03              # m: contact within this of the limit (beyond it) is reported as near the limit
GROUP_BASE: int | None = 1    # markup Collision Group g (0-based) -> filter index g + 1 (None: groups ignored)
CYLINDER_SIDES = 16            # candidate axes around a wheel cylinder


# ------------------------------------------------------------------------------------------------ vectors

def _dot(a: Iterable[float], b: Iterable[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Vec, s: float) -> Vec:
    return (a[0] * s, a[1] * s, a[2] * s)


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a: Vec) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Vec) -> Vec | None:
    n = _norm(a)
    return None if n < 1e-9 else (a[0] / n, a[1] / n, a[2] / n)


def _rotate(v: Vec, axis: Vec, angle: float) -> Vec:
    """Rodrigues: ``v`` turned right-handed by ``angle`` radians about the unit ``axis``."""
    c, s = math.cos(angle), math.sin(angle)
    k = _dot(axis, v) * (1 - c)
    x = _cross(axis, v)
    return (v[0] * c + x[0] * s + axis[0] * k, v[1] * c + x[1] * s + axis[1] * k,
            v[2] * c + x[2] * s + axis[2] * k)


def _mat_dir(m: tuple[float, ...], v: Iterable[float]) -> Vec:
    v = tuple(v)
    return (v[0] * m[0] + v[1] * m[4] + v[2] * m[8], v[0] * m[1] + v[1] * m[5] + v[2] * m[9],
            v[0] * m[2] + v[1] * m[6] + v[2] * m[10])


def _mat_point(m: tuple[float, ...], p: Iterable[float]) -> Vec:
    d = _mat_dir(m, p)
    return (d[0] + m[12], d[1] + m[13], d[2] + m[14])


# ------------------------------------------------------------------------------------------------ shapes

class Shape:
    """An oriented box (``axes`` unit rows, ``half`` extents) or a cylinder (``axes[0]`` its axis, ``radius``,
    ``half[0]`` half its width), in model space."""

    __slots__ = ("name", "body", "kind", "center", "axes", "half", "radius", "bound")

    def __init__(self, name: str, body: str, kind: str, center: Vec, axes: list[Vec], half: list[float],
                 radius: float = 0.0) -> None:
        self.name, self.body, self.kind = name, body, kind
        self.center, self.axes, self.half, self.radius = center, axes, half, radius
        if kind == "box":
            self.bound = math.sqrt(sum(h * h for h in half))
        else:
            self.bound = math.sqrt(radius * radius + half[0] * half[0])

    def radius_along(self, n: Vec) -> float:
        if self.kind == "box":
            return sum(abs(_dot(n, a)) * h for a, h in zip(self.axes, self.half))
        c = abs(_dot(n, self.axes[0]))
        return self.half[0] * c + self.radius * math.sqrt(max(0.0, 1.0 - c * c))

    def moved(self, offset: Vec | None = None, pivot: Vec | None = None, axis: Vec | None = None,
              angle: float = 0.0) -> "Shape":
        if axis is not None and pivot is not None and angle:
            center = _add(pivot, _rotate(_sub(self.center, pivot), axis, angle))
            axes = [_rotate(a, axis, angle) for a in self.axes]
        else:
            center, axes = self.center, self.axes
        if offset is not None:
            center = _add(center, offset)
        return Shape(self.name, self.body, self.kind, center, axes, self.half, self.radius)


def box_shape(name: str, body: str, center: Iterable[float], axes: Iterable[Iterable[float]],
              size: Iterable[float]) -> Shape:
    return Shape(name, body, "box", tuple(center), [tuple(a) for a in axes], [s / 2 for s in size])


def cylinder_shape(name: str, body: str, center: Iterable[float], axis: Iterable[float], radius: float,
                   width: float) -> Shape:
    return Shape(name, body, "cylinder", tuple(center), [_unit(tuple(axis)) or (1.0, 0.0, 0.0)], [width / 2],
                 radius)


def _perpendicular(w: Vec) -> tuple[Vec, Vec]:
    ref = (1.0, 0.0, 0.0) if abs(w[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _unit(_cross(w, ref)) or (0.0, 0.0, 1.0)
    return u, _cross(w, u)


def _axes(a: Shape, b: Shape) -> list[Vec]:
    out: list[Vec] = []
    edges_a = a.axes if a.kind == "box" else None
    edges_b = b.axes if b.kind == "box" else None
    for s in (a, b):
        out.extend(s.axes)
    for s, other in ((a, b), (b, a)):
        if s.kind != "cylinder":
            continue
        w = s.axes[0]
        u, v = _perpendicular(w)
        rim = []
        for k in range(CYLINDER_SIDES):
            t = 2 * math.pi * k / CYLINDER_SIDES
            out.append(_add(_mul(u, math.cos(t)), _mul(v, math.sin(t))))
            rim.append(_add(_mul(u, -math.sin(t)), _mul(v, math.cos(t))))
        towards = _sub(other.center, s.center)
        radial = _unit(_sub(towards, _mul(w, _dot(towards, w))))
        if radial is not None:
            out.append(radial)
        other_edges = other.axes if other.kind == "box" else [other.axes[0]]
        for e in other_edges:
            for d in [w] + rim:
                c = _unit(_cross(e, d))
                if c is not None:
                    out.append(c)
    if edges_a is not None and edges_b is not None:
        for ea in edges_a:
            for eb in edges_b:
                c = _unit(_cross(ea, eb))
                if c is not None:
                    out.append(c)
    return out


def penetration(a: Shape, b: Shape) -> float:
    """Smallest overlap over the candidate separating axes (m): negative or below CONTACT_EPS = apart."""
    d = _sub(b.center, a.center)
    if _norm(d) > a.bound + b.bound:
        return -1.0
    least = math.inf
    for n in _axes(a, b):
        overlap = a.radius_along(n) + b.radius_along(n) - abs(_dot(n, d))
        if overlap < least:
            least = overlap
            if least < CONTACT_EPS:
                return least
    return least


def touching(a: Shape, b: Shape) -> bool:
    return penetration(a, b) >= CONTACT_EPS


# ------------------------------------------------------------------------------------------------ filter

class Filter:
    """The engine's collision filter inside one truck (module docstring)."""

    def __init__(self, constraints: list[tuple[str, str | None]], total_constraints: int,
                 groups: list[list[str]], layers: dict[str, str | None]) -> None:
        self.ids: dict[str, int] = {}
        self.dont: dict[str, int] = {}
        self.capped = total_constraints >= CONSTRAINT_CAP
        self.layers = layers
        if not self.capped:
            seen: set[str] = set()
            counter = 0
            for child, parent in constraints:
                parent = parent or "__world"
                if child in seen and parent in seen:
                    continue                                    # loop: dropped (spanning tree)
                seen.update((child, parent))
                if child not in self.ids:
                    self.ids[child], counter = counter, counter + 1
                if parent not in self.ids:
                    self.ids[parent], counter = counter, counter + 1
                if self.dont.get(child, 0) == 0:
                    self.dont[child] = self.ids[parent]
                else:
                    self.dont[parent] = self.ids[child]
        self.group_mask: dict[str, int] = {}
        if GROUP_BASE is not None:
            for g, members in enumerate(groups[:32]):
                index = g + GROUP_BASE
                for name in members:              # calcFilterInfo(layer, 0, g, g) overwrites the constraint ids
                    self.ids[name] = self.dont[name] = index
                    self.group_mask[name] = self.group_mask.get(name, 0) | (1 << index)

    def blocked(self, a: str, b: str) -> bool:
        """Whether bodies ``a`` and ``b`` never collide; a wheel is judged as its carrier body (it copies the
        carrier's layer and id bits), so pass the carrier's name for it."""
        if self.layers.get(a) == "no_collision" or self.layers.get(b) == "no_collision":
            return True
        if self.capped and not self.group_mask:
            return False
        ga, gb = self.group_mask.get(a, 0), self.group_mask.get(b, 0)
        ma = ga | (1 << self.ids.get(a, 0))
        mb = gb | (1 << self.ids.get(b, 0))
        da = ga | (1 << self.dont.get(a, 0))
        db = gb | (1 << self.dont.get(b, 0))
        return bool(((ma & db) | (mb & da)) & ~1)


# ------------------------------------------------------------------------------------------------ sweep

def _windows(kind: str, m: Shape, s: Shape, origin: Vec, axis: Vec, sign: float, end: float
             ) -> list[tuple[float, float]]:
    """Sweep intervals (0..end, along the sweep direction) where the two shapes' bounding spheres meet."""
    reach = m.bound + s.bound
    if kind == "prismatic":
        d = _sub(s.center, m.center)
        mid = sign * _dot(d, axis)
        disc = mid * mid - _dot(d, d) + reach * reach
        if disc < 0:
            return []
        lo, hi = max(0.0, mid - math.sqrt(disc)), min(end, mid + math.sqrt(disc))
        return [(lo, hi)] if lo <= hi else []
    r, q = _sub(m.center, origin), _sub(s.center, origin)
    a, b = _dot(r, axis), _dot(q, axis)
    rv, qv = _sub(r, _mul(axis, a)), _sub(q, _mul(axis, b))
    rho, sigma = _norm(rv), _norm(qv)
    base = (a - b) ** 2 + rho * rho + sigma * sigma
    if rho < 1e-9 or sigma < 1e-9:
        return [(0.0, end)] if base <= reach * reach else []
    c = (base - reach * reach) / (2 * rho * sigma)
    if c <= -1:
        return [(0.0, end)]
    if c > 1:
        return []
    half = math.degrees(math.acos(c))
    phi = math.degrees(math.atan2(_dot(_cross(rv, qv), axis), _dot(rv, qv)))   # angle from rv to qv about axis
    centre = sign * phi                                    # in sweep coordinates (x = sign * angle)
    out = []
    for turn in (-360.0, 0.0, 360.0):
        lo, hi = max(0.0, centre + turn - half), min(end, centre + turn + half)
        if lo <= hi:
            out.append((lo, hi))
    return out


def _first_contact(kind: str, moving: list[Shape], static: list[Shape], pairs: list[tuple[int, int]], pose,
                   origin: Vec, axis: Vec, limit: float, step: float, beyond: float
                   ) -> tuple[float, int, int] | None:
    """The first position from 0 towards ``limit`` (signed) and on past it by ``beyond`` where a pair touches,
    on a ``step`` grid inside each pair's bounding-sphere window, refined by bisection; with the pair."""
    if not pairs or limit == 0:
        return None
    sign = 1.0 if limit > 0 else -1.0
    end = abs(limit) + beyond
    jobs = sorted((lo, hi, i, j) for i, j in pairs
                  for lo, hi in _windows(kind, moving[i], static[j], origin, axis, sign, end))
    best: tuple[float, int, int] | None = None
    for lo, hi, i, j in jobs:
        if best is not None and lo >= best[0]:
            break
        k = max(1, int(math.ceil(lo / step - 1e-9)))
        prev = max(0.0, min(lo, (k - 1) * step))
        while True:
            x = min(end, k * step, hi + step)
            if best is not None and x - step >= best[0]:
                break
            if touching(pose(moving[i], sign * x), static[j]):
                a, b = prev, x
                for _ in range(12):
                    mid = (a + b) / 2
                    if touching(pose(moving[i], sign * mid), static[j]):
                        b = mid
                    else:
                        a = mid
                if best is None or b < best[0]:
                    best = (b, i, j)
                break
            if x >= min(end, hi + step) - 1e-12:
                break
            prev, k = x, k + 1
    return None if best is None else (sign * best[0], best[1], best[2])


def sweep_joint(kind: str, moving: list[Shape], static: list[Shape], allowed, origin: Vec, axis: Vec,
                low: float | None, high: float | None) -> dict[str, Any]:
    """Sweep ``moving`` along a prismatic (``origin`` unused, ``axis`` the slide direction, limits in m) or about a
    hinge (``origin`` the pivot, ``axis`` the hinge axis, limits in degrees).  ``allowed(m, s)`` says whether two
    shapes may collide.  Pairs already touching at rest are left out and counted."""
    if kind == "prismatic":
        def pose(s: Shape, x: float) -> Shape:
            return s.moved(offset=_mul(axis, x))
        step, beyond = PRISMATIC_STEP, PRISMATIC_BEYOND
    else:
        def pose(s: Shape, x: float) -> Shape:
            return s.moved(pivot=origin, axis=axis, angle=math.radians(x))
        step, beyond = HINGE_STEP, HINGE_BEYOND
    candidates = [(i, j) for i, m in enumerate(moving) for j, s in enumerate(static) if allowed(m, s)]
    at_rest = [(i, j) for i, j in candidates if touching(moving[i], static[j])]
    rest = set(at_rest)
    live = [p for p in candidates if p not in rest]
    out: dict[str, Any] = {"pairs": len(live), "restOverlaps": [(moving[i], static[j]) for i, j in at_rest]}
    for side, limit in (("low", low), ("high", high)):
        if limit is None or limit == 0:
            out[side] = None
            continue
        hit = _first_contact(kind, moving, static, live, pose, origin, axis, limit, step, beyond)
        out[side] = {"limit": limit, "contact": None if hit is None else hit[0],
                     "moving": None if hit is None else moving[hit[1]],
                     "static": None if hit is None else static[hit[2]],
                     "sweptTo": (1 if limit > 0 else -1) * (abs(limit) + beyond)}
    return out


def hinge_margin(moving: list[Shape], pivot: Vec, axis: Vec, distance: float = NEAR_LIMIT) -> float:
    """Degrees that move the farthest moving shape point ``distance`` metres about the hinge."""
    far = 0.0
    for s in moving:
        r = _sub(s.center, pivot)
        far = max(far, _norm(_sub(r, _mul(axis, _dot(r, axis)))) + s.bound)
    return math.degrees(distance / far) if far > 1e-6 else 0.0


# ------------------------------------------------------------------------------------------------ truck

def _limits(ent: dict, kind: str) -> tuple[float | None, float | None] | None:
    """(low, high) travel of a markup constraint, None for a side without a limit; None for an unlimited hinge."""
    def num(key: str, default: float = 0.0) -> float:
        v = ent.get(key, default)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default
    if kind == "prismatic":
        low = num("minLimit") if ent.get("isMinLimit") is True else None
        high = num("maxLimit") if ent.get("isMaxLimit") is True else None
        return low if low is None or low < 0 else None, high if high is None or high > 0 else None
    if ent.get("limited") is not True:
        return None
    a, b = num("angleStart"), num("angleEnd")
    lo, hi = max(-HINGE_MAX, min(a, b)), min(HINGE_MAX, max(a, b))     # slewing rings: +-18000 deg in retail
    return (lo if lo < 0 else None), (hi if hi > 0 else None)


def constraint_list(infos: list[Any], body_names: set[str], parent_of_node) -> tuple[list[dict], int]:
    """Markup constraints in order: ``{child, parent, kind, entity, objectIndex}`` and the total count."""
    out, total = [], 0
    for oi, info in enumerate(infos):
        if not isinstance(info, dict):
            continue
        child = (info.get("objectId") or {}).get("name")
        for ent in info.get("entities") or []:
            kind = str(ent.get("__type", "")) if isinstance(ent, dict) else ""
            if not kind.startswith("tpl_markup_constraint_"):
                continue
            total += 1
            if child not in body_names:
                continue
            target = ent.get("target", "__parent")
            if target == "__parent":
                parent = parent_of_node(child)
            elif target == "__world":
                parent = None
            else:
                parent = target if isinstance(target, str) else None
            out.append({"child": child, "parent": parent, "kind": kind[len("tpl_markup_constraint_"):],
                        "entity": ent, "objectIndex": oi})
    return out, total


def collision_groups(doc: Any) -> list[list[str]]:
    groups = doc.get("collisionGroups") if isinstance(doc, dict) else None
    out = []
    if isinstance(groups, dict):
        for value in groups.values():
            objects = value.get("objects") if isinstance(value, dict) else None
            if isinstance(objects, list):
                out.append([o for o in objects if isinstance(o, str)])
    return out


def sweep_truck(constraints: list[dict], total: int, groups: list[list[str]], layers: dict[str, str | None],
                shapes: dict[str, list[Shape]], wheels: list[Shape], wheel_body: dict[str, str],
                nodes_matrix) -> dict[str, dict[str, Any]]:
    """Sweep every prismatic and limited hinge child body; result per child body name.

    ``shapes``: body -> its boxes; ``wheels``: wheel cylinders (``body`` = the wheel's name) with ``wheel_body``
    mapping each wheel to its carrier; ``nodes_matrix(name)``: the node's model matrix."""
    filt = Filter([(c["child"], c["parent"]) for c in constraints], total, groups, layers)
    children: dict[str, list[str]] = {}
    for c in constraints:
        if c["parent"]:
            children.setdefault(c["parent"], []).append(c["child"])
    def below(root: str) -> set[str]:
        out, todo = set(), [root]
        while todo:
            b = todo.pop()
            if b not in out:
                out.add(b)
                todo.extend(children.get(b, []))
        return out

    carriers = set(wheel_body.values())
    posed: set[str] = set()          # operator-posed work parts: a position-motor joint carrying no wheels
    for c in constraints:
        motor = c["entity"].get("motor")
        if isinstance(motor, dict) and motor.get("__type") == "tpl_markup_position_motor":
            sub = below(c["child"])
            if not sub & carriers:
                posed |= sub
    results: dict[str, dict[str, Any]] = {}
    for c in constraints:
        if c["kind"] not in ("prismatic", "hinge"):
            continue
        child, ent = c["child"], c["entity"]
        limits = _limits(ent, c["kind"])
        base = {"kind": c["kind"], "objectIndex": c["objectIndex"], "parent": c["parent"]}
        if limits is None:
            results[child] = {**base, "skipped": "unlimited hinge"}
            continue
        if limits == (None, None):
            results[child] = {**base, "skipped": "no limited travel"}
            continue
        try:
            m = nodes_matrix(child)
        except (KeyError, IndexError):
            results[child] = {**base, "skipped": f"no model node {child}"}
            continue
        subtree = below(child)
        moving = [s for b in sorted(subtree) for s in shapes.get(b, [])] + \
                 [w for w in wheels if wheel_body.get(w.body) in subtree]
        carries = bool(subtree & carriers)
        # a wheel-carrying joint is judged against the truck's structure, not against work parts (cranes, booms,
        # grapples) whose modelled pose is only one of many (retail calibration, library/validator.md RC082)
        skip = posed - subtree if carries else set()
        static = [s for b, lst in shapes.items() if b not in subtree and b not in skip for s in lst] + \
                 [w for w in wheels if wheel_body.get(w.body) not in subtree]
        if not moving:
            results[child] = {**base, "skipped": "no collision shapes on the moving bodies"}
            continue
        rot = ent.get("childRotation", [0, 0, 0])
        rot = [float(x) for x in rot] if isinstance(rot, list) and len(rot) == 3 else [0.0, 0.0, 0.0]
        trans = ent.get("childTranslation", [0, 0, 0])
        trans = [float(x) for x in trans] if isinstance(trans, list) and len(trans) == 3 else [0.0, 0.0, 0.0]
        axis = _unit(_mat_dir(m, euler_axis(rot))) or (0.0, 0.0, 1.0)
        pivot = _mat_point(m, trans)

        def allowed(a: Shape, b: Shape) -> bool:
            wa, wb = a.kind == "cylinder", b.kind == "cylinder"
            if wa and wb:
                return False                                    # tyre vs tyre: not judged
            ba = wheel_body.get(a.body, a.body) if wa else a.body
            bb = wheel_body.get(b.body, b.body) if wb else b.body
            return not filt.blocked(ba, bb)

        res = sweep_joint(c["kind"], moving, static, allowed, pivot, axis, *limits)
        res.update(base)
        res["wheels"] = sum(1 for w in moving if w.kind == "cylinder")
        res["posedSkipped"] = sorted(skip)
        res["axis"] = axis
        res["margin"] = NEAR_LIMIT if c["kind"] == "prismatic" else hinge_margin(moving, pivot, axis)
        results[child] = res
    return results


def judge(res: dict[str, Any]) -> list[dict[str, Any]]:
    """Findings for one swept joint: ``{side, severity, contact, limit, moving, static}``; severity "warning" when
    the first contact comes before the limit, "info" when it is within the near-limit margin past it."""
    out = []
    margin = res.get("margin") or 0.0
    for side in ("low", "high"):
        r = res.get(side)
        if not r or r.get("contact") is None:
            continue
        d, lim = abs(r["contact"]), abs(r["limit"])
        if d <= lim:
            sev = "warning"
        elif d <= lim + margin:
            sev = "info"
        else:
            continue
        out.append({"side": side, "severity": sev, "contact": r["contact"], "limit": r["limit"],
                    "moving": r["moving"], "static": r["static"]})
    return out


def describe(shape: Shape | None) -> str:
    if shape is None:
        return "-"
    return f"wheel {shape.name}" if shape.kind == "cylinder" else f"{shape.name} ({shape.body})"
