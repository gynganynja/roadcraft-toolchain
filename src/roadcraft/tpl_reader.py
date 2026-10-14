"""Read the node table of a compiled RoadCraft model (``.tpl``), our builds' and the retail ones alike.

Layout (decoded 2026-09-29 against models whose bone positions were known; confirmed on retail
models of the ZiKZ 605E, Armiger Thunder and the SDK's TUZ Lynx sample):

* name table: ``uint32 count``, ``uint8 flag``, then ``count`` x (``uint32 length``, ASCII name);
* ``uint32 n`` (== count) and ``n`` x ``uint16`` node index, one per name;
* ``uint32 nodes`` then ``nodes`` x 4x4 ``float32`` matrices, row-major, translation in the last row:
  each node's WORLD (model) transform in native axes (X left, Y up, Z forward).  Rows 0..2 are the
  node's local X, Y, Z axes in model space;
* parent links: an ``int16`` array, one entry per node (-1 for the root), stored earlier in the file.
  Its offset is not decoded; it is found by search (see :func:`find_parents`);
* per-mesh bounds (decoded 2026-10-14 on the CAT 793D RC68/RC69 builds, whose collision boxes are known;
  the table is found in 2412 of the 2415 retail models with a node table): a bitset of ``ceil(nodes / 8)``
  bytes (bit i, LSB first: node i has a mesh), then one 89-byte record per set bit in node order:
  ``uint32 4``, one byte (mostly 0x0c), 21 ``float32``: AABB min3 and max3, oriented box origin3 (a corner),
  axes 3x3 (rows) and size3, all in the mesh node's own frame (see :func:`find_bounds`).

Everything here is read-only and uses only the standard library.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_NAME = re.compile(rb"[ -~]+")     # printable ASCII: SDK sample names contain spaces


class TplFormatError(ValueError):
    """The data does not contain a recognisable node table."""


@dataclass
class TplNodes:
    names: list[str]
    index: dict[str, int]                        # name -> node index
    matrices: list[tuple[float, ...]]            # per node: 16 floats, row-major
    parents: list[int] | None = None             # per node: parent node index, -1 for the root
    parents_offset: int | None = None
    notes: list[str] = field(default_factory=list)
    bounds: dict[int, "MeshBounds"] | None = None  # node index -> its mesh's bounds (find_bounds)

    def matrix(self, name: str) -> tuple[float, ...]:
        return self.matrices[self.index[name]]

    def position(self, name: str) -> tuple[float, float, float]:
        m = self.matrix(name)
        return (m[12], m[13], m[14])

    def axes(self, name: str) -> dict[str, tuple[float, float, float]]:
        m = self.matrix(name)
        return {"x": tuple(m[0:3]), "y": tuple(m[4:7]), "z": tuple(m[8:11])}

    def name_of(self, node: int) -> str:
        for name, value in self.index.items():
            if value == node:
                return name
        return f"#{node}"

    def parent(self, name: str) -> str | None:
        if self.parents is None:
            return None
        p = self.parents[self.index[name]]
        return None if p < 0 else self.name_of(p)

    def children(self, name: str) -> list[str]:
        if self.parents is None:
            return []
        node = self.index[name]
        return [self.name_of(i) for i, p in enumerate(self.parents) if p == node]


def _names_at(data: bytes, start: int) -> tuple[list[str], int] | None:
    if start + 5 > len(data):
        return None
    count = struct.unpack_from("<I", data, start)[0]
    if not 2 <= count <= 50000 or data[start + 4] not in (0, 1):
        return None
    pos = start + 5
    names: list[str] = []
    for _ in range(count):
        if pos + 4 > len(data):
            return None
        length = struct.unpack_from("<I", data, pos)[0]
        raw = data[pos + 4:pos + 4 + length]
        if not 1 <= length <= 255 or len(raw) != length or not _NAME.fullmatch(raw):
            return None
        names.append(raw.decode("ascii"))
        pos += 4 + length
    return names, pos


def read_nodes(data: bytes, anchor: str | None = None) -> TplNodes:
    """Parse names, node indices and world matrices.  ``anchor`` (a node name) selects the right table
    when a file holds more than one name list."""
    # The count is a little-endian uint32 whose low byte can be anything (512 or 513 names start 00/01);
    # _names_at validates 2..50000. The old [\x02-\xff] missed a 513-node CAT 793D (2026-10-09).
    for match in re.finditer(rb"[\x00-\xff][\x00-\xc3]\x00\x00[\x00\x01][\x01-\xff]\x00\x00\x00[A-Za-z_]", data):
        found = _names_at(data, match.start())
        if not found:
            continue
        names, pos = found
        if anchor is not None and anchor not in names:
            continue
        if pos + 4 > len(data) or struct.unpack_from("<I", data, pos)[0] != len(names):
            continue
        index = struct.unpack_from(f"<{len(names)}H", data, pos + 4)
        pos += 4 + 2 * len(names)
        nodes = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        if nodes <= max(index) or pos + 64 * nodes > len(data):
            continue
        floats = struct.unpack_from(f"<{16 * nodes}f", data, pos)
        matrices = [floats[i * 16:(i + 1) * 16] for i in range(nodes)]
        if not all(abs(m[3]) < 1e-5 and abs(m[7]) < 1e-5 and abs(m[11]) < 1e-5 and abs(m[15] - 1.0) < 1e-5
                   for m in matrices):
            continue
        return TplNodes(names=names, index=dict(zip(names, index)), matrices=matrices)
    raise TplFormatError("No node table found" + (f" containing {anchor!r}" if anchor else ""))


def _valid_tree(parents: tuple[int, ...]) -> bool:
    n = len(parents)
    if sum(1 for p in parents if p == -1) != 1 or any(p < -1 or p >= n for p in parents):
        return False
    for start in range(n):
        seen = 0
        node = start
        while node != -1:
            node = parents[node]
            seen += 1
            if seen > n:
                return False
    return True


def find_parents(data: bytes, nodes: TplNodes,
                 known_pairs: list[tuple[str, str]] | None = None,
                 tiebreak: Callable[[TplNodes, tuple[int, ...]], Any] | None = None) -> TplNodes:
    """Locate the parent array: an int16 array, one entry per node, forming one tree.

    Every offset holding a valid tree is a candidate.  Candidates are ranked by how many (child,
    parent) pairs they satisfy: ``known_pairs`` first, then pairs guessed from IK chain naming
    (``*_Rod`` under ``*_Mid`` or ``*_Base``, ``*_b`` under ``*_a``, ``*_c`` under ``*_b``).  A single
    best candidate is taken; otherwise the parents stay unset and a note says why.
    """
    n = len(nodes.matrices)
    pairs = list(known_pairs or [])
    for name in nodes.names:
        for child_suffix, parent_suffixes in (("_Rod", ("_Mid", "_Base")), ("_Mid", ("_Base",)),
                                              ("_c", ("_b",)), ("_b", ("_a",))):
            if name.endswith(child_suffix):
                for parent_suffix in parent_suffixes:
                    other = name[: -len(child_suffix)] + parent_suffix
                    if other in nodes.index:
                        pairs.append((name, other))
                        break
    checks = [(nodes.index[c], nodes.index[p]) for c, p in pairs if c in nodes.index and p in nodes.index]
    samples = sorted({0, n // 3, n // 2, (2 * n) // 3, n - 1})
    candidates = []
    for offset in range(0, len(data) - 2 * n + 1):
        if any(not -1 <= struct.unpack_from("<h", data, offset + 2 * s)[0] < n for s in samples):
            continue
        parents = struct.unpack_from(f"<{n}h", data, offset)
        if _valid_tree(parents):
            score = sum(1 for c, p in checks if parents[c] == p)
            candidates.append((score, offset, parents))
    if not candidates:
        nodes.notes.append("No parent array found")
        return nodes
    candidates.sort(key=lambda row: -row[0])
    best = candidates[0]
    if len(candidates) > 1 and candidates[1][0] == best[0]:
        tied = [row for row in candidates if row[0] == best[0]]
        ranked = sorted(((tiebreak(nodes, row[2]), row) for row in tied), key=lambda r: r[0],
                        reverse=True) if tiebreak else []
        if not ranked or ranked[0][0] == ranked[1][0]:
            nodes.notes.append(f"{len(candidates)} parent array candidates tie; pass known (child, parent) pairs")
            return nodes
        best = ranked[0][1]
        nodes.notes.append(f"{len(tied)} parent array candidates tied; the caller's tie-break chose offset {best[1]}")
    nodes.parents, nodes.parents_offset = list(best[2]), best[1]
    if checks and best[0] < len(checks):
        nodes.notes.append(f"parent array satisfies {best[0]} of {len(checks)} name-guessed pairs")
    return nodes


@dataclass(frozen=True)
class MeshBounds:
    """One mesh's bounds in its node's own frame: the AABB (``min``/``max``) and the oriented box (a corner
    ``origin``, unit ``axes`` rows and edge lengths ``size``)."""
    min: tuple[float, ...]
    max: tuple[float, ...]
    origin: tuple[float, ...]
    axes: tuple[tuple[float, ...], ...]
    size: tuple[float, ...]

    def center(self) -> tuple[float, float, float]:
        return (self.origin[0] + sum(self.axes[a][0] * self.size[a] / 2 for a in range(3)),
                self.origin[1] + sum(self.axes[a][1] * self.size[a] / 2 for a in range(3)),
                self.origin[2] + sum(self.axes[a][2] * self.size[a] / 2 for a in range(3)))


BOUNDS_TAG = b"\x04\x00\x00\x00"
BOUNDS_RECORD = 89


def find_bounds(data: bytes, nodes: TplNodes) -> TplNodes:
    """Attach the per-mesh bounds (``nodes.bounds``: node index -> :class:`MeshBounds`).

    The table is the first place where the ``ceil(nodes / 8)``-byte bitset in front of it counts exactly as
    many 89-byte records (``uint32 4``, one byte, 21 finite floats) as follow.  ``bounds`` stays None, with a
    note, when no such table is found."""
    count = len(nodes.matrices)
    width = (count + 7) // 8
    for match in re.finditer(re.escape(BOUNDS_TAG), data):
        start = match.start()
        if start < width:
            continue
        mask = int.from_bytes(data[start - width:start], "little")
        k = bin(mask).count("1")
        if k == 0 or mask >> count or start + BOUNDS_RECORD * k > len(data):
            continue
        last = start + BOUNDS_RECORD * (k - 1)
        if data[last:last + 4] != BOUNDS_TAG:
            continue
        records = []
        for j in range(k):
            off = start + BOUNDS_RECORD * j
            if data[off:off + 4] != BOUNDS_TAG:
                break
            f = struct.unpack_from("<21f", data, off + 5)
            if not all(math.isfinite(x) for x in f) or any(s < 0 for s in f[18:21]):
                break
            records.append(MeshBounds(min=f[0:3], max=f[3:6], origin=f[6:9],
                                      axes=(f[9:12], f[12:15], f[15:18]), size=f[18:21]))
        if len(records) != k:
            continue
        nodes.bounds = dict(zip([i for i in range(count) if mask >> i & 1], records))
        return nodes
    nodes.notes.append("No per-mesh bounds table found")
    return nodes


def read_tpl(path: str | Path, anchor: str | None = None, parents: bool = True,
             known_pairs: list[tuple[str, str]] | None = None, bounds: bool = False) -> TplNodes:
    return read_tpl_bytes(Path(path).read_bytes(), anchor, parents, known_pairs, bounds)


def read_tpl_bytes(data: bytes, anchor: str | None = None, parents: bool = True,
                   known_pairs: list[tuple[str, str]] | None = None, bounds: bool = False) -> TplNodes:
    nodes = read_nodes(data, anchor)
    if parents:
        find_parents(data, nodes, known_pairs)
    if bounds:
        find_bounds(data, nodes)
    return nodes
