"""Synthetic preflight and output verification for the Blender USF bridge."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from roadcraft import blender_bridge as bridge  # noqa: E402
from roadcraft.source import capture_source_inventory, file_sha256  # noqa: E402


class BlenderBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="roadcraft-blender-bridge-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(bridge, "TOOLCHAIN_ROOT", self.root).start()
        self.project = self.root / "project"
        self.source = self.project / "models/cat_d11t/export.usf"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"synthetic repaired USF")
        declaration = [{"asset": "cat_d11t", "exportMethod": "usf-repair",
                        "files": [{"path": "models/cat_d11t/export.usf", "role": "build-usf"}]}]
        inventory = capture_source_inventory(self.project, declaration)
        self.inventory = self.root / "inventory.json"
        self.inventory.write_text(json.dumps(inventory), encoding="utf-8")
        self.inventory_sha = file_sha256(self.inventory)
        self.blender = self.root / "blender.exe"
        self.blender.write_bytes(b"fake executable")
        self.sdk = self.root / "sdk"
        sdk_lib = self.sdk / "saber/blender/lib"
        (sdk_lib / "usf").mkdir(parents=True)
        (sdk_lib / "binary_io.py").write_text("# fixture\n", encoding="utf-8")
        (sdk_lib / "usf/scene.py").write_text("# fixture\n", encoding="utf-8")
        self.scratch = self.root / "local/roundtrip"
        self.receipt = self.root / "operations/roundtrip.json"

    def _run(self, *, dry_run: bool = True) -> dict:
        return bridge.run_usf_roundtrip(
            asset_name="cat_d11t", inventory_path=self.inventory,
            inventory_sha256=self.inventory_sha,
            blender_executable=self.blender, sdk_script_root=self.sdk,
            scratch_root=self.scratch, receipt_path=self.receipt,
            dry_run=dry_run,
        )

    @staticmethod
    def _version_or_helper(argv: list[str], **kwargs):
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="Blender 5.2.0 LTS\n")
        output = Path(argv[argv.index("--output") + 1])
        receipt = Path(argv[argv.index("--receipt") + 1])
        source = Path(argv[argv.index("--source") + 1])
        output.write_bytes(source.read_bytes())
        result = {"sourceSha256": file_sha256(source), "sourceBytes": source.stat().st_size,
                  "outputSha256": file_sha256(output), "outputBytes": output.stat().st_size,
                  "byteIdentical": True, "semanticSummaryEqual": True,
                  "sourceSemantic": {"nodes": 1}, "outputSemantic": {"nodes": 1}}
        receipt.write_text(json.dumps(result), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0)

    def test_dry_run_pins_input_without_writing(self) -> None:
        with mock.patch.object(bridge.subprocess, "run", side_effect=self._version_or_helper):
            result = self._run()
        self.assertEqual(result["status"], "DRY_RUN")
        self.assertEqual(result["sourceSha256"], file_sha256(self.source))
        self.assertFalse(result["nativeBlendExportApproved"])
        self.assertFalse(self.scratch.exists())
        self.assertFalse(self.receipt.exists())

    def test_run_independently_hashes_disposable_output(self) -> None:
        with mock.patch.object(bridge.subprocess, "run", side_effect=self._version_or_helper):
            result = self._run(dry_run=False)
        self.assertEqual(result["status"], "BYTE_IDENTICAL")
        self.assertTrue(result["sourceUnchanged"])
        self.assertTrue(result["scratchOutputDisposed"])
        self.assertEqual(result["outputSha256Observed"], file_sha256(self.source))
        self.assertEqual(json.loads(self.receipt.read_text())["status"], "BYTE_IDENTICAL")
        self.assertEqual(list(self.scratch.iterdir()), [])
        self.assertEqual(self.source.read_bytes(), b"synthetic repaired USF")

    def test_rejects_stale_pin_and_external_scratch(self) -> None:
        self.source.write_bytes(b"changed")
        with self.assertRaisesRegex(bridge.BlenderBridgeError, "differs"):
            self._run()
        self.source.write_bytes(b"synthetic repaired USF")
        with mock.patch.object(bridge.subprocess, "run", side_effect=self._version_or_helper):
            with self.assertRaisesRegex(bridge.BlenderBridgeError, "scratch root"):
                bridge.run_usf_roundtrip(
                    asset_name="cat_d11t", inventory_path=self.inventory,
                    inventory_sha256=self.inventory_sha,
                    blender_executable=self.blender, sdk_script_root=self.sdk,
                    scratch_root=self.root / "outside", receipt_path=self.receipt,
                )

    def test_forged_helper_hash_cannot_claim_byte_identity(self) -> None:
        def forged(argv: list[str], **kwargs):
            result = self._version_or_helper(argv, **kwargs)
            if "--version" not in argv:
                receipt = Path(argv[argv.index("--receipt") + 1])
                data = json.loads(receipt.read_text())
                data["outputSha256"] = "0" * 64
                receipt.write_text(json.dumps(data))
            return result

        with mock.patch.object(bridge.subprocess, "run", side_effect=forged):
            result = self._run(dry_run=False)
        self.assertEqual(result["status"], "HELPER_MISMATCH")
        self.assertTrue(self.receipt.is_file())


if __name__ == "__main__":
    unittest.main()
