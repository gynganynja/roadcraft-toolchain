"""Cross-project onboarding without promoting imported packages."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from roadcraft import core, onboard  # noqa: E402
from roadcraft.cli import main  # noqa: E402


class OnboardTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="roadcraft-onboard-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def test_existing_third_party_package_stays_candidate(self) -> None:
        package = self.root / "someone-elses-mod.pak"
        package.write_bytes(b"third-party package")
        registry = onboard.draft_registry("Trail Truck", package, "original")
        self.assertEqual(registry["accepted"], {})
        self.assertEqual(registry["candidates"]["original"]["package"]["sha256"],
                         core.sha256_file(package))
        output = self.root / "project.json"
        self.assertEqual(main(["onboard", "--project", "Trail Truck", "--package",
                               str(package), "--candidate-name", "original", "--output",
                               str(output), "--json"]), 0)
        self.assertEqual(core.read_registry(output)["accepted"], {})
        self.assertEqual(main(["verify", "--project", "--registry", str(output),
                               "--json"]), 0)
        # A foreign registry must not import this checkout's D11 machine state.
        from roadcraft.cli import execute, make_parser
        result, passed = execute(make_parser().parse_args(
            ["status", "--registry", str(output), "--json"]))
        self.assertTrue(passed)
        self.assertFalse(result["configFound"])
        self.assertIsNone(result["installed"])
        self.assertEqual(result["transactionReceipts"], [])
        self.assertEqual(main(["onboard", "--project", "Other", "--output",
                               str(output), "--json"]), 2)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["project"],
                         "Trail Truck")

    def test_new_mod_has_no_invented_accepted_package(self) -> None:
        registry = onboard.draft_registry("My New Mod")
        self.assertEqual(registry["accepted"], {})
        self.assertEqual(registry["candidates"], {})

    def test_missing_or_changed_package_and_invalid_names_fail(self) -> None:
        with self.assertRaises(core.RoadcraftError):
            onboard.draft_registry("Third Party", self.root / "missing.pak")
        with self.assertRaises(core.RoadcraftError):
            onboard.draft_registry("\n")
        with self.assertRaises(core.RoadcraftError):
            onboard.draft_registry("Mod", candidate_name="bad/name")
