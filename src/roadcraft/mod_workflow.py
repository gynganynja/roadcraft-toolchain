"""Reusable workspaces and pinned recipes for creating or changing RoadCraft mods."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from . import core, jobs, onboard, vehicle_workflow


KINDS = ("general", "vehicle", "material", "tuning")


def scaffold(directory: Path, name: str, python: Path, *, kind: str = "general",
             adopt: bool = False, package: Path | None = None,
             spec_filename: str = "mod.json") -> dict[str, Any]:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", name):
        raise core.RoadcraftError("Mod name must be 1-48 lowercase letters, digits or underscores, starting with a letter")
    if kind not in KINDS:
        raise core.RoadcraftError("Unsupported mod kind")
    root = core._require_local_path(directory).resolve()
    if adopt and not root.is_dir():
        raise core.RoadcraftError("mod-adopt requires an existing source directory")
    if not adopt and root.exists():
        raise core.RoadcraftError("New mod destination already exists; use mod-adopt or a new directory")
    executable = core._require_local_path(python).resolve()
    if not executable.is_file():
        raise core.RoadcraftError("Python executable does not exist")
    toolchain = Path(__file__).resolve().parents[2]
    registry = onboard.draft_registry(name, package)
    spec = {"schemaVersion": 1, "name": name, "kind": kind, "sourceFiles": [],
            "recipeTemplate": "recipe-template.json"}
    if kind == "vehicle":
        spec.update(truckBro=f"project/mods_source/bro/trucks/{name}.bro",
                    compiledClass=f"project/mods_source/autogen_dw/trucks/auto_{name}/auto_{name}.cls",
                    model=f"project/mods_source/models/mods/{name}.tpl.asset/tpl/{name}.tpl")
    stages = ("prepare", "models", "import", "generate", "package") if kind == "vehicle" else ("prepare", "package")
    template = {
        "schemaVersion": 1, "name": name,
        "defaults": {"cwd": ".", "timeoutSeconds": 1800, "minFreeBytes": 5 * 1024**3, "native": True},
        "phases": {"build": [
            {"id": stage, "command": ["{python}", "-B", "{project}/tools/build.py", stage],
             "outputs": [{"path": f"reports/{stage}.json"}]} for stage in stages]}}
    dumps = lambda value: json.dumps(value, indent=2) + "\n"
    wrapper = '''"""Run the shared toolchain with this mod's identity and configuration."""
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
selector = os.environ.get("ROADCRAFT_TOOLCHAIN")
if not selector:
    selector = json.loads((root / "local/toolchain.json").read_text(encoding="utf-8"))["path"]
toolchain = Path(selector).expanduser()
if not toolchain.is_absolute():
    toolchain = root / "local" / toolchain
sys.path.insert(0, str(toolchain.resolve() / "src"))
os.environ["ROADCRAFT_REGISTRY"] = str(root / "project.json")
os.environ["ROADCRAFT_CONFIG"] = str(root / "local/machine.json")
from roadcraft.cli import main
raise SystemExit(main(sys.argv[1:]))
'''
    workflow = f'''# {name}: RoadCraft workflow

This {kind} workspace needs source art/settings and reviewed build adapters.
No package is accepted or installed. An imported package is a pinned reference
candidate; it does not contain a recovered authoring project.

1. Read the maintained toolchain's library/mod-workflow.md and relevant subjects.
2. Preserve original packages and source. For existing mods, inspect package
   members and declare the files permitted to change. Keep edits in source or
   scratch, and compare the resulting package against the original.
3. List every build input in {spec_filename} sourceFiles, globally or per step
   in recipe-template.json. Include scripts, art and SDK dependencies. Use
   ordered explicit paths; external source paths may be absolute.
4. Supply tools/build.py and adapt recipe-template.json to reviewed commands,
   all output files, validation steps and complete dependencies. Vehicle work
   includes shared BRO/compiled-model checks. Other kinds require checks suited
   to their changed resources. Configure SDK paths in local/machine.json.
5. Pin a recipe: python -B tools/roadcraft.py mod-recipe --project . --output recipes/build-001.json
6. Preflight: python -B tools/roadcraft.py build --recipe recipes/build-001.json --incremental
   Add --apply only for an authorized run. Add a test phase or separate recipe
   for package/rig audits and record in-game results separately from build checks.
7. Integrate reusable discoveries into the maintained library before completion.

Reviewed isolated steps may use cacheable: true with native: false and complete
inputs/outputs. Native steps remain process-gated. Receipt identity and visual
or campaign acceptance are separate. Keep original sources and receipts.
'''
    files = {
        "project.json": dumps(registry), spec_filename: dumps(spec),
        "recipe-template.json": dumps(template),
        "local/machine.json": dumps({"schemaVersion": 1, "tools": {"python": str(executable)}}),
        "local/toolchain.json": dumps({"path": str(toolchain)}),
        "tools/roadcraft.py": wrapper,
        "ROADCRAFT_WORKFLOW.md" if adopt else "README.md": workflow,
    }
    if spec_filename == "vehicle.json":
        files["tools/vehicle.py"] = wrapper  # Preserve the existing starter entry point.
    # Refuse conflicting workflow/configuration files before writing anything.
    # Existing source, README and agent guidance remain in place.
    for relative in files:
        target = root / relative
        core._require_local_path(target)
        if target.exists() or target.is_symlink():
            raise core.RoadcraftError(f"Workflow file already exists: {target}; use its existing workflow or a new workspace")
        parent = target.parent
        while parent != root:
            if parent.exists() and not parent.is_dir():
                raise core.RoadcraftError(f"Workflow parent is not a directory: {parent}")
            parent = parent.parent
    append = {
        "AGENTS.md": vehicle_workflow.PROJECT_AGENT_INSTRUCTIONS,
        ".gitignore": "local/\njobs/\nbuild/\nreports/\npackage/\n__pycache__/\n",
    }
    for relative in append:
        target = root / relative
        core._require_local_path(target)
        if target.exists() and not target.is_file():
            raise core.RoadcraftError(f"Workflow path is not a file: {target}")
    if not adopt:
        root.mkdir(parents=True, exist_ok=False)
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    for relative, content in append.items():
        target = root / relative
        with target.open("ab") as stream:
            if stream.tell():
                stream.write(b"\n\n")
            stream.write(content.encode("utf-8"))
    return {"directory": str(root), "kind": kind, "files": [*files, *append],
            "status": "authoring_adapters_required", "adopted": adopt,
            "importedPackage": registry["candidates"].get("imported"), "built": False, "installed": False}


def make_recipe(project: Path, output: Path, *, spec_filename: str | None = None) -> dict[str, Any]:
    root = core._require_local_path(project).resolve()
    if spec_filename is None:
        spec_filename = "mod.json" if (root / "mod.json").is_file() else "vehicle.json"
    spec_path = root / spec_filename
    spec = core.load_json(spec_path)
    machine_path = root / "local/machine.json"
    machine = core.read_config(machine_path)
    if spec.get("schemaVersion") != 1 or not isinstance(spec.get("sourceFiles"), list):
        raise core.RoadcraftError(f"{spec_filename} needs an ordered sourceFiles list")
    kind = spec.get("kind", "vehicle" if spec_filename == "vehicle.json" else "general")
    if kind not in KINDS:
        raise core.RoadcraftError("Unsupported mod kind")
    python = Path(machine["tools"]["python"])
    template_path = core.resolve_path(spec["recipeTemplate"], spec_path)
    template = core.load_json(template_path)
    if not isinstance(template.get("phases"), dict) or not template["phases"]:
        raise core.RoadcraftError("Recipe template needs at least one nonempty phase")
    all_steps = [s for steps in template["phases"].values() for s in steps]
    if any(not isinstance(s.get("sourceFiles", []), list) for s in all_steps):
        raise core.RoadcraftError("Each step's sourceFiles must be an ordered list")
    if not spec["sourceFiles"] and not any(s.get("sourceFiles") for s in all_steps):
        raise core.RoadcraftError("Declare sourceFiles globally or per step before generating a recipe")
    pins, seen = [], set()
    runtime = Path(__file__).resolve().parent
    for value in [*spec["sourceFiles"], str(spec_path), str(template_path), str(python), str(machine_path),
                  str(root / "project.json"), *(str(runtime / name) for name in vehicle_workflow.RUNTIME_FILES)]:
        path = core.resolve_path(value, spec_path)
        if str(path).casefold() not in seen:
            pins.append({"path": str(path), "sha256": core.sha256_file(path)})
            seen.add(str(path).casefold())
    template["inputs"] = [*template.get("inputs", []), *pins]
    template["projectRoot"] = str(root)
    template["defaults"]["cwd"] = str(root)
    template["defaults"].setdefault("env", {}).update({
        "PYTHONPATH": str(runtime.parent), "PYTHONDONTWRITEBYTECODE": "1",
        "ROADCRAFT_REGISTRY": str(root / "project.json"), "ROADCRAFT_CONFIG": str(machine_path)})
    for pin in template["inputs"]:
        pin["path"] = str(core.resolve_path(pin["path"], template_path))
    for steps in template["phases"].values():
        earlier = []
        for step in steps:
            step.setdefault("dependsOn", list(earlier))
            earlier.append(step["id"])
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
    if kind == "vehicle":
        template = vehicle_workflow.enhance_recipe(
            template, truck_bro=core.resolve_path(spec["truckBro"], spec_path),
            compiled_class=core.resolve_path(spec["compiledClass"], spec_path),
            model=core.resolve_path(spec["model"], spec_path), python=python, reports=root / "reports")
    target = core._require_local_path(output).resolve()
    if target.exists():
        raise core.RoadcraftError("Recipe output already exists; use a new path to preserve its identity")
    # Validate before creating a recipe, without executing its commands.
    for phase in template.get("phases", {}):
        jobs.validate_recipe_document(template, target, phase)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(template, stream, indent=2)
        stream.write("\n")
    return {"recipe": str(target), "sha256": core.sha256_file(target), "status": "recipe_created",
            "kind": kind, "executed": False}
