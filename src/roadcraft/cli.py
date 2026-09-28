"""Command-line entry point for pinned RoadCraft workflows."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from . import core
from . import jobs, source, transaction


PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit compact machine-readable JSON")


def _add_registry(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--registry", type=Path,
                        default=Path(os.environ.get("ROADCRAFT_REGISTRY",
                                                    PACKAGE_ROOT / "project.json")),
                        help="Versioned project registry JSON")


def _add_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path,
                        default=Path(os.environ.get("ROADCRAFT_CONFIG",
                                                    PACKAGE_ROOT / "local/machine.json")),
                        help="Local machine configuration JSON")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roadcraft", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="Inspect local Python, disk, SDK and tool paths")
    _add_config(doctor)
    _add_json(doctor)

    state = commands.add_parser("status", help="Compare accepted, candidate and installed identities")
    _add_registry(state)
    _add_config(state)
    _add_json(state)

    inspect = commands.add_parser("inspect", help="Inspect a file and ZIP member occurrences")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--member", help="Normalized member path within a ZIP archive")
    inspect.add_argument("--occurrence", type=int, help="One-based occurrence of --member")
    inspect.add_argument("--hash-members", action="store_true",
                         help="Read and hash each selected member (also verifies CRC)")
    _add_json(inspect)

    verify = commands.add_parser("verify", help="Verify pinned files, a manifest, or two archives")
    modes = verify.add_mutually_exclusive_group(required=True)
    modes.add_argument("--project", action="store_true",
                       help="Verify all registry-pinned accepted and candidate files")
    modes.add_argument("--file", type=Path, help="Verify one file against --sha256")
    modes.add_argument("--manifest", type=Path, help="Verify a files manifest")
    modes.add_argument("--baseline", type=Path, help="Compare baseline ZIP to --candidate ZIP")
    verify.add_argument("--sha256", help="Expected SHA-256 for --file")
    verify.add_argument("--base", type=Path, help="Base directory for relative manifest file paths")
    verify.add_argument("--candidate", type=Path, help="Candidate ZIP for --baseline")
    verify.add_argument("--allowed-path", action="append", dest="allowed_paths",
                        help="Allowed changed member glob; repeat as needed")
    _add_registry(verify)
    _add_config(verify)
    _add_json(verify)

    for phase in ("build", "test", "capture", "inspect-job"):
        command = commands.add_parser(phase, help=f"Run a pinned {phase} recipe phase")
        command.add_argument("--recipe", type=Path, required=True)
        command.add_argument("--jobs-root", type=Path, default=PACKAGE_ROOT / "jobs")
        command.add_argument("--apply", action="store_true",
                             help="Execute the recipe; without this flag, preflight only")
        _add_json(command)

    job_state = commands.add_parser("jobs-status", help="Inspect a durable job lock and receipt")
    job_state.add_argument("--jobs-root", type=Path, default=PACKAGE_ROOT / "jobs")
    _add_json(job_state)

    source_check = commands.add_parser("source-check", help="Compare current source to its pinned authoring inventory")
    _add_registry(source_check)
    _add_json(source_check)

    install = commands.add_parser("install", help="Dry-run or install one named pinned candidate")
    _add_registry(install)
    _add_config(install)
    install.add_argument("--candidate", required=True)
    install.add_argument("--transaction-root", type=Path, default=PACKAGE_ROOT / "local" / "transactions")
    install.add_argument("--expect-installed-sha256",
                         help="Exact current installed SHA-256; defaults to accepted package pin")
    install.add_argument("--apply", action="store_true")
    _add_json(install)

    for name in ("rollback", "recover"):
        operation = commands.add_parser(name, help=f"Dry-run or {name} one transaction receipt")
        operation.add_argument("--receipt", type=Path, required=True)
        operation.add_argument("--apply", action="store_true")
        _add_json(operation)
    return parser


def _verify_project(registry_path: Path, config_path: Path) -> dict[str, Any]:
    registry = core.read_registry(registry_path)
    config = core.read_config(config_path) if config_path.is_file() else {}
    state = core.status(registry, config)
    pinned = []
    accepted = state.get("accepted")
    if accepted:
        pinned.append(accepted)
    source = state.get("sourceManifest")
    if source:
        pinned.append(source)
    authoring = state.get("authoringInventory")
    if authoring:
        pinned.append(authoring)
    pinned.extend(state["candidates"].values())
    pinned.extend(state["candidateReceipts"].values())
    source_files = None
    source_pin = registry.get("accepted", {}).get("sourceManifest")
    if source_pin and source and source.get("matchesExpected") is True:
        source_files = core.verify_manifest(source_pin["path"],
                                            registry["accepted"].get("sourceRoot"))
    authoring_files = None
    authoring_pin = registry.get("accepted", {}).get("authoringInventory")
    if authoring_pin and authoring and authoring.get("matchesExpected") is True:
        source_root = registry["accepted"].get("sourceRoot")
        if not source_root:
            raise core.RoadcraftError("accepted.sourceRoot is required for authoringInventory verification")
        authoring_files = core.verify_authoring_inventory(authoring_pin["path"], source_root)
    # A registry entry without a hash is observable but cannot prove identity.
    passed = bool(pinned) and all(item.get("matchesExpected") is True and
                                      item.get("unchangedDuringRead") is True
                                      for item in pinned) and (source_files is None or source_files["passed"]) and (
                                          authoring_files is None or authoring_files["passed"])
    return {"status": state, "sourceFiles": source_files,
            "authoringFiles": authoring_files,
            "pinnedFileCount": len(pinned), "passed": passed}


def execute(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    if args.command == "doctor":
        config = core.read_config(args.config) if args.config.is_file() else None
        result = core.doctor(config)
        result["configPath"] = str(args.config.resolve())
        result["configFound"] = args.config.is_file()
        return result, True
    if args.command == "status":
        registry = core.read_registry(args.registry)
        config = core.read_config(args.config) if args.config.is_file() else {}
        result = core.status(registry, config)
        result["registryPath"] = str(args.registry.resolve())
        result["configPath"] = str(args.config.resolve())
        result["configFound"] = args.config.is_file()
        return result, True
    if args.command == "inspect":
        return core.inspect_path(args.path, member=args.member,
                                 occurrence=args.occurrence,
                                 hash_members=args.hash_members), True
    if args.command == "verify":
        if args.project:
            result = _verify_project(args.registry, args.config)
            return result, result["passed"]
        if args.file:
            if not args.sha256:
                raise core.RoadcraftError("--file requires --sha256")
            result = core.file_identity(args.file, args.sha256)
            return result, result.get("matchesExpected") is True and result.get("unchangedDuringRead") is True
        if args.manifest:
            result = core.verify_manifest(args.manifest, args.base)
            return result, result["passed"]
        if args.baseline:
            if not args.candidate:
                raise core.RoadcraftError("--baseline requires --candidate")
            result = core.compare_archives(args.baseline, args.candidate, args.allowed_paths)
            return result, result.get("passesAllowedChanges", True)
    if args.command in ("build", "test", "capture", "inspect-job"):
        phase = "inspect" if args.command == "inspect-job" else args.command
        result = jobs.run_recipe(args.recipe, phase, args.jobs_root,
                                 dry_run=not args.apply)
        return result, result["status"] in ("passed", "dry_run")
    if args.command == "jobs-status":
        return jobs.inspect_jobs(args.jobs_root), True
    if args.command == "source-check":
        registry = core.read_registry(args.registry)
        accepted = registry.get("accepted", {})
        pin = accepted.get("authoringInventory")
        root = accepted.get("sourceRoot")
        if not pin or not root:
            raise core.RoadcraftError("accepted.authoringInventory and sourceRoot are required")
        expected_identity = core.file_identity(pin["path"], pin.get("sha256"))
        if not expected_identity.get("matchesExpected"):
            raise core.RoadcraftError("Authoring inventory file differs from its registry pin")
        expected = core.load_json(pin["path"])
        declarations = [
            {"asset": asset["asset"], "exportMethod": asset["exportMethod"],
             "files": [{"path": item["path"], "role": item["role"]}
                       for item in asset["files"]]}
            for asset in expected["assets"]
        ]
        actual = source.capture_source_inventory(Path(root), declarations)
        result = source.compare_source_baselines(expected, actual)
        result["inventoryPin"] = expected_identity
        return result, result["matches"]
    if args.command == "install":
        registry = core.read_registry(args.registry)
        config = core.read_config(args.config)
        accepted = registry.get("accepted", {}).get("package")
        candidate = registry.get("candidates", {}).get(args.candidate, {}).get("package")
        installed = config.get("installedPackage")
        if not accepted or not candidate or not installed:
            raise core.RoadcraftError("Named candidate, accepted package and installed path are required")
        expected = args.expect_installed_sha256 or accepted.get("sha256")
        if not expected:
            raise core.RoadcraftError("Expected installed SHA-256 is required")
        result = transaction.install_package(
            accepted, candidate, installed, args.transaction_root, expected,
            _transaction_process_check, dry_run=not args.apply)
        return result, True
    if args.command == "rollback":
        return transaction.rollback_package(args.receipt, _transaction_process_check,
                                            dry_run=not args.apply), True
    if args.command == "recover":
        return transaction.recover_package(args.receipt, _transaction_process_check,
                                           dry_run=not args.apply), True
    raise core.RoadcraftError(f"Unsupported command: {args.command}")


def _transaction_process_check() -> list[dict[str, Any]]:
    active, error = core._editor_processes()
    if error:
        raise transaction.PackageTransactionError(f"Cannot inspect authoring processes: {error}")
    return active


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        result, passed = execute(args)
    except (core.RoadcraftError, source.SourceError, transaction.PackageTransactionError,
            OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False,
                     indent=None if args.json else 2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
