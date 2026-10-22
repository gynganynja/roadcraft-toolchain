"""Wwise 2019.2 bank reader and the no-Wwise retail sample-bank clone (roadcraft.wwise_bank, roadcraft.sound_clone).

Build-only, unbenched: these tests check bytes and IDs, not that the game plays the clone
(library/audio-assets.md, C:/RC_RE/research/sound_semantics.md §7).
"""

import os
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from roadcraft import sound_clone as sc
from roadcraft import wwise_bank as wb

GAME = Path(os.environ.get("ROADCRAFT_GAME_ROOT", r"C:\Program Files (x86)\Steam\steamapps\common\RoadCraft"))
SOUND_PAKS = sorted((GAME / "root/paks/client/default").glob("default_sound_*.pak"))
RETAIL = bool(SOUND_PAKS) and (GAME / "root/paks/client/resources.pak").is_file()
RPM = wb.fnv1_32("rtpc_vehicle_rpm")
BUS = 268529915                                  # the TK53 Krot actor-mixer's output bus (in init.bnk)


# --- a synthetic v135 bank, built with the layouts the reader walks ----------------------------------------------

def node_base(parent, bus=0, props=None):
    props = props or {}
    out = b"\x00\x00" + b"\x00" + struct.pack("<II", bus, parent) + b"\x00"
    out += bytes([len(props)]) + bytes(props) + b"".join(struct.pack("<I", v) for v in props.values())
    out += b"\x00"                               # ranged props
    out += b"\x00"                               # positioning
    out += b"\x00" + struct.pack("<I", 0)        # aux, reflections aux bus
    out += bytes(6)                              # advanced settings
    out += b"\x00\x00"                           # state props, state groups
    out += struct.pack("<H", 0)                  # RTPC curves
    return out


def obj(kind, oid, body):
    payload = struct.pack("<I", oid) + body
    return bytes([kind]) + struct.pack("<I", len(payload)) + payload


def sound(oid, parent, media, size, loop=False, stream=0):
    props = {sc.PROP_LOOP: 0} if loop else {}
    return obj(2, oid, struct.pack("<IBIIB", wb.CODEC_VORBIS, stream, media, size, 0) + node_base(parent, props=props))


def layer_cntr(oid, parent, children, layer_id, curves):
    body = node_base(parent) + struct.pack("<I", len(children)) + b"".join(struct.pack("<I", c) for c in children)
    body += struct.pack("<I", 1) + struct.pack("<I", layer_id) + struct.pack("<H", 0) + struct.pack("<I", RPM) + b"\x00"
    body += struct.pack("<I", len(curves))
    for child, points in curves:
        body += struct.pack("<II", child, len(points)) + b"".join(struct.pack("<ffI", x, y, 4) for x, y in points)
    return obj(9, oid, body + b"\x00")


def actor_mixer(oid, children):
    return obj(7, oid, node_base(0, bus=BUS) + struct.pack("<I", len(children))
               + b"".join(struct.pack("<I", c) for c in children))


def play(oid, target, bank):
    return obj(3, oid, struct.pack("<HIB", 0x0403, target, 0) + b"\x00\x00" + b"\x00" + struct.pack("<I", bank))


def event(oid, actions):
    return obj(4, oid, bytes([len(actions)]) + b"".join(struct.pack("<I", a) for a in actions))


def fake_wem(seconds, rate=48000):
    return sc.pcm_wem(sc.Pcm(1, rate, bytes(2 * int(rate * seconds))))


def synthetic_bank(name="syn_donor"):
    """Engine layer (idle/mid/high on rtpc_vehicle_rpm) plus a one-shot stop, all media in DATA."""
    bank_id = wb.fnv1_32(name)
    media = {11: fake_wem(0.5), 12: fake_wem(0.5), 13: fake_wem(0.5), 14: fake_wem(1.25)}
    objects = [
        actor_mixer(100, [200, 300]),
        sound(201, 200, 11, len(media[11]), loop=True),
        sound(202, 200, 12, len(media[12]), loop=True),
        sound(203, 200, 13, len(media[13]), loop=True),
        layer_cntr(200, 100, [201, 202, 203], 250, [
            (201, [(-800, 1), (800, 1), (980, 0)]),
            (203, [(1030, 0), (1200, 1), (1500, 1)]),
            (202, [(800, 0), (980, 1), (1030, 1), (1200, 0)])]),
        sound(300, 100, 14, len(media[14])),
        play(400, 200, bank_id), play(401, 300, bank_id),
        event(wb.fnv1_32(name + "_engine"), [400]), event(wb.fnv1_32(name + "_engine_stop"), [401]),
    ]
    didx, data = b"", b""
    for mid in sorted(media):
        data += bytes(-len(data) % 16)
        didx += struct.pack("<III", mid, len(data), len(media[mid]))
        data += media[mid]
    hirc = struct.pack("<I", len(objects)) + b"".join(objects)
    bkhd = struct.pack("<IIIII", 135, bank_id, wb.fnv1_32("sfx"), 16, 12991) + bytes(12)
    raw = b""
    for tag, payload in ((b"BKHD", bkhd), (b"DIDX", didx), (b"DATA", data), (b"HIRC", hirc)):
        raw += tag + struct.pack("<I", len(payload)) + payload
    events = {}
    for suffix, target, loop in (("engine", 200, "true"), ("engine_stop", 300, "false")):
        events[f"{name}_{suffix}"] = sc.parse_resource(
            f"__type: res_desc_sound_event\nbanks:\n- {sc.bank_tag(name)}\ndurationMax: 0.0\ndurationMin: 0.0\n"
            f"isLoop: {loop}\nmedia_bundles: []\nname: {name}_{suffix}\nstartAudioIDs:\n- {target}\nstopAudioIDs: []\n")
    bank_res = sc.parse_resource(f"__type: res_desc_sound_bank\nblob_platform_x64: ../desktop/{name}.bnk\n"
                                 f"isMasterBank: false\nname: {name}\nparents:\n- res://sounds/banks/init.sound_bank.resource\n")
    return sc.Donor(name, wb.read_bank(raw), bank_res, events)


def wav24(samples, rate=48000):
    pcm = b"".join(int(v).to_bytes(3, "little", signed=True) for v in samples)
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 3, 3, 24)
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", len(pcm)) + pcm
    return b"RIFF" + struct.pack("<I", len(body)) + body


class FnvTest(unittest.TestCase):
    def test_known_retail_hashes(self):
        # BKHD IDs and game syncs in the retail banks (sound_semantics.md §1.2, §7)
        self.assertEqual(wb.fnv1_32("vhc_vostok_tk53krot"), 3331780943)
        self.assertEqual(wb.fnv1_32("init"), 1355168291)
        self.assertEqual(wb.fnv1_32("rtpc_vehicle_rpm"), 3439180431)
        self.assertEqual(wb.fnv1_32("FUEL"), wb.fnv1_32("fuel"))


class PcmTest(unittest.TestCase):
    def test_pcm_wem_layout(self):
        wem = sc.pcm_wem(sc.Pcm(1, 48000, b"\x01\x00\xff\xff"))
        self.assertEqual(wem[:4], b"RIFF")
        self.assertEqual(struct.unpack_from("<I", wem, 4)[0], len(wem) - 8)
        self.assertEqual(wem[8:16], b"WAVEfmt ")
        self.assertEqual(struct.unpack_from("<IHHIIHHHHI", wem, 16),
                         (24, 0xFFFE, 1, 48000, 96000, 2, 16, 6, 0, 0x4101))
        self.assertEqual(wem[44:56], b"JUNK" + struct.pack("<I", 4) + bytes(4))
        self.assertEqual(wem[56:64], b"data" + struct.pack("<I", 4))
        self.assertEqual(wem[64:], b"\x01\x00\xff\xff")
        self.assertEqual(struct.unpack_from("<I", sc.pcm_wem(sc.Pcm(2, 44100, bytes(8))), 40)[0], 0x3102)
        self.assertAlmostEqual(sc.wem_seconds(fake_wem(1.5)), 1.5)

    def test_24_bit_rounds_to_16(self):
        pcm = sc.read_wav(wav24([0, 0x7FFFFF, -0x800000, 0x80, 0x7F, -0x81]))
        values = [v for (v,) in struct.iter_unpack("<h", pcm.samples)]
        self.assertEqual(values, [0, 32767, -32768, 1, 0, -1])
        self.assertEqual((pcm.channels, pcm.rate, pcm.source_bits), (1, 48000, 24))

    def test_extensible_and_float(self):
        fmt = struct.pack("<HHIIHHHHI", 0xFFFE, 1, 48000, 192000, 4, 32, 22, 32, 4) + b"\x03\x00" + bytes(14)
        body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", 8) \
            + struct.pack("<ff", 0.5, -1.0)
        pcm = sc.read_wav(b"RIFF" + struct.pack("<I", len(body)) + body)
        self.assertEqual([v for (v,) in struct.iter_unpack("<h", pcm.samples)], [16384, -32767])

    def test_resource_round_trip_crlf(self):
        text = "__type: res_desc_sound_event\r\nbanks:\r\n- res://x\r\nchildren: []\r\nname: e\r\n"
        self.assertEqual(sc.write_resource(sc.parse_resource(text)), text)


class SyntheticCloneTest(unittest.TestCase):
    def setUp(self):
        self.donor = synthetic_bank()
        self.idle = sc.read_wav(wav24([1000 * ((i % 40) - 20) for i in range(4800)]))

    def test_reader_walks_every_object(self):
        bank = self.donor.bank
        self.assertEqual(len(bank.objects), 10)
        self.assertEqual(bank.unparsed, [])
        layer = bank.by_id()[200]
        self.assertEqual([a["child"] for a in layer.info["layers"][0]["assoc"]], [201, 203, 202])
        self.assertEqual(layer.info["layers"][0]["crossfade"], RPM)

    def test_roles_from_rpm_ranges(self):
        roles = {r.role: r.sound for r in sc.donor_roles(self.donor)}
        self.assertEqual(roles, {"engine.idle": 201, "engine.mid": 202, "engine.high": 203, "engine_stop": 300})

    def test_round_trip(self):
        clone = sc.clone_bank(self.donor, "syn_clone", {"engine.idle": self.idle, "engine_stop": sc.silence()})
        raw = clone.files["sounds/desktop/syn_clone.bnk"]
        bank = wb.read_bank(raw)
        self.assertEqual(bank.bank_id, wb.fnv1_32("syn_clone"))
        objects = bank.by_id()
        self.assertIn(wb.fnv1_32("syn_clone_engine"), objects)
        self.assertIn(wb.fnv1_32("syn_clone_engine_stop"), objects)
        donor_ids = {o.id for o in self.donor.bank.objects} | {m.id for m in self.donor.bank.media}
        new_ids = {o.id for o in bank.objects} | {m.id for m in bank.media} | bank.defined_ids()
        self.assertFalse(new_ids & donor_ids)
        # same structure: every object keeps its type and size; sync IDs (RTPC) unchanged
        self.assertEqual([(o.type, o.size) for o in bank.objects], [(o.type, o.size) for o in self.donor.bank.objects])
        self.assertEqual([f.value for o in bank.objects for f in o.fields if f.kind == "sync"],
                         [f.value for o in self.donor.bank.objects for f in o.fields if f.kind == "sync"])
        # every reference resolves inside the clone (or is the external bus)
        for o in bank.objects:
            for f in o.fields:
                if f.kind == "ref" and f.value and not f.role.startswith("prop"):
                    self.assertTrue(f.value in objects or f.value == BUS, (o.id, f.role, f.value))
                if f.kind == "bank":
                    self.assertEqual(f.value, bank.bank_id)
        # PCM where assigned, donor bytes elsewhere; every Sound's media in DATA at its declared size
        media = {m.id: m for m in bank.media}
        clone_roles = {row["role"]: row for row in clone.report["roles"]}
        for o in bank.objects:
            if o.type == 2:
                self.assertEqual(o.info["stream"], wb.STREAM_DATA)
                self.assertEqual(media[o.info["media"]].size, o.info["memSize"])
                self.assertEqual(media[o.info["media"]].offset % 16, 0)
        idle = objects[clone_roles["engine.idle"]["newSound"]]
        self.assertEqual(idle.info["plugin"], wb.CODEC_PCM)
        self.assertEqual(bank.media_bytes(idle.info["media"]), sc.pcm_wem(self.idle))
        mid = objects[clone_roles["engine.mid"]["newSound"]]
        self.assertEqual(mid.info["plugin"], wb.CODEC_VORBIS)
        self.assertEqual(bank.media_bytes(mid.info["media"]), self.donor.bank.media_bytes(12))
        # resources
        engine = sc.parse_resource(clone.files["sounds/events/syn_clone_engine.sound_event.resource"].decode())
        self.assertEqual(engine["banks"], [sc.bank_tag("syn_clone")])
        self.assertEqual(engine["startAudioIDs"], [str(clone.report["events"][0]["startAudioIDs"][0])])
        self.assertIn(int(engine["startAudioIDs"][0]), objects)
        self.assertEqual(objects[int(engine["startAudioIDs"][0])].type, 9)
        stop = sc.parse_resource(clone.files["sounds/events/syn_clone_engine_stop.sound_event.resource"].decode())
        self.assertEqual((stop["durationMin"], stop["durationMax"]), ("0.05", "0.05"))
        bank_res = sc.parse_resource(clone.files["sounds/banks/syn_clone.sound_bank.resource"].decode())
        self.assertEqual(bank_res["blob_platform_x64"], "../desktop/syn_clone.bnk")

    def test_deterministic_and_name_checked(self):
        a = sc.clone_bank(self.donor, "syn_clone", {"engine.idle": self.idle})
        b = sc.clone_bank(self.donor, "syn_clone", {"engine.idle": self.idle})
        self.assertEqual(a.files, b.files)
        c = sc.clone_bank(self.donor, "syn_other", {"engine.idle": self.idle})
        self.assertFalse(wb.read_bank(c.files["sounds/desktop/syn_other.bnk"]).defined_ids()
                         & wb.read_bank(a.files["sounds/desktop/syn_clone.bnk"]).defined_ids())
        with self.assertRaises(sc.SoundCloneError):
            sc.clone_bank(self.donor, "Bad Name", {})
        with self.assertRaises(sc.SoundCloneError):
            sc.clone_bank(self.donor, "syn_clone", {"engine.nope": self.idle})

    def test_taken_ids_avoided(self):
        first = sc.clone_bank(self.donor, "syn_clone", {})
        taken = wb.read_bank(first.files["sounds/desktop/syn_clone.bnk"]).defined_ids() - {
            wb.fnv1_32("syn_clone_engine"), wb.fnv1_32("syn_clone_engine_stop")}
        again = sc.clone_bank(self.donor, "syn_clone", {}, taken=taken)
        self.assertFalse(wb.read_bank(again.files["sounds/desktop/syn_clone.bnk"]).defined_ids() & taken)


@unittest.skipUnless(RETAIL, f"RoadCraft retail sound paks not installed at {GAME}")
class RetailBankTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.banks = {}
        for pak in SOUND_PAKS:
            with zipfile.ZipFile(pak) as archive:
                for member in archive.namelist():
                    if member.endswith(".bnk"):
                        cls.banks[Path(member).stem] = archive.read(member)
        cls.donor = sc.load_donor(GAME, "vhc_vostok_tk53krot")

    def test_reader_consumes_every_supported_object_exactly(self):
        self.assertEqual(len(self.banks), 85)
        parsed = 0
        for name, raw in self.banks.items():
            bank = wb.read_bank(raw, strict=False)
            for obj in bank.unparsed:                     # only object types the reader does not claim
                self.assertNotIn(obj.type, wb.HIRC_TYPES, (name, obj.type, obj.id))
            parsed += len(bank.objects)
        self.assertGreater(parsed, 11000)

    def test_krot_map(self):
        roles = {r.role: r for r in sc.donor_roles(self.donor, sc.known_names(GAME))}
        self.assertEqual(roles["engine.idle"].sound, 31872740)
        self.assertEqual(roles["engine.mid"].sound, 598529449)
        self.assertEqual(roles["engine.high"].sound, 473787773)
        self.assertEqual(roles["engine.overlay"].sound, 14615488)
        self.assertEqual(roles["engine_start.no_fuel"].sound, 197594069)
        self.assertEqual(roles["engine_stop"].sound, 937873622)
        self.assertTrue(all(roles[k].loop for k in ("engine.idle", "engine.mid", "engine.high", "engine.overlay")))
        self.assertAlmostEqual(roles["engine_start.filled.1"].delay, 0.7, places=5)

    def test_durations_match_retail(self):
        bank = self.donor.bank
        seconds = {}
        for o in bank.objects:
            if o.type == 2:
                wem = self.donor.streamed.get(o.info["media"]) or bank.media_bytes(o.info["media"])
                seconds[o.id] = sc.wem_seconds(wem)
        spans = sc.event_durations(bank, seconds)
        for name, fields in self.donor.events.items():
            if fields["isLoop"] == "true":
                continue
            if wb.fnv1_32(name) not in spans:                # Stop-only event (mech_dig_stop): retail 0/0
                self.assertEqual((fields["durationMin"], fields["durationMax"]), ("0.0", "0.0"), name)
                continue
            low, high = spans[wb.fnv1_32(name)]
            self.assertAlmostEqual(low, float(fields["durationMin"]), places=4, msg=name)
            self.assertAlmostEqual(high, float(fields["durationMax"]), places=4, msg=name)

    def test_pcm_header_matches_retail_pcm_media(self):
        bank = wb.read_bank(self.banks["tech"], strict=False)
        pcm = [o for o in bank.objects if o.type == 2 and o.info["plugin"] == wb.CODEC_PCM]
        self.assertEqual(len(pcm), 1)
        retail = bank.media_bytes(pcm[0].info["media"])
        ours = sc.pcm_wem(sc.Pcm(1, 48000, bytes(16)))
        self.assertEqual(ours[8:56], retail[8:56])          # WAVE, fmt (all 24 bytes), JUNK
        self.assertEqual(ours[56:60], retail[56:60])        # data tag at offset 56, payload at 64

    def test_clone_ids_unique_against_all_retail_banks(self):
        retail = sc.retail_ids(GAME)
        clips = {"engine": sc.silence(), "engine_start": sc.silence(), "engine_stop": sc.silence()}
        clone = sc.clone_bank(self.donor, "rc_test_clone", clips, retail, sc.known_names(GAME))
        bank = wb.read_bank(clone.files["sounds/desktop/rc_test_clone.bnk"])
        new_ids = {o.id for o in bank.objects} | {m.id for m in bank.media} | bank.defined_ids() | {bank.bank_id}
        self.assertFalse(new_ids & retail)
        self.assertEqual(len(bank.objects), len(self.donor.bank.objects))
        self.assertEqual(sum(1 for o in bank.objects if o.type == 2 and o.info["plugin"] == wb.CODEC_PCM), 8)
        self.assertTrue(all(o.info["stream"] == wb.STREAM_DATA for o in bank.objects if o.type == 2))
        self.assertEqual(len(clone.files), 2 + len(self.donor.events))
        with tempfile.TemporaryDirectory() as tmp:
            written = sc.write_clone(clone, Path(tmp))
            self.assertTrue(all(Path(p).is_file() for p in written))
            self.assertTrue((Path(tmp) / "sounds/events/rc_test_clone_engine.sound_event.resource").is_file())


if __name__ == "__main__":
    unittest.main()
