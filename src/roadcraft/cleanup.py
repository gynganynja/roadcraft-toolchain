"""Read-only, exact-file storage review for the RoadCraft workspace.

This module deliberately has no deletion operation. Its output is a review
manifest, not an instruction to remove a folder or all files of one type.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess


TEMPLATE_NAMES = frozenset(
    {"mod_scene_1x1.fct.zip", "mod_scene_2x2.fct.zip", "mod_scene_500x500.fct.zip"}
)
UNSAFE_ATTRIBUTES = 0x400 | 0x800 | 0x200  # reparse, compressed, sparse


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def allocated_bytes(path: Path) -> int:
    """Return allocation rounded to the volume cluster size, on Windows."""
    if os.name != "nt":
        return path.stat().st_blocks * 512
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCompressedFileSizeW.argtypes = (
        wintypes.LPCWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel.GetCompressedFileSizeW.restype = wintypes.DWORD
    high = wintypes.DWORD()
    ctypes.set_last_error(0)
    low = kernel.GetCompressedFileSizeW(str(path), ctypes.byref(high))
    err = ctypes.get_last_error()
    if low == 0xFFFFFFFF and err:
        raise OSError(err, "GetCompressedFileSizeW failed", str(path))
    physical = (high.value << 32) | low
    sectors = wintypes.DWORD()
    bytes_per_sector = wintypes.DWORD()
    free_clusters = wintypes.DWORD()
    total_clusters = wintypes.DWORD()
    kernel.GetDiskFreeSpaceW.argtypes = (
        wintypes.LPCWSTR,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel.GetDiskFreeSpaceW.restype = wintypes.BOOL
    ok = kernel.GetDiskFreeSpaceW(
        path.anchor,
        ctypes.byref(sectors),
        ctypes.byref(bytes_per_sector),
        ctypes.byref(free_clusters),
        ctypes.byref(total_clusters),
    )
    if not ok:
        raise OSError(ctypes.get_last_error(), "GetDiskFreeSpaceW failed", str(path))
    cluster = sectors.value * bytes_per_sector.value
    if not cluster:
        raise ValueError(f"Invalid cluster size for {path.anchor}")
    return ((physical + cluster - 1) // cluster) * cluster


def _file_record(path: Path) -> dict:
    path = path.absolute()
    info = path.lstat()
    attrs = getattr(info, "st_file_attributes", 0)
    if not path.is_file() or path.is_symlink() or attrs & UNSAFE_ATTRIBUTES:
        raise ValueError(f"Unexpected file type or attributes: {path}")
    path = path.resolve(strict=True)
    return {
        "path": str(path.resolve()),
        "sizeBytes": info.st_size,
        "allocatedBytes": allocated_bytes(path),
        "sha256": sha256_file(path),
        "fileId": f"{info.st_dev}:{info.st_ino}",
        "hardLinks": info.st_nlink,
        "modifiedUtc": dt.datetime.fromtimestamp(
            info.st_mtime, dt.timezone.utc
        ).isoformat(),
    }


def scan_template_copies(run_roots: list[Path], sdk_templates: Path) -> list[dict]:
    """Find only copied SDK templates beneath declared old-run roots."""
    originals = {}
    for name in TEMPLATE_NAMES:
        original = sdk_templates / name
        originals[name] = _file_record(original)
    candidates = []
    seen_ids = set()
    for root in run_roots:
        root = root.resolve(strict=True)
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            here = Path(directory)
            if (here.is_symlink() or
                    getattr(here.lstat(), "st_file_attributes", 0) & UNSAFE_ATTRIBUTES):
                dirnames[:] = []
                continue
            if here.name.lower() != "templates" or here.parent.name.lower() != "editor_data":
                continue
            for name in sorted(TEMPLATE_NAMES.intersection(filenames)):
                candidate = _file_record(here / name)
                original = originals[name]
                if candidate["sha256"] != original["sha256"]:
                    raise ValueError(f"SDK template mismatch: {candidate['path']}")
                if candidate["hardLinks"] != 1:
                    raise ValueError(f"Template has other hard links: {candidate['path']}")
                if candidate["fileId"] in seen_ids:
                    raise ValueError(f"Duplicate candidate file identity: {candidate['path']}")
                seen_ids.add(candidate["fileId"])
                candidate["retainedOriginal"] = original["path"]
                candidate["kind"] = "sdk-template-copy"
                candidates.append(candidate)
    return sorted(candidates, key=lambda item: item["path"].lower())


def inspect_git_temp_pack(git_repo: Path, pack: Path) -> dict:
    """Report a single temporary pack for separate review; never remove it."""
    git_repo = git_repo.resolve(strict=True)
    pack = pack.resolve(strict=True)
    expected_parent = (git_repo / ".git" / "objects" / "pack").resolve(strict=True)
    if pack.parent != expected_parent or not pack.name.startswith("tmp_pack_"):
        raise ValueError("Git candidate is not the specified temporary pack")
    result = subprocess.run(
        [
            "git", "--no-optional-locks", "-c",
            f"safe.directory={git_repo.as_posix()}", "-C", str(git_repo),
            "count-objects", "-v",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    if pack.name not in result.stderr:
        raise ValueError("Git does not currently report this pack as garbage")
    record = _file_record(pack)
    if record["hardLinks"] != 1:
        raise ValueError("Git temporary pack has another hard link")
    record["kind"] = "git-temporary-pack-separate-review"
    record["gitGarbageObservation"] = result.stderr.strip()
    record["requiresSeparateReview"] = True
    return record


def build_review(run_roots: list[Path], sdk_templates: Path,
                 git_repo: Path | None = None, temp_pack: Path | None = None) -> dict:
    files = scan_template_copies(run_roots, sdk_templates)
    review = {
        "schemaVersion": 1,
        "generatedUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "purpose": "RoadCraft exact-file cleanup review; no files were removed",
        "runRoots": [str(root.resolve(strict=True)) for root in run_roots],
        "sdkTemplates": str(sdk_templates.resolve(strict=True)),
        "templateCopies": files,
        "templateCopyCount": len(files),
        "templateAllocatedBytes": sum(item["allocatedBytes"] for item in files),
    }
    if git_repo is not None or temp_pack is not None:
        if git_repo is None or temp_pack is None:
            raise ValueError("Git repository and temporary pack must be provided together")
        review["gitTemporaryPack"] = inspect_git_temp_pack(git_repo, temp_pack)
    return review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, action="append", required=True)
    parser.add_argument("--sdk-templates", type=Path, required=True)
    parser.add_argument("--git-repo", type=Path)
    parser.add_argument("--temp-pack", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review = build_review(args.run_root, args.sdk_templates,
                          args.git_repo, args.temp_pack)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output),
                      "templateCopyCount": review["templateCopyCount"],
                      "templateAllocatedBytes": review["templateAllocatedBytes"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
