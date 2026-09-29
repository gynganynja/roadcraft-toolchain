"""Exercise real read-only handlers; SDK registration is independently checked."""

import asyncio
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import stat
import struct
import sys
import tempfile
from types import SimpleNamespace
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
    def test_registry_override_uses_its_own_machine_config(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "project.json"
            with patch.dict("os.environ", {"ROADCRAFT_REGISTRY": str(registry)}, clear=False):
                with patch.dict("os.environ", {"ROADCRAFT_CONFIG": ""}, clear=False):
                    settings = server.ServerSettings.defaults()
            self.assertEqual(settings.registry, registry.resolve())
            self.assertEqual(settings.config, (registry.parent / "local/machine.json").resolve())

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

    def test_unc_and_device_paths_are_rejected_before_resolution(self):
        paths = (r"\\server\share\file.pak", "//server/share/file.pak",
                 r"\\.\pipe\roadcraft", r"\\?\UNC\server\share\file.pak")
        for path in paths:
            with self.subTest(path=path):
                with patch.object(server.Path, "resolve", side_effect=AssertionError("resolution touched a remote path")):
                    with self.assertRaisesRegex(ValueError, "local absolute filesystem path"):
                        self.tools.inspect_file(path)

    def test_local_path_resolving_to_unc_is_rejected(self):
        with patch.object(server.Path, "resolve", return_value=server.Path(r"\\server\share\file.pak")):
            with self.assertRaisesRegex(ValueError, "local absolute filesystem path"):
                self.tools.inspect_file(str(self.package))

    @unittest.skipUnless(sys.platform == "win32", "Windows path syntax")
    def test_windows_reserved_device_and_stream_paths_reject_before_resolution(self):
        paths = (self.root / "NUL", self.root / "COM1.txt",
                 self.root / "ordinary.txt:secret")
        for path in paths:
            with self.subTest(path=str(path)):
                with patch.object(server.Path, "lstat", side_effect=AssertionError("unsafe path was inspected")):
                    with patch.object(server.Path, "resolve", side_effect=AssertionError("unsafe path was resolved")):
                        with self.assertRaisesRegex(ValueError, "local absolute filesystem path"):
                            self.tools.inspect_file(str(path))
        with self.assertRaisesRegex(server.core.RoadcraftError, "Drive-relative paths"):
            server.core._require_local_path(f"{self.root.drive}relative.txt")
        self.assertTrue(self.tools.verify_file(str(self.package), sha(self.package.read_bytes()))["passed"])

    @unittest.skipUnless(sys.platform == "win32", "Windows reparse attributes")
    def test_local_reparse_component_rejects_before_resolution(self):
        junction = self.root / "junction"
        original_lstat = server.Path.lstat

        def marked_reparse(path, *args, **kwargs):
            if path == junction:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return original_lstat(path, *args, **kwargs)

        with patch.object(server.Path, "lstat", new=marked_reparse):
            with patch.object(server.Path, "resolve", side_effect=AssertionError("reparse target was resolved")):
                with self.assertRaisesRegex(ValueError, "Reparse or symbolic-link"):
                    self.tools.inspect_file(str(junction / "remote.pak"))

    @unittest.skipUnless(sys.platform == "win32", "Windows reparse attributes")
    def test_nested_reparse_paths_reject_before_resolution(self):
        junction = self.root / "junction"
        manifest = self.root / "nested-files.json"
        manifest.write_text(json.dumps({"files": [{"path": "junction/remote.pak", "sha256": "0" * 64}]}))
        receipt = self.root / "nested-receipt.json"
        receipt.write_text(json.dumps({"captures": [{"path": "junction/remote.png", "sha256": "0" * 64}]}))
        canonical = self.root / "canonical"
        canonical.mkdir()
        (canonical / manifest.name).write_bytes(manifest.read_bytes())
        (canonical / receipt.name).write_bytes(receipt.read_bytes())
        original_lstat = server.Path.lstat
        original_resolve = server.Path.resolve

        def marked_reparse(path, *args, **kwargs):
            # A resolved receipt/manifest may have a different lexical parent
            # (for example, a Windows temp-directory alias). Identify the
            # unique fixture component instead of comparing whole paths.
            if path.name.casefold() == junction.name.casefold():
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return original_lstat(path, *args, **kwargs)

        def local_only_resolve(path, *args, **kwargs):
            if any(part.casefold() == junction.name.casefold() for part in path.parts):
                raise AssertionError("reparse target was resolved")
            if path == manifest or path == receipt:
                # Simulate a temp-directory alias changing its parent path.
                # An exact-path lstat mock missed this on hosted Windows CI.
                return canonical / path.name
            return original_resolve(path, *args, **kwargs)

        with patch.object(server.Path, "lstat", new=marked_reparse):
            with patch.object(server.Path, "resolve", new=local_only_resolve):
                with self.assertRaisesRegex(server.core.RoadcraftError, "Reparse or symbolic-link"):
                    self.tools.verify_manifest(str(manifest))
                with self.assertRaisesRegex(server.review.ReviewError, "Reparse or symbolic-link"):
                    self.tools.evidence_report([{"path": str(receipt)}])

    def test_nested_receipt_paths_cannot_resolve_unc(self):
        remote = r"\\server\share\capture.png"
        receipt = self.root / "nested.json"
        original_resolve = server.Path.resolve

        def local_only(path, *args, **kwargs):
            if server.core._is_remote_namespace(path):
                raise AssertionError("remote path reached resolve")
            return original_resolve(path, *args, **kwargs)

        documents = ({"captures": [{"path": remote, "sha256": "0" * 64}]},
                     {"variants": [{"report": remote, "reportSha256": "0" * 64}]})
        for document in documents:
            receipt.write_text(json.dumps(document))
            with self.subTest(document=document), patch.object(server.Path, "resolve", new=local_only):
                with self.assertRaisesRegex(server.review.ReviewError, "UNC and device evidence paths"):
                    self.tools.evidence_report([{"path": str(receipt)}])

    def test_nested_manifest_registry_and_config_paths_cannot_resolve_unc(self):
        remote = r"\\server\share\file.pak"
        original_resolve = server.Path.resolve

        def local_only(path, *args, **kwargs):
            if server.core._is_remote_namespace(path):
                raise AssertionError("remote path reached resolve")
            return original_resolve(path, *args, **kwargs)

        manifest = self.root / "remote-files.json"
        manifest.write_text(json.dumps({"files": [{"path": remote, "sha256": "0" * 64}]}))
        self.registry.write_text(json.dumps({"schemaVersion": 1, "accepted": {"package": {"path": remote}},
                                             "candidates": {}}))
        self.config.write_text(json.dumps({"schemaVersion": 1, "installedPackage": remote, "tools": {}}))
        with patch.object(server.Path, "resolve", new=local_only):
            with self.assertRaisesRegex(server.core.RoadcraftError, "UNC and device paths"):
                self.tools.verify_manifest(str(manifest))
            with self.assertRaisesRegex(server.core.RoadcraftError, "UNC and device paths"):
                self.tools.project_status()
            with self.assertRaisesRegex(server.core.RoadcraftError, "UNC and device paths"):
                self.tools.project_doctor()

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
