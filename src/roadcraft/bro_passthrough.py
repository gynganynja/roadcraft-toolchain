"""Does each BRO field reach the compiled class, and as what?  (library/bro-passthrough.md)

Three sources, joined per ``".<family>::Type.field"`` key (the keys of the desktop's BRO reference,
``bro_reference.py``):

* **Empirical** (the main method).  Every retail truck BRO in ``root/prebuild/bro/Bro.Compiled.pak`` is
  resolved through its template chain (leaf -> ``Chassis*`` template -> ``Truck`` template; inline wheel
  templates in ``wheelPool``) and each field occurrence is looked up in the compiled classes the game ships
  beside it (``default_other.pak``: ``ssl/autogen_designer_wizard/trucks/auto_<truck>/``).  An occurrence is
  *same* (a class leaf with the same name and value), *renamed* (the value under another name, only for
  values rare in that truck's classes), *differs* (a same-named leaf in the same context with another value)
  or *absent*.  Sections take the result of their leaves.
* **Code** (optional, ``--generator-src``): the C# of ``Bro.Compiled.dll`` (the designer-wizard generator
  scripts, decompiled).  Every ``FindChild("k").Value = <expr>`` / ``CopyFrom(<expr>)`` is resolved to the
  BRO class field(s) it reads, and every BRO class's declared fields are indexed: a key with no C# field can
  never reach the generator (``FieldsSerializer.LoadFields`` fills declared fields only).
* **Engine** (optional): ``read_fields.json`` readers / ignored keys, the SSL schema (is the key a member of
  the class type it lands in?) and the base-game SSL source (``native var`` / references).

Nothing is written outside ``--out``.  stdlib only.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import os
import re
import statistics
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable

from . import ps_format

BRO_PAK = "root/prebuild/bro/Bro.Compiled.pak"
OTHER_PAK = "root/paks/client/default/default_other.pak"
CLS_PREFIX = "ssl/autogen_designer_wizard/trucks/"
STATUSES = ("passes", "renamed", "transformed", "dropped", "unknown")
DEFAULT_GAME = r"C:\Program Files (x86)\Steam\steamapps\common\RoadCraft"
DATA = Path(__file__).with_name("data")
CODE_NOTE_NO_FIELD = ("no C# field in Bro.Compiled.dll: FieldsSerializer.LoadFields fills declared fields only, so "
                      "the generator never sees the key (the BRO keeps it as an untyped NullModel)")
KNOWN_FACTORS = {0.0174533: "degrees -> radians", 57.2958: "radians -> degrees", 0.277778: "km/h -> m/s",
                 3.6: "m/s -> km/h", 0.001: "/ 1000", 1000.0: "* 1000"}


# ----------------------------------------------------------------------------------------------- schema

class Schema:
    """The SDK schema dump (``schema.json``: ``types`` keyed ``.<family>::<name>``)."""

    def __init__(self, types: dict[str, Any] | None):
        self.T = types or {}

    @classmethod
    def load(cls, path: str | Path | None) -> "Schema":
        if not path or not Path(path).is_file():
            return cls({})
        with open(path, encoding="utf-8") as handle:
            return cls(json.load(handle).get("types", {}))

    def lookup(self, family: str, name: str | None, order: tuple[str, ...] = (".bro", ".ssl", ".prop", "!global")):
        if not name:
            return None, None
        for fam in (family,) + order:
            key = f"{fam}::{name}"
            if key in self.T:
                return key, self.T[key]
        return None, None

    def member(self, tkey: str | None, field: str) -> dict[str, Any] | None:
        if not tkey or tkey not in self.T:
            return None
        t = self.T[tkey]
        decl = (t.get("all_members") or {}).get(field)
        if decl is None:
            return None
        _, owner = self.lookup(t.get("family", ".bro"), decl)
        if owner is None:
            return None
        return (owner.get("members") or {}).get(field)

    def has_member(self, tkey: str | None, field: str) -> bool | None:
        if not tkey or tkey not in self.T:
            return None
        return field in (self.T[tkey].get("all_members") or {})


# ------------------------------------------------------------------------------------------ BRO side

def camel(stem: str) -> str:
    """Template type name of a BRO file stem (``chassis_kronenwerk_l_34_fork`` -> ``ChassisKronenwerkL34Fork``)."""
    return "".join(part[:1].upper() + part[1:] for part in stem.split("_") if part)


class Templates:
    """BRO documents by the type name they define, with template-chain resolution."""

    def __init__(self, docs: dict[str, dict[str, Any]]):
        self.docs = docs
        self._cache: dict[str, dict[str, Any]] = {}
        self._stack: list[str] = []

    def effective(self, type_name: str) -> dict[str, Any] | None:
        if type_name not in self.docs or type_name in self._stack:
            return None
        if type_name not in self._cache:
            self._stack.append(type_name)
            try:
                self._cache[type_name] = self.resolve(self.docs[type_name], own=type_name)
            finally:
                self._stack.pop()
        return self._cache[type_name]

    def resolve(self, node: Any, own: str | None = None) -> Any:
        if isinstance(node, list):
            return [self.resolve(item) for item in node]
        if not isinstance(node, dict):
            return node
        t = node.get("__type")
        base = self.effective(t) if isinstance(t, str) and t != own else None
        if base is None:
            return {k: self.resolve(v) for k, v in node.items()}
        return self.merge(base, node)

    def merge(self, base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
        out = dict(base)
        for key, value in over.items():
            prior = out.get(key)
            if isinstance(value, dict) and isinstance(prior, dict) and value.get("__type") not in self.docs and (
                    value.get("__type") in (None, prior.get("__type")) or prior.get("__type") is None):
                out[key] = self.merge(prior, value)
            else:
                out[key] = self.resolve(value)
        return out


Occurrence = tuple  # (typeKey, field, path tuple, value, frozenset of variable path positions)


def occurrences(doc: dict[str, Any], schema: Schema) -> list[Occurrence]:
    """Every field of every typed node, keyed like the desktop's ``bro_reference.py`` walk."""
    out: list[Occurrence] = []

    def walk(node, family, tname, path, var):
        if isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, family, tname, path + (f"[{i}]",), var | {len(path)})
            return
        if not isinstance(node, dict):
            return
        if isinstance(node.get("__type"), str):
            tname = node["__type"]
        tkey = schema.lookup(family, tname)[0] if tname else None
        key_type = tkey or (f"{family}::{tname}" if tname else None)
        for key, val in node.items():
            if key.startswith("__"):
                continue
            m = schema.member(tkey, key) if tkey else None
            if key_type:
                out.append((key_type, key, path + (key,), val, var))
            if isinstance(val, (dict, list)):
                child_t, child_f = (m.get("ptr"), m.get("ptr_family", family)) if m else (None, family)
                if isinstance(val, dict) and m and m.get("kind") == "collection":
                    for item_key, item in val.items():
                        walk(item, child_f, child_t, path + (key, item_key), var | {len(path) + 1})
                else:
                    walk(val, child_f, child_t, path + (key,), var)

    walk(doc, ".bro", doc.get("__type"), (), frozenset())
    return out


# ---------------------------------------------------------------------------------------- class side

def norm(value: Any):
    if isinstance(value, bool):
        return ("b", value)
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return ("n", str(value))
        return ("n", float(f"{float(value):.5g}") + 0.0)
    if isinstance(value, str):
        return ("s", value)
    if isinstance(value, (list, tuple)) and value and all(
            isinstance(x, (bool, int, float, str)) for x in value):
        return ("l", tuple(norm(x) for x in value))
    return None


def is_leaf(value: Any) -> bool:
    return norm(value) is not None or value == [] or value == ""


CLASS_TYPE_ORDER = (".ssl", ".prop", ".cls", "!global", ".sso", ".bro")


def flatten_class(doc: dict[str, Any], schema: Schema) -> list[tuple[tuple[str, ...], Any, str | None]]:
    """(path, value, containing type key) of every scalar / scalar-list leaf of a compiled class."""
    leaves = []

    def rec(node, path, tkey):
        if isinstance(node, list):
            if norm(node) is not None:
                leaves.append((path, node, tkey))
                return
            for i, item in enumerate(node):
                rec(item, path + (f"[{i}]",), tkey)
            return
        if not isinstance(node, dict):
            if norm(node) is not None:
                leaves.append((path, node, tkey))
            return
        t = node.get("__type")
        if isinstance(t, str):
            tkey = schema.lookup(".ssl", t, CLASS_TYPE_ORDER)[0] or tkey
        for key, val in node.items():
            if key in ("__type", "__namespace"):
                continue
            child = tkey
            if path == ("properties",):
                child = schema.lookup(".prop", key, CLASS_TYPE_ORDER)[0]
            elif tkey and isinstance(val, (dict, list)):
                m = schema.member(tkey, key)
                name = (m or {}).get("ptr") or (m or {}).get("type")
                child = schema.lookup((m or {}).get("ptr_family", ".ssl"), name, CLASS_TYPE_ORDER)[0] if name else None
            if isinstance(val, (dict, list)):
                rec(val, path + (key,), child)
            elif norm(val) is not None:
                leaves.append((path + (key,), val, tkey))

    rec(doc, (), None)
    return leaves


class Corpus:
    """All compiled classes of one truck, indexed by value and by leaf name."""

    def __init__(self, truck: str, files: dict[str, dict[str, Any]], schema: Schema):
        self.truck = truck
        self.leaves: list[tuple[str, tuple[str, ...], Any, str | None]] = []
        for role in sorted(files):
            for path, value, tkey in flatten_class(files[role], schema):
                self.leaves.append((role, path, value, tkey))
        self.by_value: dict[Any, list[int]] = collections.defaultdict(list)
        self.by_name: dict[str, list[int]] = collections.defaultdict(list)
        for i, (role, path, value, _) in enumerate(self.leaves):
            self.by_value[norm(value)].append(i)
            self.by_name[path[-1]].append(i)


def class_role(rel: str, truck: str) -> str:
    """Role of a class file inside ``auto_<truck>/`` (``truck``, ``wheel:<pool>``, ``<suffix>``),
    with ``base:`` / ``preview:`` prefixes for the ``base/`` and ``preview/`` copies."""
    prefix = ""
    for variant in ("base", "preview"):
        if rel.startswith(f"{variant}/"):
            prefix = f"{variant}:"
            truck_v = f"{variant}_{truck}"
            break
    else:
        truck_v = truck
    name = rel.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    if stem == f"auto_{truck_v}":
        return prefix + "truck"
    if stem.startswith(f"auto_wheel_{truck_v}_"):
        return prefix + "wheel:" + stem[len(f"auto_wheel_{truck_v}_"):]
    if stem.startswith(f"auto_{truck_v}_"):
        return prefix + stem[len(f"auto_{truck_v}_"):] + "." + name.rsplit(".", 1)[-1]
    return prefix + name


def role_file(role: str) -> str:
    """Generic file name of a class role (truck and pool names as ``<truck>`` / ``<pool>``)."""
    prefix, rest = role.split(":", 1) if role.startswith(("base:", "preview:")) else ("", role)
    variant = f"{prefix}_" if prefix else ""
    folder = f"{prefix}/" if prefix else ""
    if rest == "truck":
        return f"{folder}auto_{variant}<truck>.cls"
    if rest.startswith("wheel:"):
        return f"{folder}auto_wheel_{variant}<truck>_<pool>.cls"
    return f"{folder}auto_{variant}<truck>_{rest}"


# ----------------------------------------------------------------------------------------- matching

def _ctx(bro_path: tuple[str, ...], cls_path: tuple[str, ...]) -> int:
    near = {seg for seg in bro_path[:-1][-4:] if not seg.startswith("[")}
    return len(near & set(cls_path[:-1]))


def general_path(path: tuple[str, ...], variable: set[str], truck: str, pools: set[str]) -> str:
    segs = []
    for seg in path:
        if seg.startswith("[") and seg.endswith("]"):
            segs.append("[]")
        elif seg in variable or seg.lower() in pools:
            segs.append("*")
        elif truck and truck in seg:
            segs.append(seg.replace(truck, "<truck>"))
        else:
            segs.append(seg)
    return "/".join(segs)


def match_leaf(occ: Occurrence, corpus: Corpus, pools: set[str]) -> dict[str, Any]:
    tkey, field, path, value, var = occ
    nv = norm(value)
    variable = {path[i] for i in var if i < len(path)}
    want = None
    if len(path) >= 3 and path[0] == "wheelPool":
        want = "wheel:" + str(path[1]).lower()

    def pref(role):
        if want is not None:
            return 3 if role == want else (1 if ":" not in role else 0)
        return 3 if role == "truck" else (2 if ":" not in role or role.startswith("wheel:") else 0)

    def describe(kind, i, extra=None):
        role, cpath, cvalue, ctype = corpus.leaves[i]
        out = {"kind": kind, "role": role, "path": cpath, "general": general_path(cpath, variable, corpus.truck,
                                                                                    pools),
               "ctype": ctype, "value": value}
        if extra:
            out.update(extra)
        return out

    if nv is None:
        return {"kind": "empty", "value": value}
    cands = corpus.by_value.get(nv, [])
    if cands:
        def score(i):
            role, cpath, _, _ = corpus.leaves[i]
            return (cpath[-1] == field, _ctx(path, cpath), pref(role), -len(cpath), "/".join(cpath))
        best = max(cands, key=score)
        if corpus.leaves[best][1][-1] == field:
            return describe("same", best)
        common = nv in (("b", True), ("b", False), ("n", 0.0), ("n", 1.0), ("n", -1.0), ("s", ""))
        if not common and len(cands) <= 3 and nv[0] in ("n", "s", "l"):
            return describe("renamed", best)
    named = corpus.by_name.get(field, [])
    if named:
        def nscore(i):
            role, cpath, _, _ = corpus.leaves[i]
            return (_ctx(path, cpath), pref(role), -len(cpath), "/".join(cpath))
        best = max(named, key=nscore)
        in_role = [i for i in named if corpus.leaves[i][0] == want] if want else []
        if in_role:
            best = max(in_role, key=nscore)
        if _ctx(path, corpus.leaves[best][1]) >= 1 or len(named) == 1 or in_role:
            return describe("differs", best, {"classValue": corpus.leaves[best][2]})
    return {"kind": "absent", "value": value}


def lcp(paths: list[str]) -> str:
    if not paths:
        return ""
    split = [p.split("/") for p in paths]
    out = []
    for segs in zip(*split):
        if all(s == segs[0] for s in segs):
            out.append(segs[0])
        else:
            break
    return "/".join(out)


# ----------------------------------------------------------------------------------- retail loading

def load_retail(game_root: str | Path) -> tuple[dict[str, tuple[str, dict]], dict[str, dict[str, dict]]]:
    """(BRO docs by member name under designer_wizard/{trucks,wheels}/, class files by truck and role)."""
    game = Path(game_root)
    bros: dict[str, tuple[str, dict]] = {}
    with zipfile.ZipFile(game / BRO_PAK) as pak:
        for member in sorted(pak.namelist()):
            if not member.endswith(".bro"):
                continue
            if not member.startswith(("designer_wizard/trucks/", "designer_wizard/wheels/")):
                continue
            try:
                doc = ps_format.loads(pak.read(member).decode("utf-8-sig"))
            except ps_format.PsSyntaxError:
                continue
            bros[member[len("designer_wizard/"):]] = (member, doc)
    classes: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    with zipfile.ZipFile(game / OTHER_PAK) as pak:
        for member in sorted(pak.namelist()):
            if not member.startswith(CLS_PREFIX) or not member.endswith((".cls", ".sso")):
                continue
            rel = member[len(CLS_PREFIX):]
            parts = rel.split("/")
            if len(parts) == 2 and parts[0].startswith("auto_"):
                truck = parts[0][len("auto_"):]
                sub = parts[1]
            elif len(parts) == 3 and parts[0] in ("base", "preview") and parts[1].startswith(f"auto_{parts[0]}_"):
                truck = parts[1][len(f"auto_{parts[0]}_"):]
                sub = f"{parts[0]}/{parts[2]}"
            else:
                continue
            try:
                doc = ps_format.loads(pak.read(member).decode("utf-8-sig", "replace"))
            except ps_format.PsSyntaxError:
                continue
            classes[truck][class_role(sub, truck)] = doc
    return bros, dict(classes)


def template_index(bros: dict[str, tuple[str, dict]]) -> Templates:
    docs = {}
    for rel, (_, doc) in sorted(bros.items()):
        stem = rel.rsplit("/", 1)[-1][:-4]
        docs.setdefault(camel(stem), doc)
    return Templates(docs)


def pairs(bros: dict[str, tuple[str, dict]], classes: dict[str, dict[str, dict]]) -> list[tuple[str, dict]]:
    """(truck, BRO doc) for every top-level truck BRO with shipped compiled classes."""
    out = []
    for rel, (_, doc) in sorted(bros.items()):
        parts = rel.split("/")
        if len(parts) == 2 and parts[0] == "trucks" and parts[1][:-4] in classes:
            out.append((parts[1][:-4], doc))
    return out


# ------------------------------------------------------------------------------------- empirical run

def analyse_truck(truck: str, doc: dict[str, Any], files: dict[str, dict], templates: Templates,
                  schema: Schema) -> list[tuple[Occurrence, dict[str, Any]]]:
    eff = templates.resolve(doc)
    corpus = Corpus(truck, files, schema)
    pools = {str(p).lower() for p in (eff.get("wheelPool") or {})}
    scales = {str(p): (v or {}).get("scale") for p, v in (eff.get("wheelPool") or {}).items() if isinstance(v, dict)}
    occs = occurrences(eff, schema)
    results: list[tuple[Occurrence, dict[str, Any]]] = []
    section: dict[tuple, dict[str, Any]] = {}
    leaf_results = []
    for occ in occs:
        value = occ[3]
        if isinstance(value, dict) or (isinstance(value, list) and value and norm(value) is None):
            section[occ[2]] = {"kind": "section", "matched": [], "differs": 0, "leaves": 0}
            continue
        res = match_leaf(occ, corpus, pools)
        if occ[2][:1] == ("wheelPool",) and len(occ[2]) > 1:
            res["scale"] = scales.get(str(occ[2][1]))
        leaf_results.append((occ, res))
    for occ, res in leaf_results:
        path = occ[2]
        for k in range(1, len(path)):
            acc = section.get(path[:k])
            if acc is None:
                continue
            if res["kind"] != "empty":
                acc["leaves"] += 1
            if res["kind"] == "same":  # value-only renames are too noisy to place a section
                acc["matched"].append((res["role"], res["general"]))
            elif res["kind"] == "differs":
                acc["differs"] += 1
    for occ in occs:
        if occ[2] in section:
            acc = section[occ[2]]
            if acc["matched"]:
                roles = collections.Counter(r for r, _ in acc["matched"])
                role = sorted(roles.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
                gpaths = [g for r, g in acc["matched"] if r == role]
                prefix = lcp(gpaths)
                props = sorted({"/".join(g.split("/")[:2]) for g in gpaths if g.startswith("properties/")})
                last = prefix.rsplit("/", 1)[-1] if prefix else ""
                kind = "same" if last == occ[1] else "renamed"
                res = {"kind": kind, "role": role, "general": prefix, "section": True, "split": props
                       if len(props) > 1 else [], "value": None, "ctype": None,
                       "leaves": acc["leaves"], "matchedLeaves": len(acc["matched"])}
            elif acc["leaves"] == 0:
                res = {"kind": "empty", "value": None, "section": True}
            elif acc["differs"]:
                res = {"kind": "differs", "general": "", "role": "", "section": True, "value": None}
            else:
                res = {"kind": "absent", "value": None, "section": True}
            results.append((occ, res))
    results.extend(leaf_results)
    return results


# ------------------------------------------------------------------------------------------ C# side

FIELD_RE = re.compile(r"^\tpublic (?!virtual\b|static\b|const\b|override\b|abstract\b)([\w.<>, \[\]]+?) @?(\w+);",
                      re.M)
CLASS_RE = re.compile(r"^public (?:abstract |sealed |partial )*class (\w+)(?:\s*:\s*([\w.]+))?", re.M)
METHOD_RE = re.compile(r"^\tpublic (?:virtual |static |override )*[\w.<>, \[\]]+ (\w+)\(([^)]*)\)\s*$", re.M)
CHAIN_RE = re.compile(r"(?<![\w.\"])(?:this\.|@)?([a-z_]\w*)((?:\.[A-Za-z_]\w*)+)")
LOCAL_RE = re.compile(r"(?:^|[\s(,])([A-Z]\w*(?:<[\w, <>]+>)?)\s+(\w+)\s*(?:=|;|\bin\b|,|\))")
MW_DECL_RE = re.compile(r"^\s*ModelWrapper (\w+) = (.*);\s*$")
VALUE_RE = re.compile(r"^\s*\(\(ModelWrapper\)\(ref (\w+)\)\)\.Value = new RuntimeObject\(\(object\)(.*)\);\s*$")
COPY_RE = re.compile(r"^\s*\(\(ModelWrapper\)\(ref (\w+)\)\)\.CopyFrom(?:AsPs)?\((.*)\);\s*$")


def _elem_type(type_text: str) -> tuple[str, str]:
    t = type_text.strip()
    m = re.match(r"^(?:List|SslDictionary|SslArray|IList|Dictionary)<(?:[\w.]+,\s*)?([\w.]+)>$", t)
    if m:
        return m.group(1).rsplit(".", 1)[-1], "container"
    return t.rsplit(".", 1)[-1], "single"


def _split_args(text: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch in "(<[":
            depth += 1
        elif ch in ")>]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


class CodeIndex:
    """BRO C# classes and the generator's class writes, from a decompiled ``Bro.Compiled.dll``."""

    def __init__(self):
        self.classes: dict[str, dict[str, Any]] = {}
        self.writes: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
        self.reads: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
        self.available = False

    # ---- classes
    def fields(self, cls: str) -> dict[str, tuple[str, str, str]]:
        """field -> (declaring class, element type, container kind), inherited fields included."""
        out: dict[str, tuple[str, str, str]] = {}
        seen = set()
        while cls in self.classes and cls not in seen:
            seen.add(cls)
            for name, (etype, kind) in self.classes[cls]["fields"].items():
                out.setdefault(name, (cls, etype, kind))
            cls = self.classes[cls]["base"]
        return out

    def declaring(self, cls: str, field: str) -> str | None:
        hit = self.fields(cls).get(field)
        return hit[0] if hit else None

    @classmethod
    def scan(cls, src: str | Path | None) -> "CodeIndex":
        index = cls()
        if not src or not Path(src).is_dir():
            return index
        index.available = True
        files = sorted(Path(src).rglob("*.cs"))
        texts = {}
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            texts[path] = text
            for m in CLASS_RE.finditer(text):
                base = (m.group(2) or "").rsplit(".", 1)[-1] or None
                fields = {}
                for f in FIELD_RE.finditer(text):
                    fields[f.group(2)] = _elem_type(f.group(1))
                index.classes.setdefault(m.group(1), {"base": base, "fields": fields,
                                                      "file": str(path.relative_to(src)).replace("\\", "/")})
                break
        for path, text in texts.items():
            if "RuntimeObject" in text or "CopyFrom(" in text:
                index._scan_generator(str(path.relative_to(src)).replace("\\", "/"), text)
        return index

    def _resolve_chain(self, root_type: str | None, members: list[str]) -> list[tuple[str, str]]:
        out = []
        t = root_type
        for m in members:
            if not t or t not in self.classes:
                break
            hit = self.fields(t).get(m)
            if not hit:
                break
            out.append((hit[0], m))
            t = hit[1]
        return out

    def _scan_generator(self, rel: str, text: str) -> None:
        cls_m = CLASS_RE.search(text)
        own_fields = {}
        if cls_m:
            for f in FIELD_RE.finditer(text):
                own_fields[f.group(2)] = _elem_type(f.group(1))[0]
        lines = text.splitlines()
        heads = [(m.start(), m.group(1), m.group(2)) for m in METHOD_RE.finditer(text)]
        starts = [text.count("\n", 0, pos) for pos, _, _ in heads]
        methods = []
        for i, (pos, name, params) in enumerate(heads):
            end = starts[i + 1] if i + 1 < len(heads) else len(lines)
            methods.append((name, params, starts[i], end))
        param_paths: dict[str, list[list[str]]] = {}
        pending: list[dict[str, Any]] = []
        calls: list[tuple[str, int, list[str], dict[str, list[str]]]] = []
        mw_params: dict[str, list[str]] = {}
        for name, params, lo, hi in methods:
            types: dict[str, str] = dict(own_fields)
            paths: dict[str, list[str]] = {}
            plist = []
            for arg in _split_args(params):
                bits = arg.replace("@", "").split()
                if len(bits) >= 2:
                    types[bits[-1]] = _elem_type(bits[-2])[0]
                    plist.append(bits[-1])
                    if bits[-2] == "ModelWrapper":
                        paths[bits[-1]] = [f"<{name}.{bits[-1]}>"]
            mw_params[name] = plist
            conds: list[str | None] = []
            pending_cond: str | None = None
            for ln in range(lo, hi):
                line = lines[ln]
                stripped = line.strip()
                if stripped.startswith(("if (", "else if (", "while (")):
                    pending_cond = stripped
                elif stripped == "else":
                    pending_cond = "else"
                elif stripped == "{":
                    conds.append(pending_cond)
                    pending_cond = None
                elif stripped == "}":
                    if conds:
                        conds.pop()
                elif stripped and not stripped.startswith("//"):
                    pending_cond = None
                for lm in LOCAL_RE.finditer(line):
                    if lm.group(1) not in ("ModelWrapper", "RuntimeObject", "Global", "Exception"):
                        types.setdefault(lm.group(2), _elem_type(lm.group(1))[0])
                where = f"{rel}:{name}:L{ln + 1}"
                for chain in CHAIN_RE.finditer(line):
                    resolved = self._resolve_chain(types.get(chain.group(1)), chain.group(2).split(".")[1:])
                    for decl_field in resolved:
                        self.reads[decl_field].append(where)
                d = MW_DECL_RE.match(line)
                if d:
                    var, rhs = d.group(1), d.group(2)
                    src = re.search(r"\(ref (\w+)\)\)\.(\w+)\(\s*(\"[^\"]*\")?", rhs)
                    if "GetOrCreateProperty(" in rhs:
                        g = re.search(r"GetOrCreateProperty\((\w+), \"([^\"]+)\"", rhs)
                        if g:
                            paths[var] = paths.get(g.group(1), [f"<{g.group(1)}>"]) + ["properties", g.group(2)]
                    elif "GetOrCreateDictionaryElement(" in rhs:
                        g = re.search(r"GetOrCreateDictionaryElement\((\w+),", rhs)
                        if g:
                            paths[var] = paths.get(g.group(1), [f"<{g.group(1)}>"]) + ["*"]
                    elif src:
                        base = paths.get(src.group(1), [f"<{src.group(1)}>"])
                        op, arg = src.group(2), (src.group(3) or "").strip('"')
                        if op == "FindChild":
                            paths[var] = base + ([arg] if arg else ["?"])
                        elif op == "FindChildByPath":
                            paths[var] = base + [s for s in arg.split("/") if s]
                        elif op in ("AddElement", "AddElementWithType"):
                            paths[var] = base + ["[]"]
                        elif op in ("SetType", "SetRootType"):
                            paths[var] = base
                        else:
                            paths[var] = base + ["?"]
                    elif ".SetRootType(" in rhs:
                        paths[var] = ["<doc>"]
                    else:
                        paths[var] = ["<?>"]
                    continue
                v = VALUE_RE.match(line)
                c = None if v else COPY_RE.match(line)
                hit = v or c
                if hit:
                    target, expr = hit.group(1), hit.group(2)
                    chains = []
                    for chain in CHAIN_RE.finditer(expr):
                        resolved = self._resolve_chain(types.get(chain.group(1)), chain.group(2).split(".")[1:])
                        if resolved:
                            chains.append((chain.group(0), resolved))
                    if not chains:
                        continue
                    plain = len(chains) == 1 and re.fullmatch(
                        r"\(*\s*" + re.escape(chains[0][0]) + r"\s*\)*", expr.replace("(object)", "")) is not None
                    active = [c for c in conds if c and not c.startswith("while")]
                    gate = active[-1] if active else None
                    for text_chain, resolved in chains:
                        pending.append({"field": resolved[-1], "to": paths.get(target, [f"<{target}>"]),
                                        "expr": expr.strip(), "plain": plain, "copy": c is not None,
                                        "where": where, "gate": gate})
            for ln in range(lo, hi):
                for call in re.finditer(r"\b([A-Z]\w+)\((.*)\)", lines[ln]):
                    if call.group(1) in mw_params or call.group(1)[0].isupper():
                        calls.append((call.group(1), ln, _split_args(call.group(2)), paths))
        # bind ModelWrapper parameters to their callers' paths (two levels are enough here)
        bindings: dict[str, list[list[str]]] = collections.defaultdict(list)
        for callee, _, args, paths in calls:
            plist = mw_params.get(callee)
            if not plist or not args:
                continue
            for pname, arg in zip(plist, args):
                arg = arg.strip()
                path = paths.get(arg)
                m = re.fullmatch(r"\(\(ModelWrapper\)\(ref (\w+)\)\)\.(FindChild|FindChildByPath|AddElement)"
                                 r"\((?:\"([^\"]+)\")?\)", arg)
                if path is None and m:
                    tail = ["[]"] if m.group(2) == "AddElement" else [s for s in (m.group(3) or "?").split("/") if s]
                    path = paths.get(m.group(1), [f"<{m.group(1)}>"]) + tail
                if path is not None and path not in bindings[f"<{callee}.{pname}>"]:
                    bindings[f"<{callee}.{pname}>"].append(path)

        def expand(path, depth=0):
            if path and path[0] in bindings and depth < 4:
                out = []
                for b in bindings[path[0]]:
                    for e in expand(b + path[1:], depth + 1):
                        if e not in out:
                            out.append(e)
                return out
            return [path]

        for p in pending:
            for full in expand(p["to"]):
                rec = dict(p)
                if full and full[0] in ("<doc>", "<root>") or (full and full[0].endswith(".root>")):
                    full = full[1:]
                rec["to"] = "/".join(full)
                self.writes[p["field"]].append(rec)

    # ---- per key
    def evidence(self, type_name: str, field: str) -> dict[str, Any]:
        """What the generator code does with ``Type.field`` (Type = a BRO C# class)."""
        if not self.available:
            return {"available": False}
        if type_name not in self.classes:
            return {"available": True, "class": False}
        decl = self.declaring(type_name, field)
        if decl is None:
            return {"available": True, "class": True, "field": False}
        writes = self.writes.get((decl, field), [])
        reads = self.reads.get((decl, field), [])
        return {"available": True, "class": True, "field": True, "declaring": decl, "writes": writes,
                "reads": reads}


# -------------------------------------------------------------------------------------------- engine

class Engine:
    def __init__(self, schema: Schema, read_fields: dict[str, Any] | None, ssl_src: str | Path | None):
        self.schema = schema
        self.readers: dict[str, set[str]] = {}
        self.ignored: dict[str, dict[str, str]] = {}
        for r in (read_fields or {}).get("readers", []):
            self.readers.setdefault(r["typeKey"], set()).update(x["key"] for x in r.get("reads", []))
        for tkey, keys in ((read_fields or {}).get("ignoredKeys") or {}).items():
            self.ignored[tkey] = keys
        self.ssl_root = Path(ssl_src) if ssl_src and Path(ssl_src).is_dir() else None
        self._ssl_text: str | None = None
        self._decl: dict[str, tuple[str, bool]] | None = None

    def _ssl(self):
        if self._ssl_text is None:
            parts, decl = [], {}
            if self.ssl_root:
                for path in sorted(self.ssl_root.rglob("*")):
                    if path.suffix in (".ssl", ".ssc") and path.is_file():
                        text = path.read_text(encoding="utf-8", errors="replace")
                        parts.append(text)
                        for m in re.finditer(r"^\s*(?:\[[^\n]*\]\s*)*(native\s+)?var\s+(\w+)\s*:", text, re.M):
                            decl.setdefault(m.group(2), (str(path.relative_to(self.ssl_root)), bool(m.group(1))))
            self._ssl_text = "\n".join(parts)
            self._words = collections.Counter(re.findall(r"\w+", self._ssl_text))
            self._decl = decl
        return self._ssl_text, self._decl

    def _module_decl(self, ctype: str, key: str) -> tuple[str, bool] | None:
        """(file, native) of ``var key`` in the SSL module of the type that declares it."""
        m = self.schema.member(ctype, key) or {}
        owner_name = m.get("declared_in")
        t = self.schema.T.get(ctype) or {}
        owner = self.schema.lookup(t.get("family", ".ssl"), owner_name, CLASS_TYPE_ORDER)[1] if owner_name else t
        module = (owner or {}).get("ssl_module")
        if not module:
            return None
        for ext in (".ssc", ".ssl"):
            path = self.ssl_root / (module.replace(".", "/") + ext)
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                hit = re.search(r"^[^\n]*?\b(native\s+)?var\s+" + re.escape(key) + r"\s*:", text, re.M)
                if hit:
                    return str(path.relative_to(self.ssl_root)).replace("\\", "/"), bool(hit.group(1))
        return None

    def reads(self, ctype: str | None, key: str, depth: int = 2) -> tuple[Any, str]:
        """(reads, basis) for class key ``key`` inside a node of type ``ctype`` at path depth ``depth``; the root of
        an autogen document is a generated subclass, so "not a member" is not trusted there."""
        chain = (self.schema.T.get(ctype) or {}).get("chain") or ([ctype] if ctype else [])
        for t in chain:
            if t in self.ignored and key in self.ignored[t]:
                return False, f"read_fields.json ignoredKeys {t}: {self.ignored[t][key]}"
        for t in chain:
            if t in self.readers:
                if key in self.readers[t]:
                    return True, f"read_fields.json reader {t}"
        if ctype and ctype.startswith((".prop::", ".ssl::")) and self.schema.has_member(ctype, key) is False                 and depth >= 2:
            return False, f"not a member of {ctype}: the class loader has no slot for it"
        if self.ssl_root and ctype:
            self._ssl()
            hit = self._module_decl(ctype, key)
            if hit and hit[1]:
                return True, f"native var in {hit[0]} (engine-bound)"
            if hit:
                if self._words.get(key, 0) > 1:
                    return True, f"SSL var in {hit[0]}, name referenced in SSL source"
                return False, f"SSL var in {hit[0]}, never referenced outside its declaration"
        return "unknown", "no reader table, schema type or SSL declaration"


# ------------------------------------------------------------------------------------------ verdicts

def _fmt(v):
    if isinstance(v, float):
        return float(f"{v:.6g}")
    return v


def transform_rule(differs: list[dict[str, Any]]) -> str | None:
    nums = [(d["value"], d["classValue"], d.get("scale")) for d in differs
            if isinstance(d["value"], (int, float)) and not isinstance(d["value"], bool)
            and isinstance(d["classValue"], (int, float)) and not isinstance(d["classValue"], bool)]
    if nums and len(nums) == len(differs):
        ratios = [c / v for v, c, _ in nums if v]
        if ratios and len(ratios) == len(nums):
            med = statistics.median(ratios)
            if med and all(abs(r - med) <= 1e-3 * abs(med) for r in ratios):
                label = next((n for k, n in KNOWN_FACTORS.items() if abs(med - k) <= 1e-3 * k), None)
                return f"class = bro * {med:.6g}" + (f" ({label})" if label else "")
            scaled = [(v, c, s) for v, c, s in nums if isinstance(s, (int, float)) and s]
            if scaled and len(scaled) == len(nums) and all(abs(c - v * s) <= 1e-3 * max(abs(c), 1e-6)
                                                           for v, c, s in scaled):
                return "class = bro * wheelPool.<pool>.scale"
        offs = [c - v for v, c, _ in nums]
        med = statistics.median(offs)
        if all(abs(o - med) <= 1e-4 * max(1.0, abs(med)) for o in offs):
            return f"class = bro + {med:.6g}"
    return None


def decide(key: str, agg: dict[str, Any], code: dict[str, Any], engine: Engine) -> dict[str, Any]:
    kinds = agg["kinds"]
    n_eff = sum(kinds[k] for k in ("same", "renamed", "differs", "absent"))
    same, renamed, differs, absent = (kinds[k] for k in ("same", "renamed", "differs", "absent"))
    rec: dict[str, Any] = {"status": "unknown", "classPath": None}
    notes: list[str] = []
    matched_values = agg["matchedValues"]
    absent_values = agg["absentValues"]
    matched = same + renamed
    only_absent = set(absent_values) - set(matched_values)
    elided = bool(matched) and len(absent_values) == 1 and bool(only_absent)
    if n_eff and (matched * 2 >= n_eff or elided) and matched >= differs:
        if same >= renamed:
            path, _ = sorted(agg["samePaths"].items(), key=lambda kv: (-kv[1], kv[0]))[0]
            rec.update(status="passes", classPath=path)
        else:
            path, _ = sorted(agg["renamedPaths"].items(), key=lambda kv: (-kv[1], kv[0]))[0]
            rec.update(status="renamed", classPath=path)
            if len(agg["matchedTrucks"]) < 2:
                notes.append("renamed on a single truck's evidence (value match only)")
        if agg["split"] and rec["classPath"] and rec["classPath"].endswith(":properties"):
            rec["status"] = "transformed"
            rec["rule"] = "section split: its fields land in " + ", ".join(sorted(agg["split"]))
        elif agg["split"]:
            notes.append("section split over " + ", ".join(sorted(agg["split"])))
        if absent and elided:
            d = _show(next(iter(absent_values)))
            default = None
            ctype = ctype_for(agg, rec["classPath"])
            if ctype and rec["classPath"]:
                m = engine.schema.member(ctype, rec["classPath"].rsplit("/", 1)[-1])
                default = (m or {}).get("default")
            tail = f" (class default {default})" if default is not None else ""
            rec["omittedWhen"] = d
            notes.append(f"not written when the value is {d}{tail}: ModelWrapper.Value skips a value equal to the "
                         "class field's current value and the .cls keeps changed values only")
        elif absent:
            notes.append(f"{absent} occurrence(s) not found in the class")
        if differs and rec["status"] != "transformed":
            notes.append(f"{differs} occurrence(s) land with another value (inheritance / generator override)")
    elif n_eff and differs and differs >= absent:
        ranked = sorted(agg["differsPaths"].items(), key=lambda kv: (-kv[1], kv[0]))
        path = ranked[0][0] if ranked else None
        rule = transform_rule(agg["differsList"])
        rec.update(status="transformed", classPath=path, rule=rule or "value changes on the way (see examples)")
    elif n_eff:
        rec.update(status="dropped")
        if not any(_distinctive(v) for v in absent_values):
            rec["status"] = "unknown"
            notes.append("only common values (0/1/true/false/empty) in retail and none seen in the class: dropped "
                         "or elided as the class default")
    # ---- code
    if code.get("available"):
        if code.get("class") and code.get("field") is False:
            if rec["status"] in ("passes", "renamed", "transformed"):
                notes.append("empirical match although the C# class has no such field (coincidental value?)")
            rec.update(status="dropped", classPath=None)
            rec.pop("rule", None)
            rec["codeNote"] = CODE_NOTE_NO_FIELD
        elif code.get("field"):
            writes = code.get("writes") or []
            reads = code.get("reads") or []
            if not writes and not reads and rec["status"] in ("unknown", "dropped"):
                rec.update(status="dropped", classPath=None)
                rec["codeNote"] = "the generator never reads this C# field"
            elif writes:
                tos = sorted({w["to"] for w in writes})
                exprs = sorted({w["expr"] for w in writes if not w["plain"]})
                gates = sorted({w["gate"] for w in writes if w.get("gate")})
                rec["codeWrites"] = tos[:6]
                plain_tos = sorted({w["to"] for w in writes if w["plain"] and not w["to"].startswith("<")})
                if rec["status"] == "renamed" and plain_tos:
                    emp_leaf = (rec["classPath"] or "").rsplit("/", 1)[-1]
                    if emp_leaf not in {t.rsplit("/", 1)[-1] for t in plain_tos}:
                        notes.append(f"value-only match {rec['classPath']} overruled by the generator code")
                        leaf = plain_tos[0].rsplit("/", 1)[-1]
                        rec.update(status="passes" if leaf == key.rsplit(".", 1)[-1] else "renamed",
                                   classPath=plain_tos[0])
                if exprs and rec["status"] in ("dropped", "unknown"):
                    ranked = sorted(agg["differsPaths"].items(), key=lambda kv: (-kv[1], kv[0]))
                    rec.update(status="transformed", classPath=ranked[0][0] if ranked else tos[0],
                               rule=transform_rule(agg["differsList"]) or "; ".join(exprs[:3]))
                    rec["codeRule"] = "; ".join(exprs[:3])
                emp_leaves = {p.rsplit("/", 1)[-1] for p in list(agg["samePaths"]) + list(agg["renamedPaths"])}
                code_leaves = {t.rsplit("/", 1)[-1] for t in plain_tos}
                if rec["status"] == "dropped" and emp_leaves & code_leaves:
                    leaf = sorted(emp_leaves & code_leaves)[0]
                    path = next(t for t in plain_tos if t.rsplit("/", 1)[-1] == leaf)
                    hits = [p for p in sorted(agg["samePaths"]) + sorted(agg["renamedPaths"])
                            if p.rsplit("/", 1)[-1] == leaf]
                    rec.update(status="passes" if leaf == key.rsplit(".", 1)[-1] else "renamed",
                               classPath=hits[0] if hits else path)
                    notes.append("absent from most retail classes because the write is gated: "
                                 + (" / ".join(gates[:2]) if gates else "(no gate found)"))
                if rec["status"] == "dropped" and plain_tos:
                    leaf = plain_tos[0].rsplit("/", 1)[-1]
                    if gates:
                        rec.update(status="passes" if leaf == key.rsplit(".", 1)[-1] else "renamed",
                                   classPath=plain_tos[0])
                        notes.append("from the generator code: retail never meets the gate "
                                     + " / ".join(gates[:2]))
                    elif len(absent_values) <= 1:
                        rec.update(status="passes" if leaf == key.rsplit(".", 1)[-1] else "renamed",
                                   classPath=plain_tos[0])
                        if absent_values:
                            rec["omittedWhen"] = _show(next(iter(absent_values)))
                            notes.append(f"written ungated by the generator; every retail value is {rec['omittedWhen']}, "
                                         "evidently the class default, so the .cls omits it")
                    else:
                        rec.update(status="unknown", classPath=plain_tos[0])
                        notes.append("conflict: the generator writes it ungated, yet no retail class carries the value")
                elif rec["status"] == "dropped":
                    notes.append(("the generator writes it only when " + " / ".join(gates[:2])) if gates else
                                 "the generator writes it, yet no retail class carries the value (another "
                                 "document, or overwritten later)")
                elif rec["status"] == "unknown":
                    leaf = tos[0].rsplit("/", 1)[-1]
                    rec.update(status="passes" if leaf == key.rsplit(".", 1)[-1] else "renamed", classPath=tos[0])
                    if absent_values and all(not _distinctive(v) for v in absent_values):
                        notes.append("written by the generator; the retail values equal the class default, so the "
                                     ".cls omits them")
                if exprs and rec["status"] in ("passes", "transformed", "renamed"):
                    rec["status"] = "transformed"
                    rec.setdefault("rule", "; ".join(exprs[:3]))
                    if rec.get("rule", "").startswith("value changes"):
                        rec["rule"] = "; ".join(exprs[:3])
                    rec["codeRule"] = "; ".join(exprs[:3])
                if gates:
                    rec["gate"] = gates[:3]
            elif reads and rec["status"] in ("unknown", "dropped") and not agg.get("section"):
                rec.update(status="transformed", classPath=None,
                           rule="consumed by the generator (switch / input to other values), not copied")
    if notes:
        rec["notes"] = notes
    return rec


def ctype_for(agg: dict[str, Any], class_path: str | None) -> str | None:
    """The schema type of the class node holding ``class_path`` (most often seen there)."""
    hits = sorted(((n, t) for (where, t), n in agg["ctypes"].items() if where == class_path), key=lambda x: (-x[0], x[1]))
    return hits[0][1] if hits else None


def _show(value: Any) -> Any:
    """A normalized value back as JSON-friendly data."""
    if isinstance(value, tuple) and len(value) == 2 and value[0] in ("b", "n", "s"):
        return value[1]
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "l":
        return [_show(v) for v in value[1]]
    return value


def _distinctive(value: Any) -> bool:
    v = value[1] if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str) else value
    if isinstance(value, tuple) and value and value[0] in ("b",):
        return False
    if v in (None, "", 0, 0.0, 1, 1.0, -1, -1.0, True, False):
        return False
    return True


# ----------------------------------------------------------------------------------------- driver

def canonical_key(schema: Schema, key: str) -> str:
    """``.bro::ChassisX.tpl`` -> ``.bro::Truck.tpl``: the type that declares the field (schema), so all
    chassis / wheel templates share one verdict."""
    tkey, field = key.rsplit(".", 1)
    t = schema.T.get(tkey)
    decl = ((t or {}).get("all_members") or {}).get(field)
    if not decl:
        return key
    owner, _ = schema.lookup(t.get("family", ".bro"), decl)
    return f"{owner}.{field}" if owner else key


def merge_aggs(into: dict[str, Any] | None, add: dict[str, Any]) -> dict[str, Any]:
    if into is None:
        into = {k: (v.copy() if hasattr(v, "copy") else v) for k, v in add.items()}
        into["examples"] = list(add["examples"])
        into["differsList"] = list(add["differsList"])
        return into
    for k, v in add.items():
        if isinstance(v, collections.Counter):
            into[k].update(v)
        elif isinstance(v, set):
            into[k] |= v
        elif isinstance(v, list):
            into[k].extend(v)
        elif isinstance(v, bool):
            into[k] = into[k] or v
        elif isinstance(v, int):
            into[k] += v
    return into


def run(game_root: str | Path, schema_path: str | Path | None = None, generator_src: str | Path | None = None,
        read_fields: str | Path | None = None, ssl_src: str | Path | None = None,
        reference: str | Path | None = None) -> dict[str, Any]:
    schema = Schema.load(schema_path)
    bros, classes = load_retail(game_root)
    templates = template_index(bros)
    code = CodeIndex.scan(generator_src)
    rf = None
    rf_path = Path(read_fields) if read_fields else DATA / "read_fields.json"
    if rf_path.is_file():
        rf = json.loads(rf_path.read_text(encoding="utf-8"))
    engine = Engine(schema, rf, ssl_src)
    aggs: dict[str, dict[str, Any]] = {}

    def agg_for(key):
        if key not in aggs:
            aggs[key] = {"trucks": set(), "matchedTrucks": set(), "kinds": collections.Counter(),
                         "samePaths": collections.Counter(), "renamedPaths": collections.Counter(),
                         "differsPaths": collections.Counter(), "differsList": [], "absentValues": collections.Counter(),
                         "matchedValues": collections.Counter(), "ctypes": collections.Counter(), "examples": [],
                         "split": set(), "section": False, "total": 0,
                         "underDropped": collections.Counter()}
        return aggs[key]

    truck_pairs = pairs(bros, classes)
    no_field: dict[str, bool] = {}

    def lacks_field(key: str) -> bool:
        if key not in no_field:
            tkey, field = key.rsplit(".", 1)
            family, _, type_name = tkey.partition("::")
            no_field[key] = family == ".bro" and code.evidence(type_name, field).get("field") is False
        return no_field[key]

    for truck, doc in truck_pairs:
        rows = analyse_truck(truck, doc, classes[truck], templates, schema)
        dead = {occ[2]: f"{occ[0]}.{occ[1]}" for occ, _ in rows if lacks_field(f"{occ[0]}.{occ[1]}")}
        for occ, res in rows:
            key = f"{occ[0]}.{occ[1]}"
            a = agg_for(key)
            a["trucks"].add(truck)
            a["total"] += 1
            parent = next((dead[occ[2][:k]] for k in range(len(occ[2]) - 1, 0, -1) if occ[2][:k] in dead), None)
            if parent:
                a["underDropped"][parent] += 1
            kind = res["kind"]
            a["kinds"][kind] += 1
            if res.get("section"):
                a["section"] = True
            nv = norm(res.get("value")) if res.get("value") is not None else None
            if kind in ("same", "renamed"):
                a["matchedTrucks"].add(truck)
                where = f"{role_file(res['role'])}:{res['general']}"
                (a["samePaths"] if kind == "same" else a["renamedPaths"])[where] += 1
                if nv is not None:
                    a["matchedValues"][nv] += 1
                if res.get("ctype"):
                    a["ctypes"][(where, res["ctype"])] += 1
                if res.get("split"):
                    a["split"].update(res["split"])
            elif kind == "differs":
                where = f"{role_file(res['role'])}:{res['general']}" if res.get("general") else None
                if where:
                    a["differsPaths"][where] += 1
                if "classValue" in res:
                    a["differsList"].append(res)
                if res.get("ctype") and where:
                    a["ctypes"][(where, res["ctype"])] += 1
            elif kind == "absent" and nv is not None:
                a["absentValues"][nv] += 1
            if len(a["examples"]) < 3 and kind != "empty":
                ex = {"truck": truck, "bro": "/".join(map(str, occ[2])), "result": kind}
                if res.get("value") is not None and norm(res["value"]) is not None:
                    ex["value"] = _fmt(res["value"]) if not isinstance(res["value"], list) else res["value"][:6]
                if kind in ("same", "renamed", "differs") and res.get("general") is not None:
                    ex["class"] = f"{role_file(res.get('role', ''))}:{res.get('general', '')}"
                if kind == "differs" and "classValue" in res:
                    cv = res["classValue"]
                    ex["classValue"] = _fmt(cv) if not isinstance(cv, list) else cv[:6]
                a["examples"].append(ex)

    canon = {key: canonical_key(schema, key) for key in aggs}
    caggs: dict[str, dict[str, Any]] = {}
    for key in sorted(aggs):
        caggs[canon[key]] = merge_aggs(caggs.get(canon[key]), aggs[key])
    keys = set(aggs)
    ref_keys: dict[str, dict[str, Any]] = {}
    if reference and Path(reference).is_file():
        ref = json.loads(Path(reference).read_text(encoding="utf-8"))
        for tkey, t in (ref.get("types") or {}).items():
            for f, rec in (t.get("fields") or {}).items():
                ref_keys[f"{tkey}.{f}"] = {"declared": True, "retailFiles": rec.get("retailFiles", 0)}
            for f, rec in (t.get("undeclared") or {}).items():
                ref_keys[f"{tkey}.{f}"] = {"declared": False, "retailFiles": rec.get("retailFiles", 0)}
        keys |= set(ref_keys)
    out: dict[str, Any] = {}
    for key in sorted(keys):
        tkey, field = key.rsplit(".", 1)
        family, _, type_name = tkey.partition("::")
        a = aggs.get(key) or agg_for(key)
        ckey = canon.get(key) or canonical_key(schema, key)
        ca = caggs.get(ckey) or a
        cev = code.evidence(type_name, field) if family == ".bro" else {"available": code.available,
                                                                           "raw": True}
        rec = decide(key, ca, cev, engine)
        if ca["total"] and sum(ca["underDropped"].values()) >= ca["total"] and rec["status"] != "dropped":
            parent = sorted(ca["underDropped"].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            if rec["status"] != "unknown":
                rec.setdefault("notes", []).append(f"empirical {rec['status']} at {rec.get('classPath')} is a "
                                                   "coincidental value match")
            rec.update(status="dropped", classPath=None)
            for stale in ("rule", "omittedWhen", "codeRule", "codeWrites", "gate"):
                rec.pop(stale, None)
            rec["codeNote"] = f"inside {parent}, which has no C# field, so the generator never sees the subtree"
        if not a["trucks"] and rec["status"] == "unknown" and not cev.get("class"):
            rec.setdefault("notes", []).append("no retail truck/wheel occurrence")
        engine_reads, basis = (None, None)
        if rec["status"] == "dropped":
            engine_reads, basis = False, "not in the compiled class"
        elif rec.get("classPath") and ":" in rec["classPath"]:
            ctype = ctype_for(ca, rec["classPath"])
            leaf = rec["classPath"].rsplit("/", 1)[-1]
            depth = rec["classPath"].split(":", 1)[1].count("/")
            engine_reads, basis = (engine.reads(ctype, leaf, depth) if leaf not in ("[]", "*")
                                   else ("unknown", "collection"))
        else:
            engine_reads, basis = "unknown", "no class path"
        ev: dict[str, Any] = {"retailTrucks": len(a["trucks"]), "matched": len(a["matchedTrucks"]),
                              "occurrences": dict(sorted((k, v) for k, v in a["kinds"].items() if v)),
                              "absentValues": [[_show(v), n] for v, n in sorted(
                                  a["absentValues"].items(), key=lambda kv: (-kv[1], str(kv[0])))[:4]],
                              "examples": a["examples"]}
        if ckey != key:
            ev["decidedOn"] = {"key": ckey, "retailTrucks": len(ca["trucks"]), "matched": len(ca["matchedTrucks"])}
        if key in ref_keys:
            ev["declared"] = ref_keys[key]["declared"]
            ev["retailFiles"] = ref_keys[key]["retailFiles"]
        code_text = None
        if cev.get("available") and family == ".bro":
            if cev.get("class") is False:
                code_text = f"{type_name}: no C# class in Bro.Compiled.dll"
            elif cev.get("field") is False:
                code_text = f"{type_name}.{field}: no C# field"
            else:
                w = cev.get("writes") or []
                r = cev.get("reads") or []
                if w:
                    code_text = "; ".join(sorted({x["where"].rsplit(":L", 1)[0] for x in w})[:4])
                elif r:
                    code_text = "read only: " + "; ".join(sorted({x.rsplit(":L", 1)[0] for x in r})[:4])
                else:
                    code_text = f"{cev.get('declaring')}.{field}: declared, never read by a generator"
        ev["code"] = code_text
        entry = {"status": rec["status"], "classPath": rec.get("classPath")}
        if rec.get("rule"):
            entry["rule"] = rec["rule"]
        entry["evidence"] = ev
        entry["engineReads"] = engine_reads
        entry["engineReadsBasis"] = basis
        for extra in ("omittedWhen", "codeRule", "codeWrites", "gate", "codeNote", "notes"):
            if rec.get(extra):
                entry[extra] = rec[extra]
        out[key] = entry
    counts = collections.Counter(e["status"] for e in out.values())
    observed = collections.Counter(e["status"] for e in out.values() if e["evidence"]["retailTrucks"])
    chains = {}
    for tkey, t in sorted(schema.T.items()):
        if tkey.startswith(".bro::"):
            chains[tkey[len(".bro::"):]] = [c.split("::", 1)[-1] for c in t.get("chain") or [tkey]
                                           if c.startswith(".bro::") and c not in (".bro::object", ".bro::GenaTemplate")]
    return {"_typeChains": chains, "schemaVersion": 1,
            "method": "bro_passthrough.py: retail truck BROs (template chain resolved) vs the shipped auto_<truck> "
                      "classes; generator C# (Bro.Compiled.dll) for undeclared keys and expressions; engine reads "
                      "from read_fields.json, the SSL schema and SSL source",
            "retailTrucks": len(truck_pairs), "codeAvailable": code.available,
            "counts": dict(sorted(counts.items())), "countsObservedInRetailTrucks": dict(sorted(observed.items())),
            "fields": out}


def compact_table(result: dict[str, Any]) -> dict[str, Any]:
    """The subset bro_lint needs (RC075), keyed ``Type.field`` on the declaring type: dropped BRO keys that retail
    sets (so donors carry them), and BRO keys whose class key the engine does not read.  ``typeChains`` maps a
    BRO type to itself and its ancestors so a ``Chassis*`` node finds the ``Truck`` entries."""
    dropped, ignored = {}, {}
    for key, e in sorted(result["fields"].items()):
        canon = e["evidence"].get("decidedOn", {}).get("key", key)
        if not canon.startswith(".bro::"):
            continue
        tf = canon[len(".bro::"):]
        if tf.split(".", 1)[0] == "null":
            continue
        if e["status"] == "dropped" and e.get("codeNote") and (e["evidence"].get("retailFiles")
                                                               or e["evidence"]["retailTrucks"]):
            dropped.setdefault(tf, e["codeNote"])
        elif e["status"] in ("passes", "renamed", "transformed") and e.get("engineReads") is False:
            ignored.setdefault(tf, f"lands in {e.get('classPath')}, which the engine does not read "
                                   f"({e.get('engineReadsBasis')})")
    return {"schemaVersion": 1, "source": "bro_passthrough.py (passthrough.json); library/bro-passthrough.md",
            "dropped": dict(sorted(dropped.items())), "engineIgnored": dict(sorted(ignored.items())),
            "typeChains": result.get("_typeChains", {})}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--game-root", default=os.environ.get("ROADCRAFT_GAME_ROOT", DEFAULT_GAME))
    ap.add_argument("--schema", help="schema.json (types keyed .<family>::<name>)")
    ap.add_argument("--generator-src", help="decompiled Bro.Compiled.dll (C# tree)")
    ap.add_argument("--read-fields", help="read_fields.json (default: package data)")
    ap.add_argument("--ssl-src", help="base-game SSL source tree (ssl/)")
    ap.add_argument("--reference", help="bro_ref.json from bro_reference.py: emit a row for every key in it")
    ap.add_argument("--out", required=True, help="passthrough.json")
    ap.add_argument("--lint-table", help="also write the compact RC075 table here")
    args = ap.parse_args(argv)
    result = run(args.game_root, args.schema, args.generator_src, args.read_fields, args.ssl_src, args.reference)
    public = {k: v for k, v in result.items() if not k.startswith("_")}
    Path(args.out).write_text(json.dumps(public, indent=1, sort_keys=False, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    if args.lint_table:
        Path(args.lint_table).write_text(json.dumps(compact_table(result), indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"retailTrucks": result["retailTrucks"], "counts": result["counts"],
                      "observed": result["countsObservedInRetailTrucks"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
