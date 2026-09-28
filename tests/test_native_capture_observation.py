"""Diagnostics for the actual fields in D11 Automation/ExecSsl replies."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import native_capture_observation as observation  # noqa: E402


def transport(*, mode: str = "SetCabFrontSeat", light_on: bool = False) -> dict:
    return {
        "schema": 1, "status": "pass", "stage": "response_received",
        "mode": mode, "readOnly": False, "engineProcessId": 14020,
        "requestSentUtc": "2026-09-27T23:17:43.5488948Z",
        "receivedUtc": "2026-09-27T23:17:43.6911718Z",
        "script": "query the editor and return result",
        "response": (
            "D11T_SYSTEMS_OK\npreviousResolution 913 559\n"
            "light d11t_work_front_1 pos 1.1362 64.4436 -15.4022 "
            "tangent 0.0000 -0.4819 0.8762 intensity 5.000 radius 30.000 cone 35.000\n"
            f"spotStarted d11t_work_front_1 {'true' if light_on else 'false'}\n"
            "cameraResolution 913 559\n"
            "cameraWorld pos 0.0667 63.6242 -18.4990 "
            "forward -0.0001 -0.1422 0.9898\n"
        ),
    }


class NativeCaptureObservationTests(unittest.TestCase):
    def test_extracts_only_runtime_values_reported_by_editor(self) -> None:
        result = observation.inspect_transport(transport())
        self.assertEqual(result["reported"]["activePlayCameraResolution"], [913, 559])
        self.assertEqual(result["reported"]["activePlayCamera"]["position"],
                         [0.0667, 63.6242, -18.499])
        self.assertEqual(result["reported"]["activePlayCamera"]["forward"],
                         [-0.0001, -0.1422, 0.9898])
        self.assertEqual(result["reported"]["truckLocalLights"][0]["enabled"], False)
        self.assertEqual(result["reported"]["truckLocalLights"][0]["intensity"], 5.0)
        self.assertEqual(result["status"], "PARTIAL_CONTEXT_ONLY")
        self.assertFalse(result["pairProtocolEligible"])
        self.assertIn("camera.up", result["missingMatchedPairRuntimeFields"])
        self.assertIn("lightingState.exposure", result["missingMatchedPairRuntimeFields"])
        self.assertIn("loadedSceneSha256", result["missingMatchedPairCaptureLinkage"])
        self.assertIn("screenshot.imageDimensions", result["missingMatchedPairCaptureLinkage"])
        self.assertNotIn("lightingState", result["reported"])

    def test_set_and_capture_responses_can_have_different_light_state(self) -> None:
        set_context = observation.inspect_transport(transport())
        capture_context = observation.inspect_transport(
            transport(mode="CaptureCabFrontSeat", light_on=True))
        self.assertFalse(set_context["reported"]["truckLocalLights"][0]["enabled"])
        self.assertTrue(capture_context["reported"]["truckLocalLights"][0]["enabled"])
        self.assertFalse(capture_context["pairProtocolEligible"])

    def test_rejects_nonpassing_or_incomplete_response(self) -> None:
        bad = transport()
        bad["status"] = "fail"
        with self.assertRaisesRegex(observation.NativeObservationError, "passing"):
            observation.inspect_transport(bad)
        bad = transport()
        bad["response"] = bad["response"].replace("spotStarted d11t_work_front_1 false\n", "")
        with self.assertRaisesRegex(observation.NativeObservationError, "enabled states"):
            observation.inspect_transport(bad)
        bad = transport()
        bad["response"] = bad["response"].replace("cameraWorld pos", "cameraUnknown pos")
        with self.assertRaisesRegex(observation.NativeObservationError, "camera transform"):
            observation.inspect_transport(bad)

    def test_path_reader_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "transport.json"
            target.write_text("{}", encoding="utf-8")
            link = Path(temp) / "link.json"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("File symlinks unavailable")
            with self.assertRaisesRegex(observation.NativeObservationError, "link"):
                observation.inspect_transport_path(link)


if __name__ == "__main__":
    unittest.main()
