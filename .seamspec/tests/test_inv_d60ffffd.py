"""Rule: `swerepo update` never moves an action pin backwards, and never guesses between two commits for one version
(ADR-20261123-f571). A workflow whose pins Dependabot moved forward, and that differs from SWERepo's earlier render in
nothing else, is updated by `update --yes` alone: the rest of the template's change comes in, and every action stays
pinned at a version at least as new as before. When the new render moves the same pin to a version older than
Dependabot's, or adds a pin line at an older version, the merge keeps Dependabot's. A version pinned to two commits,
on one line against the earlier render, across two lines of the person's file, or on a line the new render adds,
is never guessed. A fixture repository set up by `swerepo init`; its workflow is put back to an earlier render (an
older SeamSpec pin), as an older SWERepo wrote it, and one action's pin lines are then changed."""

import re
import subprocess
from pathlib import Path

from packaging.version import Version
from typer.testing import CliRunner

from swerepo.blocks import file_fingerprint
from swerepo.cli import app
from swerepo.merge import merge3
from swerepo.rebuild import rebuild
from swerepo.render import TemplateStore
from swerepo.state import Record, State

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t",
       "-c", "user.email=t@example.com"]  # fmt: skip
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
WORKFLOW = ".github/workflows/swerepo-ci.yml"
PIN = re.compile(r"uses: ([^@\s]+)@([0-9a-f]{40})\s+#\s*v(\S+)")
DEPENDABOTS = ("f" * 40, "99.0.0")
OLDER_SEAMSPEC = "0.1.1"


def _pins(text: str) -> dict[str, list[tuple[str, Version]]]:
    """Each action's pins, as (commit, version), in file order."""
    found: dict[str, list[tuple[str, Version]]] = {}
    for action, commit, version in PIN.findall(text):
        found.setdefault(action, []).append((commit, Version(version)))
    return found


def _repinned(line: str, commit: str, version: str) -> str:
    return line.split("@")[0] + "@" + commit + "  # v" + version


def _two_commits(line: str, n: int) -> str:
    """Dependabot's version on every line, but the first line on one commit and the rest on another."""
    return _repinned(line, ("f" if n == 0 else "e") * 40, "99.0.0")


def _older_workflow(tmp_path: Path, change) -> tuple[Path, str, str, str]:
    """A repository whose workflow an older render wrote, the n-th `actions/checkout` line changed by
    `change(line, n)`. Returns the root, the earlier render, the new one, and the SeamSpec version the new one pins
    (from the record's own inputs)."""
    root = tmp_path / "app"
    root.mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / "uv.lock").write_text("version = 1\n")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    assert CliRunner().invoke(app, ["init", "--path", str(root), "--yes", "--only", "ci"]).exit_code == 0
    state = State.load(root)
    record = state.files()[WORKFLOW]
    seamspec = (record.inputs or {})["seamspec"]
    assert seamspec != OLDER_SEAMSPEC
    new = rebuild(TemplateStore(), record.template, record.inputs or {})
    older_inputs = {**(record.inputs or {}), "seamspec": OLDER_SEAMSPEC}
    older = rebuild(TemplateStore(), record.template, older_inputs)
    assert new is not None and older is not None and f"seamspec=={OLDER_SEAMSPEC}" in older
    assert f"seamspec=={seamspec}" not in older
    lines, n = [], 0
    for line in older.split("\n"):
        if "actions/checkout@" in line:
            line, n = change(line, n), n + 1
        lines.append(line)
    assert n >= 2, "the workflow pins actions/checkout on several lines"
    (root / WORKFLOW).write_text("\n".join(lines))
    mark = file_fingerprint(older, record.template)
    state.set_file(WORKFLOW, Record(record.template, mark, mark, older_inputs))
    state.save(root)
    return root, older, new, seamspec


def _update(root: Path, *flags: str):
    done = CliRunner().invoke(app, ["update", "--path", str(root), *flags])
    assert done.exit_code == 0, done.output
    return done


def _dependabots(older: str) -> str:
    return "\n".join(_repinned(x, *DEPENDABOTS) if "actions/checkout@" in x else x for x in older.split("\n"))


def test_update_keeps_dependabots_newer_pins_and_brings_the_rest(tmp_path: Path):
    root, _, _, seamspec = _older_workflow(tmp_path, lambda line, n: _repinned(line, *DEPENDABOTS))
    before = _pins((root / WORKFLOW).read_text())

    _update(root, "--yes")  # no --merge: pins only were changed
    after_text = (root / WORKFLOW).read_text()
    assert f"seamspec=={OLDER_SEAMSPEC}" not in after_text  # the template's change came in:
    assert f"seamspec=={seamspec}" in after_text  # the current pin, as recorded
    after = _pins(after_text)
    expected = ("f" * 40, Version("99.0.0"))
    assert len(after["actions/checkout"]) == len(before["actions/checkout"])
    assert all(found == expected for found in after["actions/checkout"]), after["actions/checkout"]
    for action, pins in before.items():  # no pin of any action is older than its newest before
        newest = max(version for _, version in pins)
        assert min(version for _, version in after[action]) >= newest, action


def test_a_template_moving_the_same_pin_never_lowers_dependabots(tmp_path: Path):
    """The new render moves checkout to v98 (newer than the earlier render, older than Dependabot's v99) and adds a
    checkout line at the earlier version: the merge keeps Dependabot's commit and v99 everywhere."""
    _, older, new, seamspec = _older_workflow(tmp_path, lambda line, n: line)
    earlier_line = next(line for line in older.split("\n") if "actions/checkout@" in line)
    theirs = "\n".join(_repinned(x, "a" * 40, "98.0.0") if "actions/checkout@" in x else x for x in new.split("\n"))
    theirs = theirs.rstrip("\n") + "\n" + earlier_line + "\n"  # a pin line the new render adds, at the older version
    result = merge3(older, _dependabots(older), theirs)
    assert result.text is not None, "a pin the template moved must not conflict with Dependabot's"
    checkout = _pins(result.text)["actions/checkout"]
    assert len(checkout) == len(_pins(theirs)["actions/checkout"])  # the added line is there too
    assert all(found == ("f" * 40, Version("99.0.0")) for found in checkout), checkout
    assert f"seamspec=={OLDER_SEAMSPEC}" not in result.text and f"seamspec=={seamspec}" in result.text


def test_an_added_line_on_another_commit_for_dependabots_version_is_never_guessed(tmp_path: Path):
    """The new render adds a checkout line at Dependabot's version but another commit: a conflict, no text."""
    _, older, new, _ = _older_workflow(tmp_path, lambda line, n: line)
    added = _repinned(next(line for line in new.split("\n") if "actions/checkout@" in line), "b" * 40, "99.0.0")
    theirs = new.rstrip("\n") + "\n" + added + "\n"
    result = merge3(older, _dependabots(older), theirs)
    assert result.text is None and result.conflicts


def test_one_version_on_another_commit_is_never_guessed(tmp_path: Path):
    def same_version_other_commit(line: str, n: int) -> str:
        head, tail = line.split("@", 1)
        commit, rest = tail[:40], tail[40:]
        other = "e" * 40 if commit != "e" * 40 else "d" * 40
        return f"{head}@{other}{rest}"  # the same `# v…` comment

    root, _, _, _ = _older_workflow(tmp_path, same_version_other_commit)
    before = (root / WORKFLOW).read_bytes()
    done = _update(root, "--yes", "--merge")
    assert "conflict" in done.output and (root / WORKFLOW).read_bytes() == before


def test_one_newer_version_on_two_commits_across_lines_is_never_guessed(tmp_path: Path):
    """Two lines of the person's file pin v99 to two different commits; the new render adds no pin line."""
    root, _, _, _ = _older_workflow(tmp_path, _two_commits)
    before = (root / WORKFLOW).read_bytes()
    _update(root, "--yes")
    assert (root / WORKFLOW).read_bytes() == before  # not Dependabot's alone: never merged without --merge
    done = _update(root, "--yes", "--merge")
    assert "conflict" in done.output and (root / WORKFLOW).read_bytes() == before
