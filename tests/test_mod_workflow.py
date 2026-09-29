from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from roadcraft import cli, core, jobs, mod_workflow as workflow


class ModWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def scaffold(self, kind="material"):
        root = self.root / kind
        workflow.scaffold(root, "trail_mod", Path(sys.executable), kind=kind)
        return root

    def configure(self, root):
        original = root / "settings.txt"
        original.write_text("original settings")
        builder = root / "tools/build.py"
        builder.write_text("from pathlib import Path\nimport sys\np=Path('reports')\np.mkdir(exist_ok=True)\n(p/(sys.argv[1]+'.json')).write_text('{}')\n")
        spec = json.loads((root / "mod.json").read_text())
        spec["sourceFiles"] = ["settings.txt", "tools/build.py"]
        (root / "mod.json").write_text(json.dumps(spec))
        template = json.loads((root / "recipe-template.json").read_text())
        template["defaults"].update(native=False, minFreeBytes=0)
        (root / "recipe-template.json").write_text(json.dumps(template))
        return original

    def test_nonvehicle_mod_build_runs_with_own_receipts_and_no_truck_checks(self):
        root = self.scaffold()
        original = self.configure(root)
        recipe = root / "recipes/build-001.json"
        workflow.make_recipe(root, recipe)
        plan = jobs.load_recipe(recipe, "build")
        self.assertEqual([s["id"] for s in plan["steps"]], ["prepare", "package"])
        receipt, passed = cli.execute(cli.make_parser().parse_args(
            ["build", "--recipe", str(recipe), "--apply"]))
        self.assertTrue(passed)
        self.assertEqual(receipt["status"], "passed")
        self.assertTrue((root / "jobs" / receipt["runId"] / "receipt.json").is_file())
        self.assertEqual(original.read_text(), "original settings")
        self.assertFalse(json.loads((root / "project.json").read_text())["accepted"])

    def test_vehicle_kind_keeps_shared_checks(self):
        root = self.scaffold("vehicle")
        self.configure(root)
        recipe = root / "recipes/build-001.json"
        workflow.make_recipe(root, recipe)
        ids = [s["id"] for s in jobs.load_recipe(recipe, "build")["steps"]]
        self.assertIn("vehicle-check-source", ids)
        self.assertIn("vehicle-check-compiled", ids)

    def test_adoption_preserves_existing_sources_history_and_instructions(self):
        root = self.root / "existing"
        root.mkdir()
        originals = {"README.md": b"existing readme", "AGENTS.md": b"existing instructions\r\n",
                     ".gitignore": b"private/\r\n", ".git/HEAD": b"ref: refs/heads/author\n",
                     "source/model.blend": b"original source", "original.pak": b"original package"}
        for name, content in originals.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        result = workflow.scaffold(root, "existing_mod", Path(sys.executable), adopt=True,
                                   package=root / "original.pak")
        for name, content in originals.items():
            if name in ("AGENTS.md", ".gitignore"):
                self.assertTrue((root / name).read_bytes().startswith(content))
            else:
                self.assertEqual((root / name).read_bytes(), content)
        registry = core.read_registry(root / "project.json")
        self.assertEqual(registry["accepted"], {})
        self.assertEqual(registry["candidates"]["imported"]["package"]["sha256"],
                         core.sha256_file(root / "original.pak"))
        self.assertTrue(result["adopted"])
        self.assertFalse(result["installed"])

    def test_conflicting_adoption_refuses_before_any_write(self):
        root = self.root / "existing"
        (root / "local").mkdir(parents=True)
        existing = root / "local/machine.json"
        existing.write_bytes(b"preserve this configuration")
        with self.assertRaisesRegex(core.RoadcraftError, "already exists"):
            workflow.scaffold(root, "existing_mod", Path(sys.executable), adopt=True)
        self.assertEqual([p for p in root.rglob('*') if p.is_file()], [existing])
        self.assertEqual(existing.read_bytes(), b"preserve this configuration")

    def test_source_changes_invalidate_recipe_and_recipe_is_never_overwritten(self):
        root = self.scaffold("tuning")
        source = self.configure(root)
        recipe = root / "recipes/build-001.json"
        workflow.make_recipe(root, recipe)
        before = recipe.read_bytes()
        source.write_text("modified settings")
        with self.assertRaises(jobs.JobError):
            jobs.run_recipe(recipe, "build", root / "jobs", dry_run=True)
        with self.assertRaisesRegex(core.RoadcraftError, "already exists"):
            workflow.make_recipe(root, recipe)
        self.assertEqual(recipe.read_bytes(), before)
        self.assertFalse((root / "jobs").exists())

    def test_wrapper_selects_its_mod_from_another_cwd_and_overrides_unrelated_registry(self):
        root = self.scaffold()
        env = dict(os.environ, ROADCRAFT_REGISTRY=str(self.root / "unrelated.json"),
                   ROADCRAFT_CONFIG=str(self.root / "unrelated-config.json"))
        completed = subprocess.run([sys.executable, "-B", str(root / "tools/roadcraft.py"), "status", "--json"],
                                   cwd=self.root, env=env, capture_output=True, text=True, check=True)
        result = json.loads(completed.stdout)
        self.assertEqual(result["registryPath"], str(root / "project.json"))
        self.assertEqual(result["configPath"], str(root / "local/machine.json"))
        self.assertEqual(result["project"], "trail_mod")

    def test_invalid_recipe_is_rejected_without_writing_output(self):
        root = self.scaffold()
        self.configure(root)
        path = root / "recipe-template.json"
        template = json.loads(path.read_text())
        template["phases"]["build"][0]["dependsOn"] = ["package"]
        path.write_text(json.dumps(template))
        output = root / "recipes/bad.json"
        with self.assertRaisesRegex(jobs.JobError, "earlier steps"):
            workflow.make_recipe(root, output)
        self.assertFalse(output.exists())
