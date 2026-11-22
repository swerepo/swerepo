"""`swerepo adr new` and `swerepo adr index` (spec §6.5, ADR-20261121-0b7e).

ADR files are named `ADR-YYYYMMDD-xxxx-short-title.md` (SeamSpec's convention): the four random hex characters
keep two branches from picking the same name. The index in the folder's README.md is generated between
`<!-- swerepo:adr-index:begin -->` and `<!-- swerepo:adr-index:end -->`, so a merge conflict in it is fixed by
generating it again.
"""

from __future__ import annotations

import datetime
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from swerepo.blocks import ADR_INDEX, read_exact, replace_block_content
from swerepo.fingerprint import HTML, BlockError, find_block
from swerepo.render import TemplateStore

ADR_FILE = re.compile(r"^(?P<id>ADR-\d{8}-[0-9a-f]{4})(?:-[A-Za-z0-9._-]+)?\.md$")
_FIELD = re.compile(r"^(?P<key>[a-z_]+):\s*(?P<value>.*?)\s*$")
_HEADING = re.compile(r"^#\s+(?:ADR-\d{8}-[0-9a-f]{4}:\s*)?(?P<title>.+?)\s*$")
_PLACEHOLDER_ID = "ADR-YYYYMMDD-xxxx"
_PLACEHOLDER_TITLE = "One line that states the decision"


class AdrError(ValueError):
    """An ADR folder, README or index can't be used: missing, unreadable, or with broken markers."""


def _why(error: OSError | UnicodeError) -> str:
    """An error's reason without the file's absolute path (ADR-20261120-fc5a point 7)."""
    if isinstance(error, UnicodeError):
        return "not UTF-8 text"
    return error.strerror or type(error).__name__


@dataclass(frozen=True)
class Adr:
    id: str
    file: str  # the file name, relative to the ADR folder
    title: str
    status: str


def read_adr(path: Path) -> Adr:
    """The id (from the file name), title and status of an ADR. The title and status come from the
    frontmatter; without one, the title is the first heading and the status is unknown."""
    match = ADR_FILE.match(path.name)
    if match is None:
        raise AdrError(f"{path.name}: not an ADR file name (ADR-YYYYMMDD-xxxx-title.md)")
    try:
        text = path.read_text(encoding="utf-8", errors="replace").removeprefix("\ufeff")
    except OSError as error:
        raise AdrError(f"{path.name}: can't read it ({_why(error)})") from error
    lines = text.replace("\r\n", "\n").split("\n")
    fields: dict[str, str] = {}
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if field := _FIELD.match(line):
                fields[field["key"]] = _without_comment(field["value"])
    title = fields.get("title") or next((h["title"] for line in lines if (h := _HEADING.match(line))), path.stem)
    status = fields.get("status") or "?"
    successor = fields.get("superseded_by", "")
    if status.upper() == "SUPERSEDED" and successor and successor.lower() not in ("null", "none", "~"):
        status = f"{status} by {successor}"
    return Adr(id=match["id"], file=path.name, title=_cell(title), status=_cell(status))


_DOUBLE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_SINGLE = re.compile(r"'((?:[^']|'')*)'")
_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/"}


def _without_comment(value: str) -> str:
    """A frontmatter value: a quoted string as YAML reads it (a `#` inside it is text), else the text
    before a ` #` comment."""
    value = value.strip()
    if quoted := _DOUBLE.match(value):
        return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m[1], m[1]), quoted[1])
    if quoted := _SINGLE.match(value):
        return quoted[1].replace("''", "'")
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def yaml_text(text: str) -> str:
    """`text` as a YAML scalar: as it is when YAML reads it back unchanged, else double-quoted."""
    plain = re.fullmatch(r"[^\s\-?:,\[\]{}#&*!|>'\"%@`](?:[^:#]|:(?!\s)|(?<!\s)#)*", text)
    words = ("null", "true", "false", "yes", "no", "on", "off", "y", "n", "~")  # YAML 1.1 reads them as non-text
    risky = text.endswith(":") or text.lower() in words or text[:1] in "+-.0123456789"
    risky = risky or any(c in text for c in "\t\r\n")
    return text if plain and not risky else json.dumps(text, ensure_ascii=False)


def _cell(text: str) -> str:
    """Text safe inside one Markdown table cell."""
    return " ".join(text.split()).replace("|", "\\|")


def list_adrs(folder: Path) -> list[Adr]:
    """Every ADR file directly in `folder`, oldest first (by name: the date, then the random part)."""
    return [read_adr(p) for p in sorted(folder.glob("ADR-*.md")) if p.is_file() and ADR_FILE.match(p.name)]


def index_table(adrs: list[Adr]) -> str:
    rows = [f"| [{a.id}]({a.file}) | {a.title} | {a.status} |" for a in adrs]
    return "\n".join(["| ID | Title | Status |", "|---|---|---|", *rows]) + "\n"


def with_index(readme: str, adrs: list[Adr]) -> str:
    """The README text with its index regenerated. Raises AdrError when it has no index markers."""
    try:
        if find_block(readme, style=HTML, marker=ADR_INDEX) is None:
            raise AdrError(f"no index markers (<!-- {ADR_INDEX}:begin --> … <!-- {ADR_INDEX}:end -->)")
        return replace_block_content(readme, index_table(adrs), style=HTML, marker=ADR_INDEX)
    except BlockError as error:
        raise AdrError(f"index markers are broken: {error}") from error


def write_index(folder: Path, *, label: str | None = None) -> bool:
    """Regenerate `<folder>/README.md`'s index. True if the file changed. `label`: the folder as messages
    name it (repository-relative), never its absolute path."""
    name = f"{label or folder.name}/README.md"
    readme = folder / "README.md"
    if not readme.is_file():
        raise AdrError(f"{name} is missing")
    try:
        text = read_exact(readme)
    except (OSError, UnicodeError) as error:
        raise AdrError(f"{name}: can't read it ({_why(error)})") from error
    updated = with_index(text, list_adrs(folder))
    if updated == text:
        return False
    try:
        readme.write_text(updated, encoding="utf-8", newline="")
    except OSError as error:
        raise AdrError(f"{name}: can't write it ({_why(error)})") from error
    return True


def slug(title: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return words[:60].rstrip("-") or "decision"


def new_adr(
    folder: Path,
    title: str,
    *,
    today: datetime.date | None = None,
    token: str | None = None,
    store: TemplateStore | None = None,
    label: str | None = None,
) -> Path:
    """Create an ADR in `folder` from its TEMPLATE.md (or SWERepo's template), with a fresh name.
    `label`: the folder as messages name it (repository-relative)."""
    where = label or folder.name
    title = " ".join(title.split())
    if not title:
        raise AdrError("the title is empty")
    if not folder.is_dir():
        raise AdrError(f"{where}/ doesn't exist (swerepo init --only docs creates it)")
    day = today or datetime.date.today()
    own = folder / "TEMPLATE.md"
    if own.is_file():
        try:
            template = own.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise AdrError(f"{where}/TEMPLATE.md: can't read it ({_why(error)})") from error
    else:
        template = (store or TemplateStore()).latest("docs", "adr-template").text
    for _ in range(20):
        adr_id = f"ADR-{day:%Y%m%d}-{token or secrets.token_hex(2)}"
        target = folder / f"{adr_id}-{slug(title)}.md"
        if not any(folder.glob(f"{adr_id}*.md")):
            break
        if token is not None:
            raise AdrError(f"{adr_id} already exists")
    else:  # pragma: no cover - 20 collisions in 65536
        raise AdrError("couldn't find a free ADR id")
    text = template.replace(_PLACEHOLDER_ID, adr_id).replace("YYYY-MM-DD", f"{day:%Y-%m-%d}")
    text = text.replace(f"title: {_PLACEHOLDER_TITLE}", f"title: {yaml_text(title)}")  # frontmatter: YAML
    text = text.replace(_PLACEHOLDER_TITLE, title)  # the heading: as written
    try:
        with target.open("x", encoding="utf-8", newline="") as handle:  # never replaces a file
            handle.write(text)
    except OSError as error:
        raise AdrError(f"{where}/{target.name}: can't write it ({_why(error)})") from error
    return target
