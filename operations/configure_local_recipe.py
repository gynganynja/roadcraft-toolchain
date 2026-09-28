"""Create a machine-local, pinned read-only D11 inspection/test recipe."""

from __future__ import annotations

import json
from pathlib import Path
import sys


TOOLCHAIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLCHAIN / "src"))
from roadcraft.core import sha256_file  # noqa: E402


def main() -> None:
    output = TOOLCHAIN / "local" / "recipes" / "d11_toolchain_checks.json"
    if output.exists():
        raise FileExistsError(f"Refusing to replace configured recipe: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    registry = TOOLCHAIN / "project.json"
    pin = {"path": str(registry), "sha256": sha256_file(registry)}
    defaults = {"cwd": str(TOOLCHAIN), "timeoutSeconds": 900,
                "minFreeBytes": 2 * 1024**3, "native": False}
    recipe = {
        "schemaVersion": 1, "name": "d11-toolchain-checks",
        "defaults": defaults,
        "inputs": [pin],
        "phases": {
            "inspect": [{"id": "verify-project",
                         "command": [sys.executable, "-B", "-m", "roadcraft",
                                     "verify", "--project", "--json"],
                         "outputs": [pin]}],
            "test": [{"id": "toolchain-tests",
                      "command": [sys.executable, "-B", "-m", "unittest", "discover",
                                  "-s", str(TOOLCHAIN / "tests"), "-q"],
                      "outputs": [pin]}],
        },
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(recipe, stream, indent=2)
        stream.write("\n")
    print(output)


if __name__ == "__main__":
    main()
