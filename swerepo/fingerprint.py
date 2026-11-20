"""Fingerprints of generated text, and marked blocks inside files people also edit (ADR-20261120-9495).

A fingerprint is the SHA-256 of normalised text, so line-ending conversion, trailing whitespace and
end-of-file fixers never make a file look edited, while every other change does.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

_BOM = "﻿"
HEX_LENGTH = 64


def normalise(text: str | bytes) -> str:
    """The text a fingerprint is taken of: no BOM, LF line endings, no trailing whitespace on any line,
    exactly one final newline (an empty text stays empty)."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="surrogateescape")
    text = text.removeprefix(_BOM)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def fingerprint(text: str | bytes) -> str:
    """SHA-256 of the normalised text, as 64 lower-case hex characters."""
    data = normalise(text).encode("utf-8", errors="surrogateescape")
    return hashlib.sha256(data).hexdigest()


def is_fingerprint(value: object) -> bool:
    return isinstance(value, str) and len(value) == HEX_LENGTH and all(c in "0123456789abcdef" for c in value)


# --- marked blocks -------------------------------------------------------------------------------

HTML = "html"  # Markdown: <!-- swerepo:begin --> … <!-- swerepo:end -->
HASH = "hash"  # .gitignore, CODEOWNERS, TOML, YAML, Python, shell: # swerepo:begin … # swerepo:end

_HTML_SUFFIXES = {".md", ".markdown", ".html", ".htm"}


def comment_style(path: str) -> str:
    """The comment style used for markers in this file, from its name."""
    return HTML if PurePosixPath(path).suffix.lower() in _HTML_SUFFIXES else HASH


class BlockError(ValueError):
    """A marked block is malformed: a begin without an end, an end without a begin, or two blocks."""


@dataclass(frozen=True)
class Block:
    begin_line: int  # 1-based line number of the begin marker
    end_line: int  # 1-based line number of the end marker
    content: str  # the lines strictly between the markers, each ending with "\n"


def _marker_pattern(marker: str, edge: str, style: str) -> re.Pattern[str]:
    name = re.escape(f"{marker}:{edge}")
    if style == HTML:
        # The note after the name may not contain "-->": a marker line holds one comment and nothing else.
        return re.compile(rf"<!--\s*{name}(?:\s(?:(?!-->).)*)?-->\s*")
    if style == HASH:
        return re.compile(rf"#\s*{name}(?:\s.*)?")
    raise ValueError(f"unknown comment style {style!r}")


# A Markdown code fence: three or more backticks or tildes, indented at most three spaces (CommonMark).
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def find_block(text: str, *, style: str, marker: str = "swerepo") -> Block | None:
    """The block between `<marker>:begin` and `<marker>:end`, or None if the text has no such block.
    In Markdown (HTML style), markers inside fenced code blocks are examples, not markers."""
    begin_re = _marker_pattern(marker, "begin", style)
    end_re = _marker_pattern(marker, "end", style)
    lines = text.removeprefix(_BOM).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    begin: int | None = None
    found: Block | None = None
    fence: str | None = None
    for index, line in enumerate(lines):
        number = index + 1
        if style == HTML and (opening := _FENCE.match(line)):
            mark = opening[1]
            if fence is None:
                # CommonMark: a backtick fence's info string has no backticks; "```a``` text" is inline code.
                if mark[0] != "`" or "`" not in line[opening.end() :]:
                    fence = mark
                    continue
            elif mark[0] == fence[0] and len(mark) >= len(fence) and not line.strip().strip(mark[0]):
                fence = None
                continue
        if fence is not None:
            continue
        if begin_re.fullmatch(line.strip()):
            if begin is not None:
                raise BlockError(f"line {number}: `{marker}:begin` inside the block opened on line {begin}")
            if found is not None:
                raise BlockError(f"line {number}: a second `{marker}` block (the first is on line {found.begin_line})")
            begin = number
        elif end_re.fullmatch(line.strip()):
            if begin is None:
                raise BlockError(f"line {number}: `{marker}:end` without a `{marker}:begin` before it")
            content = "".join(f"{body}\n" for body in lines[begin:index])
            found = Block(begin_line=begin, end_line=number, content=content)
            begin = None
    if begin is not None:
        raise BlockError(f"line {begin}: `{marker}:begin` has no `{marker}:end` after it")
    return found
