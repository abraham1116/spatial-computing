"""SPATIAL Q lexer."""
from __future__ import annotations

import re
from dataclasses import dataclass

KEYWORDS = {
    "quantum", "task", "main", "on", "qubit", "let", "for", "in", "while", "if", "else",
    "return", "print", "parallel", "measure", "reset", "sample", "shots", "expect", "of",
    "workload", "true", "false", "and", "or", "not",
}

_TOKEN = re.compile(r"""
    (?P<ws>[ \t\r]+|//[^\n]*)
  | (?P<nl>\n)
  | (?P<num>\d+\.(?!\.)\d*(?:[eE][-+]?\d+)?|\d+[eE][-+]?\d+|\.\d+|\d+)
  | (?P<str>"[^"\n]*")
  | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>->|\.\.|==|!=|<=|>=|[-+*/%<>=(){}\[\],;:!])
""", re.X)


@dataclass
class Tok:
    kind: str     # num | str | id | kw | op | eof
    val: object
    line: int
    col: int


class SQSyntaxError(SyntaxError):
    pass


def lex(src: str) -> list[Tok]:
    out, pos, line, line_start = [], 0, 1, 0
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if not m:
            raise SQSyntaxError(f"line {line}:{pos - line_start + 1}: unexpected character {src[pos]!r}")
        kind = m.lastgroup
        text = m.group()
        col = pos - line_start + 1
        pos = m.end()
        if kind == "ws":
            continue
        if kind == "nl":
            line += 1
            line_start = pos
            continue
        if kind == "num":
            is_float = any(c in text for c in ".eE")
            out.append(Tok("num", float(text) if is_float else int(text), line, col))
        elif kind == "str":
            out.append(Tok("str", text[1:-1], line, col))
        elif kind == "id":
            out.append(Tok("kw" if text in KEYWORDS else "id", text, line, col))
        else:
            out.append(Tok("op", text, line, col))
    out.append(Tok("eof", None, line, 0))
    return out
