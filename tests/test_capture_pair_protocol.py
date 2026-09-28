"""Synthetic capture-time provenance and matched-pair gates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zlib


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import capture_pair_protocol as gate  # noqa: E402


def png(width: int = 2, height: int = 2) -> bytes:
    def chunk(tag: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + tag + body +
                struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))
    pixels = b"".join(b"\0" + b"\x10\x20\x30" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


class CapturePairTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.light = {
            "environment": {"weather": "clear", "timeOfDay": 12.0,
                            "sunDirection": [0, 1, 0], "ambientRgb": [0.2, 0.2, 0.2]},
            "localLights": [{"id": "cab", "enabled": True, "intensity": 0.7}],
            "exposure": 1.0, "tonemap": "filmic", "rendererMode": "retail",
        }

    def write(self, name: str, value: bytes | dict) -> dict[str, str]:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(value, sort_keys=True).encode("utf-8")
               if isinstance(value, dict) else value)
        path.write_bytes(raw)
        return {"path": str(path), "sha256": sha256(raw).hexdigest()}

    def fixture(self, *, mutate=None, variants=None, protocol_id="d11-protocol-v1",
                image_size=(2, 2), full_d11=False, run_ids=None) -> Path:
        protocol_variants = (list(gate.native_capture_postflight.VARIANTS)
                             if full_d11 else ["maroon"])
        if full_d11:
            camera_specs = {view: {"basis": "cockpit_camera",
                                   "spec": [[0, 0, 0], [1, index, 0]]}
                            for index, view in enumerate(gate.native_capture_postflight.VIEWS)}
        else:
            camera_specs = {
                "front": {"basis": "cockpit_camera", "spec": [[0, 0, 0], [1, 0, 0]]},
                "right": {"basis": "cockpit_camera", "spec": [[0, 0, 0], [0, -1, 0]]},
            }
        runner = self.write("runner.py", b"native runner")
        script_body = "query runtime camera lighting and resolution"
        script = self.write("probe.rsm", script_body.encode())
        protocol = self.write("protocol.json", {
            "schemaVersion": 1, "id": protocol_id, "runner": runner,
            "probeScript": script, "variants": protocol_variants,
            "views": [{"view": name, "camera": spec}
                      for name, spec in camera_specs.items()],
            "resolution": [2, 2], "lightingState": self.light,
            "maxObservationAgeSeconds": 10,
        })
        scenes = {variant: self.write(f"{variant}.scn", f"scene:{variant}".encode())
                  for variant in protocol_variants}
        runs = {}
        for role in ("baseline", "candidate"):
            run_id = run_ids.get(role, f"{role}-run") if run_ids else f"{role}-run"
            package = self.write(f"{role}.pak", role.encode())
            variant_names = variants.get(role, protocol_variants) if variants else protocol_variants
            variant_rows = []
            for variant in variant_names:
                scene = (scenes[variant] if variant in scenes else
                         self.write(f"{variant}.scn", f"scene:{variant}".encode()))
                captures = []
                for index, (view, spec) in enumerate(camera_specs.items()):
                    base = datetime(2026, 9, 28, tzinfo=timezone.utc)
                    second = 10 + protocol_variants.index(variant) * 60 + index * 4 if variant in protocol_variants else 10
                    timestamp = lambda offset: (base + timedelta(seconds=second + offset)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ")
                    image = self.write(f"{role}/{variant}/{view}.png", png(*image_size))
                    response = {
                        "status": "OBSERVED", "runId": run_id, "role": role,
                        "variant": variant, "view": view, "enginePid": 1234,
                        "protocolSha256": protocol["sha256"],
                        "loadedSceneSha256": scene["sha256"],
                        "resolution": [2, 2], "lightingState": dict(self.light),
                        "camera": {**spec, "position": [index, 0, 0],
                                   "forward": [1, 0, 0], "up": [0, 0, 1]},
                    }
                    observation = {
                        "schemaVersion": 1, "source": "native-editor-response",
                        "probeScriptSha256": script["sha256"],
                        "requestScript": script_body,
                        "requestSentUtc": timestamp(0),
                        "responseReceivedUtc": timestamp(1),
                    }
                    capture = {"view": view, "image": image,
                               "triggeredUtc": timestamp(2),
                               "copiedUtc": timestamp(3)}
                    if mutate is not None:
                        mutate(role, variant, view, response, observation, capture)
                    observation["responseRaw"] = json.dumps(response, sort_keys=True)
                    capture["observation"] = self.write(
                        f"{role}/{variant}/{view}_observation.json", observation)
                    captures.append(capture)
                variant_rows.append({"variant": variant, "scene": scene,
                                     "enginePid": 1234, "captures": captures})
            runs[role] = self.write(f"{role}_run.json", {
                "schemaVersion": 1, "status": "CAPTURE_READY", "role": role,
                "runId": run_id, "protocolSha256": protocol["sha256"],
                "runnerSha256": runner["sha256"], "package": package,
                "startedUtc": "2026-09-28T00:00:00Z",
                "finishedUtc": "2026-09-28T00:04:00Z",
                "variants": variant_rows,
            })
        pair = self.write("pair.json", {"schemaVersion": 1,
                                        "protocol": protocol, "runs": runs})
        return Path(pair["path"])

    def native_binding_fixture(self) -> tuple[Path, dict[str, str]]:
        """Make a synthetic candidate chain; postflight itself is tested elsewhere."""
        pair_path = self.fixture(full_d11=True, run_ids={
            "baseline": "a1b2c3d4", "candidate": "e5f6a7b8"})
        pair = json.loads(pair_path.read_text(encoding="utf-8"))
        protocol = json.loads(Path(pair["protocol"]["path"]).read_text(encoding="utf-8"))
        installed = self.write("installed.pak", b"accepted baseline")
        external: dict[str, str] = {}
        bindings = {}
        for role in ("candidate",):
            run_path = Path(pair["runs"][role]["path"])
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run_id = run["runId"]
            native_root = self.root / f"native_{role}"
            output_hashes = {}
            contexts = {}
            for variant_row in run["variants"]:
                variant = variant_row["variant"]
                native_run = native_root / "runs" / (
                    f"aaa_{variant}_{run_id}{variant[:2]}")
                contexts[variant] = {"scene": variant_row["scene"]["path"],
                                     "sceneSha256": variant_row["scene"]["sha256"]}
                actions = [{"action": "InspectInteriorGeom"}]
                for capture in variant_row["captures"]:
                    view = capture["view"]
                    image = self.write(
                        str((native_run / f"cab_{view}.png").relative_to(self.root)),
                        Path(capture["image"]["path"]).read_bytes())
                    capture["image"] = image
                    output_hashes[image["path"]] = image["sha256"]
                    observation = json.loads(Path(capture["observation"]["path"])
                                             .read_text(encoding="utf-8"))
                    transport = self.write(
                        str((native_run / f"pre_capture_{view}.json")
                            .relative_to(self.root)),
                        {"status": "pass", "stage": "response_received",
                         "mode": "Read", "readOnly": True,
                         "engineProcessId": variant_row["enginePid"],
                         "script": observation["requestScript"],
                         "response": observation["responseRaw"],
                         "requestSentUtc": observation["requestSentUtc"],
                         "receivedUtc": observation["responseReceivedUtc"]})
                    output_hashes[transport["path"]] = transport["sha256"]
                    observation["nativeTransport"] = transport
                    capture["observation"] = self.write(
                        str(Path(capture["observation"]["path"]).relative_to(self.root)),
                        observation)
                    sent = datetime.fromisoformat(
                        observation["requestSentUtc"].replace("Z", "+00:00"))
                    stamp = lambda offset: (sent + timedelta(seconds=offset)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ")
                    mode = view.title().replace("_", "")
                    for action, start, finish in (
                        ("SetCab" + mode, -3, -2), ("SettleCamera", -2, -1),
                        ("ScreenshotSourceGuard", -1, 0),
                        ("ReadPreCapture", 0, 1),
                        ("CaptureCab" + mode, 1, 2),
                        ("SaveScreenshot:" + view, 2, 3)):
                        actions.append({"action": action, "startedUtc": stamp(start),
                                        "finishedUtc": stamp(finish)})
                report = self.write(
                    str((native_run / "report.json").relative_to(self.root)),
                    {"enginePid": variant_row["enginePid"], "actionEvents": actions})
                output_hashes[report["path"]] = report["sha256"]
            pair["runs"][role] = self.write(run_path.name, run)
            plan = self.write(f"native_{role}/plan.json", {
                "outputContract": {
                    "runner": protocol["runner"]["path"],
                    "runnerSha256": protocol["runner"]["sha256"],
                    "variantContexts": contexts}})
            receipt = self.write(f"native_{role}/candidate_capture_{run_id}.json", {
                "runId": run_id, "requiredOutputSha256": output_hashes})
            bindings[role] = {
                "receipt": receipt, "plan": plan,
                "candidatePackage": run["package"],
                "installedPackage": installed,
                "baselineSha256": installed["sha256"],
            }
            external = {"receiptSha256": receipt["sha256"],
                        "planSha256": plan["sha256"]}
        pair["candidateNativeReceipt"] = bindings["candidate"]
        self.write("pair.json", pair)
        return pair_path, external

    @staticmethod
    def passing_postflight(*args, **kwargs) -> dict:
        return {"captureIntegrityPassed": True, "checkedViews": 45,
                "checkedPartialViews": 45, "checkedReadRequests": 45,
                "receiptSha256": kwargs["expected_capture_receipt_sha256"],
                "runId": kwargs["run_id"]}

    def test_partial_context_is_comparable_but_not_d11_complete(self) -> None:
        result = gate.validate(self.fixture())
        self.assertTrue(result["contextComparable"])
        self.assertFalse(result["pairComparable"])
        self.assertEqual(result["matchedViews"], 2)
        self.assertFalse(result["visualReviewed"])
        self.assertFalse(result["campaignAccepted"])
        self.assertFalse(result["technicalPassed"])
        self.assertFalse(result["releaseReady"])

    def test_exact_d11_roster_can_be_compared_but_not_released(self) -> None:
        result = gate.validate(self.fixture(full_d11=True))
        self.assertEqual(result["matchedViews"], 45)
        self.assertTrue(result["d11RosterComplete"])
        self.assertTrue(result["pairComparable"])
        self.assertFalse(result["nativePostflightVerified"])
        self.assertFalse(result["nativeEvidenceLinked"])
        self.assertFalse(result["technicalPassed"])

    def test_native_evidence_needs_external_pins_and_exact_view_links(self) -> None:
        pair, external = self.native_binding_fixture()
        self.assertFalse(gate.validate(pair)["nativeEvidenceLinked"])
        with mock.patch.object(gate.native_capture_postflight, "validate",
                               side_effect=self.passing_postflight) as postflight:
            result = gate.validate(pair, expected_candidate_native_pins=external)
        self.assertEqual(postflight.call_count, 1)
        self.assertTrue(result["candidateNativeReceiptLinked"])
        self.assertTrue(result["candidateNativePostflightVerified"])
        self.assertFalse(result["nativeEvidenceLinked"])
        self.assertFalse(result["nativePostflightVerified"])
        self.assertTrue(result["pairComparable"])
        self.assertFalse(result["captureProcessAuthenticated"])
        self.assertFalse(result["technicalPassed"])

    def test_native_binding_rejects_external_pin_and_failed_postflight(self) -> None:
        pair, external = self.native_binding_fixture()
        changed = dict(external)
        changed["receiptSha256"] = "0" * 64
        with self.assertRaisesRegex(gate.CapturePairError, "external pin"):
            gate.validate(pair, expected_candidate_native_pins=changed)
        with mock.patch.object(gate.native_capture_postflight, "validate",
                               return_value={"captureIntegrityPassed": False}):
            with self.assertRaisesRegex(gate.CapturePairError, "postflight"):
                gate.validate(pair, expected_candidate_native_pins=external)

    def test_native_binding_rejects_a_different_plan_runner(self) -> None:
        pair, external = self.native_binding_fixture()
        pair_row = json.loads(pair.read_text(encoding="utf-8"))
        binding = pair_row["candidateNativeReceipt"]
        plan_path = Path(binding["plan"]["path"])
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        same_bytes_different_file = self.write("other_runner.py", b"native runner")
        plan["outputContract"]["runner"] = same_bytes_different_file["path"]
        plan["outputContract"]["runnerSha256"] = same_bytes_different_file["sha256"]
        binding["plan"] = self.write(
            str(plan_path.relative_to(self.root)), plan)
        external["planSha256"] = binding["plan"]["sha256"]
        self.write("pair.json", pair_row)
        with mock.patch.object(gate.native_capture_postflight, "validate",
                               side_effect=self.passing_postflight):
            with self.assertRaisesRegex(gate.CapturePairError,
                                        "protocol runner differs from native contract"):
                gate.validate(pair, expected_candidate_native_pins=external)

    def test_native_binding_accepts_canonical_runner_path_alias(self) -> None:
        pair, external = self.native_binding_fixture()
        pair_row = json.loads(pair.read_text(encoding="utf-8"))
        binding = pair_row["candidateNativeReceipt"]
        plan_path = Path(binding["plan"]["path"])
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        runner = Path(plan["outputContract"]["runner"])
        alias = runner.parent / ".." / runner.parent.name / runner.name
        self.assertNotEqual(str(alias), str(runner))
        self.assertTrue(alias.samefile(runner))
        plan["outputContract"]["runner"] = str(alias)
        binding["plan"] = self.write(
            str(plan_path.relative_to(self.root)), plan)
        external["planSha256"] = binding["plan"]["sha256"]
        self.write("pair.json", pair_row)
        with mock.patch.object(gate.native_capture_postflight, "validate",
                               side_effect=self.passing_postflight):
            result = gate.validate(pair, expected_candidate_native_pins=external)
        self.assertTrue(result["candidateNativeReceiptLinked"])
        self.assertFalse(result["nativeEvidenceLinked"])

    @unittest.skipUnless(os.name == "nt", "Windows drive-letter identity")
    def test_native_binding_accepts_windows_drive_letter_case_alias(self) -> None:
        pair, external = self.native_binding_fixture()
        pair_row = json.loads(pair.read_text(encoding="utf-8"))
        binding = pair_row["candidateNativeReceipt"]
        plan_path = Path(binding["plan"]["path"])
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        runner = Path(plan["outputContract"]["runner"])
        self.assertTrue(runner.drive)
        alias = runner.drive.swapcase() + str(runner)[len(runner.drive):]
        self.assertNotEqual(alias, str(runner))
        self.assertTrue(Path(alias).samefile(runner))
        plan["outputContract"]["runner"] = alias
        binding["plan"] = self.write(
            str(plan_path.relative_to(self.root)), plan)
        external["planSha256"] = binding["plan"]["sha256"]
        self.write("pair.json", pair_row)
        with mock.patch.object(gate.native_capture_postflight, "validate",
                               side_effect=self.passing_postflight):
            result = gate.validate(pair, expected_candidate_native_pins=external)
        self.assertTrue(result["candidateNativeReceiptLinked"])
        self.assertFalse(result["nativeEvidenceLinked"])

    def test_native_binding_rejects_unlinked_observation_and_image(self) -> None:
        pair, external = self.native_binding_fixture()
        run_path = self.root / "candidate_run.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        capture = run["variants"][0]["captures"][0]
        observed_path = Path(capture["observation"]["path"])
        observed = json.loads(observed_path.read_text(encoding="utf-8"))
        observed["nativeTransport"]["sha256"] = "0" * 64
        capture["observation"] = self.write(
            str(observed_path.relative_to(self.root)), observed)
        pair_row = json.loads(pair.read_text(encoding="utf-8"))
        pair_row["runs"]["candidate"] = self.write(run_path.name, run)
        self.write("pair.json", pair_row)
        with mock.patch.object(gate.native_capture_postflight, "validate",
                               side_effect=self.passing_postflight):
            with self.assertRaisesRegex(gate.CapturePairError, "native transport link"):
                gate.validate(pair, expected_candidate_native_pins=external)
        pair, external = self.native_binding_fixture()
        run = json.loads(run_path.read_text(encoding="utf-8"))
        run["variants"][0]["captures"][0]["image"] = self.write("alternate.png", png())
        pair_row = json.loads(pair.read_text(encoding="utf-8"))
        pair_row["runs"]["candidate"] = self.write(run_path.name, run)
        self.write("pair.json", pair_row)
        with mock.patch.object(gate.native_capture_postflight, "validate",
                               side_effect=self.passing_postflight):
            with self.assertRaisesRegex(gate.CapturePairError, "image differs from native"):
                gate.validate(pair, expected_candidate_native_pins=external)


    def test_missing_and_mismatched_capture_time_lighting_fail(self) -> None:
        def missing(role, variant, view, response, observation, capture):
            if role == "candidate" and view == "front":
                response.pop("lightingState")
        with self.assertRaisesRegex(gate.CapturePairError, "observed lighting"):
            gate.validate(self.fixture(mutate=missing))
        def changed(role, variant, view, response, observation, capture):
            if role == "candidate" and view == "front":
                response["lightingState"]["environment"]["weather"] = "rain"
        with self.assertRaisesRegex(gate.CapturePairError, "observed lighting"):
            gate.validate(self.fixture(mutate=changed))

    def test_camera_mismatch_and_missing_transform_fail(self) -> None:
        def changed(role, variant, view, response, observation, capture):
            if role == "candidate" and view == "right":
                response["camera"]["position"] = [4, 0, 0]
        with self.assertRaisesRegex(gate.CapturePairError, "differs from baseline"):
            gate.validate(self.fixture(mutate=changed))
        def missing(role, variant, view, response, observation, capture):
            if role == "candidate" and view == "right":
                response["camera"].pop("position")
        with self.assertRaisesRegex(gate.CapturePairError, "position"):
            gate.validate(self.fixture(mutate=missing))

    def test_runtime_and_png_resolution_both_must_match(self) -> None:
        def changed(role, variant, view, response, observation, capture):
            if role == "candidate" and view == "front":
                response["resolution"] = [3, 2]
        with self.assertRaisesRegex(gate.CapturePairError, "observed resolution mismatch"):
            gate.validate(self.fixture(mutate=changed))
        with self.assertRaisesRegex(gate.CapturePairError, "image resolution mismatch"):
            gate.validate(self.fixture(image_size=(3, 2)))

    def test_variant_protocol_and_probe_identity_fail_closed(self) -> None:
        with self.assertRaisesRegex(gate.CapturePairError, "variant roster"):
            gate.validate(self.fixture(variants={"candidate": ["nearnew"]}))
        def changed(role, variant, view, response, observation, capture):
            if role == "candidate" and view == "front":
                response["protocolSha256"] = "0" * 64
        with self.assertRaisesRegex(gate.CapturePairError, "observation provenance mismatch"):
            gate.validate(self.fixture(mutate=changed))
        def unpinned_probe(role, variant, view, response, observation, capture):
            if role == "candidate" and view == "front":
                observation.pop("probeScriptSha256")
        with self.assertRaisesRegex(gate.CapturePairError, "observation provenance mismatch"):
            gate.validate(self.fixture(mutate=unpinned_probe))
        def changed_request(role, variant, view, response, observation, capture):
            if role == "candidate" and view == "front":
                observation["requestScript"] = "unreviewed request"
        with self.assertRaisesRegex(gate.CapturePairError, "pinned probe script"):
            gate.validate(self.fixture(mutate=changed_request))

    def test_stale_observation_and_tampered_image_fail(self) -> None:
        def stale(role, variant, view, response, observation, capture):
            if role == "candidate" and view == "front":
                observation["responseReceivedUtc"] = "2026-09-28T00:00:01Z"
                observation["requestSentUtc"] = "2026-09-28T00:00:00Z"
        with self.assertRaisesRegex(gate.CapturePairError, "immediately before"):
            gate.validate(self.fixture(mutate=stale))
        pair = self.fixture()
        image = self.root / "candidate/maroon/front.png"
        image.write_bytes(png(3, 2))
        with self.assertRaisesRegex(gate.CapturePairError, "SHA-256 mismatch"):
            gate.validate(pair)

    def test_one_screenshot_file_cannot_fill_two_view_slots(self) -> None:
        def reused(role, variant, view, response, observation, capture):
            if role == "candidate" and view == "right":
                capture["image"] = {
                    "path": str(self.root / "candidate/maroon/front.png"),
                    "sha256": sha256(png()).hexdigest(),
                }
        with self.assertRaisesRegex(gate.CapturePairError, "reuses the capture output"):
            gate.validate(self.fixture(mutate=reused))

    def test_baseline_and_candidate_need_distinct_run_ids(self) -> None:
        with self.assertRaisesRegex(gate.CapturePairError, "run IDs must differ"):
            gate.validate(self.fixture(run_ids={"baseline": "same-run", "candidate": "same-run"}))

    def test_hard_linked_screenshot_cannot_fill_two_view_slots(self) -> None:
        pair = self.fixture()
        first = self.root / "candidate/maroon/front.png"
        second = self.root / "candidate/maroon/right.png"
        second.unlink()
        try:
            os.link(first, second)
        except OSError as error:
            self.skipTest(f"Filesystem does not support scratch hard links: {error}")
        with self.assertRaisesRegex(gate.CapturePairError, "reuses the capture output"):
            gate.validate(pair)

    def test_view_observation_cannot_overlap_previous_copy(self) -> None:
        def overlapping(role, variant, view, response, observation, capture):
            if role == "candidate" and view == "right":
                observation["requestSentUtc"] = "2026-09-28T00:00:12Z"
                observation["responseReceivedUtc"] = "2026-09-28T00:00:13Z"
        with self.assertRaisesRegex(gate.CapturePairError, "overlaps an earlier capture"):
            gate.validate(self.fixture(mutate=overlapping))


if __name__ == "__main__":
    unittest.main()
