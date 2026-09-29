"""The shared modding library: markdown articles under ``library/`` in this checkout.

Each article collects what is known about one subject, with the evidence behind every statement
(verified in game, read from retail data, or inferred) so that later work can tell a rule from a guess.
"""

from __future__ import annotations

import re
from pathlib import Path

LIBRARY_ROOT = Path(__file__).resolve().parents[2] / "library"


def _root(root: str | Path | None) -> Path:
    return Path(root) if root is not None else LIBRARY_ROOT


def topics(root: str | Path | None = None) -> list[dict[str, str]]:
    """Every article: its slug (file stem) and its first heading."""
    rows = []
    for path in sorted(_root(root).glob("*.md")):
        title = path.stem
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        rows.append({"topic": path.stem, "title": title, "path": str(path)})
    return rows


def article(topic: str, root: str | Path | None = None) -> str:
    path = _root(root) / f"{topic}.md"
    if not path.is_file() or path.parent.resolve() != _root(root).resolve():
        raise LookupError(f"No library article {topic!r}")
    return path.read_text(encoding="utf-8")


def search(term: str, root: str | Path | None = None) -> list[dict[str, object]]:
    """Lines matching ``term`` (case-insensitive regular expression) with the heading they sit under."""
    pattern = re.compile(term, re.IGNORECASE)
    hits: list[dict[str, object]] = []
    for path in sorted(_root(root).glob("*.md")):
        heading = ""
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("#"):
                heading = line.lstrip("#").strip()
            if pattern.search(line):
                hits.append({"topic": path.stem, "line": number, "heading": heading, "text": line.strip()})
    return hits
