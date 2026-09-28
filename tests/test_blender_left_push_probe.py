"""Identity and result guards for the read-only D11 hierarchy diagnostic."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import blender_left_push_probe as probe  # noqa: E402


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _valid_result() -> dict:
    return {
        "schemaVersion": 1,
        "status": "IN_MEMORY_STATIC_PATH_MATCH",
        "asset": "cat_d11t",
        "blendSha256": probe.BLEND_SHA256,
        "repairedUsfSha256": probe.USF_SHA256,
        "blenderVersion": "5.2.0 LTS",
        "repairedPath": ("|@root|D11T_Rig.005|BoneChassis_cdt|"
                         "BoneBladeLift_cdt|IK_push_arm_left_base"),
        "repairedChildNames": ["IK_push_arm_left_tip", "IK_tilt_left_base"],
        "oldTiltBaseChain": ["BoneChassis_cdt", "BoneBladeLift_cdt", "IK_tilt_left_base"],
        "newTiltBaseChain": ["BoneChassis_cdt", "BoneBladeLift_cdt",
                             "IK_push_arm_left_base", "IK_tilt_left_base"],
        "newBoneWorldMatrixMaxError": 3.5762786865234375e-7,
        "tiltBasePoseMatrixMaxChange": 1.0766088962554932e-6,
        "tiltTipPoseMatrixMaxChange": 2.2687017917633057e-6,
        "newBoneEditLength": 0.25,
        "editLengthFromUsf": False,
        "blendSaved": False,
        "usfExported": False,
        "nativeBlendExportApproved": False,
    }


class BlenderLeftPushProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="roadcraft-left-push-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.blend = self.root / "cat_d11t.blend"
        self.blend.write_bytes(b"pinned blend")
        self.usf = self.root / "export.usf"
        self.usf.write_bytes(b"pinned repaired usf")
        self.blender = self.root / "blender.exe"
        self.blender.write_bytes(b"pinned blender")
        self.sdk = self.root / "sdk"
        (self.sdk / "saber/blender/lib/usf").mkdir(parents=True)
        (self.sdk / "saber/blender/lib/usf/scene.py").write_bytes(b"pinned sdk")
        inventory = self.root / "inventory.json"
        inventory_bytes = json.dumps({"sourceRoot": str(self.root)}).encode("utf-8")
        inventory.write_bytes(inventory_bytes)
        inventory_sha = _digest(inventory_bytes)
        self.registry = self.root / "project.json"
        self.registry.write_text(json.dumps({"accepted": {"authoringInventory": {
            "path": inventory.name, "sha256": inventory_sha}}}), encoding="utf-8")
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(probe, "INVENTORY_SHA256", inventory_sha).start()
        mock.patch.object(probe, "BLEND_SHA256", _digest(b"pinned blend")).start()
        mock.patch.object(probe, "USF_SHA256", _digest(b"pinned repaired usf")).start()
        mock.patch.object(probe, "BLENDER_SHA256", _digest(b"pinned blender")).start()
        mock.patch.object(probe, "SDK_PINS", {
            "saber/blender/lib/usf/scene.py": _digest(b"pinned sdk")}).start()
        mock.patch.object(probe, "_pinned_asset", return_value=(
            {}, self.root, {}, self.blend, self.usf)).start()

    def _run(self, side_effect=None):
        result = _valid_result()
        complete = subprocess.CompletedProcess([], 0, stdout=
            probe.RESULT_PREFIX + json.dumps(result) + "\n", stderr="")
        with mock.patch.object(probe.subprocess, "run", side_effect=side_effect,
                               return_value=complete) as run:
            output = probe.run_probe(registry_path=self.registry,
                                     blender_executable=self.blender,
                                     sdk_script_root=self.sdk)
        return output, run

    def test_emits_one_json_result_after_read_only_command(self) -> None:
        output, run = self._run()
        command = run.call_args.args[0]
        self.assertEqual(command[:4], [str(self.blender.resolve()), "--background",
                                        "--factory-startup", "--disable-autoexec"])
        self.assertNotIn("--candidate-usf", command)
        self.assertNotIn("--result", command)
        self.assertNotIn("--run", command)
        self.assertTrue(output["sourceUnchanged"])
        self.assertFalse(output["nativeBlendExportApproved"])

    def test_rejects_input_drift_before_blender_launch(self) -> None:
        self.blend.write_bytes(b"drift")
        with mock.patch.object(probe.subprocess, "run") as run:
            with self.assertRaisesRegex(probe.LeftPushProbeError, "source Blend"):
                probe.run_probe(registry_path=self.registry,
                                blender_executable=self.blender,
                                sdk_script_root=self.sdk)
            run.assert_not_called()

    def test_rejects_input_change_during_blender_process(self) -> None:
        def drift(*args, **kwargs):
            self.blend.write_bytes(b"changed during run")
            return subprocess.CompletedProcess(args[0], 0, stdout=
                probe.RESULT_PREFIX + json.dumps(_valid_result()) + "\n", stderr="")
        with self.assertRaisesRegex(probe.LeftPushProbeError, "source Blend after"):
            self._run(side_effect=drift)

    def test_rejects_linked_inventory_source_root_before_asset_resolution(self) -> None:
        linked_source = self.root / "linked-source-root"
        linked_source.mkdir()
        inventory_bytes = json.dumps({"sourceRoot": str(linked_source)}).encode("utf-8")
        inventory = self.root / "inventory.json"
        inventory.write_bytes(inventory_bytes)
        digest = _digest(inventory_bytes)
        self.registry.write_text(json.dumps({"accepted": {"authoringInventory": {
            "path": inventory.name, "sha256": digest}}}), encoding="utf-8")
        original_junction = getattr(Path, "is_junction", None)

        def is_junction(path):
            return path == linked_source or (original_junction(path) if original_junction else False)

        with (mock.patch.object(probe, "INVENTORY_SHA256", digest),
              mock.patch.object(Path, "is_junction", is_junction, create=True),
              mock.patch.object(probe, "_pinned_asset") as pinned,
              mock.patch.object(probe.subprocess, "run") as run):
            with self.assertRaisesRegex(probe.LeftPushProbeError, "crosses a link"):
                probe.run_probe(registry_path=self.registry,
                                blender_executable=self.blender,
                                sdk_script_root=self.sdk)
            pinned.assert_not_called()
            run.assert_not_called()

    def test_rejects_missing_or_duplicate_blender_result(self) -> None:
        with self.assertRaisesRegex(probe.LeftPushProbeError, "one diagnostic"):
            probe.parse_result("some Blender output\n")
        line = probe.RESULT_PREFIX + '{"schemaVersion": 1}'
        with self.assertRaisesRegex(probe.LeftPushProbeError, "one diagnostic"):
            probe.parse_result(line + "\n" + line)

    def test_rejects_incomplete_or_forged_match(self) -> None:
        with self.assertRaisesRegex(probe.LeftPushProbeError, "identity"):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps({
                "schemaVersion": 1, "status": "IN_MEMORY_STATIC_PATH_MATCH"}))
        result = _valid_result()
        result["blendSaved"] = True
        with self.assertRaisesRegex(probe.LeftPushProbeError, "no-write"):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps(result))
        result = _valid_result()
        result["newBoneWorldMatrixMaxError"] = 0.1
        with self.assertRaisesRegex(probe.LeftPushProbeError, "conflicts"):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps(result))
        result = _valid_result()
        result["tiltTipPoseMatrixMaxChange"] = float("nan")
        with self.assertRaisesRegex(probe.LeftPushProbeError, "metric"):
            probe.parse_result(probe.RESULT_PREFIX + json.dumps(result))

    def test_rejects_raw_file_parent_junction_and_registry_links(self) -> None:
        # Windows CI may not grant SeCreateSymbolicLinkPrivilege. Simulate the
        # OS link/junction reports and map resolution to a pinned target: if
        # production code resolves first, every one of these checks misses it.
        linked_file = self.root / "blend-link.blend"
        linked_file.write_bytes(self.blend.read_bytes())
        linked_parent = self.root / "linked-parent"
        linked_parent.mkdir()
        nested = linked_parent / "cat_d11t.blend"
        nested.write_bytes(self.blend.read_bytes())
        linked_sdk = self.root / "sdk-junction"
        linked_sdk.mkdir()
        linked_registry = self.root / "project-link.json"
        linked_registry.write_bytes(self.registry.read_bytes())
        original_resolve = Path.resolve
        original_symlink = Path.is_symlink
        original_junction = getattr(Path, "is_junction", None)

        def resolve(path, strict=False):
            if path in (linked_file, nested):
                return self.blend
            if path == linked_sdk:
                return self.sdk
            if path == linked_registry:
                return self.registry
            return original_resolve(path, strict=strict)

        def is_symlink(path):
            return path in (linked_file, linked_parent, linked_registry) or original_symlink(path)

        def is_junction(path):
            return path == linked_sdk or (original_junction(path) if original_junction else False)

        with (mock.patch.object(Path, "resolve", resolve),
              mock.patch.object(Path, "is_symlink", is_symlink),
              mock.patch.object(Path, "is_junction", is_junction, create=True)):
            with self.assertRaisesRegex(probe.LeftPushProbeError, "crosses a link"):
                probe.require_hash(linked_file, probe.BLEND_SHA256, "source Blend")
            with self.assertRaisesRegex(probe.LeftPushProbeError, "crosses a link"):
                probe.require_hash(nested, probe.BLEND_SHA256, "source Blend")
            with self.assertRaisesRegex(probe.LeftPushProbeError, "crosses a link"):
                probe.require_sdk_pins(linked_sdk)
            with mock.patch.object(probe.subprocess, "run") as run:
                with self.assertRaisesRegex(probe.LeftPushProbeError, "crosses a link"):
                    probe.run_probe(registry_path=linked_registry,
                                    blender_executable=self.blender,
                                    sdk_script_root=self.sdk)
                run.assert_not_called()


class BlenderLeftPushWorkerPureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with mock.patch.dict(sys.modules, {"bpy": SimpleNamespace()}):
            cls.worker = importlib.import_module("roadcraft.blender_left_push_worker")

    def test_exact_path_rejects_duplicate_or_missing_nodes(self) -> None:
        w = self.worker
        target = SimpleNamespace(name=w.NEW_BONE, children=[])
        lift = SimpleNamespace(name=w.PARENT, children=[target])
        chassis = SimpleNamespace(name="BoneChassis_cdt", children=[lift])
        rig = SimpleNamespace(name=w.ARMATURE, children=[chassis])
        root = SimpleNamespace(name="cat_d11t", children=[rig])
        self.assertIs(w.unique_node(root, w.USF_PATH), target)
        lift.children.append(SimpleNamespace(name=w.NEW_BONE, children=[]))
        with self.assertRaisesRegex(probe.LeftPushProbeError, "not unique"):
            w.unique_node(root, w.USF_PATH)

    def test_matrix_error_and_parent_chain_are_explicit(self) -> None:
        w = self.worker
        eye = [[float(row == col) for col in range(4)] for row in range(4)]
        shifted = [row[:] for row in eye]
        shifted[0][3] = 0.125
        self.assertEqual(w.max_matrix_error(eye, shifted), 0.125)
        parent = SimpleNamespace(name="parent", parent=None)
        child = SimpleNamespace(name="child", parent=parent)
        self.assertEqual(w.parent_chain(child), ["parent", "child"])


if __name__ == "__main__":
    unittest.main()
