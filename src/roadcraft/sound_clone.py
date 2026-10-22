"""Clone a retail sample-based sound bank under a new name, with your own WAVs as PCM media, without Wwise.

**Build-only and unbenched**: a hand-patched clone of a retail sample bank, untested in game
(library/audio-assets.md, "Cloning a retail sample bank"; evidence C:/RC_RE/research/sound_semantics.md §7).

The clone keeps the donor's whole structure (layer crossfades on ``rtpc_vehicle_rpm``, pitch curves, switch on
``fuel``, attenuation, bus, loop flags) and changes only what must differ for it to load beside the retail bank:

* bank ID = FNV-1 hash of the new name; event IDs = hashes of the new event names (donor prefix replaced);
* every other object, layer and media ID re-derived deterministically from the new name, checked unique
  against all retail banks;
* media: assigned roles get PCM16 ``.wem`` (the layout of retail ``tech.bnk``'s PCM media); the rest keep the
  donor's Vorbis bytes.  Every media goes into the bank's DATA chunk (no streaming, no media bundle).

    roadcraft sound clone-bank --donor vhc_vostok_tk53krot --name goli_d11            # list the roles
    roadcraft sound clone-bank --donor vhc_vostok_tk53krot --name goli_d11 \\
        --clip engine.idle=d11_idle_loop.wav --clip engine.mid=d11_high_loop.wav ... --out <mods_source>

The output is ``<out>/sounds/{banks,desktop,events}/...``, laid out like a mod's ``mods_source/sounds``.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import statistics
import struct
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import project_context, retail
from . import wwise_bank as wb

SILENCE = "silence"
PROP_LOOP = 0x3A                 # AkPropID Loop (0 = infinite), on the donor's looping Sounds
PROP_INITIAL_DELAY = 0x3B        # AkPropID InitialDelay (R: 0.7 s on the TK53 Krot start, = durationMax gap)
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
LINK_BROWSER = Path("root/mods_source/wwise/link_browser.json")


class SoundCloneError(ValueError):
    """The donor, a clip or the requested name cannot be cloned."""


# --- sound resources (the flat YAML retail writes) ----------------------------------------------------------

def parse_resource(text: str) -> dict[str, Any]:
    """Ordered ``key: value`` / ``key:`` + ``- item`` lines of a sounds/*.resource; values stay raw strings."""
    data: dict[str, Any] = {}
    key = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith("- ") and key is not None:
            data[key].append(line[2:])
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        data[key] = [] if value in ("", "[]") else value
    return data


def write_resource(data: dict[str, Any], newline: str = "\r\n") -> str:
    """Retail sounds/*.resource files are CRLF (R); keep that."""
    lines = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}: []" if not value else f"{key}:")
            lines.extend(f"- {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    return newline.join(lines) + newline


def bank_tag(name: str) -> str:
    return f"res://sounds/banks/{name}.sound_bank.resource"


# --- WAV in, PCM16 .wem out ----------------------------------------------------------------------------------

@dataclass
class Pcm:
    channels: int
    rate: int
    samples: bytes               # interleaved little-endian int16
    source_bits: int = 16

    @property
    def frames(self) -> int:
        return len(self.samples) // (2 * self.channels)

    @property
    def seconds(self) -> float:
        return self.frames / self.rate


def read_wav(data: bytes) -> Pcm:
    """PCM (8/16/24/32-bit int, or 32-bit float) WAV, plain or WAVE_FORMAT_EXTENSIBLE, mono or stereo, to int16.
    24/32-bit are rounded to 16 bits without dither; the sample rate is kept (Wwise resamples at runtime)."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise SoundCloneError("not a RIFF/WAVE file")
    fmt = payload = None
    pos = 12
    while pos + 8 <= len(data):
        tag, size = data[pos:pos + 4], struct.unpack_from("<I", data, pos + 4)[0]
        if tag == b"fmt ":
            fmt = data[pos + 8:pos + 8 + size]
        elif tag == b"data":
            payload = data[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)
    if fmt is None or payload is None:
        raise SoundCloneError("WAV has no fmt or data chunk")
    tag, channels, rate, _, align, bits = struct.unpack_from("<HHIIHH", fmt)
    if tag == 0xFFFE and len(fmt) >= 26:
        tag = struct.unpack_from("<H", fmt, 24)[0]     # SubFormat GUID's first two bytes
    if channels not in (1, 2):
        raise SoundCloneError(f"{channels} channels; use mono or stereo")
    width = bits // 8
    count = len(payload) // width
    out = bytearray(count * 2)
    if tag == 3 and bits == 32:
        for i, (value,) in enumerate(struct.iter_unpack("<f", payload[:count * 4])):
            struct.pack_into("<h", out, i * 2, max(-32768, min(32767, round(value * 32767))))
    elif tag == 1 and bits == 16:
        out[:] = payload[:count * 2]
    elif tag == 1 and bits in (8, 24, 32):
        shift = bits - 16
        for i in range(count):
            raw = payload[i * width:(i + 1) * width]
            if bits == 8:
                value = (raw[0] - 128) << 8
            else:
                value = int.from_bytes(raw, "little", signed=True)
                value = (value + (1 << (shift - 1))) >> shift
            struct.pack_into("<h", out, i * 2, max(-32768, min(32767, value)))
    else:
        raise SoundCloneError(f"unsupported WAV encoding (format {tag}, {bits}-bit)")
    usable = len(out) - len(out) % (2 * channels)
    return Pcm(channels, rate, bytes(out[:usable]), bits)


def silence(rate: int = 48000, seconds: float = 0.05) -> Pcm:
    return Pcm(1, rate, bytes(2 * int(rate * seconds)))


CHANNEL_MASK = {1: 0x4, 2: 0x3}  # SPEAKER_FRONT_CENTER; FRONT_LEFT | FRONT_RIGHT


def pcm_wem(pcm: Pcm) -> bytes:
    """A Wwise 2019.2 PCM ``.wem``, laid out like retail ``tech.bnk`` media 1006287809 (R):
    RIFF/WAVE, ``fmt `` 24 bytes (0xFFFE, cbSize 6, AkChannelConfig = channels | 1<<8 | mask<<12),
    ``JUNK`` 4 zero bytes, then ``data`` at offset 64."""
    block = 2 * pcm.channels
    config = pcm.channels | (1 << 8) | (CHANNEL_MASK[pcm.channels] << 12)
    fmt = struct.pack("<HHIIHHHHI", 0xFFFE, pcm.channels, pcm.rate, pcm.rate * block, block, 16, 6, 0, config)
    body = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"JUNK" + struct.pack("<I", 4) + bytes(4)
            + b"data" + struct.pack("<I", len(pcm.samples)) + pcm.samples)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def wem_seconds(wem: bytes) -> float | None:
    """Duration of a PCM or Vorbis ``.wem`` (Vorbis: the sample count Wwise stores at fmt+0x18)."""
    pos = wem.find(b"fmt ")
    if pos < 0:
        return None
    tag, channels, rate = struct.unpack_from("<HHI", wem, pos + 8)
    if not rate:
        return None
    if tag == 0xFFFF:
        return struct.unpack_from("<I", wem, pos + 8 + 0x18)[0] / rate
    data = wem.find(b"data")
    if tag == 0xFFFE and data > 0:
        return struct.unpack_from("<I", wem, data + 4)[0] / (2 * channels * rate)
    return None


def loop_seam(pcm: Pcm) -> dict[str, float]:
    """End-to-start step against the clip's ordinary sample steps (first channel): a crude seam check."""
    values = [v for (v,) in struct.iter_unpack("<h", pcm.samples)][::pcm.channels]
    if len(values) < 3:
        return {"seamStep": 0.0, "medianStep": 0.0, "ratio": 0.0}
    steps = [abs(b - a) for a, b in zip(values, values[1:])]
    median = statistics.median(steps) or 1.0
    seam = abs(values[0] - values[-1])
    return {"seamStep": float(seam), "medianStep": float(median), "ratio": round(seam / median, 2)}


# --- donor -----------------------------------------------------------------------------------------------------

@dataclass
class Donor:
    name: str
    bank: wb.Bank
    bank_resource: dict[str, Any]
    events: dict[str, dict[str, Any]]                  # event name -> resource fields
    streamed: dict[int, bytes] = field(default_factory=dict)   # media id -> whole .wem from media bundles


def _members(game: Path, names: Iterable[str]) -> dict[str, bytes]:
    wanted: dict[Path, list[str]] = {}
    for name in names:
        hits = retail.find_members(game, name)
        for member, pak in hits:
            wanted.setdefault(pak, []).append(member)
    out = {}
    for pak, members in wanted.items():
        with zipfile.ZipFile(pak) as archive:
            for member in members:
                out[member] = archive.read(member)
    return out


def read_media_bundle(zip_bytes: bytes) -> dict[int, bytes]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        return {int(Path(n).stem): archive.read(n) for n in archive.namelist() if n.endswith(".wem")}


def load_donor(game: Path, donor: str) -> Donor:
    try:
        bnk = retail.read_member(game, f"sounds/desktop/{donor}.bnk")
        bank_res = parse_resource(retail.read_member(game, f"sounds/banks/{donor}.sound_bank.resource").decode())
    except retail.RetailDataError as exc:
        raise SoundCloneError(f"no retail bank named {donor}") from exc
    tag = bank_tag(donor)
    events = {}
    for member, data in _members(game, ["sounds/events/*.sound_event.resource"]).items():
        fields = parse_resource(data.decode("utf-8"))
        if tag in fields.get("banks", []):
            events[fields["name"]] = fields
    streamed: dict[int, bytes] = {}
    bundles = sorted({b for e in events.values() for b in e.get("media_bundles", [])})
    for bundle in bundles:
        res = parse_resource(retail.read_member(game, bundle.replace("res://", "")).decode())
        blob = "sounds/" + res["blob_platform_x64"].replace("../", "")
        streamed.update(read_media_bundle(retail.read_member(game, blob)))
    try:
        bank = wb.read_bank(bnk)
    except wb.BankFormatError as exc:
        raise SoundCloneError(f"{donor}: {exc}. clone-bank takes sample-based banks only (not REV/FX/music "
                              f"banks; sound_semantics.md §2.1 lists the 23 sample-based vhc_* banks)") from exc
    return Donor(donor, bank, bank_res, events, streamed)


def retail_ids(game: Path) -> set[int]:
    """Every object, layer, media, bank and event ID in the retail banks (what a clone must not reuse)."""
    ids: set[int] = set()
    for member, data in _members(game, ["sounds/desktop/*.bnk"]).items():
        bank = wb.read_bank(data, strict=False)
        ids.add(bank.bank_id)
        ids.update(m.id for m in bank.media)
        ids.update(o.id for o in bank.objects + bank.unparsed)
        ids.update(bank.defined_ids())
    return ids


def known_names(game: Path | None) -> dict[int, str]:
    """ShortID -> name for game syncs listed in the SDK's link_browser.json."""
    names: dict[int, str] = {}
    path = Path(game) / LINK_BROWSER if game else None
    if path and path.is_file():
        doc = json.loads(path.read_text(encoding="utf-8"))
        for section in ("parameters", "switch_groups", "state_groups"):
            for key in doc.get(section) or {}:
                names[wb.fnv1_32(key)] = key
        for section in ("switches", "states"):
            for group in (doc.get(section) or {}).values():
                for key in group or {}:
                    names[wb.fnv1_32(key)] = key
    for key in ("rtpc_vehicle_rpm", "fuel", "filled", "no_fuel"):
        names.setdefault(wb.fnv1_32(key), key)
    return names


# --- roles -----------------------------------------------------------------------------------------------------

def _curve_value(points: list[tuple[float, float, int]], x: float) -> float:
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0, _), (x1, y1, _) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def rpm_range(points: list[tuple[float, float, int]], top: float = 1500.0) -> dict[str, list[float]] | None:
    """Where a crossfade curve is audible (>0) and full (>=0.999) on the positive side, at 1-unit steps."""
    if not points:
        return None
    audible = [x for x in range(0, int(top) + 1) if _curve_value(points, x) > 1e-3]
    full = [x for x in range(0, int(top) + 1) if _curve_value(points, x) >= 0.999]
    if not audible:
        return None
    return {"audible": [audible[0], audible[-1]], "full": [full[0], full[-1]] if full else []}


_RPM_LABELS = {1: ["main"], 2: ["low", "high"], 3: ["idle", "mid", "high"]}


@dataclass
class Role:
    role: str
    sound: int
    event: str
    path: list[str]
    media: int
    loop: bool
    rpm: dict | None = None
    delay: float = 0.0           # InitialDelay (s): retail start durationMax = 6.773 s media + 0.7 s
    aliases: list[str] = field(default_factory=list)


def donor_roles(donor: Donor, names: dict[int, str] | None = None) -> list[Role]:
    """One role per Sound reached by an event's Play actions: ``<event suffix>[.<label>...]``.
    Layer crossfades on an RTPC are labelled by audible rpm (idle/mid/high, low/high, overlay), switch
    children by state name, random/sequence children by position."""
    names = names or {}
    objects = donor.bank.by_id()
    prefix = donor.name + "_"
    found: dict[int, Role] = {}

    def visit(oid: int, event: str, labels: list[str], rpm: dict | None) -> None:
        obj = objects.get(oid)
        if obj is None:
            return
        info = obj.info
        if obj.type == 2:
            loop = PROP_LOOP in info.get("props", {})
            role = ".".join([event] + labels)
            if oid in found:
                found[oid].aliases.append(role)
            else:
                delay = info.get("props", {}).get(PROP_INITIAL_DELAY)
                delay = struct.unpack("<f", struct.pack("<I", delay))[0] if delay is not None else 0.0
                found[oid] = Role(role, oid, event, labels, info["media"], loop, rpm, delay)
            return
        children = info.get("children", [])
        if obj.type == 9:
            layers = sorted(info["layers"], key=lambda layer: -len(layer["assoc"]))
            seen = set()
            for index, layer in enumerate(layers):
                assoc = [a for a in layer["assoc"] if a["child"] in objects]
                ranges = [(rpm_range(a["points"]), a["child"]) for a in assoc]
                ranges.sort(key=lambda r: (r[0] or {"audible": [0, 0]})["audible"])
                if index == 0:
                    label_set = _RPM_LABELS.get(len(ranges), [f"r{i + 1}" for i in range(len(ranges))])
                else:
                    label_set = (["overlay"] if len(ranges) == 1 and len(layers) == 2
                                 else [f"layer{index + 1}.{i + 1}" for i in range(len(ranges))])
                for label, (span, child) in zip(label_set, ranges):
                    seen.add(child)
                    visit(child, event, labels + [label], span)
            rest = [c for c in children if c not in seen]
            for i, child in enumerate(rest):
                visit(child, event, labels + ([str(i + 1)] if len(rest) > 1 else []), rpm)
        elif obj.type == 6:
            placed = set()
            for state, nodes in info["switches"].items():
                for i, child in enumerate(nodes):
                    placed.add(child)
                    label = names.get(state, str(state))
                    visit(child, event, labels + [label] + ([str(i + 1)] if len(nodes) > 1 else []), rpm)
            for i, child in enumerate(c for c in children if c not in placed):
                visit(child, event, labels + [f"unswitched{i + 1}"], rpm)
        else:
            for i, child in enumerate(children):
                visit(child, event, labels + ([str(i + 1)] if len(children) > 1 else []), rpm)

    events = {wb.fnv1_32(name): name for name in donor.events}
    for obj in donor.bank.objects:
        if obj.type != 4:
            continue
        event_name = events.get(obj.id, str(obj.id))
        suffix = event_name[len(prefix):] if event_name.startswith(prefix) else event_name
        for action_id in obj.info["actions"]:
            action = objects.get(action_id)
            if action is not None and action.info["actionType"] >> 8 == 0x04:
                visit(action.info["target"], suffix, [], None)
    return sorted(found.values(), key=lambda r: r.role)


def match_roles(roles: list[Role], key: str) -> list[Role]:
    """Roles a ``--clip`` key names: a role, a role prefix (``acc`` matches ``acc.1``...), or a Sound ID."""
    if key.isdigit():
        return [r for r in roles if r.sound == int(key)]
    return [r for r in roles if r.role == key or r.role.startswith(key + ".") or key in r.aliases]


# --- the clone -------------------------------------------------------------------------------------------------

@dataclass
class Clone:
    name: str
    files: dict[str, bytes]
    report: dict[str, Any]


def event_rename(donor: str, name: str, event: str) -> str:
    if not event.startswith(donor + "_"):
        raise SoundCloneError(f"donor event {event} does not start with {donor}_; cannot rename it")
    return name + event[len(donor):]


def event_durations(bank: wb.Bank, seconds: dict[int, float | None]) -> dict[int, tuple[float, float]]:
    """(min, max) seconds per event, the way retail ``durationMin/Max`` come out (R, all TK53 Krot one-shots):
    a Sound is its media plus InitialDelay, a layer the longest child, a switch or random container the
    shortest and longest child, an event the longest of its Play targets.  Looping events are skipped."""
    objects = bank.by_id()

    def span(oid: int) -> tuple[float, float] | None:
        obj = objects.get(oid)
        if obj is None:
            return None
        info = obj.info
        delay = info.get("props", {}).get(PROP_INITIAL_DELAY)
        delay = struct.unpack("<f", struct.pack("<I", delay))[0] if delay is not None else 0.0
        if obj.type == 2:
            if PROP_LOOP in info.get("props", {}) or seconds.get(oid) is None:
                return None
            return seconds[oid] + delay, seconds[oid] + delay
        spans = [s for s in (span(c) for c in info.get("children", [])) if s]
        if not spans:
            return None
        if obj.type == 9:
            return max(s[0] for s in spans) + delay, max(s[1] for s in spans) + delay
        return min(s[0] for s in spans) + delay, max(s[1] for s in spans) + delay

    out = {}
    for obj in bank.objects:
        if obj.type != 4:
            continue
        spans = []
        for action_id in obj.info["actions"]:
            action = objects.get(action_id)
            if action is not None and action.info["actionType"] >> 8 == 0x04:
                spans.append(span(action.info["target"]))
        if spans and all(spans):
            out[obj.id] = (max(s[0] for s in spans), max(s[1] for s in spans))
    return out


def _seconds_text(value: float) -> str:
    text = f"{value:.6f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def _new_id(seed: str, taken: set[int]) -> int:
    salt = 0
    while True:
        value = wb.fnv1_32(seed if not salt else f"{seed}#{salt}")
        if value and value not in taken:
            taken.add(value)
            return value
        salt += 1


def clone_bank(donor: Donor, name: str, clips: dict[str, Pcm], taken: set[int] | None = None,
               names: dict[int, str] | None = None) -> Clone:
    """Build the clone.  ``clips`` maps a role key (see :func:`match_roles`) to PCM; ``taken`` is the set of
    IDs to avoid (all retail IDs); the donor's own IDs are always avoided."""
    if not NAME_RE.match(name):
        raise SoundCloneError(f"bank name {name!r}: use 3-64 lowercase letters, digits and _")
    bank = donor.bank
    if bank.unparsed:
        kinds = sorted({o.type_name for o in bank.unparsed})
        raise SoundCloneError(f"donor {donor.name} has objects this reader cannot re-ID: {kinds}")
    taken = set(taken or ()) | {bank.bank_id} | {m.id for m in bank.media} | bank.defined_ids()
    bank_id = wb.fnv1_32(name)
    if bank_id in taken:
        raise SoundCloneError(f"bank name {name} hashes to an ID already in use ({bank_id})")
    taken.add(bank_id)

    roles = donor_roles(donor, names)
    by_sound = {r.sound: r for r in roles}
    assigned: dict[int, tuple[str, Pcm]] = {}
    for key, pcm in clips.items():
        hits = match_roles(roles, key)
        if not hits:
            raise SoundCloneError(f"--clip {key}: no such role (see the role list)")
        for role in hits:
            assigned[role.sound] = (key, pcm)

    # event IDs from names, every other defined ID re-derived from the new name
    event_names = {wb.fnv1_32(e): event_rename(donor.name, name, e) for e in donor.events}
    id_map: dict[int, int] = {}
    for obj in bank.objects:
        for f in obj.fields:
            if f.kind != "def" or f.value in id_map:
                continue
            if obj.type == 4 and f.role == "ulID":
                new_event = event_names.get(f.value)
                if new_event is None:
                    raise SoundCloneError(f"event {f.value} in the bank has no retail event resource")
                value = wb.fnv1_32(new_event)
                if value in taken:
                    raise SoundCloneError(f"event {new_event} hashes to an ID already in use ({value})")
                taken.add(value)
                id_map[f.value] = value
            else:
                id_map[f.value] = _new_id(f"{name}#{f.role}#{f.value}", taken)

    # media: one new ID per distinct clip, and per donor media kept
    sound_media: dict[int, int] = {}
    media_bytes: dict[int, bytes] = {}
    clip_ids: dict[str, int] = {}
    kept_media: dict[int, int] = {}
    donor_media = {m.id: m for m in bank.media}
    for obj in bank.objects:
        if obj.type != 2:
            continue
        if obj.id in assigned:
            key, pcm = assigned[obj.id]
            if key not in clip_ids:
                clip_ids[key] = _new_id(f"{name}#clip#{key}", taken)
                media_bytes[clip_ids[key]] = pcm_wem(pcm)
            sound_media[obj.id] = clip_ids[key]
            continue
        old = obj.info["media"]
        if old not in kept_media:
            kept_media[old] = _new_id(f"{name}#media#{old}", taken)
        new = kept_media[old]
        if new not in media_bytes:
            if obj.info["stream"] == wb.STREAM_DATA and old in donor_media:
                media_bytes[new] = bank.media_bytes(old)
            elif old in donor.streamed:
                media_bytes[new] = donor.streamed[old]
            else:
                raise SoundCloneError(f"donor media {old} (Sound {obj.id}) is neither in DATA nor a media bundle")
        sound_media[obj.id] = new

    # HIRC: patch IDs in place (no object changes size)
    hirc_off, hirc_size = bank.chunk(b"HIRC")
    data = bytearray(bank.data)
    for obj in bank.objects:
        for f in obj.fields:
            if f.kind in ("def", "ref") and f.value in id_map:
                struct.pack_into("<I", data, f.offset, id_map[f.value])
            elif f.kind == "bank":
                struct.pack_into("<I", data, f.offset, bank_id)
            elif f.kind == "media":
                media_id = sound_media[obj.id]
                struct.pack_into("<I", data, f.offset, media_id)
                info = obj.info
                if obj.id in assigned:
                    struct.pack_into("<I", data, info["pluginOffset"], wb.CODEC_PCM)
                data[info["streamOffset"]] = wb.STREAM_DATA
                struct.pack_into("<I", data, info["memSizeOffset"], len(media_bytes[media_id]))
    hirc = bytes(data[hirc_off:hirc_off + hirc_size])

    # DIDX / DATA: media sorted by ID, 16-byte aligned like retail
    didx, blob = bytearray(), bytearray()
    for media_id in sorted(media_bytes):
        while len(blob) % 16:
            blob.append(0)
        didx += struct.pack("<III", media_id, len(blob), len(media_bytes[media_id]))
        blob += media_bytes[media_id]
    bkhd_off, bkhd_size = bank.chunk(b"BKHD")
    bkhd = bytearray(bank.data[bkhd_off:bkhd_off + bkhd_size])
    struct.pack_into("<I", bkhd, 4, bank_id)
    out = bytearray()
    for tag, payload in ((b"BKHD", bkhd), (b"DIDX", didx), (b"DATA", blob), (b"HIRC", hirc)):
        out += tag + struct.pack("<I", len(payload)) + payload
    for tag, offset, size in bank.chunks:
        if tag not in (b"BKHD", b"DIDX", b"DATA", b"HIRC"):
            out += bank.data[offset:offset + 8 + size]

    files = {f"sounds/desktop/{name}.bnk": bytes(out)}
    bank_res = dict(donor.bank_resource)
    bank_res["blob_platform_x64"] = f"../desktop/{name}.bnk"
    bank_res["name"] = name
    files[f"sounds/banks/{name}.sound_bank.resource"] = write_resource(bank_res).encode()

    changed_roles = {r.sound for r in roles if r.sound in assigned}
    event_rows = []
    for event, fields in sorted(donor.events.items()):
        new_event = event_rename(donor.name, name, event)
        res = dict(fields)
        res["banks"] = [bank_tag(name) if b == bank_tag(donor.name) else b for b in fields["banks"]]
        res["media_bundles"] = []
        res["name"] = new_event
        for key in ("startAudioIDs", "stopAudioIDs"):
            res[key] = [str(id_map.get(int(v), int(v))) for v in fields.get(key, [])]
        suffix = event[len(donor.name) + 1:]
        event_roles = [r for r in roles if r.event == suffix]
        if any(r.sound in changed_roles for r in event_roles) and fields.get("isLoop") != "true":
            span = event_durations(bank, {s: wem_seconds(media_bytes[m]) for s, m in sound_media.items()}).get(
                wb.fnv1_32(event))
            if span:
                res["durationMin"], res["durationMax"] = _seconds_text(span[0]), _seconds_text(span[1])
        files[f"sounds/events/{new_event}.sound_event.resource"] = write_resource(res).encode()
        event_rows.append({"donor": event, "event": new_event, "id": wb.fnv1_32(new_event),
                           "startAudioIDs": [int(v) for v in res["startAudioIDs"]]})

    role_rows = []
    for r in roles:
        row = {"role": r.role, "sound": r.sound, "newSound": id_map[r.sound], "loop": r.loop,
               "donorMedia": r.media, "newMedia": sound_media[r.sound]}
        if r.rpm:
            row["rpm"] = r.rpm
        if r.aliases:
            row["aliases"] = r.aliases
        if r.sound in assigned:
            key, pcm = assigned[r.sound]
            row["clip"] = key
            row["seconds"] = round(pcm.seconds, 3)
            if r.loop and pcm.frames > 2:
                row["seam"] = loop_seam(pcm)
        else:
            row["clip"] = None
        role_rows.append(row)
    unassigned = [r.role for r in roles if r.sound not in assigned]
    report = {"donor": donor.name, "name": name, "bankId": bank_id, "events": event_rows, "roles": role_rows,
              "unassignedKeepDonorMedia": unassigned, "media": len(media_bytes),
              "bankBytes": len(out), "status": "build-only, unbenched (library/audio-assets.md)"}
    return Clone(name, files, report)


def role_table(donor: Donor, names: dict[int, str] | None = None) -> dict[str, Any]:
    names = names or {}
    rows = []
    for r in donor_roles(donor, names):
        media = donor.streamed.get(r.media)
        if media is None and r.media in {m.id for m in donor.bank.media}:
            media = donor.bank.media_bytes(r.media)
        row = {"role": r.role, "sound": r.sound, "loop": r.loop,
               "seconds": round(wem_seconds(media), 3) if media and wem_seconds(media) else None}
        if r.rpm:
            row["rpm"] = r.rpm
        if r.delay:
            row["initialDelay"] = round(r.delay, 3)
        if r.aliases:
            row["aliases"] = r.aliases
        rows.append(row)
    layers = []
    for obj in donor.bank.objects:
        if obj.type == 9:
            for layer in obj.info["layers"]:
                if layer["crossfade"]:
                    layers.append({"container": obj.id, "crossfade": names.get(layer["crossfade"], layer["crossfade"]),
                                   "pitchCents": [[[round(x, 1), round(y, 1)] for x, y, _ in c["points"]]
                                                  for c in layer["rtpc"] if c["param"] == 2]})
    return {"donor": donor.name, "roles": rows, "crossfadeLayers": layers,
            "events": sorted(donor.events), "hint": "assign with --clip ROLE=file.wav (or ROLE=silence); "
            "a role prefix assigns all its sub-roles; unassigned roles keep the donor's recording"}


def write_clone(clone: Clone, out: Path) -> list[str]:
    written = []
    for rel, data in sorted(clone.files.items()):
        path = Path(out) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(str(path))
    return written


def _parse_clips(values: Sequence[str]) -> dict[str, Pcm]:
    clips: dict[str, Pcm] = {}
    for value in values:
        key, sep, path = value.partition("=")
        if not sep or not key or not path:
            raise SoundCloneError(f"--clip {value!r}: use ROLE=path.wav or ROLE=silence")
        clips[key] = silence() if path == SILENCE else read_wav(Path(path).read_bytes())
    return clips


def main(argv: Sequence[str] | None = None) -> int:
    """``sound clone-bank --donor BANK --name NEW [--clip ROLE=WAV ...] [--out DIR] [--game DIR] [--json]``."""
    parser = argparse.ArgumentParser(prog="roadcraft sound", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    clone = sub.add_parser("clone-bank", help="Clone a retail sample bank with your WAVs as PCM (build-only, "
                                              "unbenched; library/audio-assets.md)")
    clone.add_argument("--donor", required=True, help="retail bank name, e.g. vhc_vostok_tk53krot")
    clone.add_argument("--name", required=True, help="new bank name; also replaces the donor's event prefix")
    clone.add_argument("--clip", action="append", default=[], metavar="ROLE=WAV",
                       help="assign a WAV (or 'silence') to a role, role prefix or Sound ID (repeatable)")
    clone.add_argument("--out", type=Path, help="write <out>/sounds/...; without it, only list the roles")
    clone.add_argument("--game", type=Path, help="RoadCraft install (default: ROADCRAFT_GAME_ROOT, sdkRoot, Steam)")
    clone.add_argument("--json", action="store_true", help="compact JSON")
    args = parser.parse_args(argv)
    try:
        game = project_context.game_root(args.game)
        names = known_names(game)
        donor = load_donor(game, args.donor)
        if args.out is None and not args.clip:
            result: dict[str, Any] = role_table(donor, names)
        else:
            built = clone_bank(donor, args.name, _parse_clips(args.clip), retail_ids(game), names)
            result = built.report
            if args.out is not None:
                result["written"] = write_clone(built, args.out)
    except (SoundCloneError, wb.BankFormatError, retail.RetailDataError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
