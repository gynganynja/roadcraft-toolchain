"""Synthetic capture-time provenance and matched-pair gates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
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
                image_size=(2, 2), full_d11=False) -> Path:
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
            run_id = f"{role}-run"
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
        self.assertFalse(result["technicalPassed"])

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


if __name__ == "__main__":
    unittest.main()
