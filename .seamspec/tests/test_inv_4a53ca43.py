"""Rule: `swerepo update --dry-run` writes nothing, `swerepo update` changes only what SWERepo wrote (and
`.swerepo.toml`), and a second `swerepo update` writes nothing (ADR-20261124-7afa; SWEREPO-SPEC §16). A fixture
repository with files of the person's own, set up by `swerepo init`, with a line of the person's after SWERepo's
block in AGENTS.md; its AGENTS.md block is put back to `agents/block@1`, as an older SWERepo wrote it, so there is an
update to apply: to the latest `agents/block` version, whichever that is (replaces inv_9265607a, which named
`agents/block@2`; ADR-20261124-4d76, review P8-D02)."""

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from swerepo.blocks import replace_block_content
from swerepo.cli import app
from swerepo.fingerprint import HTML, find_block, fingerprint
from swerepo.render import TemplateStore
from swerepo.state import Record, State

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t",
       "-c", "user.email=t@example.com"]  # fmt: skip
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
MINE = {  # the person's own files: SWERepo didn't write them
    "CLAUDE.md": "# Mine\r\n\r\nMy notes, CRLF and all.\r\n",
    "README.md": "# app\n",
    ".github/swerepo/ruleset.json": json.dumps({"name": "swerepo", "rules": []}, indent=2) + "\n",
}
AFTER = "My closing note, after SWERepo's block."  # the person's line below `<!-- swerepo:end -->`
BEGIN, END = "<!-- swerepo:begin", "<!-- swerepo:end"


def _snapshot(root: Path) -> dict[str, tuple[int, int, bytes]]:
    return {p.relative_to(root).as_posix(): (p.stat().st_mtime_ns, p.stat().st_size, p.read_bytes())
            for p in sorted(root.rglob("*")) if p.is_file()}  # fmt: skip


def _outside(text: str) -> tuple[str, str]:
    """The text before SWERepo's block and after its end marker line: the person's."""
    after_end = text.find("\n", text.index(END))
    outside = text[: text.index(BEGIN)], text[after_end:] if after_end != -1 else ""
    assert AFTER in outside[1]
    return outside


def test_update_writes_only_what_swerepo_wrote_and_only_once(tmp_path: Path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / "uv.lock").write_text("version = 1\n")
    for name, text in MINE.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(text.encode())
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    done = CliRunner().invoke(app, ["init", "--path", str(root), "--yes", "--code-owner", "@dev"])
    assert done.exit_code == 0, done.output
    mine = {name: (root / name).read_bytes() for name in MINE}  # as init left them (CLAUDE.md gained a block)
    agents = (root / "AGENTS.md").read_text()
    assert agents.rstrip("\n").endswith("-->")  # init's block ends the file: the person adds a line after it
    (root / "AGENTS.md").write_text(agents + f"\n{AFTER}\n")
    state = State.load(root)
    record = state.blocks()["AGENTS.md"]
    old = TemplateStore().get("agents/block@1").render(record.inputs or {})
    latest = TemplateStore().latest("agents", "block")
    assert latest.id != "agents/block@1"
    new = latest.render(record.inputs or {})
    assert old != new
    text = (root / "AGENTS.md").read_text()
    (root / "AGENTS.md").write_text(replace_block_content(text, old, style=HTML, marker="swerepo"))
    state.set_block("AGENTS.md", Record("agents/block@1", fingerprint(old), fingerprint(old), record.inputs))
    state.save(root)
    outside = _outside((root / "AGENTS.md").read_text())

    before = _snapshot(root)
    dry = CliRunner().invoke(app, ["update", "--path", str(root), "--dry-run"])
    assert dry.exit_code == 0 and latest.id in dry.output  # there is work to do
    assert _snapshot(root) == before  # ... and a dry run did none of it (nothing added, removed or changed)

    applied = CliRunner().invoke(app, ["update", "--path", str(root), "--yes"])
    assert applied.exit_code == 0, applied.output
    after = _snapshot(root)
    changed = {name for name in before.keys() | after.keys() if after.get(name) != before.get(name)}  # deletions too
    assert "AGENTS.md" in changed and changed <= {"AGENTS.md", ".swerepo.toml"}, changed
    agents = (root / "AGENTS.md").read_text()
    block = find_block(agents, style=HTML)
    assert block is not None and block.content == new  # the update itself came in
    assert _outside(agents) == outside  # the text around the block, the person's line after it included
    assert all((root / name).read_bytes() == text for name, text in mine.items())  # the person's files

    again = CliRunner().invoke(app, ["update", "--path", str(root), "--yes"])
    assert again.exit_code == 0 and "Nothing to do." in again.output
    assert _snapshot(root) == after
