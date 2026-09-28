"""Source-pinned, no-save comparison of accepted D11 repaired rig targets."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess

from .blender_authoring import BlenderAuthoringError, _pinned_asset
from .blender_armature_parity import BLENDER_VERSION_PINS
from .blender_left_push_probe import (
    BLEND_SHA256, INVENTORY_SHA256, LeftPushProbeError,
    _unlinked_path, require_hash, require_sdk_pins,
)
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_variant_structural_targets_worker.py")
WORKER_SHA256 = "7f4170919ca0549df4e9e769b995aebd0446fb35b857327d8eaca47ea6455a8e"
RESULT_PREFIX = "ROADCRAFT_VARIANT_STRUCTURAL_TARGETS "
ASSET_USF_SHA256 = {
    "cat_d11t": "49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170",
    "cat_d11t_v2": "096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a",
    "cat_d11t_v3": "1346b73da9cf72b6e866a722d929fd5c18305537f9ef3acd369f84ea808993d1",
}
EXPECTED_DIGEST = "d2694db5513e19b3e6e23527b280f7bb46a4b724c0c3268bf171c95dd92e4369"


class VariantStructuralError(RuntimeError):
    """The pinned structural comparison or its result cannot be trusted."""


def validate_result(value: object, blender_sha256: str) -> dict:
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise VariantStructuralError("Blender result schema differs")
    expected = {
        "blendSha256": BLEND_SHA256,
        "blenderSha256": blender_sha256,
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if any(type(value.get(key)) is not type(item) or value.get(key) != item
           for key, item in expected.items()):
        raise VariantStructuralError("Blender identity or no-write fields differ")
    if (blender_sha256 not in BLENDER_VERSION_PINS or
            not isinstance(value.get("blenderVersion"), str) or
            not value["blenderVersion"].startswith(
                BLENDER_VERSION_PINS[blender_sha256])):
        raise VariantStructuralError("Blender version differs")
    rows = value.get("rows")
    if (not isinstance(rows, list) or len(rows) != 3 or
            [row.get("asset") for row in rows if isinstance(row, dict)] !=
            list(ASSET_USF_SHA256)):
        raise VariantStructuralError("three-asset roster differs")
    identical = True
    for row in rows:
        asset = row["asset"]
        if row.get("repairedUsfSha256") != ASSET_USF_SHA256[asset]:
            raise VariantStructuralError("repaired USF identity differs")
        count = row.get("structuralCount")
        shared = row.get("sharedWithBase")
        if (type(count) is not int or count < 0 or
                type(shared) is not int or shared < 0 or shared > count):
            raise VariantStructuralError("structural coverage is invalid")
        for key in ("baseOnlyPaths", "variantOnlyPaths",
                    "matrixDifferentPathsOver1e5",
                    "animationOrChildRosterDifferentPaths"):
            if (not isinstance(row.get(key), list) or
                    any(not isinstance(path, str) for path in row[key])):
                raise VariantStructuralError("structural difference roster is invalid")
        error = row.get("maxMatrixElementError")
        if (type(error) not in (int, float) or not math.isfinite(error) or
                error < 0):
            raise VariantStructuralError("matrix measurement is invalid")
        digest = row.get("structuralDigest")
        if not isinstance(digest, str) or len(digest) != 64:
            raise VariantStructuralError("structural digest is invalid")
        identical &= (count == 400 and shared == 400 and
                      row["baseOnlyPaths"] == [] and
                      row["variantOnlyPaths"] == [] and
                      row["matrixDifferentPathsOver1e5"] == [] and
                      error == 0 and
                      row["animationOrChildRosterDifferentPaths"] == [] and
                      digest == EXPECTED_DIGEST)
    status = ("REPAIRED_VARIANT_STRUCTURES_IDENTICAL" if identical else
              "REPAIRED_VARIANT_STRUCTURES_DIFFERENT")
    if value.get("status") != status:
        raise VariantStructuralError("Blender status contradicts structural measurements")
    return value


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 300) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise VariantStructuralError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise VariantStructuralError("accepted inventory pin differs")
    inventory_raw = registry.parent / inventory_ref["path"]
    inventory_path = _unlinked_path(inventory_raw, "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise VariantStructuralError("authoring inventory is outside registry checkout")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    source_root = _unlinked_path(Path(inventory["sourceRoot"]),
                                 "authoring source root")
    assets = []
    for name, sha in ASSET_USF_SHA256.items():
        _, pinned_root, _, blend, usf = _pinned_asset(
            inventory_path, INVENTORY_SHA256, name)
        if pinned_root != source_root:
            raise VariantStructuralError("authoring root changed during validation")
        require_hash(blend, BLEND_SHA256, name + " source Blend")
        require_hash(usf, sha, name + " repaired USF")
        assets.append((name, blend, usf, sha))
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise VariantStructuralError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    worker = require_hash(WORKER, WORKER_SHA256, "variant worker")
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--blend", str(assets[0][1]),
               "--sdk-script-root", str(sdk),
               "--worker-sha256", WORKER_SHA256,
               "--blender-sha256", blender_sha]
    for _, _, usf, _ in assets:
        command.extend(("--usf", str(usf)))
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command, capture_output=True, text=True, errors="replace",
        timeout=timeout_seconds, env=environment, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise VariantStructuralError(f"Blender exited {completed.returncode}: {tail}")
    lines = [line[len(RESULT_PREFIX):] for line in completed.stdout.splitlines()
             if line.startswith(RESULT_PREFIX)]
    if len(lines) != 1:
        raise VariantStructuralError("Blender did not emit one structural result")
    result = validate_result(json.loads(lines[0]), blender_sha)
    require_hash(registry, registry_sha, "registry after diagnostic")
    require_hash(inventory_raw, INVENTORY_SHA256,
                 "authoring inventory after diagnostic")
    if _unlinked_path(Path(inventory["sourceRoot"]),
                      "authoring source root after diagnostic") != source_root:
        raise VariantStructuralError("authoring root changed during diagnostic")
    for name, blend, usf, sha in assets:
        require_hash(blend, BLEND_SHA256, name + " source Blend after diagnostic")
        require_hash(usf, sha, name + " repaired USF after diagnostic")
    require_sdk_pins(sdk)
    require_hash(blender, blender_sha, "Blender executable after diagnostic")
    require_hash(worker, WORKER_SHA256, "variant worker after diagnostic")
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "workerSha256": WORKER_SHA256,
                   "inventorySha256": INVENTORY_SHA256})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path,
                        default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (VariantStructuralError, LeftPushProbeError, BlenderAuthoringError,
            OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(error),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "REPAIRED_VARIANT_STRUCTURES_IDENTICAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
