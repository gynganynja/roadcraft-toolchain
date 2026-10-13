"""Read and write RoadCraft PS/BRO text documents (``key = value`` assignments, ``{}``, ``[]``).

The parser is the read-only assignment parser used by the mod projects (originally from the CAT 793D
BRO audit); the writer produces the same text form the SDK uses and refuses to write a document that
does not parse back to itself.  Values map to Python: objects -> dict, arrays -> list, numbers ->
int/float, ``True``/``False`` -> bool, strings -> str.
"""

from __future__ import annotations

import json
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
        return repr(value)
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


# ---------------------------------------------------------------------------------------------------------
# Editor-faithful reader
#
# ``loads`` above is the toolchain's lenient reader (it accepts exponents and reads ``.5`` as 0.5).  The Mod
# Editor and its class generator read PS text with Saber.Common.Ps.Ps.Parser, whose quirks silently change
# values.  ``editor_loads`` is a port of that parser (decompiled IntegrationStudio; C:\RC_RE\research\schema.md
# section 2; grade SDK): no exponent support (``x = 1e-05`` -> 1, then a stray key ``e`` -> parse error;
# ``[1e-05]`` -> ``[1, "e", -5]``), a leading dot loses a digit (``.5`` -> 0.0, ``.25`` -> 0.5), and bare
# ``on/off/yes/no/true/false`` values are bools (case-insensitive).  Keys are never numbers or bools, a
# duplicate key in one section is an error, and ``{`` must be on the key's line.  ``warn(kind, line, detail)``
# reports the quirks: ``leading_dot_number``, ``number_followed_by_letters`` (exponents, ``3dmodel``) and
# ``bare_bool_keyword``.  Sections are :class:`PsSection` (a dict with ``lines``: key -> 1-based line).
# ---------------------------------------------------------------------------------------------------------

import bisect as _bisect

_BOOL_WORDS = (("false", "alse", False), ("true", "rue", True), ("on", "n", True),
               ("off", "ff", False), ("no", "o", False), ("yes", "es", True))
_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"'}


class PsSection(dict):
    """A parsed section: an ordinary dict plus ``lines`` (key -> 1-based line of the key) and ``line``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.lines: dict[str, int] = {}
        self.line = 0


class EditorParseError(PsSyntaxError):
    """The Mod Editor's parser rejects the text (``line``/``col`` are 1-based)."""

    def __init__(self, message: str, index: int, text: str) -> None:
        self.index = index
        self.line = text.count("\n", 0, index) + 1
        self.col = index - (text.rfind("\n", 0, index) + 1) + 1
        super().__init__(f"{message} (line {self.line}, col {self.col})")


def _valid_string_char(c: str) -> bool:
    return c == "_" or c == "|" or c.isalnum()


class _EditorParser:
    def __init__(self, text: str, warn: Any = None, lines: bool = True) -> None:
        self.s = text
        self.n = len(text)
        self.i = 0
        self.ch = "\0"
        self.warn = warn
        self._nl = [i for i, c in enumerate(text) if c == "\n"] if (lines or warn) else None

    def line_of(self, index: int) -> int:
        return _bisect.bisect_left(self._nl, index) + 1 if self._nl is not None else 0

    def _warn(self, kind: str, index: int, detail: str) -> None:
        if self.warn:
            self.warn(kind, self.line_of(index), detail)

    def read(self) -> str | None:
        if self.i >= self.n:
            return None
        c = self.s[self.i]
        self.i += 1
        return c

    def peek(self) -> str | None:
        return self.s[self.i] if self.i < self.n else None

    def look_word_ahead(self, word: str) -> bool:
        j = self.i + len(word)
        if j > self.n or self.s[self.i:j].lower() != word.lower():
            return False
        return j == self.n or not _valid_string_char(self.s[j])

    def err(self, msg: str, idx: int | None = None) -> EditorParseError:
        return EditorParseError(msg, max(0, self.i if idx is None else idx), self.s)

    def skip_comment(self) -> str | None:
        c = self.read()
        if c == "/":
            while True:
                c = self.read()
                if c in ("\n", "\r") or c is None:
                    return c
        if c != "*":
            raise self.err("unexpected '/'", self.i - 2)
        while True:
            c = self.read()
            if c is None:
                return None
            if c == "*":
                break
        while True:
            c = self.read()
            if c is None:
                return None
            if c == "/":
                break
        return " "

    def skip_ws(self) -> None:
        s, n = self.s, self.n
        while True:
            while self.i < n and s[self.i] in " \t\r\n":
                self.i += 1
            c = self.read()
            if c == "/":
                c = self.skip_comment()
            if c is None:
                self.ch = "\0"
                return
            if c in " \t\r\n":
                continue
            self.ch = c
            return

    def skip_ws_same_line(self) -> None:
        while True:
            c = self.read()
            if c is None:
                self.ch = "\0"
                return
            if c == "/":
                c = self.skip_comment()
                if c is None:
                    self.ch = "\0"
                    return
            if c not in (" ", "\t"):
                self.ch = c
                return

    def next_token(self, expect_string: bool = False) -> Any:
        c = self.ch
        if c == "\0":
            return "EOF"
        if c in "{}[],;":
            return c
        if c in ":=":
            return "="
        if c == '"':
            return "STR"
        if c == "<":
            if self.read() == "<" and self.read() == "<" and self.peek() != "<":
                return "STR"
            raise self.err("bad '<'", self.i - 3)
        if c in "+-.0123456789":
            return "STR" if expect_string else "NUM"
        if c in "_|":
            return "STR"
        if c == "#":
            if expect_string and self.look_word_ahead("ssl_begin"):
                self.i += 9
                return "SSL"
            raise self.err("unexpected '#'", self.i - 1)
        if not expect_string:
            lc = c.lower()
            start = self.i - 1
            for word, rest, value in _BOOL_WORDS:
                if lc == word[0] and self.look_word_ahead(rest):
                    self.i += len(rest)
                    if word not in ("true", "false"):
                        self._warn("bare_bool_keyword", start, self.s[start:self.i])
                    return ("BOOL", value)
        if c.isalpha():
            return "STR"
        raise self.err(f"unexpected char {c!r}", self.i - 1)

    def parse_string(self) -> str:
        c = self.ch
        buf: list[str] = []
        if c == '"':
            while True:
                d = self.read()
                if d is None:
                    raise self.err("EOF in string")
                if d == '"':
                    return "".join(buf)
                if ord(d) < 32 and d != "\t":
                    raise self.err(f"control char {d!r} in string", self.i)
                if d == "\\":
                    e = self.read()
                    if e in _ESCAPES:
                        d = _ESCAPES[e]
                    else:
                        buf.append("\\")
                        d = e if e is not None else ""
                buf.append(d)
        if c == "<":
            count = 0
            while True:
                d = self.read()
                if d is None:
                    raise self.err("EOF in <<< >>> string")
                if d == ">":          # quirk: '>' is never kept, so '>' / '>>' inside the text are dropped
                    count += 1
                    if count == 3:
                        if self.peek() == ">":
                            raise self.err("'>>>>'")
                        return "".join(buf)
                    continue
                count = 0
                if d == "\\":
                    e = self.read()
                    if e in _ESCAPES:
                        d = _ESCAPES[e]
                    else:
                        buf.append("\\")
                        d = e or ""
                buf.append(d)
        start = self.i - 1
        j = self.i
        s, n = self.s, self.n
        while j < n and _valid_string_char(s[j]):
            j += 1
        self.i = j
        return s[start:j]

    def parse_number(self) -> int | float:
        start = self.i - 1
        neg = self.ch == "-"
        num = 0
        if self.ch != ".":
            if self.ch.isdigit():
                num = ord(self.ch) - 48
            while True:
                p = self.peek()
                if p is None or not ("0" <= p <= "9"):
                    break
                num = num * 10 + (ord(p) - 48)
                self.i += 1
            if p != ".":
                self._tail(start)
                return -num if neg else num
        else:
            self._warn("leading_dot_number", start, self.s[start:start + 12].split("\n")[0])
        self.read()                   # quirk: after a leading '.', this consumes the first fraction digit
        f = 0.1
        val = float(num)
        while True:
            p = self.peek()
            if p is None or not ("0" <= p <= "9"):
                break
            val += (ord(p) - 48) * f
            self.i += 1
            f *= 0.1
        self._tail(start)
        return -val if neg else val

    def _tail(self, start: int) -> None:
        p = self.peek()
        if self.warn and p is not None and (p.isalpha() or p == "_"):
            self._warn("number_followed_by_letters", start, self.s[start:self.i + 8].split("\n")[0])

    def parse_array(self) -> list[Any]:
        out: list[Any] = []
        self.skip_ws()
        tok = self.next_token()
        while True:
            if tok == "EOF":
                raise self.err("EOF in array")
            if tok == "]":
                return out
            out.append(self.parse_object(tok))
            self.skip_ws()
            tok = self.next_token()
            if tok in (",", ";"):
                self.skip_ws()
                tok = self.next_token()

    def parse_object(self, tok: Any) -> Any:
        if isinstance(tok, tuple):
            return tok[1]
        if tok == "{":
            return self.parse_section()
        if tok == "[":
            return self.parse_array()
        if tok == "STR":
            return self.parse_string()
        if tok == "NUM":
            return self.parse_number()
        raise self.err(f"unexpected token {tok}")

    def parse_section(self, root: bool = False) -> PsSection:
        d = PsSection()
        d.line = self.line_of(max(0, self.i - 1)) if self._nl is not None else 0
        while True:
            self.skip_ws()
            tok = self.next_token(expect_string=True)
            if tok == "EOF":
                if not root:
                    raise self.err("EOF, expected '}'")
                return d
            if tok == "STR":
                kpos = self.i - 1
                key = self.parse_string()
                if key in d:
                    raise self.err(f"duplicate key '{key}'", kpos)
                self.skip_ws_same_line()
                tok = self.next_token()
                if tok == "=":
                    self.skip_ws()
                    d[key] = self.parse_object(self.next_token())
                elif tok == "{":
                    d[key] = self.parse_section()
                else:
                    raise self.err(f"expected '=' or '{{' after key '{key}', got {tok}")
                if self._nl is not None:
                    d.lines[key] = self.line_of(kpos)
            elif tok == "{":
                d[""] = self.parse_section()
            elif tok == "SSL":
                end = self.s.find("#ssl_end", self.i)
                if end < 0:
                    raise self.err("EOF, expected #ssl_end")
                d["#ssl"] = self.s[self.i:end].strip("\r\n")
                self.i = end + len("#ssl_end")
            elif tok == "}":
                if root:
                    raise self.err("unexpected '}' at root")
                return d
            elif tok in (",", ";"):
                continue
            else:
                raise self.err(f"unexpected token {tok}")


def editor_loads(text: str, warn: Any = None, lines: bool = True) -> PsSection:
    """Parse PS text exactly as the Mod Editor does (see the comment above); raises :class:`EditorParseError`."""
    if text.startswith("\ufeff"):
        text = text[1:]
    return _EditorParser(text, warn, lines).parse_section(root=True)


def editor_load(path: str | Path, warn: Any = None, lines: bool = True) -> PsSection:
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        return editor_loads(handle.read(), warn, lines)
