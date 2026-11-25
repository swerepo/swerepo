"""Rule: SWERepo never answers SeamSpec's consent, and runs `seamspec init` only in a terminal (ADR-20261124-cd64
point 1). A fake `seamspec`, first on PATH, logs every call. The command line sees a terminal throughout, so `--yes`,
`--dry-run` and `--json` are what keep `seamspec init` from running."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from swerepo import cli, seamspec_component
from swerepo.cli import app
from swerepo.state import State

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t",
       "-c", "user.email=t@example.com"]  # fmt: skip
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
OTHERS = ["docs", "agents", "ci", "security", "github"]
WRITTEN = ["AGENTS.md", "CHANGELOG.md", "docs/adr/README.md", ".github/workflows/swerepo-ci.yml",
           ".github/dependabot.yml", ".swerepo.toml"]  # fmt: skip
FAKE = """#!{python}
import hashlib, json, os, sys
from pathlib import Path
args = sys.argv[1:]
body = sys.stdin.read() if args[:1] == ["propose"] else ""
with open(os.environ["FAKE_SEAMSPEC_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
root = Path.cwd()
if args == ["--version"]:
    print("seamspec " + os.environ["FAKE_SEAMSPEC_VERSION"])
elif args[:1] == ["init"]:
    (root / ".seamspec").mkdir(exist_ok=True)
    config = root / ".seamspec" / "config.toml"
    if not config.exists():
        config.write_text('mode = "enforced"\\n')
elif args[:1] == ["propose"]:
    print(json.dumps({{"id": "inv_" + hashlib.sha256(body.encode()).hexdigest()[:8]}}))
elif args[:2] == ["spec", "--out"]:
    (root / args[2]).parent.mkdir(parents=True, exist_ok=True)
    (root / args[2]).write_text("# Earned spec\\n")
elif args[:2] == ["doctor", "--json"]:
    print(json.dumps({{"ok": True, "findings": []}}))
"""


def _calls(log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def _count(log: Path, word: str) -> int:
    return len([args for args in _calls(log) if args[:1] == [word]])


def _run(*args: str, answers: str | None = None):
    done = CliRunner().invoke(app, list(args), input=answers)
    assert done.exit_code == 0, done.output
    return done


def test_seamspec_init_runs_only_in_a_terminal_and_never_with_consent_given(tmp_path: Path, monkeypatch):
    bin_dir, log = tmp_path / "bin", tmp_path / "calls.jsonl"
    bin_dir.mkdir()
    script = bin_dir / "seamspec"
    script.write_text(FAKE.format(python=sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_SEAMSPEC_LOG", str(log))
    monkeypatch.setenv("FAKE_SEAMSPEC_VERSION", "0.1.2")
    monkeypatch.setattr(seamspec_component, "command", lambda: str(script))
    monkeypatch.setattr(cli, "_interactive", lambda: True)  # a person at a terminal, all the way
    root = tmp_path / "app"
    root.mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / "uv.lock").write_text("version = 1\n")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)

    done = _run("init", "--path", str(root), "--yes", "--code-owner", "@dev")
    assert "run it in a terminal: seamspec init" in done.output
    assert State.load(root).components == OTHERS  # everything else applied; seamspec waits
    assert all((root / path).is_file() for path in WRITTEN)
    _run("init", "--path", str(root), "--dry-run")
    _run("init", "--path", str(root), "--json")
    assert _count(log, "init") == 0 and _count(log, "review") == 0
    assert not (root / ".seamspec" / "config.toml").exists()

    _run("init", "--path", str(root), "--only", "seamspec", answers="y\nn\n")  # Apply? yes; review now? no
    assert _count(log, "init") == 1 and _count(log, "propose") > 0 and _count(log, "review") == 0
    assert (root / ".seamspec" / "config.toml").is_file()

    monkeypatch.setenv("FAKE_SEAMSPEC_VERSION", "0.2.0")  # a newer SeamSpec installed
    _run("update", "--path", str(root), "--yes", "--only", "seamspec")
    assert _count(log, "init") == 1
    _run("update", "--path", str(root), "--only", "seamspec", answers="y\nn\n")
    assert _count(log, "init") == 2

    other = tmp_path / "other"  # the same, answering yes to the review
    other.mkdir()
    (other / "pyproject.toml").write_text(PYPROJECT)
    (other / "uv.lock").write_text("version = 1\n")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(other)], check=True)
    monkeypatch.setenv("FAKE_SEAMSPEC_VERSION", "0.1.2")
    _run("init", "--path", str(other), "--yes", "--code-owner", "@dev")
    _run("init", "--path", str(other), "--only", "seamspec", answers="y\ny\n")
    assert _count(log, "review") == 1
    assert not [arg for args in _calls(log) for arg in args if arg.startswith("--accept-auto-run")]
