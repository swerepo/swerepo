"""Rule: `swerepo check` never writes to the folder it checks: not the files, not git's index (even
when it is out of date), with every default component, a recorded file, the pull-request rules (`--base`)
and the command line (`--json`, `--ci` on GitHub Actions), and in a folder that isn't a git repository
(ADR-20261120-fc5a; SWEREPO-SPEC §15: read-only)."""

import json
import os
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from swerepo.check import run_check
from swerepo.cli import app
from swerepo.fingerprint import fingerprint
from swerepo.state import Record, State

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]


def _git(root: Path, *args: str) -> None:
    subprocess.run([*GIT, "-c", "user.email=t@example.com", "-C", str(root), *args], check=True, capture_output=True)


def _snapshot(root: Path) -> dict[str, tuple[int, int, bytes | None]]:
    return {
        p.relative_to(root).as_posix(): (
            p.stat().st_mtime_ns,
            p.stat().st_size,
            p.read_bytes() if p.is_file() else None,
        )
        for p in root.rglob("*")
    }


def test_check_writes_nothing(tmp_path: Path, monkeypatch):
    files = {
        "pyproject.toml": '[project]\nname = "x"\ndependencies = ["typer"]\n',
        "docs/adr/README.md": "# ADRs\n<!-- swerepo:adr-index:begin -->\n<!-- swerepo:adr-index:end -->\n",
        "docs/PROGRESS.md": "# Progress\n",
        "AGENTS.md": "<!-- swerepo:begin -->\nrules\n<!-- swerepo:end -->\n",
        ".github/workflows/ci.yml": "jobs: {}\n",
        ".github/CODEOWNERS": "# swerepo:begin\n/.github/ @o\n# swerepo:end\n",
        ".seamspec/config.toml": 'mode = "enforced"\n',
    }
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    state = State.new(version="0.0.1")
    state.set_components(["docs", "agents", "ci", "security", "github", "seamspec"])
    state.set_file("docs/PROGRESS.md", Record("docs/progress@1", fingerprint("x"), fingerprint("x")))
    state.save(tmp_path, running="0.0.1")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(tmp_path)], check=True)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "start")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\ndependencies = ["typer", "requests"]\n')
    stamp = (tmp_path / ".github/workflows/ci.yml").stat().st_mtime_ns + 10**9
    os.utime(tmp_path / ".github/workflows/ci.yml", ns=(stamp, stamp))  # the git index is now out of date
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    before = _snapshot(tmp_path)
    run_check(tmp_path)
    report = run_check(tmp_path, base="main", author="someone")
    command = ["check", "--path", str(tmp_path), "--base", "main", "--ci"]
    text = CliRunner().invoke(app, command)
    as_json = CliRunner().invoke(app, [*command, "--json"])
    assert _snapshot(tmp_path) == before

    # every part did run: one finding from each component, the recorded file, the diff, and both commands
    items = {f.item for f in report.findings}
    expected = {"docs.adr", "agents.block", "ci.workflow", "security.policy", "github.commit-email", "seamspec.mode"}
    assert expected | {"docs.file:docs/PROGRESS.md"} <= items
    assert any("requests" in f.message for f in report.findings if f.component == "pr")
    assert text.exit_code == 1 and "SWERepo · check" in text.output and "::error " in text.output  # --ci
    data = json.loads(as_json.output)
    assert as_json.exit_code == 1 and expected <= {f["item"] for f in data["findings"]}
    assert any("requests" in f["message"] for f in data["findings"] if f["component"] == "pr")


def test_check_writes_nothing_outside_git(tmp_path: Path):
    (tmp_path / "README.md").write_text("# x\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    before = _snapshot(tmp_path)
    report = run_check(tmp_path)
    result = CliRunner().invoke(app, ["check", "--path", str(tmp_path), "--json"])
    assert _snapshot(tmp_path) == before
    assert any(f.item == "docs.readme" and f.status == "ok" for f in report.findings)  # it did look
    assert result.exit_code == 1 and json.loads(result.output)["findings"]  # the command ran to its end
