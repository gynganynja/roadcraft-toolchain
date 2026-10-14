"""Validate a mod (source folder or built ``.pak``) for faults that fail or silently break at runtime.

``validate(target)`` returns :class:`Finding` rows ``(rule, severity, path, line, message, evidence)`` plus a
stable ``code`` (continuing the toolchain's RC0xx numbering after ``bro_lint``'s RC048) and the ``key`` path
inside the file.  Severity ``error`` = will fail or silently break at runtime; ``warning`` = likely wrong;
``info`` = for review.  Every rule cites the library article / research note it implements and carries the
library's evidence grade (Game, Retail, SDK, Build, Inferred, Open).  The rules, the evidence and what they
found on the owner's mods are in library/validator.md.

Targets (read-only; nothing is ever written):

* a mod source folder: a staged project ``p/`` (its ``mods_source`` is used), a ``mods_source`` tree, or any
  folder laid out like one (``ssl/``, ``models/``, ``material_instances/``...; ``.bro`` files anywhere);
* a built ``.pak``: members are read in memory with :mod:`zipfile`, by (name, occurrence), so the duplicate
  members the SDK packager writes are honoured (identical duplicates are checked once, differing ones reported).

Context comes from the installation (``--game-root``, ``ROADCRAFT_GAME_ROOT`` or the Steam path): the editor
schema (:mod:`roadcraft.schema`), the retail pak index (:mod:`roadcraft.retail`; the override-manifest approach
of C:\\RC_RE\\research\\override_manifest.py: a tag is ``res://`` + lower-case member path) and retail classes,
models and markup presets.  Without an installation the schema- and retail-dependent rules are skipped and the
report says so.

Reused modules: :mod:`ps_format` (editor-faithful PS parser), :mod:`tpl_reader` (compiled node tables),
:mod:`bro_lint` (truck BRO checks, composed for ``.bro`` files), :mod:`lamps` (lit copies hidden by markup,
strobes), :mod:`retail`, :mod:`schema`.  Stdlib only.
"""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import hashlib
import json
import os
import posixpath
import re
import sys
import zipfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from . import bro_lint, lamps, ps_format, retail
from . import schema as schema_mod
from .tpl_reader import TplFormatError, TplNodes, read_tpl_bytes

SEVERITIES = ("error", "warning", "info")
SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2}
PS_EXTENSIONS = (".cls", ".prop", ".sso", ".tpl_markup", ".lods_base", ".mi", ".td", ".bro", ".ps")
YAML_EXTENSIONS = (".resource", ".asset", ".mod")

# code -> (rule, title, evidence grade and source).  Codes continue bro_lint's RC001-RC048 (library/validator.md).
CODES: dict[str, tuple[str, str, str]] = {
    "RC049": ("ps-parse", "the Mod Editor cannot parse the file",
              "SDK: decompiled Saber.Common Ps.Parser (C:/RC_RE/research/schema.md 2.1)"),
    "RC050": ("ps-numbers", "number followed by letters: exponent notation is not supported",
              "SDK: Ps.Parser has no exponent (schema.md 2.2); 1e-05 -> 1 then a stray key 'e'"),
    "RC051": ("ps-numbers", "leading-dot number loses its first digit",
              "SDK: Ps.Parser.ParseNumber consumes the char after '.' twice (schema.md 2.2): .5 -> 0, .25 -> 0.5"),
    "RC052": ("ps-numbers", "bare on/off/yes/no value becomes a bool",
              "SDK: Ps.Parser reads true/false/on/off/yes/no as bools in value position (schema.md 2.2)"),
    "RC053": ("unknown-keys", "key not in the schema (kept as a removed-field hint, ignored by the engine)",
              "SDK: DefaultModelTreeSerializer keeps it as a NullModel (schema.md 5.3); engine ignoring it is Inferred"),
    "RC054": ("unknown-keys", "type not found",
              "SDK: 'Type not found' ErrorModel (schema.md 5.3)"),
    "RC055": ("unknown-keys", "enum value not allowed",
              "SDK: \"Value 'x' not allowed.\" ErrorModel; Game: torqueType 'default' left wheels undriven "
              "(Roamer 105, library/truck-settings.md, symptoms.md)"),
    "RC056": ("unknown-keys", "value type mismatch",
              "SDK: Convert.ChangeType failure -> ErrorModel (schema.md 5.3)"),
    "RC057": ("unknown-keys", "value outside the field's UI range",
              "SDK: __viewType min/max are UI hints only, not enforced on load (schema.md 3)"),
    "RC058": ("wheel-frames", "wheel slot names a node the body model lacks",
              "Build: lint-bro RC023 (library/suspension-and-wheels.md 'Wheel slots')"),
    "RC059": ("wheel-frames", "mirrored (left-handed) wheel-slot frame",
              "SDK: tplexp asserts right-handed orthonormal frames, negative_scale_intl (schema.md 4.4); Retail: no "
              "shipped slot node is mirrored (306 trucks); inside-out faces Inferred"),
    "RC060": ("wheel-frames", "isRightSided disagrees with the slot's side (inside-out wheels)",
              "Game: brake discs/inner faces outward on one side (buggy, Lada; library/symptoms.md, "
              "suspension-and-wheels.md); Retail: every shipped truck is side-consistent (279) or uniformly "
              "reversed (8), none mixed"),
    "RC061": ("wheel-frames", "steering knuckle outside its wheel",
              "Game: knuckles thrown outside the wheels on one side (buggy; library/symptoms.md, "
              "suspension-and-wheels.md 'Steering joints and racks'); Retail: kingpins 0.16-0.37 m inboard, "
              "none outboard (156 knuckles)"),
    "RC062": ("wheel-frames", "deformable tyre without a 'tire' object in the wheel model",
              "Game: Lada v1 crash 'failed to find deforming geom obj with name tire' truck_wheel_prop.cpp:527 "
              "(library/symptoms.md)"),
    "RC063": ("suspension", "suspension collection missing or miswired",
              "Game: Warthog wheels on the ground with the body in the air (no useSuspensionCollection; "
              "library/suspension-and-wheels.md, symptoms.md, lint-bro RC001/RC030); Retail: every shipped truck "
              "class has suspensionAxleCollection or suspensionSet except the SDK sample tuz_119lynx_mod and "
              "auto_simplest_vehicle"),
    "RC064": ("joints", "joint with no reachable range",
              "SDK: tpl_markup constraint limits (schema.md 4.1, 7.3); Retail: limits checked on 1,751 shipped "
              "vehicle constraints"),
    "RC065": ("joints", "joint frame wrong-handed or joint names a missing body",
              "Game: KGS25 prismatic childRotation slid the telescope sideways (2.121 m error, library/frames.md); "
              "SDK: tplexp right-handed assert; Retail: no constrained node is mirrored"),
    "RC066": ("lamps", "lamp has no lit material state",
              "SDK/Retail: the SDK TUZ sample defines lights_emmissive while its lamps ask for lights_emissive "
              "(library/cockpit-and-lamps.md 'Lamps that work in the retail campaign')"),
    "RC067": ("lamps", "lamp on and off materials are identical",
              "Build: D11 d11_beacon_off/d11_beacon_on (schema.md 7.4); no visible change when lit"),
    "RC068": ("lamps", "lamp object missing or hidden by the markup",
              "Game: lit copies hidden by markup never lit (L275 v4-v8, Dump Twuck v4; "
              "library/cockpit-and-lamps.md 'Do not hide lit lamp copies in the markup')"),
    "RC069": ("materials", "material slot the exporter merged away or will merge",
              "Build/Game: one material per texture in an exported object (L275 glass; library/build-pipeline.md, "
              "textures-and-materials.md); SDK: advanced.merge_materials (C:/RC_RE/research/pak_and_assets.md 4.3)"),
    "RC070": ("references", "reference resolves neither in the mod nor in retail",
              "Build: mod_pak_builder skips missing links silently and the engine substitutes ge_missing / a red "
              "texture (schema.md 4.3, 7.6; library/build-pipeline.md 'Package dependency closure')"),
    "RC071": ("duplicates", "duplicate pak members with different bytes",
              "Build: the packager writes byte-identical duplicates of each markup (library/build-pipeline.md, "
              "pak_and_assets.md 1.4); differing copies are Open (which one loads is not known)"),
    "RC072": ("ignored-fields", "field present but not read by the component",
              "code analysis, static: per-component reader tables (C:/RC_RE/research/physics_semantics.md T5, T7, "
              "F1; data/read_fields.json when present)"),
    "RC073": ("engine-defaults", "markup physics body leaves a property to the engine default",
              "code analysis, static: markup body constructor FUN_1430811e0 sets restitution 0.4, friction 0.5, "
              "angularDamping 0.05, density 600 and the reader FUN_1430812a0 overwrites only keys present "
              "(physics_semantics.md F2); Retail: crawler markups omit restitution"),
    "RC074": ("objsettings-gate", "markup objSettings entries gated off by objSettings.exportedVersion",
              "code analysis, static; in-game check pending: consumer 0x1431e6c60 applies per-object objSettings only "
              "when exportedVersion >= 1 (collision), 2 (visibility), 3 (lighting, sorting, render); absent = 0 "
              "(list ctor 0x1435ca970); read_fields.json 'gated', read_fields.md 3a"),
    "RC076": ("spring-motors", "load-bearing prismatic spring motor outside the retail regime",
              "code analysis, static: hkpCalcMotorData (ME FUN_1442406f0) turns tpl_markup_spring_motor into "
              "tau = k*dt^2/m_eff and damping = c*dt/m_eff, each clamped to [0, 1], m_eff = the row's virtual mass "
              "from both bodies (FUN_14423aa80), maxForce = HK_REAL_MAX (FUN_141594b60); Retail: load-bearing "
              "prismatic springs (lighter body >= 200 kg, TUZ Lynx family) reach 0.38 / 0.68 at most; Game: Mammoth "
              "RC62 rear heave (0.86 / 4.0) shook and swung limit to limit parked (physics_semantics.md "
              "'Spring-motor stability')"),
    "RC077": ("save-compat", "saved vehicle state the baseline wrote and this version cannot restore",
              "code analysis, static (C:/RC_RE/research/save_semantics.md): PropSavableObject.SetSavedProps matches "
              "saved descs by type; TruckConstraintsSavablePropDesc.LoadData replaces the constraint state with the "
              "saved one, then PropTruckConstraintView.RestoreFromSave does data.Get(chain.name) and the controller "
              "indexes saved chains/stages/constraints by the current names ('key not found in dictionary', Retail "
              "string); Game: L275 v35 'Toolboxes' chain hung old saves (library/save-compatibility.md)"),
}
RULES = sorted({rule for rule, _, _ in CODES.values()} | {"bro-lint"})


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    path: str
    line: int | None
    message: str
    evidence: str
    code: str = ""
    key: str = ""
    fixHint: str = ""               # noqa: N815 - JSON field name used by the desktop agent
    member: str = ""                # path inside the mod root (lower case), without the pak/tree prefix
    id: str = ""                    # stable id: short hash of (code, member, key); see finding_id

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["keyPath"] = self.key
        return out


def finding_id(code: str, member: str, key: str) -> str:
    """Stable finding id: 12 hex digits of sha1(code | member | keyPath).  No line number, message or pak name,
    so the same fault keeps its id across builds, line shifts and pak/tree targets."""
    return hashlib.sha1(f"{code}|{member.lower()}|{key}".encode("utf-8")).hexdigest()[:12]


# ------------------------------------------------------------------------------------------------ bundles

@dataclass
class _Member:
    name: str                       # path inside the mod root, '/'-separated, original case
    read: Callable[[], bytes]
    occurrence: int = 0


class Bundle:
    """The files of one target, keyed by lower-case mod-root path (= resource tag minus ``res://``)."""

    def __init__(self, label: str, kind: str, members: list[_Member]) -> None:
        self.label = label
        self.kind = kind
        self.members = members
        self.by_name: dict[str, list[_Member]] = {}
        for member in members:
            self.by_name.setdefault(member.name.lower(), []).append(member)
        self._cache: dict[str, bytes] = {}

    def names(self) -> list[str]:
        return [occ[0].name for occ in self.by_name.values()]

    def has(self, name: str) -> bool:
        return name.lower() in self.by_name

    def read(self, name: str) -> bytes:
        key = name.lower()
        if key not in self._cache:
            self._cache[key] = self.by_name[key][0].read()
        return self._cache[key]

    def display(self, name: str) -> str:
        return f"{self.label}!{name}" if self.kind == "pak" else f"{self.label}/{name}"

    def member_of(self, path: str) -> str:
        """The mod-root member path of a displayed path (inverse of :meth:`display`), lower case."""
        prefix = self.label + ("!" if self.kind == "pak" else "/")
        return (path[len(prefix):] if path.startswith(prefix) else path).lower()


def _open_pak(path: Path) -> Bundle:
    archive = zipfile.ZipFile(path)
    members = []
    seen: dict[str, int] = {}
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = info.filename.replace("\\", "/")
        occurrence = seen.get(name.lower(), 0)
        seen[name.lower()] = occurrence + 1
        members.append(_Member(name, (lambda i=info: archive.read(i)), occurrence))
    return Bundle(path.name, "pak", members)


SKIP_DIRS = {".git", ".venv", "__pycache__", "intermediate"}


def _open_folder(path: Path) -> Bundle:
    root = path / "mods_source" if (path / "mods_source").is_dir() else path
    members = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for filename in sorted(filenames):
            full = Path(dirpath) / filename
            rel = full.relative_to(root).as_posix()
            members.append(_Member(rel, (lambda f=full: f.read_bytes())))
    label = root.as_posix()
    return Bundle(label, "folder", members)


def open_target(target: str | Path) -> Bundle:
    path = Path(target)
    if path.is_dir():
        return _open_folder(path)
    if path.is_file() and zipfile.is_zipfile(path):
        return _open_pak(path)
    raise ValueError(f"not a mod folder or a .pak: {target}")


# ------------------------------------------------------------------------------------------------ retail

class Retail:
    """Read-only view of the retail paks (client paks + the retail BRO pak) by lower-case member path."""

    def __init__(self, game_root: Path) -> None:
        self.game_root = game_root
        index = retail._index(game_root)
        self.names = {name.lower(): name for name in index}
        self.stems: dict[tuple[str, str], str] = {}
        for lower, name in self.names.items():
            base = lower.rsplit("/", 1)[-1]
            stem, dot, ext = base.partition(".")
            if dot:
                self.stems.setdefault((stem, "." + ext), name)
        self._cache: dict[str, bytes] = {}

    def has(self, name: str) -> bool:
        return name.lower() in self.names

    def read(self, name: str) -> bytes:
        key = name.lower()
        if key not in self._cache:
            self._cache[key] = retail.read_member(self.game_root, self.names[key])
        return self._cache[key]


# ------------------------------------------------------------------------------------------------ context

_EXPONENT = re.compile(r"^[-+]?\d+(\.\d*)?[eE][-+]?\d")


# ------------------------------------------------------------------------------------------------ read fields (RC072)

DATA_DIR = Path(__file__).with_name("data")
READ_FIELDS_FILE = DATA_DIR / "read_fields.json"
READ_FIELDS_LOCAL = DATA_DIR / "read_fields_local.json"
_STATIC = "code analysis, static"
_GLOB = "glob:"
# Families whose table readers list every key they look up (the generated native tplMARKUP readers,
# read_fields.md 1).  .ssl/.prop readers come from native binding tables only; SSL code reads the rest, so a
# key missing from their lists proves nothing and the "not in the reads list" info is not raised for them.
EXHAUSTIVE_FAMILIES = (".tpl_markup::", ".obj_settings::", "!global::")


@dataclass
class Condition:
    """A key ignored only for some values of another key (read_fields.json ``conditional``).

    ``when`` maps a gate to a value: ``{"massFromDensity": true}`` (a sibling key, equality) or
    ``{"/objSettings.exportedVersion": {"notIn": [3, "OBJ_SETTINGS_EXPORT_VER_MOD_EDITOR"], "default": 0}}``
    (a leading ``/`` = a dotted path from the file root; operators ``eq``, ``ne``, ``in``, ``notIn``, ``lt``,
    ``le``, ``gt``, ``ge``; ``default`` = the value when the gate key is absent, else the reader's default for
    a sibling).  ``aggregate`` ``file`` reports one finding per file instead of one per occurrence."""
    key: str
    when: dict[str, Any]
    why: str = ""
    evidence: str = ""
    fixHint: str = ""               # noqa: N815
    severity: str = "warning"
    aggregate: str = ""
    status: str = ""


@dataclass
class Reader:
    """One native/SSL reader of a type: the keys it reads, keys known to be present but never read, and
    conditionally ignored keys.

    ``type_key`` names the type (``.ssl::WheelParticleMaterialSettings``, or the short ``WheelParticleMaterialSettings``;
    ``*`` = any type); the reader also applies to subtypes (the schema chain).  The research file's ``context``
    and ``match`` are descriptions; only a ``match`` written ``glob:<pattern>`` restricts by fnmatch on the
    section's key path with indices normalised (``a.b[].c``)."""
    type_key: str
    match: str = ""
    reads: dict[str, dict] = field(default_factory=dict)
    ignored: dict[str, dict] = field(default_factory=dict)
    conditions: dict[str, Condition] = field(default_factory=dict)
    address: str = ""
    grade: str = ""
    source: str = ""
    exhaustive: bool | None = None  # reads lists every key looked up; None = by family (EXHAUSTIVE_FAMILIES)

    def complete(self) -> bool:
        return self.exhaustive if self.exhaustive is not None else self.type_key.startswith(EXHAUSTIVE_FAMILIES)

    def applies(self, chain: list[str], key_path: str) -> bool:
        if self.type_key not in ("", "*"):
            names = set(chain) | {t.split("::", 1)[-1] for t in chain}
            if self.type_key not in names:
                return False
        if self.match.startswith(_GLOB):
            return fnmatch.fnmatchcase(normalise_key(key_path), self.match[len(_GLOB):])
        return True

    def evidence(self, extra: str = "") -> str:
        parts = [_STATIC + (f" ({self.grade})" if self.grade else "")]
        if self.address:
            parts.append(self.address)
        if extra and extra != self.address:
            parts.append(extra)
        if self.source:
            parts.append(self.source)
        return "; ".join(parts)


# Code-confirmed present-but-ignored keys (C:/RC_RE/research/physics_semantics.md T5, T7 and Follow-up F1).  They
# hold whether or not data/read_fields.json is present, and retail carrying the same dead keys (2,235 wheel
# spreadAngle, 52 lowRangeMultiplier, position-motor spring) does not make them live.
BUILTIN_READERS = [
    Reader("tpl_markup_position_motor", address="FUN_141594b60", grade="C", source="physics_semantics.md T5",
           ignored={"spring": {
               "keepWarning": True,
               "why": "the position-motor reader reads tau, damping, maxForce and the two recovery velocities only; "
                      "`spring` is never read, so the motor runs on its tau",
               "fixHint": "move `spring` to a tpl_markup_spring_motor {spring, damping} on this constraint (true "
                          "N/m or N*m/rad; it reads only those two, default 0, unlimited force), with the joint "
                          "limits as end stops"}}),
    Reader("*", address="no reader: the string is in neither exe and TruckGearboxParams (truck_components.ssl) "
                        "does not declare it", grade="C", source="physics_semantics.md F1",
           ignored={"lowRangeMultiplier": {
               "why": "`lowRangeMultiplier` is read by nothing; retail carries it dead in TruckGearboxParams "
                      "(only the debug UI scales low range, via SetLowRangeGearMultiplier)",
               "fixHint": "lowRangeMultiplier is read by nothing (retail carries it dead); low range is lowRangeGear "
                          "(set lowRangeGear.angularVelocity for the speed cap)"}}),
    Reader("WheelParticleMaterialSettings", address="FUN_140cbbfe0", grade="C", source="physics_semantics.md F1",
           ignored={"spreadAngle": {
               "why": "WheelParticleMaterialSettings is registered by FUN_140cbbfe0 without `spreadAngle`; only "
                      "TrackParticleMaterialSettings (FUN_140cbbdb0) reads it",
               "fixHint": "spreadAngle is only read under TrackParticleMaterialSettings; "
                          "WheelParticleMaterialSettings uses spreadAngleProb"}}),
]


def _merge_spec(old: dict | None, new: dict) -> dict:
    out = dict(old or {})
    out.update({k: v for k, v in new.items() if v not in (None, "")})
    return out


class ReadFields:
    """Reader tables for RC072: the built-in code-confirmed cases, then data/read_fields.json (the research
    file, copied unchanged) and data/read_fields_local.json (validator-side additions: fix hints, interim
    rules) when present.  Later sources refine earlier ones key by key.

    Accepted shapes: the research schema ``{"schemaVersion": 1, "readers": [{"context", "typeKey", "match",
    "reads": [{"key", "default", "notes"}], "ignoredKnown": [{"key", "why", "evidence"}], "conditional":
    [{"key", "ignoredWhen"}], "address", "grade"}], "ignoredKeys": {typeKey: {key: why}}, "conditional":
    {typeKey: [{"key", "ignoredWhen", ...}]}}``, and a legacy ``{type key: [fields read]}`` mapping."""

    def __init__(self, readers: list[Reader] | None = None, *, table_loaded: bool = False, note: str = "",
                 gated: dict | None = None) -> None:
        self.readers = list(BUILTIN_READERS) + list(readers or [])
        self.table_loaded = table_loaded
        self.note = note
        self.gated = gated if isinstance(gated, dict) else None     # read_fields.json "gated" (objSettings, RC074)

    # ---- loading
    @staticmethod
    def parse(data: Any, source: str = "") -> list[Reader]:
        label = posixpath.basename(source.replace("\\", "/")) if source else ""
        readers: list[Reader] = []
        if not isinstance(data, dict):
            raise ValueError(f"{source or 'read fields'}: expected a JSON object")
        if "readers" in data or "ignoredKeys" in data or "conditional" in data:
            version = data.get("schemaVersion")
            if version != 1:
                raise ValueError(f"{source or 'read fields'}: schemaVersion {version!r} is not supported (1)")
            by_type: dict[str, Reader] = {}
            for index, item in enumerate(data.get("readers") or []):
                if not isinstance(item, dict):
                    raise ValueError(f"{source}: readers[{index}] is not an object")
                type_key = str(item.get("typeKey") or item.get("context") or "*")
                conditional_keys = {c.get("key") for c in item.get("conditional") or [] if isinstance(c, dict)}
                reads = {r["key"]: r for r in item.get("reads") or [] if isinstance(r, dict) and r.get("key")}
                ignored, conditions = {}, {}
                for r in item.get("ignoredKnown") or []:
                    if not (isinstance(r, dict) and r.get("key")):
                        continue
                    if r["key"] in conditional_keys:      # described here, applied only under its condition
                        conditions[r["key"]] = Condition(r["key"], {}, str(r.get("why") or ""),
                                                         str(r.get("evidence") or ""))
                    else:
                        ignored[r["key"]] = r
                match = str(item.get("match") or "")
                reader = Reader(type_key, match if match.startswith(_GLOB) else "", reads, ignored, conditions,
                                str(item.get("address") or ""), _grade(item.get("grade")), label,
                                item["exhaustive"] if isinstance(item.get("exhaustive"), bool) else None)
                for c in item.get("conditional") or []:
                    _add_condition(reader, c)
                readers.append(reader)
                by_type.setdefault(type_key, reader)
            for type_key, keys in (data.get("ignoredKeys") or {}).items():
                reader = by_type.get(type_key) or _new(readers, by_type, type_key, label)
                for key, why in (keys or {}).items():
                    if key not in reader.conditions:
                        spec = why if isinstance(why, dict) else {"why": str(why)}
                        reader.ignored[key] = _merge_spec(reader.ignored.get(key), spec)
            for type_key, entries in (data.get("conditional") or {}).items():
                reader = by_type.get(type_key) or _new(readers, by_type, type_key, label)
                for c in entries or []:
                    _add_condition(reader, c)
                    reader.ignored.pop(c.get("key"), None) if isinstance(c, dict) else None
        else:
            for type_key, keys in data.items():
                if isinstance(keys, (list, tuple, set, frozenset)):
                    readers.append(Reader(type_key, reads={k: {} for k in keys}, source=label, exhaustive=True))
        return readers

    @classmethod
    def from_data(cls, data: Any, source: str = "") -> "ReadFields":
        readers = cls.parse(data, source)
        return cls(readers, table_loaded=True, gated=data.get("gated"),
                   note=f"RC072 reader table: {source or 'in-memory'} "
                                                    f"({len(readers)} readers) + {len(BUILTIN_READERS)} built-in cases")

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ReadFields":
        """``path`` (or ROADCRAFT_READ_FIELDS, or data/read_fields.json, plus data/read_fields_local.json).  An
        absent default file disables the table-driven part with a note; the built-in cases still run."""
        explicit = path or os.environ.get("ROADCRAFT_READ_FIELDS")
        target = Path(explicit) if explicit else READ_FIELDS_FILE
        readers: list[Reader] = []
        notes = []
        gated = None
        if target.is_file():
            data = json.loads(target.read_text(encoding="utf-8"))
            readers += cls.parse(data, str(target))
            gated = data.get("gated") if isinstance(data, dict) else None
            notes.append(f"{target.name} ({len(readers)} readers)")
        elif explicit:
            raise FileNotFoundError(f"read-fields table not found: {target}")
        if not explicit and READ_FIELDS_LOCAL.is_file() and readers:
            local = cls.parse(json.loads(READ_FIELDS_LOCAL.read_text(encoding="utf-8")), str(READ_FIELDS_LOCAL))
            readers += local
            notes.append(f"{READ_FIELDS_LOCAL.name} ({len(local)} readers)")
        if not readers:
            return cls(note=f"RC072 reader table {target.name} not present (src/roadcraft/data): the table-driven "
                            f"check is disabled; only the {len(BUILTIN_READERS)} built-in code-confirmed cases "
                            "(position-motor spring, lowRangeMultiplier, wheel-particle spreadAngle) run")
        return cls(readers, table_loaded=True, gated=gated,
                   note="RC072 reader table: " + " + ".join(notes) + f" + {len(BUILTIN_READERS)} built-in cases")

    # ---- queries
    def applicable(self, chain: list[str], section_path: str) -> list[Reader]:
        return [r for r in self.readers if r.applies(chain, section_path)]

    def ignored(self, chain: list[str] | str, key: str, section_path: str) -> tuple[Reader, dict] | None:
        """(reader, merged spec) when ``key`` is unconditionally ignored here; the reader cited is the last one
        with an address, the spec merges every source (later ones refine the text and add fix hints)."""
        chain = [chain] if isinstance(chain, str) else chain
        hits = [r for r in self.applicable(chain, section_path) if key in r.ignored]
        if not hits:
            return None
        spec: dict = {}
        for reader in hits:
            spec = _merge_spec(spec, reader.ignored[key])
        cited = next((r for r in reversed(hits) if r.address), hits[-1])
        return cited, spec

    def condition(self, chain: list[str], key: str, section_path: str) -> tuple[Reader, Condition] | None:
        """(reader, merged condition) when ``key`` is ignored only for some values of a gate key."""
        hits = [r for r in self.applicable(chain, section_path) if key in r.conditions]
        merged: Condition | None = None
        for reader in hits:
            merged = reader.conditions[key] if merged is None else _merge_condition(merged, reader.conditions[key])
        if merged is None or not merged.when:
            return None
        cited = next((r for r in reversed(hits) if r.address), hits[-1])
        return cited, merged

    def reads(self, chain: list[str], section_path: str) -> set[str]:
        """Keys a table reader of this type (or a parent) reads: schema gaps such as TplObjSettingsGeom.lighting."""
        out: set[str] = set()
        for reader in self.applicable(chain, section_path):
            if reader not in BUILTIN_READERS:
                out.update(reader.reads)
        return out

    def default(self, chain: list[str], key: str) -> Any:
        for reader in self.applicable(chain, ""):
            spec = reader.reads.get(key)
            if isinstance(spec, dict) and "default" in spec:
                return spec["default"]
        return None

    def unread(self, chain: list[str] | str, key: str, section_path: str) -> Reader | None:
        """A table reader of this type with a reads list that lacks ``key`` (and no reader of it reads it)."""
        chain = [chain] if isinstance(chain, str) else chain
        candidates = [r for r in self.applicable(chain, section_path)
                      if r.reads and r.complete() and r not in BUILTIN_READERS]
        if not candidates or any(key in r.reads for r in candidates):
            return None
        return candidates[0]

    def global_ignored(self) -> dict[str, tuple[Reader, dict]]:
        """Keys ignored under every type (``*``), checked on every document, typed or not."""
        out = {}
        for reader in self.readers:
            if reader.type_key in ("", "*") and not reader.match:
                for key, spec in reader.ignored.items():
                    out[key] = (reader, _merge_spec(out.get(key, (None, {}))[1], spec))
        return out


def _grade(value: Any) -> str:
    text = str(value or "")
    return {"Confirmed-from-code": "C", "Inferred": "I", "Unknown": "U"}.get(text, text)


def _new(readers: list[Reader], by_type: dict[str, Reader], type_key: str, label: str) -> Reader:
    reader = Reader(type_key, source=label)
    readers.append(reader)
    by_type[type_key] = reader
    return reader


def _add_condition(reader: Reader, item: Any) -> None:
    if not (isinstance(item, dict) and item.get("key") and isinstance(item.get("ignoredWhen", {}), dict)):
        return
    old = reader.conditions.get(item["key"])
    new = Condition(item["key"], dict(item.get("ignoredWhen") or {}), str(item.get("why") or ""),
                    str(item.get("evidence") or ""), str(item.get("fixHint") or ""),
                    str(item.get("severity") or "warning"), str(item.get("aggregate") or ""),
                    str(item.get("status") or ""))
    reader.conditions[item["key"]] = _merge_condition(old, new) if old else new


def _merge_condition(old: Condition, new: Condition) -> Condition:
    return Condition(old.key, new.when or old.when, new.why or old.why, new.evidence or old.evidence,
                     new.fixHint or old.fixHint, new.severity if new.when else old.severity,
                     new.aggregate or old.aggregate, new.status or old.status)


_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda a, b: a == b, "ne": lambda a, b: a != b,
    "in": lambda a, b: a in b, "notIn": lambda a, b: a not in b,
    "lt": lambda a, b: _num(a) is not None and _num(a) < b, "le": lambda a, b: _num(a) is not None and _num(a) <= b,
    "gt": lambda a, b: _num(a) is not None and _num(a) > b, "ge": lambda a, b: _num(a) is not None and _num(a) >= b,
}


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def condition_holds(cond: Condition, section: dict, root: Any, default_of: Callable[[str], Any]) -> bool | None:
    """True when every gate of ``cond`` says the key is ignored; None when a gate value is unknown."""
    for gate, expected in cond.when.items():
        spec = expected if isinstance(expected, dict) and any(op in expected for op in _OPS) else {"eq": expected}
        if gate.startswith("/"):
            value: Any = root
            for part in gate[1:].split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if value is None:
                value = spec.get("default")
        else:
            value = section.get(gate) if gate in section else spec.get("default", default_of(gate))
        if value is None:
            return None
        for op, operand in spec.items():
            if op in _OPS and not _OPS[op](value, operand):
                return False
    return True


RETAIL_IGNORED_FILE = DATA_DIR / "retail_ignored_counts.json"
_retail_ignored: dict[str, dict] | None = None


def retail_ignored() -> dict[str, dict]:
    """``"<type key>|<key>" -> {"occurrences", "files"}``: RC072 keys retail content carries the same way
    (data/retail_ignored_counts.json, made by :func:`count_retail_ignored`); empty when the file is absent."""
    global _retail_ignored
    if _retail_ignored is None:
        try:
            _retail_ignored = json.loads(RETAIL_IGNORED_FILE.read_text(encoding="utf-8")).get("counts") or {}
        except (OSError, ValueError):
            _retail_ignored = {}
    return _retail_ignored


def dead_key_severity(type_key: str, key: str, severity: str, spec: dict | None = None) -> tuple[str, str]:
    """RC072 severity and message note.  A dead key that retail carries at the same type is info: retail's own
    value is equally inert, so the author lost nothing.  ``keepWarning`` in the reader spec (position-motor
    ``spring``, where the author clearly expected a spring) keeps the warning."""
    counts = retail_ignored()
    if type_key == "*":
        hits = [v for k, v in counts.items() if k.endswith("|" + key)]
    else:
        hits = [counts[f"{type_key}|{key}"]] if f"{type_key}|{key}" in counts else []
    total = sum(int(h.get("occurrences", 0)) for h in hits)
    if not total:
        return severity, ""
    note = f"; retail carries it too ({total} retail occurrences)"
    if (spec or {}).get("keepWarning"):
        return severity, note
    return ("info" if severity == "warning" else severity), note + "; harmless unless you expected it to do something"


def normalise_key(key: str) -> str:
    """A key path with list indices removed: ``objectInfos[3].entities[0].motor`` -> ``objectInfos[].entities[].motor``."""
    return re.sub(r"\[\d+\]", "[]", key or "")


class Context:
    def __init__(self, bundle: Bundle, retail_view: Retail | None, schema: schema_mod.Schema | None,
                 rules: set[str], read_fields: ReadFields | None = None) -> None:
        self.bundle = bundle
        self.retail = retail_view
        self.schema = schema
        self.rules = rules
        self.read_fields = read_fields or ReadFields()
        self.game_root: Path | None = None
        self.findings: list[Finding] = []
        self._docs: dict[tuple[str, str], Any] = {}
        self._nodes: dict[str, TplNodes | None] = {}
        self._stems: dict[tuple[str, str], str] = {}
        for name in bundle.names():
            base = name.lower().rsplit("/", 1)[-1]
            stem, dot, ext = base.partition(".")
            if dot:
                self._stems.setdefault((stem, "." + ext), name)
        self._instance_types: dict[str, Any] = {}
        self._sso_classes: set[str] | None = None

    def sso_classes(self) -> set[str]:
        """SSL class names of every mod and retail ``.sso`` file (SSLUtils.ConvertBrandToClassName)."""
        if self._sso_classes is None:
            stems = [s for s, e in self._stems if e == ".sso"]
            if self.retail is not None:
                stems += [s for s, e in self.retail.stems if e == ".sso"]
            self._sso_classes = {schema_mod.brand_class_name(s) for s in stems}
        return self._sso_classes

    # ---- reporting
    def add(self, code: str, severity: str, path: str, message: str, *, line: int | None = None, key: str = "",
            evidence: str | None = None, fix: str = "") -> None:
        rule = CODES[code][0] if code in CODES else "bro-lint"
        if rule not in self.rules:
            return
        self.findings.append(Finding(rule, severity, path, line, message, evidence or CODES[code][2], code, key,
                                     fix))

    # ---- files
    def source_of(self, name: str) -> str | None:
        """'mod' or 'retail' for a member path, None if neither has it."""
        if self.bundle.has(name):
            return "mod"
        if self.retail is not None and self.retail.has(name):
            return "retail"
        return None

    def read(self, name: str) -> bytes | None:
        if self.bundle.has(name):
            return self.bundle.read(name)
        if self.retail is not None and self.retail.has(name):
            return self.retail.read(name)
        return None

    def find_stem(self, stem: str, ext: str) -> str | None:
        """A member named ``<stem><ext>`` anywhere in the mod, else in retail (case-insensitive)."""
        key = (stem.lower(), ext.lower())
        if key in self._stems:
            return self._stems[key]
        if self.retail is not None and key in self.retail.stems:
            return self.retail.stems[key]
        return None

    def ps(self, name: str, report: bool = False) -> Any:
        """Editor-parsed PS document of a member (mod first, then retail), None when absent or unparsable."""
        origin = self.source_of(name)
        if origin is None:
            return None
        cache_key = (origin, name.lower())
        if cache_key in self._docs:
            return self._docs[cache_key]
        data = self.read(name) or b""
        text = data.decode("utf-8-sig", errors="replace")
        warnings: list[tuple[str, int, str]] = []
        try:
            doc = ps_format.editor_loads(text, warn=lambda kind, line, detail: warnings.append((kind, line, detail)))
        except ps_format.EditorParseError as exc:
            doc = None
            if report and origin == "mod":
                self.add("RC049", "error", self.bundle.display(name), f"the Mod Editor cannot parse this file: {exc}",
                         line=exc.line)
        if report and origin == "mod":
            self._number_findings(name, warnings)
        self._docs[cache_key] = doc
        return doc

    def _number_findings(self, name: str, warnings: list[tuple[str, int, str]]) -> None:
        path = self.bundle.display(name)
        for kind, line, detail in warnings:
            if kind == "number_followed_by_letters":
                exp = bool(_EXPONENT.match(detail))
                token = detail.split()[0].rstrip(",]}")
                self.add("RC050", "error", path,
                         (f"exponent notation {token!r}: the editor reads the number up to 'e' and then a "
                          "new key (a parse error; inside [ ] the value silently becomes [n, \"e\", m]); write it in "
                          "full decimal") if exp else
                         f"{token!r}: a number followed by letters splits into a number and a new key",
                         line=line,
                         fix=f"write {_full_decimal(token)} instead of {token}" if exp and _full_decimal(token) else "")
            elif kind == "leading_dot_number":
                text = detail.split()[0].rstrip(",]}")
                fixed = text.replace(".", "0.", 1) if not text.startswith(("-", "+")) else text[0] + "0" + text[1:]
                self.add("RC051", "error", path,
                         f"{text!r} is read by the editor as {_leading_dot_value(text)!r}: write a 0 before the point",
                         line=line, fix=f"write {fixed} instead of {text}")
            elif kind == "bare_bool_keyword":
                self.add("RC052", "warning", path,
                         f"bare {detail!r} is read as the bool {detail.lower() in ('on', 'yes')}; quote it if a "
                         "string or enum value was meant", line=line,
                         fix=f'write "{detail}" (quoted) if a string or enum value was meant')

    def nodes(self, tpl_name: str | None, anchor: str | None = None) -> TplNodes | None:
        """Node table of the compiled model ``<name>.tpl`` (mod first, then retail); ``anchor`` is a node name
        that selects the right name table (tpl_reader.read_nodes)."""
        if not tpl_name:
            return None
        key = f"{tpl_name.lower()}|{anchor or ''}"
        if key not in self._nodes:
            member = self.find_stem(tpl_name, ".tpl")
            nodes = None
            if member is not None:
                data = self.read(member) or b""
                try:
                    nodes = read_tpl_bytes(data, anchor=anchor, parents=False)
                except (TplFormatError, ValueError, IndexError):
                    nodes = None
                try:
                    nodes = nodes or read_tpl_bytes(data, parents=False)
                except (TplFormatError, ValueError, IndexError):
                    nodes = None
            self._nodes[key] = nodes
        return self._nodes[key]

    def tpl_bytes(self, tpl_name: str | None) -> bytes | None:
        member = self.find_stem(tpl_name, ".tpl") if tpl_name else None
        return self.read(member) if member else None

    def tree(self, tpl_name: str | None) -> TplNodes | None:
        """Like :meth:`nodes`, with the parent array located (tpl_reader.find_parents); slower, so callers ask
        for it only when they need the node tree.  None when the model or its parent array is not found."""
        if not tpl_name:
            return None
        key = f"tree|{tpl_name.lower()}"
        if key not in self._nodes:
            data = self.tpl_bytes(tpl_name)
            nodes = None
            if data:
                try:
                    nodes = read_tpl_bytes(data, parents=True)
                except (TplFormatError, ValueError, IndexError):
                    nodes = None
            self._nodes[key] = nodes if nodes is not None and nodes.parents is not None else None
        return self._nodes[key]

    def markup(self, tpl_name: str | None) -> tuple[Any, str | None]:
        """Effective markup of a model: ``tpl/X.lods_base`` with ``X.tpl_markup`` merged on top (schema.md 4.1)."""
        if not tpl_name:
            return None, None
        markup_name = self.find_stem(tpl_name, ".tpl_markup")
        base_name = self.find_stem(tpl_name, ".lods_base")
        markup = self.ps(markup_name) if markup_name else None
        base = self.ps(base_name) if base_name else None
        if markup is None and base is None:
            return None, markup_name
        merged = schema_mod._clone(base) if isinstance(base, dict) else {}
        if isinstance(markup, dict):
            schema_mod.saber_merge(merged, markup)
        return merged, markup_name


def _full_decimal(token: str) -> str:
    """``1e-05`` -> ``0.00001`` (the exponent-free spelling the editor parses), '' when not a number."""
    from decimal import Decimal, InvalidOperation
    try:
        value = Decimal(token.rstrip(",]}"))
    except InvalidOperation:
        return ""
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _leading_dot_value(text: str) -> float:
    try:
        return ps_format.editor_loads("v = " + text, lines=False)["v"]
    except ps_format.PsSyntaxError:
        return 0.0


# ------------------------------------------------------------------------------------------------ rule: PS numbers

def rule_ps(ctx: Context) -> None:
    for name in ctx.bundle.names():
        if name.lower().endswith(PS_EXTENSIONS) and not name.lower().endswith("res_cnv_options.ps"):
            ctx.ps(name, report=True)


# ------------------------------------------------------------------------------------------------ rule: unknown keys

# Keys the SDK schema lacks but retail content ships (the meta descs lag the game build), collected by running
# RC053 over every retail truck class, vehicle markup and retail BRO on 2026-10-13 (data/retail_unknown_keys.json;
# library/validator.md "False positives").  Not reported: a key retail ships cannot be shown to break anything.
RETAIL_KEYS: dict[str, frozenset[str]] = {
    key: frozenset(names) for key, names in json.loads(
        (Path(__file__).with_name("data") / "retail_unknown_keys.json").read_text(encoding="utf-8"))["keys"].items()}
_OPAQUE = "opaque"


class _TypeWalker:
    """Walks a parsed PS document against the schema like DefaultModelTreeSerializer (schema.md 7.1)."""

    def __init__(self, ctx: Context, name: str) -> None:
        self.ctx = ctx
        self.schema = ctx.schema
        self.name = name
        self.path = ctx.bundle.display(name)
        self.aggregated: dict[tuple[str, str], dict] = {}

    def resolve(self, type_name: Any, ns: str | None) -> tuple[str | None, set[str]]:
        """Schema type key (or _OPAQUE) for a ``__type`` / element name, plus extra keys an instance file allows."""
        if not isinstance(type_name, str) or not type_name:
            return None, set()
        if type_name in schema_mod.BUILTIN or type_name.startswith("local__"):
            return _OPAQUE, set()          # builtin kinds and a field's own __types (local__xxx)
        key = self.schema.find(type_name, ns or SSL_FALLBACK)
        if key is not None:
            return key, set()
        found = self.instance_type(type_name, ns)
        if found[0] is None:
            key = self.schema.find(type_name, None)
            if key is not None:
                return key, set()
        return found

    def instance_type(self, type_name: str, ns: str | None) -> tuple[str | None, set[str]]:
        """A type defined by a file (mod or retail), as ClassPakParser/DefaultFileParser register them."""
        cache = self.ctx._instance_types
        cache_key = f"{ns}|{type_name}"
        if cache_key in cache:
            return cache[cache_key]
        cache[cache_key] = (None, set())          # cycle guard
        result: tuple[str | None, set[str]] = (None, set())
        exts = [ns] if ns and ns != ".ssl" else []
        exts += [e for e in (".cls", ".prop", ".sso", ".tpl_markup") if e not in exts]
        for ext in exts:
            member = self.ctx.find_stem(type_name, ext)
            if member is None:
                continue
            doc = self.ctx.ps(member)
            if not isinstance(doc, dict) or "#ssl" in doc:
                result = (_OPAQUE, set())
                break
            parent = doc.get("__type")
            if parent:
                key, extra = self.resolve(parent, ext)
            else:
                root = schema_mod.FAMILY_ROOTS.get(ext)
                key, extra = (self.schema.find(root, ext), set()) if root else (_OPAQUE, set())
            result = (key, extra | {k for k in doc if not k.startswith("__")})
            break
        else:
            # an SSL class registered from a mod/retail .sso file (BrandToClassName), e.g. AutoXxxReplicated
            if type_name in self.ctx.sso_classes():
                result = (_OPAQUE, set())
        cache[cache_key] = result
        return result

    # ---- walking
    def chain(self, type_key: str) -> list[str]:
        try:
            chain = list(self.schema.chain(type_key)) if self.schema is not None else []
        except (KeyError, ValueError, AttributeError):
            chain = []
        return [type_key] + [t for t in chain if t != type_key]

    def check_members(self, section: dict, type_key: str, path: str, extra: set[str]) -> None:
        schema = self.schema
        fields = self.ctx.read_fields
        chain = self.chain(type_key)
        owners = {name: type_key for name in schema.member_names(type_key)}
        family = type_key.split("::", 1)[0]
        root = schema.find(schema_mod.FAMILY_ROOTS[family], family) if family in schema_mod.FAMILY_ROOTS else None
        if root and root != type_key:
            # a .cls/.prop/.sso instance also keeps its family root's members (iactor.properties; __useSslClassByBrand)
            for name in schema.member_names(root):
                owners.setdefault(name, root)
        names = set(owners)
        table_reads = fields.reads(chain, path)          # keys the exe reads that the schema lacks (schema gaps)
        allowed = names | extra | RETAIL_KEYS.get(type_key, frozenset()) | table_reads
        lines = getattr(section, "lines", {})
        for key, value in section.items():
            if key.startswith("__") or key in ("", "#ssl"):
                continue
            here = f"{path}.{key}" if path else key
            line = lines.get(key)
            # RC072 first: a key that code shows is never read is reported even when retail ships it too
            # (data/retail_unknown_keys.json only says retail carries it, not that anything reads it)
            known = fields.ignored(chain, key, path)
            if known is not None:
                reader, spec = known
                severity, note = dead_key_severity(type_key, key, "warning", spec)
                self.ctx.add("RC072", severity, self.path,
                             f"{type_key}.{key} is present but ignored: {spec.get('why') or 'not read by the reader'}"
                             + note, line=line, key=here, fix=spec.get("fixHint", ""),
                             evidence=reader.evidence(str(spec.get("evidence") or "")))
                continue
            conditional = fields.condition(chain, key, path)
            if conditional is not None:
                self.check_condition(conditional, section, chain, type_key, key, here, line)
            if key not in allowed:
                hint = difflib.get_close_matches(key, sorted(names), n=1, cutoff=0.75)
                self.ctx.add("RC053", "warning", self.path,
                             f"{key!r} is not a field of {type_key}" + (f"; did you mean {hint[0]!r}?" if hint else "") +
                             " The editor keeps it as a 'removed field' hint and the engine is expected to ignore it.",
                             line=line, key=here, fix=f"rename {key!r} to {hint[0]!r}" if hint else "")
                continue
            reader = fields.unread(chain, key, path)
            if reader is not None and conditional is None:
                self.ctx.add("RC072", "info", self.path,
                             f"{type_key}.{key} is not in the reader's list of keys it reads"
                             + (f" ({reader.address})" if reader.address else "")
                             + "; a static reads list can be incomplete, so this is for review",
                             line=line, key=here, evidence=reader.evidence())
            if key not in names:
                continue
            fld = schema.field(owners[key], key)
            if fld is not None:
                self.check_value(value, fld, here, line, type_key.split("::", 1)[0])

    def check_condition(self, found: tuple[Reader, Condition], section: dict, chain: list[str], type_key: str,
                        key: str, here: str, line: int | None) -> None:
        reader, cond = found
        holds = condition_holds(cond, section, self.ctx.ps(self.name),
                                lambda gate: self.ctx.read_fields.default(chain, gate))
        if not holds:
            return
        gates = ", ".join(f"{g.lstrip('/')} {v}" for g, v in cond.when.items())
        why = cond.why or f"ignored when {gates}"
        status = f" ({cond.status})" if cond.status else ""
        evidence = reader.evidence(cond.evidence)
        if cond.aggregate == "file":
            group = self.aggregated.setdefault((type_key, key), {"cond": cond, "evidence": evidence, "keys": [],
                                                                 "line": line, "why": why + status})
            group["keys"].append(here)
            return
        severity, note = dead_key_severity(type_key, key, cond.severity if cond.severity in SEVERITIES else "warning")
        self.ctx.add("RC072", severity, self.path,
                     f"{type_key}.{key} has no effect here: {why}{status}{note}", line=line, key=here,
                     fix=cond.fixHint, evidence=evidence)

    def flush(self) -> None:
        """One RC072 per file and (type, key) for ``aggregate: file`` conditions, keyed by the pattern."""
        for (type_key, key), group in sorted(self.aggregated.items()):
            cond: Condition = group["cond"]
            keys = group["keys"]
            pattern = re.sub(r"\.[^.\[\]]+\.(?=" + re.escape(key) + r"$)", ".*.", keys[0])
            self.ctx.add("RC072", cond.severity if cond.severity in SEVERITIES else "info", self.path,
                         f"{type_key}.{key} on {len(keys)} object(s) ({', '.join(k for k in keys[:3])}"
                         f"{' ...' if len(keys) > 3 else ''}): {group['why']}", line=group["line"],
                         key=pattern, fix=cond.fixHint, evidence=group["evidence"])
        self.aggregated.clear()

    def check_value(self, value: Any, fld: dict, path: str, line: int | None, owner_ns: str) -> None:
        kind = fld.get("kind")
        ns = fld.get("namespace") or owner_ns
        if isinstance(value, dict):
            line = getattr(value, "line", None) or line
            if "__type" in value:
                key, extra = self.resolve(value["__type"], fld.get("ptr_family") or ns)
                if key is None:
                    self.ctx.add("RC054", "error", self.path,
                                 f"type {value['__type']!r} is not known to the editor schema, the mod or retail "
                                 "('Type not found')", line=line, key=path + ".__type")
                elif key != _OPAQUE:
                    self.check_members(value, key, path, extra)
                return
            if kind in ("collection", "exclusiveCollection", "uniformCollection"):
                self.check_collection(value, fld, path, ns)
                return
            if kind == "section" and fld.get("type") and fld["type"] not in schema_mod.BUILTIN:
                key, extra = self.resolve(fld["type"], ns)
                if key and key != _OPAQUE:
                    self.check_members(value, key, path, extra)
            return
        if isinstance(value, list):
            element = fld.get("element")
            if element:
                for index, item in enumerate(value):
                    self.check_value(item, element, f"{path}[{index}]", line, ns)
            return
        self.check_scalar(value, fld, path, line)

    def check_collection(self, value: dict, fld: dict, path: str, ns: str) -> None:
        family = fld.get("ptr_family") or ns
        is_components = family == ".prop" and fld.get("kind") == "exclusiveCollection"
        lines = getattr(value, "lines", {})
        for item_key, item in value.items():
            if item_key.startswith("__"):
                continue
            here = f"{path}.{item_key}"
            if not isinstance(item, dict) or "__value" in item:
                continue
            type_name = item.get("__type") or item_key
            key, extra = self.resolve(type_name, family)
            if key is None and "__type" not in item and not is_components:
                continue                       # a named item of the pointer type: nothing more to check here
            if key is None:
                self.ctx.add("RC054", "error", self.path,
                             (f"component {type_name!r} is not a known .prop type" if is_components else
                              f"type {type_name!r} not found") + " ('Type not found')",
                             line=lines.get(item_key), key=here)
            elif key != _OPAQUE:
                self.check_members(item, key, here, extra)

    def check_scalar(self, value: Any, fld: dict, path: str, line: int | None) -> None:
        kind = fld.get("kind")
        default = fld.get("default")
        shown_default = f" (schema default {default!r})" if "default" in fld else ""
        if kind == "enum":
            items = fld.get("enum_items") or []
            aliases = fld.get("enum_aliases") or {}
            if isinstance(value, bool):
                self.ctx.add("RC055", "error", self.path,
                             f"{path.rsplit('.', 1)[-1]} = {value} is a bare word read as a bool; allowed: {items}"
                             f"{shown_default}", line=line, key=path)
            elif isinstance(value, str) and items and value not in items and value not in aliases:
                hint = difflib.get_close_matches(value, [str(i) for i in items], n=1, cutoff=0.6)
                self.ctx.add("RC055", "error", self.path,
                             f"{value!r} is not allowed; allowed: {items}" + (f"; did you mean {hint[0]!r}?" if hint else "")
                             + shown_default, line=line, key=path,
                             fix=f"set {path.rsplit('.', 1)[-1]} = \"{hint[0]}\"" if hint else "")
        elif kind == "string" and isinstance(value, bool):
            self.ctx.add("RC056", "error", self.path,
                         f"a bare yes/no/on/off/true/false became the bool {value}; quote the string{shown_default}",
                         line=line, key=path, fix="quote the value as written (for example \"yes\")")
        elif kind == "bool" and isinstance(value, (int, float)) and not isinstance(value, bool) and value not in (0, 1):
            self.ctx.add("RC056", "error", self.path, f"{value!r} is not a bool{shown_default}", line=line, key=path,
                         fix="use True or False")
        elif kind == "bool" and isinstance(value, str) and value.lower() not in ("true", "false", "1", "0"):
            self.ctx.add("RC056", "error", self.path, f"{value!r} is not a bool{shown_default}", line=line, key=path,
                         fix="use True or False (unquoted)")
        elif kind in ("int", "float") and isinstance(value, str):
            try:
                float(value)
            except ValueError:
                self.ctx.add("RC056", "error", self.path, f"{value!r} is not a number{shown_default}",
                             line=line, key=path)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            low, high = fld.get("min"), fld.get("max")
            if isinstance(low, (int, float)) and not isinstance(low, bool) and value < low or \
                    isinstance(high, (int, float)) and not isinstance(high, bool) and value > high:
                units = f" {fld['units']}" if fld.get("units") else ""
                self.ctx.add("RC057", "info", self.path,
                             f"{value}{units} is outside the editor's range [{low}, {high}]{shown_default}; the range is "
                             "a UI hint and the value loads unchanged", line=line, key=path)


SSL_FALLBACK = ".ssl"


def rule_unknown_keys(ctx: Context) -> None:
    if ctx.schema is None:
        return
    for name in ctx.bundle.names():
        lower = name.lower()
        ext = "." + lower.rsplit("/", 1)[-1].partition(".")[2]
        if ext not in (".cls", ".prop", ".tpl_markup", ".bro"):
            continue
        doc = ctx.ps(name)
        if not isinstance(doc, dict) or "#ssl" in doc:
            continue
        walker = _TypeWalker(ctx, name)
        if ext == ".tpl_markup":
            stem = lower.rsplit("/", 1)[-1][: -len(".tpl_markup")]
            base_name = ctx.find_stem(stem, ".lods_base")
            base = ctx.ps(base_name) if base_name else None
            root_type = doc.get("__type") or (base.get("__type") if isinstance(base, dict) else None) or "tpl_markup"
            key, extra = walker.resolve(root_type, ".tpl_markup")
        elif ext == ".bro":
            if not doc.get("__type"):
                continue
            key, extra = walker.resolve(doc["__type"], ".bro")
        else:
            parent = doc.get("__type")
            if parent:
                key, extra = walker.resolve(parent, ext)
            else:
                key, extra = ctx.schema.find(schema_mod.FAMILY_ROOTS[ext], ext), set()
        if key is None and doc.get("__type"):
            ctx.add("RC054", "error", walker.path, f"root type {doc['__type']!r} not found ('Type not found')",
                    line=getattr(doc, "lines", {}).get("__type"), key="__type")
        elif key and key != _OPAQUE:
            walker.check_members(doc, key, "", extra)
        walker.flush()


def _walk_paths(value: Any, path: str = "") -> Iterator[tuple[str, str, Any, Any]]:
    """(section path, key, value, section) for every dict key of a parsed PS document, in the walker's
    key-path spelling (``a.b[2].c``)."""
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or key.startswith("__"):
                continue
            yield path, key, item, value
            yield from _walk_paths(item, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_paths(item, f"{path}[{index}]")


def _walk_dicts(value: Any, path: str = "") -> Iterator[tuple[str, dict]]:
    """(key path, dict) for every dict in a parsed PS document."""
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            if isinstance(key, str) and not key.startswith("__"):
                yield from _walk_dicts(item, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_dicts(item, f"{path}[{index}]")


def rule_ignored_global(ctx: Context) -> None:
    """RC072 for keys no reader of any type reads (``lowRangeMultiplier``), on every class/prop/BRO/markup the
    mod ships, typed or not and with or without the SDK schema; the typed walk (rule_unknown_keys) already
    reported the ones it reached."""
    if "ignored-fields" not in ctx.rules:
        return
    keys = ctx.read_fields.global_ignored()
    if not keys:
        return
    done = {(f.path, f.key) for f in ctx.findings if f.code == "RC072"}
    for name in ctx.bundle.names():
        if not name.lower().endswith((".cls", ".prop", ".bro", ".tpl_markup")):
            continue
        doc = ctx.ps(name)
        if not isinstance(doc, dict):
            continue
        path = ctx.bundle.display(name)
        for section_path, key, _value, section in _walk_paths(doc):
            if key not in keys:
                continue
            here = f"{section_path}.{key}" if section_path else key
            if (path, here) in done:
                continue
            reader, spec = keys[key]
            severity, note = dead_key_severity("*", key, "warning", spec)
            ctx.add("RC072", severity, path,
                    f"{key} is present but ignored: {spec.get('why') or 'read by nothing'}{note}",
                    line=getattr(section, "lines", {}).get(key), key=here, fix=spec.get("fixHint", ""),
                    evidence=reader.evidence(str(spec.get("evidence") or "")))


# Engine defaults of a markup physics body (FUN_1430811e0; physics_semantics.md F2): key -> (value, remark)
BODY_DEFAULTS = {
    "restitution": (0.4, "retail crawler markups (EPEC TC305, HT500) omit it too; against terrain (restitution "
                         "0) it never bounces, it matters only between dynamic bodies"),
    "friction": (0.5, ""),
    "angularDamping": (0.05, ""),
    "density": (600, "only used when massFromDensity is True (the default)"),
}


def rule_engine_defaults(ctx: Context) -> None:
    """RC073 (info): one finding per mod markup listing how many physics bodies leave restitution, friction,
    angularDamping or (with massFromDensity) density to the engine default."""
    if "engine-defaults" not in ctx.rules:
        return
    for name in ctx.bundle.names():
        lower = name.lower()
        if not lower.endswith(".tpl_markup"):
            continue
        stem = lower.rsplit("/", 1)[-1][: -len(".tpl_markup")]
        merged, _ = ctx.markup(stem)
        doc = merged if isinstance(merged, dict) else ctx.ps(name)
        if not isinstance(doc, dict):
            continue
        bodies = 0
        omitted: dict[str, list[str]] = {}
        for body_path, value in _walk_dicts(doc):
            if value.get("__type") != "tpl_markup_object_property_physics" or value.get("disable") is True:
                continue
            bodies += 1
            owner = _body_name(doc, body_path) or body_path
            for field_name in BODY_DEFAULTS:
                if field_name == "density" and value.get("massFromDensity", True) is False:
                    continue
                if field_name not in value:
                    omitted.setdefault(field_name, []).append(owner)
        if not omitted:
            continue
        parts = []
        for field_name, owners in omitted.items():
            default, remark = BODY_DEFAULTS[field_name]
            shown = ", ".join(owners[:3]) + (" ..." if len(owners) > 3 else "")
            parts.append(f"{field_name} -> {default} on {len(owners)}/{bodies} ({shown})"
                         + (f" [{remark}]" if remark else ""))
        ctx.add("RC073", "info", ctx.bundle.display(name),
                "physics bodies that omit a key get the engine default: " + "; ".join(parts)
                + ". Set the key in the body only where a different value is intended",
                key="objectInfos[].physicsBody")


# Exporter name prefixes that already hide an object (name_convention_config.json affixes with
# visibility_hidden: cdt_, hidden_) plus prefixes the desktop treats as hidden helpers (hp_, sfx_, leading _;
# no exporter rule found for them, read_fields.md 3a).  The config is re-read from the game root when present.
HIDDEN_PREFIXES_EXTRA = ("hp_", "sfx_", "_")
NAME_CONVENTION = Path("tools/bin/blender_to_usf_script/saber/blender/blender_to_usf/name_convention_config.json")


def hidden_prefixes(game_root: Path | None) -> tuple[str, ...]:
    found = {"cdt_", "hidden_"}
    config = (game_root / NAME_CONVENTION) if game_root else None
    if config is not None and config.is_file():
        try:
            affixes = json.loads(config.read_text(encoding="utf-8")).get("sys_affix_map") or {}
            found = {prefix for prefix, items in affixes.items()
                     if any(isinstance(i, dict) and "visibility_hidden" in i for i in items or [])} or found
        except (ValueError, OSError, AttributeError):
            pass
    return tuple(sorted(found)) + HIDDEN_PREFIXES_EXTRA


def _export_version(value: Any, enum: dict[str, int]) -> int | None:
    if value is None:
        return 0
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return enum.get(str(value))


def rule_objsettings(ctx: Context) -> None:
    """RC074: objSettings per-object entries are parsed but applied only from an exportedVersion threshold
    (read_fields.json ``gated``).  One info per markup summarising what is inert (and which entries name no
    node of the compiled model); a warning per node meant hidden (visibleDefault False) that renders because
    the visibility gate is closed and no exporter prefix hides it."""
    gated = ctx.read_fields.gated
    if "objsettings-gate" not in ctx.rules or not gated:
        return
    enum = {str(k): int(v) for k, v in (gated.get("enum") or {}).items()}
    names_by_value = {v: k for k, v in enum.items()}
    mins: dict[str, dict[str, int]] = gated.get("minExportedVersion") or {}
    geom = mins.get(".obj_settings::TplObjSettingsGeom") or {}
    prefixes = hidden_prefixes(ctx.game_root)
    for name in ctx.bundle.names():
        lower = name.lower()
        if not lower.endswith(".tpl_markup"):
            continue
        doc = ctx.ps(name)
        obj_settings = doc.get("objSettings") if isinstance(doc, dict) else None
        settings = obj_settings.get("settings") if isinstance(obj_settings, dict) else None
        if not isinstance(settings, dict) or not settings:
            continue
        raw = obj_settings.get("exportedVersion")
        version = _export_version(raw, enum)
        if version is None:
            continue                                   # unrecognised value: the enum reader leaves it at 0? Open
        stem = lower.rsplit("/", 1)[-1][: -len(".tpl_markup")]
        nodes = ctx.nodes(stem)
        path = ctx.bundle.display(name)
        inert: dict[str, int] = {}
        needed = 0
        stale: list[str] = []
        lines = getattr(settings, "lines", {})
        for obj, entry in settings.items():
            if not isinstance(entry, dict) or obj.startswith("__"):
                continue
            type_key = ".obj_settings::" + str(entry.get("__type") or "TplObjSettingsGeom")
            table = mins.get(type_key) or geom
            blocks = [k for k in entry if not k.startswith("__")]
            for block in blocks:
                need = max(1, int(table.get(block, 1)))
                if version < need:
                    inert[block] = inert.get(block, 0) + 1
                    needed = max(needed, need)
            if nodes is not None and not _has_node(nodes, obj):
                stale.append(obj)
                continue
            vis = entry.get("visibility")
            gate = int(table.get("visibility", 2))
            if isinstance(vis, dict) and vis.get("visibleDefault") is False and version < gate and nodes is not None \
                    and not obj.lower().startswith(prefixes):
                ctx.add("RC074", "warning", path,
                        f"intended hidden, actually visible: {obj} has visibleDefault=False but "
                        f"objSettings.exportedVersion is {'absent' if raw is None else repr(raw)}, so the engine "
                        "ignores it and the node renders", line=lines.get(obj),
                        key=f"objSettings.settings.{obj}.visibility.visibleDefault",
                        fix=f"add objSettings.exportedVersion = {names_by_value.get(gate, gate)} ({gate}) or higher, "
                            "or hide it by prefix/blueprint init")
        if not inert and not stale:
            continue
        counts = ", ".join(f"{block} {n}" for block, n in sorted(inert.items(), key=lambda kv: -kv[1]))
        gates = ", ".join(f"{block} needs >= {int(geom.get(block, 1))}" for block in sorted(inert) if block in geom)
        message = (f"objSettings per-object entries are parsed but inert: exportedVersion is "
                   f"{'absent (0)' if raw is None else f'{raw!r} ({version})'}"
                   + (f"; {sum(inert.values())} entries ({counts}) have no effect" if inert else "")
                   + (f"; {gates}" if gates else ""))
        if stale:
            message += (f"; stale entries, no effect (no such node in the compiled model): "
                        f"{', '.join(stale[:8])}{' ...' if len(stale) > 8 else ''}")
        elif nodes is None:
            message += "; the compiled model's node table was not readable, so stale entries are not checked"
        ctx.add("RC074", "info", path, message, line=getattr(obj_settings, "lines", {}).get("settings"),
                key="objSettings.settings",
                fix=(f"add objSettings.exportedVersion = {names_by_value.get(needed, needed)} if they are meant to "
                     "apply; check name prefixes (cdt_/hidden_) already give the intended result") if inert else "")


def _body_name(doc: dict, section_path: str) -> str | None:
    match = re.match(r"objectInfos\[(\d+)\]", section_path)
    infos = doc.get("objectInfos")
    if match and isinstance(infos, list) and int(match.group(1)) < len(infos):
        info = infos[int(match.group(1))]
        name = (info.get("objectId") or {}).get("name") if isinstance(info, dict) else None
        return name if isinstance(name, str) else None
    return None


# ------------------------------------------------------------------------------------------------ trucks

@dataclass
class Truck:
    name: str                       # member path of the class
    doc: dict
    props: dict
    rb: dict
    slots: list
    tpl: str | None
    nodes: TplNodes | None


def _merged_class(ctx: Context, name: str, depth: int = 0) -> dict | None:
    """A class with the ``properties`` of its ``__type`` parent classes merged under it (ClassPakParser)."""
    doc = ctx.ps(name)
    if not isinstance(doc, dict):
        return None
    parent = doc.get("__type")
    if isinstance(parent, str) and depth < 8:
        member = ctx.find_stem(parent, ".cls")
        if member is not None and member.lower() != name.lower():
            base = _merged_class(ctx, member, depth + 1)
            if isinstance(base, dict):
                merged = schema_mod._clone(base)
                schema_mod.saber_merge(merged, doc)
                return merged
    return doc


def trucks(ctx: Context) -> Iterator[Truck]:
    for name in ctx.bundle.names():
        if not name.lower().endswith(".cls"):
            continue
        data = ctx.bundle.read(name)
        if b"prop_truck_rb" not in data and b"__type" not in data:
            continue
        doc = _merged_class(ctx, name)
        props = (doc or {}).get("properties")
        rb = props.get("prop_truck_rb") if isinstance(props, dict) else None
        if not isinstance(rb, dict) or not rb.get("wheelSlotWithDescs"):
            continue
        tpl = (props.get("geom") or {}).get("nameTpl") if isinstance(props.get("geom"), dict) else None
        slots = list(rb["wheelSlotWithDescs"])
        anchor = next((s.get("geomName") for s in slots if isinstance(s, dict) and s.get("geomName")), None)
        yield Truck(name, doc, props, rb, slots, tpl, ctx.nodes(tpl, anchor))


def _det(m: tuple[float, ...]) -> float:
    a, b, c = m[0:3], m[4:7], m[8:11]
    return (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0]))


def _wheel_class(ctx: Context, truck: Truck, editable: Any) -> dict | None:
    pool = truck.rb.get("wheelPool") or {}
    entry = pool.get(editable) if isinstance(pool, dict) else None
    cls_name = entry.get("__value") if isinstance(entry, dict) else entry
    if not isinstance(cls_name, str):
        return None
    member = ctx.find_stem(cls_name, ".cls")
    return _merged_class(ctx, member) if member else None


def _has_node(nodes: TplNodes, name: str) -> bool:
    if name in nodes.index:
        return True
    prefix = name + "_"
    return any(n.startswith(prefix) for n in nodes.names)


def rule_wheel_frames(ctx: Context, truck: Truck) -> None:
    path = ctx.bundle.display(truck.name)
    nodes = truck.nodes
    if nodes is None:
        return
    consistent, inverted = [], []
    for index, slot in enumerate(truck.slots):
        if not isinstance(slot, dict):
            continue
        key = f"properties.prop_truck_rb.wheelSlotWithDescs[{index}]"
        geom = slot.get("geomName")
        for field_name in ("geomName", "parentFrame", "customSteeringJointObjName"):
            value = slot.get(field_name)
            if isinstance(value, str) and value and value not in nodes.index:
                ctx.add("RC058", "error", path, f"{field_name} {value!r} is not a node of model {truck.tpl!r}",
                        key=f"{key}.{field_name}")
        if geom not in nodes.index:
            continue
        m = nodes.matrix(geom)
        if _det(m) < 0:
            ctx.add("RC059", "error", path,
                    f"slot node {geom!r} has a mirrored (left-handed) frame (det {_det(m):.3f}): the wheel model is "
                    "drawn inside out on this side; mirror by rotation, not by negative scale", key=f"{key}.geomName")
        x = m[12]
        if abs(x) > 0.05:
            (consistent if (x < 0) == bool(slot.get("isRightSided")) else inverted).append((index, geom, round(x, 3)))
        knuckle = slot.get("customSteeringJointObjName")
        if isinstance(knuckle, str) and knuckle and knuckle != geom and knuckle in nodes.index:
            kx = nodes.position(knuckle)[0]
            if abs(x) > 0.05 and (kx * x < 0 or abs(kx) - abs(x) > 0.02):
                ctx.add("RC061", "error", path,
                        f"steering joint {knuckle!r} (x {kx:+.3f}) lies outside wheel slot {geom!r} (x {x:+.3f}); retail "
                        "kingpins sit 0.16-0.37 m inboard of the wheel centre", key=f"{key}.customSteeringJointObjName")
        # deformable tyre needs an object named deformingGeomName in the wheel model
        wheel = _wheel_class(ctx, truck, slot.get("editableWheel"))
        wprops = (wheel or {}).get("properties") or {}
        wheel_rb = wprops.get("prop_truck_wheel") if isinstance(wprops, dict) else None
        if isinstance(wheel_rb, dict) and wheel_rb.get("deformEnable") is True:
            wtpl = (wprops.get("geom") or {}).get("nameTpl") if isinstance(wprops.get("geom"), dict) else None
            wnodes = ctx.nodes(wtpl)
            tyre = slot.get("deformingGeomName", "tire")
            if wnodes is not None and not _has_node(wnodes, tyre):
                ctx.add("RC062", "error", path,
                        f"wheel {slot.get('editableWheel')!r} has deformEnable = True but its model {wtpl!r} has no "
                        f"object {tyre!r} (crash: failed to find deforming geom obj); split the tyre and name it "
                        f"{tyre}_LOD0", key=f"{key}.deformingGeomName")
    if consistent and inverted:
        ctx.add("RC060", "error", path,
                f"isRightSided disagrees with the slot side for {[g for _, g, _ in inverted]} while "
                f"{[g for _, g, _ in consistent]} agree (native +X is the vehicle's left): those wheels are mounted "
                "inside out", key="properties.prop_truck_rb.wheelSlotWithDescs")


def rule_suspension(ctx: Context, truck: Truck) -> None:
    path = ctx.bundle.display(truck.name)
    rb = truck.rb
    collection = rb.get("suspensionAxleCollection") or []
    if not collection and not rb.get("suspensionSet"):
        ctx.add("RC063", "error", path,
                "wheel slots but neither suspensionAxleCollection nor suspensionSet: every axle runs on the engine "
                "default (min 0, max 1 m, strength 0), so the wheels hang below a body resting on its lowest point. "
                "Set truckSettings.useSuspensionCollection = True in the BRO (the SDK TUZ sample omits it)",
                key="properties.prop_truck_rb.suspensionAxleCollection")
        return
    size = len(collection) if isinstance(collection, list) else 0
    for index, slot in enumerate(truck.slots):
        value = slot.get("suspensionCollectionAxleIndex", -1) if isinstance(slot, dict) else -1
        if isinstance(value, int) and value >= size and collection:
            ctx.add("RC063", "error", path, f"suspensionCollectionAxleIndex {value} but only {size} axles",
                    key=f"properties.prop_truck_rb.wheelSlotWithDescs[{index}].suspensionCollectionAxleIndex")
    mapping = rb.get("suspensionCollectionMap") or {}
    if isinstance(mapping, dict):
        for item, entry in mapping.items():
            value = entry.get("__value") if isinstance(entry, dict) else entry
            if isinstance(value, int) and not 0 <= value < max(size, 1):
                ctx.add("RC063", "error", path, f"suspensionCollectionMap.{item} = {value} but only {size} axles",
                        key=f"properties.prop_truck_rb.suspensionCollectionMap.{item}")


# ------------------------------------------------------------------------------------------------ joints

def rule_joints(ctx: Context, markup: dict, markup_name: str, nodes: TplNodes | None) -> None:
    path = ctx.bundle.display(markup_name)
    infos = markup.get("objectInfos") or []
    original = ctx.ps(markup_name)
    original_infos = original.get("objectInfos") if isinstance(original, dict) else None

    def line_of(oi_index: int, e_index: int) -> int | None:
        try:
            return original_infos[oi_index]["entities"][e_index].line or None
        except (TypeError, IndexError, KeyError, AttributeError):
            return None
    objects = {(oi.get("objectId") or {}).get("name") for oi in infos if isinstance(oi, dict)}
    names: dict[str, int] = {}
    for oi_index, info in enumerate(infos):
        if not isinstance(info, dict):
            continue
        body = (info.get("objectId") or {}).get("name")
        for e_index, entity in enumerate(info.get("entities") or []):
            if not isinstance(entity, dict):
                continue
            kind = str(entity.get("__type", ""))
            if not kind.startswith("tpl_markup_constraint"):
                continue
            key = f"objectInfos[{oi_index}].entities[{e_index}]"
            line = line_of(oi_index, e_index)
            label = f"{kind.replace('tpl_markup_constraint_', '')} on {body!r}"
            if entity.get("name"):
                names[entity["name"]] = names.get(entity["name"], 0) + 1
            target = entity.get("target", "__parent")
            if target not in ("__parent", "__world") and target not in objects and \
                    (nodes is None or target not in nodes.index):
                ctx.add("RC065", "error", path, f"{label}: target {target!r} is neither a markup object nor a model node",
                        line=line, key=key + ".target")
            if nodes is not None and body:
                if body not in nodes.index:
                    ctx.add("RC065", "error", path, f"{label}: the model has no node {body!r}", line=line,
                            key=f"objectInfos[{oi_index}].objectId.name")
                elif _det(nodes.matrix(body)) < 0:
                    ctx.add("RC065", "error", path,
                            f"{label}: node {body!r} has a mirrored (left-handed) frame, so the joint turns or slides "
                            "the wrong way; rebuild the bone without negative scale", line=line, key=key)
            motor = entity.get("motor") if isinstance(entity.get("motor"), dict) else {}
            driven = motor.get("__type") == "tpl_markup_position_motor"
            if kind.endswith("_hinge"):
                start, end = entity.get("angleStart", 0), entity.get("angleEnd", 0)
                if entity.get("limited") is True and driven and start == end:
                    ctx.add("RC064", "info", path,
                            f"{label}: limited with angleStart = angleEnd = {start} deg but driven by a position motor: "
                            "the joint cannot move (retail locks a few joints this way, e.g. the tree crusher's stump "
                            "grinder)", line=line, key=key)
            elif kind.endswith("_prismatic"):
                low, high = entity.get("minLimit", 0), entity.get("maxLimit", 0)
                if entity.get("isMinLimit") and isinstance(low, (int, float)) and low > 0:
                    ctx.add("RC064", "error", path, f"{label}: minLimit {low} > 0 puts the rest pose outside the range "
                            "(the joint snaps on spawn)", line=line, key=key + ".minLimit")
                if entity.get("isMaxLimit") and isinstance(high, (int, float)) and high < 0:
                    ctx.add("RC064", "error", path, f"{label}: maxLimit {high} < 0 puts the rest pose outside the range",
                            line=line, key=key + ".maxLimit")
                if entity.get("isMinLimit") and entity.get("isMaxLimit") and low > high:
                    ctx.add("RC064", "error", path, f"{label}: minLimit {low} > maxLimit {high}", line=line, key=key)
                elif entity.get("isMinLimit") and entity.get("isMaxLimit") and low == high and driven:
                    ctx.add("RC064", "error", path, f"{label}: min = max = {low} but driven by a position motor",
                            line=line, key=key)
            elif kind.endswith("_wheel"):
                low, high = entity.get("minLimit", 0), entity.get("maxLimit", 0)
                if low > 0 or high < 0:
                    ctx.add("RC064", "error", path, f"{label}: limits [{low}, {high}] exclude the rest position",
                            line=line, key=key)
            elif kind.endswith("_ragdoll"):
                ranges = (("coneAngle", 0, 90), ("planeMinAngle", -90, 0), ("planeMaxAngle", 0, 90),
                          ("twistAngleMin", -180, 180), ("twistAngleMax", -180, 180))
                for fname, low, high in ranges:
                    value = entity.get(fname, 0)
                    if isinstance(value, (int, float)) and not low <= value <= high:
                        ctx.add("RC064", "error", path, f"{label}: {fname} {value} outside {low}..{high}",
                                line=line, key=f"{key}.{fname}")
            elif kind.endswith("_six_dof"):
                modes = []
                for axis in ("linearX", "linearY", "linearZ", "angularX", "angularY", "angularZ"):
                    spec = entity.get(axis) if isinstance(entity.get(axis), dict) else {}
                    mode = spec.get("mode", "UNLIMITED")
                    if axis.startswith("angular"):
                        modes.append(mode)
                    if mode == "LIMITED" and spec.get("min", 0) >= spec.get("max", 0):
                        ctx.add("RC064", "error", path, f"{label}: {axis} LIMITED with min >= max", line=line,
                                key=f"{key}.{axis}")
                fixed = modes.count("FIXED")
                if not (fixed == 3 or modes.count("UNLIMITED") == 3 or fixed == 2):
                    ctx.add("RC064", "error", path,
                            f"{label}: angular modes {modes}; the schema hint says only all-unlimited, all-fixed or two "
                            "fixed + one free/limited are valid, other combinations crash", line=line, key=key)
    for joint, count in sorted(names.items()):
        if count > 1:
            ctx.add("RC065", "info", path, f"joint name {joint!r} is used {count} times (retail Junttan PM20 does this "
                    "too); controls that address joints by name reach only one", key="objectInfos")


# ------------------------------------------------------------------------------------------------ spring motors

SPRING_DT = 1.0 / 60.0                  # editor.cfg Physics.Substep.fixedFps (physics_semantics.md Q7)
SPRING_RETAIL_TAU = 0.38                # retail load-bearing prismatic springs: TUZ Lynx trailer axle 0.375
SPRING_RETAIL_DAMPING = 0.68            # TUZ Lynx trailer axles 0.675; frames 0.52
SPRING_MIN_BODY_KG = 200.0              # lighter props (antennas, balloons, wires) run clamped in retail too


def _body_masses(markup: dict) -> dict[str, float | None]:
    """Markup physics body -> mass in kg (None when massFromDensity: the hull volume is not decoded)."""
    out: dict[str, float | None] = {}
    for info in markup.get("objectInfos") or []:
        if not isinstance(info, dict):
            continue
        name = (info.get("objectId") or {}).get("name")
        for prop in info.get("properties") or []:
            if isinstance(prop, dict) and prop.get("__type") == "tpl_markup_object_property_physics" and name:
                mass = prop.get("mass")
                out[name] = None if prop.get("massFromDensity") is True or not isinstance(mass, (int, float)) \
                    else float(mass)
    return out


def _body_above(nodes: TplNodes, name: str, bodies: dict[str, Any]) -> str | None:
    """Nearest markup physics body above node ``name`` in the model tree (the '__parent' constraint target)."""
    if nodes.parents is None or name not in nodes.index:
        return None
    by_index = {index: node for node, index in nodes.index.items()}
    index = nodes.index[name]
    for _ in range(len(nodes.parents)):
        index = nodes.parents[index] if 0 <= index < len(nodes.parents) else -1
        if index < 0:
            return None
        node = by_index.get(index)
        if node in bodies:
            return node
    return None


def rule_spring_motors(ctx: Context, markup: dict, markup_name: str, tpl_name: str | None) -> None:
    """RC076: a prismatic ``tpl_markup_spring_motor`` between two bodies of >= 200 kg whose per-step solver numbers
    leave the retail regime.  The engine turns spring k and damping c into k*dt^2/m_eff and c*dt/m_eff, each clamped
    to [0, 1]; m_eff is the constraint row's virtual mass from the two connected bodies only, at most the reduced mass
    m1*m2/(m1+m2), so the values here are lower bounds.  Hinge springs need the reduced inertia about the axis, which
    is not decoded, and are not checked."""
    if "spring-motors" not in ctx.rules:
        return
    path = ctx.bundle.display(markup_name)
    masses = _body_masses(markup)
    original = ctx.ps(markup_name)
    original_infos = original.get("objectInfos") if isinstance(original, dict) else None
    tree: TplNodes | None = None
    tree_loaded = False
    for oi_index, info in enumerate(markup.get("objectInfos") or []):
        if not isinstance(info, dict):
            continue
        body = (info.get("objectId") or {}).get("name")
        for e_index, entity in enumerate(info.get("entities") or []):
            if not isinstance(entity, dict) or entity.get("__type") != "tpl_markup_constraint_prismatic":
                continue
            motor = entity.get("motor")
            if not isinstance(motor, dict) or motor.get("__type") != "tpl_markup_spring_motor":
                continue
            k, c = motor.get("spring", 0), motor.get("damping", 0)
            if not isinstance(k, (int, float)) or not isinstance(c, (int, float)):
                continue
            target = entity.get("target", "__parent")
            if target == "__world":
                continue
            if target == "__parent":
                if not tree_loaded:
                    tree, tree_loaded = ctx.tree(tpl_name), True
                target = _body_above(tree, body, masses) if tree is not None and body else None
            m1, m2 = masses.get(body), masses.get(target) if target else None
            if not m1 or not m2 or min(m1, m2) < SPRING_MIN_BODY_KG:
                continue
            m_red = m1 * m2 / (m1 + m2)
            tau = k * SPRING_DT * SPRING_DT / m_red
            damping = c * SPRING_DT / m_red
            if tau <= SPRING_RETAIL_TAU and damping <= SPRING_RETAIL_DAMPING:
                continue
            notes = []
            if damping > 1:
                notes.append(f"damping is clamped to 1, so at most m_eff/dt = {m_red / SPRING_DT:.3g} N*s/m of the "
                             f"{c:.3g} asked for is delivered ({100 * min(1.0, 1 / damping):.0f} %)")
            if tau > 1:
                notes.append(f"the rate is clamped to 1, so at most m_eff/dt^2 = {m_red / SPRING_DT ** 2:.3g} N/m of "
                             f"the {k:.3g} asked for is delivered")
            if not notes:
                notes.append("not clamped, but beyond anything retail ships on a load-bearing prismatic")
            try:
                line = original_infos[oi_index]["entities"][e_index].line or None
            except (TypeError, IndexError, KeyError, AttributeError):
                line = None
            ctx.add("RC076", "warning", path,
                    f"spring motor on prismatic {body!r} against {target!r} ({m1:.0f} / {m2:.0f} kg): k*dt^2/m_eff "
                    f">= {tau:.2f} and c*dt/m_eff >= {damping:.2f} at 60 Hz (m_eff <= {m_red:.0f} kg, the reduced mass; "
                    f"the supported load is not in it); retail load-bearing prismatic springs stay at <= "
                    f"{SPRING_RETAIL_TAU} / <= {SPRING_RETAIL_DAMPING}; " + "; ".join(notes),
                    line=line, key=f"objectInfos[{oi_index}].entities[{e_index}].motor",
                    fix=f"raise the lighter body's mass (take it from the heavier one) or keep spring <= "
                        f"{SPRING_RETAIL_TAU * m_red / SPRING_DT ** 2:.3g} N/m and damping <= "
                        f"{SPRING_RETAIL_DAMPING * m_red / SPRING_DT:.3g} N*s/m")


def rule_ik_frames(ctx: Context, truck: Truck) -> None:
    nodes = truck.nodes
    ik = truck.props.get("prop_ik_system_visual")
    if nodes is None or not isinstance(ik, dict):
        return
    path = ctx.bundle.display(truck.name)
    seen = set()
    for node in bro_lint._walk(ik):
        for key in ("ikChainBodies", "bodies"):
            for body in node.get(key) or []:
                if isinstance(body, str) and body in nodes.index and body not in seen:
                    seen.add(body)
                    if _det(nodes.matrix(body)) < 0:
                        ctx.add("RC065", "error", path,
                                f"IK body {body!r} has a mirrored (left-handed) frame: the chain solves about "
                                "wrong-handed axes", key="properties.prop_ik_system_visual")


# ------------------------------------------------------------------------------------------------ lamps

def _tokens(data: bytes | None) -> set[str]:
    return {t.decode("ascii") for t in re.findall(rb"[A-Za-z_][A-Za-z0-9_]{2,}", data or b"")}


def rule_lamps(ctx: Context, truck: Truck) -> None:
    lights_prop = truck.props.get("prop_vehicle_lights_material")
    lights = (lights_prop or {}).get("lights") if isinstance(lights_prop, dict) else None
    _check_lights(ctx, truck.name, "properties.prop_vehicle_lights_material.lights", lights, truck.tpl, truck.nodes,
                  truck.props.get("prop_blueprints"))


def bro_lights(doc: dict) -> dict[str, dict]:
    """vehicleLightMaterials.lights.<Name>.lightData of a truck BRO (compiled to prop_vehicle_lights_material)."""
    block = doc.get("vehicleLightMaterials")
    lights = block.get("lights") if isinstance(block, dict) else None
    out = {}
    for name, entry in (lights or {}).items() if isinstance(lights, dict) else ():
        data = entry.get("lightData") if isinstance(entry, dict) else None
        if isinstance(data, dict):
            out[f"{name}.lightData"] = data
    return out


def _object_slots(ctx: Context, tpl: str | None) -> dict[str, set[str]] | None:
    """Object name -> material slots it uses, from the source tree's tpl/obj_list.json (None without it)."""
    member = ctx.find_stem(tpl, ".tpl_markup") if tpl else None
    if member is None:
        return None
    listing = posixpath.join(posixpath.dirname(member), "tpl", "obj_list.json")
    if not ctx.bundle.has(listing):
        return None
    try:
        stack = [json.loads(ctx.bundle.read(listing)).get("engine_objects") or {}]
    except ValueError:
        return None
    out: dict[str, set[str]] = {}
    while stack:
        obj = stack.pop()
        names = {m.get("maya_name") for m in obj.get("material_info") or [] if m.get("maya_name")}
        if names and obj.get("name"):
            out.setdefault(re.sub(r"_LOD\d+$|_vis$", "", obj["name"]), set()).update(names)
        stack.extend(obj.get("children") or [])
    return out


def _check_lights(ctx: Context, owner: str, prefix: str, lights: Any, tpl: str | None, nodes: TplNodes | None,
                  blueprints: Any = None) -> None:
    path = ctx.bundle.display(owner)
    markup, markup_name = ctx.markup(tpl)
    materials = (markup or {}).get("materials") if isinstance(markup, dict) else None
    materials = materials if isinstance(materials, dict) else {}
    dynamic: dict[str, list[tuple[str, str | None, str | None]]] = {}
    for slot, entry in materials.items():
        if isinstance(entry, dict):
            for state, spec in (entry.get("dynamicMaterials") or {}).items():
                mat = spec.get("materialName") if isinstance(spec, dict) else None
                dynamic.setdefault(state, []).append((slot, mat, entry.get("materialName")))
    hidden = lamps.markup_hidden(markup) if isinstance(markup, dict) else set()
    object_slots = _object_slots(ctx, tpl) if dynamic else None
    tokens: set[str] | None = None
    if isinstance(lights, dict):
        for light_key, light in lights.items():
            if not isinstance(light, dict):
                continue
            key = f"{prefix}.{light_key}"
            on = light.get("lightName", "lights")
            off = light.get("defaultName", "default_cc")
            if on not in dynamic and dynamic:
                # the markup route (Blender mods): states come from materials.<slot>.dynamicMaterials. Retail models
                # carry their states inside the compiled .tpl instead, so a markup without any dynamic state is
                # not judged.
                if tokens is None:
                    tokens = _tokens(ctx.tpl_bytes(tpl))
                if on not in tokens:
                    near = difflib.get_close_matches(on, sorted(set(dynamic) | {t for t in tokens if "light" in t}),
                                                     n=1, cutoff=0.8)
                    ctx.add("RC066", "error", path,
                            f"lamp {light.get('__type', light_key)} {light.get('geomNames')} switches to state {on!r}, "
                            f"which no markup material slot ({markup_name}) or compiled model material defines"
                            + (f"; did you mean {near[0]!r}?" if near else "") + ": the lamp never lights",
                            key=key + ".lightName")
            elif on in dynamic:
                for slot, lit, base in dynamic[on]:
                    unlit = next((m for s, m, _ in dynamic.get(off, []) if s == slot), base)
                    if lit and unlit and (lit == unlit or _same_material(ctx, lit, unlit)):
                        ctx.add("RC067", "error", ctx.bundle.display(markup_name or owner),
                                f"slot {slot!r}: lit state {on!r} uses {lit!r} and off state {off!r} uses {unlit!r}, "
                                "identical materials: the lamp shows no change when lit",
                                key=f"materials.{slot}.dynamicMaterials.{on}")
            for geom in light.get("geomNames") or []:
                slots = (object_slots or {}).get(geom) if isinstance(geom, str) else None
                if slots and on in dynamic and not slots & {slot for slot, _, _ in dynamic[on]}:
                    states = sorted({st for st, rows in dynamic.items() for sl, _, _ in rows if sl in slots})
                    near = difflib.get_close_matches(on, states, n=1, cutoff=0.8)
                    ctx.add("RC066", "error", path,
                            f"lamp object {geom!r} uses material slot(s) {sorted(slots)}, none of which has state {on!r} "
                            f"(their states: {states})" + (f"; misspelt {near[0]!r}?" if near else "")
                            + ": this lamp never lights", key=key + ".geomNames")
                if nodes is not None and isinstance(geom, str) and not _has_node(nodes, geom):
                    ctx.add("RC068", "info", path, f"lamp object {geom!r} is not in model {tpl!r} (hidden in "
                            "Blender, hidden_/cdt_ prefix or renamed?); retail ships 10 such entries, so this is listed for review",
                            key=key + ".geomNames")
                elif geom in hidden:
                    ctx.add("RC068", "error", path, f"lamp object {geom!r} is hidden by the markup (objSettings "
                            "visibility): its material switch is never seen", key=key + ".geomNames")
    # lit copies hidden by the markup and strobes that hide the unlit lens (lamps.py RC037 / RC039)
    if isinstance(markup, dict) and blueprints and "lamps" in ctx.rules:
        for code, severity, message, where in lamps.lamp_findings(blueprints, hidden):
            if code in ("RC037", "RC039"):     # RC038 is left out: retail ships it (ZiKZ 605E scalper)
                ctx.findings.append(Finding(
                    "lamps", "error" if code == "RC037" else severity, path, None, message,
                    "Game: L275 v4-v8, Dump Twuck v4 never lit (library/cockpit-and-lamps.md); markup cause Inferred",
                    code, "properties.prop_blueprints." + where.split(".", 1)[-1]))


def rule_misspelt_states(ctx: Context, lamp_states: set[str]) -> None:
    """A markup dynamic state no lamp switches but one letter away from a state the lamps do switch
    (lights_emmissive vs lights_emissive in the SDK TUZ sample)."""
    if not lamp_states:
        return
    for name in ctx.bundle.names():
        if not name.lower().endswith(".tpl_markup"):
            continue
        doc = ctx.ps(name)
        materials = doc.get("materials") if isinstance(doc, dict) else None
        for slot, entry in (materials or {}).items() if isinstance(materials, dict) else ():
            states = (entry or {}).get("dynamicMaterials") if isinstance(entry, dict) else None
            for state in states or {}:
                if state in lamp_states or not isinstance(state, str):
                    continue
                near = difflib.get_close_matches(state, sorted(lamp_states), n=1, cutoff=0.85)
                if near:
                    ctx.add("RC066", "error", ctx.bundle.display(name),
                            f"slot {slot!r} defines state {state!r}, which no lamp switches; the lamps switch "
                            f"{near[0]!r}: misspelt, so objects on this slot never light",
                            line=getattr(states, "lines", {}).get(state),
                            key=f"materials.{slot}.dynamicMaterials.{state}")


def rule_state_pairs(ctx: Context, lamp_states: set[str]) -> None:
    """``<x>_on`` / ``<x>_off`` dynamic states (D11 beacon), one finding per markup and state, only when NO slot
    of the pair differs: then switching the state can never be seen.  Slots where on = off = the slot's base
    material are no-ops a copied markup carries for every body slot, and are ignored as long as some slot
    differs (the Goliath: 82 no-op slots, one real beacon slot; verified by the RC6 fix)."""
    for name in ctx.bundle.names():
        if not name.lower().endswith(".tpl_markup"):
            continue
        doc = ctx.ps(name)
        materials = doc.get("materials") if isinstance(doc, dict) else None
        if not isinstance(materials, dict):
            continue
        same: dict[str, list[str]] = {}
        differs: set[str] = set()
        for slot, entry in materials.items():
            states = (entry or {}).get("dynamicMaterials") if isinstance(entry, dict) else None
            if not isinstance(states, dict):
                continue
            for state, spec in states.items():
                if not (isinstance(state, str) and state.endswith("_on")) or not isinstance(spec, dict):
                    continue
                other = states.get(state[:-3] + "_off")
                lit = spec.get("materialName")
                unlit = other.get("materialName") if isinstance(other, dict) else None
                if not (lit and unlit):
                    continue
                if lit == unlit or _same_material(ctx, lit, unlit):
                    same.setdefault(state, []).append(slot)
                else:
                    differs.add(state)
        for state, slots in sorted(same.items()):
            if state in differs:
                continue                       # some slot shows the switch; identical slots are no-ops
            used = state in lamp_states
            ctx.add("RC067", "error" if used else "warning", ctx.bundle.display(name),
                    f"states {state!r} / {state[:-3] + '_off'!r} use identical materials in every slot that defines "
                    f"them ({len(slots)}: {slots[:6]}{' ...' if len(slots) > 6 else ''}): the state can never be seen"
                    + ("" if used else " (no lamp of this mod uses the state)"),
                    line=getattr(materials, "lines", {}).get(slots[0]),
                    key=f"materials.{slots[0]}.dynamicMaterials.{state}")


def _mi_member(name: str) -> str:
    return f"material_instances/{name.lower()}.mi"


def _same_material(ctx: Context, a: str, b: str) -> bool:
    da, db = ctx.ps(_mi_member(a)), ctx.ps(_mi_member(b))
    if not isinstance(da, dict) or not isinstance(db, dict):
        return False
    return json.dumps(da, sort_keys=True) == json.dumps(db, sort_keys=True)


# ------------------------------------------------------------------------------------------------ materials

def rule_materials(ctx: Context) -> None:
    for name in ctx.bundle.names():
        lower = name.lower()
        if lower.endswith("/export_options.ps"):
            doc = ctx.ps(name)
            advanced = ((doc or {}).get("options") or {}).get("advanced") if isinstance(doc, dict) else None
            if isinstance(advanced, dict) and advanced.get("merge_materials") is True:
                ctx.add("RC069", "warning", ctx.bundle.display(name),
                        "advanced.merge_materials = True: tplexp merges material slots, so per-slot lamp and dynamic "
                        "states can be lost (every export_options.ps the owner has uses False)",
                        key="options.advanced.merge_materials")
        if not lower.endswith(".tpl_markup") or "/models/" not in "/" + lower:
            continue
        stem = lower.rsplit("/", 1)[-1][: -len(".tpl_markup")]
        doc = ctx.ps(name)
        if not isinstance(doc, dict) or not isinstance(doc.get("materials"), dict):
            continue
        listing = posixpath.join(posixpath.dirname(name), "tpl", "obj_list.json")
        used: set[str] | None = None
        if ctx.bundle.has(listing):
            try:
                used = set()
                stack = [json.loads(ctx.bundle.read(listing)).get("engine_objects") or {}]
                while stack:
                    obj = stack.pop()
                    used.update(m.get("maya_name") for m in obj.get("material_info") or [] if m.get("maya_name"))
                    stack.extend(obj.get("children") or [])
            except (ValueError, AttributeError):
                used = None
        # A built pak has no obj_list.json; the compiled .tpl's strings are not a reliable material list (the
        # Goliath pak's model lacks names its source obj_list.json lists), so the check needs the source tree.
        if not used:
            continue
        lines = getattr(doc["materials"], "lines", {})
        looks = {slot: _material_look(ctx, entry) for slot, entry in doc["materials"].items() if isinstance(entry, dict)}
        kept_by_texture: dict[str, list[tuple[str, str]]] = {}
        for slot, (texture, preset) in looks.items():
            if slot in used and texture:
                kept_by_texture.setdefault(texture, []).append((slot, preset))
        for slot, (texture, preset) in looks.items():
            if slot in used or not texture:
                continue
            # merged away: another slot on the same texture survived with a different preset (L275 glass)
            winners = [(s2, p2) for s2, p2 in kept_by_texture.get(texture, []) if p2 != preset]
            if not winners:
                continue                  # unused slots (copied markups list every body material) are harmless
            states = bool((doc["materials"][slot] or {}).get("dynamicMaterials"))
            ctx.add("RC069", "warning", ctx.bundle.display(name),
                    f"material slot {slot!r} ({preset}) is not in the compiled model while {winners[0][0]!r} "
                    f"({winners[0][1]}) on the same texture {texture!r} is: the exporter keeps one material per "
                    "texture in an object (or the slot has no faces in the export), so this slot's look"
                    + (" and its lamp states" if states else "") + " is lost; give it its own object or texture", line=lines.get(slot), key=f"materials.{slot}")


def _material_look(ctx: Context, entry: dict) -> tuple[str | None, str]:
    """(base texture, preset) of a markup material slot's instance."""
    mi = ctx.ps(_mi_member(str(entry.get("materialName", ""))))
    if not isinstance(mi, dict):
        return None, ""
    texture = None
    for node in bro_lint._walk(mi):
        value = node.get("texDiff") or node.get("albedo")
        if isinstance(value, str) and value:
            texture = value.lower()
            break
    return texture, str(mi.get("__type", ""))


# ------------------------------------------------------------------------------------------------ references

_GENERIC_REF = re.compile(r"^(links|link[A-Z]|parents$)")


def _resolve_tag(base_dir: str, value: str) -> str:
    if value.startswith("res://"):
        return value[6:].lower()
    path = base_dir
    while value.startswith("../"):
        path = posixpath.dirname(path)
        value = value[3:]
    return posixpath.normpath(posixpath.join(path, value)).lower()


def rule_references(ctx: Context) -> None:
    descs = (ctx.schema.resource_descs or {}) if ctx.schema is not None else {}
    retail_ok = ctx.retail is not None

    def present(member: str) -> bool:
        return ctx.bundle.has(member) or (retail_ok and ctx.retail.has(member))

    def missing(path: str, key: str, target: str, what: str, line: int | None = None) -> None:
        where = "the mod" + ("" if retail_ok else " (retail not checked: no game root)")
        ctx.add("RC070", "error", path, f"{what} {target!r} is in neither {where} nor retail", line=line, key=key)

    for name in ctx.bundle.names():
        lower = name.lower()
        path = ctx.bundle.display(name)
        if lower.endswith(YAML_EXTENSIONS) and not lower.endswith((".tpl_markup.resource",)) or \
                lower.endswith(".tpl_markup.resource"):
            try:
                doc = schema_mod.yaml_loads(ctx.bundle.read(name).decode("utf-8-sig", errors="replace"))
            except Exception:                                    # noqa: BLE001 - malformed YAML is reported below
                doc = None
            if not isinstance(doc, dict):
                continue
            base_dir = posixpath.dirname(name)
            if lower.endswith(".mod"):
                for index, asset in enumerate(doc.get("assets") or []):
                    if isinstance(asset, str) and not present(asset):
                        missing(path, f"assets[{index}]", asset, ".mod asset root")
                continue
            spec = descs.get(doc.get("__type")) or {}
            refs = set(spec.get("refs") or {}) | {k for k in doc if _GENERIC_REF.match(k)}
            for key in sorted(refs):
                values = doc.get(key)
                for index, value in enumerate(values if isinstance(values, list) else [values]):
                    if isinstance(value, str) and value:
                        target = _resolve_tag(base_dir, value)
                        if not present(target) and not target.startswith("$"):
                            missing(path, f"{key}[{index}]" if isinstance(values, list) else key, value, "link")
            for key in spec.get("blobs") or []:
                value = doc.get(key)
                for item in value if isinstance(value, list) else [value]:
                    if isinstance(item, str) and item and not present(_resolve_tag(base_dir, item)):
                        missing(path, key, item, "blob")
        elif lower.endswith(".tpl_markup"):
            doc = ctx.ps(name)
            materials = doc.get("materials") if isinstance(doc, dict) else None
            for slot, entry in (materials or {}).items() if isinstance(materials, dict) else ():
                if not isinstance(entry, dict):
                    continue
                specs = [("materialName", entry.get("materialName"))]
                specs += [(f"dynamicMaterials.{state}.materialName", (s or {}).get("materialName"))
                          for state, s in (entry.get("dynamicMaterials") or {}).items() if isinstance(s, dict)]
                for key, material in specs:
                    if isinstance(material, str) and material and not present(_mi_member(material) + ".resource") \
                            and not present(_mi_member(material)):
                        missing(path, f"materials.{slot}.{key}", material, "material instance",
                                getattr(materials, "lines", {}).get(slot))
        elif lower.endswith(".mi"):
            doc = ctx.ps(name)
            if not isinstance(doc, dict):
                continue
            for node in bro_lint._walk(doc):
                for key, value in node.items():
                    if key.startswith("tex") and isinstance(value, str) and value and \
                            not present(f"pct/{value.lower()}.pct.resource"):
                        missing(path, key, value, "texture")
        elif lower.endswith(".cls"):
            doc = ctx.ps(name)
            props = doc.get("properties") if isinstance(doc, dict) else None
            if not isinstance(props, dict):
                continue
            geom = props.get("geom")
            tpl = geom.get("nameTpl") if isinstance(geom, dict) else None
            if isinstance(tpl, str) and tpl and ctx.find_stem(tpl, ".tpl.asset") is None and \
                    ctx.find_stem(tpl, ".tpl") is None:
                missing(path, "properties.geom.nameTpl", tpl, "model")
            rb = props.get("prop_truck_rb")
            pool = rb.get("wheelPool") if isinstance(rb, dict) else None
            for item, entry in (pool or {}).items() if isinstance(pool, dict) else ():
                cls_name = entry.get("__value") if isinstance(entry, dict) else entry
                if isinstance(cls_name, str) and cls_name and ctx.find_stem(cls_name, ".cls") is None:
                    missing(path, f"properties.prop_truck_rb.wheelPool.{item}", cls_name, "wheel class")


# ------------------------------------------------------------------------------------------------ duplicates / BRO

def rule_duplicates(ctx: Context) -> None:
    if ctx.bundle.kind != "pak":
        return
    for occurrences in ctx.bundle.by_name.values():
        if len(occurrences) > 1:
            hashes = {hashlib.sha256(m.read()).hexdigest() for m in occurrences}
            if len(hashes) > 1:
                ctx.add("RC071", "warning", ctx.bundle.display(occurrences[0].name),
                        f"{len(occurrences)} occurrences with {len(hashes)} different contents; the packager's duplicates "
                        "are byte-identical, and which copy the engine loads is not established")


def rule_bro(ctx: Context) -> None:
    for name in ctx.bundle.names():
        if not name.lower().endswith(".bro"):
            continue
        doc = ctx.ps(name)
        if not isinstance(doc, dict) or not isinstance(doc.get("truckSettings"), dict):
            continue
        tpl = doc.get("tpl") if isinstance(doc.get("tpl"), str) else None
        markup, _ = ctx.markup(tpl)
        model = ctx.nodes(tpl)
        for f in bro_lint.lint_truck(doc, model=model, markup=markup if isinstance(markup, dict) else None):
            if f["severity"] == "info" or "bro-lint" not in ctx.rules:
                continue
            ctx.findings.append(Finding("bro-lint", f["severity"], ctx.bundle.display(name),
                                        getattr(doc, "lines", {}).get(f["where"].split(".")[0]), f["message"],
                                        f"lint-bro {f['code']} ({f['library']})", f["code"], f["where"]))


# ------------------------------------------------------------------------------------------------ save-compat

CONSTRAINT_DESC = "TruckConstraintsSavablePropDesc"
CARGO_DESC = "TruckStorageSavablePropDesc"
OWNER = "OWNER"                     # PropTruckConstraintView.OWNER, the default addon of a chain constraint


def _named(value: Any) -> list[tuple[str, Any]]:
    """Entries of a ``[collection]`` field: a PS dict keyed by the ``[magic]`` name, or a list with ``name``."""
    if isinstance(value, dict):
        return [(str(k), v) for k, v in value.items() if not str(k).startswith("__")]
    if isinstance(value, list):
        return [(str(v.get("name", i)) if isinstance(v, dict) else str(i), v) for i, v in enumerate(value)]
    return []


def _list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [v for k, v in value.items() if not str(k).startswith("__")]
    return []


@dataclass
class SavableDescriptors:
    """What restore looks up for one class (save_semantics.md): the savable desc types, and for the constraint
    desc the powered constraints by index, the controllable ones by name, the sequential chains by name with each
    stage's (addon, constraint) set by stage index, and the cargo slots."""
    member: str
    types: list[str]
    powered: list[str]
    controllable: list[str]
    chain_refs: set[str]            # controllable constraints referenced by constraintChains links
    sequential: dict[str, list[tuple[str, set[tuple[str, str]]]]]
    cargo_slots: dict[str, bool]


def savable_descriptors(ctx: Context) -> dict[str, SavableDescriptors]:
    """Every class of the target with a ``prop_savable_object``, keyed by lower-case member path."""
    out: dict[str, SavableDescriptors] = {}
    for name in ctx.bundle.names():
        if not name.lower().endswith(".cls"):
            continue
        data = ctx.bundle.read(name)
        if b"prop_savable_object" not in data and b"__type" not in data:
            continue
        doc = _merged_class(ctx, name)
        props = (doc or {}).get("properties") if isinstance(doc, dict) else None
        holder = props.get("prop_savable_object") if isinstance(props, dict) else None
        if not isinstance(holder, dict):
            continue
        types = []
        for item in _list(holder.get("savablePropDescs")):
            desc = item.get("desc") if isinstance(item, dict) else None
            if isinstance(desc, dict) and isinstance(desc.get("__type"), str):
                types.append(desc["__type"])
        view = props.get("prop_truck_constraint_view")
        view = view if isinstance(view, dict) else {}
        powered = [c.get("constraintName", "") for c in _list(view.get("powerConstraints")) if isinstance(c, dict)]
        controllable = [c.get("constraintName", "") for c in _list(view.get("controllableConstraints"))
                        if isinstance(c, dict)]
        refs = set()
        for _, chain in _named(view.get("constraintChains")):
            for link in _list(chain.get("links") if isinstance(chain, dict) else None):
                if isinstance(link, dict) and link.get("constraint") in controllable \
                        and link.get("addon", OWNER) == OWNER:
                    refs.add(link["constraint"])
        sequential: dict[str, list[tuple[str, set[tuple[str, str]]]]] = {}
        for chain_name, chain in _named(view.get("constraintSequentialChains")):
            stages = []
            for stage_name, stage in _named(chain.get("links") if isinstance(chain, dict) else None):
                pairs = {(str(c.get("addon", OWNER)), str(c.get("constraintName", "")))
                         for c in _list(stage.get("constraints") if isinstance(stage, dict) else None)
                         if isinstance(c, dict)}
                stages.append((stage_name, pairs))
            sequential[chain_name] = stages
        cargo = props.get("prop_truck_cargo_controller")
        cargo = cargo if isinstance(cargo, dict) else {}
        slots = {k: isinstance(cargo.get(k), dict) for k in ("firstCargoSlot", "secondCargoSlot")}
        out[name.lower()] = SavableDescriptors(name, types, powered, controllable, refs, sequential, slots)
    return out


_TRUCK_INFO = re.compile(r"^(?:.*/)?auto_(?!wheel_|preview_)(.+?)_truck_info_[^/]*\.sso\.resource$", re.I)


def truck_identities(bundle: Bundle) -> dict[str, str]:
    """Truck library names of a mod: ``auto_<name>_truck_info_<suffix>.sso.resource`` -> ``<name>``
    (AutogenLibrariesCreator.ExtractModTagDirName / CreateKeyByDir); the save origin is truck_manager_rb_<name>."""
    out = {}
    for name in bundle.names():
        match = _TRUCK_INFO.match(name)
        if match:
            out[match.group(1).lower()] = name
    return out


def rule_save_compat(ctx: Context, baseline: Context) -> None:
    """RC077: compare the candidate's savable descriptors with the baseline's (the version existing saves were
    written with).  error = restore or the first use of the restored state indexes a key or index the save lacks
    (crash: the L275 v35 hang); warning = saved state dropped or applied to something else."""
    if "save-compat" not in ctx.rules:
        return
    new = savable_descriptors(ctx)
    old = savable_descriptors(baseline)
    view_key = "properties.prop_truck_constraint_view"
    old_ids, new_ids = truck_identities(baseline.bundle), truck_identities(ctx.bundle)
    for ident, tag in sorted(old_ids.items()):
        if ident not in new_ids:
            ctx.add("RC077", "warning", ctx.bundle.display(tag),
                    f"truck identity {ident!r} is gone (save origin 'truck_manager_rb_{ident}'): saved trucks of it are "
                    "not recreated (ActorSaveManager.CreateActorFromSave finds no registered origin and returns null; "
                    "the truck silently disappears from the save)", key=f"truck_info.{ident}",
                    fix=f"keep 'auto_{ident}_truck_info_' in the .sso.resource name; a new identity is a new truck")
    unmatched_new = [m for m in new if m not in old]
    for member, base in sorted(old.items()):
        cand = new.get(member)
        if cand is None and len(unmatched_new) == 1 and len([m for m in old if m not in new]) == 1:
            cand = new[unmatched_new[0]]          # the class file was renamed (e.g. a new suffix): compare anyway
        if cand is None:
            ctx.add("RC077", "warning", ctx.bundle.display(base.member),
                    f"class {base.member} with saved state is gone from the candidate: saved actors of it are not "
                    "restored against it", key="properties.prop_savable_object")
            continue
        path = ctx.bundle.display(cand.member)
        removed = [t for t in dict.fromkeys(base.types) if t not in cand.types]
        added = [t for t in dict.fromkeys(cand.types) if t not in base.types]
        for t in removed:
            ctx.add("RC077", "warning", path,
                    f"savable desc {t} was removed: the state it saved is ignored on load (SetSavedProps only loads "
                    "saved descs whose type the class still lists)", key=f"properties.prop_savable_object.{t}",
                    fix="intended only as the defensive fix for an incompatible change (symptoms.md 'loads forever')")
        for t in added:
            ctx.add("RC077", "info", path,
                    f"savable desc {t} is new: saves from the baseline restore its state from the class defaults"
                    + ("; saves older than the baseline that still carry it are restored against this class"
                       if t == CONSTRAINT_DESC else ""), key=f"properties.prop_savable_object.{t}")
        if CARGO_DESC in base.types and CARGO_DESC in cand.types:
            for slot, present in base.cargo_slots.items():
                if present and not cand.cargo_slots.get(slot):
                    ctx.add("RC077", "error", path,
                            f"cargo slot {slot} was removed: a save with cargo in it calls ChangeCargo on a null slot "
                            "(assert 'cargo slot is not setted' in PropTruckCargoController)",
                            key=f"properties.prop_truck_cargo_controller.{slot}",
                            fix="keep the slot, or drop TruckStorageSavablePropDesc")
        if not (CONSTRAINT_DESC in base.types and CONSTRAINT_DESC in cand.types):
            continue
        # The saved TruckConstraintGlobalState replaces the one SetState built from the current class.
        if len(cand.powered) != len(base.powered):
            ctx.add("RC077", "error", path,
                    f"powerConstraints count changed {len(base.powered)} -> {len(cand.powered)}: the save keeps the old "
                    "array and the view/unit index it by the current positions (powerConstraints[i] / "
                    "poweredConstrains[index] out of range)", key=f"{view_key}.powerConstraints",
                    fix="keep the count; add new joints as controllable constraints, or drop "
                        "TruckConstraintsSavablePropDesc")
        else:
            for i, (a, b) in enumerate(zip(base.powered, cand.powered)):
                if a != b:
                    ctx.add("RC077", "warning", path,
                            f"powerConstraints[{i}] renamed {a!r} -> {b!r}: powered state is saved by index, so the "
                            f"saved target of {a!r} drives {b!r}", key=f"{view_key}.powerConstraints[{i}]")
        for name in cand.controllable:
            if name in base.controllable:
                continue
            if name in cand.chain_refs:
                ctx.add("RC077", "error", path,
                        f"controllable constraint {name!r} is new and a constraintChains link uses it: the controller "
                        "reads globalState.controlledConstrains.Get(name), which the old save lacks",
                        key=f"{view_key}.controllableConstraints.{name}",
                        fix="drop TruckConstraintsSavablePropDesc, or keep the joint out of constraintChains")
            else:
                ctx.add("RC077", "warning", path,
                        f"controllable constraint {name!r} is new: an old save has no target for it (it stays at the "
                        "model pose until moved); coop clients read controlledConstrains[name] when the host moves it",
                        key=f"{view_key}.controllableConstraints.{name}")
        for name in base.controllable:
            if name not in cand.controllable:
                ctx.add("RC077", "warning", path,
                        f"controllable constraint {name!r} was removed or renamed: its saved target is still applied "
                        "by name on load (SetConstraintTarget dereferences a null joint if the model lost it)",
                        key=f"{view_key}.controllableConstraints.{name}",
                        fix="keep the joint name in the model; renaming = removing plus adding")
        for chain, stages in cand.sequential.items():
            key = f"{view_key}.constraintSequentialChains.{chain}"
            saved = base.sequential.get(chain)
            if saved is None:
                ctx.add("RC077", "error", path,
                        f"sequential chain {chain!r} is new: PropTruckConstraintView.RestoreFromSave does "
                        f"data.Get({chain!r}) on the old save's chains (key not found: the game hangs loading)",
                        key=key, fix="drop TruckConstraintsSavablePropDesc from prop_savable_object (constraint state "
                                     "is then not saved), or ship the chain as a new truck identity")
                continue
            if len(stages) != len(saved):
                ctx.add("RC077", "error", path,
                        f"sequential chain {chain!r} has {len(stages)} stages, the save {len(saved)}: the controller "
                        "indexes the saved links by the current stage index (out of range when the chain runs, or at "
                        "once if the save stopped past the new end)", key=f"{key}.links")
            for i, (stage, pairs) in enumerate(stages[:len(saved)]):
                saved_pairs = saved[i][1]
                for addon, cname in sorted(pairs - saved_pairs):
                    ctx.add("RC077", "error", path,
                            f"sequential chain {chain!r} stage {i} ({stage}) gained {cname!r}"
                            + (f" on addon {addon!r}" if addon != OWNER else "")
                            + ": the controller reads links[i].addons[addon].constraints[name] from the saved chain "
                              "(key not found when the chain runs)", key=f"{key}.links.{stage}.{cname}")
                for addon, cname in sorted(saved_pairs - pairs):
                    ctx.add("RC077", "warning", path,
                            f"sequential chain {chain!r} stage {i} ({stage}) lost {cname!r}: the saved target is "
                            "still applied by name on load (null joint if the model lost it)",
                            key=f"{key}.links.{stage}.{cname}")
        for chain in base.sequential:
            if chain not in cand.sequential:
                ctx.add("RC077", "warning", path,
                        f"sequential chain {chain!r} was removed or renamed: the saved chain is kept in the state and "
                        "its current stage targets are still applied by joint name (null joint if the model lost it)",
                        key=f"{view_key}.constraintSequentialChains.{chain}")


def count_retail_ignored(game_root: str | Path | None = None, out: str | Path | None = RETAIL_IGNORED_FILE) -> dict:
    """Count RC072 dead keys in retail content (every retail .cls, .prop and .tpl_markup) per (type key, key)
    with this module's walker and read-fields tables, and write data/retail_ignored_counts.json.  Takes about
    6 minutes.  Re-run after a game update or a read_fields.json change."""
    import collections
    import time
    root = Path(game_root) if game_root else schema_mod.default_game_root()
    index = retail._index(root)
    names = sorted(n for n in index if n.lower().endswith((".cls", ".prop", ".tpl_markup")))
    bundle = Bundle("retail", "pak", [_Member(n, (lambda n=n: retail.read_member(root, n))) for n in names])
    global _retail_ignored
    saved, _retail_ignored = _retail_ignored, {}       # count raw warnings, not the downgraded ones
    try:
        ctx = Context(bundle, Retail(root), schema_mod.load(root), {"ignored-fields"}, ReadFields.load())
        ctx.game_root = root
        rule_unknown_keys(ctx)
        rule_ignored_global(ctx)
    finally:
        _retail_ignored = saved
    counts: collections.Counter = collections.Counter()
    files: dict[str, set] = collections.defaultdict(set)
    for f in ctx.findings:
        if f.code != "RC072" or f.severity != "warning":
            continue
        key = f.key.rsplit(".", 1)[-1]
        head = f.message.split(" ", 1)[0]
        type_key = head[: -len("." + key)] if head.endswith("." + key) and "::" in head else "*"
        counts[f"{type_key}|{key}"] += 1
        files[f"{type_key}|{key}"].add(f.path)
    result = {"about": "RC072 'present but ignored' keys that retail content carries too, counted per (type key, "
                       "key) over every retail .cls, .prop and .tpl_markup with the validator's walker and "
                       "read-fields tables. validate reports such keys at info. Regenerate with "
                       "roadcraft.validate.count_retail_ignored() after a game update or a read_fields.json change.",
              "generated": time.strftime("%Y-%m-%d"), "retailMembers": len(names),
              "counts": {k: {"occurrences": n, "files": len(files[k])} for k, n in sorted(counts.items())}}
    if out:
        Path(out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        _retail_ignored = None
    return result


# ------------------------------------------------------------------------------------------------ driver

def _read_fields_of(read_fields: Any) -> ReadFields:
    if isinstance(read_fields, ReadFields):
        return read_fields
    if read_fields is None:
        return ReadFields.load()
    return ReadFields.from_data(read_fields)


def validate(target: str | Path, *, rules: Iterable[str] | None = None, game_root: str | Path | None = None,
             read_fields: ReadFields | dict | None = None, notes: list[str] | None = None,
             baseline: str | Path | None = None) -> list[Finding]:
    """Findings for a mod folder or a built .pak (see the module docstring).  ``rules`` limits the rule names
    (``RULES``); ``baseline`` is the installed/older pak or tree existing saves were written with (enables the
    RC077 save-compat rule, which only runs then); ``read_fields`` is the RC072 reader table (:class:`ReadFields`, a read_fields.json-shaped dict, or a
    legacy ``{type key: [fields read]}``); None loads data/read_fields.json when present.  Every finding carries
    its ``member`` path and stable ``id`` (:func:`finding_id`)."""
    selected = set(rules) if rules else set(RULES)
    unknown = selected - set(RULES)
    if unknown:
        raise ValueError(f"unknown rules {sorted(unknown)}; known: {RULES}")
    notes = notes if notes is not None else []
    bundle = open_target(target)
    root = Path(game_root) if game_root else schema_mod.default_game_root()
    retail_view = schema = None
    if (root / "root" / "paks").is_dir():
        retail_view = Retail(root)
    else:
        notes.append(f"no retail paks under {root}: retail references and instance types not checked")
    if schema_mod.sdk_present(root):
        schema = schema_mod.load(root)
    else:
        notes.append(f"no SDK meta descriptions under {root}: unknown-key/type/enum checks skipped")
    fields = _read_fields_of(read_fields)
    if "ignored-fields" in selected and fields.note:
        notes.append(fields.note)
    ctx = Context(bundle, retail_view, schema, selected, fields)
    ctx.game_root = root
    if "objsettings-gate" in selected and not fields.gated:
        notes.append("RC074 objSettings gate table ('gated' in read_fields.json) not loaded: check skipped")
    rule_ps(ctx)
    rule_unknown_keys(ctx)
    rule_ignored_global(ctx)
    rule_engine_defaults(ctx)
    rule_objsettings(ctx)
    rule_duplicates(ctx)
    rule_references(ctx)
    rule_materials(ctx)
    rule_bro(ctx)
    if baseline is not None and "save-compat" in selected:
        rule_save_compat(ctx, Context(open_target(baseline), retail_view, schema, selected, fields))
    checked_markups = set()
    lamp_states: set[str] = set()
    for truck in trucks(ctx):
        lights = (truck.props.get("prop_vehicle_lights_material") or {}) if isinstance(
            truck.props.get("prop_vehicle_lights_material"), dict) else {}
        for light in (lights.get("lights") or {}).values() if isinstance(lights.get("lights"), dict) else ():
            if isinstance(light, dict):
                lamp_states.update({light.get("lightName", "lights"), light.get("defaultName", "default_cc")})
        rule_suspension(ctx, truck)
        rule_wheel_frames(ctx, truck)
        rule_ik_frames(ctx, truck)
        rule_lamps(ctx, truck)
        markup, markup_name = ctx.markup(truck.tpl)
        if isinstance(markup, dict) and markup_name and ctx.bundle.has(markup_name):
            checked_markups.add(markup_name.lower())
            rule_joints(ctx, markup, markup_name, truck.nodes)
            rule_spring_motors(ctx, markup, markup_name, truck.tpl)
    for name in ctx.bundle.names():
        if name.lower().endswith(".bro"):
            doc = ctx.ps(name)
            if isinstance(doc, dict) and isinstance(doc.get("tpl"), str):
                lights = bro_lights(doc)
                if lights:
                    for light in lights.values():
                        lamp_states.update({light.get("lightName", "lights"), light.get("defaultName", "default_cc")})
                    _check_lights(ctx, name, "vehicleLightMaterials.lights", lights, doc["tpl"], ctx.nodes(doc["tpl"]))
    rule_state_pairs(ctx, lamp_states)
    rule_misspelt_states(ctx, lamp_states)
    for name in ctx.bundle.names():
        lower = name.lower()
        if lower.endswith(".tpl_markup") and lower not in checked_markups:
            stem = lower.rsplit("/", 1)[-1][: -len(".tpl_markup")]
            markup, markup_name = ctx.markup(stem)
            if isinstance(markup, dict):
                rule_joints(ctx, markup, name, ctx.nodes(stem))
                rule_spring_motors(ctx, markup, name, stem)
    unique: dict[tuple, Finding] = {}
    for f in ctx.findings:
        unique.setdefault((f.code, f.path, f.line, f.key, f.message), f)
    return _with_ids(bundle, sorted(unique.values(), key=lambda f: (SEVERITY_ROW(f), f.path, f.line or 0, f.code,
                                                                     f.key)))


def _with_ids(bundle: Bundle, findings: list[Finding]) -> list[Finding]:
    """Set ``member`` and ``id``.  Findings sharing (code, member, keyPath) - several RC051 in one file, a rule
    without a key path - are told apart by their order in the file: the first keeps the bare id, later ones get
    ``-2``, ``-3``... (order by line, then message), which survives line shifts that keep their order."""
    staged = [replace(f, member=bundle.member_of(f.path)) for f in findings]
    by_base: dict[str, list[int]] = {}
    for index, f in enumerate(staged):
        by_base.setdefault(finding_id(f.code, f.member, f.key), []).append(index)
    for base, indices in by_base.items():
        ordered = sorted(indices, key=lambda i: (staged[i].line or 0, staged[i].message))
        for rank, index in enumerate(ordered):
            staged[index] = replace(staged[index], id=base if rank == 0 else f"{base}-{rank + 1}")
    return staged


def SEVERITY_ROW(f: Finding) -> int:  # noqa: N802 - sort helper
    return SEVERITY_RANK.get(f.severity, 3)


# ------------------------------------------------------------------------------------------------ report

GROUP_SHOWN = 3


@dataclass(frozen=True)
class TrackedFinding(Finding):
    """A finding labelled against a baseline: ``new``, ``unchanged`` or ``fixed``."""
    status: str = ""


GROUP_BY_KEY_NAME = {"RC072"}      # one group per dead key, wherever it sits


def group_pattern(f: Finding) -> str:
    key = normalise_key(f.key)
    if f.code in GROUP_BY_KEY_NAME and "." in key and "*" not in key:
        return "*." + key.rsplit(".", 1)[-1]
    return key


def group_findings(findings: list[Finding], *, expand: bool = False) -> list[dict[str, Any]]:
    """Findings grouped by (code, severity, keyPath with list indices normalised; for the per-key codes in
    GROUP_BY_KEY_NAME only the last key, ``*.spreadAngle``): count, the first message and fix hint, the number
    of members touched and the first GROUP_SHOWN locations (all with ``expand``)."""
    groups: dict[tuple[str, str, str], list[Finding]] = {}
    for f in findings:
        groups.setdefault((f.code, f.severity, group_pattern(f)), []).append(f)
    out = []
    for (code, _severity, pattern), items in groups.items():
        worst = min(items, key=SEVERITY_ROW)
        shown = items if expand else items[:GROUP_SHOWN]
        statuses: dict[str, int] = {}
        for f in items:
            if isinstance(f, TrackedFinding):
                statuses[f.status] = statuses.get(f.status, 0) + 1
        out.append({
            "code": code, "rule": worst.rule, "severity": worst.severity, "keyPattern": pattern,
            "count": len(items), "members": len({f.member for f in items}),
            "message": items[0].message, "fixHint": next((f.fixHint for f in items if f.fixHint), ""),
            "evidence": items[0].evidence, "statuses": statuses,
            "locations": [{"id": f.id, "path": f.path, "line": f.line, "keyPath": f.key,
                           **({"status": f.status} if isinstance(f, TrackedFinding) else {})} for f in shown],
            "more": len(items) - len(shown),
        })
    return sorted(out, key=lambda g: (SEVERITY_RANK.get(g["severity"], 3), g["code"], -g["count"], g["keyPattern"]))


def compare(current: list[Finding], baseline: list[Finding]) -> tuple[list[TrackedFinding], list[TrackedFinding]]:
    """Label findings by id: current ones ``new`` or ``unchanged``; baseline ones absent now ``fixed``."""
    old = {f.id for f in baseline}
    now = {f.id for f in current}
    labelled = [TrackedFinding(**asdict(f), status="unchanged" if f.id in old else "new") for f in current]
    fixed = [TrackedFinding(**asdict(f), status="fixed") for f in baseline if f.id not in now]
    return labelled, fixed


def report(target: str, findings: list[Finding], notes: list[str], *, expand: bool = False,
           baseline: tuple[str, list[Finding]] | None = None) -> dict[str, Any]:
    """The JSON report of one target (library/validator.md 'Output')."""
    counts = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITIES}
    item: dict[str, Any] = {"target": str(target), "counts": counts, "notes": notes}
    if baseline is not None:
        base_target, base_findings = baseline
        labelled, fixed = compare(findings, base_findings)
        findings = labelled
        status = {s: sum(1 for f in labelled if f.status == s) for s in ("new", "unchanged")}
        status["fixed"] = len(fixed)
        item["baseline"] = {
            "target": str(base_target), "counts": status,
            "newBySeverity": {s: sum(1 for f in labelled if f.status == "new" and f.severity == s)
                              for s in SEVERITIES},
            "fixed": [f.as_dict() for f in fixed],
            "fixedGroups": group_findings(fixed, expand=expand),
        }
    item["groups"] = group_findings(findings, expand=expand)
    item["findings"] = [f.as_dict() for f in findings]
    return item


def exit_code(items: list[dict[str, Any]], fail_on: str) -> int:
    """1 when a finding at or above ``fail_on`` exists; with a baseline only NEW findings count."""
    threshold = SEVERITY_RANK[fail_on]
    for item in items:
        for f in item["findings"]:
            if "baseline" in item and f.get("status") != "new":
                continue
            if SEVERITY_RANK.get(f["severity"], 3) <= threshold:
                return 1
    return 0


def _print_text(item: dict[str, Any]) -> None:
    c = item["counts"]
    print(f"{item['target']}: {c['error']} errors, {c['warning']} warnings, {c['info']} info "
          f"in {len(item['groups'])} groups")
    if "baseline" in item:
        b = item["baseline"]["counts"]
        print(f"  baseline {item['baseline']['target']}: {b['new']} new, {b['fixed']} fixed, "
              f"{b['unchanged']} unchanged")
    for note in item["notes"]:
        print(f"  note: {note}")
    for g in item["groups"]:
        status = ", ".join(f"{n} {s}" for s, n in sorted(g["statuses"].items()))
        print(f"  {g['severity']:7} {g['code']} {g['rule']} x{g['count']} [{g['keyPattern'] or '-'}]"
              + (f" ({status})" if status else ""))
        print(f"          {g['message']}")
        if g["fixHint"]:
            print(f"          fix: {g['fixHint']}")
        for loc in g["locations"]:
            where = loc["path"] + (f":{loc['line']}" if loc["line"] else "") + \
                (f" [{loc['keyPath']}]" if loc["keyPath"] else "")
            print(f"          - {where} #{loc['id']}" + (f" {loc['status']}" if loc.get("status") else ""))
        if g["more"]:
            print(f"          ... {g['more']} more (--expand)")
    if "baseline" in item and item["baseline"]["fixed"]:
        print("  fixed since the baseline:")
        for g in item["baseline"]["fixedGroups"]:
            print(f"  {g['severity']:7} {g['code']} x{g['count']} [{g['keyPattern'] or '-'}] {g['message'][:120]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roadcraft validate",
                                     description="Validate a mod folder or .pak for runtime failures (read-only)")
    parser.add_argument("target", nargs="+", help="mod source folder (p/, mods_source) or .pak")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--rules", default=None, help=f"comma-separated subset of {','.join(RULES)}")
    parser.add_argument("--fail-on", choices=SEVERITIES, default="error",
                        help="exit 1 when a finding at or above this severity exists (default error); with "
                             "--baseline only NEW findings count")
    parser.add_argument("--baseline", default=None,
                        help="an older .pak or tree (the installed version): label findings new/fixed/unchanged by "
                             "id, and run the RC077 save-compat rule against it")
    parser.add_argument("--expand", action="store_true", help="list every location of each group")
    parser.add_argument("--game-root", default=None)
    parser.add_argument("--read-fields", default=None,
                        help="RC072 reader table (read_fields.json schemaVersion 1, or legacy {type: [fields]}); "
                             "default ROADCRAFT_READ_FIELDS or src/roadcraft/data/read_fields.json when present")
    args = parser.parse_args(argv)
    rules = [r.strip() for r in args.rules.split(",") if r.strip()] if args.rules else None
    items: list[dict[str, Any]] = []
    try:
        fields = ReadFields.load(args.read_fields)
        base = None
        if args.baseline:
            base = (args.baseline, validate(args.baseline, rules=rules, game_root=args.game_root, read_fields=fields,
                                            notes=[]))
        for target in args.target:
            notes: list[str] = []
            findings = validate(target, rules=rules, game_root=args.game_root, read_fields=fields, notes=notes,
                                baseline=args.baseline)
            items.append(report(str(target), findings, notes, expand=args.expand, baseline=base))
    except Exception as exc:                                  # noqa: BLE001 - tool error -> exit 2
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(items if len(items) > 1 else items[0], indent=1))
    else:
        for item in items:
            _print_text(item)
    return exit_code(items, args.fail_on)


if __name__ == "__main__":
    sys.exit(main())
