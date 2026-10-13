"""Shared checks and starter layout for vehicle-specific authoring adapters.

Adapters still own geometry and SDK commands. This module supplies their common
validation, input pinning, stage dependencies and project setup.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from . import core


RUNTIME_FILES = ("__init__.py", "__main__.py", "cli.py", "core.py", "jobs.py", "incremental.py",
                 "vehicle_workflow.py", "bro_lint.py", "lamps.py", "load_volume.py", "ps_format.py", "vehicle.py",
                 "native_suspension.py", "tpl_reader.py", "tracks.py", "physics_bench.py",
                 "library.py", "retail.py", "source.py", "transaction.py", "onboard.py",
                 "mod_workflow.py", "project_context.py", "pak_build.py", "pak_determinism.py", "quiet.py",
                 "overrides.py", "validate.py", "schema.py")


PROJECT_AGENT_INSTRUCTIONS = """# RoadCraft mod project

Locate the maintained toolchain using ROADCRAFT_TOOLCHAIN when set, otherwise
the path in this project's local/toolchain.json. Read that checkout's AGENTS.md,
skills/roadcraft-workflow/SKILL.md, library/mod-workflow.md and library/learning.md
before relevant RoadCraft work. For vehicle rigs, suspension or truck settings,
also read skills/roadcraft-vehicle-authoring/SKILL.md.

Use this project's project.json and local/machine.json for its identities and
machine paths; pass them explicitly or through ROADCRAFT_REGISTRY and
ROADCRAFT_CONFIG. Keep jobs, receipts and package identities scoped to this mod.
The shared checkout's historical registries are explicit case-study inputs.

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
            # lint-bro also reads the body markup beside the model (lamp visibility, RC037 / RC038).
            from . import lamps
            markup = lamps.markup_beside(model)
            final_check["inputs"] = [
                {"path": str(path.resolve()), "sha256": core.sha256_file(path)}
                for path in (truck_bro, compiled_class, model, *([markup] if markup else []))
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
    """Compatibility entry point for vehicle-specific starters."""
    from . import mod_workflow
    return mod_workflow.scaffold(directory, name, python, kind="vehicle", spec_filename="vehicle.json")


def make_recipe(project: Path, output: Path) -> dict[str, Any]:
    """Compatibility entry point for the existing vehicle.json contract."""
    from . import mod_workflow
    return mod_workflow.make_recipe(project, output, spec_filename="vehicle.json")
