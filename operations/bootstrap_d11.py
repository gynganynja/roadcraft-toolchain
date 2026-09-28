"""Pin the reviewed D11 snapshot without changing its source or installed mod.

Run once after verifying the accepted installation receipt.  Existing output
files are never overwritten; a new accepted revision needs an explicit review.
"""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import sys


TOOLCHAIN = Path(__file__).resolve().parents[1]
WORKSPACE = TOOLCHAIN.parent
sys.path.insert(0, str(TOOLCHAIN / "src"))

from roadcraft.core import sha256_file  # noqa: E402
from roadcraft.manifest import capture_tree_manifest  # noqa: E402
from roadcraft.source import capture_source_inventory  # noqa: E402


ACCEPTED_SHA = "3e3d21b877ad6e52c61de7665a90fe3a9e4dd3761c0f3115fc734938caf4aa16"
CANDIDATE_SHA = "3b4129d22b8a79bf1969ee7effd8d92b699beae1aa6a33deebb658cd2ade6031"
RECEIPT_SHA = "40fe7ad060aa95f7d23bd17331716017a24cc3951915fef15c52a1d9e73b2b8e"


def write_new(path: Path, value: dict) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to replace an existing baseline: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temp = path.with_name(path.name + ".tmp")
    if temp.exists():
        raise FileExistsError(f"Stale temporary output needs inspection: {temp}")
    try:
        with temp.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def main() -> None:
    source = WORKSPACE / "D11_Interior_Standalone_20260927" / "p"
    accepted = WORKSPACE / "D11_Interior_Standalone_20260927" / "build" / "retail" / "cat_d11t_standalone_interior_candidate.pak"
    candidate = WORKSPACE / "D11_Interior_AAA_20260928" / "build" / "retail" / "cat_d11t_aaa_candidate.pak"
    receipt = WORKSPACE / "D11_Interior_AAA_20260928" / "build" / "package_receipt.json"
    for name, path, expected in (("accepted", accepted, ACCEPTED_SHA),
                                 ("candidate", candidate, CANDIDATE_SHA),
                                 ("candidate receipt", receipt, RECEIPT_SHA)):
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"{name} changed: expected {expected}, observed {actual}")
    manifest_path = TOOLCHAIN / "operations" / "d11_accepted_source_manifest.json"
    inventory_path = TOOLCHAIN / "operations" / "d11_authoring_inventory.json"
    registry_path = TOOLCHAIN / "project.json"
    machine_path = TOOLCHAIN / "local" / "machine.json"
    for path in (manifest_path, inventory_path, registry_path, machine_path):
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite {path}")

    manifest = capture_tree_manifest(source, [".project", "config", "mods_source"])
    write_new(manifest_path, manifest)
    assets = []
    for variant in ("cat_d11t", "cat_d11t_v2", "cat_d11t_v3"):
        directory = source / "mods_source" / "models" / "mods" / f"{variant}.tpl.asset"
        files = []
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            role = ("build-usf" if path.name == "export.usf" else
                    "blend-reference" if path.suffix.lower() == ".blend" else
                    "export-options" if path.name == "export_options.ps" else
                    "accepted-source")
            files.append({"path": path.relative_to(source).as_posix(), "role": role})
        assets.append({"asset": variant, "exportMethod": "usf-repair", "files": files})
    inventory = capture_source_inventory(source, assets)
    write_new(inventory_path, inventory)

    registry = {
        "schemaVersion": 1,
        "project": "D11",
        "accepted": {
            "package": {"path": str(accepted), "sha256": ACCEPTED_SHA},
            "sourceManifest": {"path": "operations/d11_accepted_source_manifest.json",
                               "sha256": sha256_file(manifest_path)},
            "sourceRoot": str(source),
            "authoringInventory": {"path": "operations/d11_authoring_inventory.json",
                                    "sha256": sha256_file(inventory_path)},
        },
        "candidates": {
            "aaa-20260928": {
                "package": {"path": str(candidate), "sha256": CANDIDATE_SHA},
                "receipt": {"path": str(receipt), "sha256": RECEIPT_SHA},
            }
        },
        "variants": ["maroon", "nearnew", "worn"],
        "recipes": {},
    }
    write_new(registry_path, registry)
    sdk_tools = WORKSPACE.parent / "tools" / "bin"
    machine = {
        "schemaVersion": 1,
        "sdkRoot": str(WORKSPACE),
        "installedPackage": str(WORKSPACE.parent / "root" / "mods" / "cat_d11t.pak"),
        "tools": {
            "integrationStudio": str(sdk_tools / "ModEditor" / "IntegrationStudio.exe"),
            "furnace": str(sdk_tools / "ResourceTools" / "furnace" / "furnace.exe"),
            "modPakBuilder": str(sdk_tools / "ModPakBuilder" / "mod_pak_builder.exe"),
        },
        "transactionReceipts": [str(WORKSPACE / "D11_Interior_AAA_20260928" / "native" /
                                    "candidate_capture_bd58bce0.json")],
        "transactionLocks": [str(WORKSPACE / "D11_Interior_AAA_20260928" / "native" /
                                 "candidate_capture.lock.json")],
    }
    write_new(machine_path, machine)
    print(json.dumps({"sourceFiles": len(manifest["files"]),
                      "sourceBytes": sum(row["bytes"] for row in manifest["files"]),
                      "sourceManifestSha256": registry["accepted"]["sourceManifest"]["sha256"],
                      "authoringAssets": [row["asset"] for row in inventory["assets"]],
                      "acceptedSha256": ACCEPTED_SHA, "candidateSha256": CANDIDATE_SHA}))


if __name__ == "__main__":
    main()
