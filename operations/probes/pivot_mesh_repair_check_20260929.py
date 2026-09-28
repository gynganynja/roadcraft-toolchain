"""Run the maintained D11 pivot repair in a disposable, no-save scene."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from roadcraft.blender_pivot_mesh_repair import install_in_memory_pivot
from roadcraft.blender_residual_bones import WORKER_SHA256, validate_result
from roadcraft.blender_residual_bones_worker import run as structural_run


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


inventory_path = ROOT / "operations/d11_authoring_inventory.json"
module_path = ROOT / "src/roadcraft/blender_pivot_mesh_repair.py"
if sha(inventory_path) != "03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d":
    raise RuntimeError("accepted inventory pin differs")
module_sha = "38ad41a614cde117447308a7af5740ff5d04538837642147dd256748c46e60bb"
if sha(module_path) != module_sha:
    raise RuntimeError("pivot repair module pin differs")
inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
asset = next(row for row in inventory["assets"] if row["asset"] == "cat_d11t")
source_root = Path(inventory["sourceRoot"])
blend = source_root / next(row["path"] for row in asset["files"]
                           if row["role"] == "blend-reference")
usf = source_root / next(row["path"] for row in asset["files"]
                         if row["role"] == "build-usf")
sdk = Path(r"C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script")
blender_sha = "e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7"
structural = structural_run(
    blend=blend, usf=usf, sdk_root=sdk,
    worker_sha256=WORKER_SHA256, blender_sha256=blender_sha)
validate_result(structural, blender_sha)
if structural["status"] != "IN_MEMORY_STRUCTURAL_MATCH":
    raise RuntimeError("structural reconstruction differs")
pivot = install_in_memory_pivot(
    blend=blend, repaired=usf, sdk_root=sdk, blender_sha256=blender_sha)
if pivot["status"] != "IN_MEMORY_PIVOT_MESH_MATCH" or sha(module_path) != module_sha:
    raise RuntimeError("pivot result or module bytes differ")
print("ROADCRAFT_PIVOT_REPAIR " + json.dumps({
    "structuralStatus": structural["status"],
    "pivot": pivot,
    "blendSaved": False,
    "usfExported": False,
}, sort_keys=True), flush=True)
