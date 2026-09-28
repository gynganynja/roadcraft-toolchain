"""Evidence-chain and classification checks for the Blender worklist."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from roadcraft.blender_reconciliation import (  # noqa: E402
    ReconciliationError, build_reconciliation_report, reconcile_diff,
)
from roadcraft.source import capture_source_inventory, file_sha256  # noqa: E402


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReconciliationTests(unittest.TestCase):
    def test_unique_leaf_is_candidate_not_proven_equivalence(self) -> None:
        diff = {
            "missingNodePaths": ["|@root|Old|Shared", "|@root|Old|Absent"],
            "extraNodePaths": ["|@root|New|Shared", "|@root|New|Unexpected"],
            "matchedNodeDifferences": [{
                "path": "|@root|Body_vis", "fields": {
                    "mesh": {"baseline": {
                        "faces": 3, "materialNames": [
                            'material = { name = "painter_01" }'],
                        "skinEntries": 9, "skinBoneNodeUids": [4],
                        "inverseBindMatricesSha256": "old",
                    }, "candidate": {
                        "faces": 2, "materialNames": [], "skinEntries": 0,
                        "skinBoneNodeUids": [], "inverseBindMatricesSha256": "new",
                    }},
                    "animation": {"baseline": {"spl_rotation": {"keys": 36}},
                                  "candidate": None},
                },
            }],
        }
        result = reconcile_diff(diff)
        self.assertEqual(result["counts"]["pathRelocationCandidates"], 1)
        self.assertEqual(result["counts"]["totalRepairedOnlyPaths"], 2)
        self.assertEqual(result["counts"]["unpairedRepairedPaths"], 1)
        self.assertFalse(result["pathRelocationCandidates"][0]["equivalenceVerified"])
        self.assertEqual(result["repairedOnlyPaths"], ["|@root|Old|Absent"])
        self.assertEqual(result["nativeExportOnlyPaths"], ["|@root|New|Unexpected"])
        mesh = result["changedMeshNodes"][0]
        self.assertEqual(mesh["missingMaterialLabels"],
                         [{"label": "painter_01", "count": 1}])
        self.assertEqual(mesh["measurements"]["skinEntries"],
                         {"repaired": 9, "nativeExport": 0})
        self.assertTrue(mesh["inverseBindMatricesDifferent"])
        self.assertEqual(result["changedAnimationNodes"][0]["candidate"], None)

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="roadcraft-reconcile-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        source = self.root / "source"
        source.mkdir()
        self.blend = source / "asset.blend"
        self.blend.write_bytes(b"pinned source Blend")
        self.usf = source / "export.usf"
        self.usf.write_bytes(b"pinned repaired USF")
        self.candidate = self.root / "candidate.usf"
        self.candidate.write_bytes(b"different native export")
        inventory = capture_source_inventory(source, [{
            "asset": "asset", "exportMethod": "usf-repair",
            "files": [{"path": "asset.blend", "role": "blend-reference"},
                      {"path": "export.usf", "role": "build-usf"}],
        }])
        self.inventory = self.root / "inventory.json"
        self.inventory.write_text(json.dumps(inventory), encoding="utf-8")
        self.registry = self.root / "project.json"
        self.registry.write_text(json.dumps({"accepted": {"authoringInventory": {
            "path": "inventory.json", "sha256": file_sha256(self.inventory),
        }}}), encoding="utf-8")
        self.archive = self.root / "summary.json.gz"
        self.summary = self.root / "summary.json"
        diff = {"missingNodePaths": ["|@root|Missing"],
                "extraNodePaths": [], "matchedNodeDifferences": [],
                "matchesIndexedFields": False}
        diagnostic = {
            "blendSha256": file_sha256(self.blend),
            "baselineUsfSha256": file_sha256(self.usf),
            "candidateUsfSha256": file_sha256(self.candidate),
            "candidateUsfBytes": self.candidate.stat().st_size,
            "nativeBlendExportApproved": False,
            "baselineSemantic": {"nodes": 2},
            "candidateSemantic": {"nodes": 1},
            "baselineRootName": "asset", "candidateRootName": "asset",
            "nodeDiff": diff,
        }
        self.full = {
            "asset": "asset", "inventorySha256": file_sha256(self.inventory),
            "sourceAssetDigest": inventory["assets"][0]["assetDigest"],
            "blendPath": str(self.blend), "blendSha256": file_sha256(self.blend),
            "baselineUsfPath": str(self.usf),
            "baselineUsfSha256": file_sha256(self.usf),
            "candidateUsfPath": str(self.candidate),
            "candidateUsfSha256Observed": file_sha256(self.candidate),
            "candidateUsfBytesObserved": self.candidate.stat().st_size,
            "sdkFileHashes": {}, "helperSha256": "h", "diffSha256": "d",
            "summarySha256": "s", "status": "PARITY_DIFFERENT",
            "exportGate": {"status": "BLOCKED"},
            "sourceUnchanged": True, "sdkUnchanged": True,
            "blenderExitCode": 0, "diagnostic": diagnostic,
            "nativeBlendExportApproved": False,
        }
        self._seal()

    def _seal(self) -> None:
        raw = (json.dumps(self.full, sort_keys=True) + "\n").encode()
        archive = gzip.compress(raw, mtime=0)
        self.archive.write_bytes(archive)
        summary = {key: self.full[key] for key in (
            "asset", "inventorySha256", "sourceAssetDigest", "blendPath",
            "blendSha256", "baselineUsfPath", "baselineUsfSha256",
            "candidateUsfPath", "sdkFileHashes", "helperSha256", "diffSha256",
            "summarySha256", "status", "exportGate", "nativeBlendExportApproved",
        )}
        summary.update({"candidateUsfSha256": file_sha256(self.candidate),
                        "candidateUsfBytes": self.candidate.stat().st_size,
                        "archivePath": str(self.archive),
                        "archiveBytes": len(archive), "archiveSha256": _sha(archive),
                        "fullRawBytes": len(raw), "fullRawSha256": _sha(raw)})
        self.summary.write_text(json.dumps(summary), encoding="utf-8")

    def test_report_requires_current_source_and_preserves_blocked_gate(self) -> None:
        report = build_reconciliation_report(self.registry, [self.summary])
        self.assertEqual(report["status"], "RECONSTRUCTION_REQUIRED")
        self.assertFalse(report["nativeBlendExportApproved"])
        self.assertEqual(report["assets"][0]["findings"]["repairedOnlyPaths"],
                         ["|@root|Missing"])
        self.blend.write_bytes(b"changed source")
        with self.assertRaisesRegex(ReconciliationError, "declared authoring source differs"):
            build_reconciliation_report(self.registry, [self.summary])

    def test_tampered_archive_cannot_generate_worklist(self) -> None:
        self.archive.write_bytes(self.archive.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ReconciliationError, "archive differs"):
            build_reconciliation_report(self.registry, [self.summary])

    def test_failed_source_verification_cannot_generate_worklist(self) -> None:
        self.full["sdkUnchanged"] = False
        self._seal()
        with self.assertRaisesRegex(ReconciliationError, "blocked-difference"):
            build_reconciliation_report(self.registry, [self.summary])


if __name__ == "__main__":
    unittest.main()
