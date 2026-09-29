"""Shared checks and starter layout for vehicle-specific authoring adapters.

Adapters still own geometry and SDK commands. This module supplies their common
validation, input pinning, stage dependencies and project setup.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import sys
from typing import Any

from . import core


RUNTIME_FILES = ("__init__.py", "__main__.py", "cli.py", "core.py", "jobs.py", "incremental.py",
                 "vehicle_workflow.py", "bro_lint.py", "ps_format.py", "vehicle.py", "tpl_reader.py",
                 "library.py", "retail.py", "source.py", "transaction.py")


PROJECT_AGENT_INSTRUCTIONS = """# RoadCraft vehicle project

Locate the maintained toolchain using ROADCRAFT_TOOLCHAIN when set, otherwise
the path in this project's local/toolchain.json. Read that checkout's AGENTS.md,
skills/roadcraft-workflow/SKILL.md, skills/roadcraft-vehicle-authoring/SKILL.md
and library/learning.md before relevant RoadCraft work.

Use this project's project.json and local/machine.json for its identities and
machine paths; pass them explicitly or through ROADCRAFT_REGISTRY and
ROADCRAFT_CONFIG. The toolchain checkout's default D11 registry is not this
vehicle's baseline.

Whenever a task yields reusable knowledge, integrate it into the maintained
toolchain during the same task before reporting completion. Record discoveries,
failed approaches, fixes, user feedback and corrected assumptions with scope,
evidence grade and source/build/test references. Update the relevant article
and add shared checks/helpers where justified, including their workflow wiring.
Preserve uncertainty and prior evidence. Chat or private agent memory alone
does not satisfy this rule. Report what was integrated and where, or preserve
a handoff and state why integration remains blocked. Do not invent findings
or treat this as additional build, installation or acceptance authorization.
"""


def enhance_recipe(document: dict[str, Any], *, truck_bro: Path, compiled_class: Path,
                   model: Path, python: Path, reports: Path,
                   builder: Path | None = None, prepare_id: str = "prepare",
                   generate_id: str = "generate") -> dict[str, Any]:
    """Add mandatory source/compiled checks to the existing six-stage adapter layout.

The original recipe is left unchanged. All predecessors' declared outputs are
dependencies: existing adapters are conservative until split input scopes are
explicitly reviewed. No stage is made cacheable implicitly.
    """
    result = copy.deepcopy(document)
    source_root = Path(__file__).resolve().parent
    pins = result.setdefault("inputs", [])
    known = {str(core.resolve_path(p["path"], Path(result["defaults"]["cwd"]) / "recipe.json")).casefold() for p in pins}
    for path in [*(source_root / name for name in RUNTIME_FILES), *([builder] if builder else [])]:
        path = path.resolve()
        if str(path).casefold() not in known:
            pins.append({"path": str(path), "sha256": core.sha256_file(path)})
            known.add(str(path).casefold())

    def check(step_id: str, compiled: bool) -> dict[str, Any]:
        command = [str(python.resolve()), "-B", "-m", "roadcraft", "lint-bro", str(truck_bro.resolve())]
        if compiled:
            command += ["--class", str(compiled_class.resolve()), "--tpl", str(model.resolve())]
        report = reports.resolve() / f"{step_id}.json"
        command += ["--report", str(report), "--json"]
        return {"id": step_id, "command": command, "native": False, "cacheable": False,
                "timeoutSeconds": 120, "outputs": [{"path": str(report)}]}

    for phase, steps in result["phases"].items():
        ids = [s["id"] for s in steps]
        if any(s.startswith("vehicle-check-") for s in ids):
            raise core.RoadcraftError("Recipe already contains shared vehicle checks")
        if phase == "build":
            if prepare_id not in ids or generate_id not in ids or ids.index(prepare_id) >= ids.index(generate_id):
                raise core.RoadcraftError("Vehicle build needs ordered prepare and generate steps")
            steps.insert(ids.index(prepare_id) + 1, check("vehicle-check-source", False))
            steps.insert(next(i for i, s in enumerate(steps) if s["id"] == generate_id) + 1,
                         check("vehicle-check-compiled", True))
        elif phase == "test":
            final_check = check("vehicle-check-final", True)
            final_check["inputs"] = [
                {"path": str(path.resolve()), "sha256": core.sha256_file(path)}
                for path in (truck_bro, compiled_class, model)
                if str(path.resolve()).casefold() not in known]
            steps.insert(0, final_check)
        # Legacy adapters conservatively depend on every earlier output. A new
        # adapter can explicitly declare a narrower reviewed dependency graph.
        earlier: list[str] = []
        for step in steps:
            step.setdefault("dependsOn", list(earlier))
            earlier.append(step["id"])
    return result


def require_checks(document: dict[str, Any], phase: str) -> None:
    ids = [step["id"] for step in document.get("phases", {}).get(phase, [])]
    required = {"build": {"vehicle-check-source", "vehicle-check-compiled"},
                "test": {"vehicle-check-final"}}.get(phase, set())
    if not required <= set(ids):
        raise core.RoadcraftError("This recipe predates the shared vehicle checks; generate a new recipe first")


def scaffold(directory: Path, name: str, python: Path) -> dict[str, Any]:
    """Create only a new project; never clone a vehicle's geometry or acceptance.

The declarative adapter contract is based on the buggy/Warthog stage layout.
Authoring scripts and reviewed native commands must be supplied before building.
    """
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", name):
        raise core.RoadcraftError("Vehicle name must be 1-48 lowercase letters, digits or underscores, starting with a letter")
    root = core._require_local_path(directory).resolve()
    if root.exists():
        raise core.RoadcraftError("New vehicle destination already exists; choose a new directory")
    executable = core._require_local_path(python).resolve()
    if not executable.is_file():
        raise core.RoadcraftError("Python executable does not exist")
    package = Path(__file__).resolve().parents[2]
    files: dict[str, str] = {
        "AGENTS.md": PROJECT_AGENT_INSTRUCTIONS,
        "project.json": json.dumps({"schemaVersion": 1, "project": name, "accepted": {},
                                    "candidates": {}, "recipes": {}}, indent=2) + "\n",
        "local/machine.json": json.dumps({"schemaVersion": 1, "tools": {"python": str(executable)}}, indent=2) + "\n",
        "local/toolchain.json": json.dumps({"path": str(package)}, indent=2) + "\n",
        ".gitignore": "local/\njobs/\nbuild/\nreports/\npackage/\n__pycache__/\n",
        "vehicle.json": json.dumps({
            "schemaVersion": 1, "name": name, "sourceFiles": [],
            "truckBro": f"project/mods_source/bro/trucks/{name}.bro",
            "compiledClass": f"project/mods_source/autogen_dw/trucks/auto_{name}/auto_{name}.cls",
            "model": f"project/mods_source/models/mods/{name}.tpl.asset/tpl/{name}.tpl",
            "recipeTemplate": "recipe-template.json"}, indent=2) + "\n",
        "recipe-template.json": json.dumps({
            "schemaVersion": 1, "name": name,
            "defaults": {"cwd": ".", "timeoutSeconds": 1800, "minFreeBytes": 5 * 1024**3,
                         "native": True},
            "phases": {"build": [
                {"id": stage, "command": ["{python}", "-B", "{project}/tools/build.py", stage],
                 "outputs": [{"path": f"reports/{stage}.json"}]}
                for stage in ("prepare", "models", "import", "generate", "package")]}
        }, indent=2) + "\n",
        "tools/vehicle.py": '''"""Use the project's configured shared toolchain."""
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
toolchain = Path(json.loads((root / "local/toolchain.json").read_text())["path"])
sys.path.insert(0, str(toolchain / "src"))
from roadcraft.cli import main
raise SystemExit(main(sys.argv[1:]))
''',
        "README.md": f'''# {name}

This is a vehicle workflow starter, not a built vehicle. No package is accepted.

1. Supply the vehicle's source art and authoring adapters under `tools/`.
2. List every build input (scripts, art, SDK executables and support files) in
   `vehicle.json` `sourceFiles`, in explicit order. Paths are relative to this project.
3. Adapt `recipe-template.json` to the reviewed commands and **all** output files.
   `{{python}}` and `{{project}}` expand from local configuration. Native steps remain
   process-gated. Set `native: false` and `cacheable: true` only for reviewed isolated
   steps whose complete file dependencies and outputs are declared.
4. Configure SDK paths in `local/machine.json`. Then generate a pinned recipe:
   `python -B tools/vehicle.py vehicle-recipe --project . --output recipes/build-001.json`
5. Preflight with `python -B tools/vehicle.py build --recipe recipes/build-001.json --jobs-root jobs --incremental`.
   Add `--apply` to execute. Omit `--incremental` for a full rebuild.

Shared checks run after preparation and class generation. Keep rig audits and
package validation in the template as additional steps. Source and compiled
checks do not prove driving, visual or campaign acceptance. The starter does
not invent a SDK export command or copy a donor's rig/acceptance into this project.
''',
    }
    root.mkdir(parents=True, exist_ok=False)
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    return {"directory": str(root), "files": list(files), "status": "authoring_adapters_required",
            "built": False, "installed": False}


def make_recipe(project: Path, output: Path) -> dict[str, Any]:
    root = core._require_local_path(project).resolve()
    spec = core.load_json(root / "vehicle.json")
    machine = core.read_config(root / "local/machine.json")
    if spec.get("schemaVersion") != 1 or not isinstance(spec.get("sourceFiles"), list):
        raise core.RoadcraftError("vehicle.json needs an ordered sourceFiles list")
    python = Path(machine["tools"]["python"])
    template_path = core.resolve_path(spec["recipeTemplate"], root / "vehicle.json")
    template = core.load_json(template_path)
    all_steps = [s for steps in template["phases"].values() for s in steps]
    if any(not isinstance(s.get("sourceFiles", []), list) for s in all_steps):
        raise core.RoadcraftError("Each step's sourceFiles must be an ordered list")
    if not spec["sourceFiles"] and not any(s.get("sourceFiles") for s in all_steps):
        raise core.RoadcraftError("Declare sourceFiles globally or per step before generating a recipe")
    pins = []
    seen = set()
    for value in [*spec["sourceFiles"], "vehicle.json", str(template_path), str(python)]:
        path = core.resolve_path(value, root / "vehicle.json")
        if str(path).casefold() not in seen:
            pins.append({"path": str(path), "sha256": core.sha256_file(path)})
            seen.add(str(path).casefold())
    template["inputs"] = [*template.get("inputs", []), *pins]
    template["defaults"]["cwd"] = str(root)
    template["defaults"].setdefault("env", {}).update({"PYTHONPATH": str(Path(__file__).resolve().parents[1]),
                                                        "PYTHONDONTWRITEBYTECODE": "1"})
    for pin in template["inputs"]:
        pin["path"] = str(core.resolve_path(pin["path"], template_path))
    for steps in template["phases"].values():
        for step in steps:
            scoped = step.setdefault("inputs", [])
            declared = seen | {str(core.resolve_path(pin["path"], template_path)).casefold() for pin in scoped}
            for value in step.pop("sourceFiles", []):
                path = core.resolve_path(value, template_path)
                if str(path).casefold() not in declared:
                    scoped.append({"path": str(path), "sha256": core.sha256_file(path)})
                    declared.add(str(path).casefold())
            step["command"] = [arg.replace("{python}", str(python)).replace("{project}", str(root))
                               for arg in step["command"]]
            if "cwd" in step:
                step["cwd"] = str(core.resolve_path(step["cwd"], template_path))
            step["outputTrees"] = [str(core.resolve_path(p, template_path)) for p in step.get("outputTrees", [])]
            for field in ("inputs", "outputs"):
                for pin in step.get(field, []):
                    pin["path"] = str(core.resolve_path(pin["path"], template_path))
    recipe = enhance_recipe(template, truck_bro=core.resolve_path(spec["truckBro"], root / "vehicle.json"),
                            compiled_class=core.resolve_path(spec["compiledClass"], root / "vehicle.json"),
                            model=core.resolve_path(spec["model"], root / "vehicle.json"),
                            python=python, reports=root / "reports")
    target = core._require_local_path(output).resolve()
    if target.exists():
        raise core.RoadcraftError("Recipe output already exists; use a new path to preserve its identity")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(recipe, stream, indent=2)
        stream.write("\n")
    return {"recipe": str(target), "sha256": core.sha256_file(target), "status": "recipe_created",
            "executed": False}
