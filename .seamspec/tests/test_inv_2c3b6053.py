"""Rule: swerepo-ci.yml tests exactly the Python versions each project declares (ADR-20261122-4a06 point 7;
SWEREPO-SPEC §6.2). Read from the text, without a YAML library."""

import re
import subprocess
from pathlib import Path

import pytest

from swerepo.init import apply, make_plan

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]
WORKFLOW = ".github/workflows/swerepo-ci.yml"


def _blocks(text: str) -> dict[str, str]:
    """Each job's lines, by job name."""
    jobs = text.split("\njobs:\n", 1)[1]
    found: dict[str, str] = {}
    for part in re.split(r"(?m)^(?=  [A-Za-z_][\w-]*:\s*$)", jobs):
        name = re.match(r"^  ([A-Za-z_][\w-]*):", part)
        if name:
            found[name[1]] = part
    return found


def _matrix(block: str) -> list[str]:
    match = re.search(r"^        python: \[([^\]]*)\]$", block, re.MULTILINE)
    assert match, block
    return [v.strip().strip('"') for v in match[1].split(",")]


@pytest.mark.parametrize(
    ("declared", "versions"),
    [
        ('requires-python = ">=3.12"\n', ["3.12", "3.13", "3.14"]),
        ('requires-python = ">=3.11,<3.14"\n', ["3.11", "3.12", "3.13"]),
        ("", ["3.11", "3.12", "3.13", "3.14"]),
    ],
)
def test_each_test_job_runs_its_projects_versions(tmp_path: Path, declared: str, versions: list[str]):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n' + declared)
    (tmp_path / "services/api").mkdir(parents=True)
    (tmp_path / "services/api/pyproject.toml").write_text('[project]\nname = "api"\nrequires-python = ">=3.13"\n')
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(tmp_path)], check=True)
    apply(make_plan(tmp_path, only=["ci"], hosts=[], projects=["services/api"]), tmp_path)
    blocks = _blocks((tmp_path / WORKFLOW).read_text())
    assert _matrix(blocks["test"]) == versions
    assert "python-version: ${{ matrix.python }}" in blocks["test"] and "- run: uv run pytest" in blocks["test"]
    assert _matrix(blocks["test-services-api"]) == ["3.13", "3.14"]
    assert "- run: uv run pytest" in blocks["test-services-api"]
    assert f'python-version: "{versions[-1]}"' in blocks["test-macos"]
