"""Pinned, read-only USF geometry diagnostic for the 60 D11 blade leaves.

The numeric comparison is stdlib-only so its rigid-fit and normal invariants
can be tested without Blender. The worker parses USFs; this host never exports.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from .blender_authoring import BlenderAuthoringError, _pinned_asset
from .blender_blade_relocation import (
    BLEND_SHA256, BLENDER_VERSION_PINS, INVENTORY_SHA256, LEAVES,
    NATIVE_PARENT, REPAIRED_PARENT, USF_SHA256, WORKLIST, WORKLIST_SHA256,
    BladeRelocationError, _rows_and_native, _unlinked_path, require_hash,
    require_sdk_pins,
)
from .blender_left_push_probe import LeftPushProbeError
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_blade_geometry_worker.py")
WORKER_SHA256 = "5c1b39a11b4f897a7d40ec5c1b4baf09f9a120754b2a31fad3ed803f25fa7fbc"
RESULT_PREFIX = "ROADCRAFT_BLADE_GEOMETRY "
MAX_JSON_BYTES = 128 * 1024
EXPECTED_CORNERS = 6486
POSITION_TOLERANCE = 1e-5
NORMAL_ANGLE_DEGREES = 0.1


class BladeGeometryError(RuntimeError):
    """A pin, array, numeric comparison or no-write invariant differs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BladeGeometryError(message)


def _vector(value, width: int, label: str) -> tuple[float, ...]:
    _require(len(value) == width, f"{label} width differs")
    result = tuple(float(component) for component in value)
    _require(all(math.isfinite(component) for component in result),
             f"{label} is not finite")
    return result


def _points(values, label: str) -> list[tuple[float, float, float]]:
    _require(0 < len(values) <= 5000 and len(values) % 3 == 0,
             f"{label} count differs")
    return [_vector(value, 3, label) for value in values]


def _matrix(value, label: str) -> tuple[tuple[float, ...], ...]:
    rows = tuple(_vector(row, 4, label) for row in value)
    _require(len(rows) == 4 and all(abs(a-b) <= 1e-5 for a, b in
             zip(rows[3], (0.0, 0.0, 0.0, 1.0))), f"{label} is not affine")
    return rows


def _matmul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(4))
                       for j in range(4)) for i in range(4))


def _inverse3(a):
    x, y, z = a
    det = (x[0]*(y[1]*z[2]-y[2]*z[1])
           - x[1]*(y[0]*z[2]-y[2]*z[0])
           + x[2]*(y[0]*z[1]-y[1]*z[0]))
    _require(math.isfinite(det) and abs(det) > 1e-12,
             "singular mesh transform")
    return (
        ((y[1]*z[2]-y[2]*z[1])/det, (x[2]*z[1]-x[1]*z[2])/det,
         (x[1]*y[2]-x[2]*y[1])/det),
        ((y[2]*z[0]-y[0]*z[2])/det, (x[0]*z[2]-x[2]*z[0])/det,
         (x[2]*y[0]-x[0]*y[2])/det),
        ((y[0]*z[1]-y[1]*z[0])/det, (x[1]*z[0]-x[0]*z[1])/det,
         (x[0]*y[1]-x[1]*y[0])/det),
    )


def _inverse_affine(m):
    inv = _inverse3(tuple(row[:3] for row in m[:3]))
    t = tuple(-sum(inv[i][k] * m[k][3] for k in range(3))
              for i in range(3))
    return (tuple(tuple(inv[i]) + (t[i],) for i in range(3)) +
            ((0.0, 0.0, 0.0, 1.0),))


def _transform(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) + m[i][3]
                 for i in range(3))


def _normal_transform(m, v):
    inv = _inverse3(tuple(row[:3] for row in m[:3]))
    return _unit(tuple(sum(inv[k][i] * v[k] for k in range(3))
                       for i in range(3)))


def _unit(v):
    length = math.sqrt(sum(component * component for component in v))
    _require(length > 1e-12 and math.isfinite(length), "zero normal")
    return tuple(component / length for component in v)


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _distance(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def _errors(values):
    _require(bool(values), "empty numeric comparison")
    return {"max": max(values),
            "rms": math.sqrt(sum(value*value for value in values)/len(values))}


def _largest_eigenvector_symmetric4(value):
    """Jacobi diagonalization for Horn's symmetric quaternion matrix."""
    a = [list(row) for row in value]
    eig = [[float(i == j) for j in range(4)] for i in range(4)]
    scale = max(abs(a[i][j]) for i in range(4) for j in range(4))
    _require(scale > 0 and math.isfinite(scale), "degenerate rigid fit")
    for _ in range(100):
        p, q = max(((i, j) for i in range(4) for j in range(i+1, 4)),
                   key=lambda pair: abs(a[pair[0]][pair[1]]))
        if abs(a[p][q]) <= 1e-14 * scale:
            break
        tau = (a[q][q]-a[p][p])/(2*a[p][q])
        t = (1 if tau >= 0 else -1)/(abs(tau)+math.sqrt(1+tau*tau))
        c = 1/math.sqrt(1+t*t)
        s = t*c
        off = a[p][q]
        a[p][p] -= t*off
        a[q][q] += t*off
        a[p][q] = a[q][p] = 0.0
        for k in range(4):
            if k != p and k != q:
                left, right = a[k][p], a[k][q]
                a[k][p] = a[p][k] = c*left-s*right
                a[k][q] = a[q][k] = s*left+c*right
            left, right = eig[k][p], eig[k][q]
            eig[k][p] = c*left-s*right
            eig[k][q] = s*left+c*right
    else:
        raise BladeGeometryError("rigid-fit eigenvalue solver did not converge")
    index = max(range(4), key=lambda i: a[i][i])
    return _unit(tuple(eig[i][index] for i in range(4)))


def _proper_rigid_fit(native, repaired):
    count = len(native)
    nx = tuple(sum(p[i] for p in native)/count for i in range(3))
    ry = tuple(sum(p[i] for p in repaired)/count for i in range(3))
    cov = [[0.0]*3 for _ in range(3)]
    for p, q in zip(native, repaired):
        x = tuple(p[i]-nx[i] for i in range(3))
        y = tuple(q[i]-ry[i] for i in range(3))
        for i in range(3):
            for j in range(3):
                cov[i][j] += x[i]*y[j]
    xx, xy, xz = cov[0]
    yx, yy, yz = cov[1]
    zx, zy, zz = cov[2]
    horn = (
        (xx+yy+zz, yz-zy, zx-xz, xy-yx),
        (yz-zy, xx-yy-zz, xy+yx, zx+xz),
        (zx-xz, xy+yx, -xx+yy-zz, yz+zy),
        (xy-yx, zx+xz, yz+zy, -xx-yy+zz),
    )
    w, x, y, z = _largest_eigenvector_symmetric4(horn)
    rotation = (
        (1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)),
        (2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)),
        (2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)),
    )
    translation = tuple(ry[i]-_dot(rotation[i], nx) for i in range(3))
    residuals = [_distance(q, tuple(_dot(rotation[i], p)+translation[i]
                                    for i in range(3)))
                 for p, q in zip(native, repaired)]
    result = _errors(residuals)
    result["determinant"] = (
        rotation[0][0]*(rotation[1][1]*rotation[2][2]-rotation[1][2]*rotation[2][1])
        - rotation[0][1]*(rotation[1][0]*rotation[2][2]-rotation[1][2]*rotation[2][0])
        + rotation[0][2]*(rotation[1][0]*rotation[2][1]-rotation[1][1]*rotation[2][0]))
    return result


def _face_area(points, corner):
    face = corner // 3
    a, b, c = points[3*face:3*face+3]
    u = tuple(b[i]-a[i] for i in range(3))
    v = tuple(c[i]-a[i] for i in range(3))
    cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2],
             u[0]*v[1]-u[1]*v[0])
    return math.sqrt(_dot(cross, cross))/2


def compare_arrays(native_positions, repaired_positions,
                   native_normals, repaired_normals,
                   native_world, repaired_world, native_local, repaired_local):
    """Compare ordered triangle corners; never infer behavior from a digest."""
    pn = _points(native_positions, "native position")
    pr = _points(repaired_positions, "repaired position")
    nn = _points(native_normals, "native normal")
    nr = _points(repaired_normals, "repaired normal")
    _require(len(pn) == len(pr) == len(nn) == len(nr),
             "blade position/normal corner count differs")
    wn = _matrix(native_world, "native world matrix")
    wr = _matrix(repaired_world, "repaired world matrix")
    ln = _matrix(native_local, "native local matrix")
    lr = _matrix(repaired_local, "repaired local matrix")
    compensation = _matmul(_inverse_affine(wr), wn)
    identity = tuple(tuple(float(i == j) for j in range(4))
                     for i in range(4))
    local = [_distance(a, b) for a, b in zip(pn, pr)]
    expected_local = [_distance(_transform(compensation, a), b)
                      for a, b in zip(pn, pr)]
    world = [_distance(_transform(wn, a), _transform(wr, b))
             for a, b in zip(pn, pr)]
    normals_native = [_unit(v) for v in nn]
    normals_repaired = [_unit(v) for v in nr]
    angles = [math.degrees(math.acos(max(-1.0, min(1.0,
              _dot(_normal_transform(compensation, a), b)))))
              for a, b in zip(normals_native, normals_repaired)]
    worst = max(range(len(angles)), key=lambda i: angles[i])
    pair_error = -1.0
    pair = (0, 0)
    pair_dots = (1.0, 1.0)
    for i in range(len(pn)):
        for j in range(i+1, len(pn)):
            before = _dot(normals_native[i], normals_native[j])
            after = _dot(normals_repaired[i], normals_repaired[j])
            delta = abs(before-after)
            if delta > pair_error:
                pair_error, pair, pair_dots = delta, (i, j), (before, after)
    _require(pair_error >= 0, "normal pair coverage differs")
    return {
        "corners": len(pn),
        "worldMatrixMaxElementDifference": max(
            abs(wn[i][j]-wr[i][j]) for i in range(4) for j in range(4)),
        "localMatrixMaxElementDifference": max(
            abs(ln[i][j]-lr[i][j]) for i in range(4) for j in range(4)),
        "compensationMaxFromIdentity": max(
            abs(compensation[i][j]-identity[i][j])
            for i in range(4) for j in range(4)),
        "localPositions": _errors(local),
        "parentCompensatedLocalPositions": _errors(expected_local),
        "worldPositions": _errors(world),
        "properRigidFit": _proper_rigid_fit(pn, pr),
        "normals": {
            "maxAngleDegrees": max(angles),
            "over0p1Degrees": sum(a > NORMAL_ANGLE_DEGREES for a in angles),
            "over1Degree": sum(a > 1.0 for a in angles),
            "worstCorner": worst,
            "worstNative": list(nn[worst]),
            "worstRepaired": list(nr[worst]),
            "worstTriangleNativeArea": _face_area(pn, worst),
            "worstTriangleRepairedArea": _face_area(pr, worst),
            "pairwiseDotMaxDifference": pair_error,
            "pairwiseDotWitness": list(pair),
            "pairwiseDotNative": pair_dots[0],
            "pairwiseDotRepaired": pair_dots[1],
        },
    }


def _aggregate(rows):
    corners = sum(row["corners"] for row in rows)
    _require(corners == EXPECTED_CORNERS, "blade corner coverage differs")
    def combined(key):
        values = [row[key] for row in rows]
        return {"max": max(item["max"] for item in values),
                "rms": math.sqrt(sum(item["rms"]**2 * row["corners"]
                                     for item, row in zip(values, rows))/corners)}
    return {
        "corners": corners,
        "worldMatrixMaxElementDifference": max(
            row["worldMatrixMaxElementDifference"] for row in rows),
        "localPositions": combined("localPositions"),
        "parentCompensatedLocalPositions": combined(
            "parentCompensatedLocalPositions"),
        "worldPositions": combined("worldPositions"),
        "properRigidFitMax": max(row["properRigidFit"]["max"] for row in rows),
        "properRigidFitRms": math.sqrt(sum(
            row["properRigidFit"]["rms"]**2 * row["corners"]
            for row in rows)/corners),
        "positionRowsWithinTolerance": sum(
            row["parentCompensatedLocalPositions"]["max"] <= POSITION_TOLERANCE
            for row in rows),
        "normalCornersOver0p1Degrees": sum(
            row["normals"]["over0p1Degrees"] for row in rows),
        "normalCornersOver1Degree": sum(
            row["normals"]["over1Degree"] for row in rows),
        "normalRowsOver0p1Degrees": sum(
            row["normals"]["over0p1Degrees"] > 0 for row in rows),
        "maxNormalAngleDegrees": max(
            row["normals"]["maxAngleDegrees"] for row in rows),
        "maxNormalPairwiseDotDifference": max(
            row["normals"]["pairwiseDotMaxDifference"] for row in rows),
    }


def parse_result(stdout: str, *, native_sha: str, blender_sha: str,
                 worker_sha: str, host_sha: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    _require(len(matches) == 1 and len(matches[0]) <= MAX_JSON_BYTES,
             "one bounded geometry result required")
    result = json.loads(matches[0])
    expected = {"schemaVersion": 1, "asset": "cat_d11t",
                "nativeUsfSha256": native_sha,
                "repairedUsfSha256": USF_SHA256,
                "blenderSha256": blender_sha, "workerSha256": worker_sha,
                "hostSha256": host_sha,
                "nativeBlendExportApproved": False,
                "blendSaved": False, "usfExported": False,
                "equivalenceVerified": False}
    _require(isinstance(result, dict) and all(
        result.get(key) == value and type(result.get(key)) is type(value)
        for key, value in expected.items()), "identity or no-write gate differs")
    rows = result.get("rows")
    _require(isinstance(rows, list) and len(rows) == len(LEAVES),
             "blade row coverage differs")
    for leaf, row in zip(LEAVES, rows):
        _require(isinstance(row, dict) and row.get("leafName") == leaf and
                 row.get("nativePath") == NATIVE_PARENT + "|" + leaf and
                 row.get("repairedPath") == REPAIRED_PARENT + "|" + leaf,
                 "blade exact-path mapping differs")
    _require(result.get("summary") == _aggregate(rows),
             "geometry aggregate contradicts rows")
    return result


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 600) -> dict:
    _require(type(timeout_seconds) is int and timeout_seconds > 0,
             "timeout must be positive")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    _require(inventory_ref["sha256"] == INVENTORY_SHA256,
             "authoring inventory pin differs")
    inventory_path = _unlinked_path(registry.parent / inventory_ref["path"],
                                    "authoring inventory")
    _require(inventory_path.is_relative_to(registry.parent),
             "authoring inventory outside checkout")
    inventory, source_root, asset, blend, repaired = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, USF_SHA256, "repaired USF")
    worklist = require_hash(WORKLIST, WORKLIST_SHA256, "worklist")
    rows, native, native_sha, summary_path, summary_sha = _rows_and_native(
        json.loads(worklist.read_text(encoding="utf-8")), asset["assetDigest"],
        blend, repaired)
    _require(len(rows) == len(LEAVES), "blade worklist coverage differs")
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    _require(blender_sha in BLENDER_VERSION_PINS,
             "Blender executable is not reviewed")
    sdk = require_sdk_pins(sdk_script_root)
    worker = require_hash(WORKER, WORKER_SHA256, "geometry worker")
    host_sha = file_sha256(Path(__file__))
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--native-usf", str(native),
               "--repaired-usf", str(repaired), "--sdk-script-root", str(sdk),
               "--native-usf-sha256", native_sha,
               "--blender-sha256", blender_sha, "--worker-sha256", WORKER_SHA256,
               "--host-sha256", host_sha]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise BladeGeometryError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout, native_sha=native_sha,
                          blender_sha=blender_sha, worker_sha=WORKER_SHA256,
                          host_sha=host_sha)
    for path, digest, label in (
            (registry, registry_sha, "registry"),
            (inventory_path, INVENTORY_SHA256, "authoring inventory"),
            (blend, BLEND_SHA256, "source Blend"),
            (repaired, USF_SHA256, "repaired USF"),
            (native, native_sha, "native USF"),
            (worklist, WORKLIST_SHA256, "worklist"),
            (summary_path, summary_sha, "parity summary"),
            (blender, blender_sha, "Blender executable"),
            (worker, WORKER_SHA256, "geometry worker"),
            (Path(__file__), host_sha, "geometry host")):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    _require(_unlinked_path(Path(inventory["sourceRoot"]),
                            "source root after readback") == source_root,
             "source root changed")
    result.update({"inventorySha256": INVENTORY_SHA256,
                   "worklistSha256": WORKLIST_SHA256,
                   "summarySha256": summary_sha,
                   "sourceBlendSha256": BLEND_SHA256,
                   "sourceUnchanged": True, "sdkUnchanged": True,
                   "nativeUsfUnchanged": True})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path,
                        default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--summary-only", action="store_true",
                        help="show totals and normal outlier rows after full validation")
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (BladeGeometryError, BladeRelocationError, LeftPushProbeError,
            BlenderAuthoringError, OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR", "error": str(exc),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    if args.summary_only:
        compact = {key: value for key, value in result.items() if key != "rows"}
        compact["normalOutlierRows"] = [
            {"leafName": row["leafName"], "corners": row["corners"],
             "worldPositions": row["worldPositions"],
             "properRigidFit": row["properRigidFit"],
             "normals": row["normals"]}
            for row in result["rows"]
            if row["normals"]["over0p1Degrees"] > 0]
        print(json.dumps(compact, sort_keys=True))
    else:
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
