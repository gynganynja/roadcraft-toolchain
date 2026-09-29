from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from roadcraft import core, jobs


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.jobs = self.root / "jobs"
        self.recipe = self.root / "recipe.json"
        self.input = self.root / "source.txt"
        self.input.write_text("one")

    def step(self, name, *, inputs=None, depends=(), text="ok"):
        return {"id": name, "command": [sys.executable, "-B", "-c",
                "from pathlib import Path; import sys; Path(sys.argv[1]).write_text(sys.argv[2])",
                str(self.root / f"{name}.txt"), text], "cwd": str(self.root),
                "inputs": inputs or [], "outputs": [{"path": str(self.root / f"{name}.txt")}],
                "timeoutSeconds": 15, "minFreeBytes": 0, "native": False,
                "cacheable": True, "dependsOn": list(depends)}

    def run_steps(self, steps, **kwargs):
        self.recipe.write_text(json.dumps({"schemaVersion": 1, "name": "fixture", "phases": {"build": steps}}))
        return jobs.run_recipe(self.recipe, "build", self.jobs, incremental_build=True, **kwargs)

    def test_second_run_reuses_bytes_and_records_original_receipt(self):
        step = self.step("models")
        first = self.run_steps([step])
        second = self.run_steps([step])
        self.assertEqual(first["status"], "passed")
        self.assertEqual(second["steps"][0]["status"], "cached")
        self.assertEqual(second["steps"][0]["reusedFrom"]["runId"], first["runId"])
        self.assertEqual(second["incremental"]["executedSteps"], 0)
        summary = jobs.summarize_jobs(self.jobs)
        self.assertEqual(len(summary["runs"]), 2)
        self.assertEqual(summary["runs"][-1]["reusedSteps"], 1)
        self.assertIsInstance(summary["runs"][-1]["elapsedSeconds"], float)

    def test_changed_output_and_missing_output_force_execution(self):
        step = self.step("models")
        self.run_steps([step])
        output = self.root / "models.txt"
        output.write_text("tampered")
        self.assertEqual(self.run_steps([step])["steps"][0]["status"], "passed")
        output.unlink()
        self.assertEqual(self.run_steps([step])["steps"][0]["status"], "passed")

    def test_changed_scoped_input_keeps_independent_step_and_rebuilds_consumer(self):
        def steps():
            pin = {"path": str(self.input), "sha256": core.sha256_file(self.input)}
            return [self.step("models"), self.step("textures", inputs=[pin], text=self.input.read_text()),
                    self.step("package", depends=["models", "textures"])]
        self.run_steps(steps())
        self.input.write_text("two")
        result = self.run_steps(steps())
        self.assertEqual([s["status"] for s in result["steps"]], ["cached", "passed", "passed"])

    def test_stale_pin_is_failure_even_with_previous_cached_success(self):
        step = self.step("models", inputs=[{"path": str(self.input), "sha256": core.sha256_file(self.input)}])
        self.run_steps([step])
        self.input.write_text("changed")
        result = self.run_steps([step])
        self.assertEqual(result["status"], "failed")
        self.assertIn("Stale or missing input", result["error"])

    def test_missing_companion_in_output_tree_forces_rebuild(self):
        step = self.step("import")
        tree = self.root / "compiled"
        step["outputTrees"] = [str(tree)]
        step["command"] = [sys.executable, "-B", "-c",
            "from pathlib import Path; import sys; p=Path(sys.argv[1]); p.mkdir(exist_ok=True); "
            "(p/'resource').write_text('descriptor'); Path(sys.argv[2]).write_text('ok')",
            str(tree), str(self.root / "import.txt")]
        self.run_steps([step])
        self.assertEqual(self.run_steps([step])["steps"][0]["status"], "cached")
        (tree / "resource").unlink()
        self.assertEqual(self.run_steps([step])["steps"][0]["status"], "passed")

    def test_tampered_receipt_is_not_reused(self):
        step = self.step("models")
        first = self.run_steps([step])
        receipt = self.jobs / first["runId"] / "receipt.json"
        receipt.write_text(receipt.read_text() + " ")
        self.assertEqual(self.run_steps([step])["steps"][0]["status"], "passed")

    def test_failure_does_not_seed_cache(self):
        good, bad = self.step("models"), self.step("fails")
        bad["command"] = [sys.executable, "-B", "-c", "raise SystemExit(7)"]
        result = self.run_steps([good, bad])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.run_steps([good])["steps"][0]["status"], "passed")

    def test_environment_and_command_changes_force_execution(self):
        step = self.step("models")
        self.run_steps([step])
        with patch.dict(os.environ, {"ROADCRAFT_TEST_SETTING": "changed"}):
            self.assertEqual(self.run_steps([step])["steps"][0]["status"], "passed")
        self.assertEqual(self.run_steps([self.step("models", text="different")])["steps"][0]["status"], "passed")

    def test_dry_run_is_read_only_and_native_cache_refused(self):
        step = self.step("models")
        result = self.run_steps([step], dry_run=True)
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse(self.jobs.exists())
        step["native"] = True
        with self.assertRaisesRegex(jobs.JobError, "isolated"):
            self.run_steps([step])

    def test_dependency_order_and_capture_cache_refused(self):
        with self.assertRaisesRegex(jobs.JobError, "earlier"):
            self.run_steps([self.step("models", depends=["future"])])
        self.recipe.write_text(json.dumps({"schemaVersion": 1, "name": "fixture",
                                          "phases": {"capture": [self.step("capture")]}}))
        with self.assertRaisesRegex(jobs.JobError, "non-capture"):
            jobs.load_recipe(self.recipe, "capture")

    def test_existing_lock_still_blocks_cache_hit(self):
        step = self.step("models")
        self.run_steps([step])
        (self.jobs / jobs.LOCK_NAME).write_text('{}')
        with self.assertRaises(jobs.JobBusy):
            self.run_steps([step])

    def test_unopted_step_always_runs_and_full_run_bypasses_cache(self):
        step = self.step("models")
        self.run_steps([step])
        full = jobs.run_recipe(self.recipe, "build", self.jobs)
        self.assertEqual(full["steps"][0]["status"], "passed")
        step["cacheable"] = False
        self.run_steps([step])
        self.assertEqual(self.run_steps([step])["steps"][0]["status"], "passed")
