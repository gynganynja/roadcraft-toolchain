"""Meaningful fail-closed parsing checks for proposed native API probe replies."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft.native_runtime_probe import (  # noqa: E402
    NativeRuntimeProbeError, parse_probe_reply,
)


class NativeRuntimeProbeTests(unittest.TestCase):
    def test_parses_each_partial_readback_without_pair_eligibility(self) -> None:
        replies = {
            "camera_up": "D11R_CAMERA_UP pos 1 2 3 forward 0 0 1 up 0 1 0",
            "weather_state": "D11R_WEATHER_STATE rainEnabled false rainPower 0.25",
            "sun_direction": "D11R_SUN_DIRECTION 0 0.8 -0.6",
            "daytime": "D11R_DAYTIME 0.5",
        }
        for kind, reply in replies.items():
            with self.subTest(kind=kind):
                result = parse_probe_reply(kind, reply)
                self.assertEqual(result["status"], "PARTIAL_RUNTIME_READBACK")
                self.assertFalse(result["pairProtocolEligible"])
                self.assertTrue(result["reported"])
        self.assertEqual(
            parse_probe_reply("camera_up", replies["camera_up"])["reported"]["camera"]["up"],
            [0.0, 1.0, 0.0],
        )
        self.assertEqual(
            parse_probe_reply("weather_state", replies["weather_state"])["reported"]["weatherState"],
            {"rainEnabled": False, "rainPower": 0.25},
        )

    def test_rejects_malformed_or_ambiguous_replies(self) -> None:
        bad = (
            ("camera_up", "D11R_CAMERA_UP_NO_CAMERA"),
            ("camera_up", "D11R_CAMERA_UP pos 1 2 3 forward 0 0 1 up 0 0 0"),
            ("weather_state", "D11R_WEATHER_STATE rainEnabled true rainPower 1.1"),
            ("sun_direction", "D11R_SUN_DIRECTION 0 0 0"),
            ("daytime", "D11R_DAYTIME NaN"),
            ("daytime", "D11R_DAYTIME 0.5\nD11R_DAYTIME 0.5"),
            ("sun_direction", "D11R_DAYTIME 0.5"),
        )
        for kind, reply in bad:
            with self.subTest(kind=kind, reply=reply):
                with self.assertRaises(NativeRuntimeProbeError):
                    parse_probe_reply(kind, reply)

    def test_rejects_unknown_probe_and_non_string_reply(self) -> None:
        with self.assertRaisesRegex(NativeRuntimeProbeError, "Unknown probe"):
            parse_probe_reply("exposure", "D11R_EXPOSURE 1")
        with self.assertRaisesRegex(NativeRuntimeProbeError, "not a string"):
            parse_probe_reply("daytime", None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
