"""Read-only D11 regression gate over pinned package and review evidence.

The gate evaluates exact capture contexts and numeric limits. It never treats a
capture, an image difference, or a legacy visual-review status as visual or
campaign approval. Those stages require a detached Ed25519 claim from a key
explicitly trusted by the gate policy.
"""

from __future__ import annotations

import argparse
import base64
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from . import core, review


KINDS = frozenset({"source", "package", "package-receipt", "capture", "metric"})
ROLES = frozenset({"baseline", "candidate"})
BOUNDS = ("candidateMin", "candidateMax", "deltaMin", "deltaMax",
          "percentChangeMin", "percentChangeMax")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class RegressionError(ValueError):
    """A gate policy or pinned evidence is malformed or has changed."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise RegressionError(f"{label} requires a SHA-256 pin")
    return value.lower()


def _path(value: Any, base: Path) -> Path:
    if not isinstance(value, str) or not value or "://" in value:
        raise RegressionError("Evidence requires a local path")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def _read_pinned_json(path: Path, digest: str) -> dict[str, Any]:
    try:
        raw = review._read(path, review.MAX_RECEIPT_BYTES)
        review._pin(raw, digest, path)
        data = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"Non-finite JSON value: {value}")))
    except (review.ReviewError, ValueError, UnicodeError) as exc:
        raise RegressionError(f"Invalid pinned receipt {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RegressionError(f"Receipt must be an object: {path}")
    return data


def _context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RegressionError("Required context must be an object")
    try:
        context = review._context({}, {"context": value})
    except review.ReviewError as exc:
        raise RegressionError(str(exc)) from exc
    missing = review._missing(context)
    if missing:
        raise RegressionError(f"Required context omits {', '.join(missing)}")
    return context


def _lookup(data: Mapping[str, Any], field: str) -> Any:
    if not isinstance(field, str) or not field:
        raise RegressionError("Chain link requires a dotted field path")
    value: Any = data
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _validate_policy(policy: Mapping[str, Any], base: Path) -> dict[str, Any]:
    if policy.get("schemaVersion") != 1:
        raise RegressionError("Unsupported regression policy schemaVersion")
    artifacts = policy.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise RegressionError("artifacts must be a nonempty object")
    normalized = {}
    for artifact_id, row in artifacts.items():
        if not isinstance(artifact_id, str) or not SAFE_ID.fullmatch(artifact_id):
            raise RegressionError("Artifact IDs must be safe, nonempty names")
        if not isinstance(row, dict) or row.get("kind") not in KINDS:
            raise RegressionError(f"Invalid artifact kind: {artifact_id}")
        role = row.get("role")
        if role is not None and role not in ROLES:
            raise RegressionError(f"Invalid artifact role: {artifact_id}")
        statuses = row.get("allowedStatuses")
        if statuses is not None and (not isinstance(statuses, list) or not statuses or
                                     any(not isinstance(x, str) or not x for x in statuses)):
            raise RegressionError(f"Invalid allowedStatuses: {artifact_id}")
        normalized[artifact_id] = {**row, "path": str(_path(row.get("path"), base)),
                                   "sha256": _digest(row.get("sha256"), artifact_id)}
        if row.get("sourceRoot") is not None:
            normalized[artifact_id]["sourceRoot"] = str(_path(row["sourceRoot"], base))
        if row["kind"] in ("capture", "metric") and statuses is None:
            raise RegressionError(f"{artifact_id}: capture/metric receipt needs allowedStatuses")
    for role in ROLES:
        if sum(x["kind"] == "package" and x.get("role") == role
               for x in normalized.values()) != 1:
            raise RegressionError(f"Exactly one {role} package is required")
        if sum(x["kind"] == "capture" and x.get("role") == role
               for x in normalized.values()) != 1:
            raise RegressionError(f"Exactly one {role} capture receipt is required")
    if not any(x["kind"] == "source" for x in normalized.values()):
        raise RegressionError("At least one pinned source receipt is required")
    if not any(x["kind"] == "package-receipt" for x in normalized.values()):
        raise RegressionError("At least one pinned package receipt is required")
    views = policy.get("requiredViews")
    if not isinstance(views, list) or not views:
        raise RegressionError("requiredViews must be a nonempty array")
    normalized_views = []
    seen = set()
    for row in views:
        if not isinstance(row, dict) or not isinstance(row.get("view"), str) or not row["view"]:
            raise RegressionError("Each required view needs view and context")
        entry = {"view": row["view"], "context": _context(row.get("context"))}
        identity = _canonical(entry)
        if identity in seen:
            raise RegressionError("Duplicate required view")
        seen.add(identity)
        normalized_views.append(entry)
    thresholds = policy.get("thresholds", [])
    if not isinstance(thresholds, list):
        raise RegressionError("thresholds must be an array")
    normalized_thresholds = []
    seen.clear()
    for row in thresholds:
        if (not isinstance(row, dict) or not isinstance(row.get("name"), str) or
                not row["name"] or not isinstance(row.get("unit"), str) or not row["unit"]):
            raise RegressionError("Threshold needs metric name, unit, and context")
        entry = {"name": row["name"], "unit": row["unit"],
                 "context": _context(row.get("context"))}
        if not any(key in row for key in BOUNDS):
            raise RegressionError(f"Threshold for {row['name']} has no bound")
        for key in BOUNDS:
            if key in row:
                value = row[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise RegressionError(f"{key} for {row['name']} must be finite")
                entry[key] = value
        identity = _canonical([entry["name"], entry["unit"], entry["context"]])
        if identity in seen:
            raise RegressionError("Duplicate metric threshold")
        seen.add(identity)
        normalized_thresholds.append(entry)
    if thresholds:
        for role in ROLES:
            if sum(x["kind"] == "metric" and x.get("role") == role
                   for x in normalized.values()) != 1:
                raise RegressionError(f"Numerical thresholds require one {role} metric receipt")
    equivalences = policy.get("sceneEquivalences", [])
    if not isinstance(equivalences, list):
        raise RegressionError("sceneEquivalences must be an array")
    normalized_scenes = []
    scene_ids = set()
    scene_paths = set()
    for row in equivalences:
        if not isinstance(row, dict) or not isinstance(row.get("sceneId"), str) or not SAFE_ID.fullmatch(row["sceneId"]):
            raise RegressionError("Scene equivalence needs a safe sceneId")
        if row["sceneId"] in scene_ids:
            raise RegressionError("Duplicate scene equivalence ID")
        scene_ids.add(row["sceneId"])
        pins = {}
        for role in ROLES:
            pin = row.get(role)
            if not isinstance(pin, dict):
                raise RegressionError(f"Scene equivalence {row['sceneId']} needs {role} file pin")
            pins[role] = {"path": str(_path(pin.get("path"), base)),
                          "sha256": _digest(pin.get("sha256"), f"{row['sceneId']} {role} scene")}
            if pins[role]["path"].casefold() in scene_paths:
                raise RegressionError("A scene path belongs to multiple equivalences")
            scene_paths.add(pins[role]["path"].casefold())
        if pins["baseline"]["sha256"] != pins["candidate"]["sha256"]:
            raise RegressionError(f"Scene equivalence {row['sceneId']} does not have identical bytes")
        normalized_scenes.append({"sceneId": row["sceneId"], **pins})
    links = policy.get("links")
    if not isinstance(links, list) or not links:
        raise RegressionError("A nonempty explicit links array is required")
    normalized_links = []
    for link in links:
        if not isinstance(link, dict) or set(link) != {"receipt", "field", "artifact"}:
            raise RegressionError("Each link needs receipt, field, and artifact")
        left, right = link["receipt"], link["artifact"]
        if left not in normalized or right not in normalized or left == right:
            raise RegressionError("Chain link references an invalid artifact")
        if normalized[left]["kind"] == "package":
            raise RegressionError("A package binary cannot contain a receipt link")
        normalized_links.append(dict(link))
    return {"artifacts": normalized, "requiredViews": normalized_views,
            "thresholds": normalized_thresholds, "links": normalized_links,
            "sceneEquivalences": normalized_scenes,
            "approvals": policy.get("approvals", {})}


def _approval(stage: str, pin: Any, trusted: Any, base: Path,
              gate_digest: str, candidate_sha: str) -> dict[str, Any]:
    pending = lambda reason: {"state": "pending", "reason": reason}
    if pin is None:
        return pending("No detached signed approval was supplied")
    if not isinstance(pin, dict) or not isinstance(trusted, dict):
        raise RegressionError("approvals and trustedReviewers must be objects")
    path = _path(pin.get("path"), base)
    data = _read_pinned_json(path, _digest(pin.get("sha256"), f"{stage} approval"))
    claim = data.get("claim")
    if not isinstance(claim, dict):
        return pending("Approval claim is missing")
    if (claim.get("stage") != stage or claim.get("decision") != "approved" or
            claim.get("candidatePackageSha256") != candidate_sha or
            claim.get("gateDigest") != gate_digest or
            not isinstance(claim.get("signedAtUtc"), str) or
            not isinstance(claim.get("reviewer"), str)):
        return pending("Approval claim does not bind this gate and candidate")
    key_text = trusted.get(claim["reviewer"])
    if not isinstance(key_text, str):
        return pending("Reviewer key is not trusted by this policy")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = base64.b64decode(key_text, validate=True)
        signature = base64.b64decode(data.get("signature", ""), validate=True)
        Ed25519PublicKey.from_public_bytes(key).verify(signature, _canonical(claim))
    except ImportError:
        return pending("Ed25519 verifier is unavailable")
    except Exception:
        return pending("Detached signature is invalid")
    return {"state": "approved", "reviewer": claim["reviewer"],
            "signedAtUtc": claim["signedAtUtc"], "receipt": str(path)}


def evaluate(policy: Mapping[str, Any] | str | Path, *,
             base_dir: str | Path | None = None,
             trusted_keys: Mapping[str, str] | str | Path | None = None) -> dict[str, Any]:
    """Verify pins and chain, then evaluate required views and metric limits."""
    if isinstance(policy, (str, Path)):
        policy_path = Path(policy).expanduser().resolve()
        raw_policy = core.load_json(policy_path)
        base = policy_path.parent
    else:
        raw_policy = dict(policy)
        base = Path(base_dir or Path.cwd()).expanduser().resolve()
    plan = _validate_policy(raw_policy, base)
    if isinstance(trusted_keys, (str, Path)):
        trust = core.load_json(trusted_keys)
    elif trusted_keys is None:
        trust = {}
    elif isinstance(trusted_keys, Mapping):
        trust = dict(trusted_keys)
    else:
        raise RegressionError("trusted_keys must be an external reviewer-key mapping or JSON file")
    artifacts = plan["artifacts"]
    checked = {}
    receipt_data = {}
    collector = review._Collector()
    chain_reasons = []
    scene_map = {}
    for equivalent in plan["sceneEquivalences"]:
        for role in ROLES:
            pin = equivalent[role]
            identity = core.file_identity(pin["path"], pin["sha256"])
            if not identity.get("matchesExpected") or not identity.get("unchangedDuringRead"):
                raise RegressionError(f"Scene equivalence changed: {equivalent['sceneId']} {role}")
            scene_map[pin["path"].casefold()] = equivalent["sceneId"]
    for artifact_id, row in artifacts.items():
        identity = core.file_identity(row["path"], row["sha256"])
        if not identity.get("matchesExpected") or not identity.get("unchangedDuringRead"):
            raise RegressionError(f"Pinned artifact changed or missing: {artifact_id}")
        checked[artifact_id] = {"kind": row["kind"], "role": row.get("role"), **identity}
        if row["kind"] != "package":
            receipt_data[artifact_id] = _read_pinned_json(Path(row["path"]), row["sha256"])
            statuses = row.get("allowedStatuses")
            if statuses is not None and receipt_data[artifact_id].get("status") not in statuses:
                chain_reasons.append(f"{artifact_id}: status {receipt_data[artifact_id].get('status')!r} is not allowed")
            if row["kind"] == "capture" and any(
                    word in str(receipt_data[artifact_id].get("status", "")).upper()
                    for word in ("FAIL", "ERROR", "PENDING")):
                chain_reasons.append(f"{artifact_id}: capture receipt reports failure or pending work")
            if row["kind"] == "source":
                source_format = row.get("sourceFormat", "receipt")
                if source_format == "files-manifest":
                    result = core.verify_manifest(row["path"], row.get("sourceRoot"))
                    if not result["passed"]:
                        chain_reasons.append(f"{artifact_id}: source files differ from manifest")
                elif source_format == "authoring-inventory":
                    if not row.get("sourceRoot"):
                        raise RegressionError(f"{artifact_id}: authoring inventory requires sourceRoot")
                    result = core.verify_authoring_inventory(row["path"], row["sourceRoot"])
                    if not result["passed"]:
                        chain_reasons.append(f"{artifact_id}: authoring files differ from inventory")
                elif source_format != "receipt":
                    raise RegressionError(f"{artifact_id}: unknown sourceFormat")
            if row["kind"] in ("capture", "metric"):
                before_captures, before_metrics = len(collector.captures), len(collector.metrics)
                try:
                    collector.collect(Path(row["path"]), row["sha256"], parent_role=row.get("role"))
                except review.ReviewError as exc:
                    raise RegressionError(f"Invalid review evidence {artifact_id}: {exc}") from exc
                new_rows = [*collector.captures[before_captures:], *collector.metrics[before_metrics:]]
                if any(x["role"] != row.get("role") for x in new_rows):
                    chain_reasons.append(f"{artifact_id}: nested evidence changed baseline/candidate role")
                if any(not x["receiptVerified"] for x in new_rows):
                    chain_reasons.append(f"{artifact_id}: nested evidence is not pinned")
    if scene_map:
        for record in [*collector.captures, *collector.metrics]:
            scene = record["context"].get("scene")
            if isinstance(scene, str):
                mapped = scene_map.get(str(Path(scene).expanduser().resolve()).casefold())
                if mapped:
                    record["context"]["scene"] = mapped
    graph = {artifact_id: set() for artifact_id in artifacts}
    for link in plan["links"]:
        left, right = link["receipt"], link["artifact"]
        value = _lookup(receipt_data[left], link["field"])
        if value != artifacts[right]["sha256"]:
            chain_reasons.append(f"{left}.{link['field']} does not pin {right}")
        else:
            graph[left].add(right)
            graph[right].add(left)
    connected = set()
    stack = [next(iter(graph))]
    while stack:
        node = stack.pop()
        if node not in connected:
            connected.add(node)
            stack.extend(graph[node] - connected)
    if connected != set(graph):
        chain_reasons.append("Pinned source, package, capture, and metric artifacts are not one verified chain")
    capture_pairs, capture_exclusions = review._compare(collector.captures)
    metric_pairs, metric_exclusions = review._compare(collector.metrics, metrics=True)
    views = []
    for required in plan["requiredViews"]:
        matches = [pair for pair in capture_pairs if pair["view"] == required["view"] and
                   pair["context"] == required["context"]]
        views.append({**required, "passed": len(matches) == 1,
                      "reason": None if len(matches) == 1 else "No unique pinned baseline/candidate pair"})
    thresholds = []
    for required in plan["thresholds"]:
        matches = [pair for pair in metric_pairs if pair["name"] == required["name"] and
                   pair["unit"] == required["unit"] and pair["context"] == required["context"]]
        if len(matches) != 1:
            thresholds.append({**required, "passed": False,
                               "reason": "No unique pinned baseline/candidate metric pair"})
            continue
        pair = matches[0]
        failures = []
        for minimum, maximum, value in (("candidateMin", "candidateMax", pair["candidateValue"]),
                                        ("deltaMin", "deltaMax", pair["delta"]),
                                        ("percentChangeMin", "percentChangeMax", pair["percentChange"])):
            if minimum in required and (value is None or value < required[minimum]):
                failures.append(f"{minimum} failed")
            if maximum in required and (value is None or value > required[maximum]):
                failures.append(f"{maximum} failed")
        thresholds.append({**required, "baselineValue": pair["baselineValue"],
                           "candidateValue": pair["candidateValue"], "delta": pair["delta"],
                           "percentChange": pair["percentChange"],
                           "passed": not failures, "reason": ", ".join(failures) or None})
    candidate_sha = next(row["sha256"] for row in artifacts.values()
                         if row["kind"] == "package" and row.get("role") == "candidate")
    gate_subject = {"artifacts": {name: {"kind": row["kind"], "role": row.get("role"),
                                            "sha256": row["sha256"],
                                            "allowedStatuses": row.get("allowedStatuses"),
                                            "sourceFormat": row.get("sourceFormat")}
                                  for name, row in artifacts.items()},
                    "links": plan["links"], "requiredViews": plan["requiredViews"],
                    "thresholds": plan["thresholds"],
                    "sceneEquivalences": [{"sceneId": row["sceneId"],
                                           "sha256": row["baseline"]["sha256"]}
                                          for row in plan["sceneEquivalences"]]}
    gate_digest = sha256(_canonical(gate_subject)).hexdigest()
    approvals = plan["approvals"]
    if not isinstance(approvals, dict):
        raise RegressionError("approvals must be an object")
    acceptance = {stage: _approval(stage, approvals.get(stage), trust,
                                   base, gate_digest, candidate_sha)
                  for stage in ("visual", "campaign")}
    technical = not chain_reasons and all(x["passed"] for x in [*views, *thresholds])
    return {"schemaVersion": 1, "kind": "roadcraft.regression", "gateDigest": gate_digest,
            "artifacts": checked, "chain": {"passed": not chain_reasons, "reasons": chain_reasons},
            "sceneEquivalences": gate_subject["sceneEquivalences"],
            "views": views, "thresholds": thresholds,
            "matchedCapturePairs": len(capture_pairs), "matchedMetricPairs": len(metric_pairs),
            "comparisonExclusions": [*capture_exclusions, *metric_exclusions],
            "technicalPassed": technical, "acceptance": acceptance,
            "releaseReady": technical and all(x["state"] == "approved" for x in acceptance.values())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path, help="Pinned regression policy JSON")
    parser.add_argument("--trust-store", type=Path,
                        help="External JSON mapping reviewer names to Ed25519 public keys")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = evaluate(args.policy, trusted_keys=args.trust_store)
    except (RegressionError, core.RoadcraftError, OSError) as exc:
        parser.exit(2, f"regression: {exc}\n")
    print(json.dumps(result, indent=None if args.json else 2, sort_keys=True))
    return 0 if result["technicalPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
