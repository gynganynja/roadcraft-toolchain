from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import jobs  # noqa: E402


class JobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / "work space"
        self.work.mkdir()
        self.jobs_root = self.root / "jobs"
        self.input = self.work / "input.txt"
        self.input.write_text("pinned", encoding="utf-8")

    def recipe(self, steps: list[dict], *, phase: str = "build") -> Path:
        source = self.root / "recipe.json"
        source.write_text(json.dumps({"schemaVersion": 1, "name": "fixture",
                                      "phases": {phase: steps}}), encoding="utf-8")
        return source

    def step(self, step_id: str, output: Path, *, native: bool = False,
             command: list[str] | None = None, inputs: list[dict] | None = None,
             timeout: int = 5) -> dict:
        if command is None:
            command = [sys.executable, "-c",
                       "import sys; from pathlib import Path; Path(sys.argv[1]).write_text('ok')",
                       str(output)]
        return {"id": step_id, "command": command, "cwd": str(self.work),
                "inputs": inputs if inputs is not None else [
                    {"path": str(self.input), "sha256": sha256(b"pinned").hexdigest()}],
                "outputs": [{"path": str(output), "sha256": sha256(b"ok").hexdigest()}],
                "timeoutSeconds": timeout, "minFreeBytes": 1, "native": native}

    def test_dry_run_is_read_only_and_explicit_argv_is_preserved(self) -> None:
        output = self.work / "output.txt"
        recipe = self.recipe([self.step("make", output)], phase="inspect")
        result = jobs.run_recipe(recipe, "inspect", self.jobs_root, dry_run=True)
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse(self.jobs_root.exists())
        self.assertFalse(output.exists())
        self.assertEqual(result["steps"][0]["command"][0], str(Path(sys.executable).resolve()))

    def test_ordered_steps_persist_receipt_and_logs(self) -> None:
        first = self.work / "first.txt"
        second = self.work / "second.txt"
        steps = [self.step("first", first),
                 self.step("second", second, inputs=[
                     {"path": str(first), "sha256": sha256(b"ok").hexdigest()}])]
        recipe = self.recipe(steps)
        preview = jobs.run_recipe(recipe, "build", self.jobs_root, dry_run=True)
        self.assertTrue(preview["steps"][1]["inputs"][0]["generatedByPreviousStep"])
        result = jobs.run_recipe(recipe, "build", self.jobs_root)
        self.assertEqual(result["status"], "passed")
        self.assertEqual([row["id"] for row in result["steps"]], ["first", "second"])
        self.assertTrue(all(row["status"] == "passed" for row in result["steps"]))
        run_dir = self.jobs_root / result["runId"]
        self.assertEqual(json.loads((run_dir / "receipt.json").read_text()), result)
        self.assertTrue((run_dir / "first.log").is_file())
        self.assertTrue((run_dir / "second.log").is_file())
        self.assertFalse((run_dir / ".first.log.partial").exists())
        self.assertEqual(result["steps"][0]["logSha256"],
                         sha256((run_dir / "first.log").read_bytes()).hexdigest())
        self.assertFalse((self.jobs_root / jobs.LOCK_NAME).exists())

    def test_stale_pin_and_missing_output_fail_closed(self) -> None:
        output = self.work / "missing.txt"
        step = self.step("missing", output, command=[sys.executable, "-c", "pass"])
        recipe = self.recipe([step])
        self.input.write_text("changed", encoding="utf-8")
        with self.assertRaises(jobs.JobError):
            jobs.run_recipe(recipe, "build", self.jobs_root, dry_run=True)
        self.assertFalse(self.jobs_root.exists())
        self.input.write_text("pinned", encoding="utf-8")
        result = jobs.run_recipe(recipe, "build", self.jobs_root)
        self.assertEqual(result["status"], "failed")
        self.assertIn("expected outputs", result["error"])
        self.assertFalse((self.jobs_root / jobs.LOCK_NAME).exists())

    def test_existing_lock_refuses_run_and_reports_interruption(self) -> None:
        output = self.work / "out.txt"
        recipe = self.recipe([self.step("make", output)])
        self.jobs_root.mkdir()
        run_id = "stale-run"
        run_dir = self.jobs_root / run_id
        run_dir.mkdir()
        (run_dir / "receipt.json").write_text(json.dumps({"status": "running", "runId": run_id}))
        (self.jobs_root / jobs.LOCK_NAME).write_text(json.dumps({"runId": run_id, "pid": 999999}))
        with self.assertRaises(jobs.JobBusy):
            jobs.run_recipe(recipe, "build", self.jobs_root)
        with patch.object(jobs, "_pid_alive", return_value=False):
            state = jobs.inspect_jobs(self.jobs_root)
        self.assertTrue(state["recoveryRequired"])
        self.assertFalse(state["ownerAlive"])

    def test_current_pid_liveness_probe_is_read_only(self) -> None:
        self.assertTrue(jobs._pid_alive(os.getpid()))

    def test_native_step_refuses_active_authoring_process(self) -> None:
        output = self.work / "out.txt"
        recipe = self.recipe([self.step("make", output, native=True)], phase="capture")
        with patch.object(jobs, "editor_processes", return_value=([{"pid": 42, "name": "IntegrationStudio.exe"}], None)):
            with self.assertRaises(jobs.JobError):
                jobs.run_recipe(recipe, "capture", self.jobs_root, dry_run=True)
        self.assertFalse(self.jobs_root.exists())

    def test_native_timeout_retains_recovery_lock(self) -> None:
        output = self.work / "out.txt"
        sleepy = [sys.executable, "-c", "import time; time.sleep(2)"]
        recipe = self.recipe([self.step("sleep", output, native=True,
                                        command=sleepy, timeout=1)], phase="test")
        with patch.object(jobs, "editor_processes", return_value=([], None)):
            result = jobs.run_recipe(recipe, "test", self.jobs_root)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["recoveryRequired"])
        self.assertEqual(result["steps"][0]["status"], "timed_out")
        self.assertTrue((self.jobs_root / jobs.LOCK_NAME).exists())


if __name__ == "__main__":
    unittest.main()
