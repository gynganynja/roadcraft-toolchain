"""Read-only mesh-name inventory of three historical D11 Blender files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[1]
worklist = ROOT / "operations/d11_blender_reconstruction_worklist_20260928.json"
if hashlib.sha256(worklist.read_bytes()).hexdigest() != "a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3":
    raise RuntimeError("worklist pin differs")
if hashlib.sha256(Path(bpy.app.binary_path).read_bytes()).hexdigest() != "e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7":
    raise RuntimeError("Blender pin differs")
items = json.loads(worklist.read_text(encoding="utf-8"))["assets"]
findings = next(row for row in items if row["asset"] == "cat_d11t")["findings"]
expected = [path.rsplit("|", 1)[-1] for path in findings["repairedOnlyPaths"]
            if "_vis" in path.rsplit("|", 1)[-1] or
            path.endswith("|cdt_blade_roll_pivot")]
if len(expected) != 52 or len(set(expected)) != 52:
    raise RuntimeError("repaired-only mesh name coverage differs")

candidates = [
    (r"C:\RC\D11_Development\port_cat_d11t\reports\central_hose_sockets_v2\cat_d11t_central_sockets_review.blend",
     "1e897b139bd8b43237db441f4b74aa88c3d4abf4ec1d6ff187ce27e54405362d"),
    (r"C:\RC\D11_Development\port_cat_d11t\reports\blade_flex_hoses_v1\cat_d11t_blade_flex_review_v2.blend",
     "948aa4d65026ce5afdef9cdf5493109289a9419e3072a34d2cc78320118fe338"),
    (r"C:\RC\D11_Development\port_cat_d11t\reports\combined_user_fixes_20260923\export_v1\native_import\project\mods_source\models\mods\cat_d11t.tpl.asset\cat_d11t.blend",
     "9b112b53e064224c4a29200110d5d1119f384c25c612d2baf2a6e083ff015fa1"),
]

rows = []
for name, digest in candidates:
    path = Path(name)
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"candidate pin differs: {path}")
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False)
    scene_meshes = {obj.name: obj for obj in bpy.context.scene.objects
                    if obj.type == "MESH"}
    all_meshes = {obj.name: obj for obj in bpy.data.objects if obj.type == "MESH"}
    present = []
    absent = []
    for target in expected:
        names = [target]
        if target.endswith("_vis"):
            names.append(target + "_LOD0")
        if any(name in scene_meshes for name in names):
            present.append(target)
        else:
            absent.append(target)
    all_present = sum(any(name in all_meshes for name in
                          ([target, target + "_LOD0"] if target.endswith("_vis")
                           else [target])) for target in expected)
    rows.append({"path": str(path), "sha256": digest,
                 "sceneMeshObjects": len(scene_meshes),
                 "allBlendMeshObjects": len(all_meshes),
                 "repairedOnlyMeshNamesPresentInScene": len(present),
                 "repairedOnlyMeshNamesPresentInFile": all_present,
                 "presentNames": present, "absentNames": absent,
                 "armatureObjects": sum(obj.type == "ARMATURE" for obj in bpy.context.scene.objects),
                 "actions": [action.name for action in bpy.data.actions]})
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"candidate changed while inspected: {path}")

print("ROADCRAFT_ALTERNATE_BLEND_INVENTORY " + json.dumps({
    "status": "READ_ONLY_ALTERNATE_AUTHORING_INVENTORY",
    "targetMeshNames": 52, "rows": rows,
    "blendSaved": False, "usfExported": False,
}, sort_keys=True), flush=True)
