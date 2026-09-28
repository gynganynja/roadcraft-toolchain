"""Exercise real read-only handlers; SDK registration is independently checked."""

import asyncio
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import mcp_server as server


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tiny_png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"\0\x01\x02\x03")) + chunk(b"IEND", b""))


class FakeAnnotations:
    def __init__(self, **values):
        self.values = values


class FakeMCP:
    def __init__(self, name, **settings):
        self.name, self.settings, self.tools, self.transport = name, settings, {}, None

    def add_tool(self, function, *, name, annotations):
        self.tools[name] = (function, annotations.values)

    def run(self, *, transport):
        self.transport = transport


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.package = self.root / "accepted.pak"
        self.package.write_bytes(b"accepted package")
        self.registry = self.root / "project.json"
        self.registry.write_text(json.dumps({"schemaVersion": 1, "project": "fixture",
                                            "accepted": {"package": {"path": "accepted.pak", "sha256": sha(self.package.read_bytes())}},
                                            "candidates": {}}))
        self.config = self.root / "machine.json"
        self.config.write_text(json.dumps({"schemaVersion": 1, "sdkRoot": str(self.root),
                                          "installedPackage": str(self.package), "tools": {}}))
        self.settings = server.ServerSettings(self.registry, self.config)
        self.tools = server.RoadcraftTools(self.settings)

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}

    def test_project_status_doctor_verify_are_readonly(self):
        before = self.snapshot()
        status = self.tools.project_status()
        self.assertEqual(status["installedRelation"], "accepted")
        self.assertTrue(self.tools.verify_project()["passed"])
        with patch.object(server.core, "_editor_processes", return_value=([], None)):
            self.assertTrue(self.tools.project_doctor()["sdkRoot"]["exists"])
        self.assertEqual(self.snapshot(), before)

    def test_verify_file_and_manifest_detect_tampering(self):
        expected = sha(self.package.read_bytes())
        self.assertTrue(self.tools.verify_file(str(self.package), expected)["passed"])
        manifest = self.root / "files.json"
        manifest.write_text(json.dumps({"files": [{"path": self.package.name, "sha256": expected}]}))
        self.package.write_bytes(b"changed")
        self.assertFalse(self.tools.verify_file(str(self.package), expected)["passed"])
        self.assertFalse(self.tools.verify_manifest(str(manifest))["passed"])

    def test_archive_occurrences_and_pagination(self):
        archive = self.root / "test.pak"
        with ZipFile(archive, "w") as output:
            output.writestr("a", b"one")
            output.writestr("b", b"two")
        before = self.snapshot()
        result = self.tools.inspect_file(str(archive), limit=1)
        self.assertEqual(result["pagination"]["total"], 2)
        self.assertEqual(len(result["members"]), 1)
        self.assertEqual(result["pagination"]["nextOffset"], 1)
        self.assertEqual(self.tools.compare_archives(str(archive), str(archive))["changeCount"], 0)
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(ValueError):
            self.tools.inspect_file(str(archive), limit=1001)

    def test_source_inventory_and_compare_do_not_save(self):
        declarations = [{"asset": "D11", "exportMethod": "guarded-usf", "files": [{"path": "accepted.pak", "role": "fixture"}]}]
        before = self.snapshot()
        manifest = self.tools.source_inventory(str(self.root), declarations)
        self.assertEqual(self.snapshot(), before)
        left, right = self.root / "left.json", self.root / "right.json"
        left.write_text(json.dumps(manifest))
        right.write_text(json.dumps(manifest))
        self.assertTrue(self.tools.source_compare(str(left), str(right))["matches"])

    def test_storage_review_does_not_remove_candidates(self):
        templates = self.root / "sdk-templates"
        copies = self.root / "old-run" / "editor_data" / "templates"
        templates.mkdir()
        copies.mkdir(parents=True)
        for name in server.cleanup.TEMPLATE_NAMES:
            (templates / name).write_bytes(name.encode())
            (copies / name).write_bytes(name.encode())
        before = self.snapshot()
        result = self.tools.storage_review([str(self.root / "old-run")], str(templates))
        self.assertEqual(result["templateCopyCount"], 3)
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(ValueError):
            self.tools.storage_review([str(self.root)], str(templates), git_repo=str(self.root))

    def test_report_is_in_memory_only_and_separates_acceptance(self):
        image = self.root / "capture.png"
        image.write_bytes(tiny_png())
        receipt = self.root / "capture.json"
        receipt.write_text(json.dumps({"captures": [{"path": "capture.png", "sha256": sha(image.read_bytes())}]}))
        before = self.snapshot()
        with patch.object(server.review, "generate_report", side_effect=AssertionError("No disk writer may be called")):
            result = self.tools.evidence_report([{"path": str(receipt), "sha256": sha(receipt.read_bytes())}], include_html=True)
        self.assertFalse(result["writesPerformed"])
        self.assertIn("data:image/png;base64,", result["html"])
        self.assertEqual(result["htmlSha256"], sha(result["html"].encode()))
        self.assertEqual(result["manifest"]["evidence"]["campaign"]["state"], "not_assessed_by_report")
        self.assertEqual(self.snapshot(), before)

    def test_large_html_is_not_returned_unbounded(self):
        receipt = self.root / "receipt.json"
        receipt.write_text("{}")
        with patch.object(server, "MAX_RETURNED_HTML_BYTES", 1):
            result = self.tools.evidence_report([{"path": str(receipt)}], include_html=True)
        self.assertNotIn("html", result)
        self.assertIn("htmlOmittedReason", result)

    def test_all_registered_tools_are_readonly_without_mutations(self):
        with patch.object(server, "_sdk_components", return_value=(FakeMCP, FakeAnnotations)):
            instance = server.create_server(self.settings)
        self.assertEqual(set(instance.tools), set(server.TOOL_NAMES))
        self.assertEqual(len(instance.tools), 11)
        for name, (function, annotations) in instance.tools.items():
            self.assertTrue(annotations["readOnlyHint"], name)
            self.assertFalse(annotations["destructiveHint"], name)
            self.assertFalse(annotations["openWorldHint"], name)
            self.assertTrue(function.__doc__)
            self.assertFalse(any(word in name for word in ("delete", "install", "repack", "build", "recover", "execute")))

    def test_missing_sdk_exits_cleanly_without_stdout(self):
        stderr, stdout = io.StringIO(), io.StringIO()
        with patch.object(server.importlib.metadata, "version", side_effect=importlib.metadata.PackageNotFoundError("mcp")):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(server.main([]), 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("requirements-mcp.txt", stderr.getvalue())

    def test_incompatible_sdk_has_actionable_error(self):
        with patch.object(server.importlib.metadata, "version", return_value="2.0.0"):
            with self.assertRaisesRegex(server.MCPDependencyError, "incompatible version 2.0.0"):
                server.create_server(self.settings)

    def test_main_uses_stdio_only(self):
        instance = FakeMCP("test")
        with patch.object(server, "create_server", return_value=instance):
            self.assertEqual(server.main(["--registry", str(self.registry), "--config", str(self.config)]), 0)
        self.assertEqual(instance.transport, "stdio")

    def test_relative_and_remote_top_level_paths_are_rejected(self):
        for path in ("relative.pak", "https://example.com/file.pak", ""):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.tools.verify_file(path, "0" * 64)

    def test_real_sdk_schemas_when_dependency_is_available(self):
        try:
            instance = server.create_server(self.settings)
        except server.MCPDependencyError:
            self.skipTest("Optional supported MCP SDK is not installed")
        tools = asyncio.run(instance.list_tools())
        self.assertEqual({tool.name for tool in tools}, set(server.TOOL_NAMES))
        for tool in tools:
            self.assertTrue(tool.annotations.readOnlyHint)
            self.assertEqual(tool.inputSchema["type"], "object")
        inventory = next(tool for tool in tools if tool.name == "source_inventory")
        self.assertIn("assets", inventory.inputSchema["properties"])


if __name__ == "__main__":
    unittest.main()
