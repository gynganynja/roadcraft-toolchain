"""Boundaries and real SDK schemas for the separate Blender scratch MCP."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from roadcraft import blender_bridge, blender_mcp_server as adapter  # noqa: E402
from roadcraft.source import capture_source_inventory, file_sha256  # noqa: E402


class FakeAnnotations:
    def __init__(self, **values):
        self.values = values


class FakeMCP:
    def __init__(self, name, **kwargs):
        self.tools = {}
        self.transport = None

    def add_tool(self, function, *, name, annotations):
        self.tools[name] = (function, annotations.values)

    def run(self, *, transport):
        self.transport = transport


class BlenderMCPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="roadcraft-blender-mcp-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(adapter, "TOOLCHAIN_ROOT", self.root).start()
        mock.patch.object(blender_bridge, "TOOLCHAIN_ROOT", self.root).start()
        self.project = self.root / "project"
        self.source = self.project / "models/cat_d11t/export.usf"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"synthetic repaired USF")
        self.reference = self.project / "models/cat_d11t/reference.blend"
        self.reference.write_bytes(b"synthetic authoring reference")
        inventory = capture_source_inventory(self.project, [{
            "asset": "cat_d11t", "exportMethod": "usf-repair",
            "files": [{"path": "models/cat_d11t/export.usf", "role": "build-usf"},
                      {"path": "models/cat_d11t/reference.blend", "role": "blend-reference"}],
        }])
        self.inventory = self.root / "inventory.json"
        self.inventory.write_text(json.dumps(inventory), encoding="utf-8")
        (self.root / "project.json").write_text(json.dumps({
            "schemaVersion": 1,
            "accepted": {
                "authoringInventory": {"path": "inventory.json",
                                       "sha256": file_sha256(self.inventory)},
                "sourceRoot": str(self.project),
            },
            "candidates": {},
        }), encoding="utf-8")
        self.blender = self.root / "blender.exe"
        self.blender.write_bytes(b"fake pinned Blender executable")
        self.sdk = self.root / "sdk"
        sdk_lib = self.sdk / "saber/blender/lib"
        (sdk_lib / "usf").mkdir(parents=True)
        (sdk_lib / "binary_io.py").write_text("# fixture\n", encoding="utf-8")
        (sdk_lib / "usf/scene.py").write_text("# fixture\n", encoding="utf-8")
        self.settings = adapter.BlenderSettings(
            self.blender, file_sha256(self.blender), self.sdk,
            self.root / "local/blender-mcp-scratch",
        )
        self.tools = adapter.BlenderTools(self.settings)
        self.commands = []

    def _request(self, **kwargs):
        return self.tools.usf_roundtrip(
            "cat_d11t", str(self.inventory), file_sha256(self.inventory), **kwargs,
        )

    def _fake_blender(self, argv, **kwargs):
        self.commands.append(argv)
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="Blender 5.2.0 LTS\n")
        self.assertIn("--background", argv)
        self.assertIn("--factory-startup", argv)
        self.assertIn("--disable-autoexec", argv)
        self.assertNotIn(".blend", " ".join(argv).lower())
        output = Path(argv[argv.index("--output") + 1])
        receipt = Path(argv[argv.index("--receipt") + 1])
        source = Path(argv[argv.index("--source") + 1])
        output.write_bytes(source.read_bytes())
        receipt.write_text(json.dumps({
            "sourceSha256": file_sha256(source), "sourceBytes": source.stat().st_size,
            "outputSha256": file_sha256(output), "outputBytes": output.stat().st_size,
            "byteIdentical": True, "semanticSummaryEqual": True,
        }), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0)

    def _files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def test_status_probes_pinned_binary_and_is_read_only(self):
        before = self._files()
        with mock.patch.object(adapter.subprocess, "run", side_effect=self._fake_blender):
            status = self.tools.blender_status()
        self.assertTrue(status["ready"])
        self.assertEqual(status["version"], "Blender 5.2.0 LTS")
        self.assertEqual(self._files(), before)
        self.blender.write_bytes(b"tampered")
        self.commands.clear()
        with mock.patch.object(adapter.subprocess, "run", side_effect=self._fake_blender):
            status = self.tools.blender_status()
        self.assertFalse(status["ready"])
        self.assertEqual(self.commands, [])

    def test_dry_run_checks_inventory_without_writing(self):
        before = self._files()
        with mock.patch.object(adapter.subprocess, "run", side_effect=self._fake_blender):
            result = self._request()
        self.assertEqual(result["status"], "DRY_RUN")
        self.assertIsNone(result["receiptPath"])
        self.assertFalse(result["durableReceiptWritten"])
        self.assertFalse(result["nativeBlendExportApproved"])
        self.assertEqual(self._files(), before)

    def test_run_disposes_ephemeral_receipt_and_source_is_unchanged(self):
        with mock.patch.object(adapter.subprocess, "run", side_effect=self._fake_blender):
            result = self._request(run=True)
        self.assertEqual(result["status"], "BYTE_IDENTICAL")
        self.assertTrue(result["sourceUnchanged"])
        self.assertTrue(result["scratchOutputDisposed"])
        self.assertIsNone(result["receiptPath"])
        self.assertFalse(result["durableReceiptWritten"])
        self.assertEqual(list(self.settings.scratch_root.rglob("*")), [])
        self.assertEqual(self.source.read_bytes(), b"synthetic repaired USF")

    def test_explicit_jobs_receipt_only_and_stale_input_refused(self):
        receipt = self.root / "local/jobs/probe.json"
        with mock.patch.object(adapter.subprocess, "run", side_effect=self._fake_blender):
            result = self._request(run=True, receipt_path=str(receipt))
        self.assertTrue(result["durableReceiptWritten"])
        self.assertEqual(json.loads(receipt.read_text())["status"], "BYTE_IDENTICAL")
        with self.assertRaisesRegex(adapter.BlenderMCPError, "already exists"):
            self._request(run=True, receipt_path=str(receipt))
        with self.assertRaisesRegex(adapter.BlenderMCPError, "under"):
            self._request(run=True, receipt_path=str(self.root / "outside.json"))
        self.source.write_bytes(b"changed")
        with mock.patch.object(adapter.subprocess, "run", side_effect=self._fake_blender):
            with self.assertRaisesRegex(adapter.BlenderMCPError, "source differs"):
                self._request(run=True)

    def test_rejects_alternate_self_consistent_inventory_before_blender(self):
        other_root = self.root / "other-project"
        other_usf = other_root / "models/cat_d11t/export.usf"
        other_usf.parent.mkdir(parents=True)
        other_usf.write_bytes(b"different but self-consistent USF")
        alternate = capture_source_inventory(other_root, [{
            "asset": "cat_d11t", "exportMethod": "usf-repair",
            "files": [{"path": "models/cat_d11t/export.usf", "role": "build-usf"}],
        }])
        alternate_path = self.root / "alternate.json"
        alternate_path.write_text(json.dumps(alternate), encoding="utf-8")
        with mock.patch.object(adapter.subprocess, "run", side_effect=self._fake_blender):
            with self.assertRaisesRegex(adapter.BlenderMCPError, "accepted.authoringInventory"):
                self.tools.usf_roundtrip("cat_d11t", str(alternate_path),
                                         file_sha256(alternate_path), run=True)
        self.assertEqual(self.commands, [])
        self.assertFalse(self.settings.scratch_root.exists())

    def test_rejects_changed_non_usf_authoring_source_before_blender(self):
        self.reference.write_bytes(b"changed authoring reference")
        with mock.patch.object(adapter.subprocess, "run", side_effect=self._fake_blender):
            with self.assertRaisesRegex(adapter.BlenderMCPError, "source differs"):
                self._request()
        self.assertEqual(self.commands, [])
        self.assertFalse(self.settings.scratch_root.exists())

    def test_rejects_registry_pin_change_before_blender(self):
        registry_path = self.root / "project.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["accepted"]["authoringInventory"]["sha256"] = "0" * 64
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        with mock.patch.object(adapter.subprocess, "run", side_effect=self._fake_blender):
            with self.assertRaisesRegex(adapter.BlenderMCPError, "accepted.authoringInventory"):
                self._request()
        self.assertEqual(self.commands, [])

    def test_rejects_registry_source_root_mismatch_before_blender(self):
        other_root = self.root / "other-project"
        other_root.mkdir()
        registry_path = self.root / "project.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["accepted"]["sourceRoot"] = str(other_root)
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        with mock.patch.object(adapter.subprocess, "run", side_effect=self._fake_blender):
            with self.assertRaisesRegex(adapter.BlenderMCPError, "sourceRoot differs"):
                self._request()
        self.assertEqual(self.commands, [])

    def test_refuses_concurrent_run_and_invalid_arguments(self):
        self.assertTrue(self.tools._roundtrip_lock.acquire(blocking=False))
        try:
            with self.assertRaisesRegex(adapter.BlenderMCPError, "already running"):
                self._request(run=True)
        finally:
            self.tools._roundtrip_lock.release()
        with self.assertRaises(adapter.BlenderMCPError):
            self._request(timeout_seconds=901)
        with self.assertRaises(adapter.BlenderMCPError):
            self.tools.usf_roundtrip("../bad", str(self.inventory), file_sha256(self.inventory))
        with self.assertRaises(adapter.BlenderMCPError):
            self.tools.usf_roundtrip("cat_d11t", "relative.json", file_sha256(self.inventory))

    def test_only_two_tools_and_stdio_transport(self):
        with mock.patch.object(adapter, "_sdk_components", return_value=(FakeMCP, FakeAnnotations)):
            server = adapter.create_server(self.settings)
        self.assertEqual(set(server.tools), set(adapter.TOOL_NAMES))
        self.assertTrue(server.tools["blender_status"][1]["readOnlyHint"])
        self.assertFalse(server.tools["usf_roundtrip"][1]["readOnlyHint"])
        with mock.patch.object(adapter, "create_server", return_value=server):
            code = adapter.main(["--blender-executable", str(self.blender),
                                 "--blender-sha256", file_sha256(self.blender),
                                 "--sdk-script-root", str(self.sdk),
                                 "--scratch-root", str(self.settings.scratch_root)])
        self.assertEqual(code, 0)
        self.assertEqual(server.transport, "stdio")

    def test_real_sdk_schemas_when_installed(self):
        try:
            server = adapter.create_server(self.settings)
        except adapter.MCPDependencyError:
            self.skipTest("Optional official MCP SDK is not installed")
        tools = asyncio.run(server.list_tools())
        self.assertEqual({tool.name for tool in tools}, set(adapter.TOOL_NAMES))
        status = next(tool for tool in tools if tool.name == "blender_status")
        roundtrip = next(tool for tool in tools if tool.name == "usf_roundtrip")
        self.assertTrue(status.annotations.readOnlyHint)
        self.assertFalse(roundtrip.annotations.readOnlyHint)
        self.assertIn("inventory_sha256", roundtrip.inputSchema["properties"])
        self.assertIn("run", roundtrip.inputSchema["properties"])


if __name__ == "__main__":
    unittest.main()
