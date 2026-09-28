"""Read-only object-name search across the supplied WizTree Blend inventory."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
worklist = ROOT / "operations/d11_blender_reconstruction_worklist_20260928.json"
if hashlib.sha256(worklist.read_bytes()).hexdigest() != "a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3":
    raise RuntimeError("worklist pin differs")
if hashlib.sha256(Path(bpy.app.binary_path).read_bytes()).hexdigest() != "e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7":
    raise RuntimeError("Blender pin differs")
findings = next(row for row in json.loads(worklist.read_text(encoding="utf-8"))["assets"]
                if row["asset"] == "cat_d11t")["findings"]
expected = [path.rsplit("|", 1)[-1] for path in findings["repairedOnlyPaths"]
            if "_vis" in path.rsplit("|", 1)[-1] or
            path.endswith("|cdt_blade_roll_pivot")]
if len(expected) != 52 or len(set(expected)) != 52:
    raise RuntimeError("target roster differs")

csv_path = Path(r"C:\Users\Gynga\OneDrive\Documents\WholeDrive.csv")
csv_sha = "0af10a3066d01780c5e9d4a0f7146646a3acd1d5701d6fe25767937b2f535fdc"
if hashlib.sha256(csv_path.read_bytes()).hexdigest() != csv_sha:
    raise RuntimeError("drive inventory pin differs")
rows = []
with csv_path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
    next(stream)
    for row in csv.DictReader(stream):
        name = row["File Name"]
        if name.lower().endswith(".blend") and "cat_d11t" in name.lower():
            rows.append(name)

checked = 0
missing_files = []
errors = []
hits = []
for name in rows:
    path = Path(name)
    if not path.is_file():
        missing_files.append(name)
        continue
    try:
        with bpy.data.libraries.load(str(path), link=False) as (source, target):
            names = set(source.objects)
    except Exception as exc:
        errors.append({"path": name, "error": str(exc)[:200]})
        continue
    checked += 1
    present = [item for item in expected if item in names or
               (item.endswith("_vis") and item + "_LOD0" in names)]
    if present:
        hits.append({"path": name, "present": present,
                     "objectNames": len(names),
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

if hashlib.sha256(csv_path.read_bytes()).hexdigest() != csv_sha:
    raise RuntimeError("drive inventory changed during search")

print("ROADCRAFT_DRIVE_BLEND_NAME_SEARCH " + json.dumps({
    "status": "READ_ONLY_BLEND_NAME_SEARCH",
    "inventoryPath": str(csv_path),
    "inventorySha256": csv_sha,
    "listedBlends": len(rows), "checkedBlends": checked,
    "missingFileCount": len(missing_files),
    "missingFileExamples": missing_files[:10],
    "errorCount": len(errors), "errors": errors[:10],
    "targetNames": len(expected), "hitCount": len(hits),
    "hits": hits,
    "blendSaved": False, "usfExported": False,
}, sort_keys=True), flush=True)
