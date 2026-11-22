"""Writing marked blocks, and the fingerprint of files with generated parts (ADR-20261121-6c3d).

Finding blocks and fingerprinting live in `swerepo.fingerprint`; this module only adds and replaces them.
"""

from __future__ import annotations

import re
from pathlib import Path

from swerepo.fingerprint import HTML, BlockError, comment_style, find_block, fingerprint

ADR_INDEX = "swerepo:adr-index"  # the generated index in an ADR folder's README.md


def read_exact(path: Path, *, errors: str = "strict") -> str:
    """A file's text with its line endings as they are. (`Path.read_text` turns CRLF into LF, so writing that
    text back would change every line of a CRLF file.)"""
    with path.open(encoding="utf-8", errors=errors, newline="") as handle:
        return handle.read()


def inside(root: Path, path: Path) -> bool:
    """Whether `path` stays inside `root` (already resolved) after following every symbolic link: its own, and
    its folders'. For a path that doesn't exist yet, its nearest existing folder decides. SWERepo never writes
    through a link that leads out of the repository (review: Copilot on PR #6)."""
    probe = path
    while not probe.exists() and not probe.is_symlink() and probe != probe.parent:
        probe = probe.parent
    resolved = probe.resolve()
    return resolved == root or root in resolved.parents


def markers(style: str, marker: str = "swerepo") -> tuple[str, str]:
    if style == HTML:
        return f"<!-- {marker}:begin -->", f"<!-- {marker}:end -->"
    return f"# {marker}:begin", f"# {marker}:end"


def wrap(content: str, path: str, marker: str = "swerepo") -> str:
    """`content` between begin and end markers in the comment style of `path`, ending with a newline."""
    begin, end = markers(comment_style(path), marker)
    body = content if content.endswith("\n") or not content else content + "\n"
    return f"{begin}\n{body}{end}\n"


def lines(text: str) -> list[str]:
    """Lines with their endings, split on CR, LF and CRLF only: the same lines `find_block` numbers.
    (`str.splitlines` also splits on U+2028, form feeds and others, which would shift the numbers.)"""
    return re.findall(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$", text)


def append_block(text: str, content: str, path: str) -> str:
    """`text` exactly as it is, then a SWERepo block in the file's own line endings, after one blank line.
    Only line breaks are added before the block: as many as make one blank line (none when the text already
    ends with a blank line, two when it has no final line break). An empty file becomes the block alone."""
    newline = "\r\n" if "\r\n" in text else "\n"
    block = wrap(content, path).replace("\n", newline)
    if not text:
        return block
    ending = text[len(text.rstrip("\r\n")) :]  # linear: a searching regex here backtracks 2^n (P3-F10)
    breaks = len(re.findall(r"\r\n|\r|\n", ending))
    return text + newline * max(0, 2 - breaks) + block


def replace_block_content(text: str, content: str, *, style: str, marker: str) -> str:
    """`text` with the lines between the markers of `marker` replaced by `content`; the markers and
    everything outside them stay. Raises BlockError for malformed markers, ValueError if there is no block."""
    block = find_block(text, style=style, marker=marker)
    if block is None:
        raise ValueError(f"no {marker} block")
    split = lines(text)
    newline = "\r\n" if split[block.begin_line - 1].endswith("\r\n") else "\n"  # the block's own line endings
    body = content.replace("\r\n", "\n")
    body = (body if body.endswith("\n") or not body else body + "\n").replace("\n", newline)
    return "".join(split[: block.begin_line]) + body + "".join(split[block.end_line - 1 :])


def file_fingerprint(text: str, template: str) -> str:
    """The fingerprint SWERepo records and compares for a file it wrote. A generated part (the ADR index,
    rewritten by `swerepo adr index` with every new ADR) is left out, so it never makes the file look edited."""
    if template.startswith("docs/adr-readme@"):
        try:
            if find_block(text, style=HTML, marker=ADR_INDEX) is not None:
                text = replace_block_content(text, "", style=HTML, marker=ADR_INDEX)
        except BlockError:
            pass  # broken index markers: the whole text counts, so the file reads as changed (check reports it)
    return fingerprint(text)
