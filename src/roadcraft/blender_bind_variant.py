"""No-save skin identity/inverse readback for the accepted D11 v2/v3 sources."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from . import blender_bind_identity as base
from . import blender_mesh_variant_inventory as variants
from .blender_left_push_probe import (
    INVENTORY_SHA256, LeftPushProbeError, _unlinked_path, require_hash,
    require_sdk_pins,
)
from .blender_mesh_inventory import WORKLIST, WORKLIST_SHA256
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_bind_variant_worker.py")
WORKER_SHA256 = "967f08b9c46509b9fc7b3491fa4b5ec69b96267645435bc6637a60199ff38c66"
BASE_HOST_SHA256 = "58e2491b5a00b0537cdb658a2b7e455b954cadda5f688b87796fe40f1949bb78"
BASE_WORKER_SHA256 = "b8444c389bfbae5efd0c74ca68623e96db82c144511c65a9584fbe1169f31181"
VARIANT_HOST_SHA256 = "4f0bc0b0dc8312d147b654f95b63b361e3c84c180f807565b6a2bbb06ab073c0"
RESULT_PREFIX = "ROADCRAFT_VARIANT_BIND "
MAX_JSON_BYTES = base.MAX_JSON_BYTES


class VariantBindError(RuntimeError):
    """A variant source or pinned bind readback is incomplete or changed."""


def _asset_inputs(registry_path: Path, asset_name: str) -> dict:
    require_hash(Path(variants.__file__), VARIANT_HOST_SHA256,
                 "variant inventory host")
    pins = variants._pins(asset_name)
    known = variants._variant_inputs(registry_path, asset_name)
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    ref = config["accepted"]["authoringInventory"]
    if ref["sha256"] != INVENTORY_SHA256:
        raise VariantBindError("accepted inventory pin differs")
    inventory = _unlinked_path(registry.parent / ref["path"], "inventory")
    if not inventory.is_relative_to(registry.parent):
        raise VariantBindError("inventory outside checkout")
    worklist = require_hash(WORKLIST, WORKLIST_SHA256, "worklist")
    parsed = json.loads(worklist.read_text(encoding="utf-8"))
    matches = [a for a in parsed["assets"] if a.get("asset") == asset_name]
    if len(matches) != 1:
        raise VariantBindError("variant worklist asset is not unique")
    asset = matches[0]
    if (asset.get("blendSha256") != pins["blendSha256"] or
            asset.get("repairedUsfSha256") != pins["repairedUsfSha256"] or
            asset.get("sourceAssetDigest") != pins["sourceAssetDigest"] or
            asset.get("nativeExportRootName") != asset_name or
            asset.get("repairedRootName") != "cat_d11t" or
            asset.get("nativeBlendExportApproved") is not False):
        raise VariantBindError("variant worklist identity or gate differs")
    summary_sha = asset["summarySha256"]
    summary = require_hash(Path(asset["summaryPath"]), summary_sha,
                           "variant parity summary")
    summary_data = json.loads(summary.read_text(encoding="utf-8"))
    native_sha = asset["scratchNativeUsfSha256"]
    native = require_hash(Path(summary_data["candidateUsfPath"]), native_sha,
                          "variant retained native USF")
    if (summary_data.get("asset") != asset_name or
            summary_data.get("blendPath") != str(known["blend"]) or
            summary_data.get("blendSha256") != pins["blendSha256"] or
            summary_data.get("baselineUsfPath") != str(known["usf"]) or
            summary_data.get("baselineUsfSha256") != pins["repairedUsfSha256"] or
            summary_data.get("candidateUsfSha256") != native_sha or
            summary_data.get("baselineRootName") != "cat_d11t" or
            summary_data.get("candidateRootName") != asset_name or
            summary_data.get("nativeBlendExportApproved") is not False):
        raise VariantBindError("variant summary does not pin its own sources")
    return {
        **known, "registry": registry, "registrySha256": registry_sha,
        "inventory": inventory, "worklist": worklist,
        "summary": summary, "summarySha256": summary_sha,
        "native": native, "nativeSha256": native_sha,
        "assetDigest": pins["sourceAssetDigest"],
        "repairedSha256": pins["repairedUsfSha256"],
    }


def interpret_readback(result: dict, inputs: dict, asset_name: str,
                       blender_sha: str, host_sha: str) -> dict:
    rows = result.get("rows") if isinstance(result, dict) else None
    if (not isinstance(rows, list) or any(
            not isinstance(row, dict) or
            not isinstance(row.get("sourceObject"), str) or
            not row["sourceObject"].strip() for row in rows)):
        raise VariantBindError("variant source object name is missing")
    if (not isinstance(result, dict) or
            result.get("schemaVersion") != 1 or
            result.get("asset") != asset_name or
            result.get("sourceAssetDigest") != inputs["assetDigest"] or
            result.get("blendSha256") != base.BLEND_SHA256 or
            result.get("repairedUsfSha256") != inputs["repairedSha256"] or
            result.get("nativeExportUsfSha256") != inputs["nativeSha256"] or
            result.get("nativeExportRootName") != asset_name or
            result.get("repairedRootName") != "cat_d11t" or
            result.get("nativeBlendExportApproved") is not False):
        raise VariantBindError("variant worker identity, roots or gate differ")
    normalized = dict(result)
    normalized.update({"asset": "cat_d11t",
                       "repairedUsfSha256": base.USF_SHA256,
                       "nativeExportRootName": "cat_d11t"})
    normalized.pop("sourceAssetDigest", None)
    compact = base.interpret_readback(
        normalized, inputs["gapRows"], blender_sha=blender_sha,
        native_sha=inputs["nativeSha256"],
        summary_sha=inputs["summarySha256"], host_sha=host_sha)
    compact.update({"asset": asset_name,
                    "sourceAssetDigest": inputs["assetDigest"],
                    "repairedUsfSha256": inputs["repairedSha256"],
                    "nativeExportRootName": asset_name,
                    "status": "SOURCE_VARIANT_USF_BIND_IDENTITY_READBACK"})
    if len(base.canonical(compact)) > MAX_JSON_BYTES:
        raise VariantBindError("bounded variant bind result exceeded")
    return compact


def run_probe(*, registry_path: Path, asset_name: str,
              blender_executable: Path, sdk_script_root: Path,
              timeout_seconds: int = 900) -> dict:
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise VariantBindError("timeout must be a positive integer")
    variants._pins(asset_name)
    require_hash(Path(base.__file__), BASE_HOST_SHA256, "base bind host")
    base_worker = require_hash(Path(base.__file__).with_name(
        "blender_bind_identity_worker.py"), BASE_WORKER_SHA256,
        "base bind worker")
    inputs = _asset_inputs(registry_path, asset_name)
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in base.BLENDER_VERSION_PINS:
        raise VariantBindError("Blender executable differs from reviewed pins")
    sdk = require_sdk_pins(sdk_script_root)
    mapper = require_hash(base.MAPPER_WORKER, base.MAPPER_WORKER_SHA256,
                          "mesh path mapper")
    worker = require_hash(WORKER, WORKER_SHA256, "variant bind worker")
    host_sha = file_sha256(Path(__file__))
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(worker), "--", "--asset", asset_name,
               "--blend", str(inputs["blend"]),
               "--repaired-usf", str(inputs["usf"]),
               "--native-usf", str(inputs["native"]),
               "--worklist", str(inputs["worklist"]),
               "--summary", str(inputs["summary"]),
               "--sdk-script-root", str(sdk),
               "--worker-sha256", WORKER_SHA256,
               "--host-sha256", host_sha,
               "--blender-sha256", blender_sha]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise VariantBindError(f"Blender exited {completed.returncode}: {tail}")
    lines = [line[len(RESULT_PREFIX):] for line in completed.stdout.splitlines()
             if line.startswith(RESULT_PREFIX)]
    if len(lines) != 1 or len(lines[0]) > MAX_JSON_BYTES:
        raise VariantBindError("Blender did not emit one bounded variant readback")
    result = interpret_readback(json.loads(lines[0]), inputs, asset_name,
                                blender_sha, host_sha)
    again = _asset_inputs(registry_path, asset_name)
    if (inputs["registrySha256"] != again["registrySha256"] or
            inputs["sourceRoot"] != again["sourceRoot"] or
            inputs["blend"] != again["blend"] or
            inputs["usf"] != again["usf"] or
            inputs["native"] != again["native"] or
            inputs["gapRows"] != again["gapRows"]):
        raise VariantBindError("variant inputs changed during readback")
    for path, sha, label in (
            (blender, blender_sha, "Blender"),
            (mapper, base.MAPPER_WORKER_SHA256, "mapper"),
            (base_worker, BASE_WORKER_SHA256, "base worker"),
            (Path(base.__file__), BASE_HOST_SHA256, "base host"),
            (worker, WORKER_SHA256, "variant worker"),
            (Path(__file__), host_sha, "variant host")):
        require_hash(path, sha, label + " after")
    require_sdk_pins(sdk)
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "nativeExportUnchanged": True,
                   "inventorySha256": INVENTORY_SHA256,
                   "workerSha256": WORKER_SHA256})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", choices=tuple(variants.ASSET_PINS), required=True)
    parser.add_argument("--registry", type=Path,
                        default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry, asset_name=args.asset,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (VariantBindError, base.BindIdentityError,
            variants.VariantMeshInventoryError, LeftPushProbeError,
            OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc), "nativeBlendExportApproved": False},
                         sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
