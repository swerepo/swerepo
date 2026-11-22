"""The `swerepo` command line.

Commands arrive phase by phase (docs/PROGRESS.md): `check` since Phase 2.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from swerepo import __version__
from swerepo.check import UsageError, in_github_actions, one_line, run_check

app = typer.Typer(
    name="swerepo",
    help="Set up a repository the way an AI-assisted team should work, and keep it that way.",
    add_completion=False,
    no_args_is_help=True,
)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"swerepo {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", callback=_show_version, is_eager=True, help="Show the version and exit."
    ),
) -> None:
    """SWERepo. See SWEREPO-SPEC.md for what each command will do."""


@app.command()
def check(
    only: Annotated[str | None, typer.Option("--only", help="Check only these components, comma-separated.")] = None,
    base: Annotated[str | None, typer.Option("--base", help="Also check pull-request rules against this ref.")] = None,
    author: Annotated[str | None, typer.Option("--author", help="The pull request's author (bot exemptions).")] = None,
    skip: Annotated[list[str] | None, typer.Option("--skip", help="Skip a pull-request rule: progress.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON result instead of text.")] = False,
    ci: Annotated[bool, typer.Option("--ci", help="For workflows: never call GitHub; annotate on Actions.")] = False,
    path: Annotated[Path, typer.Option("--path", help="The repository to check.")] = Path("."),
) -> None:
    """Report what the repository meets, misses or has changed. Changes nothing."""
    components = [c.strip() for c in only.split(",") if c.strip()] if only is not None else None
    try:
        report = run_check(path, only=components, base=base, author=author, skip=tuple(skip or ()))
    except UsageError as error:
        typer.echo(one_line(f"swerepo check: {error}"), err=True)
        raise typer.Exit(2) from error
    if as_json:
        typer.echo(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        typer.echo(report.render_text())
    if ci and in_github_actions() and not as_json:  # --json prints one JSON value and nothing else
        for line in report.annotations():
            typer.echo(line)
    raise typer.Exit(report.exit_code)


def main() -> None:
    app()
