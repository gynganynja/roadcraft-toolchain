"""Select a mod without borrowing identities or state from the toolchain checkout."""

from __future__ import annotations

import os
from pathlib import Path

from . import core


TOOLCHAIN_ROOT = Path(__file__).resolve().parents[2]


def registry_path(explicit: Path | str | None = None, *, required: bool = True,
                  cwd: Path | None = None) -> Path | None:
    """Explicit argument, environment, then nearest project above the working folder.

    The checkout's historical registry is preserved for explicit D11 continuation,
    but never selected implicitly. Stop at the shared checkout boundary.
    """
    value = explicit if explicit is not None else os.environ.get("ROADCRAFT_REGISTRY")
    if value:
        return core._require_local_path(value).expanduser().resolve()
    start = core._require_local_path(cwd or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        if directory == TOOLCHAIN_ROOT.resolve():
            break
        candidate = directory / "project.json"
        if candidate.is_file():
            return core._require_local_path(candidate).resolve()
    if required:
        raise core.RoadcraftError(
            "No mod selected. Run from a mod project, pass --registry PATH, or set "
            "ROADCRAFT_REGISTRY. Use mod-init for a new mod or mod-adopt for existing sources.")
    return None


def config_path(explicit: Path | str | None = None, *, registry: Path | None = None) -> Path | None:
    value = explicit if explicit is not None else os.environ.get("ROADCRAFT_CONFIG")
    if value:
        return core._require_local_path(value).expanduser().resolve()
    selected = registry if registry is not None else registry_path(required=False)
    return (selected.parent / "local/machine.json").resolve() if selected is not None else None


def jobs_path(explicit: Path | None = None, *, registry: Path | None = None,
              recipe: Path | None = None) -> Path:
    if explicit is not None:
        return core._require_local_path(explicit).resolve()
    if recipe is not None:
        # Recipe ownership wins over whichever folder happened to launch the CLI.
        document = core.load_json(recipe)
        root = document.get("projectRoot") or document.get("defaults", {}).get("cwd")
        if not root:
            raise core.RoadcraftError("Recipe needs projectRoot/defaults.cwd or an explicit --jobs-root")
        return core.resolve_path(root, recipe) / "jobs"
    selected = registry if registry is not None else registry_path()
    return selected.parent / "jobs"
