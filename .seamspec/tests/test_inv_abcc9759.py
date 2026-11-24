"""Rule: in what `swerepo init` writes for the github component, Dependabot's version updates wait until a new
version is a week old, and SWERepo's merge settings turn auto-merge off (ADR-20261123-cc8d, ADR-20261123-4e40;
SWEREPO-SPEC §6.1). The files are read as text, without YAML; GitHub is never reached (no remote)."""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from swerepo.cli import app

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]


def _init(root: Path, lockfile: bool, mode: str) -> None:
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "app"\nrequires-python = ">=3.12"\n')
    if lockfile:
        (root / "uv.lock").write_text("version = 1\n")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    command = ["init", "--path", str(root), "--only", "github", "--mode", mode, "--code-owner", "@dev", "--yes"]
    result = CliRunner().invoke(app, command)
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize(("lockfile", "python"), [(True, "uv"), (False, "pip")])
@pytest.mark.parametrize("mode", ["solo", "team"])
def test_dependabot_waits_a_week_and_auto_merge_is_off(tmp_path: Path, lockfile: bool, python: str, mode: str):
    root = tmp_path / "app"
    _init(root, lockfile, mode)
    text = (root / ".github/dependabot.yml").read_text()
    body = text.split("\nupdates:\n", 1)[1]
    entries = body.split("  - package-ecosystem: ")
    assert entries[0] == "", "nothing but updates entries under updates:"
    entries = entries[1:]
    assert [e.split("\n", 1)[0] for e in entries] == ["github-actions", python]
    for entry in entries:
        lines = entry.splitlines()[1:]
        # everything after the ecosystem belongs to the entry: no other section hides after the last one
        assert all(line.startswith("    ") for line in lines), entry
        # one cooldown, and in it only the 7 days: no shorter wait for some updates, no exclusions
        assert [line for line in lines if line.startswith("    cooldown:")] == ["    cooldown:"], entry
        start = lines.index("    cooldown:") + 1
        end = next((i for i in range(start, len(lines)) if not lines[i].startswith("      ")), len(lines))
        assert lines[start:end] == ["      default-days: 7"], entry
    settings = json.loads((root / ".github/swerepo/repo-settings.json").read_text())
    assert settings["allow_auto_merge"] is False
