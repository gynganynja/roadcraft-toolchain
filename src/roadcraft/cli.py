"""Command-line entry point for pinned RoadCraft workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from . import core
from . import jobs, onboard, source, transaction
from . import bro_lint, library, physics_bench, ps_format, retail, tpl_reader, vehicle
from . import vehicle_workflow, mod_workflow, project_context


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit compact machine-readable JSON")


def _add_registry(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--registry", type=Path,
                        default=None,
                        help="Versioned project registry JSON")


def _add_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path,
                        default=None,
                        help="Local machine configuration JSON")


def _config_path(args: argparse.Namespace) -> Path | None:
    return project_context.config_path(args.config, registry=getattr(args, "registry", None))


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roadcraft", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    start = commands.add_parser("onboard", help="Draft a registry for a new or existing mod")
    start.add_argument("--project", required=True, help="Mod or project name")
    start.add_argument("--package", type=Path,
                       help="Existing package to pin as an unreviewed candidate")
    start.add_argument("--candidate-name", default="imported")
    start.add_argument("--output", type=Path,
                       help="Write new registry here; omitted means preview only")
    _add_json(start)

    doctor = commands.add_parser("doctor", help="Inspect local Python, disk, SDK and tool paths")
    _add_registry(doctor)
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
        command.add_argument("--jobs-root", type=Path)
        command.add_argument("--apply", action="store_true",
                             help="Execute the recipe; without this flag, preflight only")
        command.add_argument("--incremental", action="store_true",
                             help="Reuse opted-in isolated steps with verified inputs and outputs")
        _add_json(command)

    job_state = commands.add_parser("jobs-status", help="Inspect a durable job lock and receipt")
    job_state.add_argument("--jobs-root", type=Path)
    _add_registry(job_state)
    _add_json(job_state)

    timings = commands.add_parser("jobs-summary", help="Summarize recorded job duration and reused steps")
    timings.add_argument("--jobs-root", type=Path)
    _add_registry(timings)
    _add_json(timings)

    job_recovery = commands.add_parser("jobs-recover", help="Verify and release an abandoned native job lock")
    job_recovery.add_argument("--jobs-root", type=Path)
    job_recovery.add_argument("--run-id", required=True)
    job_recovery.add_argument("--expected-lock-sha256", required=True)
    job_recovery.add_argument("--expected-receipt-sha256", required=True)
    job_recovery.add_argument("--expected-installed-sha256", required=True)
    job_recovery.add_argument("--expected-registry-sha256", required=True)
    job_recovery.add_argument("--expected-config-sha256", required=True)
    job_recovery.add_argument("--apply", action="store_true",
                              help="Release the verified lock; without this flag, preflight only")
    _add_registry(job_recovery)
    _add_config(job_recovery)
    _add_json(job_recovery)

    source_check = commands.add_parser("source-check", help="Compare current source to its pinned authoring inventory")
    _add_registry(source_check)
    _add_json(source_check)

    lib = commands.add_parser("library", help="List, read or search the shared modding library")
    lib.add_argument("topic", nargs="?", help="Article to print (a file stem under library/)")
    lib.add_argument("--search", help="Case-insensitive regular expression to find across all articles")
    _add_json(lib)

    for action in ("mod-init", "mod-adopt"):
        mod = commands.add_parser(action, help="Create a mod workspace" if action == "mod-init" else
                                  "Add workflow files to existing mod sources without overwriting files")
        mod.add_argument("--directory", type=Path, required=True)
        mod.add_argument("--name", required=True)
        mod.add_argument("--kind", choices=mod_workflow.KINDS, default="general")
        mod.add_argument("--package", type=Path, help="Pin an original package as an unreviewed imported candidate")
        mod.add_argument("--python", type=Path, default=Path(sys.executable))
        _add_json(mod)
    mod_recipe = commands.add_parser("mod-recipe", help="Pin a mod's declared sources and workflow")
    mod_recipe.add_argument("--project", type=Path, required=True)
    mod_recipe.add_argument("--output", type=Path, required=True)
    _add_json(mod_recipe)

    starter = commands.add_parser("vehicle-init", help="Create a new vehicle workflow layout")
    starter.add_argument("--directory", type=Path, required=True)
    starter.add_argument("--name", required=True)
    starter.add_argument("--python", type=Path, default=Path(sys.executable))
    _add_json(starter)
    recipe = commands.add_parser("vehicle-recipe", help="Pin a vehicle's declared sources and add shared checks")
    recipe.add_argument("--project", type=Path, required=True)
    recipe.add_argument("--output", type=Path, required=True)
    _add_json(recipe)

    lint = commands.add_parser("lint-bro", help="Check a truck BRO (and its compiled class / model) for known pitfalls")
    lint.add_argument("bro", type=Path)
    lint.add_argument("--class", dest="compiled_class", type=Path, help="Generated auto_<mod>.cls")
    lint.add_argument("--tpl", type=Path, help="Compiled body model .tpl")
    lint.add_argument("--markup", type=Path, help="Body model .tpl_markup (default: the one beside --tpl's asset)")
    lint.add_argument("--beta", type=float, default=vehicle.SUSPENSION_BETA)
    lint.add_argument("--report", type=Path, help="Write the check result to this explicit report path")
    _add_json(lint)

    lamp = commands.add_parser("lamps", help="Build an exterior-light graph, beams and flashers (roadcraft.lamps)")
    lamp.add_argument("spec", help='JSON text or file: {"anchors": {anchor: role}, "lenses": {...}, '
                                   '"flashers": [{"prefix", "lit", "roles", "pattern": "single"|"double"|[[true, s], ...]}]}')
    lamp.add_argument("--blueprint", default="ExteriorLights", help="Blueprint name in the truck BRO")
    lamp.add_argument("--output", type=Path, help="Also write the BRO fragment in the game's text format here")
    _add_json(lamp)

    nodes = commands.add_parser("tpl-nodes", help="List node names, world transforms and parents of a compiled .tpl")
    nodes.add_argument("tpl", type=Path)
    nodes.add_argument("--anchor", help="A node name that the wanted name table contains")
    nodes.add_argument("--pattern", help="Only nodes whose name matches this regular expression")
    nodes.add_argument("--no-parents", action="store_true", help="Skip the parent-array search")
    _add_json(nodes)

    susp = commands.add_parser("suspension", help="Design or check a SuspensionAxle with the library's model")
    susp.add_argument("--sag", type=float, help="Static sag to design for (m)")
    susp.add_argument("--share", type=float, help="One wheel's fraction of the weight (0.25 on an even 4x4)")
    susp.add_argument("--lift", type=float, default=0.0, help="Rest this much higher than modelled (m)")
    susp.add_argument("--bump", type=float, default=0.16, help="Travel up from rest (m)")
    susp.add_argument("--droop", type=float, default=0.20, help="Travel down from rest (m)")
    susp.add_argument("--damping", type=float, default=0.15)
    susp.add_argument("--axle", help="Existing SuspensionAxle as JSON, to check instead of design")
    susp.add_argument("--calibrate", help='Rests seen in the game, JSON list of {"axle": {...}, "rest": m, '
                                          '"wheels": n} covering every axle: solve beta')
    susp.add_argument("--beta", type=float, default=vehicle.SUSPENSION_BETA)
    susp.add_argument("--geometry", choices=["legacy", "measured"], default="legacy",
                      help="measured: stops at height+min / height+max (native_suspension, "
                           "suspension-and-wheels.md 'Stop geometry'); legacy: stops at min / max")
    _add_json(susp)

    ret = commands.add_parser("retail", help="Read the retail game's own vehicle data (read-only)")
    ret.add_argument("action", choices=["find", "show", "bro", "survey", "tracks"])
    ret.add_argument("name", nargs="?", help="find: glob; show: pak member; bro/tracks: retail truck name")
    ret.add_argument("--game", type=Path, help="Game root (default: sdkRoot of the machine configuration)")
    ret.add_argument("--out", type=Path, help="show: write the member here instead of printing it")
    _add_config(ret)
    _add_registry(ret)
    _add_json(ret)

    bench = commands.add_parser("bench", help="Measure handling in the Mod Editor before installing (library/physics-bench.md)")
    bench.add_argument("action", choices=["init", "apply", "run", "batch", "analyse", "compare"])
    bench.add_argument("items", nargs="*", type=Path,
                       help="run/batch/apply: variant JSON files; analyse/compare: run folders")
    bench.add_argument("--bench", type=Path, help="Bench folder (holds bench.json)")
    bench.add_argument("--schedule", choices=sorted(physics_bench.SCHEDULES), default="normal")
    bench.add_argument("--project", type=Path, help="init: the mod's editor project (holds mods_source)")
    bench.add_argument("--data-dir", type=Path, help="init: editor data folder to copy")
    bench.add_argument("--profiles-dir", type=Path, help="init: editor profiles folder to copy")
    bench.add_argument("--editor", type=Path, help="init: IntegrationStudio.exe")
    bench.add_argument("--scene", help="init: test scene, relative to mods_source")
    bench.add_argument("--vehicle", help="init: the vehicle object's name in the scene")
    bench.add_argument("--class", dest="compiled_class", help="init: compiled truck class, relative to mods_source")
    bench.add_argument("--markup", help="init: model .tpl_markup, relative to mods_source")
    bench.add_argument("--wheel", action="append", default=[], metavar="KIND=PATH",
                       help="init: a compiled wheel class to patch, relative to mods_source (repeatable)")
    bench.add_argument("--sdk-editor-dir", type=Path,
                       help="init: SDK tools/bin/ModEditor (default: sdkRoot of the machine configuration)")
    _add_config(bench)
    _add_registry(bench)
    _add_json(bench)

    install = commands.add_parser("install", help="Dry-run or install one named pinned candidate")
    _add_registry(install)
    _add_config(install)
    install.add_argument("--candidate", required=True)
    install.add_argument("--transaction-root", type=Path)
    install.add_argument("--expect-installed-sha256",
                         help="Exact current installed SHA-256; defaults to accepted package pin")
    install.add_argument("--expect-absent", action="store_true", help="First installation: require the mod slot to be empty")
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
    if hasattr(args, "registry"):
        required = args.command in ("status", "source-check", "install", "jobs-recover") or (
            args.command == "verify" and args.project)
        args.registry = project_context.registry_path(args.registry, required=required)
    if hasattr(args, "config"):
        args.config = _config_path(args)
    if hasattr(args, "jobs_root"):
        args.jobs_root = project_context.jobs_path(args.jobs_root, registry=getattr(args, "registry", None),
                                                  recipe=getattr(args, "recipe", None))
    if args.command == "install" and args.transaction_root is None:
        args.transaction_root = args.registry.parent / "local/transactions"
    if args.command == "onboard":
        registry = onboard.draft_registry(args.project, args.package, args.candidate_name)
        output = onboard.write_registry(args.output, registry) if args.output else None
        return {"registry": registry, "writtenPath": str(output) if output else None,
                "packageStatus": "unreviewed_candidate" if args.package else "none"}, True
    if args.command == "doctor":
        config = core.read_config(args.config) if args.config and args.config.is_file() else None
        result = core.doctor(config)
        result["configPath"] = str(args.config.resolve()) if args.config else None
        result["configFound"] = bool(args.config and args.config.is_file())
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
                                 dry_run=not args.apply, incremental_build=args.incremental)
        return result, result["status"] in ("passed", "dry_run")
    if args.command == "jobs-status":
        return jobs.inspect_jobs(args.jobs_root), True
    if args.command == "jobs-summary":
        return jobs.summarize_jobs(args.jobs_root), True
    if args.command == "jobs-recover":
        result = jobs.recover_jobs(args.jobs_root, args.run_id,
                                   args.expected_lock_sha256,
                                   args.expected_receipt_sha256,
                                   args.expected_installed_sha256,
                                   args.registry, args.expected_registry_sha256,
                                   args.config, args.expected_config_sha256,
                                   dry_run=not args.apply)
        return result, result["status"] in ("ready", "released")
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
    if args.command == "library":
        if args.search:
            return {"search": args.search, "hits": library.search(args.search)}, True
        if args.topic:
            return {"topic": args.topic, "text": library.article(args.topic)}, True
        return {"root": str(library.LIBRARY_ROOT), "topics": library.topics()}, True
    if args.command == "vehicle-init":
        return vehicle_workflow.scaffold(args.directory, args.name, args.python), True
    if args.command in ("mod-init", "mod-adopt"):
        return mod_workflow.scaffold(args.directory, args.name, args.python, kind=args.kind,
                                     adopt=args.command == "mod-adopt", package=args.package), True
    if args.command == "mod-recipe":
        return mod_workflow.make_recipe(args.project, args.output), True
    if args.command == "vehicle-recipe":
        return vehicle_workflow.make_recipe(args.project, args.output), True
    if args.command == "lint-bro":
        result = bro_lint.lint_files(args.bro, args.compiled_class, args.tpl, args.beta, args.markup)
        if args.report:
            report = core._require_local_path(args.report).resolve()
            sources = [p.resolve() for p in (args.bro, args.compiled_class, args.tpl, args.markup) if p]
            if report in sources:
                raise core.RoadcraftError("Check report must not overwrite an input")
            report.parent.mkdir(parents=True, exist_ok=True)
            jobs._atomic_json(report, result)
        return result, result["errors"] == 0
    if args.command == "lamps":
        from . import lamps
        text = Path(args.spec).read_text(encoding="utf-8") if Path(args.spec).suffix == ".json" else args.spec
        spec = json.loads(text)
        named = {"single": lamps.SINGLE_FLASH, "double": lamps.DOUBLE_FLASH}
        flashers = [dict(f, pattern=named.get(f.get("pattern"), f.get("pattern") or lamps.SINGLE_FLASH)) for f in spec.get("flashers") or []]
        built = lamps.exterior_lights(spec.get("anchors") or {}, lenses=spec.get("lenses"), flashers=flashers)
        fragment = {"blueprint": {"blueprints": {args.blueprint: built["blueprint"]}},
                    "effects": {"propSfx": {"list": built["effects"]}}}
        result = {"fragment": fragment, "litObjects": built["litObjects"], "markupHidden": built["markupHidden"],
                  "findings": [dict(zip(("code", "severity", "message", "where"), f))
                               for f in lamps.lamp_findings(fragment["blueprint"], set())]}
        if args.output:
            target = core._require_local_path(args.output).resolve()
            if target.exists():
                raise core.RoadcraftError("lamps --output must name a new file")
            target.parent.mkdir(parents=True, exist_ok=True)
            ps_format.dump(fragment, target)
            result["output"] = str(target)
        return result, not result["findings"]
    if args.command == "tpl-nodes":
        found = tpl_reader.read_tpl(args.tpl, anchor=args.anchor, parents=not args.no_parents)
        rows = []
        for name in found.names:
            if args.pattern and not __import__("re").search(args.pattern, name):
                continue
            rows.append({"name": name, "position": [round(v, 4) for v in found.position(name)],
                         "axes": {k: [round(v, 4) for v in axis] for k, axis in found.axes(name).items()},
                         "parent": found.parent(name)})
        return {"tpl": str(args.tpl), "nodes": len(found.matrices), "names": len(found.names),
                "parentsOffset": found.parents_offset, "notes": found.notes, "rows": rows}, True
    if args.command == "suspension":
        from . import native_suspension
        model = native_suspension if args.geometry == "measured" else vehicle
        if args.calibrate:
            return model.calibrate_beta(json.loads(args.calibrate)), True
        if args.share is None:
            raise core.RoadcraftError("suspension needs --share to design or check an axle")
        if args.axle:
            axle = json.loads(args.axle)
        elif args.sag is not None:
            axle = model.design_axle(args.sag, args.share, lift=args.lift, bump=args.bump, droop=args.droop,
                                     damping=args.damping, beta=args.beta)
        else:
            raise core.RoadcraftError("suspension needs --sag to design or --axle to check")
        report = (native_suspension.rest_report(axle, args.share, args.beta) if args.geometry == "measured"
                  else vehicle.axle_report(axle, args.share, args.beta))
        return {"axle": axle, "geometry": args.geometry, "report": report}, True
    if args.command == "retail":
        game = args.game
        if game is None:
            config = core.read_config(args.config) if args.config and args.config.is_file() else {}
            game = Path(config["sdkRoot"]) if config.get("sdkRoot") else None
        if game is None:
            raise core.RoadcraftError("retail needs --game or sdkRoot in the machine configuration")
        if args.action == "survey":
            return retail.suspension_survey(game), True
        if args.action == "tracks":
            from . import tracks
            return tracks.retail_track_survey(game, [args.name] if args.name else None), True
        if not args.name:
            raise core.RoadcraftError(f"retail {args.action} needs a name")
        if args.action == "find":
            return {"matches": [{"member": m, "pak": str(p)} for m, p in retail.find_members(game, args.name)]}, True
        if args.action == "bro":
            return retail.retail_bro(game, args.name), True
        data = retail.read_member(game, args.name)
        if args.out:
            args.out.write_bytes(data)
            return {"member": args.name, "written": str(args.out), "bytes": len(data)}, True
        return {"member": args.name, "text": data.decode("utf-8", "replace")}, True
    if args.command == "bench":
        return _bench(args)
    if args.command == "install":
        registry = core.read_registry(args.registry)
        config = core.read_config(args.config)
        accepted = registry.get("accepted", {}).get("package")
        candidate = registry.get("candidates", {}).get(args.candidate, {}).get("package")
        installed = config.get("installedPackage")
        if not candidate or not installed:
            raise core.RoadcraftError("Named candidate and installed path are required")
        if args.expect_absent and args.expect_installed_sha256:
            raise core.RoadcraftError("Choose --expect-absent or --expect-installed-sha256")
        expected = None if args.expect_absent else args.expect_installed_sha256 or (accepted or {}).get("sha256")
        if not expected and not args.expect_absent:
            raise core.RoadcraftError("Expected installed SHA-256 or --expect-absent is required")
        result = transaction.install_package(
            accepted, candidate, installed, args.transaction_root, expected,
            _transaction_process_check, dry_run=not args.apply, expect_absent=args.expect_absent)
        return result, True
    if args.command == "rollback":
        return transaction.rollback_package(args.receipt, _transaction_process_check,
                                            dry_run=not args.apply), True
    if args.command == "recover":
        return transaction.recover_package(args.receipt, _transaction_process_check,
                                           dry_run=not args.apply), True
    raise core.RoadcraftError(f"Unsupported command: {args.command}")


def _bench(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    if args.action == "compare":
        return {"table": physics_bench.compare(args.items)}, True
    if args.action == "analyse":
        return {"runs": {str(folder): physics_bench.analyse(folder) for folder in args.items}}, True
    if args.bench is None:
        raise core.RoadcraftError(f"bench {args.action} needs --bench")
    if args.action == "init":
        needed = {"--project": args.project, "--data-dir": args.data_dir, "--profiles-dir": args.profiles_dir,
                  "--editor": args.editor, "--scene": args.scene, "--vehicle": args.vehicle,
                  "--class": args.compiled_class, "--markup": args.markup}
        missing = [flag for flag, value in needed.items() if not value]
        if missing:
            raise core.RoadcraftError("bench init needs " + ", ".join(missing))
        sdk = args.sdk_editor_dir
        if sdk is None:
            config = core.read_config(args.config) if args.config and args.config.is_file() else {}
            sdk = Path(config["sdkRoot"]) / "tools" / "bin" / "ModEditor" if config.get("sdkRoot") else None
        if sdk is None or not (sdk / "Saber.ConsoleTre.dll").is_file():
            raise core.RoadcraftError("bench init needs --sdk-editor-dir (or sdkRoot in the machine configuration) "
                                      "holding Saber.ConsoleTre.dll")
        wheels = dict(item.split("=", 1) for item in args.wheel)
        files = {"class": args.compiled_class, "markup": args.markup, "wheelClasses": wheels}
        return physics_bench.init_bench(args.project, args.data_dir, args.profiles_dir, args.bench, scene=args.scene,
                                        vehicle=args.vehicle, editor=args.editor, files=files,
                                        sdk_editor_directory=sdk), True
    config = physics_bench.load_config(args.bench / "bench.json")
    variants = [physics_bench.load_variant(path) for path in args.items]
    if args.action == "apply":
        if len(variants) > 1:
            raise core.RoadcraftError("bench apply takes one variant (none restores the pristine project)")
        variant = variants[0]["variant"] if variants else {}
        return {"written": physics_bench.apply_variant(config, variant)}, True
    if not variants:
        raise core.RoadcraftError(f"bench {args.action} needs variant files")
    active, error = core._editor_processes(tokens=("roadcraft", "integrationstudio"))
    if error or active:
        raise core.RoadcraftError("close the game and the editor first" if active else f"Cannot inspect processes: {error}")
    if args.action == "run":
        if len(variants) != 1:
            raise core.RoadcraftError("bench run takes one variant; use batch for several")
        return physics_bench.run(config, variants[0]["name"], variants[0]["variant"], args.schedule), True
    results = physics_bench.batch(config, variants, args.schedule)
    return {"results": results}, all("summary" in r for r in results)


def _transaction_process_check() -> list[dict[str, Any]]:
    # Installing a pinned PAK does not consume open DCC authoring documents.
    # Keep native readers/builders closed; the full authoring gate remains
    # available to build and capture workflows.
    active, error = core._editor_processes(tokens=(
        "roadcraft", "modeditor", "integrationstudio", "furnace", "mod_pak_builder"))
    if error:
        raise transaction.PackageTransactionError(f"Cannot inspect authoring processes: {error}")
    return active


PASSTHROUGH_HELP = """headless editor commands (each has its own --help):
  pak build ...         pack a mod without the Mod Editor (library/headless-build.md)
  pak stage ...         stage autogen_dw/ classes as ssl/<stem>_<suffix> in a copy (library/headless-build.md)
  pak normalize|check   deterministic package bytes (library/deterministic-paks.md)
  pak manifest ...      which retail file or other mod each member overrides (library/install-manifest.md)
  validate <target>     runtime-failure checks for a source tree or .pak (library/validator.md)
  schema dump|show|search  the engine's type schema (library/validator.md)
  physics report <target>  the physics values the engine will use, with their source (library/physics-report.md)
  compare <mod> --donor <retail truck|pak>  effective physics side by side with outliers (library/physics-report.md)"""


def _passthrough(argv: list[str]) -> int | None:
    """Commands owned by their modules' own parsers; ``None`` when ``argv`` is not one of them."""
    if not argv:
        return None
    head, rest = argv[0], argv[1:]
    if head == "pak" and rest:
        if rest[0] == "build":
            from . import pak_build
            return pak_build.main(rest[1:])
        if rest[0] == "stage":
            from . import class_staging
            return class_staging.main(rest[1:])
        if rest[0] in ("normalize", "check"):
            from . import pak_determinism
            return pak_determinism.main(rest)
        if rest[0] == "manifest":
            from . import overrides
            return overrides.main(rest[1:])
    if head == "validate":
        from . import validate
        return validate.main(rest)
    if head == "schema":
        from . import schema
        return schema.main(rest)
    if head == "physics" and rest[:1] == ["report"]:
        from . import physics_report
        return physics_report.main(rest)
    if head == "compare":
        from . import physics_report
        return physics_report.main(argv)
    return None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    delegated = _passthrough(argv)
    if delegated is not None:
        return delegated
    if argv[:1] == ["pak"]:
        print(PASSTHROUGH_HELP, file=sys.stderr)
        return 2
    parser = make_parser()
    parser.epilog = PASSTHROUGH_HELP
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    args = parser.parse_args(argv)
    try:
        result, passed = execute(args)
    except (core.RoadcraftError, source.SourceError, transaction.PackageTransactionError,
            ps_format.PsSyntaxError, tpl_reader.TplFormatError, retail.RetailDataError,
            OSError, KeyError, TypeError, LookupError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False,
                     indent=None if args.json else 2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
