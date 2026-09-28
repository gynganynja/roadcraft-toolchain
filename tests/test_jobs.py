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
from roadcraft import cli, jobs  # noqa: E402


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

    def recovery_fixture(self) -> dict:
        """A tiny accepted-package/rolled-back-transaction fixture, never a native run."""
        accepted = self.work / "accepted.pak"
        installed = self.work / "installed.pak"
        accepted.write_bytes(b"accepted package")
        installed.write_bytes(b"accepted package")
        accepted_sha = sha256(accepted.read_bytes()).hexdigest()
        registry = self.root / "project.json"
        registry.write_text(json.dumps({"schemaVersion": 1, "project": "fixture",
                                        "accepted": {"package": {"path": str(accepted),
                                                                 "sha256": accepted_sha}},
                                        "candidates": {}}), encoding="utf-8")
        legacy_receipt = self.work / "legacy_receipt.json"
        legacy_receipt.write_text(json.dumps({"status": "FAIL_ROLLBACK_PENDING",
                                              "baselineSha256": accepted_sha,
                                              "rollback": {"status": "BASELINE_RESTORED"}}),
                                  encoding="utf-8")
        legacy_lock = self.work / "legacy.lock.json"
        config = self.root / "machine.json"
        config.write_text(json.dumps({"schemaVersion": 1, "installedPackage": str(installed),
                                      "transactionReceipts": [str(legacy_receipt)],
                                      "transactionLocks": [str(legacy_lock)]}), encoding="utf-8")
        self.jobs_root.mkdir()
        run_id = "abandoned-native"
        run_dir = self.jobs_root / run_id
        run_dir.mkdir()
        receipt = run_dir / "receipt.json"
        receipt.write_text(json.dumps({"schemaVersion": 1, "runId": run_id,
                                       "status": "failed", "recoveryRequired": True,
                                       "steps": [{"id": "capture", "native": True,
                                                  "status": "failed"}]}), encoding="utf-8")
        lock = self.jobs_root / jobs.LOCK_NAME
        lock.write_text(json.dumps({"runId": run_id, "pid": 999999,
                                    "createdUtc": "2026-09-28T00:00:00Z"}), encoding="utf-8")
        return {"jobs_root": self.jobs_root, "run_id": run_id,
                "expected_lock_sha256": sha256(lock.read_bytes()).hexdigest(),
                "expected_receipt_sha256": sha256(receipt.read_bytes()).hexdigest(),
                "expected_installed_sha256": accepted_sha,
                "registry_path": registry,
                "expected_registry_sha256": sha256(registry.read_bytes()).hexdigest(),
                "config_path": config,
                "expected_config_sha256": sha256(config.read_bytes()).hexdigest()}

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

    def test_native_nonzero_exit_retains_lock_until_external_recovery(self) -> None:
        output = self.work / "unused.txt"
        command = [sys.executable, "-c", "raise SystemExit(7)"]
        recipe = self.recipe([self.step("native-fails", output, native=True,
                                        command=command)], phase="capture")
        with patch.object(jobs, "editor_processes", return_value=([], None)):
            result = jobs.run_recipe(recipe, "capture", self.jobs_root)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["recoveryRequired"])
        self.assertEqual(result["steps"][0]["exitCode"], 7)
        self.assertEqual(result["steps"][0]["status"], "failed")
        self.assertTrue((self.jobs_root / jobs.LOCK_NAME).is_file())
        self.assertEqual(json.loads((self.jobs_root / result["runId"] /
                                     "receipt.json").read_text()), result)

    def test_native_output_failure_retains_lock(self) -> None:
        output = self.work / "wrong.txt"
        command = [sys.executable, "-c",
                   "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('wrong')",
                   str(output)]
        recipe = self.recipe([self.step("native-wrong-output", output,
                                        native=True, command=command)], phase="capture")
        with patch.object(jobs, "editor_processes", return_value=([], None)):
            result = jobs.run_recipe(recipe, "capture", self.jobs_root)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["recoveryRequired"])
        self.assertEqual(result["steps"][0]["exitCode"], 0)
        self.assertIn("expected outputs", result["error"])
        self.assertTrue((self.jobs_root / jobs.LOCK_NAME).is_file())

    def test_native_preflight_failure_before_command_releases_lock(self) -> None:
        output = self.work / "out.txt"
        recipe = self.recipe([self.step("native-not-started", output,
                                        native=True)], phase="capture")
        self.input.write_text("stale", encoding="utf-8")
        with patch.object(jobs, "editor_processes", return_value=([], None)):
            result = jobs.run_recipe(recipe, "capture", self.jobs_root)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["recoveryRequired"])
        self.assertFalse((self.jobs_root / jobs.LOCK_NAME).exists())

    def test_prior_native_command_keeps_lock_if_later_step_fails(self) -> None:
        first = self.work / "first.txt"
        second = self.work / "second.txt"
        recipe = self.recipe([
            self.step("native-passes", first, native=True),
            self.step("later-fails", second,
                      command=[sys.executable, "-c", "raise SystemExit(8)"],
                      inputs=[{"path": str(first),
                               "sha256": sha256(b"ok").hexdigest()}]),
        ], phase="capture")
        with patch.object(jobs, "editor_processes", return_value=([], None)):
            result = jobs.run_recipe(recipe, "capture", self.jobs_root)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["recoveryRequired"])
        self.assertEqual([row["status"] for row in result["steps"]],
                         ["passed", "failed"])
        self.assertTrue((self.jobs_root / jobs.LOCK_NAME).is_file())

    def test_recovery_preview_is_read_only_and_applied_release_is_receipted(self) -> None:
        args = self.recovery_fixture()
        original_receipt = (self.jobs_root / args["run_id"] / "receipt.json").read_bytes()
        installed = self.work / "installed.pak"
        with (patch.object(jobs, "_pid_alive", return_value=False),
              patch.object(jobs, "editor_processes", return_value=([], None))):
            preview = jobs.recover_jobs(**args)
            self.assertEqual(preview["status"], "ready")
            self.assertFalse(preview["writesPerformed"])
            self.assertEqual(list((self.jobs_root / args["run_id"]).glob("job_recovery_*.json")), [])
            self.assertTrue((self.jobs_root / jobs.LOCK_NAME).is_file())
            result = jobs.recover_jobs(**args, dry_run=False)
        self.assertEqual(result["status"], "released")
        self.assertFalse((self.jobs_root / jobs.LOCK_NAME).exists())
        self.assertEqual((self.jobs_root / args["run_id"] / "receipt.json").read_bytes(),
                         original_receipt)
        self.assertEqual(installed.read_bytes(), b"accepted package")
        recovery_path = Path(result["recoveryReceiptPath"])
        recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
        self.assertEqual(recovery["status"], "released")
        self.assertEqual(sha256(recovery_path.read_bytes()).hexdigest(),
                         result["recoveryReceiptSha256"])

    def test_recovery_refuses_live_owner_or_active_editor(self) -> None:
        args = self.recovery_fixture()
        with patch.object(jobs, "_pid_alive", return_value=True):
            with self.assertRaisesRegex(jobs.JobError, "owner has exited"):
                jobs.recover_jobs(**args)
        with (patch.object(jobs, "_pid_alive", return_value=False),
              patch.object(jobs, "editor_processes", return_value=([{"pid": 42}], None))):
            with self.assertRaisesRegex(jobs.JobError, "authoring processes"):
                jobs.recover_jobs(**args)
        self.assertTrue((self.jobs_root / jobs.LOCK_NAME).is_file())

    def test_recovery_refuses_stale_evidence_and_unaccepted_install(self) -> None:
        args = self.recovery_fixture()
        stale = dict(args, expected_receipt_sha256="0" * 64)
        with patch.object(jobs, "_pid_alive", return_value=False):
            with self.assertRaisesRegex(jobs.JobError, "receipt identity"):
                jobs.recover_jobs(**stale)
        (self.work / "installed.pak").write_bytes(b"candidate package")
        with patch.object(jobs, "_pid_alive", return_value=False):
            with self.assertRaisesRegex(jobs.JobError, "package or transaction state"):
                jobs.recover_jobs(**args)
        self.assertTrue((self.jobs_root / jobs.LOCK_NAME).is_file())

    def test_recovery_refuses_pending_transaction_or_unlisted_state(self) -> None:
        args = self.recovery_fixture()
        legacy_lock = self.work / "legacy.lock.json"
        legacy_lock.write_text("pending", encoding="utf-8")
        with patch.object(jobs, "_pid_alive", return_value=False):
            with self.assertRaises(jobs.JobError):
                jobs.recover_jobs(**args)
        legacy_lock.unlink()
        config = Path(args["config_path"])
        data = json.loads(config.read_text())
        data["transactionLocks"] = []
        config.write_text(json.dumps(data), encoding="utf-8")
        args["expected_config_sha256"] = sha256(config.read_bytes()).hexdigest()
        with patch.object(jobs, "_pid_alive", return_value=False):
            with self.assertRaisesRegex(jobs.JobError, "enumerate transaction"):
                jobs.recover_jobs(**args)
        self.assertTrue((self.jobs_root / jobs.LOCK_NAME).is_file())

    def test_recovery_refuses_nonterminal_legacy_receipt_even_if_status_says_clear(self) -> None:
        args = self.recovery_fixture()
        legacy_receipt = self.work / "legacy_receipt.json"
        data = json.loads(legacy_receipt.read_text())
        data["status"] = "RUNNING"
        legacy_receipt.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(jobs, "_pid_alive", return_value=False):
            with self.assertRaisesRegex(jobs.JobError, "terminal rollback"):
                jobs.recover_jobs(**args)
        self.assertTrue((self.jobs_root / jobs.LOCK_NAME).is_file())

    def test_recovery_late_process_change_keeps_lock_and_failed_attempt(self) -> None:
        args = self.recovery_fixture()
        with (patch.object(jobs, "_pid_alive", return_value=False),
              patch.object(jobs, "editor_processes",
                           side_effect=[([], None), ([], None), ([{"pid": 42}], None)])):
            with self.assertRaisesRegex(jobs.JobError, "External state"):
                jobs.recover_jobs(**args, dry_run=False)
        self.assertTrue((self.jobs_root / jobs.LOCK_NAME).is_file())
        attempts = list((self.jobs_root / args["run_id"]).glob("job_recovery_*.json"))
        self.assertEqual(len(attempts), 1)
        self.assertEqual(json.loads(attempts[0].read_text())["status"], "release_failed")

    def test_recovery_cli_preview_does_not_require_apply(self) -> None:
        pins = self.recovery_fixture()
        args = cli.make_parser().parse_args([
            "jobs-recover", "--jobs-root", str(pins["jobs_root"]),
            "--run-id", pins["run_id"],
            "--expected-lock-sha256", pins["expected_lock_sha256"],
            "--expected-receipt-sha256", pins["expected_receipt_sha256"],
            "--expected-installed-sha256", pins["expected_installed_sha256"],
            "--expected-registry-sha256", pins["expected_registry_sha256"],
            "--expected-config-sha256", pins["expected_config_sha256"],
            "--registry", str(pins["registry_path"]),
            "--config", str(pins["config_path"]),
        ])
        with (patch.object(jobs, "_pid_alive", return_value=False),
              patch.object(jobs, "editor_processes", return_value=([], None))):
            result, passed = cli.execute(args)
        self.assertTrue(passed)
        self.assertEqual(result["status"], "ready")
        self.assertTrue((self.jobs_root / jobs.LOCK_NAME).is_file())


if __name__ == "__main__":
    unittest.main()
