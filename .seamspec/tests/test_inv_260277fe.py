"""Rule (ADR-20261125-5f22): missing tests never fail `check --ci`. In a repository whose `swerepo-ci.yml` SWERepo
wrote, a project with no file named `test_*.py` or `*_test.py` outside the folders pytest skips by default (dot-folders
such as `.seamspec/`, `build`, `dist`, `venv` …) and under its `testpaths` when it sets them, is reported as `ci.tests`,
missing and not blocking: `check --ci` still exits 0, and run in GitHub Actions prints warnings, never an error. Once a
test exists, `ci.tests` isn't reported. Structure is checked, never the wording."""

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from swerepo.cli import app

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t",
       "-c", "user.email=t@example.com"]  # fmt: skip
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'


def _check(root: Path, *args: str):
    return CliRunner().invoke(app, ["check", "--path", str(root), "--only", "ci", *args])


def test_no_tests_is_a_warning_never_a_failure(tmp_path: Path, monkeypatch):
    root = tmp_path / "app"
    (root / "app").mkdir(parents=True)
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / "uv.lock").write_text("version = 1\n")
    (root / "app" / "core.py").write_text("VALUE = 1\n")
    (root / ".seamspec" / "tests").mkdir(parents=True)  # tests pytest never collects don't count
    (root / ".seamspec" / "tests" / "test_inv_x.py").write_text("def test_x():\n    assert True\n")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    plan = CliRunner().invoke(app, ["init", "--path", str(root), "--only", "ci", "--yes"])
    assert plan.exit_code == 0, plan.output
    findings = json.loads(_check(root, "--json").output)["findings"]
    tests = [f for f in findings if f["item"] == "ci.tests"]
    assert len(tests) == 1 and tests[0]["status"] == "missing" and tests[0]["blocking"] is False
    missing = [f for f in findings if f["status"] == "missing"]
    assert not [f for f in missing if f["blocking"]]  # nothing here blocks: ci.tests least of all

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)  # anywhere: on a person's machine, or another CI
    plain = _check(root, "--ci")
    assert plain.exit_code == 0 and "::" not in plain.output, plain.output
    monkeypatch.setenv("GITHUB_ACTIONS", "true")  # in GitHub Actions, where check prints annotations
    ci = _check(root, "--ci")
    assert ci.exit_code == 0, ci.output  # never a failure
    lines = ci.output.splitlines()
    warnings = [line for line in lines if line.startswith("::warning ")]
    assert len(warnings) == len(missing), ci.output  # one warning per non-blocking gap, ci.tests among them
    assert not [line for line in lines if line.startswith("::error ")], ci.output  # never an error

    (root / "tests").mkdir()
    (root / "tests" / "test_core.py").write_text("def test_core():\n    assert True\n")
    after = json.loads(_check(root, "--json").output)["findings"]
    assert not [f for f in after if f["item"] == "ci.tests"]
