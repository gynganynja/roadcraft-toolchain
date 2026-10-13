"""The Mod Editor's type schema: every component type and field, with defaults, ranges, units and enums.

The Mod Editor (IntegrationStudio) builds its whole data model from plain-text PS files in the SDK
(C:\\RC_RE\\research\\schema.md section 1; grade SDK, from the decompiled editor):

* ``root/prebuild/meta_descs/meta_desc.ps``: engine/editor types (``prop_base``, ``iactor``, ``tpl_markup``...);
* ``root/prebuild/meta_descs/meta_desc_ssl.ps``: SSL script classes, each also registered under its brand
  (``PropTruckWheel`` -> ``.prop::prop_truck_wheel``), where most vehicle component fields live;
* ``tools/bin/ModEditor/meta_desc_ssl_overrides.ps`` (+ ``root/prebuild/meta_descs/meta_desc_ssl_overrides.ps``
  and ``meta_desc_ssl_user.ps`` when present): deep-merged into the SSL descriptions first;
* ``root/prebuild/meta_descs/meta_desc_bro.ps``: the designer-wizard (``.bro``) types;
* ``resources_schema.yaml`` inside ``root/paks/client/resources.pak``: blobs and links of every ``res_desc_*``.

:class:`Schema` resolves inheritance the way the editor does (``__type`` chains, brand/SSL merging, member
re-declaration, type-level ``__defaultValue`` overrides) and answers "which fields does type T have, of
what kind, default, range, units and enum".  Ranges and units are UI hints the editor does not enforce
(schema.md section 3).  :func:`dump` writes deterministic JSON (sorted keys, no timestamps) with the same
layout and counts as the research prototype ``C:\\RC_RE\\research\\dump_schema.py`` (24,382 types,
27,763 declared fields, 264,406 with inheritance, 98 resource descriptor types on the 2026-10-13 SDK).

Read-only and standard library only.  ``python -m roadcraft.schema dump --output schema.json``,
``... show tpl_markup_constraint_hinge.angleEnd``, ``... search suspension``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterator

from .ps_format import editor_loads

DEFAULT_GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\RoadCraft")

# Saber.ModelTree OptiBasicModels / TypeHelper.IsBuildInType
BUILTIN = frozenset({
    "section", "collection", "uniformCollection", "exclusiveCollection", "mod", "optional", "array", "string",
    "bool", "int", "float", "enum", "null", "error", "spline", "colorspline", "colorsplinesep", "vec3", "vec4",
    "debugSection",
})
SSL_NS = ".ssl"
GLOBAL = "!global"
FAMILY_ROOTS = {".cls": "iactor", ".prop": "prop_base", ".sso": "ssl_object"}

VIEW_KEYS = {
    "__caption": "caption", "__hint": "hint", "__category": "category", "__units": "units", "__min": "min",
    "__max": "max", "__step": "step", "__precision": "precision", "__dynRange": "dyn_range",
    "__dynMin": "dyn_min", "__dynMax": "dyn_max", "__minX": "min_x", "__maxX": "max_x", "__minY": "min_y",
    "__maxY": "max_y", "__readOnly": "read_only", "__hidden": "hidden", "__hiddenIn": "hidden_in",
    "__visibleIf": "visible_if", "__request": "link_request", "__manualEdit": "manual_edit",
    "__localized": "localized", "__type": "widget",
}
FIELD_KEYS = {
    "__typeEngine": "type_engine", "__ptr": "ptr", "__family": "ptr_family", "__nullable": "nullable",
    "__smart_ptr": "smart_ptr", "__fixedSize": "fixed_size", "__removeFromEngineBin": "remove_from_engine_bin",
    "__deprecated": "deprecated", "__saveAlways": "save_always", "__skipDefault": "skip_default",
    "__isAbstract": "abstract", "__allowAbstractTypes": "allow_abstract_types", "__linkTag": "link_tag",
    "__resource": "resource", "__path": "path", "__units": "units", "__min": "min", "__max": "max",
    "__require": "require",
}
TYPE_KEYS = (("__isAbstract", "abstract"), ("__isStruct", "struct"), ("__typeEngine", "type_engine"),
             ("__smart_ptr", "smart_ptr"), ("__version", "version"), ("__moduleName", "ssl_module"),
             ("__resourceTag", "resource_tag"), ("__deprecated", "deprecated"),
             ("__useSslClassByBrand", "use_ssl_class_by_brand"), ("__namespace", "namespace"),
             ("__libType", "lib_type"), ("__skipDefault", "skip_default"),
             ("__useAsDefaultType", "use_as_default_type"))


class SchemaError(LookupError):
    """The SDK's schema files are not where they should be."""


# ------------------------------------------------------------------------------------------------ helpers

def saber_merge(dst: dict, src: dict) -> dict:
    """PsSection.MergeSection / SaberMerge: sections merge recursively, scalars and arrays replace."""
    for key, value in src.items():
        if key not in dst:
            dst[key] = _clone(value)
        elif isinstance(value, dict) and isinstance(dst[key], dict):
            saber_merge(dst[key], value)
        elif not isinstance(value, dict):
            dst[key] = _clone(value)
    return dst


def _clone(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clone(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clone(v) for v in value]
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def brand_class_name(brand: str) -> str:
    """SSLUtils.ConvertBrandToClassName: ``prop_truck_wheel`` -> ``PropTruckWheel``."""
    def merge(parts: list[str]) -> str:
        if len(parts) <= 1:
            return parts[0] if parts else ""
        a, b = merge(parts[: len(parts) // 2]), merge(parts[len(parts) // 2:])
        return a + "_" + b if a and b and a[-1].isdigit() and b[0].isdigit() else a + b

    def part(text: str) -> str:
        bits = [p for p in text.replace("::", "_").split("_") if p]
        return merge([p[0].upper() + p[1:].lower() for p in bits])
    return "_".join(part(p) for p in brand.split("|"))


# ------------------------------------------------------------------------------------------------ YAML

def _yaml_scalar(text: str) -> Any:
    text = text.strip()
    if not text:
        return None
    if text[0] == "'" and text.endswith("'") and len(text) > 1:
        return text[1:-1].replace("''", "'")
    if text[0] == '"' and text.endswith('"') and len(text) > 1:
        return json.loads(text) if "\\" in text else text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [_yaml_scalar(p) for p in _split_flow(inner)] if inner else []
    if text == "{}":
        return {}
    return text


def _split_flow(text: str) -> list[str]:
    parts, depth, quote, start = [], 0, "", 0
    for i, c in enumerate(text):
        if quote:
            if c == quote:
                quote = ""
        elif c in "'\"":
            quote = c
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [p.strip() for p in parts]


def yaml_loads(text: str) -> Any:
    """The block-YAML subset the SDK writes (resource descriptors, ``.mod``, ``resources_schema.yaml``):
    mappings, ``-`` sequences (also at the parent key's indent), flow lists, quoted and folded plain
    scalars, full-line comments.  Scalars stay strings."""
    rows: list[tuple[int, str]] = []
    for raw in text.lstrip("\ufeff").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        rows.append((len(raw) - len(raw.lstrip(" ")), raw.strip()))
    pos = 0

    def parse_block(indent: int) -> Any:
        nonlocal pos
        if pos >= len(rows):
            return None
        if rows[pos][1].startswith("- ") or rows[pos][1] == "-":
            return parse_seq(rows[pos][0])
        return parse_map(rows[pos][0])

    def continuation(value: str, indent: int) -> str:
        nonlocal pos
        while pos < len(rows) and rows[pos][0] > indent and not rows[pos][1].startswith("- ") \
                and not _is_key(rows[pos][1]):
            value += " " + rows[pos][1]
            pos += 1
        return value

    def parse_map(indent: int) -> dict:
        nonlocal pos
        out: dict[str, Any] = {}
        while pos < len(rows) and rows[pos][0] == indent and not rows[pos][1].startswith("- "):
            line = rows[pos][1]
            key, _, rest = line.partition(":")
            key = _yaml_scalar(key) or ""
            pos += 1
            rest = rest.strip()
            if rest:
                out[key] = _yaml_scalar(continuation(rest, indent))
            elif pos < len(rows) and (rows[pos][0] > indent or (rows[pos][0] == indent and rows[pos][1].startswith("- "))):
                out[key] = parse_block(rows[pos][0])
            else:
                out[key] = None
        return out

    def parse_seq(indent: int) -> list:
        nonlocal pos
        out: list[Any] = []
        while pos < len(rows) and rows[pos][0] == indent and (rows[pos][1].startswith("- ") or rows[pos][1] == "-"):
            item = rows[pos][1][1:].strip()
            if not item:
                pos += 1
                out.append(parse_block(rows[pos][0]) if pos < len(rows) and rows[pos][0] > indent else None)
            elif _is_key(item):
                # "- key: value" starts a mapping whose keys sit at indent + 2
                rows[pos] = (indent + 2, item)
                out.append(parse_map(indent + 2))
            else:
                pos += 1
                out.append(_yaml_scalar(continuation(item, indent)))
        return out

    return parse_block(rows[0][0]) if rows else None


def _is_key(text: str) -> bool:
    if text[:1] in "'\"[{":
        return False
    key, sep, rest = text.partition(":")
    return bool(sep) and (not rest or rest[0] == " ") and " " not in key.strip()


# ------------------------------------------------------------------------------------------------ type database

class _TypeDB:
    def __init__(self) -> None:
        self.types: dict[tuple[str, str], dict[str, Any]] = {}
        self.by_name: dict[str, list[dict[str, Any]]] = {}

    def add(self, family: str, name: str, desc: dict, source: str, slot: str) -> None:
        rec = self.types.get((family, name))
        if rec is None:
            rec = self.types[(family, name)] = {"family": family, "name": name, "slots": {}, "sources": []}
            self.by_name.setdefault(name, []).append(rec)
        rec["slots"][slot] = desc
        rec["sources"].append(source)

    def find(self, name: str, ns: str | None) -> dict[str, Any] | None:
        """ClassDataBaseExtension.FindInfoAuto: (name, ns) then (name, !global); then (Inferred) .ssl and .bro,
        because brand/bro descriptions name SSL structs."""
        if ns and (ns, name) in self.types:
            return self.types[(ns, name)]
        if (GLOBAL, name) in self.types:
            return self.types[(GLOBAL, name)]
        for fallback in (SSL_NS, ".bro"):
            if fallback != ns and (fallback, name) in self.types:
                return self.types[(fallback, name)]
        if not ns:
            recs = self.by_name.get(name)
            if recs:
                return recs[0]
        return None


def _family_of_plain(top: dict, name: str) -> str:
    """PlainLibFileParser: ``__family``, else the one found along the ``__type`` chain in the file."""
    seen: list[str] = []
    desc = top[name]
    family = desc.get("__family") if isinstance(desc, dict) else None
    while not family:
        parent = desc.get("__type") if isinstance(desc, dict) else None
        if not parent or parent in seen:
            break
        seen.append(parent)
        desc = top.get(parent)
        if not isinstance(desc, dict):
            break
        family = desc.get("__family")
    return family or GLOBAL


def _prepare_ssl_desc(desc: dict) -> None:
    """SslMergeableDataParser.PrepareSslDesc: SSL member/element/local types get ``__namespace = .ssl``."""
    targets: list[Any] = [desc.get("__elementType")]
    for key in ("__members", "__types"):
        if isinstance(desc.get(key), dict):
            targets += list(desc[key].values())
    for item in targets:
        if not isinstance(item, dict):
            continue
        kind = item.get("__type")
        if kind and (kind not in BUILTIN or item.get("__family") == SSL_NS):
            item.setdefault("__namespace", SSL_NS)
        _prepare_ssl_desc(item)


def _merged_desc(rec: dict, ssl_families: set[str]) -> tuple[dict, str]:
    cls, ssl = rec["slots"].get("class"), rec["slots"].get("ssl")
    if cls is None:
        return _clone(ssl), "ssl"
    if ssl is None:
        return _clone(cls), "class"
    if rec["family"] in ssl_families:      # MergeMembersToClass: class keeps __type, SSL members on top
        out, keep = _clone(cls), cls.get("__type")
        saber_merge(out, ssl)
        mode = "class+ssl"
    else:                                   # SslMetaDataParser.MergeData: SSL base, class over it
        out, keep = _clone(ssl), ssl.get("__type")
        saber_merge(out, cls)
        mode = "ssl+class"
    if keep is not None:
        out["__type"] = keep
    return out, mode


def _view_info(desc: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    view = desc.get("__viewType")
    if isinstance(view, str):
        out["widget"] = view
        view = {}
    if isinstance(view, dict):
        for key, name in VIEW_KEYS.items():
            if key in view:
                out[name] = _plain(view[key])
        if "__items" in view:
            out["enum_labels"] = _plain(view["__items"])
        extra = {k: _plain(v) for k, v in view.items() if k not in VIEW_KEYS and k != "__items"}
        if extra:
            out["view_extra"] = extra
    for key in ("__min", "__max", "__units", "__step"):
        if key in desc and VIEW_KEYS[key] not in out:
            out[VIEW_KEYS[key]] = _plain(desc[key])
    return out


SOURCE_FILES = {
    "meta_desc": ("root", "prebuild", "meta_descs", "meta_desc.ps"),
    "meta_desc_ssl": ("root", "prebuild", "meta_descs", "meta_desc_ssl.ps"),
    "meta_desc_bro": ("root", "prebuild", "meta_descs", "meta_desc_bro.ps"),
    "ssl_overrides_common": ("tools", "bin", "ModEditor", "meta_desc_ssl_overrides.ps"),
    "ssl_overrides_project": ("root", "prebuild", "meta_descs", "meta_desc_ssl_overrides.ps"),
    "meta_desc_ssl_user": ("root", "prebuild", "meta_descs", "meta_desc_ssl_user.ps"),
}
RESOURCES_PAK = ("root", "paks", "client", "resources.pak")


def source_paths(game_root: str | Path) -> dict[str, Path]:
    root = Path(game_root)
    return {key: root.joinpath(*parts) for key, parts in SOURCE_FILES.items()}


def sdk_present(game_root: str | Path | None = None) -> bool:
    paths = source_paths(game_root or default_game_root())
    return all(paths[k].is_file() for k in ("meta_desc", "meta_desc_ssl", "meta_desc_bro"))


def default_game_root() -> Path:
    env = os.environ.get("ROADCRAFT_GAME_ROOT")
    return Path(env) if env else DEFAULT_GAME_ROOT


# ------------------------------------------------------------------------------------------------ Schema

class Schema:
    """The resolved type schema.  Build with :func:`load` (cached per installation and file stamps)."""

    def __init__(self, game_root: str | Path, log: Callable[[str], None] | None = None) -> None:
        self.game_root = Path(game_root)
        self.paths = source_paths(self.game_root)
        log = log or (lambda _msg: None)
        if not all(self.paths[k].is_file() for k in ("meta_desc", "meta_desc_ssl", "meta_desc_bro")):
            raise SchemaError(f"meta_desc*.ps not found under {self.game_root}")
        self.data: dict[str, dict | None] = {}
        for key, path in self.paths.items():
            self.data[key] = editor_loads(path.read_text(encoding="utf-8-sig", errors="replace"), lines=False) \
                if path.is_file() else None
            log(f"{key}: {'absent' if self.data[key] is None else len(self.data[key])} <- {path}")
        self.resource_descs = self._load_resource_schema()
        self._db, self.ssl_families, self.brand_map = self._build()
        self._merged: dict[tuple[str, str], tuple[dict, str]] = {}
        self._flat: dict[tuple[str, str], dict[str, tuple[dict, str]]] = {}
        self._fields: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._document: dict[str, Any] | None = None

    # ---- construction
    def _load_resource_schema(self) -> dict[str, Any] | None:
        pak = self.game_root.joinpath(*RESOURCES_PAK)
        if not pak.is_file():
            return None
        with zipfile.ZipFile(pak) as archive:
            name = next((n for n in archive.namelist() if n.lower().endswith("resources_schema.yaml")), None)
            if not name:
                return None
            doc = yaml_loads(archive.read(name).decode("utf-8", "replace")) or {}
        out: dict[str, Any] = {}
        for item in doc.get("types") or []:
            refs: dict[str, Any] = {}
            for ref in item.get("refs") or []:
                attrs = {}
                for attr in ref.get("attrs") or []:
                    attrs[attr.get("name")] = attr.get("args", True)
                refs[ref.get("name")] = attrs
            entry: dict[str, Any] = {"parent": item.get("parent") or item.get("base"),
                                     "blobs": item.get("blobs") or [], "refs": refs}
            for key in ("platforms", "launch_modes", "display_modes", "configurations"):
                if item.get(key):
                    entry[key] = item[key]
            out[item.get("name")] = entry
        return out

    def _build(self) -> tuple[_TypeDB, set[str], dict[str, str]]:
        db = _TypeDB()
        md = self.data["meta_desc"] or {}
        for name, desc in md.items():
            if isinstance(desc, dict):
                db.add(_family_of_plain(md, name), name, desc, "meta_desc.ps", "class")
        ssl_families = {d["__family"] for d in md.values()
                        if isinstance(d, dict) and d.get("__family") and d["__family"] != SSL_NS
                        and (d.get("__namespace") == SSL_NS or d.get("__type") == "sslClass")}
        overrides: dict[str, Any] = {}
        for key in ("ssl_overrides_common", "ssl_overrides_project"):
            if self.data.get(key):
                saber_merge(overrides, self.data[key])
        ssl = _clone(self.data["meta_desc_ssl"] or {})
        saber_merge(ssl, overrides)
        if self.data.get("meta_desc_ssl_user"):
            saber_merge(ssl, self.data["meta_desc_ssl_user"])
        brand_map: dict[str, str] = {}
        for name, desc in ssl.items():
            if not isinstance(desc, dict) or not desc:
                continue
            _prepare_ssl_desc(desc)
            db.add(SSL_NS, name, desc, "meta_desc_ssl.ps", "ssl")
            extra = desc.get("__extraData") or {}
            brand, family = extra.get("__sslBrandName"), extra.get("__sslBrandFamily")
            if brand and family and family != SSL_NS:
                part = extra.get("__sslBrandPart") or ""
                tname = brand
                if part:
                    tname = f"{brand}::{part}"
                    if family.endswith("lib"):
                        family = family[:-3]
                db.add(family, tname, desc, "meta_desc_ssl.ps#brand:" + name, "ssl")
                brand_map[f"{family}:{tname}"] = name
        for name, desc in (self.data["meta_desc_bro"] or {}).items():
            if isinstance(desc, dict):
                db.add(desc.get("__family", ".bro"), name, desc, "meta_desc_bro.ps", "class")
        return db, ssl_families, brand_map

    # ---- resolution
    def _desc(self, rec: dict) -> dict:
        key = (rec["family"], rec["name"])
        if key not in self._merged:
            self._merged[key] = _merged_desc(rec, self.ssl_families)
        return self._merged[key][0]

    def _parent(self, rec: dict, desc: dict | None = None) -> dict | None:
        desc = self._desc(rec) if desc is None else desc
        kind = desc.get("__type")
        if not kind or kind in BUILTIN:
            return None
        found = self._db.find(kind, desc.get("__namespace", rec["family"]))
        if found is None and "ssl" in rec["slots"]:
            found = self._db.find(kind, SSL_NS)
        if found is not None and found["family"] == SSL_NS and rec["family"] != SSL_NS:
            # [Inferred] prefer the parent's brand registration in the same family, so .prop::prop_truck_rb
            # inherits .prop::prop_truck (engine members such as suspensionAxleCollection)
            extra = self._desc(found).get("__extraData") or {}
            if extra.get("__sslBrandFamily") == rec["family"] and extra.get("__sslBrandName"):
                brand = self._db.types.get((rec["family"], extra["__sslBrandName"]))
                if brand is not None and brand is not rec:
                    found = brand
        if found is rec:
            for other in self._db.by_name.get(kind, []):
                if other is not rec:
                    return other
            return None
        return found

    def _chain(self, rec: dict) -> list[dict]:
        out, seen, cur = [], set(), rec
        while cur is not None and id(cur) not in seen:
            seen.add(id(cur))
            out.append(cur)
            cur = self._parent(cur)
        return out

    def _base_kind(self, rec: dict) -> str:
        kind = self._desc(self._chain(rec)[-1]).get("__type")
        return kind if kind in BUILTIN else ("unresolved:" + str(kind) if kind else "none")

    def _kind_of_ref(self, name: Any, ns: str | None) -> str | None:
        if not name:
            return None
        if name in BUILTIN:
            return name
        rec = self._db.find(name, ns)
        return "unresolved" if rec is None else self._base_kind(rec)

    def _flat_members(self, rec: dict) -> dict[str, tuple[dict, str]]:
        """Members incl. inherited (DefaultModelTreeBuilder.BuildSectionModel order)."""
        key = (rec["family"], rec["name"])
        if key in self._flat:
            return self._flat[key]
        self._flat[key] = {}           # cycle guard
        desc = self._desc(rec)
        parent = self._parent(rec, desc)
        members: dict[str, tuple[dict, str]] = {}
        if parent is not None:
            for name, (md, origin) in self._flat_members(parent).items():
                members[name] = (md, origin)
        own = desc.get("__members")
        if isinstance(own, dict):
            for name, md in own.items():
                if not isinstance(md, dict):
                    continue
                if name in members:
                    old = members[name][0]
                    kind = md.get("__type")
                    if kind and kind != old.get("__type"):
                        members[name] = (md, rec["name"])
                    else:
                        merged = _clone(old)
                        saber_merge(merged, md)
                        members[name] = (merged, rec["name"])
                else:
                    members[name] = (md, rec["name"])
        defaults = desc.get("__defaultValue")
        if isinstance(defaults, dict):
            for name, value in defaults.items():
                if name in members and not name.startswith("__"):
                    md, origin = members[name]
                    md = dict(md)
                    md["__x_default_from_type"] = rec["name"]
                    md["__defaultValue"] = value
                    members[name] = (md, origin)
        self._flat[key] = members
        return members

    def _field(self, md: dict, owner_ns: str, declared_in: str) -> dict[str, Any]:
        f: dict[str, Any] = {}
        kind = md.get("__type")
        ns = md.get("__namespace", owner_ns)
        f["type"] = kind
        if md.get("__namespace"):
            f["namespace"] = md["__namespace"]
        f["kind"] = self._kind_of_ref(kind, ns)
        f["declared_in"] = declared_in
        for key, name in FIELD_KEYS.items():
            if key in md:
                f[name] = _plain(md[key])
        if "__defaultValue" in md:
            f["default"] = _plain(md["__defaultValue"])
        if "__x_default_from_type" in md:
            f["default_from_type"] = md["__x_default_from_type"]
        if "__items" in md:
            f["enum_items"] = _plain(md["__items"])
        if "__aliases" in md:
            f["enum_aliases"] = _plain(md["__aliases"])
        f.update(_view_info(md))
        if f["kind"] == "enum" and "enum_items" not in f and kind and kind not in BUILTIN:
            rec = self._db.find(kind, ns)
            if rec is not None:
                enum_desc = self._desc(rec)
                if "__items" in enum_desc:
                    f["enum_items"] = _plain(enum_desc["__items"])
                    if "default" not in f and "__defaultValue" in enum_desc:
                        f["default"] = _plain(enum_desc["__defaultValue"])
        if isinstance(md.get("__elementType"), dict):
            f["element"] = self._field(md["__elementType"], ns, declared_in)
        if isinstance(md.get("__internalTypes"), dict):
            f["internal_types"] = list(md["__internalTypes"].keys())
        if isinstance(md.get("__types"), dict):
            f["local_types"] = list(md["__types"].keys())
        return f

    # ---- public lookups
    def find(self, name: str, family: str | None = None) -> str | None:
        """``<family>::<name>`` of a type as the editor resolves it (``family`` = the namespace looked in)."""
        rec = self._db.find(name, family)
        return None if rec is None else f"{rec['family']}::{rec['name']}"

    def _rec(self, type_key: str) -> dict[str, Any]:
        family, _, name = type_key.partition("::")
        rec = self._db.types.get((family, name))
        if rec is None:
            raise KeyError(type_key)
        return rec

    def __contains__(self, type_key: str) -> bool:
        family, _, name = type_key.partition("::")
        return (family, name) in self._db.types

    def type_keys(self) -> list[str]:
        return [f"{f}::{n}" for f, n in sorted(self._db.types, key=lambda k: (k[0], k[1].lower()))]

    def chain(self, type_key: str) -> list[str]:
        return [f"{r['family']}::{r['name']}" for r in self._chain(self._rec(type_key))]

    def kind(self, type_key: str) -> str:
        return self._base_kind(self._rec(type_key))

    def enum_items(self, type_key: str) -> list[Any] | None:
        items = self._desc(self._rec(type_key)).get("__items")
        return _plain(items) if items is not None else None

    def member_names(self, type_key: str) -> list[str]:
        return list(self._flat_members(self._rec(type_key)))

    def field(self, type_key: str, name: str) -> dict[str, Any] | None:
        """One field of a type, inherited ones included: type, kind, default, min/max, units, enum, doc..."""
        cache_key = (type_key, name, "")
        if cache_key not in self._fields:
            rec = self._rec(type_key)
            entry = self._flat_members(rec).get(name)
            if entry is None:
                return None
            md, origin = entry
            self._fields[cache_key] = self._field(md, md.get("__namespace", rec["family"]), origin)
        return self._fields[cache_key]

    def fields(self, type_key: str) -> dict[str, dict[str, Any]]:
        return {name: self.field(type_key, name) for name in self.member_names(type_key)}  # type: ignore[misc]

    def lookup(self, name: str, family: str | None = None) -> dict[str, Any] | None:
        """``{"key", "family", "name", "parent", "chain", "kind", "enum_items", "fields"}`` or None."""
        key = name if "::" in name and name in self else self.find(name, family)
        if key is None:
            return None
        desc = self._desc(self._rec(key))
        return {"key": key, "family": key.split("::", 1)[0], "name": key.split("::", 1)[1],
                "parent": desc.get("__type"), "chain": self.chain(key), "kind": self.kind(key),
                "enum_items": self.enum_items(key), "fields": self.fields(key)}

    # ---- export
    def document(self) -> dict[str, Any]:
        """The schema as JSON-ready data (layout of the research prototype's schema.json, without its timestamp)."""
        if self._document is not None:
            return self._document
        types_out: dict[str, Any] = {}
        stats: Counter = Counter()
        families: Counter = Counter()
        for (family, name), rec in sorted(self._db.types.items(), key=lambda kv: (kv[0][0], kv[0][1].lower())):
            desc = self._desc(rec)
            parent = self._parent(rec, desc)
            kind = self._base_kind(rec)
            extra = desc.get("__extraData") if isinstance(desc.get("__extraData"), dict) else {}
            t: dict[str, Any] = {"name": name, "family": family, "sources": list(rec["sources"]),
                                 "merge": self._merged[(family, name)][1], "parent": desc.get("__type")}
            if parent is not None:
                t["parent_ref"] = f"{parent['family']}::{parent['name']}"
            t["kind"] = kind
            t["chain"] = [f"{r['family']}::{r['name']}" for r in self._chain(rec)]
            for key, out_key in TYPE_KEYS:
                if key in desc:
                    t[out_key] = _plain(desc[key])
            if extra.get("__sslBrandName"):
                t["ssl_brand"] = {"name": extra.get("__sslBrandName"), "family": extra.get("__sslBrandFamily"),
                                  "part": extra.get("__sslBrandPart", "")}
            if "__items" in desc:
                t["enum_items"] = _plain(desc["__items"])
            if "__aliases" in desc:
                t["enum_aliases"] = _plain(desc["__aliases"])
            if "__defaultValue" in desc:
                t["default"] = _plain(desc["__defaultValue"])
            if isinstance(desc.get("__elementType"), dict):
                t["element"] = self._field(desc["__elementType"], desc.get("__namespace", family), name)
            t.update(_view_info(desc))
            if isinstance(desc.get("__animatables"), dict):
                t["animatables"] = list(desc["__animatables"].keys())
            members: dict[str, Any] = {}
            all_members: dict[str, str] = {}
            default_overrides: dict[str, Any] = {}
            for member, (md, origin) in self._flat_members(rec).items():
                all_members[member] = origin
                stats["fields_total"] += 1
                if origin != name and md.get("__x_default_from_type") == name:
                    default_overrides[member] = _plain(md["__defaultValue"])
                if origin != name:
                    continue
                f = self._field(md, md.get("__namespace", family), origin)
                members[member] = f
                stats["fields_declared"] += 1
                for key in ("units", "min", "max", "default", "enum_items", "hint", "caption", "type_engine"):
                    if key in f:
                        stats["declared_with_" + key] += 1
                if str(f.get("kind", "")).startswith("unresolved"):
                    stats["declared_unresolved_type"] += 1
            t["all_members"] = all_members
            if default_overrides:
                t["default_overrides"] = default_overrides
            t["members"] = members
            types_out[f"{family}::{name}"] = t
            stats["types"] += 1
            stats["kind:" + kind] += 1
            families[family] += 1
        roots: dict[str, list[str]] = {}
        for t in types_out.values():
            parent_ref = t.get("parent_ref")
            if not parent_ref or parent_ref.split("::", 1)[0] != t["family"]:
                roots.setdefault(t["family"], []).append(t["name"])
        counts = dict(stats)
        if self.resource_descs:
            counts["resource_desc_types"] = len(self.resource_descs)
        self._document = {
            "meta": {
                "generator": "roadcraft.schema",
                "sources": {k: (str(p) if self.data.get(k) is not None else None) for k, p in self.paths.items()},
                "notes": [
                    "Type key = '<family>::<name>'. '.ssl' = SSL script classes; '!global' = engine structs/enums.",
                    "A '<name><ext>' mod file defines type <name> in family <ext>, parent = its __type or the "
                    "family root (.cls -> iactor). A .cls 'properties' section is an exclusiveCollection of .prop "
                    "types keyed by type name.",
                    "'members' = fields this type declares; 'all_members' = every field incl. inherited -> "
                    "declaring type; 'default_overrides' = inherited defaults changed by this type.",
                    "min/max/step/units are UI hints; the editor does not enforce them on load.",
                ],
                "ssl_families": sorted(self.ssl_families),
                "brand_map_count": len(self.brand_map),
            },
            "counts": counts,
            "families": {f: {"types": families[f], "roots": sorted(roots.get(f, []))[:50]} for f in families},
            "brand_map": dict(self.brand_map),
            "resource_descs": self.resource_descs,
            "types": types_out,
        }
        return self._document

    @property
    def counts(self) -> dict[str, int]:
        return dict(self.document()["counts"])

    def dump(self, path: str | Path) -> Path:
        path = Path(path)
        text = json.dumps(self.document(), sort_keys=True, indent=1, ensure_ascii=False)
        path.write_text(text + "\n", encoding="utf-8", newline="\n")
        return path


_CACHE: dict[tuple, Schema] = {}


def _stamp(game_root: Path) -> tuple:
    out = [str(game_root.resolve())]
    paths = list(source_paths(game_root).values()) + [game_root.joinpath(*RESOURCES_PAK)]
    for path in paths:
        try:
            info = path.stat()
            out.append((path.name, info.st_size, info.st_mtime_ns))
        except OSError:
            out.append((path.name, None))
    return tuple(out)


def load(game_root: str | Path | None = None, log: Callable[[str], None] | None = None) -> Schema:
    """The schema of an installation (default: ``ROADCRAFT_GAME_ROOT`` or the Steam path), cached in-process
    until a source file changes."""
    root = Path(game_root) if game_root else default_game_root()
    key = _stamp(root)
    if key not in _CACHE:
        _CACHE.clear()
        _CACHE[key] = Schema(root, log)
    return _CACHE[key]


def dump(path: str | Path, game_root: str | Path | None = None) -> Path:
    """Write the schema JSON (sorted keys, stable ordering, no timestamps)."""
    return load(game_root).dump(path)


# Where values of a family's types are written (schema.md sections 1.3, 4.1).
SERIALISED_TO = {
    ".cls": ".cls files (ssl/*.cls); root type iactor, components under 'properties'",
    ".prop": "a component section under a .cls 'properties' block, keyed by the type name (also .prop files)",
    ".sso": ".sso files (SSL objects)",
    ".ssl": "nested sections inside .cls/.sso/.prop files, selected by __type (SSL script structs)",
    ".bro": ".bro designer-wizard files (mods_source/bro/...), compiled by the generator into auto_*.cls",
    ".tpl_markup": ".tpl_markup files (merged over tpl/<model>.lods_base), e.g. objectInfos[].entities[]",
    ".obj_settings": ".tpl_markup objSettings.settings.<object>",
    ".resource": "YAML *.resource descriptors",
    "!global": "nested engine structs/enums inside any PS file",
}


def serialised_to(type_key: str) -> str:
    family = type_key.split("::", 1)[0]
    return SERIALISED_TO.get(family, f"{family} files or nested sections of that family")


def show(schema: Schema, query: str, family: str | None = None) -> dict[str, Any] | None:
    """``Type`` or ``Type.field`` (``Type`` may be ``<family>::<name>``): fields with type, default, range, units,
    enum values and doc, plus the file the type is serialised to."""
    field_name = None
    head, sep, tail = query.partition("::")
    name = tail if sep else head
    if "." in name:
        name, field_name = name.split(".", 1)
    key = f"{head}::{name}" if sep else None
    info = schema.lookup(key or name, None if key else family)
    if info is None:
        return None
    info["serialisedTo"] = serialised_to(info["key"])
    if field_name is not None:
        fld = info["fields"].get(field_name)
        if fld is None:
            import difflib
            return {"key": info["key"], "field": field_name, "error": "no such field",
                    "didYouMean": difflib.get_close_matches(field_name, list(info["fields"]), n=3)}
        return {"key": info["key"], "field": field_name, "serialisedTo": info["serialisedTo"], **fld}
    return info


def search(schema: Schema, text: str, limit: int = 50) -> list[dict[str, Any]]:
    """Types and fields whose name, caption or hint contains ``text`` (case-insensitive)."""
    needle = text.lower()
    out: list[dict[str, Any]] = []
    doc = schema.document()["types"]
    for key in schema.type_keys():
        t = doc[key]
        if needle in t["name"].lower() or needle in str(t.get("caption", "")).lower():
            out.append({"key": key, "kind": t["kind"], "serialisedTo": serialised_to(key)})
        for member, f in t["members"].items():
            if needle in member.lower() or needle in str(f.get("caption", "")).lower():
                row = {"key": f"{key}.{member}", "type": f.get("type"), "kind": f.get("kind")}
                for k in ("default", "min", "max", "units", "enum_items", "caption"):
                    if k in f:
                        row[k] = f[k]
                out.append(row)
        if len(out) >= limit:
            break
    return out[:limit]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="roadcraft schema", description="Export or query the Mod Editor type schema")
    parser.add_argument("--game-root", default=None, help="RoadCraft install folder (default: ROADCRAFT_GAME_ROOT or Steam)")
    sub = parser.add_subparsers(dest="command", required=True)
    dump_p = sub.add_parser("dump", help="write schema JSON")
    dump_p.add_argument("--output", required=True)
    show_p = sub.add_parser("show", help="one type (or Type.field) with inherited fields, as JSON")
    show_p.add_argument("type", help="Type, Type.field, or <family>::Type[.field]")
    show_p.add_argument("--family", default=None)
    search_p = sub.add_parser("search", help="types and fields matching text, as JSON")
    search_p.add_argument("text")
    search_p.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)
    try:
        schema = load(args.game_root)
        if args.command == "dump":
            path = schema.dump(args.output)
            counts = schema.counts
            print(json.dumps({"output": str(path), "types": counts.get("types"),
                              "fieldsDeclared": counts.get("fields_declared"), "fieldsTotal": counts.get("fields_total"),
                              "resourceDescTypes": counts.get("resource_desc_types")}, indent=2))
            return 0
        if args.command == "search":
            print(json.dumps(search(schema, args.text, args.limit), indent=1, sort_keys=True, default=str))
            return 0
        info = show(schema, args.type, args.family)
    except (SchemaError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if info is None:
        print(f"error: no type {args.type!r}", file=sys.stderr)
        return 1
    print(json.dumps(info, indent=1, sort_keys=True, default=str))
    return 1 if "error" in info else 0


if __name__ == "__main__":
    sys.exit(main())
