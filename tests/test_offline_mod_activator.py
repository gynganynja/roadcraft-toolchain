"""Windows integration checks; all settings and writes use a temporary directory."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib


def transform(data):
    result = bytearray()
    key = bytes.fromhex("9d64aaec")
    index = count = marker = 0
    for value in data:
        if count == marker:
            count, marker = 0, value
            result.append(value)
        else:
            result.append(value ^ key[index])
            index = (index + 1) & 3
            count += 1
    return bytes(result)


def container(raw, codec=2):
    payload = raw if codec == 0 else zlib.compress(raw)
    if codec == 2:
        payload = transform(payload)
    return b"SSF1" + struct.pack("<QQ", len(payload), len(raw)) + hashlib.md5(payload).hexdigest().encode("ascii") + bytes([codec]) + payload


def decode(file):
    assert file[:4] == b"SSF1"
    packed, raw_size = struct.unpack_from("<QQ", file, 4)
    payload = file[53:]
    assert len(payload) == packed
    assert file[20:52] == hashlib.md5(payload).hexdigest().encode("ascii")
    codec = file[52]
    raw = payload if codec == 0 else zlib.decompress(transform(payload) if codec == 2 else payload)
    assert len(raw) == raw_size
    return raw


@unittest.skipUnless(os.name == "nt", "Windows .NET Framework application")
class OfflineModActivatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch_root = Path(os.environ.get("ROADCRAFT_TEST_TMP", tempfile.gettempdir())).resolve()
        cls.scratch = tempfile.TemporaryDirectory(prefix="roadcraft-offline-mod-tests-", dir=cls.scratch_root)
        cls.directory = Path(cls.scratch.name).resolve()
        assert cls.directory.parent == cls.scratch_root
        compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        if not compiler.is_file():
            compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework/v4.0.30319/csc.exe"
        if not compiler.is_file():
            raise unittest.SkipTest("Windows .NET Framework compiler unavailable")
        here = Path(__file__).resolve().parent
        source = here / "OfflineMods.cs"
        if not source.is_file():
            source = here.parent / "integrations/windows-offline-mods/OfflineMods.cs"
        cls.exe = cls.directory / "RoadCraftOfflineMods.exe"
        subprocess.run([str(compiler), "/nologo", "/target:winexe", "/optimize+", "/out:" + str(cls.exe), "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll", "/reference:System.Web.Extensions.dll", str(source)], check=True, capture_output=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        assert cls.directory.parent == cls.scratch_root and cls.directory.name.startswith("roadcraft-offline-mod-tests-")
        cls.scratch.cleanup()

    def run_app(self, *args):
        return subprocess.run([str(self.exe), *map(str, args)], capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)

    def test_transactions_and_independent_decode(self):
        raw = b'{\n   "UserSettings": {\n      "enabledMods": ["local:already_enabled", "pros:keep]\\\"me"],\n      "language": "english",\n      "number": 1.0,\n      "nested": {"enabledMods": [], "text": "comma, bracket]"},\n      "systemVersion": 47\n   }\n}'
        source = self.directory / "original.cfg"
        original = container(raw)
        source.write_bytes(original)
        output = self.directory / "transactions"
        run = self.run_app("--self-test", source, output)
        self.assertEqual(run.returncode, 0, (output / "test-result.txt").read_text())
        self.assertIn("17 checks passed", (output / "test-result.txt").read_text())
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual((output / "user_settings.cfg").read_bytes(), original)
        backups = list(output.glob("*.bak"))
        self.assertEqual(len(backups), 2)
        observed = []
        for backup in backups:
            current = json.loads(decode(backup.read_bytes()))
            observed.append(len(current["UserSettings"].pop("enabledMods")))
            expected = json.loads(raw)
            expected["UserSettings"].pop("enabledMods")
            self.assertEqual(current, expected)
        self.assertEqual(sorted(observed), [2, 3])

    def test_observed_retail_codec_fixture(self):
        # Exact payload observed in retail platform/config/config.cfg on 2026-10-01.
        payload = bytes.fromhex("7801cf4cbecd34fa9e6b93d91fe93318be3562dbadbfa13f29b8cd138d34216f75641deae5fe2fd97cc949fdc19d52fee024")
        expected = b'{\n   "CONFIG": {\n      "systemVersion": 397\n   }\n}'
        fixture = b"SSF1" + struct.pack("<QQ", len(payload), len(expected)) + hashlib.md5(payload).hexdigest().encode("ascii") + b"\x02" + payload
        source, output = self.directory / "retail.cfg", self.directory / "retail.json"
        source.write_bytes(fixture)
        self.assertEqual(self.run_app("--decode", source, output).returncode, 0)
        self.assertEqual(output.read_bytes(), expected)
        self.assertEqual(decode(fixture), expected)

    def test_decode_all_supported_codecs(self):
        raw = ('{"UserSettings":{"enabledMods":[],"unicode":"\u00e9\u96ea","data":"' + "abcdef0123456789" * 1000 + '"}}').encode("utf-8")
        for codec in (0, 1, 2):
            with self.subTest(codec=codec):
                source, output = self.directory / ("codec%d.cfg" % codec), self.directory / ("codec%d.json" % codec)
                source.write_bytes(container(raw, codec))
                self.assertEqual(self.run_app("--decode", source, output).returncode, 0)
                self.assertEqual(output.read_bytes(), raw)

    def test_corruption_refused_without_output(self):
        original = container(b'{"UserSettings":{"enabledMods":[]}}')
        cases = {}
        corrupt = bytearray(original); corrupt[-1] ^= 1; cases["md5"] = corrupt
        corrupt = bytearray(original); corrupt[4] ^= 1; cases["packed_length"] = corrupt
        corrupt = bytearray(original); corrupt[12] ^= 1; cases["raw_length"] = corrupt
        corrupt = bytearray(original); corrupt[52] = 3; cases["codec"] = corrupt
        corrupt = bytearray(container(b'{"UserSettings":{"enabledMods":[]}}', 1)); corrupt[-1] ^= 1
        corrupt[20:52] = hashlib.md5(corrupt[53:]).hexdigest().encode("ascii"); cases["adler"] = corrupt
        for name, data in cases.items():
            with self.subTest(name=name):
                source, output = self.directory / (name + ".cfg"), self.directory / (name + ".json")
                source.write_bytes(data)
                self.assertEqual(self.run_app("--decode", source, output).returncode, 1)
                self.assertFalse(output.exists())
                self.assertEqual(source.read_bytes(), data)

    def test_self_test_refuses_input_directory(self):
        directory = self.directory / "do-not-overwrite"
        directory.mkdir()
        source = directory / "user_settings.cfg"
        original = container(b'{"UserSettings":{"enabledMods":[]}}')
        source.write_bytes(original)
        self.assertEqual(self.run_app("--self-test", source, directory).returncode, 1)
        self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
