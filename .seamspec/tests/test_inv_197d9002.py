"""Rule (ADR-20261125-5f22): a codebase never linted isn't red on day one. In a repository with history and no linter
of its own, `swerepo init` writes a `lint` job that checks only the Python files each change touches; a new project
(no commits when SWERepo first ran, also when it is set up in stages) gets ruff on every file; and a recorded choice is
never changed by a later `init` or `update`. The root project only: what `--projects` folders get is left to v0.2's
monorepo work. Structure is checked (the recorded choice, the job's commands), never the plan's wording."""

import subprocess
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from swerepo.cli import app

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t",
       "-c", "user.email=t@example.com"]  # fmt: skip
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
WORKFLOW = ".github/workflows/swerepo-ci.yml"
EVERY_FILE = "- run: uv run ruff check ."  # the full lint job
CHANGED_ONLY = "uv run ruff check --force-exclude"  # the gradual job: the files a change touches


def _project(root: Path) -> Path:
    (root / "app").mkdir(parents=True)
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / "uv.lock").write_text("version = 1\n")
    (root / "app" / "core.py").write_text("import os\n")  # unused import: a codebase ruff has never seen
    (root / "tests").mkdir()
    (root / "tests" / "test_core.py").write_text("def test_core():\n    assert True\n")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    return root


def _commit(root: Path) -> None:
    subprocess.run([*GIT, "-C", str(root), "add", "-A"], check=True)
    subprocess.run([*GIT, "-C", str(root), "commit", "-qm", "work"], check=True)


def _swerepo(*args: str) -> str:
    done = CliRunner().invoke(app, list(args))
    assert done.exit_code == 0, done.output
    return done.output


def _lint(root: Path) -> tuple[str, str]:
    """The recorded lint choice and the lint job as written."""
    values = tomllib.loads((root / ".swerepo.toml").read_text())["values"]
    return values["lint"], (root / WORKFLOW).read_text()


def test_an_existing_codebase_is_linted_file_by_file(tmp_path: Path):
    root = _project(tmp_path / "old")
    _commit(root)  # history: an existing codebase
    _swerepo("init", "--path", str(root), "--only", "ci", "--yes")
    lint, workflow = _lint(root)
    assert lint == "gradual" and CHANGED_ONLY in workflow and EVERY_FILE not in workflow


def test_a_new_project_is_linted_whole(tmp_path: Path):
    root = _project(tmp_path / "plain")  # no commits, one run: SWERepo asks git, as nothing is recorded yet
    _swerepo("init", "--path", str(root), "--only", "ci", "--yes")
    lint, workflow = _lint(root)
    assert lint == "ruff" and EVERY_FILE in workflow and CHANGED_ONLY not in workflow


def test_a_new_project_is_linted_whole_also_when_set_up_in_stages(tmp_path: Path):
    root = _project(tmp_path / "new")  # no commits yet
    _swerepo("init", "--path", str(root), "--only", "docs,agents", "--yes")
    _commit(root)  # the first stage, committed: still a new project
    _swerepo("init", "--path", str(root), "--only", "ci", "--yes")
    lint, workflow = _lint(root)
    assert lint == "ruff" and EVERY_FILE in workflow and CHANGED_ONLY not in workflow


def _record(root: Path, lint: str) -> None:
    """The person's choice in `.swerepo.toml`, `[values] lint`, as the plan tells them to switch."""
    text = (root / ".swerepo.toml").read_text()
    current = tomllib.loads(text)["values"]["lint"]
    (root / ".swerepo.toml").write_text(text.replace(f'lint = "{current}"', f'lint = "{lint}"', 1))
    assert tomllib.loads((root / ".swerepo.toml").read_text())["values"]["lint"] == lint


def _again(root: Path) -> None:
    _swerepo("init", "--path", str(root), "--only", "ci", "--yes")
    _swerepo("update", "--path", str(root), "--only", "ci", "--yes")


def test_a_recorded_choice_is_never_changed(tmp_path: Path):
    root = _project(tmp_path / "kept")
    _commit(root)
    _swerepo("init", "--path", str(root), "--only", "ci", "--yes")
    _commit(root)
    before = (root / WORKFLOW).read_text()
    _again(root)
    assert _lint(root) == ("gradual", before)


def test_a_recorded_choice_wins_over_what_would_be_chosen(tmp_path: Path):
    """Each choice recorded where SWERepo would choose the other: kept by `init` and `update`, in either direction."""
    old = _project(tmp_path / "switched")  # an existing codebase, switched to full ruff as the plan explains
    _commit(old)
    _swerepo("init", "--path", str(old), "--only", "ci", "--yes")
    _record(old, "ruff")
    _swerepo("update", "--path", str(old), "--only", "ci", "--yes")  # the switch: the workflow follows the record
    _commit(old)
    switched = (old / WORKFLOW).read_text()
    assert EVERY_FILE in switched
    _again(old)
    assert _lint(old) == ("ruff", switched)
    new = _project(tmp_path / "chosen")  # a new project whose person chose gradual
    _swerepo("init", "--path", str(new), "--only", "ci", "--yes")
    _record(new, "gradual")
    _swerepo("update", "--path", str(new), "--only", "ci", "--yes")
    _commit(new)
    chosen = (new / WORKFLOW).read_text()
    assert CHANGED_ONLY in chosen
    _again(new)
    assert _lint(new) == ("gradual", chosen)
