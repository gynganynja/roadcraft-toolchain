from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from roadcraft import cli, core, mcp_server, project_context as context


class ProjectContextTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.env = mock.patch.dict("os.environ", {"ROADCRAFT_REGISTRY": "", "ROADCRAFT_CONFIG": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.a = self.root / "mod_a/project.json"
        self.b = self.root / "mod_b/project.json"
        for path in (self.a, self.b):
            path.parent.mkdir()
            path.write_text(json.dumps({"schemaVersion": 1, "project": path.parent.name,
                                        "accepted": {}, "candidates": {}}))

    def test_selection_is_explicit_then_environment_then_nearest_mod(self):
        child = self.a.parent / "sources/models"
        child.mkdir(parents=True)
        self.assertEqual(context.registry_path(cwd=child), self.a)
        with mock.patch.dict("os.environ", {"ROADCRAFT_REGISTRY": str(self.b)}):
            self.assertEqual(context.registry_path(cwd=child), self.b)
            self.assertEqual(context.registry_path(self.a, cwd=child), self.a)

    def test_shared_checkout_does_not_implicitly_select_historical_registry(self):
        before = (context.TOOLCHAIN_ROOT / "project.json").read_bytes()
        with self.assertRaisesRegex(core.RoadcraftError, "No mod selected"):
            context.registry_path(cwd=context.TOOLCHAIN_ROOT / "src")
        self.assertEqual(context.registry_path(context.TOOLCHAIN_ROOT / "project.json"),
                         context.TOOLCHAIN_ROOT / "project.json")
        self.assertEqual((context.TOOLCHAIN_ROOT / "project.json").read_bytes(), before)

    def test_status_and_mcp_use_selected_mod_from_nested_working_folder(self):
        with mock.patch.object(Path, "cwd", return_value=self.b.parent):
            state, passed = cli.execute(cli.make_parser().parse_args(["status"]))
            settings = mcp_server.ServerSettings.defaults()
        self.assertTrue(passed)
        self.assertEqual(state["project"], "mod_b")
        self.assertEqual(settings.registry, self.b)
        self.assertEqual(settings.config, self.b.parent / "local/machine.json")
        self.assertFalse(state["configFound"])
        self.assertIsNone(state["installed"])

    def test_recipe_jobs_belong_to_recipe_mod_even_when_launched_from_other_mod(self):
        recipe = self.a.parent / "recipe.json"
        recipe.write_text(json.dumps({"defaults": {"cwd": str(self.a.parent)}}))
        with mock.patch.object(Path, "cwd", return_value=self.b.parent):
            with mock.patch.object(cli.jobs, "run_recipe", return_value={"status": "dry_run"}) as run:
                cli.execute(cli.make_parser().parse_args(["build", "--recipe", str(recipe)]))
                self.assertEqual(run.call_args.args[2], self.a.parent / "jobs")
            with mock.patch.object(cli.jobs, "summarize_jobs", return_value={}) as summary:
                cli.execute(cli.make_parser().parse_args(["jobs-summary"]))
                self.assertEqual(summary.call_args.args[0], self.b.parent / "jobs")

    def test_explicit_jobs_and_config_paths_override_defaults(self):
        custom = self.root / "custom"
        self.assertEqual(context.jobs_path(custom, registry=self.a), custom)
        self.assertEqual(context.config_path(custom, registry=self.a), custom)
        with mock.patch.dict("os.environ", {"ROADCRAFT_CONFIG": str(custom)}):
            self.assertEqual(context.config_path(registry=self.b), custom)

    def test_unconfigured_project_status_fails_but_file_inspection_does_not_need_project(self):
        with mock.patch.object(Path, "cwd", return_value=self.root):
            with self.assertRaisesRegex(core.RoadcraftError, "No mod selected"):
                cli.execute(cli.make_parser().parse_args(["status"]))
            result, passed = cli.execute(cli.make_parser().parse_args(
                ["verify", "--file", str(self.a), "--sha256", core.sha256_file(self.a)]))
        self.assertTrue(passed)
        self.assertTrue(result["matchesExpected"])

    def test_unselected_doctor_does_not_borrow_checkout_machine_config(self):
        with mock.patch.object(Path, "cwd", return_value=context.TOOLCHAIN_ROOT):
            with mock.patch.object(cli.core, "doctor", return_value={}) as doctor:
                result, passed = cli.execute(cli.make_parser().parse_args(["doctor"]))
        self.assertTrue(passed)
        doctor.assert_called_once_with(None)
        self.assertFalse(result["configFound"])
        self.assertIsNone(result["configPath"])
