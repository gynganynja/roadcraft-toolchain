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
import hashlib
import json
import os
import posixpath
import re
import sys
import zipfile
from dataclasses import asdict, dataclass, field
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
              "Hook: needs a per-component read-fields table from code (C:/RC_RE/research/physics_semantics.md)"),
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

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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


class Context:
    def __init__(self, bundle: Bundle, retail_view: Retail | None, schema: schema_mod.Schema | None,
                 rules: set[str], read_fields: dict[str, set[str]] | None = None) -> None:
        self.bundle = bundle
        self.retail = retail_view
        self.schema = schema
        self.rules = rules
        self.read_fields = read_fields or {}
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
            evidence: str | None = None) -> None:
        rule = CODES[code][0] if code in CODES else "bro-lint"
        if rule not in self.rules:
            return
        self.findings.append(Finding(rule, severity, path, line, message, evidence or CODES[code][2], code, key))

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
                self.add("RC050", "error", path,
                         (f"exponent notation {detail.split()[0]!r}: the editor reads the number up to 'e' and then a "
                          "new key (a parse error; inside [ ] the value silently becomes [n, \"e\", m]); write it in "
                          "full decimal") if exp else
                         f"{detail.split()[0]!r}: a number followed by letters splits into a number and a new key",
                         line=line)
            elif kind == "leading_dot_number":
                text = detail.split()[0].rstrip(",]}")
                self.add("RC051", "error", path,
                         f"{text!r} is read by the editor as {_leading_dot_value(text)!r}: write a 0 before the point",
                         line=line)
            elif kind == "bare_bool_keyword":
                self.add("RC052", "warning", path,
                         f"bare {detail!r} is read as the bool {detail.lower() in ('on', 'yes')}; quote it if a "
                         "string or enum value was meant", line=line)

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
    def check_members(self, section: dict, type_key: str, path: str, extra: set[str]) -> None:
        schema = self.schema
        owners = {name: type_key for name in schema.member_names(type_key)}
        family = type_key.split("::", 1)[0]
        root = schema.find(schema_mod.FAMILY_ROOTS[family], family) if family in schema_mod.FAMILY_ROOTS else None
        if root and root != type_key:
            # a .cls/.prop/.sso instance also keeps its family root's members (iactor.properties; __useSslClassByBrand)
            for name in schema.member_names(root):
                owners.setdefault(name, root)
        names = set(owners)
        allowed = names | extra | RETAIL_KEYS.get(type_key, frozenset())
        lines = getattr(section, "lines", {})
        for key, value in section.items():
            if key.startswith("__") or key in ("", "#ssl"):
                continue
            here = f"{path}.{key}" if path else key
            line = lines.get(key)
            if key not in allowed:
                hint = difflib.get_close_matches(key, sorted(names), n=1, cutoff=0.75)
                self.ctx.add("RC053", "warning", self.path,
                             f"{key!r} is not a field of {type_key}" + (f"; did you mean {hint[0]!r}?" if hint else "") +
                             " The editor keeps it as a 'removed field' hint and the engine is expected to ignore it.",
                             line=line, key=here)
                continue
            if key not in names:
                continue
            fld = schema.field(owners[key], key)
            if fld is not None:
                read = self.ctx.read_fields.get(type_key)
                if read is not None and key not in read:
                    self.ctx.add("RC072", "warning", self.path, f"{type_key}.{key} is not read by the loader",
                                 line=line, key=here)
                self.check_value(value, fld, here, line, type_key.split("::", 1)[0])

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
                             + shown_default, line=line, key=path)
        elif kind == "string" and isinstance(value, bool):
            self.ctx.add("RC056", "error", self.path,
                         f"a bare yes/no/on/off/true/false became the bool {value}; quote the string{shown_default}",
                         line=line, key=path)
        elif kind == "bool" and isinstance(value, (int, float)) and not isinstance(value, bool) and value not in (0, 1):
            self.ctx.add("RC056", "error", self.path, f"{value!r} is not a bool{shown_default}", line=line, key=path)
        elif kind == "bool" and isinstance(value, str) and value.lower() not in ("true", "false", "1", "0"):
            self.ctx.add("RC056", "error", self.path, f"{value!r} is not a bool{shown_default}", line=line, key=path)
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
    """``<x>_on`` / ``<x>_off`` dynamic states that use the same material in a slot (D11 beacon); one finding per
    markup and state, listing the slots."""
    for name in ctx.bundle.names():
        if not name.lower().endswith(".tpl_markup"):
            continue
        doc = ctx.ps(name)
        materials = doc.get("materials") if isinstance(doc, dict) else None
        if not isinstance(materials, dict):
            continue
        same: dict[str, list[str]] = {}
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
                if lit and unlit and (lit == unlit or _same_material(ctx, lit, unlit)):
                    same.setdefault(state, []).append(slot)
        for state, slots in sorted(same.items()):
            used = state in lamp_states
            ctx.add("RC067", "error" if used else "warning", ctx.bundle.display(name),
                    f"states {state!r} / {state[:-3] + '_off'!r} use identical materials in {len(slots)} slot(s) "
                    f"{slots[:6]}{' ...' if len(slots) > 6 else ''}: switching them shows no change"
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


# ------------------------------------------------------------------------------------------------ driver

def validate(target: str | Path, *, rules: Iterable[str] | None = None, game_root: str | Path | None = None,
             read_fields: dict[str, Iterable[str]] | None = None, notes: list[str] | None = None) -> list[Finding]:
    """Findings for a mod folder or a built .pak (see the module docstring).  ``rules`` limits the rule names
    (``RULES``); ``read_fields`` is the optional per-component table of fields the loader reads (RC072)."""
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
    ctx = Context(bundle, retail_view, schema, selected,
                  {k: set(v) for k, v in (read_fields or {}).items()})
    rule_ps(ctx)
    rule_unknown_keys(ctx)
    rule_duplicates(ctx)
    rule_references(ctx)
    rule_materials(ctx)
    rule_bro(ctx)
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
    unique: dict[tuple, Finding] = {}
    for f in ctx.findings:
        unique.setdefault((f.code, f.path, f.line, f.key, f.message), f)
    return sorted(unique.values(), key=lambda f: (SEVERITY_ROW(f), f.path, f.line or 0, f.code, f.key))


def SEVERITY_ROW(f: Finding) -> int:  # noqa: N802 - sort helper
    return SEVERITY_RANK.get(f.severity, 3)


def _load_read_fields(path: str | None) -> dict[str, list[str]] | None:
    path = path or os.environ.get("ROADCRAFT_READ_FIELDS")
    if not path:
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roadcraft validate",
                                     description="Validate a mod folder or .pak for runtime failures (read-only)")
    parser.add_argument("target", nargs="+", help="mod source folder (p/, mods_source) or .pak")
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    parser.add_argument("--rules", default=None, help=f"comma-separated subset of {','.join(RULES)}")
    parser.add_argument("--fail-on", choices=SEVERITIES, default="error",
                        help="exit 1 when a finding at or above this severity exists (default error)")
    parser.add_argument("--game-root", default=None)
    parser.add_argument("--read-fields", default=None, help="JSON {type key: [fields the loader reads]} (RC072)")
    args = parser.parse_args(argv)
    rules = [r.strip() for r in args.rules.split(",") if r.strip()] if args.rules else None
    report: list[dict[str, Any]] = []
    worst = 3
    try:
        read_fields = _load_read_fields(args.read_fields)
        for target in args.target:
            notes: list[str] = []
            findings = validate(target, rules=rules, game_root=args.game_root, read_fields=read_fields, notes=notes)
            counts = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITIES}
            worst = min([worst] + [SEVERITY_RANK[f.severity] for f in findings])
            report.append({"target": str(target), "counts": counts, "notes": notes,
                           "findings": [f.as_dict() for f in findings]})
    except Exception as exc:                                  # noqa: BLE001 - tool error -> exit 2
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report if len(report) > 1 else report[0], indent=1))
    else:
        for item in report:
            print(f"{item['target']}: {item['counts']['error']} errors, {item['counts']['warning']} warnings, "
                  f"{item['counts']['info']} info")
            for note in item["notes"]:
                print(f"  note: {note}")
            for f in item["findings"]:
                where = f["path"] + (f":{f['line']}" if f["line"] else "") + (f" [{f['key']}]" if f["key"] else "")
                print(f"  {f['severity']:7} {f['code']} {f['rule']}: {where}\n          {f['message']}")
    return 1 if worst <= SEVERITY_RANK[args.fail_on] else 0


if __name__ == "__main__":
    sys.exit(main())
