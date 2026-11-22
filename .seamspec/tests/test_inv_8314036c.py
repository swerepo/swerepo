"""Rule: `swerepo init` never replaces or edits a file it didn't write: a person's file is either left
byte for byte, or keeps its whole text byte for byte, blank lines at its end included, followed only by the
line breaks that make one blank line and SWERepo's marked block, in the file's own line endings. A file or
block a person changed after init is left alone by the next run. A file or block that appears between the
plan and applying it stops init with nothing written (ADR-20261121-6c3d; SWEREPO-SPEC §5 principles 2, 3)."""

import re
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from swerepo.cli import app
from swerepo.init import InitError, apply, make_plan

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]
OUR_ADR = "docs/adr/ADR-20260101-abcd-ours.md"
THEIRS = {
    "README.md": "# Ours\n\nOur words.\n",
    "AGENTS.md": "# Our rules\r\n\r\nBe kind.\r\n\r\n\r\n",  # CRLF, ending in two blank lines
    "CLAUDE.md": "Use tabs.",  # no final newline
    "CONTRIBUTING.md": "# Help\n",
    "CHANGELOG.md": "# Changes\n",
    "docs/PROGRESS.md": "# Where we are\n",
    OUR_ADR: "---\ntitle: Use Postgres\nstatus: ACCEPTED\n---\n\nOurs.\n",
}


def _repo(root: Path) -> Path:
    for name, text in THEIRS.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(text.encode())
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run([*GIT, "-c", "user.email=t@example.com", "-C", str(root), "add", "-A"], check=True)
    subprocess.run([*GIT, "-c", "user.email=t@example.com", "-C", str(root), "commit", "-qm", "x"], check=True)
    return root


def _init(root: Path) -> None:
    result = CliRunner().invoke(app, ["init", "--path", str(root), "--yes"])
    assert result.exit_code == 0, result.output


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {p.relative_to(root).as_posix(): p.read_bytes() if p.is_file() else None for p in root.rglob("*")}


def test_existing_text_is_kept_exactly_and_only_gains_a_block(tmp_path: Path):
    _init(_repo(tmp_path))
    changed = set()
    for name, text in THEIRS.items():
        now = (tmp_path / name).read_bytes().decode()  # as on disk: every byte counts
        if now == text:
            continue
        changed.add(name)
        nl = "\r\n" if "\r\n" in text else "\n"
        assert now.startswith(text), name  # the whole text, blank lines at its end included
        rest = now[len(text) :]
        gap = re.match(r"(?:\r\n|\n)*", rest).group(0)
        block = rest[len(gap) :]
        assert (text + gap).endswith(nl + nl) and len(gap) <= 2 * len(nl), name  # one blank line, no more added
        assert block.startswith("<!-- swerepo:begin -->" + nl) and block.endswith("<!-- swerepo:end -->" + nl), name
        assert block.count("<!-- swerepo:begin -->") == 1 and (nl == "\n" or "\n" not in block.replace("\r\n", "")), (
            name
        )
    assert changed == {"AGENTS.md", "CLAUDE.md"}  # both gained a block; the CRLF and no-final-newline cases ran
    index = (tmp_path / "docs/adr/README.md").read_text()  # created by init, listing the person's own ADR
    assert "| [ADR-20260101-abcd](ADR-20260101-abcd-ours.md) | Use Postgres | ACCEPTED |" in index


def test_what_a_person_changed_after_init_is_left_alone(tmp_path: Path):
    _init(_repo(tmp_path))
    agents = (tmp_path / "AGENTS.md").read_text().replace("## Commands", "## Our commands")
    (tmp_path / "AGENTS.md").write_text(agents)
    (tmp_path / "docs/agents/prepare-pr.md").write_text("# Our way\n")
    _init(tmp_path)
    assert (tmp_path / "AGENTS.md").read_text() == agents
    assert (tmp_path / "docs/agents/prepare-pr.md").read_text() == "# Our way\n"


def test_a_file_that_appears_after_the_plan_stops_init_with_nothing_written(tmp_path: Path):
    plan = make_plan(_repo(tmp_path), hosts=["claude"])
    assert any(a.path == "docs/agents/record-adr.md" and a.verb == "create" for a in plan.actions)
    (tmp_path / "docs/agents").mkdir(parents=True)
    (tmp_path / "docs/agents/record-adr.md").write_text("# Written meanwhile\n")
    meanwhile = _snapshot(tmp_path)
    with pytest.raises(InitError):
        apply(plan, tmp_path)
    assert _snapshot(tmp_path) == meanwhile  # not replaced, and no other file or block written either


def test_a_block_that_appears_after_the_plan_stops_init_with_nothing_written(tmp_path: Path):
    plan = make_plan(_repo(tmp_path), hosts=["claude"])
    assert any(a.path == "CLAUDE.md" and a.verb == "add block" for a in plan.actions)
    (tmp_path / "CLAUDE.md").write_text("Use tabs.\n<!-- swerepo:begin -->\nours\n<!-- swerepo:end -->\n")
    meanwhile = _snapshot(tmp_path)
    with pytest.raises(InitError):
        apply(plan, tmp_path)
    assert _snapshot(tmp_path) == meanwhile  # not doubled, and nothing else written either
