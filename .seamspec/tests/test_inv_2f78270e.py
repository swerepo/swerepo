"""Rule: `swerepo update --only seamspec` moves the SeamSpec pin forward only, and every workflow pinning SeamSpec and
`[tools] seamspec` always name one version (ADR-20261124-cd64 point 8; review P7-F01). A fake `seamspec`, first on
PATH, reports the installed version, so the machine's own SeamSpec never decides the outcome."""

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from swerepo import seamspec_component
from swerepo.cli import app
from swerepo.state import State

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t",
       "-c", "user.email=t@example.com"]  # fmt: skip
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
WORKFLOW = ".github/workflows/swerepo-ci.yml"
SEAMSPEC_WORKFLOW = ".github/workflows/seamspec.yml"
FILES = (WORKFLOW, SEAMSPEC_WORKFLOW, ".swerepo.toml")
FAKE = """#!{python}
import json, os, sys
args = sys.argv[1:]
if args == ["--version"]:
    print("seamspec " + os.environ["FAKE_SEAMSPEC_VERSION"])
elif args[:2] == ["doctor", "--json"]:
    print(json.dumps({{"ok": True, "findings": []}}))
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run([*GIT, "-C", str(root), *args], check=True)


def _set_up(tmp_path: Path, monkeypatch, mode: str = "enforced") -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "seamspec"
    script.write_text(FAKE.format(python=sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(seamspec_component, "command", lambda: str(script))
    monkeypatch.setenv("FAKE_SEAMSPEC_VERSION", "0.1.2")
    root = tmp_path / "app"
    root.mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / "uv.lock").write_text("version = 1\n")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    done = CliRunner().invoke(app, ["init", "--path", str(root), "--yes", "--code-owner", "@dev"])
    assert done.exit_code == 0, done.output
    (root / ".seamspec").mkdir(exist_ok=True)
    (root / ".seamspec" / "config.toml").write_text(f'mode = "{mode}"\n')
    adopt = CliRunner().invoke(app, ["init", "--path", str(root), "--yes", "--only", "seamspec"])
    assert adopt.exit_code == 0, adopt.output
    assert "seamspec" in State.load(root).components
    assert (root / SEAMSPEC_WORKFLOW).is_file() == (mode == "strict")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "set up")
    assert _one_version(root) == "0.1.2"
    return root


def _one_version(root: Path) -> str:
    """The one SeamSpec version every workflow pinning it and `[tools] seamspec` name; each workflow must pin it."""
    versions = {State.load(root).tools["seamspec"]}
    for path in (WORKFLOW, SEAMSPEC_WORKFLOW):
        if (root / path).is_file():
            pins = set(re.findall(r"seamspec==([0-9A-Za-z.+!_-]+)", (root / path).read_text()))
            assert pins, f"{path} pins no SeamSpec"
            versions |= pins
    assert len(versions) == 1, versions
    return versions.pop()


def _bytes(root: Path) -> dict[str, bytes | None]:
    return {path: (root / path).read_bytes() if (root / path).is_file() else None for path in FILES}


def _update(root: Path, *flags: str) -> None:
    done = CliRunner().invoke(app, ["update", "--path", str(root), "--yes", "--only", "seamspec", *flags])
    assert done.exit_code == 0, done.output


def test_a_newer_seamspec_moves_the_pin_everywhere(tmp_path: Path, monkeypatch):
    root = _set_up(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_SEAMSPEC_VERSION", "0.2.0")
    _update(root)
    assert _one_version(root) == "0.2.0"


def test_strict_mode_moves_all_three_together(tmp_path: Path, monkeypatch):
    root = _set_up(tmp_path, monkeypatch, mode="strict")
    monkeypatch.setenv("FAKE_SEAMSPEC_VERSION", "0.2.0")
    _update(root)
    assert "seamspec==0.2.0" in (root / SEAMSPEC_WORKFLOW).read_text()
    assert "seamspec==0.2.0" in (root / WORKFLOW).read_text()
    assert _one_version(root) == "0.2.0"


@pytest.mark.parametrize("mode", ["enforced", "strict"])
@pytest.mark.parametrize("installed", ["0.1.1", "0.1.2", "0.3.0.dev0", "0.3.0+local"])
def test_never_backwards_and_never_a_development_or_local_build(tmp_path: Path, monkeypatch, installed, mode):
    root = _set_up(tmp_path, monkeypatch, mode=mode)
    before = _bytes(root)
    monkeypatch.setenv("FAKE_SEAMSPEC_VERSION", installed)
    _update(root)
    assert _bytes(root) == before and _one_version(root) == "0.1.2"


def test_a_conflict_moves_nothing(tmp_path: Path, monkeypatch):
    root = _set_up(tmp_path, monkeypatch)
    workflow = root / WORKFLOW
    line = next(x for x in workflow.read_text().splitlines() if "seamspec==" in x)
    workflow.write_text(workflow.read_text().replace(line, line + "  # mine"))
    before = _bytes(root)
    monkeypatch.setenv("FAKE_SEAMSPEC_VERSION", "0.2.0")
    _update(root, "--merge")
    assert _bytes(root) == before and _one_version(root) == "0.1.2"


def test_strict_a_seamspec_yml_that_cant_take_it_holds_the_pin_everywhere(tmp_path: Path, monkeypatch):
    root = _set_up(tmp_path, monkeypatch, mode="strict")
    seamspec_workflow = root / SEAMSPEC_WORKFLOW
    text = seamspec_workflow.read_text()
    assert "timeout-minutes: 15" in text
    seamspec_workflow.write_text(text.replace("timeout-minutes: 15", "timeout-minutes: 20"))  # the person's edit
    before = _bytes(root)
    monkeypatch.setenv("FAKE_SEAMSPEC_VERSION", "0.2.0")
    _update(root)  # --yes without --merge: seamspec.yml can't take the pin
    assert _bytes(root) == before and _one_version(root) == "0.1.2"
