"""`swerepo progress`: Now, Next and the latest progress entries, for people and agents (spec §6.5).

Read-only. `docs/PROGRESS.md` holds Now and Next; `docs/progress/` (or `[adopted] progress_dir`) holds one
entry per pull request, named `YYYYMMDD-<slug>.md`, so the newest sort last by name.
"""

from __future__ import annotations

import re
from pathlib import Path

from swerepo import standard

_SECTION = re.compile(r"^##\s+(?P<name>.+?)\s*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def sections(text: str, names: tuple[str, ...] = ("Now", "Next")) -> list[tuple[str, str]]:
    """The `## <name>` sections of a Markdown text, in file order, each up to the next `## ` heading."""
    found: list[tuple[str, str]] = []
    current: str | None = None
    lines: list[str] = []
    fence: str | None = None
    for line in re.split(r"\r\n|\r|\n", text):
        opening = _FENCE.match(line)
        rest = line[opening.end() :] if opening else ""
        was_fenced = fence is not None
        if opening and fence is None and not (opening[1][0] == "`" and "`" in rest):
            fence = opening[1]  # CommonMark, as fingerprint.find_block: a backtick fence's info has no backticks
        elif (
            opening and fence and opening[1][0] == fence[0] and len(opening[1]) >= len(fence) and not rest.strip(" \t")
        ):
            fence = None  # a closing fence: the same character, at least as long, then only spaces or tabs
        heading = None if was_fenced or fence is not None else _SECTION.match(line)
        if heading is None:
            if current is not None:
                lines.append(line)
            continue
        if current is not None:
            found.append((current, "\n".join(lines).strip()))
        current, lines = (heading["name"] if heading["name"] in names else None), []
    if current is not None:
        found.append((current, "\n".join(lines).strip()))
    return found


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def latest_entries(folder: Path, count: int) -> list[Path]:
    if count <= 0 or not folder.is_dir():
        return []
    entries = sorted(p for p in folder.glob("*.md") if p.is_file())
    return list(reversed(entries[-count:]))


def report(root: Path, *, progress_dir: str | None = None, count: int = 3) -> str:
    """The text `swerepo progress` prints."""
    out: list[str] = []
    progress_file = root / standard.PROGRESS_FILE
    text = _read(progress_file) if progress_file.is_file() else None
    if text is not None:
        for name, body in sections(text):
            out += [f"## {name}", "", body or "(empty)", ""]
    elif progress_file.is_file():
        out += [f"({standard.PROGRESS_FILE} can't be read)", ""]
    else:
        out += [f"({standard.PROGRESS_FILE} is missing: swerepo init --only docs creates it)", ""]
    folder = progress_dir or standard.PROGRESS_DIR
    entries = latest_entries(root / folder, count)
    if entries:
        out += [f"## Latest entries in {folder}/", ""]
        for entry in entries:
            body = _read(entry)
            out += [f"### {entry.name}", "", body.strip() if body is not None else "(can't be read)", ""]
    else:
        out += [f"(no entries in {folder}/ yet)", ""]
    return "\n".join(out).rstrip() + "\n"
