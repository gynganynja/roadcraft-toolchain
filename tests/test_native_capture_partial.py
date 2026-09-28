"""Synthetic per-view pre-screenshot transport and timing linkage checks."""

from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import struct
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft.native_capture_partial import (  # noqa: E402
    PartialViewError, _read, build_partial_view, verify_partial_view,
)


def png() -> bytes:
    def chunk(name: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + name + data +
                struct.pack(">I", zlib.crc32(name + data)))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00")) + chunk(b"IEND", b""))


def when(seconds: float) -> str:
    return (datetime(2026, 9, 28, tzinfo=timezone.utc) +
            timedelta(seconds=seconds)).isoformat()


def response(light_on: bool) -> str:
    return (
        "D11T_SYSTEMS_OK\npreviousResolution 1 1\n"
        "light d11_light pos 1 2 3 tangent 0 0 1 intensity 5 radius 30 cone 35\n"
        f"spotStarted d11_light {'true' if light_on else 'false'}\n"
        "cameraResolution 1 1\n"
        "cameraWorld pos 0.1 2 3 forward 0 0 1\n"
    )


def fixture(root: Path) -> dict:
    run = root / "aaa_maroon_a1b2c3d4ma"
    run.mkdir()
    scene_dir = root / "d11t_maroon_validation"
    scene_dir.mkdir()
    scene = scene_dir / "d11t_maroon_validation.scn"
    scene.write_bytes(b"source scene only")
    helper = run / "native_controls.ps1"
    helper.write_bytes(b"bounded synthetic helper")
    helper_sha = sha256(helper.read_bytes()).hexdigest()
    image = run / "cab_front_seat.png"
    image.write_bytes(png())
    paths = {
        "camera_transport": run / "camera_front_seat.json",
        "pre_transport": run / "pre_capture_front_seat.json",
        "capture_transport": run / "capture_front_seat.json",
    }
    specs = (
        ("camera_transport", "SetCabFrontSeat", False, 0.2, 0.8, False,
         "var shot = new Transform3d()\nreturn result"),
        ("pre_transport", "Read", True, 2.15, 2.25, False,
         "return result"),
        ("capture_transport", "CaptureCabFrontSeat", False, 2.45, 2.65, True,
         'SaveScreenshot(ScreenshotSaveTarget.FILE,"d11_cab_a1b2c3d4ma_front_seat",false,ScreenshotFormat.PNG)\nreturn result'),
    )
    for index, (key, mode, read_only, sent, received, light_on, script) in enumerate(specs, 1):
        reply = response(light_on)
        raw = reply.encode("utf-8") + b"\0"
        paths[key].write_text(json.dumps({
            "schema": 1, "status": "pass", "stage": "response_received",
            "mode": mode, "readOnly": read_only, "engineProcessId": 1234,
            "helperSha256": helper_sha, "workspace": "RoadBuilder",
            "requestId": f"{{1234567{index}-ABCD-4abc-8ABC-ABCDEF123456}}",
            "requestSentUtc": when(sent), "receivedUtc": when(received),
            "script": script, "response": reply, "responseBase64": base64.b64encode(raw).decode(),
            "responseBytes": len(raw),
        }), encoding="utf-8")
    names = (
        ("SetCabFrontSeat", 0, 1), ("SettleCamera", 1, 2),
        ("ScreenshotSourceGuard", 2, 2.1), ("ReadPreCapture", 2.1, 2.3),
        ("CaptureCabFrontSeat", 2.4, 2.7), ("SaveScreenshot:front_seat", 2.8, 3),
    )
    events = [{"action": action, "view": "front_seat", "status": "PASS",
               "enginePid": 1234, "startedUtc": when(start), "finishedUtc": when(end)}
              for action, start, end in names]
    return {"run_id": "a1b2c3d4", "variant": "maroon", "view": "front_seat",
            "engine_pid": 1234, "scene": scene, "helper": helper, "image": image,
            **paths, "action_events": events}


class NativePartialViewTests(unittest.TestCase):
    def test_growth_during_read_is_bounded_before_allocating_entire_file(self) -> None:
        class GrowingFile:
            def __init__(self) -> None:
                self.read_size = None

            def is_absolute(self) -> bool:
                return True

            def is_symlink(self) -> bool:
                return False

            def is_file(self) -> bool:
                return True

            def stat(self) -> SimpleNamespace:
                return SimpleNamespace(st_size=1, st_mtime_ns=1, st_ino=1)

            def open(self, mode: str) -> io.BytesIO:
                stream = io.BytesIO(b"x" * 100)
                original_read = stream.read

                def bounded_read(size: int = -1) -> bytes:
                    self.read_size = size
                    return original_read(size)

                stream.read = bounded_read  # type: ignore[method-assign]
                return stream

        growing = GrowingFile()
        with self.assertRaisesRegex(PartialViewError, "grew beyond size limit"):
            _read(growing, "growing fixture", 8)  # type: ignore[arg-type]
        self.assertEqual(growing.read_size, 9)

    def test_links_exact_pre_response_to_following_capture_without_pair_claim(self) -> None:
        with TemporaryDirectory() as directory:
            args = fixture(Path(directory))
            record = build_partial_view(**args)
            self.assertEqual(record["status"], "PARTIAL_PRE_SCREENSHOT_CONTEXT")
            self.assertFalse(record["pairProtocolEligible"])
            self.assertFalse(record["loadedSceneVerified"])
            self.assertFalse(record["declaredTriggerWindow"]["exactTriggerUtcKnown"])
            self.assertEqual(record["screenshot"]["resolutionPixels"], [1, 1])
            self.assertFalse(record["preScreenshotReported"]["truckLocalLights"][0]["enabled"])
            self.assertTrue(record["postTriggerReported"]["truckLocalLights"][0]["enabled"])
            self.assertIn("lightingState.exposure", record["missingMatchedPairRuntimeFields"])
            self.assertEqual(verify_partial_view(record)["status"],
                             "PARTIAL_VIEW_LINKAGE_CONSISTENT")

    def test_rejects_wrong_transport_identity_or_raw_reply(self) -> None:
        with TemporaryDirectory() as directory:
            args = fixture(Path(directory))
            path = args["pre_transport"]
            baseline = json.loads(path.read_text(encoding="utf-8"))
            for label, change in (
                ("wrong mode", {"mode": "SetCabFrontSeat"}),
                ("not read only", {"readOnly": False}),
                ("wrong PID", {"engineProcessId": 5678}),
                ("wrong helper", {"helperSha256": "0" * 64}),
                ("wrong workspace", {"workspace": ""}),
                ("wrong raw reply", {"responseBase64": base64.b64encode(b"other\0").decode()}),
                ("oversize raw reply", {"responseBase64":
                                        base64.b64encode(b"x" * 65_536 + b"\0").decode()}),
                ("malformed GUID", {"requestId": "not-a-guid"}),
            ):
                with self.subTest(label=label):
                    path.write_text(json.dumps({**baseline, **change}), encoding="utf-8")
                    with self.assertRaises(PartialViewError):
                        build_partial_view(**args)
            path.write_text(json.dumps(baseline), encoding="utf-8")
            capture = args["capture_transport"]
            row = json.loads(capture.read_text(encoding="utf-8"))
            row["script"] = "return result"
            capture.write_text(json.dumps(row), encoding="utf-8")
            with self.assertRaisesRegex(PartialViewError, "screenshot action"):
                build_partial_view(**args)

    def test_rejects_stale_or_overlapping_action_windows(self) -> None:
        with TemporaryDirectory() as directory:
            args = fixture(Path(directory))
            late = deepcopy(args)
            late["action_events"] = deepcopy(args["action_events"])
            late["action_events"][4]["startedUtc"] = when(20)
            late["action_events"][4]["finishedUtc"] = when(21)
            late["action_events"][5]["startedUtc"] = when(22)
            late["action_events"][5]["finishedUtc"] = when(23)
            with self.assertRaises(PartialViewError):
                build_partial_view(**late)
            overlap = deepcopy(args)
            overlap["action_events"] = deepcopy(args["action_events"])
            overlap["action_events"][3]["startedUtc"] = when(2.0)
            with self.assertRaisesRegex(PartialViewError, "overlap"):
                build_partial_view(**overlap)

    def test_rejects_tampered_saved_link_and_png(self) -> None:
        with TemporaryDirectory() as directory:
            args = fixture(Path(directory))
            record = build_partial_view(**args)
            changed = deepcopy(record)
            changed["pairProtocolEligible"] = True
            with self.assertRaisesRegex(PartialViewError, "differs"):
                verify_partial_view(changed)
            args["image"].write_bytes(args["image"].read_bytes() + b"changed")
            with self.assertRaisesRegex(PartialViewError, "differs"):
                verify_partial_view(record)


if __name__ == "__main__":
    unittest.main()
