"""Read-only, source-pinned D11 left push-arm hierarchy diagnostic.

This command launches Blender in the background to edit one bone *in memory*.
It neither saves the Blend nor exports a USF.  Its result is JSON on stdout;
it cannot approve the native-Blend build route.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys

from .blender_authoring import BlenderAuthoringError, _pinned_asset
from .source import file_sha256


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).with_name("blender_left_push_worker.py")
WORKER_SHA256 = "7a1a56a04c8946c115f33292dc8d47c6ee60d4b4032a45ee0574da4d756ea67b"
INVENTORY_SHA256 = "03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d"
BLEND_SHA256 = "1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731"
USF_SHA256 = "49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170"
BLENDER_SHA256 = "e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7"
SDK_PINS = {
    "saber/__init__.py": "b8fc2d9ea0c7c919f124a0774a783e8c641684c1dd95615c8e2239e5250054c3",
    "saber/blender/__init__.py": "3c2227f61523edf9627a09c4539c121fabd612abe983c44482026c0f1cc8b56c",
    "saber/blender/lib/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "saber/blender/lib/binary_io.py": "b0f48e355b0c6a5c1038f948661ec8a6f46b34b369b174bf7ba0ad53474938cf",
    "saber/blender/lib/trifles.py": "f6fa4a8016a2cfc7f256a6dd642a2f8ac1b4dcc924dd9d06cf108f4c6ea92a14",
    "saber/blender/lib/usf/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "saber/blender/lib/usf/animation.py": "5aabb249c2bcecf82c229602f81538d3590011753733e9717d9c55706604f76f",
    "saber/blender/lib/usf/export.py": "b5ac27895463abce897d15d7da6b0feb92b9419190b3f5af5010460166997a83",
    "saber/blender/lib/usf/material.py": "dca9f8356ea24a30ba39be6947cf90ef37afddab1fbf669fa04f4fc450113d65",
    "saber/blender/lib/usf/mesh.py": "4ab671128044524524028dbea32a5c7dcaf5274630348de151592c87b08be337",
    "saber/blender/lib/usf/misc.py": "301d79c7e98edee58da0c4e77229524291968ce504a99be07dc76e1a09358a1c",
    "saber/blender/lib/usf/node.py": "a3849da13777e5a89c7951cba23b8fb2f4991bba18205e2c0ce466ae49417797",
    "saber/blender/lib/usf/scene.py": "386567f324799274fc7b1ab6c3c92898b19d0d04de6f072ab5b4a47001c551fd",
    "saber/blender/lib/usf/transform.py": "c79cd0947590abf36bd23c590e642ee69d2c93fb9d042f944b7a2bdc857d0101",
}
RESULT_PREFIX = "ROADCRAFT_LEFT_PUSH_PROBE "


class LeftPushProbeError(RuntimeError):
    """The narrowly pinned, read-only diagnostic cannot safely proceed."""


def _unlinked_path(path: Path, label: str) -> Path:
    """Check lexical components before resolving any reparse point or link."""
    raw = path.expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    if ".." in raw.parts:
        raise LeftPushProbeError(f"{label} path contains parent traversal")
    cursor = Path(raw.parts[0])
    for component in ("", *raw.parts[1:]):
        if component:
            cursor = cursor / component
        info = cursor.lstat()
        attributes = getattr(info, "st_file_attributes", 0)
        is_junction = getattr(cursor, "is_junction", None)
        if (cursor.is_symlink() or
                (callable(is_junction) and is_junction()) or
                attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
            raise LeftPushProbeError(f"{label} path crosses a link")
    return raw.resolve(strict=True)


def require_hash(path: Path, expected: str, label: str) -> Path:
    """Resolve a regular file and reject different bytes before use."""
    path = _unlinked_path(path, label)
    if not path.is_file() or file_sha256(path) != expected:
        raise LeftPushProbeError(f"{label} differs from reviewed pin")
    return path


def require_sdk_pins(sdk_root: Path) -> Path:
    root = _unlinked_path(sdk_root, "SDK script root")
    if not root.is_dir():
        raise LeftPushProbeError("SDK script root is missing")
    for relative, digest in SDK_PINS.items():
        require_hash(root / relative, digest, f"SDK {relative}")
    return root


def build_command(blender: Path, worker: Path, blend: Path, usf: Path,
                  sdk_root: Path) -> list[str]:
    """No output or save/export argument is accepted by the worker."""
    return [str(blender), "--background", "--factory-startup",
            "--disable-autoexec", "--threads", "1", "--python-exit-code", "1",
            "--python", str(worker), "--", "--blend", str(blend),
            "--repaired-usf", str(usf), "--sdk-script-root", str(sdk_root),
            "--worker-sha256", WORKER_SHA256]


def parse_result(stdout: str) -> dict:
    matches = [line[len(RESULT_PREFIX):] for line in stdout.splitlines()
               if line.startswith(RESULT_PREFIX)]
    if len(matches) != 1:
        raise LeftPushProbeError("Blender did not emit one diagnostic result")
    try:
        result = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise LeftPushProbeError("Blender result is malformed") from exc
    if not isinstance(result, dict) or result.get("schemaVersion") != 1:
        raise LeftPushProbeError("Blender result schema differs")
    _validate_result(result)
    return result


def _validate_result(result: dict) -> None:
    """Do not turn a partial or forged worker line into a parity claim."""
    expected = {
        "asset": "cat_d11t",
        "blendSha256": BLEND_SHA256,
        "repairedUsfSha256": USF_SHA256,
        "repairedPath": ("|@root|D11T_Rig.005|BoneChassis_cdt|"
                         "BoneBladeLift_cdt|IK_push_arm_left_base"),
        "newBoneEditLength": 0.25,
        "editLengthFromUsf": False,
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
    }
    if any(type(result.get(key)) is not type(value) or result.get(key) != value
           for key, value in expected.items()):
        raise LeftPushProbeError("Blender result identity or no-write fields differ")
    if (not isinstance(result.get("blenderVersion"), str) or
            not result["blenderVersion"].startswith("5.2.")):
        raise LeftPushProbeError("Blender result version differs")
    old_chain = ["BoneChassis_cdt", "BoneBladeLift_cdt", "IK_tilt_left_base"]
    expected_chain = ["BoneChassis_cdt", "BoneBladeLift_cdt",
                      "IK_push_arm_left_base", "IK_tilt_left_base"]
    chain = result.get("newTiltBaseChain")
    children = result.get("repairedChildNames")
    if (result.get("oldTiltBaseChain") != old_chain or
            not isinstance(chain, list) or not all(isinstance(name, str) for name in chain) or
            not isinstance(children, list) or
            children != ["IK_push_arm_left_tip", "IK_tilt_left_base"]):
        raise LeftPushProbeError("Blender result hierarchy differs")
    metric_names = ("newBoneWorldMatrixMaxError", "tiltBasePoseMatrixMaxChange",
                    "tiltTipPoseMatrixMaxChange")
    values = [result.get(name) for name in metric_names]
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
           for value in values):
        raise LeftPushProbeError("Blender result matrix metric is invalid")
    matches = chain == expected_chain and all(value <= 1e-5 for value in values)
    status = ("IN_MEMORY_STATIC_PATH_MATCH" if matches else
              "IN_MEMORY_STATIC_PATH_DIFFERENT")
    if result.get("status") != status:
        raise LeftPushProbeError("Blender result status conflicts with hierarchy or metrics")


def run_probe(*, registry_path: Path, blender_executable: Path,
              sdk_script_root: Path, timeout_seconds: int = 300) -> dict:
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds < 1:
        raise LeftPushProbeError("timeout must be a positive integer")
    registry = _unlinked_path(registry_path, "registry")
    registry_sha = file_sha256(registry)
    config = json.loads(registry.read_text(encoding="utf-8"))
    inventory_ref = config["accepted"]["authoringInventory"]
    if inventory_ref["sha256"] != INVENTORY_SHA256:
        raise LeftPushProbeError("accepted authoring inventory pin differs")
    inventory_raw = registry.parent / inventory_ref["path"]
    inventory_path = _unlinked_path(inventory_raw, "authoring inventory")
    if not inventory_path.is_relative_to(registry.parent):
        raise LeftPushProbeError("authoring inventory is outside registry checkout")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    source_root = _unlinked_path(Path(inventory["sourceRoot"]),
                                 "authoring source root")
    _, pinned_root, _, blend, usf = _pinned_asset(
        inventory_path, INVENTORY_SHA256, "cat_d11t")
    if pinned_root != source_root:
        raise LeftPushProbeError("authoring source root changed during validation")
    require_hash(blend, BLEND_SHA256, "source Blend")
    require_hash(usf, USF_SHA256, "repaired USF")
    blender = require_hash(blender_executable, BLENDER_SHA256, "Blender executable")
    sdk = require_sdk_pins(sdk_script_root)
    worker = require_hash(WORKER, WORKER_SHA256, "diagnostic worker")
    worker_sha = WORKER_SHA256
    command = build_command(blender, worker, blend, usf, sdk)
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, capture_output=True, text=True,
                               errors="replace", timeout=timeout_seconds,
                               env=environment, check=False,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode != 0:
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-12:])
        raise LeftPushProbeError(f"Blender exited {completed.returncode}: {tail}")
    result = parse_result(completed.stdout)
    require_hash(registry_path, registry_sha, "registry after diagnostic")
    require_hash(inventory_raw, INVENTORY_SHA256,
                 "authoring inventory after diagnostic")
    if _unlinked_path(Path(inventory["sourceRoot"]),
                      "authoring source root after diagnostic") != source_root:
        raise LeftPushProbeError("authoring source root changed during diagnostic")
    require_hash(blend, BLEND_SHA256, "source Blend after diagnostic")
    require_hash(usf, USF_SHA256, "repaired USF after diagnostic")
    require_sdk_pins(sdk_script_root)
    require_hash(blender_executable, BLENDER_SHA256, "Blender executable after diagnostic")
    require_hash(WORKER, WORKER_SHA256, "diagnostic worker after run")
    if result.get("status") not in {"IN_MEMORY_STATIC_PATH_MATCH", "IN_MEMORY_STATIC_PATH_DIFFERENT"}:
        raise LeftPushProbeError("Blender reported an invalid diagnostic status")
    result.update({"sourceUnchanged": True, "sdkUnchanged": True,
                   "workerSha256": worker_sha,
                   "inventorySha256": INVENTORY_SHA256,
                   "blenderSha256": BLENDER_SHA256,
                   "nativeBlendExportApproved": False})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=TOOLCHAIN_ROOT / "project.json")
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--sdk-script-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        result = run_probe(registry_path=args.registry, blender_executable=args.blender,
                           sdk_script_root=args.sdk_script_root,
                           timeout_seconds=args.timeout_seconds)
    except (LeftPushProbeError, BlenderAuthoringError, OSError, ValueError,
            KeyError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"schemaVersion": 1, "status": "ERROR",
                          "error": str(exc), "nativeBlendExportApproved": False},
                         sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
