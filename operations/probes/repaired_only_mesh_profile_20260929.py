"""Read-only profile of D11 repaired-only nodes in the pinned worklist."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from roadcraft.blender_left_push_probe import require_sdk_pins


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def need(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


inventory = ROOT / "operations/d11_authoring_inventory.json"
worklist = ROOT / "operations/d11_blender_reconstruction_worklist_20260928.json"
sdk = Path(r"C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\blender_to_usf_script")
need(sha(inventory) == "03d3eae96720612ae3b1457a27cc797f8bc6ebb694b230f253bcadbe9d13b50d", "inventory pin")
need(sha(worklist) == "a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3", "worklist pin")
need(sha(Path(bpy.app.binary_path)) == "e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7", "Blender pin")
require_sdk_pins(sdk)
inv = json.loads(inventory.read_text(encoding="utf-8"))
asset = next(row for row in inv["assets"] if row["asset"] == "cat_d11t")
usf_row = next(row for row in asset["files"] if row["role"] == "build-usf")
usf = Path(inv["sourceRoot"]) / usf_row["path"]
need(sha(usf) == usf_row["sha256"] == "49bfc77c1172a0e324934974d5612a13d121c3cee78ae7ca454468b61649e170", "repaired USF pin")
items = json.loads(worklist.read_text(encoding="utf-8"))["assets"]
findings = next(row for row in items if row["asset"] == "cat_d11t")["findings"]
missing = set(findings["repairedOnlyPaths"])
need(len(missing) == 67, "repaired-only worklist coverage")

sys.path.insert(0, str(sdk))
from saber.blender.lib.binary_io import BinaryIO
from saber.blender.lib.usf.scene import usf_read

reader = BinaryIO.read_bytearray
BinaryIO.read_bytearray = lambda self, size=None: self.io.read(size) if size is not None else reader(self)
try:
    _, parsed = usf_read(str(usf))
finally:
    BinaryIO.read_bytearray = reader

nodes = {}
stack = [(parsed._root_node, "|@root")]
while stack:
    node, path = stack.pop()
    need(path not in nodes, f"duplicate path: {path}")
    nodes[path] = node
    stack.extend((child, path + "|" + child.name) for child in node.children)
need(missing <= set(nodes), "worklist repaired-only path absent")

rows = []
for path in sorted(missing):
    node = nodes[path]
    mesh = node.mesh
    row = {"path": path, "name": node.name, "mesh": mesh is not None,
           "parent": path.rsplit("|", 1)[0]}
    if mesh is not None:
        row.update({
            "faces": len(mesh.faces),
            "vertices": len(mesh.vertices),
            "materials": len(mesh.materials.data),
            "skinEntries": len(mesh.skin.skin),
            "skinBones": len(mesh.skin.skin_bones),
            "materialLabels": [item.mat for item in mesh.materials.data],
        })
    rows.append(row)

mesh_rows = [row for row in rows if row["mesh"]]
result = {
    "asset": "cat_d11t",
    "status": "REPAIRED_ONLY_MESH_PROFILE",
    "repairedOnlyPaths": len(rows),
    "meshPaths": len(mesh_rows),
    "nonMeshPaths": len(rows) - len(mesh_rows),
    "meshFaces": sum(row["faces"] for row in mesh_rows),
    "meshSkinEntries": sum(row["skinEntries"] for row in mesh_rows),
    "skinnedMeshPaths": sum(row["skinEntries"] > 0 for row in mesh_rows),
    "materialSlotOccurrences": sum(row["materials"] for row in mesh_rows),
    "parentCounts": dict(sorted(Counter(row["parent"] for row in mesh_rows).items())),
    "rows": rows,
    "blendSaved": False,
    "usfExported": False,
}
need(sha(usf) == usf_row["sha256"] and sha(worklist) == "a842c0e7dd355e64ace39a724a806f509328ba3fb1916fc7ab4bbb85062759c3", "post-run inputs changed")
print("ROADCRAFT_REPAIRED_ONLY_MESH " + json.dumps(result, sort_keys=True), flush=True)
