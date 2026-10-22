"""Read and re-ID Wwise 2019.2 SoundBanks (BKHD version 135), the format of every retail RoadCraft ``.bnk``.

Nothing here runs Wwise.  The reader walks the HIRC object types RoadCraft's sample-based vehicle banks use
(Sound, Action, Event, Random/Sequence, Switch, Layer, Actor-Mixer, Attenuation, State) field by field and
records where every 32-bit ID sits, so a bank can be cloned by patching those IDs in place: no object changes
size, so the HIRC re-serialises byte for byte.  Field layouts follow Wwise 2019.2 (bank v135) as checked
against all 85 retail banks (``tests/test_wwise_bank.py``; C:/RC_RE/research/sound_semantics.md §7).

ID kinds:

* ``def``   an object's own ID (``ulID``), a layer ID or a media ID: defined by this bank, re-IDed on clone;
* ``ref``   a reference that may point inside the bank (parent, children, action target, attenuation,
            FX, state instance) or outside it (busses in ``init.bnk``): remapped only if defined here;
* ``media`` a Sound's source (media) ID;
* ``bank``  a Play action's bank ID;
* ``sync``  a game-sync, bus or curve ID owned by ``init.bnk`` (RTPC, switch group/state, state group):
            never changed.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Iterator

BANK_VERSION = 135

HIRC_TYPES = {1: "State", 2: "Sound", 3: "Action", 4: "Event", 5: "RanSeqCntr", 6: "SwitchCntr",
              7: "ActorMixer", 9: "LayerCntr", 14: "Attenuation"}

CODEC_PCM = 0x00010001
CODEC_ADPCM = 0x00020001
CODEC_VORBIS = 0x00040001

STREAM_DATA = 0          # media wholly in the bank's DATA chunk
STREAM_PREFETCH = 1      # the first bytes in DATA, the rest in a streamed media bundle
STREAM_ONLY = 2          # wholly streamed


class BankFormatError(ValueError):
    """The bank is not a v135 bank, or holds an object this reader cannot walk."""


def fnv1_32(name: str) -> int:
    """Wwise ShortID of a name: FNV-1 32-bit over the lowercase ASCII bytes (bank, event, game-sync IDs)."""
    value = 2166136261
    for byte in name.lower().encode("ascii"):
        value = (value * 16777619) & 0xFFFFFFFF
        value ^= byte
    return value


@dataclass
class IdField:
    offset: int          # absolute offset in the bank file
    kind: str            # def / ref / media / bank / sync
    value: int
    role: str = ""       # e.g. "ulID", "parent", "child", "target", "rtpc"


@dataclass
class HircObject:
    type: int
    id: int
    offset: int          # offset of the type byte in the file
    size: int            # the declared size (from ulID to the end)
    fields: list[IdField] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    @property
    def type_name(self) -> str:
        return HIRC_TYPES.get(self.type, f"type{self.type}")


@dataclass
class Media:
    id: int
    offset: int          # relative to the start of DATA's payload
    size: int


@dataclass
class Bank:
    data: bytes
    version: int
    bank_id: int
    bank_id_offset: int
    chunks: list[tuple[bytes, int, int]]          # (tag, offset of the tag, payload size)
    media: list[Media]
    objects: list[HircObject]
    unparsed: list[HircObject] = field(default_factory=list)

    def chunk(self, tag: bytes) -> tuple[int, int] | None:
        """(payload offset, payload size) of a chunk."""
        for name, offset, size in self.chunks:
            if name == tag:
                return offset + 8, size
        return None

    def by_id(self) -> dict[int, HircObject]:
        return {obj.id: obj for obj in self.objects}

    def defined_ids(self) -> set[int]:
        return {f.value for obj in self.objects for f in obj.fields if f.kind == "def"}

    def media_bytes(self, media_id: int) -> bytes:
        data = self.chunk(b"DATA")
        for item in self.media:
            if item.id == media_id and data:
                return self.data[data[0] + item.offset:data[0] + item.offset + item.size]
        raise KeyError(media_id)


class _Reader:
    def __init__(self, data: bytes, start: int, end: int, obj: HircObject):
        self.data, self.pos, self.end, self.obj = data, start, end, obj

    def _take(self, fmt: str):
        size = struct.calcsize(fmt)
        if self.pos + size > self.end:
            raise BankFormatError(f"{self.obj.type_name} {self.obj.id}: read past the object end")
        value = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return value[0] if len(value) == 1 else value

    def u8(self) -> int: return self._take("<B")
    def u16(self) -> int: return self._take("<H")
    def u32(self) -> int: return self._take("<I")
    def f32(self) -> float: return self._take("<f")
    def skip(self, n: int) -> None:
        if self.pos + n > self.end:
            raise BankFormatError(f"{self.obj.type_name} {self.obj.id}: read past the object end")
        self.pos += n

    def var(self) -> int:
        value = 0
        while True:
            byte = self.u8()
            value = (value << 7) | (byte & 0x7F)
            if not byte & 0x80:
                return value

    def id(self, kind: str, role: str = "") -> int:
        offset = self.pos
        value = self.u32()
        self.obj.fields.append(IdField(offset, kind, value, role))
        return value


def _prop_bundle(r: _Reader) -> dict[int, int]:
    count = r.u8()
    ids = [r.u8() for _ in range(count)]
    props = {}
    for pid in ids:
        # values are floats or IDs (AttenuationID, ...): record them all as refs, remapped only if defined here
        props[pid] = r.id("ref", f"prop{pid}")
    return props


def _ranged_bundle(r: _Reader) -> None:
    count = r.u8()
    r.skip(count + count * 8)


def _curve(r: _Reader) -> list[tuple[float, float, int]]:
    count = r.u16()
    return [r._take("<ffI") for _ in range(count)]


def _initial_rtpc(r: _Reader) -> list[dict]:
    curves = []
    for _ in range(r.u16()):
        rtpc = r.id("sync", "rtpc")
        rtpc_type, accum = r.u8(), r.u8()
        param = r.var()
        curve_id = r.id("sync", "curve")
        scaling = r.u8()
        curves.append({"rtpc": rtpc, "type": rtpc_type, "accum": accum, "param": param, "curveId": curve_id,
                       "scaling": scaling, "points": _curve(r)})
    return curves


def _positioning(r: _Reader) -> None:
    bits = r.u8()
    has_positioning = bits & 1
    has_3d = (bits >> 1) & 1 if has_positioning else 0
    if has_positioning and has_3d:
        r.u8()                                         # uBits3d
        if (bits >> 5) & 3:                            # e3DPositionType != emitter: automation path
            r.u8()
            r.skip(4)
            vertices = r.u32()
            r.skip(vertices * 16)
            items = r.u32()
            r.skip(items * 8 + items * 12)


def _state_chunk(r: _Reader) -> None:
    for _ in range(r.var()):                           # (PropertyId, accumType, inDb)
        r.var()
        r.skip(2)
    for _ in range(r.var()):
        r.id("sync", "stateGroup")
        r.u8()
        for _ in range(r.var()):
            r.id("sync", "state")
            r.id("ref", "stateInstance")


def _node_base(r: _Reader, info: dict) -> None:
    r.u8()                                             # bIsOverrideParentFX
    fx = r.u8()
    if fx:
        r.u8()
        for _ in range(fx):
            r.u8()
            r.id("ref", "fx")
            r.skip(2)
    r.u8()                                             # bOverrideAttachmentParams
    info["bus"] = r.id("ref", "bus")
    info["parent"] = r.id("ref", "parent")
    r.u8()
    info["props"] = _prop_bundle(r)
    _ranged_bundle(r)
    _positioning(r)
    aux = r.u8()
    if aux & 0x08:
        for _ in range(4):
            r.id("ref", "aux")
    r.id("ref", "reflectionsAux")
    r.skip(6)                                          # AdvSettingsParams
    _state_chunk(r)
    info["rtpc"] = _initial_rtpc(r)


def _children(r: _Reader) -> list[int]:
    return [r.id("ref", "child") for _ in range(r.u32())]


def _sound(r: _Reader, info: dict) -> None:
    info["pluginOffset"] = r.pos
    plugin = r.u32()
    info["plugin"] = plugin
    info["streamOffset"] = r.pos
    info["stream"] = r.u8()
    info["media"] = r.id("media", "source")
    info["memSizeOffset"] = r.pos
    info["memSize"] = r.u32()
    info["sourceBitsOffset"] = r.pos
    info["sourceBits"] = r.u8()
    if plugin & 0x0F == 2:                             # source plugin (Sine, REV, ...) with parameters
        r.skip(r.u32())
    _node_base(r, info)


def _ranseq(r: _Reader, info: dict) -> None:
    _node_base(r, info)
    info["loopOffset"] = r.pos
    info["loopCount"] = r.u16()
    r.skip(4 + 12 + 2 + 3 + 1)
    info["children"] = _children(r)
    for _ in range(r.u16()):
        r.id("ref", "playlist")
        r.skip(4)


def _switch(r: _Reader, info: dict) -> None:
    _node_base(r, info)
    r.u8()
    info["group"] = r.id("sync", "switchGroup")
    info["default"] = r.id("sync", "defaultSwitch")
    r.u8()
    info["children"] = _children(r)
    info["switches"] = {}
    for _ in range(r.u32()):
        switch = r.id("sync", "switch")
        info["switches"][switch] = [r.id("ref", "switchNode") for _ in range(r.u32())]
    for _ in range(r.u32()):
        r.id("ref", "switchParam")
        r.skip(2 + 8)


def _layer(r: _Reader, info: dict) -> None:
    _node_base(r, info)
    info["children"] = _children(r)
    layers = []
    for _ in range(r.u32()):
        layer = {"id": r.id("def", "layer")}
        layer["rtpc"] = _initial_rtpc(r)
        layer["crossfade"] = r.id("sync", "crossfadeRtpc")
        r.u8()
        layer["assoc"] = []
        for _ in range(r.u32()):
            child = r.id("ref", "layerChild")
            count = r.u32()
            points = [r._take("<ffI") for _ in range(count)]
            layer["assoc"].append({"child": child, "points": points})
        layers.append(layer)
    info["layers"] = layers
    r.u8()                                             # bIsContinuousValidation


def _actor_mixer(r: _Reader, info: dict) -> None:
    _node_base(r, info)
    info["children"] = _children(r)


def _attenuation(r: _Reader, info: dict) -> None:
    if r.u8() & 1:
        r.skip(20)
    r.skip(7)                                          # curveToUse[7]
    for _ in range(r.u8()):
        r.u8()
        _curve(r)
    info["rtpc"] = _initial_rtpc(r)


def _state(r: _Reader, info: dict) -> None:
    count = r.u16()
    r.skip(count * 2 + count * 4)


def _except(r: _Reader) -> None:
    for _ in range(r.var()):
        r.id("ref", "except")
        r.u8()


def _action(r: _Reader, info: dict) -> None:
    kind = r.u16()
    info["actionType"] = kind
    info["target"] = r.id("ref", "target")
    r.u8()                                             # target is a bus
    info["props"] = _prop_bundle(r)
    _ranged_bundle(r)
    family = kind >> 8
    # Retail uses only 0x0403, 0x0103, 0x1E03, 0x1901, 0x1C03 and 0x1403; those layouts are size-checked
    # against all 85 banks.  The other families follow the Wwise 2019.2 layouts and are unverified.
    if family == 0x04:                                 # Play
        r.u8()
        info["bank"] = r.id("bank", "bank")
    elif family in (0x01, 0x02, 0x03):                 # Stop / Pause / Resume
        r.u8()
        r.u8()
        _except(r)
    elif family in (0x06, 0x07):                       # Mute / Unmute
        r.u8()
        _except(r)
    elif family in (0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x20, 0x30):  # Set/Reset Ak props
        r.u8()
        r.u8()
        r.skip(12)
        _except(r)
    elif family == 0x12:                               # SetState
        info["stateGroup"] = r.id("sync", "stateGroup")
        info["state"] = r.id("sync", "state")
    elif family == 0x19:                               # SetSwitch
        info["switchGroup"] = r.id("sync", "switchGroup")
        info["switchState"] = r.id("sync", "switchState")
    elif family in (0x13, 0x14):                       # Set/Reset GameParameter
        r.u8()
        r.u8()
        r.u8()
        r.skip(12)
        _except(r)
    elif family == 0x1E:                               # Seek: relative-to-duration, value/min/max, snap
        r.u8()
        info["seek"] = r._take("<fff")
        r.u8()
        _except(r)
    elif family in (0x10, 0x11, 0x1C):                 # Use/UnuseState, Break: no parameters
        pass
    else:
        raise BankFormatError(f"Action {info.get('id')}: unsupported action type 0x{kind:04x}")


def _event(r: _Reader, info: dict) -> None:
    info["actions"] = [r.id("ref", "action") for _ in range(r.var())]


_PARSERS = {1: _state, 2: _sound, 3: _action, 4: _event, 5: _ranseq, 6: _switch, 7: _actor_mixer, 9: _layer,
            14: _attenuation}


def _parse_object(data: bytes, offset: int) -> HircObject:
    kind = data[offset]
    size, oid = struct.unpack_from("<II", data, offset + 1)
    obj = HircObject(kind, oid, offset, size)
    reader = _Reader(data, offset + 5, offset + 5 + size, obj)
    reader.id("def", "ulID")
    obj.info["id"] = oid
    _PARSERS[kind](reader, obj.info)
    if reader.pos != reader.end:
        raise BankFormatError(f"{obj.type_name} {oid}: parsed {reader.pos - offset - 5} of {size} bytes")
    return obj


def iter_chunks(data: bytes) -> Iterator[tuple[bytes, int, int]]:
    pos = 0
    while pos + 8 <= len(data):
        tag = data[pos:pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        yield tag, pos, size
        pos += 8 + size


def read_bank(data: bytes, strict: bool = True) -> Bank:
    """Parse a bank.  ``strict`` raises on an object type or layout this reader cannot walk; otherwise such
    objects are kept in ``Bank.unparsed`` (their IDs then cannot be rewritten, so a clone refuses them)."""
    chunks = list(iter_chunks(data))
    if not chunks or chunks[0][0] != b"BKHD":
        raise BankFormatError("not a Wwise SoundBank (no BKHD)")
    version, bank_id = struct.unpack_from("<II", data, 8)
    if version != BANK_VERSION:
        raise BankFormatError(f"bank version {version}; only {BANK_VERSION} (Wwise 2019.2) is supported")
    media: list[Media] = []
    objects: list[HircObject] = []
    unparsed: list[HircObject] = []
    for tag, offset, size in chunks:
        if tag == b"DIDX":
            for pos in range(offset + 8, offset + 8 + size, 12):
                media.append(Media(*struct.unpack_from("<III", data, pos)))
        elif tag == b"HIRC":
            count = struct.unpack_from("<I", data, offset + 8)[0]
            pos = offset + 12
            for _ in range(count):
                kind = data[pos]
                obj_size, oid = struct.unpack_from("<II", data, pos + 1)
                if kind in _PARSERS:
                    try:
                        objects.append(_parse_object(data, pos))
                    except (BankFormatError, struct.error) as exc:
                        if strict:
                            raise BankFormatError(str(exc)) from exc
                        unparsed.append(HircObject(kind, oid, pos, obj_size))
                elif strict:
                    raise BankFormatError(f"unsupported HIRC object type {kind} (ID {oid})")
                else:
                    unparsed.append(HircObject(kind, oid, pos, obj_size))
                pos += 5 + obj_size
    return Bank(data, version, bank_id, 12, chunks, media, objects, unparsed)
