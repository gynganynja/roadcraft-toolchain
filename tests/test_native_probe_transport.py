"""Fail-closed offline tests for the five scratch-only SSL transport modes."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft.native_probe_transport import (  # noqa: E402
    ProbeInputs, ProbeTransportError, PROBE_SHA256, main, pinned_inputs,
    verify_probe_plan, verify_probe_receipt, verify_scratch_output,
)


ROOT = Path(__file__).resolve().parents[1]
SUCCESS = {
    "weather_state": "D11R_WEATHER_STATE rainEnabled false rainPower 0.25",
    "camera_up": "D11R_CAMERA_UP pos 1 2 3 forward 0 0 1 up 0 1 0",
    "sun_direction": "D11R_SUN_DIRECTION 0 0.8 -0.6",
    "daytime": "D11R_DAYTIME 0.5",
    "level_name": "D11R_LEVEL_NAME d11t_maroon_validation",
}


def local_native_fixture_available() -> bool:
    if not shutil.which("pwsh") or not (ROOT / "local" / "machine.json").exists():
        return False
    try:
        inputs = pinned_inputs("weather_state", "maroon")
    except (OSError, ValueError, KeyError):
        return False
    return all(path.is_file() for path in (
        inputs.fragment, inputs.scene, inputs.editor, inputs.json_dll,
        inputs.console_dll, inputs.helper, inputs.machine_config,
    ))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture(root: Path, kind: str = "weather_state") -> tuple[ProbeInputs, dict]:
    script = (ROOT / "operations" / "probes" / f"d11_{kind}.ssl").read_bytes()
    files = {
        "fragment": root / f"d11_{kind}.ssl",
        "scene": root / "scene.scn",
        "editor": root / "Roadcraft ModEditor.exe",
        "json_dll": root / "Saber.Json.dll",
        "console_dll": root / "Saber.ConsoleTre.dll",
        "helper": root / "native_runtime_probe.ps1",
        "machine_config": root / "machine.json",
    }
    for name, data in (
        ("fragment", script), ("scene", b"scratch scene source"),
        ("editor", b"scratch editor executable"),
        ("json_dll", b"scratch JSON assembly"),
        ("console_dll", b"scratch ConsoleTre assembly"),
        ("helper", b"scratch helper source"),
        ("machine_config", b'{"sdkRoot":"scratch"}'),
    ):
        files[name].write_bytes(data)
    inputs = ProbeInputs(
        kind=kind, variant="maroon", **files,
        fragment_sha256=sha(script), scene_sha256=sha(files["scene"].read_bytes()),
        editor_sha256=sha(files["editor"].read_bytes()),
        json_dll_sha256=sha(files["json_dll"].read_bytes()),
        console_dll_sha256=sha(files["console_dll"].read_bytes()),
        helper_sha256=sha(files["helper"].read_bytes()),
    )
    now = datetime.now(timezone.utc)
    raw = SUCCESS[kind].encode("utf-8") + b"\0"
    record = {
        "schema": 1, "status": "TRANSPORT_RESPONSE_UNVALIDATED", "stage": "response_received",
        "probeKind": kind, "variant": "maroon", "readOnly": True,
        "pairProtocolEligible": False, "loadedSceneVerified": False, "transportSent": True,
        "fragmentPath": str(inputs.fragment), "fragmentSha256": inputs.fragment_sha256,
        "sceneSourcePath": str(inputs.scene), "sceneSourceSha256": inputs.scene_sha256,
        "editorPath": str(inputs.editor), "editorSha256": inputs.editor_sha256,
        "jsonDllPath": str(inputs.json_dll), "jsonDllSha256": inputs.json_dll_sha256,
        "consoleDllPath": str(inputs.console_dll), "consoleDllSha256": inputs.console_dll_sha256,
        "helperPath": str(inputs.helper), "helperSha256": sha(inputs.helper.read_bytes()),
        "machineConfigPath": str(inputs.machine_config),
        "machineConfigSha256": sha(inputs.machine_config.read_bytes()),
        "requestScript": script.decode("utf-8"), "requestScriptSha256": inputs.fragment_sha256,
        "engineProcessId": 1234, "engineStartUtc": (now - timedelta(minutes=5)).isoformat(),
        "requestPreparedUtc": now.isoformat(),
        "requestSendStartedUtc": (now + timedelta(milliseconds=1)).isoformat(),
        "requestSentUtc": (now + timedelta(milliseconds=2)).isoformat(),
        "responseReceivedUtc": (now + timedelta(milliseconds=3)).isoformat(),
        "requestId": "{12ABCDEF-ABCD-4abc-8ABC-ABCDEF123456}", "workspace": "scratch",
        "responseBase64": base64.b64encode(raw).decode("ascii"),
        "responseBytes": len(raw), "responseSha256": sha(raw),
        "response": SUCCESS[kind],
    }
    return inputs, record


class NativeProbeTransportTests(unittest.TestCase):
    def test_synthetic_transport_covers_all_five_readbacks_without_pair_eligibility(self) -> None:
        with TemporaryDirectory() as directory:
            for kind in PROBE_SHA256:
                with self.subTest(kind=kind):
                    subdir = Path(directory) / kind
                    subdir.mkdir()
                    inputs, record = fixture(subdir, kind)
                    result = verify_probe_receipt(record, inputs)
                    self.assertEqual(result["status"],
                                     "LEVEL_NAME_RESPONSE_CONSISTENCY_VERIFIED"
                                     if kind == "level_name" else
                                     "PARTIAL_RESPONSE_CONSISTENCY_VERIFIED")
                    self.assertFalse(result["pairProtocolEligible"])
                    self.assertFalse(result["loadedSceneVerified"])
                    self.assertTrue(result["reported"])
                    if kind == "level_name":
                        self.assertTrue(result["levelNameMatchesPinnedSourceStem"])

    def test_level_name_mismatch_is_diagnostic_only(self) -> None:
        with TemporaryDirectory() as directory:
            inputs, record = fixture(Path(directory), "level_name")
            raw = b"D11R_LEVEL_NAME RoadBuilder\0"
            record.update(responseBase64=base64.b64encode(raw).decode("ascii"),
                          responseBytes=len(raw), responseSha256=sha(raw),
                          response=raw[:-1].decode("ascii"))
            result = verify_probe_receipt(record, inputs)
            self.assertEqual(result["status"], "LEVEL_NAME_RESPONSE_CONSISTENCY_VERIFIED")
            self.assertFalse(result["levelNameMatchesPinnedSourceStem"])
            self.assertFalse(result["loadedSceneVerified"])
            self.assertFalse(result["pairProtocolEligible"])

    def test_rejects_tampered_inputs_and_response_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            inputs, record = fixture(Path(directory))
            cases = (
                ("arbitrary script", {"requestScript": 'SaveScreenshot("anything")'}),
                ("wrong helper digest", {"helperSha256": "0" * 64}),
                ("wrong ConsoleTre digest", {"consoleDllSha256": "0" * 64}),
                ("scene falsely verified", {"loadedSceneVerified": True}),
                ("claimed pair", {"pairProtocolEligible": True}),
                ("no send", {"transportSent": False}),
                ("wrong PID", {"engineProcessId": 0}),
                ("missing workspace", {"workspace": ""}),
                ("bad request ID", {"requestId": "not-a-guid"}),
                ("response interval exceeds bound", {"responseReceivedUtc": (
                    datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}),
                ("malformed base64", {"responseBase64": "!"}),
                ("wrong raw hash", {"responseSha256": "0" * 64}),
                ("wrong decoded text", {"response": "D11R_WEATHER_STATE rainEnabled true rainPower 0"}),
                ("failed transport", {"status": "FAILED"}),
            )
            for label, changes in cases:
                with self.subTest(label=label):
                    with self.assertRaises(ProbeTransportError):
                        verify_probe_receipt({**record, **changes}, inputs)
            inputs.fragment.write_text("return 'tampered'", encoding="utf-8")
            with self.assertRaisesRegex(ProbeTransportError, "fragment SHA-256"):
                verify_probe_receipt(record, inputs)

    def test_rejects_oversize_raw_reply_even_if_its_hash_is_consistent(self) -> None:
        with TemporaryDirectory() as directory:
            inputs, record = fixture(Path(directory))
            raw = b"x" * 65_536 + b"\0"
            record.update(responseBase64=base64.b64encode(raw).decode("ascii"),
                          responseBytes=len(raw), responseSha256=sha(raw),
                          response=raw[:-1].decode("ascii"))
            with self.assertRaisesRegex(ProbeTransportError, "byte bound"):
                verify_probe_receipt(record, inputs)

    def test_helper_drift_fails_before_preflight_or_execution_launch(self) -> None:
        with TemporaryDirectory() as directory:
            inputs, record = fixture(Path(directory))
            inputs.helper.write_bytes(b"modified scratch helper source")
            record["helperSha256"] = sha(inputs.helper.read_bytes())
            with self.assertRaisesRegex(ProbeTransportError, "PowerShell helper SHA-256"):
                verify_probe_plan({**record, "status": "PREFLIGHT_ONLY",
                                   "transportSent": False}, inputs)
            for extra in ([], ["--execute", "--engine-pid", "1234",
                               "--output", str(Path(directory) / "new.json")]):
                with self.subTest(extra=extra), \
                     mock.patch("roadcraft.native_probe_transport.pinned_inputs",
                                return_value=inputs), \
                     mock.patch("roadcraft.native_probe_transport.shutil.which",
                                return_value="pwsh"), \
                     mock.patch("roadcraft.native_probe_transport.subprocess.run") as launch, \
                     self.assertRaisesRegex(ProbeTransportError,
                                            "PowerShell helper SHA-256"):
                    main(["--kind", "weather_state", "--variant", "maroon", *extra])
                launch.assert_not_called()

    def test_rejects_native_compile_error_even_when_transport_is_intact(self) -> None:
        with TemporaryDirectory() as directory:
            inputs, record = fixture(Path(directory))
            raw = b"SSL compile error: GetWeatherState unavailable\0"
            record.update(responseBase64=base64.b64encode(raw).decode("ascii"),
                          responseBytes=len(raw), responseSha256=sha(raw),
                          response=raw[:-1].decode("utf-8"))
            with self.assertRaisesRegex(ProbeTransportError, "Native probe result rejected"):
                verify_probe_receipt(record, inputs)

    def test_verifier_hashes_the_same_fragment_bytes_it_compares_to_request(self) -> None:
        with TemporaryDirectory() as directory:
            inputs, record = fixture(Path(directory))
            original_read = Path.read_bytes
            reads = 0

            def read_once(path: Path) -> bytes:
                nonlocal reads
                if path == inputs.fragment:
                    reads += 1
                    if reads > 1:
                        return b"different bytes on a second read"
                return original_read(path)

            with mock.patch.object(Path, "read_bytes", read_once):
                verify_probe_receipt(record, inputs)
            self.assertEqual(reads, 1)

    def test_execution_receipt_path_is_bounded_to_plain_local_scratch(self) -> None:
        with TemporaryDirectory() as directory:
            toolchain = Path(directory) / "toolchain"
            scratch = toolchain / "local" / "native-probes"
            scratch.mkdir(parents=True)
            verify_scratch_output(scratch / "probe-1.json", toolchain)
            for bad in (
                toolchain / "operations" / "probe.json",
                toolchain / "local" / "probe.json",
                scratch / ".." / "escape.json",
                scratch / "bad name.json",
            ):
                with self.subTest(path=bad), self.assertRaises(ProbeTransportError):
                    verify_scratch_output(bad, toolchain)
            existing = scratch / "existing.json"
            existing.write_text("{}", encoding="utf-8")
            with self.assertRaises(ProbeTransportError):
                verify_scratch_output(existing, toolchain)
            if hasattr(Path, "symlink_to"):
                second = Path(directory) / "toolchain2"
                (second / "local").mkdir(parents=True)
                link = second / "local" / "native-probes"
                try:
                    link.symlink_to(scratch, target_is_directory=True)
                except (OSError, NotImplementedError):
                    pass
                else:
                    with self.assertRaises(ProbeTransportError):
                        verify_scratch_output(link / "probe.json", second)

    @unittest.skipUnless(local_native_fixture_available(),
                         "Local RoadCraft SDK/editor fixture unavailable")
    def test_real_helper_offline_preflight_is_pinned_and_does_not_send(self) -> None:
        helper = ROOT / "operations" / "probes" / "native_runtime_probe.ps1"
        for kind, variant in (
            ("weather_state", "maroon"), ("camera_up", "nearnew"),
            ("sun_direction", "worn"), ("daytime", "maroon"),
            ("level_name", "nearnew"),
        ):
            with self.subTest(kind=kind):
                result = subprocess.run(
                    [shutil.which("pwsh"), "-NoProfile", "-NonInteractive", "-File",
                     str(helper), "-Kind", kind, "-Variant", variant],
                    capture_output=True, text=True, timeout=30, check=True,
                )
                plan = json.loads(result.stdout)
                self.assertEqual(plan["status"], "PREFLIGHT_ONLY")
                self.assertFalse(plan["transportSent"])
                self.assertEqual(
                    verify_probe_plan(plan, pinned_inputs(kind, variant))["status"],
                    "PREFLIGHT_VERIFIED",
                )
        rejected = subprocess.run(
            [shutil.which("pwsh"), "-NoProfile", "-NonInteractive", "-File",
             str(helper), "-Kind", "screenshot", "-Variant", "maroon"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertNotEqual(rejected.returncode, 0)


if __name__ == "__main__":
    unittest.main()
