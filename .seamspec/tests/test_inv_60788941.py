"""Rule: `swerepo update` never changes a file a person edited without a deliberate yes, and never writes conflict
markers (ADR-20261124-7afa; SWEREPO-SPEC §16). Without `--yes` and without a terminal nothing is written; a no at
the terminal's "Apply?" writes nothing; `--yes` alone updates only what nobody edited; a yes at the terminal, or
`--yes --merge`, merges the update into the person's edits, keeping them and the text around SWERepo's block; a
conflict, or an earlier render that can't be rebuilt, leaves the file byte for byte. A fixture repository set up by
`swerepo init`, with a line of the person's after SWERepo's block in AGENTS.md; its AGENTS.md block and
`docs/agents/address-review.md` are put back to their version 1 templates, as an older SWERepo wrote them, so there
are updates to apply."""

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from swerepo import cli
from swerepo.blocks import file_fingerprint, replace_block_content
from swerepo.cli import app
from swerepo.fingerprint import HTML, find_block, fingerprint
from swerepo.render import TemplateStore
from swerepo.state import Record, State

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t",
       "-c", "user.email=t@example.com"]  # fmt: skip
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
MINE = "A rule of my own."
AFTER = "My closing note, after SWERepo's block."  # the person's line below `<!-- swerepo:end -->`
RUNBOOK = "docs/agents/address-review.md"
NEW = "swerepo threads"  # what both version 2 templates add
BEGIN, END = "<!-- swerepo:begin", "<!-- swerepo:end"


def _set_up(root: Path) -> None:
    root.mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / "uv.lock").write_text("version = 1\n")
    (root / "CLAUDE.md").write_text("# Mine\n")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    done = CliRunner().invoke(app, ["init", "--path", str(root), "--yes", "--code-owner", "@dev"])
    assert done.exit_code == 0, done.output
    agents = (root / "AGENTS.md").read_text()
    assert agents.rstrip("\n").endswith("-->")  # init's block ends the file: the person adds a line after it
    (root / "AGENTS.md").write_text(agents + f"\n{AFTER}\n")
    subprocess.run([*GIT, "-C", str(root), "add", "-A"], check=True)
    subprocess.run([*GIT, "-C", str(root), "commit", "-q", "-m", "set up"], check=True)


def _older_agents_block(root: Path, edit=None) -> str:
    """AGENTS.md's block as `agents/block@1` wrote it, recorded so; `edit` changes it as a person would."""
    state = State.load(root)
    record = state.blocks()["AGENTS.md"]
    old = TemplateStore().get("agents/block@1").render(record.inputs or {})
    text = (root / "AGENTS.md").read_text()
    shown = edit(old) if edit else old
    (root / "AGENTS.md").write_text(replace_block_content(text, shown, style=HTML, marker="swerepo"))
    state.set_block("AGENTS.md", Record("agents/block@1", fingerprint(old), fingerprint(old), record.inputs))
    state.save(root)
    return old


def _older_runbook(root: Path, edit=None) -> str:
    """The runbook as `agents/address-review@1` wrote it, recorded so; `edit` changes it as a person would."""
    state = State.load(root)
    record = state.files()[RUNBOOK]
    old = TemplateStore().get("agents/address-review@1").render(record.inputs or {})
    (root / RUNBOOK).write_text(edit(old) if edit else old)
    mark = file_fingerprint(old, "agents/address-review@1")
    state.set_file(RUNBOOK, Record("agents/address-review@1", mark, mark, record.inputs))
    state.save(root)
    return old


def _edited(root: Path) -> None:
    """The AGENTS.md block edited by the person; the runbook older and untouched."""
    _set_up(root)
    _older_agents_block(root, edit=lambda old: old.replace("\n", f"\n{MINE}\n", 1))
    _older_runbook(root)


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and ".git" not in p.relative_to(root).parts}  # fmt: skip


def _update(root: Path, *flags: str, code: int = 0, answer: str | None = None):
    done = CliRunner().invoke(app, ["update", "--path", str(root), *flags], input=answer)
    assert done.exit_code == code, done.output
    return done


def _block(root: Path) -> str:
    found = find_block((root / "AGENTS.md").read_text(), style=HTML)
    assert found is not None
    return found.content


def _outside(text: str) -> tuple[str, str]:
    """The text before SWERepo's block and after its end marker line: the person's."""
    after_end = text.find("\n", text.index(END))
    outside = text[: text.index(BEGIN)], text[after_end:] if after_end != -1 else ""
    assert AFTER in outside[1]
    return outside


def _no_markers(root: Path) -> None:
    for name, data in _files(root).items():
        for line in data.decode(errors="replace").splitlines():
            assert not line.startswith(("<" * 7, "=" * 7, ">" * 7)), name


def _merged(root: Path, outside: tuple[str, str]) -> None:
    merged = _block(root)
    assert MINE in merged and NEW in merged  # the person's line and the update's
    assert _outside((root / "AGENTS.md").read_text()) == outside  # the text around the block: untouched
    _no_markers(root)


def test_without_a_deliberate_yes_nothing_the_person_edited_changes(tmp_path: Path, monkeypatch):
    root = tmp_path / "app"
    _edited(root)
    before = _files(root)
    done = _update(root, code=2)  # no --yes, no terminal: something to apply, nothing applied
    assert "nothing applied" in done.output and _files(root) == before
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    done = _update(root, answer="n\n")  # a terminal, and the person says no
    assert "Apply?" in done.output and _files(root) == before
    monkeypatch.setattr(cli, "_interactive", lambda: False)
    done = _update(root, "--yes")  # --yes alone: what nobody edited, never into a person's edits
    assert "--merge" in done.output
    assert (root / "AGENTS.md").read_bytes() == before["AGENTS.md"]
    assert NEW in (root / RUNBOOK).read_text() and (root / RUNBOOK).read_bytes() != before[RUNBOOK]


def test_a_yes_at_the_terminal_merges(tmp_path: Path, monkeypatch):
    root = tmp_path / "app"
    _edited(root)
    outside = _outside((root / "AGENTS.md").read_text())
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    assert "Apply?" in _update(root, answer="y\n").output
    _merged(root, outside)


def test_yes_and_merge_merges(tmp_path: Path):
    root = tmp_path / "app"
    _edited(root)
    outside = _outside((root / "AGENTS.md").read_text())
    _update(root, "--yes", "--merge")
    _merged(root, outside)


def test_a_whole_file_the_person_edited(tmp_path: Path):
    root = tmp_path / "app"
    _set_up(root)
    _older_runbook(root, edit=lambda old: old + f"\n{MINE}\n")
    before = (root / RUNBOOK).read_bytes()
    _update(root, "--yes")
    assert (root / RUNBOOK).read_bytes() == before  # --yes alone: never into a person's edits
    _update(root, "--yes", "--merge")
    text = (root / RUNBOOK).read_text()
    assert MINE in text and NEW in text
    _no_markers(root)


def test_a_conflict_leaves_the_file_byte_for_byte(tmp_path: Path):
    root = tmp_path / "app"
    _set_up(root)
    inputs = State.load(root).blocks()["AGENTS.md"].inputs or {}
    old = TemplateStore().get("agents/block@1").render(inputs)
    new = TemplateStore().get("agents/block@2").render(inputs)
    first = next(a for a, b in zip(old.splitlines(), new.splitlines(), strict=False) if a != b)
    _older_agents_block(root, edit=lambda text: text.replace(first, first + " (mine)"))
    before = (root / "AGENTS.md").read_bytes()
    done = _update(root, "--yes", "--merge")
    assert "conflict" in done.output and (root / "AGENTS.md").read_bytes() == before
    _no_markers(root)


def test_no_merge_against_an_earlier_render_that_doesnt_rebuild(tmp_path: Path):
    root = tmp_path / "app"
    _set_up(root)
    _older_agents_block(root, edit=lambda old: old.replace("\n", f"\n{MINE}\n", 1))
    state = State.load(root)
    record = state.blocks()["AGENTS.md"]
    state.set_block("AGENTS.md", Record(record.template, fingerprint("not it"), record.written, record.inputs))
    state.save(root)
    before = (root / "AGENTS.md").read_bytes()
    done = _update(root, "--yes", "--merge")
    assert "can't merge" in done.output and (root / "AGENTS.md").read_bytes() == before
