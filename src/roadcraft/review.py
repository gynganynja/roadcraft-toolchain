"""Offline evidence reports; generating a report never grants acceptance.

``generate_report([{\"path\": receipt, \"sha256\": pin}], output_dir)`` verifies
caller-pinned receipts, nested ``variants[].report`` receipts, and every image.
Bare receipt paths are useful for inspection but are snapshot-only: they cannot
produce comparisons. Existing native ``views`` / visual-review ``captures`` are
supported. New receipts may declare ``role`` (baseline/candidate), ``context``
(variant, scene, camera, lighting, resolution, protocol), ``captures``, typed
``metrics`` (name/value/unit/context), and independent ``acceptance`` claims.
Context can be overridden per capture/metric. Missing context is never inferred
from filenames, status prose, or nearby files. Native viewSpecs are preserved.

All six context fields, units (for metrics), and receipt pins must match before
comparison. Duplicate baseline/candidate records are ambiguous and not paired.
Image resolution is measured from the PNG/JPEG bytes, not trusted from JSON.
The HTML embeds the original verified images without resizing their file data.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import math
from pathlib import Path
import re
import struct
from typing import Any, Iterable, Mapping


CONTEXT_FIELDS = ("variant", "scene", "camera", "lighting", "resolution", "protocol")
MAX_RECEIPT_BYTES = 16 * 1024 * 1024
MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 256 * 1024 * 1024
MAX_RECEIPTS = 256


class ReviewError(ValueError):
    """Evidence is invalid, unavailable, unpinned, or internally inconsistent."""


def _json_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _read(path: Path, limit: int) -> bytes:
    try:
        with path.open("rb") as stream:
            content = stream.read(limit + 1)
    except OSError as exc:
        raise ReviewError(f"Cannot read evidence {path}: {exc}") from exc
    if len(content) > limit:
        raise ReviewError(f"Evidence exceeds {limit} bytes: {path}")
    return content


def _pin(content: bytes, expected: Any, path: Path, *, required: bool = True) -> str:
    actual = hashlib.sha256(content).hexdigest()
    if expected is None and not required:
        return actual
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise ReviewError(f"Missing or invalid SHA-256 pin: {path}")
    if actual != expected.lower():
        raise ReviewError(f"SHA-256 mismatch: {path}")
    return actual


def _path(value: Any, relative_to: Path) -> Path:
    if not isinstance(value, (str, Path)) or not str(value):
        raise ReviewError("Evidence path must be a nonempty local path")
    value = str(value)
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        raise ReviewError("Remote evidence URLs are not supported")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else relative_to / path).resolve()


def _image_info(data: bytes) -> tuple[str, list[int]]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 33:
        if data[12:16] != b"IHDR" or data[8:12] != b"\0\0\0\r":
            raise ReviewError("PNG has no valid IHDR")
        width, height = struct.unpack(">II", data[16:24])
        mime = "image/png"
    elif data.startswith(b"\xff\xd8"):
        width = height = 0
        offset = 2
        while offset < len(data):
            if data[offset] != 0xFF:
                raise ReviewError("Invalid JPEG marker")
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xD9, 0xDA):
                break
            if marker == 0x01 or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                break
            size = int.from_bytes(data[offset:offset + 2], "big")
            if size < 2 or offset + size > len(data):
                raise ReviewError("Truncated JPEG segment")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9,
                          0xCA, 0xCB, 0xCD, 0xCE, 0xCF) and size >= 8:
                height, width = struct.unpack(">HH", data[offset + 3:offset + 7])
                break
            offset += size
        mime = "image/jpeg"
    else:
        raise ReviewError("Only PNG and JPEG capture evidence is supported")
    if width <= 0 or height <= 0:
        raise ReviewError("Image dimensions are unavailable or invalid")
    return mime, [width, height]


def _context(parent: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(parent)
    for field in CONTEXT_FIELDS:
        if field in row:
            result[field] = row[field]
    declared = row.get("context", {})
    if not isinstance(declared, dict):
        raise ReviewError("context must be an object")
    result.update({key: declared[key] for key in CONTEXT_FIELDS if key in declared})
    if "resolution" in result:
        resolution = result["resolution"]
        if (not isinstance(resolution, list) or len(resolution) != 2 or
                any(type(value) is not int or value <= 0 for value in resolution)):
            raise ReviewError("resolution must be [positive width, positive height]")
    # JSON serialization also rejects NaN/Infinity and preserves typed equality.
    try:
        _json_key(result)
    except (TypeError, ValueError) as exc:
        raise ReviewError(f"Invalid comparison context: {exc}") from exc
    return result


def _missing(context: Mapping[str, Any]) -> list[str]:
    return [key for key in CONTEXT_FIELDS if context.get(key) in (None, "", [], {})]


class _Collector:
    def __init__(self) -> None:
        self.sources: list[dict[str, Any]] = []
        self.captures: list[dict[str, Any]] = []
        self.metrics: list[dict[str, Any]] = []
        self.claims: dict[str, list[dict[str, Any]]] = {"visual": [], "campaign": []}
        self.images: dict[str, str] = {}
        self.image_bytes = 0
        self.active: set[Path] = set()

    def collect(self, path: Path, expected: str | None = None, *,
                parent_context: Mapping[str, Any] | None = None,
                parent_role: str | None = None, parent_label: str | None = None,
                chain_verified: bool = True) -> None:
        if path in self.active:
            raise ReviewError(f"Receipt reference cycle: {path}")
        if len(self.sources) >= MAX_RECEIPTS:
            raise ReviewError("Too many nested receipts")
        raw = _read(path, MAX_RECEIPT_BYTES)
        digest = _pin(raw, expected, path, required=False)
        try:
            data = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"Non-finite JSON value: {value}")))
        except (ValueError, UnicodeError) as exc:
            raise ReviewError(f"Invalid JSON receipt: {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ReviewError(f"Receipt must contain an object: {path}")
        verified = expected is not None and chain_verified
        source_id = len(self.sources)
        self.sources.append({"path": str(path), "sha256": digest,
                             "pinVerified": expected is not None,
                             "chainVerified": verified,
                             "integrity": "pinned" if verified else "snapshot_only",
                             "reportedStatus": data.get("status")})
        context = _context(parent_context or {}, data)
        role = data.get("role", parent_role)
        label = str(data.get("label", parent_label or path.stem))
        common = {"source": source_id, "role": role, "label": label,
                  "receiptVerified": verified}
        acceptance = data.get("acceptance", {})
        if not isinstance(acceptance, dict):
            raise ReviewError("acceptance must be an object")
        for stage in self.claims:
            if stage in acceptance:
                self.claims[stage].append({**common, "claim": acceptance[stage]})
        # Old visual approvals are retained as attributed claims, never promoted
        # into campaign or numerical acceptance by interpreting status strings.
        if "reviewedViews" in data or "observations" in data:
            self.claims["visual"].append({**common, "claim": {
                key: data[key] for key in ("status", "scope", "method", "finding",
                                          "observations", "reviewedViews") if key in data}})
        captures = data.get("captures", data.get("views", []))
        if not isinstance(captures, list):
            raise ReviewError(f"captures/views must be an array: {path}")
        for row in captures:
            if not isinstance(row, dict):
                raise ReviewError("Capture entry must be an object")
            capture_context = _context(context, row)
            view = str(row.get("view", row.get("name", "capture")))
            if ("camera" not in capture_context and data.get("cameraBasis") and
                    view in data.get("viewSpecs", {})):
                capture_context["camera"] = {"basis": data.get("cameraBasis"),
                                              "spec": data["viewSpecs"][view]}
            image_path = _path(row.get("path"), path.parent)
            content = _read(image_path, MAX_IMAGE_BYTES)
            image_hash = _pin(content, row.get("sha256"), image_path)
            mime, resolution = _image_info(content)
            if ("resolution" in capture_context and
                    capture_context["resolution"] != resolution):
                raise ReviewError(f"Declared resolution differs from image: {image_path}")
            capture_context["resolution"] = resolution
            if image_hash not in self.images:
                self.image_bytes += len(content)
                if self.image_bytes > MAX_TOTAL_IMAGE_BYTES:
                    raise ReviewError("Embedded images exceed total size limit")
                self.images[image_hash] = f"data:{mime};base64," + base64.b64encode(content).decode("ascii")
            self.captures.append({**common, "id": f"capture-{len(self.captures)}", "view": view,
                                  "path": str(image_path), "sha256": image_hash,
                                  "bytes": len(content), "mime": mime,
                                  "context": capture_context,
                                  "missingContext": _missing(capture_context)})
        metrics = data.get("metrics", [])
        if isinstance(metrics, dict):
            metrics = [{"name": name, **value} if isinstance(value, dict)
                       else {"name": name, "value": value} for name, value in metrics.items()]
        if not isinstance(metrics, list):
            raise ReviewError("metrics must be an array or object")
        for table, table_role in (("baselineYellow", "baseline"), ("candidateYellow", "candidate")):
            for case, values in data.get(table, {}).items():
                for name, value in values.items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        metrics.append({"name": f"{case}.{name}", "value": value, "role": table_role})
        for row in metrics:
            if not isinstance(row, dict) or not isinstance(row.get("name"), str):
                raise ReviewError("Metric requires a name and numeric value")
            value = row.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ReviewError("Metric value must be finite and numeric")
            metric_context = _context(context, row)
            self.metrics.append({**common, "id": f"metric-{len(self.metrics)}",
                                 "role": row.get("role", role), "name": row["name"],
                                 "value": value, "unit": row.get("unit"),
                                 "context": metric_context, "missingContext": _missing(metric_context)})
        self.active.add(path)
        try:
            variants = data.get("variants", [])
            if not isinstance(variants, list):
                raise ReviewError("variants must be an array")
            for child in variants:
                if not isinstance(child, dict) or "report" not in child:
                    raise ReviewError("Variant entry requires a report path")
                if not child.get("reportSha256"):
                    raise ReviewError("Nested report requires reportSha256")
                self.collect(_path(child["report"], path.parent), child["reportSha256"],
                             parent_context=_context(context, child), parent_role=role,
                             parent_label=label, chain_verified=verified)
        finally:
            self.active.remove(path)


def _compare(records: list[dict[str, Any]], *, metrics: bool = False) -> tuple[list[dict], list[dict]]:
    groups: dict[str, list[dict]] = {}
    blocked = []
    for row in records:
        reasons = [f"missing context: {key}" for key in row["missingContext"]]
        if not row["receiptVerified"]:
            reasons.append("receipt chain is not caller-pinned")
        if row["role"] not in ("baseline", "candidate"):
            reasons.append("explicit baseline/candidate role is missing")
        if metrics and (not isinstance(row["unit"], str) or not row["unit"]):
            reasons.append("explicit metric unit is missing")
        if reasons:
            blocked.append({"id": row["id"], "reasons": reasons})
            continue
        identity = [row["context"], row["name"], row["unit"]] if metrics else [row["context"], row["view"]]
        groups.setdefault(_json_key(identity), []).append(row)
    comparisons = []
    for rows in groups.values():
        baseline = [row for row in rows if row["role"] == "baseline"]
        candidate = [row for row in rows if row["role"] == "candidate"]
        if len(baseline) != 1 or len(candidate) != 1:
            reason = "no uniquely matched baseline and candidate for exact context"
            blocked.extend({"id": row["id"], "reasons": [reason]} for row in rows)
            continue
        before, after = baseline[0], candidate[0]
        item = {"baseline": before["id"], "candidate": after["id"], "context": before["context"]}
        if metrics:
            item.update(name=before["name"], unit=before["unit"], baselineValue=before["value"],
                        candidateValue=after["value"], delta=after["value"] - before["value"],
                        percentChange=None if before["value"] == 0 else
                        (after["value"] - before["value"]) / abs(before["value"]) * 100)
        else:
            item["view"] = before["view"]
        comparisons.append(item)
    return comparisons, blocked


def _render(manifest: dict[str, Any], images: Mapping[str, str], title: str) -> str:
    escape = lambda value: html.escape(str(value), quote=True)
    captures = {row["id"]: row for row in manifest["captures"]}

    def figure(row: dict) -> str:
        details = (f'{row["label"]} · {row["role"] or "unassigned"} · '
                   f'{row["context"].get("variant", "variant unspecified")} · {row["view"]}')
        return (f'<figure><img src="{images[row["sha256"]]}" alt="{escape(details)}">'
                f'<figcaption>{escape(details)}<br><small>{escape(row["path"])}<br>'
                f'SHA-256 {row["sha256"]}</small><details><summary>Capture context</summary>'
                f'<pre>{escape(json.dumps(row["context"], indent=2))}</pre></details></figcaption></figure>')

    parts = ["<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">",
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             f'<title>{escape(title)}</title>',
             '<style>body{font:16px system-ui,sans-serif;margin:2rem;background:#15191f;color:#eef2f6}'
             'h1,h2{line-height:1.2}small{overflow-wrap:anywhere;color:#adb8c5}figure{margin:0;background:#222933;padding:1rem}'
             'img{width:100%;height:auto;object-fit:contain}figcaption{padding-top:.6rem}.grid{display:grid;'
             'grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:1rem;margin:1rem 0}'
             '.pair{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin:1rem 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
             'td,th{padding:.6rem;text-align:left;border-bottom:1px solid #566}table{border-collapse:collapse}'
             '@media(max-width:700px){.pair{grid-template-columns:1fr}body{margin:1rem}}</style>',
             f'<h1>{escape(title)}</h1>',
             '<p>Images are verified against receipt hashes. Numerical comparisons require matching context. '
             'This report does not grant visual or campaign acceptance.</p>',
             f'<p>{len(captures)} captures · {len(manifest["captureComparisons"])} matched image pairs · '
             f'{len(manifest["metricComparisons"])} matched metric pairs</p>', '<h2>Matched captures</h2>']
    for pair in manifest["captureComparisons"]:
        parts.append('<div class="pair">' + figure(captures[pair["baseline"]]) + figure(captures[pair["candidate"]]) + '</div>')
    if not manifest["captureComparisons"]:
        parts.append('<p>No complete, uniquely matched baseline/candidate contexts.</p>')
    parts.append('<h2>Capture contact sheet</h2><div class="grid">')
    parts.extend(figure(row) for row in captures.values())
    parts.append('</div><h2>Numerical comparisons</h2><table><tr><th>Metric</th><th>Baseline</th><th>Candidate</th><th>Delta</th><th>Unit</th></tr>')
    for metric in manifest["metricComparisons"]:
        parts.append('<tr>' + ''.join(f'<td>{escape(metric[key])}</td>' for key in
                                     ("name", "baselineValue", "candidateValue", "delta", "unit")) + '</tr>')
    parts.append('</table><h2>Recorded metrics</h2><table><tr><th>Source</th><th>Role</th><th>Metric</th><th>Value</th><th>Unit</th></tr>')
    for metric in manifest["metrics"]:
        parts.append('<tr>' + ''.join(f'<td>{escape(metric[key] if metric[key] is not None else "unspecified")}</td>'
                                     for key in ("label", "role", "name", "value", "unit")) + '</tr>')
    parts.append('</table><h2>Evidence and acceptance</h2><pre>' + escape(json.dumps(manifest["evidence"], indent=2)) + '</pre>')
    parts.append('<h2>Comparison exclusions</h2><pre>' + escape(json.dumps(manifest["comparisonExclusions"], indent=2)) + '</pre>')
    parts.append('<h2>Receipt integrity</h2><pre>' + escape(json.dumps(manifest["receipts"], indent=2)) + '</pre></html>')
    return ''.join(parts)


def generate_report(receipt_paths: Iterable[str | Path | Mapping[str, Any]],
                    output_dir: str | Path, *, title: str = "RoadCraft evidence review",
                    overwrite: bool = False) -> dict[str, Any]:
    """Verify evidence and write review.html / review.json, returning the manifest.

    Inputs may be local paths or {path, sha256} mappings. All root pins are caller
    expectations; newly computed hashes do not retroactively authenticate a run.
    Files are validated before any output is written. Existing output files are
    refused unless overwrite=True. No source asset or receipt is changed.
    """
    collector = _Collector()
    for source in receipt_paths:
        if isinstance(source, Mapping):
            collector.collect(_path(source.get("path"), Path.cwd()), source.get("sha256"))
        else:
            collector.collect(_path(source, Path.cwd()))
    if not collector.sources:
        raise ReviewError("At least one receipt is required")
    capture_pairs, capture_blocked = _compare(collector.captures)
    metric_pairs, metric_blocked = _compare(collector.metrics, metrics=True)
    manifest = {"schemaVersion": 1, "kind": "roadcraft.review", "title": title,
                "receipts": collector.sources, "captures": collector.captures,
                "metrics": collector.metrics, "captureComparisons": capture_pairs,
                "metricComparisons": metric_pairs,
                "comparisonExclusions": capture_blocked + metric_blocked,
                "evidence": {
                    "captured": {"state": "hash_verified" if collector.captures else "not_provided",
                                 "count": len(collector.captures)},
                    "numerical": {"state": "compared" if metric_pairs else
                                  "recorded_only" if collector.metrics else "not_provided",
                                  "records": len(collector.metrics), "matchedPairs": len(metric_pairs),
                                  "acceptance": "not_assessed_by_report"},
                    "visual": {"state": "not_assessed_by_report", "claims": collector.claims["visual"]},
                    "campaign": {"state": "not_assessed_by_report", "claims": collector.claims["campaign"]}}}
    output = Path(output_dir).expanduser().resolve()
    html_path, json_path = output / "review.html", output / "review.json"
    if any(path.resolve() != path for path in (html_path, json_path)):
        raise ReviewError("Report output must not be a symbolic link")
    sources = {Path(row["path"]) for row in collector.sources + collector.captures}
    if html_path in sources or json_path in sources:
        raise ReviewError("Report output would overwrite input evidence")
    if not overwrite and (html_path.exists() or json_path.exists()):
        raise ReviewError("Report output already exists")
    rendered = _render(manifest, collector.images, title).encode("utf-8")
    manifest["artifacts"] = {"html": str(html_path), "htmlSha256": hashlib.sha256(rendered).hexdigest(),
                             "manifest": str(json_path)}
    serialized = (json.dumps(manifest, indent=2, allow_nan=False) + "\n").encode("utf-8")
    output.mkdir(parents=True, exist_ok=True)
    mode = "wb" if overwrite else "xb"
    with html_path.open(mode) as stream:
        stream.write(rendered)
    with json_path.open(mode) as stream:
        stream.write(serialized)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", nargs="+", help="Local JSON receipt paths")
    parser.add_argument("--output", required=True)
    parser.add_argument("--title", default="RoadCraft evidence review")
    parser.add_argument("--pin", action="append", default=[], metavar="PATH=SHA256",
                        help="Expected receipt hash; may be repeated")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        pins = {}
        for value in args.pin:
            path, separator, digest = value.rpartition("=")
            if not separator:
                raise ReviewError("--pin requires PATH=SHA256")
            pins[str(_path(path, Path.cwd()))] = digest
        sources = [{"path": str(_path(path, Path.cwd())),
                    "sha256": pins.get(str(_path(path, Path.cwd())))} for path in args.receipts]
        result = generate_report(sources, args.output, title=args.title, overwrite=args.overwrite)
    except (ReviewError, OSError) as exc:
        parser.exit(2, f"review: {exc}\n")
    print(json.dumps(result["artifacts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
