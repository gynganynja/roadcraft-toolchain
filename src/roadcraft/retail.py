"""Read-only access to the retail game's own vehicle data, for comparing a mod against what ships.

Where it lives under the game root (library/retail-data.md):

* ``root/prebuild/bro/Bro.Compiled.pak``: the retail BRO documents, text, under ``designer_wizard/``
  (``trucks/<name>.bro``, ``wheels/<name>.bro``, ...);
* ``root/paks/client/default/default_other.pak``: compiled truck classes, text,
  ``ssl/autogen_designer_wizard/trucks/auto_<truck>/auto_<truck>.cls``;
* ``root/paks/client/default/default_tpl_*.pak``: models,
  ``models/database/vehicles/<tpl>.tpl.asset/<tpl>.tpl_markup`` (text) and ``tpl/<tpl>.tpl`` (binary,
  see :mod:`roadcraft.tpl_reader`).

Nothing here writes anything.
"""

from __future__ import annotations

import fnmatch
import math
import re
import statistics
import zipfile
from pathlib import Path
from typing import Any, Iterator

from . import ps_format

BRO_PAK = Path("root/prebuild/bro/Bro.Compiled.pak")
PAK_DIR = Path("root/paks/client")
_INDEX: dict[str, dict[str, Path]] = {}


class RetailDataError(LookupError):
    """The requested retail file is not in this installation."""


def _index(game_root: Path) -> dict[str, Path]:
    key = str(Path(game_root).resolve())
    if key not in _INDEX:
        index: dict[str, Path] = {}
        paks = sorted((Path(game_root) / PAK_DIR).rglob("*.pak"))
        if (Path(game_root) / BRO_PAK).is_file():
            paks.append(Path(game_root) / BRO_PAK)
        for pak in paks:
            try:
                with zipfile.ZipFile(pak) as archive:
                    for name in archive.namelist():
                        index.setdefault(name, pak)
            except zipfile.BadZipFile:
                continue
        _INDEX[key] = index
    return _INDEX[key]


def find_members(game_root: str | Path, pattern: str) -> list[tuple[str, Path]]:
    """Members of the client paks and the retail BRO pak matching a glob pattern (e.g. ``*armiger*``)."""
    index = _index(Path(game_root))
    return [(name, pak) for name, pak in sorted(index.items()) if fnmatch.fnmatch(name, pattern)]


def read_member(game_root: str | Path, member: str) -> bytes:
    pak = _index(Path(game_root)).get(member)
    if pak is None:
        raise RetailDataError(f"{member} is not in the client paks or the retail BRO pak")
    with zipfile.ZipFile(pak) as archive:
        return archive.read(member)


MATERIAL_TEMPLATE_EXTENSIONS = (".mp", ".mm", ".mtl")
_MATERIALS: dict[str, frozenset[str]] = {}


def material_templates(game_root: str | Path) -> frozenset[str]:
    """Names in the retail material library: the file stems of every material preset (``material_presets/*.mp``),
    master material (``master_materials/*.mm``) and ``.mtl`` in the client paks, cached in-process per installation.

    These are the res_desc_mtl templates the library singleton (FUN_1421508f0, created as "material"/".mtl")
    registers by resource name; the ``.mi`` load job (FUN_14214f0f0) looks its ``__type`` up there
    (C:/RC_RE/research/retail_crash_0x214f223.md).  Retail ships no ``.mi`` in its paks."""
    key = str(Path(game_root).resolve())
    if key not in _MATERIALS:
        names = set()
        for member in _index(Path(game_root)):
            base = member.replace("\\", "/").rsplit("/", 1)[-1]
            for ext in MATERIAL_TEMPLATE_EXTENSIONS:
                if base.lower().endswith(ext) and len(base) > len(ext):
                    names.add(base[: -len(ext)])
        _MATERIALS[key] = frozenset(names)
    return _MATERIALS[key]


def retail_class_text(game_root: str | Path, truck: str) -> str:
    member = f"ssl/autogen_designer_wizard/trucks/auto_{truck}/auto_{truck}.cls"
    return read_member(game_root, member).decode("utf-8", "replace")


def retail_markup_text(game_root: str | Path, tpl: str) -> str:
    member = f"models/database/vehicles/{tpl}.tpl.asset/{tpl}.tpl_markup"
    return read_member(game_root, member).decode("utf-8", "replace")


def retail_tpl_bytes(game_root: str | Path, tpl: str) -> bytes:
    return read_member(game_root, f"models/database/vehicles/{tpl}.tpl.asset/tpl/{tpl}.tpl")


def iter_retail_bros(game_root: str | Path, kind: str = "trucks") -> Iterator[tuple[str, dict[str, Any]]]:
    """(name, document) of every retail BRO of one kind; unparsable documents are skipped."""
    pak = Path(game_root) / BRO_PAK
    with zipfile.ZipFile(pak) as archive:
        prefix = f"designer_wizard/{kind}/"
        for member in sorted(archive.namelist()):
            if member.startswith(prefix) and member.endswith(".bro"):
                try:
                    yield member[len(prefix):-4], ps_format.loads(archive.read(member).decode("utf-8-sig"))
                except ps_format.PsSyntaxError:
                    continue


def retail_bro(game_root: str | Path, name: str, kind: str = "trucks") -> dict[str, Any]:
    with zipfile.ZipFile(Path(game_root) / BRO_PAK) as archive:
        try:
            text = archive.read(f"designer_wizard/{kind}/{name}.bro").decode("utf-8-sig")
        except KeyError as exc:
            raise RetailDataError(f"No retail {kind} BRO named {name}") from exc
    return ps_format.loads(text)


def markup_mass(markup_text: str) -> float:
    """Sum of the rigid-body masses in a model markup (wheels are not bodies and not included)."""
    return sum(float(x) for x in re.findall(r"\bmass\s*=\s*([\d.]+)", markup_text))


def suspension_survey(game_root: str | Path, max_mass: float = 6000.0, wheel_count: int = 4) -> dict[str, Any]:
    """Implied suspension beta of every light retail vehicle with a suspension collection, assuming
    each rests as modelled: beta = 1 / (wheels * strength * height)."""
    rows = []
    for name, doc in iter_retail_bros(game_root):
        settings = doc.get("truckSettings") or {}
        collection = settings.get("suspensionCollection")
        slots = settings.get("wheelSlots") or []
        if not settings.get("useSuspensionCollection") or not collection or len(slots) != wheel_count:
            continue
        try:
            mass = markup_mass(retail_markup_text(game_root, doc.get("tpl", "")))
        except RetailDataError:
            continue
        if not 0 < mass <= max_mass:
            continue
        for item, axle in collection.items():
            height, strength = axle.get("height", 0), axle.get("strength", 0)
            if height > 0 and strength > 0:
                rows.append({"truck": name, "axle": item, "mass": mass, "height": height, "strength": strength,
                             "min": axle.get("min", 0), "max": axle.get("max", 1),
                             "beta": round(1.0 / (wheel_count * strength * height), 2)})
    betas = [row["beta"] for row in rows]
    summary: dict[str, Any] = {"axles": len(rows), "rows": rows}
    if betas:
        logs = [math.log(b) for b in betas]
        summary.update(medianBeta=round(statistics.median(betas), 2),
                       logSpread=round(statistics.pstdev(logs), 3))
    return summary
