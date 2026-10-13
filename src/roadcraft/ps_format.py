"""Read and write RoadCraft PS/BRO text documents (``key = value`` assignments, ``{}``, ``[]``).

The parser is the read-only assignment parser used by the mod projects (originally from the CAT 793D
BRO audit); the writer produces the same text form the SDK uses and refuses to write a document that
does not parse back to itself.  Values map to Python: objects -> dict, arrays -> list, numbers ->
int/float, ``True``/``False`` -> bool, strings -> str.
"""

from __future__ import annotations

import json
import math
from decimal import Decimal
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(
    r"""
    (?P<WS>\s+)
  | (?P<STRING>"(?:\\.|[^"\\])*")
  | (?P<NUMBER>[-+]?(?:(?:\d+\.\d*)|(?:\.\d+)|(?:\d+))(?:[eE][-+]?\d+)?)
  | (?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<PUNCT>[{}\[\]=,])
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    offset: int


class PsSyntaxError(ValueError):
    """The text is not a PS/BRO assignment document."""


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    offset = 0
    while offset < len(text):
        match = TOKEN_RE.match(text, offset)
        if not match:
            raise PsSyntaxError(f"Unexpected character {text[offset]!r} at offset {offset}")
        kind = match.lastgroup or ""
        if kind != "WS":
            tokens.append(Token(kind, match.group(), offset))
        offset = match.end()
    return tokens


class PsParser:
    def __init__(self, text: str) -> None:
        self.tokens = tokenize(text)
        self.index = 0

    def _peek(self) -> Token | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _next(self) -> Token:
        token = self._peek()
        if token is None:
            raise PsSyntaxError("Unexpected end of document")
        self.index += 1
        return token

    def _expect(self, value: str) -> None:
        token = self._next()
        if token.value != value:
            raise PsSyntaxError(f"Expected {value!r} at offset {token.offset}, found {token.value!r}")

    def document(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while self._peek() is not None:
            if self._peek().value == ",":
                self._next()
                continue
            key, value = self._assignment()
            result[key] = value
        return result

    def _key(self) -> str:
        token = self._next()
        if token.kind == "IDENT":
            return token.value
        if token.kind == "STRING":
            return json.loads(token.value)
        if token.kind == "NUMBER":
            return token.value
        raise PsSyntaxError(f"Expected a key at offset {token.offset}, found {token.value!r}")

    def _assignment(self) -> tuple[str, Any]:
        key = self._key()
        self._expect("=")
        return key, self._value()

    def _value(self) -> Any:
        token = self._next()
        if token.value == "{":
            obj: dict[str, Any] = {}
            while True:
                nxt = self._peek()
                if nxt is None:
                    raise PsSyntaxError("Unclosed object")
                if nxt.value == "}":
                    self._next()
                    return obj
                if nxt.value == ",":
                    self._next()
                    continue
                key, value = self._assignment()
                obj[key] = value
        if token.value == "[":
            items: list[Any] = []
            while True:
                nxt = self._peek()
                if nxt is None:
                    raise PsSyntaxError("Unclosed array")
                if nxt.value == "]":
                    self._next()
                    return items
                if nxt.value == ",":
                    self._next()
                    continue
                items.append(self._value())
        if token.kind == "STRING":
            return json.loads(token.value)
        if token.kind == "NUMBER":
            text = token.value
            return float(text) if any(c in text for c in ".eE") else int(text)
        if token.kind == "IDENT":
            if token.value == "True":
                return True
            if token.value == "False":
                return False
            return token.value
        raise PsSyntaxError(f"Unexpected {token.value!r} at offset {token.offset}")


def loads(text: str) -> dict[str, Any]:
    """Parse PS/BRO text (a UTF-8 BOM is tolerated)."""
    return PsParser(text.lstrip("﻿")).document()


def load(path: str | Path) -> dict[str, Any]:
    return loads(Path(path).read_text(encoding="utf-8-sig"))


def _key_text(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) else json.dumps(key)


def _value_text(value: Any, level: int) -> str:
    pad = "   " * level
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("PS floating-point values must be finite")
        # Native class loading can interpret scientific notation as psARRAY
        # even though our permissive reader accepts it. Expand the shortest
        # round-tripping float representation without losing precision.
        number = format(Decimal(repr(value)), "f")
        return number if "." in number else number + ".0"
    if isinstance(value, dict):
        rows = ["   " * (level + 1) + _key_text(k) + " = " + _value_text(v, level + 1) for k, v in value.items()]
        return "{\n" + "\n".join(rows) + "\n" + pad + "}"
    if isinstance(value, (list, tuple)):
        if all(isinstance(x, (str, int, float)) and not isinstance(x, bool) for x in value):
            return "[ " + ", ".join(_value_text(x, 0) for x in value) + " ]"
        return "[\n" + ",\n".join("   " * (level + 1) + _value_text(v, level + 1) for v in value) + "\n" + pad + "]"
    raise TypeError(f"Cannot write {type(value).__name__} to a PS document")


def dumps(document: dict[str, Any]) -> str:
    """PS/BRO text of a document; raises if the text would not parse back to the same document."""
    text = "\n".join(f"{_key_text(k)} = {_value_text(v, 0)}" for k, v in document.items()) + "\n"
    normalised = json.loads(json.dumps(document))
    if json.dumps(loads(text), sort_keys=True) != json.dumps(normalised, sort_keys=True):
        raise ValueError("PS document does not round-trip")
    return text


def dump(document: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(dumps(document), encoding="utf-8")
