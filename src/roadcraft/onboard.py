"""Create a project registry without inferring package acceptance."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from . import core


_CANDIDATE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def draft_registry(project: str, package: str | Path | None = None,
                   candidate_name: str = "imported") -> dict[str, Any]:
    """Treat a discovered package as an unreviewed candidate, never accepted."""
    if not isinstance(project, str) or not project.strip() or any(
            ord(character) < 32 for character in project):
        raise core.RoadcraftError("Project name must be nonempty and contain no control characters")
    if not _CANDIDATE_NAME.fullmatch(candidate_name):
        raise core.RoadcraftError("Candidate name must use letters, digits, dot, underscore or hyphen")
    registry: dict[str, Any] = {
        "schemaVersion": 1,
        "project": project.strip(),
        "accepted": {},
        "candidates": {},
        "variants": [],
        "recipes": {},
    }
    if package is not None:
        identity = core.file_identity(package)
        if not identity.get("exists") or identity.get("unchangedDuringRead") is not True:
            raise core.RoadcraftError("Package is missing or changed while being hashed")
        registry["candidates"][candidate_name] = {
            "package": {"path": identity["path"], "sha256": identity["sha256"]}
        }
    return registry


def write_registry(path: str | Path, registry: dict[str, Any]) -> Path:
    """Write a new registry, refusing to replace any existing file."""
    target = core._require_local_path(path).absolute()
    if not target.parent.is_dir():
        raise core.RoadcraftError(f"Registry parent directory does not exist: {target.parent}")
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(registry, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return target
