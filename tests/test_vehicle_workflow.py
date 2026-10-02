from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from roadcraft import cli, core, incremental, jobs, ps_format, vehicle_workflow as workflow


class VehicleWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ("truck.bro", "truck.cls", "truck.tpl"):
            (self.root / name).write_text("fixture")

    def enhanced(self):
        stages = [{"id": stage, "command": [sys.executable, "-B", "-c", "pass"],
                   "outputs": [{"path": str(self.root / f"{stage}.out")}], "cacheable": True}
                  for stage in ("prepare", "models", "import", "generate", "package")]
        doc = {"schemaVersion": 1, "name": "fixture", "defaults": {"cwd": str(self.root),
               "timeoutSeconds": 20, "minFreeBytes": 0, "native": False},
               "phases": {"build": stages, "test": [dict(stages[-1], id="validate")]}}
        result = workflow.enhance_recipe(doc, truck_bro=self.root / "truck.bro",
                                        compiled_class=self.root / "truck.cls", model=self.root / "truck.tpl",
                                        python=Path(sys.executable), reports=self.root / "reports")
        self.assertEqual(len(doc["phases"]["build"]), 5)
        return result

    def test_checks_are_before_models_and_packaging_and_never_cached(self):
        result = self.enhanced()
        steps = result["phases"]["build"]
        self.assertEqual([s["id"] for s in steps], ["prepare", "vehicle-check-source", "models", "import",
                                                  "generate", "vehicle-check-compiled", "package"])
        self.assertFalse(steps[1]["cacheable"])
        self.assertFalse(steps[5]["cacheable"])
        self.assertIn("vehicle-check-compiled", steps[-1]["dependsOn"])
        self.assertEqual(result["phases"]["test"][0]["id"], "vehicle-check-final")
        self.assertEqual(len(result["phases"]["test"][0]["inputs"]), 3)
        self.assertTrue(any(p["path"].endswith("bro_lint.py") for p in result["inputs"]))
        recipe = self.root / "recipe.json"
        recipe.write_text(json.dumps(result))
        self.assertEqual(len(jobs.load_recipe(recipe, "build")["steps"]), 7)

    def test_old_recipe_requires_regeneration(self):
        with self.assertRaisesRegex(core.RoadcraftError, "generate a new recipe"):
            workflow.require_checks({"phases": {"build": []}}, "build")
        workflow.require_checks(self.enhanced(), "build")

    def test_new_cli_dependency_change_requires_recipe_regeneration(self):
        runtime = self.root / "runtime"
        runtime.mkdir()
        for module in Path(workflow.__file__).parent.glob("*.py"):
            (runtime / module.name).write_text("original shared module")
        with mock.patch.object(workflow, "__file__", str(runtime / "vehicle_workflow.py")):
            result = self.enhanced()
        recipe = self.root / "recipe.json"
        recipe.write_text(json.dumps(result))
        self.assertEqual(jobs.run_recipe(recipe, "build", self.root / "jobs", dry_run=True)["status"],
                         "dry_run")
        (runtime / "onboard.py").write_text("changed shared CLI dependency")
        with self.assertRaises(jobs.JobError):
            jobs.run_recipe(recipe, "build", self.root / "jobs", dry_run=True)
        self.assertFalse((self.root / "jobs").exists())

    def test_every_module_the_cli_can_import_is_pinned(self):
        # load_volume, native_suspension, tracks and physics_bench were once imported but unpinned
        import ast
        package = Path(workflow.__file__).parent
        seen, todo = set(), ["__main__.py", "cli.py"]
        while todo:
            name = todo.pop()
            if name in seen:
                continue
            seen.add(name)
            for node in ast.walk(ast.parse((package / name).read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.level == 1:
                    names = [node.module.split(".")[0]] if node.module else [a.name for a in node.names]
                    todo.extend(f"{n}.py" for n in names if (package / f"{n}.py").exists())
        self.assertEqual(sorted(seen - set(workflow.RUNTIME_FILES)), [])

    def test_source_error_stops_before_model_command(self):
        result = self.enhanced()
        bro = self.root / "truck.bro"
        bro.write_text(ps_format.dumps({"truckSettings": {"suspensionCollection": {"front": {
            "height": .2, "min": -.1, "max": .3, "strength": .03}}, "wheelSlots": []}}))
        result["phases"]["build"][0]["outputs"] = [{"path": str(bro)}]
        result["defaults"]["env"] = {"PYTHONPATH": str(Path(cli.__file__).resolve().parents[1])}
        recipe = self.root / "recipe.json"
        recipe.write_text(json.dumps(result))
        receipt = jobs.run_recipe(recipe, "build", self.root / "jobs")
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual([s["id"] for s in receipt["steps"]], ["prepare", "vehicle-check-source"])
        report = json.loads((self.root / "reports/vehicle-check-source.json").read_text())
        self.assertGreater(report["errors"], 0)

    def test_report_cannot_overwrite_bro(self):
        bro = self.root / "truck.bro"
        bro.write_text("truckSettings = {}")
        before = bro.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["lint-bro", str(bro), "--report", str(bro)])
        self.assertEqual(code, 2)
        self.assertEqual(bro.read_bytes(), before)

    def test_starter_has_no_accepted_identity_and_requires_explicit_sources(self):
        dest = self.root / "new_vehicle"
        result = workflow.scaffold(dest, "new_vehicle", Path(sys.executable))
        self.assertFalse(result["built"])
        self.assertEqual(json.loads((dest / "project.json").read_text())["accepted"], {})
        with self.assertRaisesRegex(core.RoadcraftError, "sourceFiles"):
            workflow.make_recipe(dest, dest / "recipes/one.json")
        with self.assertRaisesRegex(core.RoadcraftError, "already exists"):
            workflow.scaffold(dest, "new_vehicle", Path(sys.executable))

    def test_starter_generates_pinned_recipe_without_execution(self):
        dest = self.root / "new_vehicle"
        workflow.scaffold(dest, "new_vehicle", Path(sys.executable))
        adapter = dest / "tools/build.py"
        adapter.write_text("raise RuntimeError('must not execute during recipe creation')")
        spec_path = dest / "vehicle.json"
        spec = json.loads(spec_path.read_text())
        spec["sourceFiles"] = ["tools/build.py"]
        spec_path.write_text(json.dumps(spec))
        output = dest / "recipes/one.json"
        result = workflow.make_recipe(dest, output)
        self.assertFalse(result["executed"])
        loaded = jobs.load_recipe(output, "build")
        self.assertEqual(Path(loaded["steps"][0]["command"][-2]), adapter)
        self.assertTrue(any(p["path"] == str(adapter) and p["sha256"] == core.sha256_file(adapter)
                            for p in loaded["steps"][0]["inputs"]))
        with self.assertRaisesRegex(core.RoadcraftError, "already exists"):
            workflow.make_recipe(dest, output)

    def test_scoped_texture_edit_does_not_invalidate_independent_model_stage(self):
        dest = self.root / "scoped"
        workflow.scaffold(dest, "scoped", Path(sys.executable))
        adapter = dest / "tools/build.py"
        adapter.write_text("pass")
        texture = dest / "texture.dat"
        texture.write_text("first")
        (dest / "model.dat").write_text("geometry")
        template_path = dest / "recipe-template.json"
        template = json.loads(template_path.read_text())
        template["phases"]["build"][0]["sourceFiles"] = ["tools/build.py", "texture.dat"]
        models = template["phases"]["build"][1]
        models.update(sourceFiles=["tools/build.py", "model.dat"], dependsOn=[])
        template_path.write_text(json.dumps(template))
        first = dest / "recipes/one.json"
        workflow.make_recipe(dest, first)
        old = jobs.load_recipe(first, "build")["steps"]
        before_models = incremental.fingerprint(old[2], [])
        before_textures = incremental.fingerprint(old[0], [])
        texture.write_text("second")
        second = dest / "recipes/two.json"
        workflow.make_recipe(dest, second)
        new = jobs.load_recipe(second, "build")["steps"]
        self.assertEqual(before_models, incremental.fingerprint(new[2], []))
        self.assertNotEqual(before_textures, incremental.fingerprint(new[0], []))
