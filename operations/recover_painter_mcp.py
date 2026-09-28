"""Extract the archived Painter MCP into this toolchain with provenance pins."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import stat
from zipfile import ZipFile


ARCHIVE = Path(r"C:\RC\D11_Audit_20260917\01_RoadCraft_Essentials.zip")
PREFIX = "RoadCraftLaptop/extras/SubstancePainterMCP/"
DESTINATION = Path(__file__).resolve().parents[1] / "integrations" / "SubstancePainterMCP"
MAX_FILE_BYTES = 32 * 1024 * 1024


def digest(path: Path) -> str:
    result = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def main() -> None:
    if DESTINATION.exists():
        raise FileExistsError(f"Refusing to overwrite recovered source: {DESTINATION}")
    entries = []
    seen = set()
    with ZipFile(ARCHIVE) as source:
        for info in source.infolist():
            if not info.filename.startswith(PREFIX) or info.is_dir():
                continue
            suffix = info.filename[len(PREFIX):]
            relative = PurePosixPath(suffix)
            if (not suffix or relative.is_absolute() or
                    any(part in ("", ".", "..") for part in suffix.split("/")) or
                    suffix.casefold() in seen):
                raise ValueError(f"Unsafe or duplicate archived name: {info.filename!r}")
            if info.file_size > MAX_FILE_BYTES:
                raise ValueError(f"Archived file is unexpectedly large: {suffix}")
            unix_mode = info.external_attr >> 16
            if stat.S_IFMT(unix_mode) == stat.S_IFLNK:
                raise ValueError(f"Archived link is not accepted: {suffix}")
            seen.add(suffix.casefold())
            entries.append((info, relative))
        if not entries:
            raise ValueError("Archived Painter MCP prefix was not found")
        DESTINATION.mkdir(parents=True)
        rows = []
        for info, relative in entries:
            target = DESTINATION.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            content_hash = sha256()
            with source.open(info) as incoming, target.open("xb") as outgoing:
                for block in iter(lambda: incoming.read(1024 * 1024), b""):
                    content_hash.update(block)
                    outgoing.write(block)
            rows.append({"path": relative.as_posix(), "bytes": info.file_size,
                         "sha256": content_hash.hexdigest()})
    provenance = {"schemaVersion": 1, "archive": str(ARCHIVE),
                  "archiveSha256": digest(ARCHIVE), "prefix": PREFIX,
                  "files": rows}
    (DESTINATION / "RECOVERY_PROVENANCE.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"destination": str(DESTINATION), "files": len(rows),
                      "archiveSha256": provenance["archiveSha256"]}))


if __name__ == "__main__":
    main()
