"""Baseline capture must keep the accepted source mount and scene identity."""

from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from roadcraft import native_baseline_capture as baseline
from roadcraft import native_baseline_postflight as postflight


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BaselineSourceIsolationTests(unittest.TestCase):
    def test_editor_mount_rejects_a_candidate_source_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            accepted = root / "accepted" / "p"
            config = accepted / "config" / "editor.cfg"
            config.parent.mkdir(parents=True)
            actual = accepted.resolve(strict=True).as_posix()
            config.write_text(
                "  ModsSourceLocal: " + actual + "/mods_source\n"
                "  ProjectPath: " + actual + "/.project\n", encoding="utf-8")
            self.assertEqual(baseline._mount(accepted, digest)["modsSourceLocal"],
                             actual + "/mods_source")
            config.write_text(
                "  ModsSourceLocal: " + (root / "candidate" / "p").as_posix()
                + "/mods_source\n"
                "  ProjectPath: " + actual + "/.project\n", encoding="utf-8")
            with self.assertRaisesRegex(baseline.BaselineCaptureError,
                                        "does not mount the accepted project"):
                baseline._mount(accepted, digest)

    def test_contract_rejects_changed_validation_scene(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            accepted = root / "accepted" / "p"
            candidate = root / "candidate"
            scene_rel = Path("mods_source/xscenes/mods/maroon/maroon.scn")
            scene = accepted / scene_rel
            scene.parent.mkdir(parents=True)
            scene.write_bytes(b"same scene")
            candidate_scene = candidate / "p" / scene_rel
            candidate_scene.parent.mkdir(parents=True)
            candidate_scene.write_bytes(b"different scene")
            runner = Mock()
            runner.NATIVE = root / "native"
            runner.RUNS = runner.NATIVE / "baseline_runs"
            runner.HERE = candidate
            runner.WORKSPACE = root / "sdk"
            runner.SCENES = {"maroon": "maroon/maroon.scn"}
            runner.sha = digest
            with self.assertRaisesRegex(baseline.BaselineCaptureError,
                                        "validation scenes differ"):
                baseline._contract(runner, "a1b2c3d4", accepted,
                                   root / "accepted.pak", "a" * 64, {},
                                   ("maroon",),
                                   ("front_seat",), {"front_seat": ((0, 0, 0),
                                                                     (1, 0, 0))})

    def test_postflight_rejects_ambiguous_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_bytes(b'{"status":"ready","status":"failed"}')
            with self.assertRaises(postflight.BaselinePostflightError):
                postflight._json(path, digest(path), "baseline plan")


if __name__ == "__main__":
    unittest.main()
