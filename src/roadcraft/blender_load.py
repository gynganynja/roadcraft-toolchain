"""Blender-side dump-truck load geometry for ``roadcraft.load_volume``. Run inside Blender (``bpy`` on use).

* ``floor_sampler``  the tub's real floor under (x, y), ray-cast from the bed art (faces weighted to the dump
                     body), so the load follows the steel instead of a box under a sloping floor.
* ``heap_top``       a heaped surface: crown paraboloid or pointed elliptic cone, cut by end slopes.
* ``heap_hull``      the load volume: convex hull between floor + clearance and the heap, tapering to the
                     steel where the heap thins out (no thick open edge).
* ``load_borders``   the four border meshes the native grid spans: sides and front under the dump body, the
                     back block over the rear corners under the tail lid, tops at the sand height.
* ``grid_report``    emulate the native grid on the authored meshes and return ``load_volume`` findings.

Hide the volume and borders in the model markup (``load_volume.hidden_markup``): ``hide_render`` only keeps
them out of Blender renders. Coordinates: Blender model space, x left, y rear, z up.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Mapping, Sequence

from . import load_volume


def attach(obj: Any, rig: Any, bone: str) -> Any:
    """Parent ``obj`` to ``bone`` of ``rig`` keeping its model-space placement."""
    import bpy
    bpy.context.view_layer.update()
    world = obj.matrix_world.copy()
    obj.parent, obj.parent_type, obj.parent_bone = rig, "BONE", bone
    bpy.context.view_layer.update()
    obj.matrix_world = world
    return obj


def floor_sampler(obj: Any, *, group: str | None = None, faces: set[int] | None = None,
                  rim: float | None = None, start: float | None = None) -> Callable[[float, float], float | None]:
    """``floor(x, y)``: the first up-facing surface below ``rim`` (- 5 cm) under (x, y) on ``obj``'s rest mesh,
    restricted to faces whose vertices are all weighted over 0.5 to vertex group ``group`` or to ``faces``."""
    import bmesh
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    if group is not None:
        index = obj.vertex_groups[group].index
        keep = {v.index for v in obj.data.vertices if any(g.group == index and g.weight > .5 for g in v.groups)}
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if not all(v.index in keep for v in f.verts)], context="FACES")
    elif faces is not None:
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in faces], context="FACES")
    top = start if start is not None else max(v.co.z for v in bm.verts) + 1.0
    tree = BVHTree.FromBMesh(bm)
    bm.free()

    def floor(x: float, y: float) -> float | None:
        origin = Vector((x, y, top))
        for _ in range(64):
            loc, normal, _, _ = tree.ray_cast(origin, Vector((0, 0, -1)))
            if loc is None:
                return None
            if (rim is None or loc.z < rim - .05) and normal.z > .05:
                return loc.z
            origin = loc + Vector((0, 0, -.002))
        return None
    return floor


def heap_top(*, side_x: float, crown_z: float, side_z: float, crown_y: float = 0.0, fall_y: float = 0.0,
             front: Sequence[float] | None = None, rear: Sequence[float] | None = None,
             profile: str = "paraboloid", cone_slope_y: float | None = None) -> Callable[[float, float], float]:
    """Heap surface ``top(x, y)``, optionally cut by unchanged front/rear slope planes.

    The default paraboloid has ``crown_z`` at ``(0, crown_y)``, ``side_z`` at
    ``(+/-side_x, crown_y)``, and loses ``fall_y`` metres per square metre along y.
    ``elliptic_cone`` gives a pointed crown with linear centreline drops: transverse
    slope ``(crown_z - side_z) / side_x`` and longitudinal ``cone_slope_y`` (m/m).
    It ignores ``fall_y``. Cone dimensions and slopes must be finite and positive.
    Front ``(y, z, degrees)`` rises rearward; rear ``(y, z, degrees)`` rises forward.
    Include the exact crown coordinates in hull samples to retain the pointed peak.
    """
    if profile not in ("paraboloid", "elliptic_cone"):
        raise ValueError(f"unknown heap profile: {profile!r}")
    if profile == "elliptic_cone":
        values = {"side_x": side_x, "crown_z": crown_z, "side_z": side_z,
                  "crown_y": crown_y, "cone_slope_y": cone_slope_y}
        for name, value in values.items():
            if value is None or not math.isfinite(value):
                raise ValueError(f"elliptic_cone requires finite {name}")
        if side_x <= 0 or cone_slope_y <= 0 or crown_z <= side_z:
            raise ValueError("elliptic_cone requires positive side_x, cone_slope_y and crown height above side_z")
        slope_x = (crown_z - side_z) / side_x
        if not math.isfinite(slope_x) or slope_x <= 0:
            raise ValueError("elliptic_cone requires a finite positive transverse slope")

    def top(x: float, y: float) -> float:
        if profile == "elliptic_cone":
            z = crown_z - math.hypot(slope_x * x, cone_slope_y * (y - crown_y))
        else:
            z = crown_z - (crown_z - side_z) * (x / side_x) ** 2 - fall_y * (y - crown_y) ** 2
        if front:
            z = min(z, front[1] + math.tan(math.radians(front[2])) * (y - front[0]))
        if rear:
            z = min(z, rear[1] + math.tan(math.radians(rear[2])) * (rear[0] - y))
        return z
    return top


def heap_hull(name: str, floor: Callable[[float, float], float | None], top: Callable[[float, float], float],
              xs: Sequence[float], ys: Sequence[float], *, clearance: float | Callable[[float], float] = 0.0,
              rig: Any = None, bone: str | None = None, material: Any = None) -> tuple[Any, dict[str, Any]]:
    """Convex hull between ``floor + clearance`` and ``top`` over ``xs`` x ``ys``. Between samples where the
    heap thins to nothing, the zero-thickness point is bisected so the hull tapers onto the steel. Returns the
    object (bone-parented to ``bone`` when given, at the model origin like shipped ``_load_volume``) and its
    measurements, including the worst hull-floor point below the steel on a 0.1 m survey."""
    import bmesh
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    lift = clearance if callable(clearance) else (lambda y: clearance)

    def bottom(x: float, y: float) -> float | None:
        f = floor(x, y)
        return None if f is None else f + lift(y)

    def depth(x: float, y: float) -> float | None:
        b = bottom(x, y)
        return None if b is None else top(x, y) - b

    points = []
    ys = sorted(ys)
    for x in xs:
        for y in ys:
            d = depth(x, y)
            if d is not None and d > 1e-3:
                points += [(x, y, bottom(x, y)), (x, y, top(x, y))]
        for ya, yb in zip(ys, ys[1:]):
            da, db = depth(x, ya), depth(x, yb)
            if da is None or db is None or (da > 0) == (db > 0):
                continue
            lo, hi = ya, yb
            for _ in range(40):
                mid = (lo + hi) / 2
                if (depth(x, mid) > 0) == (da > 0):
                    lo = mid
                else:
                    hi = mid
            y = (lo + hi) / 2
            points.append((x, y, bottom(x, y)))
    if len(points) < 4:
        raise ValueError("the heap does not rise above the floor at enough samples")
    hull = bmesh.new()
    for p in points:
        hull.verts.new(p)
    result = bmesh.ops.convex_hull(hull, input=hull.verts, use_existing_faces=False)
    loose = {e for e in result["geom_interior"] + result["geom_unused"] if isinstance(e, bmesh.types.BMVert)}
    bmesh.ops.delete(hull, geom=list(loose), context="VERTS")
    bmesh.ops.dissolve_limit(hull, angle_limit=math.radians(1), verts=hull.verts, edges=hull.edges)
    bmesh.ops.delete(hull, geom=[v for v in hull.verts if not v.link_faces], context="VERTS")
    bmesh.ops.triangulate(hull, faces=hull.faces)
    bmesh.ops.recalc_face_normals(hull, faces=hull.faces)
    volume = abs(hull.calc_volume())
    tree = BVHTree.FromBMesh(hull)
    lo_v = [min(v.co[i] for v in hull.verts) for i in range(3)]
    hi_v = [max(v.co[i] for v in hull.verts) for i in range(3)]
    worst, samples = 0.0, 0
    for i in range(int(lo_v[0] * 10), int(hi_v[0] * 10) + 1):
        for j in range(int(lo_v[1] * 10), int(hi_v[1] * 10) + 1):
            x, y = i / 10, j / 10
            loc = tree.ray_cast(Vector((x, y, lo_v[2] - 10)), Vector((0, 0, 1)))[0]
            f = floor(x, y)
            if loc is None or f is None:
                continue
            samples += 1
            worst = min(worst, loc.z - f)
    mesh = bpy.data.meshes.new(name)
    hull.to_mesh(mesh)
    hull.free()
    mesh.uv_layers.new(name="UVMap")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if material is not None:
        mesh.materials.append(material)
    if rig is not None and bone:
        attach(obj, rig, bone)
    obj.hide_render, obj.display_type = True, "WIRE"
    info = {"volume": volume, "min": lo_v, "max": hi_v, "heightRange": hi_v[2] - lo_v[2],
            "vertices": len(mesh.vertices), "faces": len(mesh.polygons), "floorSamples": samples,
            "worstBelowFloor": worst}
    if info["heightRange"] >= load_volume.SHEET_RANGE:
        raise ValueError(f"the heap spans {info['heightRange']:.2f} m; keep it under {load_volume.SHEET_RANGE} m")
    return obj, info


def _box(name: str, verts: Sequence[Sequence[float]], rig: Any, bone: str, material: Any) -> Any:
    import bpy
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
    mesh.update()
    mesh.uv_layers.new(name="UVMap")
    if material is not None:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    attach(obj, rig, bone)
    obj.hide_render, obj.display_type = True, "WIRE"
    return obj


def load_borders(rig: Any, parent_body: str, lid_body: str | None, *, side_x: float, side_y: Sequence[float],
                 front_y: float, base: float, side_top: float, front_top: float,
                 back: Sequence[float] | None = None, thickness: float = load_volume.BORDER_THICKNESS,
                 prefix: str = "hidden__load_border_", material: Any = None) -> dict[str, Any]:
    """Borders inside the hull's bounds (they set the grid): left/right slabs ``thickness`` thick at
    ``+-side_x`` over ``side_y = (y0, y1)``, a front slab at ``front_y``, all from ``base`` to their tops under
    ``parent_body``; and ``back = (y0, y1, bottom, top_at_y0, top_at_y1)``, a sloped block across the rear
    corners under ``lid_body``. Tops should sit at the sand height beside each border; omit ``back`` for an
    open-backed tub. Keep slabs at least ``load_volume.BORDER_THICKNESS`` thick: grid samples are nudged
    1/64 m toward the body origin, so a thinner slab on the grid's edge can be missed."""
    w, (y0, y1) = thickness, side_y
    slab = lambda a, b: [(x, y, z) for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])]  # noqa: E731
    out = {
        "left": _box(prefix + "left", slab((side_x - w, y0, base), (side_x, y1, side_top)), rig, parent_body, material),
        "right": _box(prefix + "right", slab((-side_x, y0, base), (-side_x + w, y1, side_top)), rig, parent_body, material),
        "front": _box(prefix + "front", slab((-side_x, front_y, base), (side_x, front_y + w, front_top)), rig, parent_body, material),
    }
    if back:
        if not lid_body:
            raise ValueError("the back border hangs from the tail-lid body; name it")
        b0, b1, bottom, t0, t1 = back
        verts = [(x, y, bottom if z == "b" else t0 + (t1 - t0) * (y - b0) / (b1 - b0))
                 for x in (-side_x, side_x) for y in (b0, b1) for z in "bt"]
        out["back"] = _box(prefix + "back", verts, rig, lid_body, material)
    return out


def triangles(obj: Any) -> list[load_volume.Tri]:
    """Model-space triangles of ``obj``'s rest mesh."""
    mesh, mw = obj.data, obj.matrix_world
    mesh.calc_loop_triangles()
    return [tuple(tuple(mw @ mesh.vertices[i].co) for i in tri.vertices) for tri in mesh.loop_triangles]  # type: ignore[misc]


def body_frames(rig: Any) -> dict[str, tuple[str | None, load_volume.Vec]]:
    """``{bone: (parent bone, model-space head)}`` for ``load_volume.composition_shift``."""
    mw = rig.matrix_world
    return {b.name: (b.parent.name if b.parent else None, tuple(mw @ b.head_local)) for b in rig.data.bones}


def grid_report(volume: Any, borders: Mapping[str, Any], rig: Any, parent_body: str,
                tub: Mapping[str, Sequence[float]] | None = None) -> dict[str, Any]:
    """Emulate the native grid on the authored volume and borders (in the engine's view of their parents) and
    attach ``load_volume.grid_findings``. The per-cell table is dropped from the result for compact reports."""
    frames = body_frames(rig)
    parent = lambda o: o.parent_bone if o.parent_type == "BONE" else None  # noqa: E731
    shifts = {"volume": load_volume.composition_shift("volume", parent(volume), parent_body, frames)}
    view = {}
    for role, obj in borders.items():
        shifts[role] = load_volume.composition_shift(role, parent(obj), parent_body, frames)
        view[role] = load_volume.shifted(triangles(obj), shifts[role])
    report = load_volume.emulate(load_volume.shifted(triangles(volume), shifts["volume"]), view, frames[parent_body][1])
    report["shifts"] = shifts
    report["findings"] = load_volume.grid_findings(report, shifts, tub)
    report.pop("cells")
    return report
