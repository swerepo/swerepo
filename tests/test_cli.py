import os
import subprocess
import sys
from importlib.metadata import version

from click import unstyle
from typer.testing import CliRunner

from swerepo import __version__
from swerepo.cli import app

runner = CliRunner()


def plain(text: str) -> str:
    """Help text without terminal styling. Typer forces Rich's terminal output (colours, bold) when
    GITHUB_ACTIONS, FORCE_COLOR or PY_COLORS is set, so tests compare what a person reads, not bytes."""
    return unstyle(text)


def test_version_matches_installed_metadata():
    assert __version__ == version("swerepo")


def test_version_flag_prints_name_and_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"swerepo {__version__}"


def test_help_describes_the_tool():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--version" in plain(result.stdout)
    assert "AI-assisted team" in plain(result.stdout)


def test_help_reads_the_same_when_ci_forces_terminal_styling():
    # Found on the first CI run (PR #1): on GitHub Actions the help is styled, which split "--version".
    env = {**os.environ, "GITHUB_ACTIONS": "true"}
    completed = subprocess.run(
        [sys.executable, "-m", "swerepo", "--help"], capture_output=True, text=True, env=env, check=False
    )
    assert completed.returncode == 0
    assert "\x1b[" in completed.stdout  # the styling really is on, or this test proves nothing
    assert "--version" in plain(completed.stdout)
    assert "AI-assisted team" in plain(completed.stdout)


def test_unknown_option_is_a_usage_error():
    # Exit code 2 means wrong usage (SWEREPO-SPEC §7).
    result = runner.invoke(app, ["--no-such-option"])
    assert result.exit_code == 2


def test_no_arguments_shows_help_as_a_usage_error():
    # Without a command there is nothing to do: show help, exit 2 (wrong usage), like any unknown command.
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Usage" in plain(result.output)


def test_runs_as_a_module():
    # `python -m swerepo` must behave like the `swerepo` script.
    completed = subprocess.run(
        [sys.executable, "-m", "swerepo", "--version"], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == f"swerepo {__version__}"
