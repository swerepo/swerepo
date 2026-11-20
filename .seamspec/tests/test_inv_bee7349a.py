"""Locked rule: detection never writes to the repository it looks at: not in a committed git repository
whose index is out of date (where a refreshing git command would rewrite it), and not when it walks a
folder that isn't a repository; while it reads workflows, pre-commit, setup.cfg and tox.ini
(ADR-20261120-25b5; SWEREPO-SPEC §15: `check` is read-only)."""

import os
import subprocess
from pathlib import Path

import pytest

from swerepo.detect import detect

FILES = {
    "pyproject.toml": '[project]\nname = "x"\nrequires-python = ">=3.11"\n',
    "services/api/pyproject.toml": "[project]\nname = 'api'\n",
    ".github/workflows/ci.yml": "jobs:\n  t:\n    steps:\n      - run: pytest\n",
    ".pre-commit-config.yaml": "repos:\n  - hooks:\n      - id: ruff\n",
    "setup.cfg": "[flake8]\nmax-line-length = 100\n",
    "tox.ini": "[pytest]\n",
    "docs/adr/0001-x.md": "# x\n",
}
GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    return {p.relative_to(root).as_posix(): (p.stat().st_mtime_ns, p.stat().st_size) for p in root.rglob("*")}


@pytest.mark.parametrize("with_git", [True, False])
def test_detection_writes_nothing(tmp_path: Path, with_git: bool):
    for name, text in FILES.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    if with_git:
        subprocess.run([*GIT, "init", "-q", str(tmp_path)], check=True)
        subprocess.run([*GIT, "-C", str(tmp_path), "add", "-A"], check=True)
        subprocess.run([*GIT, "-c", "user.email=t@example.com", "-C", str(tmp_path), "commit", "-qm", "x"], check=True)
        subprocess.run([*GIT, "init", "-q", str(tmp_path / "vendor" / "lib")], check=True)  # a nested repository
        stamp = (tmp_path / "setup.cfg").stat().st_mtime_ns + 10**9
        os.utime(tmp_path / "setup.cfg", ns=(stamp, stamp))  # the index is now out of date for this file
    before = _snapshot(tmp_path)
    found = detect(tmp_path)
    assert _snapshot(tmp_path) == before
    assert found.git.listed_by == ("git" if with_git else "walk")
    # The readers this rule speaks of really ran.
    assert [w.path for w in found.workflows] == [".github/workflows/ci.yml"]
    assert {linter.name for linter in found.linters} == {"flake8", "ruff"}
    assert found.pytest_configured
