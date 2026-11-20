"""The `swerepo` command line.

Commands arrive phase by phase (docs/PROGRESS.md); Phase 0 has only `--version` and `--help`.
"""

from __future__ import annotations

import typer

from swerepo import __version__

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


def main() -> None:
    app()
