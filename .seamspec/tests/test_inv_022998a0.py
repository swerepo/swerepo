"""Rule: `swerepo check` stays read-only with SeamSpec set up, and with `--ci` runs no SeamSpec command
(ADR-20261124-cd64 point 9). A fake `seamspec`, first on PATH, logs every call and changes nothing."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from swerepo import seamspec_component
from swerepo.cli import app
from swerepo.state import State

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t",
       "-c", "user.email=t@example.com"]  # fmt: skip
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
FAKE = """#!{python}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_SEAMSPEC_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if args == ["--version"]:
    print("seamspec 0.1.2")
elif args[:2] == ["doctor", "--json"]:
    print(json.dumps({{"ok": True, "findings": []}}))
"""
READ_ONLY = (["--version"], ["doctor", "--json"], ["spec", "--check", "docs/EARNED_SPEC.md"])
RULES = {
    "inv_11111111": {"status": "LOCKED", "title": "my privacy rule", "origin": {"ref": None}},
    "inv_33333333": {"status": "LOCKED", "title": "adr", "origin": {"ref": "swerepo:hygiene/adr-index@1"}},
    "inv_22222222": {"status": "PROPOSED", "title": "b", "origin": {"ref": "swerepo:hygiene/changelog@1"}},
}
REPORTED = [
    "hygiene/privacy: adopted (inv_11111111)",
    "hygiene/adr-index: locked (inv_33333333)",
    "hygiene/changelog: proposed (inv_22222222)",
    "hygiene/ci-tests: not proposed yet",
]


def _snapshot(root: Path) -> dict[str, tuple[int, int, bytes]]:
    """Every file's modification time, size and bytes, and every folder's modification time, `.git` included."""
    paths = sorted(root.rglob("*"))
    files = {p.relative_to(root).as_posix(): (p.stat().st_mtime_ns, p.stat().st_size, p.read_bytes())
             for p in paths if p.is_file()}  # fmt: skip
    folders = {p.relative_to(root).as_posix() + "/": (p.stat().st_mtime_ns, 0, b"") for p in [root, *paths]
               if p.is_dir()}  # fmt: skip
    return files | folders


def _calls(log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_check_reads_only_and_ci_runs_no_seamspec(tmp_path: Path, monkeypatch):
    bin_dir, log = tmp_path / "bin", tmp_path / "calls.jsonl"
    bin_dir.mkdir()
    script = bin_dir / "seamspec"
    script.write_text(FAKE.format(python=sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_SEAMSPEC_LOG", str(log))
    monkeypatch.setattr(seamspec_component, "command", lambda: str(script))
    root = tmp_path / "app"
    root.mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / "uv.lock").write_text("version = 1\n")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    assert CliRunner().invoke(app, ["init", "--path", str(root), "--yes", "--code-owner", "@dev"]).exit_code == 0
    (root / ".seamspec" / "invariants").mkdir(parents=True)
    (root / ".seamspec" / "config.toml").write_text('mode = "enforced"\n')
    for rule_id, data in RULES.items():
        (root / ".seamspec" / "invariants" / f"{rule_id}.json").write_text(json.dumps({"id": rule_id, **data}))
    (root / "docs" / "EARNED_SPEC.md").write_text("# Earned spec\n")
    state = State.load(root)
    state.set_components([*state.components, "seamspec"])
    state.set_seamspec_adopted("privacy", "inv_11111111")
    state.save(root)
    subprocess.run([*GIT, "-C", str(root), "add", "-A"], check=True)
    subprocess.run([*GIT, "-C", str(root), "commit", "-q", "-m", "set up"], check=True)
    before, earlier = _snapshot(root), len(_calls(log))  # init may read SeamSpec's version: only check's calls count

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    in_ci = CliRunner().invoke(app, ["check", "--path", str(root), "--ci"])
    assert in_ci.exit_code in (0, 1), in_ci.output
    assert _calls(log)[earlier:] == []  # --ci: no SeamSpec command at all
    assert _snapshot(root) == before
    monkeypatch.delenv("GITHUB_ACTIONS")

    local = CliRunner().invoke(app, ["check", "--path", str(root)])
    assert local.exit_code in (0, 1), local.output
    for line in REPORTED:
        assert line in local.output, line
    calls = _calls(log)[earlier:]
    assert calls and all(args in READ_ONLY for args in calls), calls  # whole argument lists
    assert ["spec", "--check", "docs/EARNED_SPEC.md"] in calls  # the earned spec was checked, read-only
    assert _snapshot(root) == before
