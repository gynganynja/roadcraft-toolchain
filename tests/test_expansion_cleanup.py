"""Synthetic checks for the exact-file retail-export cleanup executor."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from roadcraft import expansion_cleanup as expansion


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExpansionFixture:
    def __init__(self, root: Path, *, second_stage: bool = False):
        self.root = root
        self.scope = root / "source"
        self.scope.mkdir(parents=True)
        self.receipt = root / "receipt.jsonl"
        self.manifest = root / "review.json"
        self.rows = []
        self.stages = []
        self.unlisted = []
        self.retained = []
        for number in range(2 if second_stage else 1):
            stage = self.scope / "build" / "retail_exports" / f"T{number}"
            project = stage / "project" / "mods_source"
            project.mkdir(parents=True)
            audit = stage / "audit.json"
            audit.write_text("{}", encoding="utf-8")
            source_pak = stage / "source.pak"
            source_pak.write_bytes(b"sealed source")
            package = stage / "cat_d11t.pak"
            with ZipFile(package, "w") as archive:
                archive.writestr("models/item.bin", b"generated package payload")
            candidate = project / "models" / "item.bin"
            candidate.parent.mkdir()
            candidate.write_bytes(b"generated package payload")
            unlisted = project / "models" / "keep.bin"
            unlisted.write_bytes(b"keep this unlisted file")
            self.unlisted.append(unlisted)
            self.retained.extend((audit, source_pak, package))
            snapshot = expansion._snapshot(candidate, "candidate", candidate=True)
            row = {**snapshot, "path": str(candidate),
                   "retainedOriginal": {
                       "kind": "retained-package-member", "path": str(package),
                       "packageSha256": _digest(package),
                       "occurrences": [{"index": 0, "member": "models/item.bin",
                                        "bytes": candidate.stat().st_size,
                                        "sha256": _digest(candidate)}]},
                   "classification": "generated-retail-export-copy",
                   "stage": str(stage),
                   "executionStatus": "review-candidate-only-active-ownership-recheck-required"}
            self.rows.append(row)
            self.stages.append({
                "stage": str(stage), "project": str(stage / "project"),
                "status": "reviewed", "candidateFiles": 1,
                "candidateAllocatedBytes": snapshot["allocatedBytes"],
                "executableOrMarkdownReferences": [],
                "retainedAudit": {"path": str(audit), "sha256": _digest(audit)},
                "retainedPackage": {"path": str(package), "sha256": _digest(package)},
                "retainedSourceSnapshot": {"path": str(source_pak),
                                           "sha256": _digest(source_pak)}})
        self.save()

    def save(self) -> None:
        self.manifest.write_text(json.dumps({
            "schemaVersion": 1, "scope": str(self.scope),
            "candidateCount": len(self.rows),
            "candidateAllocatedBytes": sum(row["allocatedBytes"] for row in self.rows),
            "stages": self.stages, "candidates": self.rows,
        }, indent=2), encoding="utf-8")
        self.pin = _digest(self.manifest)

    def run(self, *, apply: bool = False, pin: str | None = None,
            process_checker=None, git_checker=None):
        return expansion.execute_expansion_cleanup(
            self.manifest, manifest_sha256=self.pin if pin is None else pin,
            apply=apply, receipt_path=self.receipt,
            process_checker=process_checker or (lambda: ([], None)),
            git_checker=git_checker or (lambda scope, rows: {
                "head": "synthetic", "trackedCandidateCount": 0,
                "trackedStatusSha256": "stable", "trackedStatusEntries": 0}),
        )


class ExpansionCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = ExpansionFixture(Path(self.temp.name))

    def test_default_dry_run_verifies_and_keeps_files(self):
        fixture = self.fixture
        result = fixture.run()
        self.assertTrue(result["dryRun"])
        self.assertTrue(result["applyReady"])
        self.assertEqual(result["candidateCount"], 1)
        self.assertTrue(Path(fixture.rows[0]["path"]).exists())
        self.assertFalse(fixture.receipt.exists())

    def test_process_fallback_blocks_uninspectable_python_but_excludes_self(self):
        snapshot = [{"pid": 41, "name": "python.exe"},
                    {"pid": 42, "name": "python.exe"},
                    {"pid": 43, "name": "RoadCraft.exe"}]
        with patch.object(expansion.core, "_editor_processes", return_value=(snapshot, None)), \
                patch.object(expansion, "_command_line_processes",
                             return_value=({}, "CIM access denied")), \
                patch.object(expansion.os, "getpid", return_value=41):
            active, error, details = expansion._process_state()
        self.assertEqual(error, "CIM access denied")
        self.assertEqual([(row["pid"], row["reason"]) for row in active],
                         [(42, "uninspectable-script-host"),
                          (43, "known-game-or-export-process")])
        self.assertEqual(details["method"], "toolhelp-conservative-script-host-block")
        self.assertFalse(details["complete"])
        self.assertFalse(details["commandLinesAvailable"])

    def test_complete_command_line_query_distinguishes_unrelated_python(self):
        snapshot = [{"pid": 41, "name": "python.exe"},
                    {"pid": 42, "name": "python.exe"},
                    {"pid": 43, "name": "python.exe"},
                    {"pid": 44, "name": "python.exe"},
                    {"pid": 46, "name": "python.exe"}]
        commands = {
            42: {"Name": "python.exe", "CommandLine": "python unrelated.py"},
            43: {"Name": "python.exe", "CommandLine": "python retail_export.py"},
            44: {"Name": "python.exe", "CommandLine": None},
            45: {"Name": "custom.exe", "CommandLine": "custom.exe retail_export.py"},
            46: {"Name": "reused.exe", "CommandLine": "reused.exe harmless"},
        }
        active = expansion._classify_processes(snapshot, commands, None, own_pid=41)
        self.assertEqual([(row["pid"], row["reason"]) for row in active],
                         [(43, "retail-export-script"),
                          (44, "uninspectable-script-host"),
                          (46, "uninspectable-script-host"),
                          (45, "retail-export-script")])

    def test_process_snapshot_error_fails_closed(self):
        with patch.object(expansion.core, "_editor_processes",
                          return_value=([], "snapshot denied")):
            active, error, details = expansion._process_state()
        self.assertEqual(active, [])
        self.assertEqual(error, "snapshot denied")
        self.assertFalse(details["complete"])

    def test_cim_denial_blocks_even_when_no_other_process_is_visible(self):
        with patch.object(expansion.core, "_editor_processes",
                          return_value=([{"pid": 41, "name": "python.exe"}], None)), \
                patch.object(expansion, "_command_line_processes",
                             return_value=({}, "CIM access denied")), \
                patch.object(expansion.os, "getpid", return_value=41):
            active, error, details = expansion._process_state()
        self.assertEqual(active, [])
        self.assertEqual(error, "CIM access denied")
        self.assertFalse(details["complete"])

    def test_command_line_query_rejects_missing_process_identity(self):
        response = expansion.subprocess.CompletedProcess(
            args=[], returncode=0, stdout='[{"Name":"python.exe"}]', stderr="")
        with patch.object(expansion.subprocess, "run", return_value=response):
            rows, error = expansion._command_line_processes()
        self.assertEqual(rows, {})
        self.assertIn("invalid", error)

    def test_bounded_sample_is_labeled_incomplete_and_cannot_apply(self):
        fixture = self.fixture
        result = expansion.execute_expansion_cleanup(
            fixture.manifest, manifest_sha256=fixture.pin, sample_candidates=1,
            process_checker=lambda: ([], None),
            git_checker=lambda scope, rows: {"trackedCandidateCount": 0})
        self.assertTrue(result["partialSample"])
        self.assertFalse(result["applyReady"])
        self.assertEqual(result["sampleCandidateCount"], 1)
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "dry-run only"):
            expansion.execute_expansion_cleanup(
                fixture.manifest, manifest_sha256=fixture.pin,
                sample_candidates=1, apply=True, receipt_path=fixture.receipt)
        self.assertTrue(Path(fixture.rows[0]["path"]).exists())

    def test_apply_requires_exact_pin_and_receipt(self):
        fixture = self.fixture
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "requires an exact"):
            expansion.execute_expansion_cleanup(
                fixture.manifest, apply=True, receipt_path=fixture.receipt)
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "differs from pinned"):
            fixture.run(apply=True, pin="0" * 64)
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "requires an external"):
            expansion.execute_expansion_cleanup(
                fixture.manifest, manifest_sha256=fixture.pin, apply=True,
                process_checker=lambda: ([], None),
                git_checker=lambda scope, rows: {"trackedCandidateCount": 0})
        self.assertTrue(Path(fixture.rows[0]["path"]).exists())

    def test_apply_removes_only_listed_file_and_writes_per_file_journal(self):
        fixture = self.fixture
        result = fixture.run(apply=True)
        self.assertEqual(result["state"], "COMPLETE")
        self.assertEqual(result["deletedCount"], 1)
        self.assertFalse(Path(fixture.rows[0]["path"]).exists())
        self.assertTrue(all(path.exists() for path in fixture.unlisted + fixture.retained))
        self.assertTrue(Path(fixture.stages[0]["project"]).exists())
        events = [json.loads(line) for line in fixture.receipt.read_text().splitlines()]
        self.assertEqual([row["type"] for row in events],
                         ["start", "intent", "deleted", "complete"])

    def test_candidate_drift_aborts_before_receipt(self):
        fixture = self.fixture
        Path(fixture.rows[0]["path"]).write_bytes(b"changed")
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "candidate drift"):
            fixture.run(apply=True)
        self.assertTrue(Path(fixture.rows[0]["path"]).exists())

    def test_retained_package_member_drift_aborts(self):
        fixture = self.fixture
        package = Path(fixture.stages[0]["retainedPackage"]["path"])
        with ZipFile(package, "w") as archive:
            archive.writestr("models/item.bin", b"changed package payload")
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "retainedPackage differs"):
            fixture.run(apply=True)
        self.assertTrue(Path(fixture.rows[0]["path"]).exists())

    def test_retained_source_texture_is_hashed_and_preserved(self):
        fixture = self.fixture
        original = fixture.scope / "retained" / "texture.pct"
        original.parent.mkdir()
        original.write_bytes(b"retained source texture")
        candidate = Path(fixture.stages[0]["project"]) / "mods_source" / "pct" / "texture.pct"
        candidate.parent.mkdir()
        candidate.write_bytes(original.read_bytes())
        row = {**expansion._snapshot(candidate, "candidate", candidate=True),
               "retainedOriginal": {"kind": "retained-source-texture-copy",
                                    "path": str(original), "sha256": _digest(original)},
               "classification": "generated-retail-export-copy",
               "stage": fixture.stages[0]["stage"],
               "executionStatus": "review-candidate-only-active-ownership-recheck-required"}
        fixture.rows.append(row)
        fixture.stages[0]["candidateFiles"] += 1
        fixture.stages[0]["candidateAllocatedBytes"] += row["allocatedBytes"]
        fixture.save()
        self.assertEqual(fixture.run()["verifiedRetainedSourceFiles"], 1)
        original.write_bytes(b"changed retained source")
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "retained texture drift"):
            fixture.run(apply=True)
        self.assertTrue(candidate.exists())

    def test_hardlink_candidate_aborts(self):
        fixture = self.fixture
        candidate = Path(fixture.rows[0]["path"])
        link = candidate.with_name("other-link.bin")
        try:
            os.link(candidate, link)
        except OSError:
            self.skipTest("filesystem does not permit synthetic hardlink")
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "candidate drift"):
            fixture.run(apply=True)
        self.assertTrue(candidate.exists())

    def test_tracked_candidate_and_active_process_block_apply(self):
        fixture = self.fixture
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "tracked candidate"):
            fixture.run(apply=True, git_checker=lambda scope, rows: {
                "trackedCandidateCount": 1, "head": "test"})
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "active process"):
            fixture.run(apply=True, process_checker=lambda: ([{"name": "RoadCraft.exe"}], None))
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "incomplete process"):
            fixture.run(apply=True, process_checker=lambda: ([], "access denied"))
        self.assertTrue(Path(fixture.rows[0]["path"]).exists())

    def test_resume_reconciles_durable_intent_after_unlink(self):
        fixture = self.fixture
        row = fixture.rows[0]
        expansion._append(fixture.receipt, {
            "type": "start", "schemaVersion": 1, "manifestSha256": fixture.pin,
            "scope": str(fixture.scope), "candidateCount": 1, "utc": "synthetic"})
        expansion._append(fixture.receipt, expansion._event("intent", 0, row))
        Path(row["path"]).unlink()
        result = fixture.run(apply=True)
        self.assertEqual(result["state"], "COMPLETE")
        self.assertTrue(all(path.exists() for path in fixture.unlisted + fixture.retained))
        events = [json.loads(line) for line in fixture.receipt.read_text().splitlines()]
        self.assertEqual([entry["type"] for entry in events][-2:], ["deleted", "complete"])

    def test_unjournaled_missing_file_aborts(self):
        fixture = self.fixture
        Path(fixture.rows[0]["path"]).unlink()
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "missing or unreadable"):
            fixture.run(apply=True)

    def test_git_state_change_between_stages_stops_before_second_unlink(self):
        fixture = ExpansionFixture(Path(self.temp.name) / "two", second_stage=True)
        calls = 0
        def git(scope, rows):
            nonlocal calls
            calls += 1
            return {"trackedCandidateCount": 0, "head": "changed" if calls == 3 else "same"}
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "Git state changed"):
            fixture.run(apply=True, git_checker=git)
        self.assertFalse(Path(fixture.rows[0]["path"]).exists())
        self.assertTrue(Path(fixture.rows[1]["path"]).exists())
        events = [json.loads(line) for line in fixture.receipt.read_text().splitlines()]
        self.assertEqual([event["type"] for event in events], ["start", "intent", "deleted"])

    def test_reparse_ancestor_aborts_if_supported(self):
        fixture = self.fixture
        source = Path(fixture.stages[0]["stage"])
        link = source.with_name("linked-stage")
        try:
            os.symlink(source, link, target_is_directory=True)
        except OSError:
            self.skipTest("filesystem does not permit synthetic symlink")
        fixture.rows[0]["path"] = str(link / "project" / "mods_source" / "models" / "item.bin")
        fixture.rows[0]["stage"] = str(link)
        fixture.stages[0]["stage"] = str(link)
        fixture.stages[0]["project"] = str(link / "project")
        fixture.save()
        with self.assertRaisesRegex(expansion.ExpansionCleanupBlocked, "reparse point|symlink"):
            fixture.run(apply=True)


if __name__ == "__main__":
    unittest.main()
