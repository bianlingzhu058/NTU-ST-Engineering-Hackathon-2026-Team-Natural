"""A minimal YAML subset parser, standard-library only (no pyyaml, no pip).

Supports exactly what our config and objective files use:
  - nested mappings by indentation (2 spaces)
  - list items with '- '
  - scalars: int, float, bool, null, quoted and bare strings
  - inline flow lists:  key: [a, b, c]
  - inline flow maps:   args: {name: edge, x: 10}
  - comments beginning with #

It is deliberately small. If a file needs more than this, simplify the file.
"""
from __future__ import annotations

from typing import Any


def _scalar(token: str) -> Any:
    t = token.strip()
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        return t[1:-1]
    low = t.lower()
    if low in ("null", "~", ""):
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        if t.lstrip("-").isdigit():
            return int(t)
        return float(t)
    except ValueError:
        return t


def _split_top(s: str) -> list[str]:
    """Split on commas not inside brackets/quotes."""
    out, depth, cur, q = [], 0, [], None
    for ch in s:
        if q:
            cur.append(ch)
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            cur.append(ch)
        elif ch in "[{":
            depth += 1
            cur.append(ch)
        elif ch in "]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return [x for x in (p.strip() for p in out) if x != ""]


def _flow(token: str) -> Any:
    t = token.strip()
    if t.startswith("[") and t.endswith("]"):
        inner = t[1:-1].strip()
        return [_value(x) for x in _split_top(inner)] if inner else []
    if t.startswith("{") and t.endswith("}"):
        inner = t[1:-1].strip()
        result = {}
        for pair in _split_top(inner):
            k, _, v = pair.partition(":")
            result[k.strip()] = _value(v)
        return result
    return _scalar(t)


def _value(token: str) -> Any:
    t = token.strip()
    if t.startswith(("[", "{")):
        return _flow(t)
    return _scalar(t)


def _looks_like_mapping(item: str) -> bool:
    """True only if a list item is really 'key: value', not a URL or scalar.

    YAML treats a colon as a key separator only when followed by whitespace or
    end-of-string. 'https://x' has no such colon, so it stays a scalar.
    """
    if item.startswith(("[", "{", '"', "'")):
        return False
    q = None
    for i, ch in enumerate(item):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == ":" and (i + 1 == len(item) or item[i + 1] == " "):
            return True
    return False


def _strip_comment(line: str) -> str:
    q = None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "#":
            return line[:i]
    return line


class _Line:
    __slots__ = ("indent", "text")

    def __init__(self, indent: int, text: str):
        self.indent = indent
        self.text = text


def _prepare(text: str) -> list[_Line]:
    lines = []
    for raw in text.splitlines():
        stripped = _strip_comment(raw).rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        lines.append(_Line(indent, stripped.strip()))
    return lines


def _parse_block(lines: list[_Line], start: int, indent: int) -> tuple[Any, int]:
    # Decide list vs map by the first line at this indent.
    if lines[start].text.startswith("- "):
        return _parse_list(lines, start, indent)
    return _parse_map(lines, start, indent)


def _parse_map(lines: list[_Line], start: int, indent: int) -> tuple[dict, int]:
    result: dict = {}
    i = start
    while i < len(lines) and lines[i].indent == indent:
        line = lines[i]
        key, _, rest = line.text.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "":
            # value is a nested block on following, more-indented lines
            if i + 1 < len(lines) and lines[i + 1].indent > indent:
                child, i = _parse_block(lines, i + 1, lines[i + 1].indent)
                result[key] = child
            else:
                result[key] = None
                i += 1
        else:
            result[key] = _value(rest)
            i += 1
    return result, i


def _parse_list(lines: list[_Line], start: int, indent: int) -> tuple[list, int]:
    result: list = []
    i = start
    while i < len(lines) and lines[i].indent == indent and lines[i].text.startswith("- "):
        item = lines[i].text[2:].strip()
        if item.startswith("- ") or item == "-":
            # Nested list item: "- - value" (and more "- ..." lines indented under it).
            # Re-read this item and its continuation lines as their own list block.
            inner_indent = indent + 2
            synthetic = [_Line(inner_indent, item)]
            j = i + 1
            while j < len(lines) and lines[j].indent > indent:
                synthetic.append(_Line(lines[j].indent, lines[j].text))
                j += 1
            child, _ = _parse_list(synthetic, 0, inner_indent)
            result.append(child)
            i = j
        elif _looks_like_mapping(item):
            # inline first key of a mapping item; re-read as a small map block
            synthetic = [_Line(indent + 2, item)]
            j = i + 1
            while j < len(lines) and lines[j].indent > indent:
                synthetic.append(_Line(lines[j].indent, lines[j].text))
                j += 1
            child, _ = _parse_map(synthetic, 0, indent + 2)
            result.append(child)
            i = j
        else:
            result.append(_value(item))
            i += 1
    return result, i


def load_yaml(text: str) -> Any:
    lines = _prepare(text)
    if not lines:
        return {}
    value, _ = _parse_block(lines, 0, lines[0].indent)
    return value
