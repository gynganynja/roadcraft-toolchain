from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import warnings
from zipfile import ZipFile


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import core  # noqa: E402
from roadcraft.cli import main  # noqa: E402


class CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Windows runners may expose Temp through an 8.3 alias (RUNNER~1).
        # Production paths are resolved, so fixtures must use the same form.
        self.root = Path(self.temp.name).resolve()

    def write(self, name: str, data: bytes) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def write_json(self, name: str, data: dict) -> Path:
        return self.write(name, json.dumps(data).encode())

    def test_status_distinguishes_accepted_candidate_and_transient_install(self) -> None:
        accepted = self.write("accepted.pak", b"accepted")
        candidate = self.write("candidate.pak", b"candidate")
        installed = self.write("installed.pak", b"transient")
        receipt = self.write_json("capture.json", {
            "status": "FAIL_ROLLBACK_PENDING", "runId": "abc",
            "candidateSha256": core.sha256_file(candidate),
            "baselineSha256": core.sha256_file(accepted),
            "rollback": {"status": "BASELINE_RESTORED"},
        })
        registry_path = self.write_json("registry.json", {
            "schemaVersion": 1, "project": "D11",
            "accepted": {"package": {"path": "accepted.pak", "sha256": core.sha256_file(accepted)}},
            "candidates": {"trial": {"package": {"path": "candidate.pak",
                                                   "sha256": core.sha256_file(candidate)}}},
        })
        config_path = self.write_json("machine.json", {
            "schemaVersion": 1, "installedPackage": "installed.pak",
            "transactionReceipts": ["capture.json"],
        })
        result = core.status(core.read_registry(registry_path), core.read_config(config_path))
        self.assertEqual(result["installedRelation"], "unrecognized")
        self.assertTrue(result["accepted"]["matchesExpected"])
        self.assertTrue(result["candidates"]["trial"]["matchesExpected"])
        self.assertTrue(result["recoveryRequired"])
        self.assertFalse(result["transactionReceipts"][0]["installedMatchesReceiptBaseline"])
        installed.write_bytes(b"candidate")
        result = core.status(core.read_registry(registry_path), core.read_config(config_path))
        self.assertEqual(result["installedRelation"], "candidate:trial")
        self.assertTrue(result["recoveryRequired"])
        self.assertEqual(result["accepted"]["sha256"], core.sha256_file(accepted))
        installed.write_bytes(b"accepted")
        result = core.status(core.read_registry(registry_path), core.read_config(config_path))
        self.assertEqual(result["installedRelation"], "accepted")
        self.assertFalse(result["recoveryRequired"])
        self.assertTrue(result["transactionReceipts"][0]["failedRun"])
        self.assertTrue(result["transactionReceipts"][0]["rollbackVerifiedNow"])
        accepted.write_bytes(b"later accepted")
        installed.write_bytes(b"later accepted")
        current = core.read_registry(registry_path)
        current["accepted"]["package"]["sha256"] = core.sha256_file(accepted)
        result = core.status(current, core.read_config(config_path))
        self.assertFalse(result["recoveryRequired"])
        self.assertTrue(result["transactionReceipts"][0]["supersededByAccepted"])

    def test_duplicate_zip_occurrences_are_compared_by_content(self) -> None:
        before = self.root / "before.pak"
        after = self.root / "after.pak"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with ZipFile(before, "w") as archive:
                archive.writestr("models\\body.tpl", b"one")
                archive.writestr("models/body.tpl", b"two")
                archive.writestr("ssl/keep.cls", b"same")
            with ZipFile(after, "w") as archive:
                archive.writestr("models/body.tpl", b"one")
                archive.writestr("models/body.tpl", b"changed")
                archive.writestr("ssl/keep.cls", b"same")
        rows = core.archive_members(after, member="models/body.tpl", occurrence=2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sha256"], sha256(b"changed").hexdigest())
        result = core.compare_archives(before, after, ["models/*"])
        self.assertEqual(result["changeCount"], 1)
        self.assertEqual(result["changes"][0]["occurrence"], 2)
        self.assertTrue(result["passesAllowedChanges"])
        denied = core.compare_archives(before, after, ["ssl/*"])
        self.assertFalse(denied["passesAllowedChanges"])

    def test_manifest_and_cli_failure_codes(self) -> None:
        source = self.write("source/model.usf", b"model")
        manifest = self.write_json("manifest.json", {
            "files": [{"relativePath": "model.usf", "sha256": core.sha256_file(source),
                       "bytes": source.stat().st_size}],
        })
        self.assertTrue(core.verify_manifest(manifest, source.parent)["passed"])
        self.assertEqual(main(["verify", "--file", str(source),
                               "--sha256", core.sha256_file(source), "--json"]), 0)
        source.write_bytes(b"changed")
        self.assertFalse(core.verify_manifest(manifest, source.parent)["passed"])
        self.assertEqual(main(["verify", "--file", str(source),
                               "--sha256", sha256(b"model").hexdigest(), "--json"]), 1)

    def test_config_resolves_relative_paths_and_rejects_bad_schema(self) -> None:
        config = self.write_json("local/machine.json", {
            "schemaVersion": 1, "installedPackage": "../installed.pak",
            "tools": {"furnace": "../bin/furnace.exe"},
            "transactionLocks": ["capture.lock.json"],
        })
        resolved = core.read_config(config)
        self.assertEqual(resolved["installedPackage"], str(self.root / "installed.pak"))
        self.assertEqual(resolved["transactionLocks"], [str(self.root / "local/capture.lock.json")])
        wrong = self.write_json("wrong.json", {"schemaVersion": 2})
        with self.assertRaises(core.RoadcraftError):
            core.read_config(wrong)

    def test_project_verify_checks_manifest_contents_not_only_manifest_hash(self) -> None:
        source = self.write("assets/model.usf", b"good")
        manifest = self.write_json("manifest.json", {
            "files": [{"path": "model.usf", "sha256": core.sha256_file(source)}]
        })
        package = self.write("accepted.pak", b"package")
        registry = self.write_json("project.json", {
            "schemaVersion": 1, "project": "D11", "candidates": {},
            "accepted": {
                "package": {"path": "accepted.pak", "sha256": core.sha256_file(package)},
                "sourceManifest": {"path": "manifest.json", "sha256": core.sha256_file(manifest)},
                "sourceRoot": "assets",
            },
        })
        from roadcraft.cli import execute, make_parser
        args = make_parser().parse_args(["verify", "--project", "--registry", str(registry),
                                         "--config", str(self.root / "missing-config.json")])
        self.assertTrue(execute(args)[1])
        source.write_bytes(b"tampered")
        result, passed = execute(args)
        self.assertFalse(passed)
        self.assertFalse(result["sourceFiles"]["passed"])

    def test_transaction_states_are_distinct_from_legacy_capture_status(self) -> None:
        accepted = self.write("accepted.pak", b"accepted")
        candidate = self.write("candidate.pak", b"candidate")
        installed = self.write("installed.pak", b"accepted")
        transaction = {
            "schemaVersion": 1, "transactionId": "a" * 32,
            "installedPath": str(installed), "state": "SWAP_READY",
            "previousSha256": core.sha256_file(accepted),
            "candidateSha256": core.sha256_file(candidate),
        }
        receipt = self.write_json("tx/receipt.json", transaction)
        registry = self.write_json("project.json", {
            "schemaVersion": 1, "project": "D11", "candidates": {},
            "accepted": {"package": {"path": "accepted.pak", "sha256": core.sha256_file(accepted)}},
        })
        config = self.write_json("machine.json", {
            "schemaVersion": 1, "installedPackage": "installed.pak",
            "transactionReceipts": ["tx/receipt.json"],
        })
        state = core.status(core.read_registry(registry), core.read_config(config))
        self.assertTrue(state["recoveryRequired"])
        self.assertEqual(state["transactionReceipts"][0]["state"], "SWAP_READY")
        transaction["state"] = "NOT_INSTALLED"
        receipt.write_text(json.dumps(transaction))
        state = core.status(core.read_registry(registry), core.read_config(config))
        self.assertFalse(state["recoveryRequired"])
        installed.write_bytes(b"candidate")
        transaction["state"] = "INSTALLED"
        receipt.write_text(json.dumps(transaction))
        state = core.status(core.read_registry(registry), core.read_config(config))
        self.assertFalse(state["recoveryRequired"])
        transaction["state"] = "ROLLBACK_READY"
        receipt.write_text(json.dumps(transaction))
        state = core.status(core.read_registry(registry), core.read_config(config))
        self.assertTrue(state["recoveryRequired"])

    def test_project_verify_checks_authoring_inventory_contents(self) -> None:
        from roadcraft import source
        authored = self.write("assets/model.usf", b"original")
        inventory = source.capture_source_inventory(self.root / "assets", [
            {"asset": "model", "exportMethod": "usf-repair",
             "files": [{"path": "model.usf", "role": "build-usf"}]},
        ])
        inventory_path = self.write_json("inventory.json", inventory)
        package = self.write("accepted.pak", b"package")
        registry = self.write_json("project.json", {
            "schemaVersion": 1, "project": "D11", "candidates": {},
            "accepted": {
                "package": {"path": "accepted.pak", "sha256": core.sha256_file(package)},
                "sourceRoot": "assets",
                "authoringInventory": {"path": "inventory.json",
                                       "sha256": core.sha256_file(inventory_path)},
            },
        })
        from roadcraft.cli import execute, make_parser
        args = make_parser().parse_args(["verify", "--project", "--registry", str(registry),
                                         "--config", str(self.root / "missing-config.json")])
        self.assertTrue(execute(args)[1])
        authored.write_bytes(b"tampered")
        result, passed = execute(args)
        self.assertFalse(passed)
        self.assertFalse(result["authoringFiles"]["passed"])


if __name__ == "__main__":
    unittest.main()
