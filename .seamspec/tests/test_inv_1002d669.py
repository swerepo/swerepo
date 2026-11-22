"""Rule: `swerepo init --dry-run` writes nothing, and a second `swerepo init` on a repository it set up
writes nothing and says "Nothing to do" (SWEREPO-SPEC §5 principles 1 and 6; ADR-20261121-6c3d)."""

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from swerepo.cli import app

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]


def _snapshot(root: Path) -> dict[str, tuple[int, int, bytes | None]]:
    return {
        p.relative_to(root).as_posix(): (
            p.stat().st_mtime_ns,
            p.stat().st_size,
            p.read_bytes() if p.is_file() else None,
        )
        for p in root.rglob("*")
    }


def test_dry_run_then_a_second_run_write_nothing(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    (tmp_path / "CLAUDE.md").write_text("Ours.\n")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(tmp_path)], check=True)
    runner = CliRunner()

    before = _snapshot(tmp_path)
    dry = runner.invoke(app, ["init", "--path", str(tmp_path), "--dry-run"])
    assert dry.exit_code == 0 and "create" in dry.output  # the plan had work to do
    assert _snapshot(tmp_path) == before

    first = runner.invoke(app, ["init", "--path", str(tmp_path), "--yes"])
    assert first.exit_code == 0 and "Applied:" in first.output
    after_first = _snapshot(tmp_path)
    assert after_first != before

    second = runner.invoke(app, ["init", "--path", str(tmp_path), "--yes"])
    assert second.exit_code == 0 and "Nothing to do." in second.output
    assert _snapshot(tmp_path) == after_first
