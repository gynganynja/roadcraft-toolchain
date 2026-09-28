"""Pinned, no-save D11 v2/v3 source/repaired/native animation readback."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from .blender_animation_payload import (
    AnimationPayloadError, _canonical, compare_records,
)
from .blender_authoring import BlenderAuthoringError, _pinned_asset
from .blender_left_push_probe import (
    INVENTORY_SHA256, LeftPushProbeError, _unlinked_path, require_hash,
    require_sdk_pins,
)
from .blender_mesh_inventory import (
    BLEND_SHA256, BLENDER_VERSION_PINS, WORKLIST, WORKLIST_SHA256,
    MeshInventoryError,
)
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_animation_variants_worker.py")
WORKER_SHA256 = "b830e8089c748d6724eddf107e3c2feb276e76457f625d36169320aee62cd1ec"
BASE_HOST = Path(__file__).with_name("blender_animation_payload.py")
BASE_HOST_SHA256 = "729c5a9ca1056b58044dd7497cc2b48d30bda0a37af6ed7127be56360725d997"
BASE_WORKER = Path(__file__).with_name("blender_animation_payload_worker.py")
BASE_WORKER_SHA256 = "d464ccf0656ed848bb49df1640fa54d31644c0bccf1f2f11ad17caff536769ab"
RESULT_PREFIX = "ROADCRAFT_ANIMATION_VARIANTS "
MAX_JSON_BYTES = 128 * 1024
VARIANTS = {
    "cat_d11t_v2": {
        "repairedSha256": "096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a",
        "nativeSha256": "0e533bbc80a95798824e69e5c6545cc50b9d98f0ba81e7f0e96d9e3a93c2dc3f",
        "summarySha256": "ffcc6bb774911f0f1e7a1d865cb2b113f88305a07a2e4aef2f4e5aff07814dc0",
        "sourceAssetDigest": "6f6d47667c5dd24aa18fa1734aa2cbc7c6af48ac28bc57c67e8609f899f22d6f",
    },
    "cat_d11t_v3": {
        "repairedSha256": "1346b73da9cf72b6e866a722d929fd5c18305537f9ef3acd369f84ea808993d1",
        "nativeSha256": "bdd562bafeef47644e998cad413e246f10ff0d13bf172cf18d75cdf032e6cc13",
        "summarySha256": "c7d28c2f630eadd51cb042150c3162c4f5da811d02e59897e9c0314d6ae058a0",
        "sourceAssetDigest": "7c3588072e21e5aa8944d136491ebc26e9dace14ab47929bd8672a75ffbac0e7",
    },
}


def interpret_readback(result: object, asset: str, blender_sha: str,
                       host_sha: str) -> dict:
    if asset not in VARIANTS:
        raise AnimationPayloadError("unreviewed animation variant")
    pins = VARIANTS[asset]
    expected = {
        "schemaVersion": 1, "asset": asset,
        "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": pins["repairedSha256"],
        "nativeExportUsfSha256": pins["nativeSha256"],
        "summarySha256": pins["summarySha256"],
        "sourceAssetDigest": pins["sourceAssetDigest"],
        "worklistSha256": WORKLIST_SHA256,
        "blenderSha256": blender_sha,
        "hostSha256": host_sha,
        "workerSha256": WORKER_SHA256,
        "baseHostSha256": BASE_HOST_SHA256,
        "baseWorkerSha256": BASE_WORKER_SHA256,
        "repairedRootName": "cat_d11t",
        "nativeRootName": asset,
        "blendSaved": False, "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if (not isinstance(result, dict) or
            set(result) != set(expected) | {
                "blenderVersion", "sourceActions", "repaired", "native"} or
            any(type(result.get(key)) is not type(value) or
                result.get(key) != value for key, value in expected.items()) or
            blender_sha not in BLENDER_VERSION_PINS or
            not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith(BLENDER_VERSION_PINS[blender_sha])):
        raise AnimationPayloadError("variant animation identity or no-write fields differ")
    if (not isinstance(result["repaired"], dict) or
            result["repaired"].get("actorName") != "cat_d11t" or
            not isinstance(result["native"], dict) or
            result["native"].get("actorName") != asset):
        raise AnimationPayloadError("variant actor roots differ")
    native_for_comparison = dict(result["native"])
    native_for_comparison["actorName"] = "cat_d11t"
    comparison = compare_records(result["sourceActions"],
                                 result["repaired"], native_for_comparison)
    payload = {key: result[key] for key in expected}
    payload.update({
        "status": "SOURCE_REPAIRED_NATIVE_VARIANT_ANIMATION_READBACK",
        "blenderVersion": result["blenderVersion"],
        "comparison": comparison,
        "recordsDigestSha256": hashlib.sha256(_canonical([
            result["sourceActions"], result["repaired"],
            result["native"]])).hexdigest(),
        "sourceActions": result["sourceActions"],
        "repaired": result["repaired"], "native": result["native"],
    })
    if len(_canonical(payload)) > MAX_JSON_BYTES:
        raise AnimationPayloadError("variant animation result exceeded bound")
    return payload


def _inputs(registry_path: Path, asset_name: str) -> dict:
    pins = VARIANTS[asset_name]
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise AnimationPayloadError("accepted inventory pin differs")
    inventory_path = _unlinked_path(registry.parent / inventory_ref["path"],
                                    "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise AnimationPayloadError("inventory path is outside checkout")
    inventory, source_root, asset, blend, repaired = _pinned_asset(
        inventory_path, INVENTORY_SHA256, asset_name)
    if asset["assetDigest"] != pins["sourceAssetDigest"]:
        raise AnimationPayloadError("source asset digest differs")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(repaired, pins["repairedSha256"], "repaired USF")
    worklist = require_hash(WORKLIST, WORKLIST_SHA256, "reconstruction worklist")
    work = json.loads(worklist.read_text(encoding="utf-8"))
    if (work.get("schemaVersion") != 1 or
            work.get("status") != "RECONSTRUCTION_REQUIRED" or
            work.get("inventorySha256") != INVENTORY_SHA256 or
            work.get("nativeBlendExportApproved") is not False):
        raise AnimationPayloadError("reconstruction worklist identity differs")
    matches = [row for row in work["assets"] if row.get("asset") == asset_name]
    if len(matches) != 1:
        raise AnimationPayloadError("variant worklist row is not unique")
    row = matches[0]
    if (row.get("sourceAssetDigest") != pins["sourceAssetDigest"] or
            row.get("blendSha256") != BLEND_SHA256 or
            row.get("repairedUsfSha256") != pins["repairedSha256"] or
            row.get("scratchNativeUsfSha256") != pins["nativeSha256"] or
            row.get("summarySha256") != pins["summarySha256"] or
            row.get("nativeBlendExportApproved") is not False):
        raise AnimationPayloadError("variant worklist pins differ")
    summary = require_hash(Path(row["summaryPath"]), pins["summarySha256"],
                           "variant parity summary")
    receipt = json.loads(summary.read_text(encoding="utf-8"))
    if (receipt.get("asset") != asset_name or
            receipt.get("blendSha256") != BLEND_SHA256 or
            receipt.get("baselineUsfSha256") != pins["repairedSha256"] or
            receipt.get("candidateUsfSha256") != pins["nativeSha256"] or
            receipt.get("baselineRootName") != "cat_d11t" or
            receipt.get("candidateRootName") != asset_name or
            Path(receipt["blendPath"]) != blend or
            Path(receipt["baselineUsfPath"]) != repaired or
            receipt.get("nativeBlendExportApproved") is not False):
        raise AnimationPayloadError("variant parity summary differs")
    native = require_hash(Path(receipt["candidateUsfPath"]),
                          pins["nativeSha256"], "retained native USF")
    return {"registry": registry, "registrySha": registry_sha,
            "inventory": inventory, "inventoryPath": inventory_path,
            "sourceRoot": source_root, "blend": blend,
            "repaired": repaired, "native": native,
            "worklist": worklist, "summary": summary}


def run_probe(*, asset_name: str, registry_path: Path,
              blender_executable: Path, sdk_script_root: Path,
              timeout_seconds: int = 900) -> dict:
    if asset_name not in VARIANTS:
        raise AnimationPayloadError("unreviewed animation variant")
    if type(timeout_seconds) is not int or timeout_seconds < 1:
        raise AnimationPayloadError("timeout must be a positive integer")
    paths = _inputs(registry_path, asset_name)
    pins = VARIANTS[asset_name]
    blender = _unlinked_path(blender_executable, "Blender executable")
    blender_sha = file_sha256(blender)
    if blender_sha not in BLENDER_VERSION_PINS:
        raise AnimationPayloadError("Blender executable differs from reviewed pins")
    require_hash(blender, blender_sha, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    deps = ((BASE_HOST, BASE_HOST_SHA256, "base animation host"),
            (BASE_WORKER, BASE_WORKER_SHA256, "base animation worker"),
            (WORKER, WORKER_SHA256, "variant animation worker"))
    for path, digest, label in deps:
        require_hash(path, digest, label)
    host_sha = file_sha256(Path(__file__))
    command = [str(blender), "--background", "--factory-startup",
               "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
               "--python", str(WORKER), "--",
               "--asset", asset_name,
               "--blend", str(paths["blend"]),
               "--repaired-usf", str(paths["repaired"]),
               "--native-usf", str(paths["native"]),
               "--worklist", str(paths["worklist"]),
               "--summary", str(paths["summary"]),
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
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise AnimationPayloadError(f"Blender exited {completed.returncode}: {tail}")
    matches = [line[len(RESULT_PREFIX):] for line in completed.stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1 or len(matches[0]) > MAX_JSON_BYTES:
        raise AnimationPayloadError("Blender did not emit one bounded variant readback")
    result = interpret_readback(json.loads(matches[0]), asset_name,
                                blender_sha, host_sha)
    require_hash(paths["registry"], paths["registrySha"],
                 "registry after readback")
    require_hash(paths["inventoryPath"], INVENTORY_SHA256,
                 "inventory after readback")
    if _unlinked_path(Path(paths["inventory"]["sourceRoot"]),
                      "source root after") != paths["sourceRoot"]:
        raise AnimationPayloadError("source root changed during readback")
    for path, digest, label in (
            (paths["blend"], BLEND_SHA256, "source Blend"),
            (paths["repaired"], pins["repairedSha256"], "repaired USF"),
            (paths["native"], pins["nativeSha256"], "retained native USF"),
            (paths["worklist"], WORKLIST_SHA256, "worklist"),
            (paths["summary"], pins["summarySha256"], "parity summary"),
            (blender, blender_sha, "Blender executable"),
            (Path(__file__), host_sha, "variant animation host"), *deps):
        require_hash(path, digest, label + " after readback")
    require_sdk_pins(sdk)
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "nativeExportUnchanged": True,
                   "inventorySha256": INVENTORY_SHA256})
    if len(_canonical(result)) > MAX_JSON_BYTES:
        raise AnimationPayloadError("final variant result exceeded bound")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", choices=sorted(VARIANTS), required=True)
    parser.add_argument("--registry", type=Path,
                        default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        result = run_probe(asset_name=args.asset, registry_path=args.registry,
                           blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (AnimationPayloadError, BlenderAuthoringError, LeftPushProbeError,
            MeshInventoryError, OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc),
                          "nativeBlendExportApproved": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
