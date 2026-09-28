"""Portable fail-closed checks for the exact pre-screenshot SSL request."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from roadcraft import native_precapture_request as request


TEMPLATE = """$script=@'
var result = "observed"
__ACTION__
return result
'@
$action=''
if($Mode -eq 'Capture'){
 $action='SaveScreenshot(ScreenshotSaveTarget.FILE,"scratch",false,ScreenshotFormat.PNG)'
}
$script=$script.Replace('__ACTION__',$action)
$speaker.Send((New-SslMessage $requestId $script))
"""
TEMPLATE_RELATIVE = "D11_Final_Candidate_20260925/native_controls_template.ps1"


class PrecaptureRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name).resolve()
        self.helper = self.workspace / "aaa_maroon_bd58bce0ma" / "native_controls.ps1"
        self.helper.parent.mkdir()
        self.helper.write_text(TEMPLATE, encoding="utf-8")
        self.expected = TEMPLATE.split("$script=@'\n", 1)[1].split("\n'@", 1)[0].replace(
            "__ACTION__", "")
        pins = {
            TEMPLATE_RELATIVE: sha256(TEMPLATE.encode()).hexdigest(),
            "D11_Interior_AAA_20260928/capture_candidate_native.py": sha256(b"runner").hexdigest(),
        }
        for relative, content in ((TEMPLATE_RELATIVE, TEMPLATE.encode()),
                                  ("D11_Interior_AAA_20260928/capture_candidate_native.py", b"runner")):
            path = self.workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        source_patch = patch.object(request, "SOURCE_SHA256", pins)
        digest_patch = patch.object(request, "READ_SCRIPT_SHA256",
                                    sha256(self.expected.encode()).hexdigest())
        helper_patch = patch.object(request, "NORMALIZED_HELPER_SHA256",
                                    sha256(TEMPLATE.encode()).hexdigest())
        count_patch = patch.object(request, "HELPER_RUN_ID_COUNT", 0)
        source_patch.start()
        digest_patch.start()
        helper_patch.start()
        count_patch.start()
        self.addCleanup(source_patch.stop)
        self.addCleanup(digest_patch.stop)
        self.addCleanup(helper_patch.stop)
        self.addCleanup(count_patch.stop)

    def transport(self, script: str | None = None, *, read_only: bool = True) -> Path:
        row = {
            "schema": 1, "status": "pass", "stage": "response_received",
            "mode": "Read", "readOnly": read_only,
            "helperSha256": sha256(self.helper.read_bytes()).hexdigest(),
            "script": script if script is not None else self.expected,
        }
        path = self.workspace / "pre_capture.json"
        path.write_text(json.dumps(row), encoding="utf-8")
        return path

    def test_pinned_source_helper_and_actual_transport_request(self) -> None:
        path = self.transport(self.expected.replace("\n", "\r\n"))
        row = request.audit(self.workspace, helper=self.helper, transport=path)
        self.assertTrue(row["sourcePinsVerified"])
        self.assertTrue(row["generatedHelperVerified"])
        self.assertTrue(row["transportRequestVerified"])
        self.assertFalse(row["loadedSceneVerified"])
        self.assertFalse(row["captureProcessAuthenticated"])
        self.assertFalse(row["pairProtocolEligible"])

    def test_read_only_marker_cannot_hide_mutating_request(self) -> None:
        path = self.transport(self.expected.replace(
            "return result", "truck.owner.Get<State>().Set(true)\nreturn result"))
        with self.assertRaisesRegex(request.PrecaptureRequestError, "Sent Read request"):
            request.audit(self.workspace, helper=self.helper, transport=path)

    def test_generated_helper_cannot_add_read_action(self) -> None:
        self.helper.write_text(TEMPLATE.replace(
            "$script=$script.Replace", "if($Mode -eq 'Read'){$action='Set(true)'}\n"
            "$script=$script.Replace"), encoding="utf-8")
        with self.assertRaisesRegex(request.PrecaptureRequestError, "Read-mode action"):
            request.audit(self.workspace, helper=self.helper)

    def test_other_generated_helper_tampering_rejected(self) -> None:
        self.helper.write_text(TEMPLATE.replace("if($Mode -eq 'Capture')",
                                               "if($Mode -like '*')"), encoding="utf-8")
        with self.assertRaisesRegex(request.PrecaptureRequestError, "reviewed full script"):
            request.audit(self.workspace, helper=self.helper)

    def test_source_drift_and_unverified_transport_fail_closed(self) -> None:
        path = self.transport()
        with self.assertRaisesRegex(request.PrecaptureRequestError, "requires its generated helper"):
            request.audit(self.workspace, transport=path)
        path.write_text(json.dumps({"schema": 1, "status": "pass", "stage": "response_received",
                                    "mode": "Read", "readOnly": False,
                                    "helperSha256": sha256(self.helper.read_bytes()).hexdigest(),
                                    "script": self.expected}), encoding="utf-8")
        with self.assertRaisesRegex(request.PrecaptureRequestError, "not a passing Read reply"):
            request.audit(self.workspace, helper=self.helper, transport=path)
        (self.workspace / "D11_Interior_AAA_20260928/capture_candidate_native.py").write_bytes(
            b"changed runner")
        with self.assertRaisesRegex(request.PrecaptureRequestError, "Generator source changed"):
            request.audit(self.workspace)


if __name__ == "__main__":
    unittest.main()
