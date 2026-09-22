from __future__ import annotations

import re
from typing import Iterator

_TOKEN = re.compile(r'(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+)|\s+')
_NUM = re.compile(r'^[-+]?(?:\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$')


class Sym(str):
    """A bare symbol, as opposed to a quoted string."""
    __slots__ = ()


def _atom(text: str):
    if _NUM.match(text):
        return float(text) if any(c in text for c in ".eE") else int(text)
    return Sym(text)


def loads(text: str) -> list:
    stack: list[list] = []
    root: list | None = None
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None:
            raise ValueError(f"bad token at {pos}: {text[pos:pos + 40]!r}")
        pos = m.end()
        if m.group(1):                       # (
            node: list = []
            if stack:
                stack[-1].append(node)
            elif root is None:
                root = node
            else:
                raise ValueError("more than one top-level expression")
            stack.append(node)
        elif m.group(2):                     # )
            if not stack:
                raise ValueError("unbalanced ')'")
            stack.pop()
        elif m.group(3) is not None:         # "quoted"
            stack[-1].append(m.group(3).encode().decode("unicode_escape"))
        elif m.group(4):                     # bare
            stack[-1].append(_atom(m.group(4)))
    if stack or root is None:
        raise ValueError("unbalanced input")
    return root


def load(path) -> list:
    with open(path, encoding="utf-8") as fh:
        return loads(fh.read())


def name(node) -> str | None:
    """Node name, or None for an atom."""
    if isinstance(node, list) and node and isinstance(node[0], str):
        return str(node[0])
    return None


def kids(node: list, want: str) -> list[list]:
    return [c for c in node[1:] if isinstance(c, list) and name(c) == want]


def kid(node: list, want: str) -> list | None:
    found = kids(node, want)
    return found[0] if found else None


def val(node: list, want: str, default=None):
    """First argument of the first child named `want`."""
    c = kid(node, want)
    return c[1] if c is not None and len(c) > 1 else default


def walk(node) -> Iterator[list]:
    if isinstance(node, list):
        yield node
        for c in node:
            if isinstance(c, list):
                yield from walk(c)


def find(node, want: str) -> Iterator[list]:
    """Every node named `want`, anywhere in the tree."""
    for n in walk(node):
        if name(n) == want:
            yield n