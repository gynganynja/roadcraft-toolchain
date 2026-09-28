"""Inventory generated retail-export copies only; never alters original paths."""
from __future__ import annotations
import collections
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

OUT = Path(__file__).resolve().parent
REPO = Path(r"C:\RC\D11_Development")
CSV = Path(r"C:\Users\Gynga\OneDrive\Documents\WholeDrive.csv")
sys.path.insert(0, str(OUT.parent / "src"))
from roadcraft.cleanup import allocated_bytes

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def stat_record(p):
    s = p.stat(follow_symlinks=False)
    return {"path": str(p), "logicalBytes": s.st_size,
            "allocatedBytes": allocated_bytes(p), "hardLinks": s.st_nlink,
            "fileId": f"{s.st_dev}:{s.st_ino}",
            "attributes": getattr(s, "st_file_attributes", 0),
            "mtimeNs": s.st_mtime_ns}

def reparse_ancestor(p):
    while p != REPO.parent:
        if p.stat(follow_symlinks=False).st_file_attributes & 0x400:
            return str(p)
        p = p.parent
    return None

def main():
    with CSV.open(encoding="utf-8-sig", newline="") as f:
        header = next(f).strip()
        rows = list(csv.DictReader(f))
    stages = sorted({Path(r["File Name"].rstrip("\\")).parent
                     for r in rows
                     if re.search(r"\\retail_exports\\[^\\]+\\project\\$", r["File Name"])
                     and "\\checkpoints\\" not in r["File Name"].lower()})
    git = ["git", "--no-optional-locks", "-c", "safe.directory=" + REPO.as_posix(), "-C", str(REPO)]
    tracked_run = subprocess.run(git + ["ls-files", "-z"], capture_output=True, check=True)
    tracked = {os.path.normcase(str(REPO / p)) for p in tracked_run.stdout.decode().split("\0") if p}
    # Lookup retained source texture copies outside every export staging tree.
    originals = collections.defaultdict(list)
    for r in rows:
        name = r["File Name"]
        if name.endswith("\\") or "\\retail_exports\\" in name.lower():
            continue
        p = Path(name)
        if p.suffix.lower() == ".pct" or p.name.lower().endswith(".pct.resource"):
            if "\\mods_source\\pct\\" in name.lower():
                originals[(p.name.lower(), int(r["Size"]))].append(p)
    patterns = OUT / "storage_expansion_reference_patterns_20260928.txt"
    patterns.write_text("\n".join(p.name for p in stages) + "\n", encoding="utf-8")
    reference_run = subprocess.run(["rg", "--json", "-F", "-f", str(patterns),
        "-g", "*.py", "-g", "*.ps1", "-g", "*.js", "-g", "*.md",
        "-g", "!.git/**", str(REPO)], capture_output=True, text=True)
    refs = []
    for line in reference_run.stdout.splitlines():
        item = json.loads(line)
        if item.get("type") == "match":
            data = item["data"]
            refs.append({"path": data["path"]["text"], "line": data["line_number"],
                         "text": data["lines"]["text"].strip()[:1000]})
    hash_cache = {}
    def cached_sha(p):
        s = p.stat(follow_symlinks=False)
        key = (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if key not in hash_cache:
            hash_cache[key] = sha(p)
        return hash_cache[key]
    candidates, summaries, exclusions = [], [], []
    for stage in stages:
        project = stage / "project"
        print("Inspect " + str(stage), flush=True)
        summary = {"stage": str(stage), "project": str(project), "status": "reviewed", "candidateFiles": 0,
                   "candidateAllocatedBytes": 0, "excluded": collections.Counter()}
        summaries.append(summary)
        stage_refs = [r for r in refs if stage.name in r["text"]]
        summary["executableOrMarkdownReferences"] = stage_refs
        if not project.is_dir():
            summary["status"] = "missing"; continue
        if reparse_ancestor(project):
            summary["status"] = "reparse-ancestor"; continue
        audit_path = stage / "audit.json"
        pak = stage / "cat_d11t.pak"
        source_pak = stage / "source.pak"
        if not all(p.is_file() for p in (audit_path, pak, source_pak)):
            summary["status"] = "missing-sealed-package-inputs"; continue
        audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
        if audit.get("status") != "PASS" or cached_sha(pak) != audit.get("packageSha256") or cached_sha(source_pak) != audit.get("sourceSha256"):
            summary["status"] = "retained-package-pin-failed"; continue
        summary["retainedAudit"] = {"path": str(audit_path), "sha256": cached_sha(audit_path)}
        summary["retainedPackage"] = {"path": str(pak), "sha256": cached_sha(pak)}
        summary["retainedSourceSnapshot"] = {"path": str(source_pak), "sha256": cached_sha(source_pak)}
        archive_members = collections.defaultdict(list)
        with zipfile.ZipFile(pak) as z:
            for index, info in enumerate(z.infolist()):
                if not info.is_dir():
                    archive_members[info.filename.replace("\\", "/").lower()].append(
                        {"index": index, "member": info.filename, "bytes": info.file_size,
                         "sha256": hashlib.sha256(z.read(info)).hexdigest()})
        for directory, dirnames, filenames in os.walk(project, followlinks=False):
            here = Path(directory)
            for name in list(dirnames):
                if (here / name).stat(follow_symlinks=False).st_file_attributes & 0x400:
                    dirnames.remove(name)
                    summary["excluded"]["reparse-directory"] += 1
            for name in filenames:
                p = here / name
                record = stat_record(p)
                reason = None
                if record["attributes"] & 0x400: reason = "reparse-file"
                elif record["hardLinks"] != 1: reason = "hardlinked-preserved"
                elif os.path.normcase(str(p)) in tracked: reason = "tracked-preserved"
                elif stage_refs: reason = "fixed-stage-reference-needs-review"
                elif p.suffix.lower() in (".blend", ".blend1", ".spp", ".usf", ".tga", ".png", ".npz", ".bro"): reason = "source-or-evidence-preserved"
                elif "mods_source" not in p.parts: reason = "generated-config-preserved"
                if reason:
                    summary["excluded"][reason] += 1; continue
                digest = cached_sha(p)
                rel = p.relative_to(project / "mods_source").as_posix()
                archive_name = rel[5:] if rel.startswith("mods/") else rel
                matches = [m for m in archive_members.get(archive_name.lower(), []) if m["sha256"] == digest]
                retained = None
                if matches:
                    retained = {"kind": "retained-package-member", "path": str(pak),
                                "packageSha256": audit["packageSha256"], "occurrences": matches}
                elif p.suffix.lower() == ".pct" or p.name.lower().endswith(".pct.resource"):
                    possible = originals.get((p.name.lower(), record["logicalBytes"]), [])
                    for original in possible:
                        if original.is_file() and not reparse_ancestor(original) and cached_sha(original) == digest:
                            retained = {"kind": "retained-source-texture-copy", "path": str(original), "sha256": digest}
                            break
                if not retained:
                    summary["excluded"]["no-identical-retained-original"] += 1
                    exclusions.append({"path": str(p), "allocatedBytes": record["allocatedBytes"], "reason": "no-identical-retained-original"})
                    continue
                after = p.stat(follow_symlinks=False)
                if (after.st_size, after.st_mtime_ns, after.st_ino) != (record["logicalBytes"], record["mtimeNs"], int(record["fileId"].split(":")[1])):
                    summary["excluded"]["changed-during-inspection"] += 1; continue
                record.update(sha256=digest, retainedOriginal=retained,
                              classification="generated-retail-export-copy", stage=str(stage),
                              executionStatus="review-candidate-only-active-ownership-recheck-required")
                candidates.append(record)
                summary["candidateFiles"] += 1
                summary["candidateAllocatedBytes"] += record["allocatedBytes"]
        summary["excluded"] = dict(summary["excluded"])
    allocated = sum(r["allocatedBytes"] for r in candidates)
    report = {"schemaVersion": 1, "generatedUtc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": str(REPO), "csv": {"path": str(CSV), "header": header, "sha256": sha(CSV)},
        "purpose": "Additional exact-file review only. No deletion, move, compression or Git mutation performed.",
        "requestedAdditionalMinimumGiB": 15, "requestedAdditionalMaximumGiB": 20,
        "candidateCount": len(candidates), "candidateAllocatedBytes": allocated,
        "candidateGiB": allocated / 2**30, "meets15GiBTarget": allocated >= 15 * 2**30,
        "generatorEvidence": {"path": str(REPO / "port_cat_d11t/tools/retail_export.py"),
            "sha256": sha(REPO / "port_cat_d11t/tools/retail_export.py"),
            "behavior": "Timestamped retail_exports project is freshly staged from packaged payloads and original PCT inputs; each candidate matches retained package occurrence or unaffected source PCT."},
        "references": {"searched": "All .py/.ps1/.js/.md beneath root for exact timestamp identifiers", "matches": refs,
            "rgExitCode": reference_run.returncode, "stderr": reference_run.stderr.strip(),
            "limits": "JSON receipts are retained evidence and were not scanned as executable callers. Process handles were not available in this sandbox; ownership must be rechecked before execution."},
        "preserve": ["all authored sources", "all checkpoints and source.pak snapshots", "all Git history",
            "all hardlinked files", "all 23 retained fixture projects", "all accepted/AAA workspaces",
            "all stage audit.json, roots.txt, package.log, source.pak and cat_d11t.pak", "every file not explicitly listed"],
        "executionRequirements": ["Current user authorization for exact cleanup", "Recheck file identity, hash, allocation, link count and all ancestor reparse flags", "Recheck retained original/archive hash", "Verify no process or active job owns the stage; do not stop user apps", "Delete exact candidate files only; preserve enclosing directories and all unlisted evidence"],
        "stages": summaries, "candidates": candidates, "unmatched": exclusions}
    destination = OUT / "storage_expansion_review_20260928.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# Additional D11 storage review — 28 September 2026", "", "No original file was changed.", "",
        f"Identified {len(candidates):,} exact generated retail-export files totaling **{allocated / 2**30:.2f} GiB** of current exclusive allocation.",
        "This does **not** establish the requested additional 15–20 GiB. Do not broaden deletion to source-bearing report folders to reach a quota.", "",
        "Every candidate has one hard link, no reparse ancestor, is untracked, and matches either an occurrence in its retained audited PAK or a retained original texture file. Generated projects were created by the inspected retail_export.py recipe. Archive duplicates were inspected by occurrence. All PAK snapshots, outputs, audits, logs, sources, checkpoints, and Git data remain protected.", "",
        "Only exact files in storage_expansion_review_20260928.json are candidates. Keep every enclosing project/report directory and unlisted file. Active ownership was not established; recheck current processes/jobs, hashes, identity, allocation, links and reparse status before any authorized execution.", "",
        "| Generated staging project | Candidate allocation GiB | Files |", "|---|---:|---:|"]
    for s in summaries:
        if s["candidateFiles"]:
            lines.append(f"| `{s['project']}` | {s['candidateAllocatedBytes']/2**30:.3f} | {s['candidateFiles']} |")
    lines += ["", "The input CSV covers C:\\RC\\D11_Development only. Large remaining areas hold authored TGA/Blend/USF data, source-construction JSON, retained fixtures and historical evidence. Temp occupies less than 1 MiB in the snapshot. Prior September 25 project/template cleanup batches were already absent in a fresh check; they are not counted again.", "", "Reference checking searched executable scripts and Markdown for exact export-stage timestamps. Matching stages were excluded. JSON and binary content can contain other historical references, so this is a bounded review, not a claim of complete dependency reachability."]
    (OUT / "STORAGE_EXPANSION_REVIEW_20260928.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(destination), "files": len(candidates), "allocatedBytes": allocated, "GiB": allocated / 2**30, "stages": len(stages), "referenceMatches": len(refs)}), flush=True)

if __name__ == "__main__":
    main()
