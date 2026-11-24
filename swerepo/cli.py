"""The `swerepo` command line.

Commands arrive phase by phase (docs/PROGRESS.md): `check` since Phase 2; `init` (docs, agents), `adr` and
`progress` since Phase 3; `init` for ci and security since Phase 4.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from swerepo import __version__, standard
from swerepo.adr import AdrError, new_adr, write_index
from swerepo.blocks import inside
from swerepo.check import UsageError, in_github_actions, one_line, run_check
from swerepo.init import (
    HOSTS,
    MODE_MEANING,
    InitError,
    apply,
    apply_github,
    has_github_remote,
    make_plan,
    noreply_warning,
)
from swerepo.progress import report
from swerepo.state import COMPONENTS, State, StateError

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


# `--docs` is `--only docs`, `--no-docs` skips docs, and so for every component (spec §7). Read from the extra
# arguments rather than declared one by one, and checked: anything else is wrong usage.
EXTRA_ARGS = {"allow_extra_args": True, "ignore_unknown_options": True}
SHORTHAND = "Shorthand: --docs is --only docs, --no-docs skips docs; likewise for every component."


def _selection(only: str | None, extra: list[str]) -> tuple[list[str] | None, list[str]]:
    """(`--only` list or None, skipped components) from `--only` and the shorthand flags."""
    chosen = [c.strip() for c in only.split(",") if c.strip()] if only is not None else None
    skip: list[str] = []
    for arg in extra:
        name = arg.removeprefix("--no-") if arg.startswith("--no-") else arg.removeprefix("--")
        if not arg.startswith("--") or name not in COMPONENTS:
            raise UsageError(f"unknown option or argument {arg!r} ({SHORTHAND.lower()})")
        if arg.startswith("--no-"):
            skip.append(name)
        else:
            chosen = [*(chosen or []), name]
    return chosen, skip


def _fail(error: Exception, code: int, prefix: str) -> typer.Exit:
    typer.echo(one_line(f"swerepo {prefix}: {error}"), err=True)
    return typer.Exit(code)


@app.command(context_settings=EXTRA_ARGS, epilog=SHORTHAND)
def check(
    ctx: typer.Context,
    only: Annotated[str | None, typer.Option("--only", help="Check only these components, comma-separated.")] = None,
    base: Annotated[str | None, typer.Option("--base", help="Also check pull-request rules against this ref.")] = None,
    author: Annotated[str | None, typer.Option("--author", help="The pull request's author (bot exemptions).")] = None,
    skip: Annotated[list[str] | None, typer.Option("--skip", help="Skip a pull-request rule: progress.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON result instead of text.")] = False,
    ci: Annotated[bool, typer.Option("--ci", help="For workflows: never call GitHub; annotate on Actions.")] = False,
    path: Annotated[Path, typer.Option("--path", help="The repository to check.")] = Path("."),
) -> None:
    """Report what the repository meets, misses or has changed. Changes nothing."""
    try:
        components, skipped = _selection(only, ctx.args)
        if components is not None and components and not [c for c in components if c not in skipped]:
            raise UsageError("nothing left to check after the --no- flags")
        result = run_check(
            path, only=components, base=base, author=author, skip=tuple(skip or ()), exclude=tuple(skipped),
            read_github=not ci,  # CI never needs GitHub access (spec §15)
        )  # fmt: skip
    except UsageError as error:
        raise _fail(error, 2, "check") from error
    if as_json:
        typer.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        typer.echo(result.render_text())
    if ci and in_github_actions() and not as_json:  # --json prints one JSON value and nothing else
        for line in result.annotations():
            typer.echo(line)
    raise typer.Exit(result.exit_code)


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _ask_hosts(detected: list[str]) -> list[str]:
    """Which editors the project uses (spec §6.6), pre-filled from what detection found."""
    answer = typer.prompt(
        f"Editors in use ({', '.join(HOSTS)}; 'none' for none)", default=", ".join(detected) or "none"
    )
    names = [h.strip().lower() for h in answer.replace(" ", ",").split(",") if h.strip()]
    return [] if names == ["none"] else names


def _ask_lint() -> str:
    """Keep the project's linters, or move to ruff gradually (spec §6.3)."""
    typer.echo(
        "Linters other than ruff were found. Keep them (CI runs them), or move to ruff gradually "
        "(ruff checks only the files each change touches)?"
    )
    answer = typer.prompt("Linters (keep, gradual)", default="keep").strip().lower()
    return "gradual" if answer.startswith("g") else "kept"


def _ask_contact(root: Path) -> str:
    """Who to report vulnerabilities to, for SECURITY.md (ADR-20261122-a48e point 1)."""
    default = "github" if has_github_remote(root) else "placeholder"
    typer.echo(
        "SECURITY.md says how to report a vulnerability privately: 'github' (GitHub's private vulnerability "
        "reporting, no address published), an email address, or 'placeholder' to decide later."
    )
    return typer.prompt("Security contact", default=default).strip()


def _ask_github(ask: dict[str, str]) -> dict[str, object]:
    """The mode and the code owner (spec §12), each only when neither given nor recorded, with the default init
    detected (`team` for an organisation's repository, the owner's login for a user's; review P5-F04)."""
    answers: dict[str, object] = {}
    if "mode" in ask:
        typer.echo("Mode for the ruleset:")
        for mode, meaning in MODE_MEANING.items():
            typer.echo(f"  {mode}: {meaning}")
        typer.echo("Nobody can approve their own pull request, so team mode needs a second person or identity.")
        answers["mode"] = typer.prompt("Mode (solo, team)", default=ask["mode"]).strip().lower()
    if "code_owner" in ask:
        prompt = "Code owner for governance files (@login or @org/team, or none)"
        answers["code_owner"] = typer.prompt(prompt, default=ask["code_owner"]).strip()
    return answers


def _apply_github(plan, path: Path, yes: bool) -> list[str]:
    """Show each GitHub change as JSON and apply what the person says yes to (all of them with --yes)."""
    labels = {"ruleset": 'Apply ruleset "swerepo" on the default branch?', "settings": "Apply merge settings?"}
    chosen = []
    for name, data in plan.github_apply.items():
        if not yes:
            typer.echo(json.dumps(data, indent=2))
            if not typer.confirm(labels[name], default=False):
                continue
        chosen.append(name)
    if not chosen:
        return ["GitHub: nothing applied (run `swerepo init --only github` again to apply)"]
    return [f"GitHub: {line}" for line in apply_github(plan, path, chosen)]


@app.command(context_settings=EXTRA_ARGS, epilog=SHORTHAND)
def init(
    ctx: typer.Context,
    only: Annotated[str | None, typer.Option("--only", help="Apply only these components, comma-separated.")] = None,
    projects: Annotated[
        str | None, typer.Option("--projects", help="Monorepo: Python project folders with CI jobs, comma-separated.")
    ] = None,
    with_governance: Annotated[
        bool, typer.Option("--with-governance", help="Add the governance CI job even from an unreleased SWERepo.")
    ] = False,
    mode: Annotated[str | None, typer.Option("--mode", help="github: solo or team (spec §12).")] = None,
    code_owner: Annotated[
        str | None, typer.Option("--code-owner", help="github: governance files' code owner, @login or @org/team.")
    ] = None,
    copilot_review: Annotated[
        bool | None,
        typer.Option("--copilot-review/--no-copilot-review", help="github: request Copilot's review, and wait for it."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the plan and stop.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Apply without asking (for scripts).")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON result instead of text.")] = False,
    path: Annotated[Path, typer.Option("--path", help="The repository to set up.")] = Path("."),
) -> None:
    """Set the repository up to the standard: print the plan, then apply it. Never replaces your files.
    This version applies `docs`, `agents`, `ci`, `security` and `github`; the others come in later phases."""
    interactive = _interactive() and not as_json and not yes
    try:
        components, skipped = _selection(only, ctx.args)
        listed = [p.strip() for p in projects.split(",") if p.strip()] if projects is not None else None
        options = {"only": components, "skip": skipped, "with_governance": with_governance, "projects": listed,
                   "mode": mode, "code_owner": code_owner, "copilot_review": copilot_review}  # fmt: skip
        plan = make_plan(path, **options)
        if interactive and not dry_run:
            asked: dict[str, object] = {}
            if "agents" in plan.components and not plan.hosts_recorded:
                asked["hosts"] = _ask_hosts(plan.hosts)
            if plan.lint_question:
                asked["lint"] = _ask_lint()
            if plan.contact_question:
                asked["contact"] = _ask_contact(path.resolve())
            if plan.github_question:
                asked.update(_ask_github(plan.github_ask))  # asks only what no flag or record decided
            if asked:
                plan = make_plan(path, **{**options, **asked})
    except UsageError as error:
        raise _fail(error, 2, "init") from error
    except InitError as error:
        raise _fail(error, 1, "init") from error
    if not as_json:
        typer.echo(plan.render_text())
    if dry_run or not plan.changes:
        if as_json:
            typer.echo(json.dumps(plan.to_dict(applied=False), indent=2, ensure_ascii=False))
        raise typer.Exit(0)
    if not yes and not interactive:
        if as_json:
            typer.echo(json.dumps(plan.to_dict(applied=False), indent=2, ensure_ascii=False))
        typer.echo("swerepo init: nothing applied: run it in a terminal to answer, or with --yes", err=True)
        raise typer.Exit(2)
    if not yes and not typer.confirm("Apply?", default=False):
        typer.echo("Nothing applied.")
        raise typer.Exit(0)
    try:
        apply(plan, path)
        github_lines = _apply_github(plan, path, yes) if plan.github_apply else []
    except InitError as error:
        raise _fail(error, 1, "init") from error
    if as_json:
        typer.echo(json.dumps({**plan.to_dict(applied=True), "github": github_lines}, indent=2, ensure_ascii=False))
        raise typer.Exit(0)
    created = sum(1 for a in plan.changes if a.verb == "create")
    blocks = sum(1 for a in plan.changes if a.verb == "add block")
    rewritten = sum(1 for a in plan.changes if a.verb == "rewrite")
    again = f", {rewritten} rewritten" if rewritten else ""
    typer.echo(f"Applied: {created} file(s) created, {blocks} block(s) added{again}.")
    for line in github_lines:
        typer.echo(one_line(line))
    if any(a.verb == "waiting" for a in plan.actions) and plan.github_remote:  # on GitHub, gh missing or logged out
        typer.echo("Next: review the changes (git status, git diff), commit them on a new branch, open a pull request.")
        typer.echo("Then, with gh installed and logged in (gh auth login), apply the ruleset and merge settings:")
        typer.echo("  swerepo init --only github")
    elif any(a.verb == "waiting" for a in plan.actions):
        typer.echo("Next, as there is no GitHub repository yet (spec §12):")
        typer.echo("  1. commit these files on the default branch (the one commit straight to it)")
        typer.echo("  2. create the repository and push: gh repo create --source . --push")
        typer.echo("  3. apply the ruleset and merge settings: swerepo init --only github")
    else:
        typer.echo("Next: review the changes (git status, git diff), commit them on a new branch, open a pull request.")
    warning = noreply_warning(path.resolve())
    if warning:
        typer.echo(warning)


adr_app = typer.Typer(help="Architecture decision records: a new one from the template, or the index.")
app.add_typer(adr_app, name="adr")


def _repository(path: Path, command: str) -> tuple[Path, State | None]:
    """The repository folder and its state, for commands without a plan: a missing folder is wrong usage."""
    root = path.resolve()
    if not root.is_dir():
        raise _fail(UsageError(f"{root.name}: not a folder"), 2, command)
    try:
        return root, State.load(root)
    except StateError as error:
        raise _fail(error, 1, command) from error


def _adr_folder(path: Path, command: str) -> tuple[Path, str]:
    """The ADR folder, and its repository-relative name for messages. A folder or README that is a link out of
    the repository is refused: the ADR commands never write outside it (review: Copilot on PR #6)."""
    root, state = _repository(path, command)
    folder = str((state.adopted.get("adr_dir") if state else None) or standard.ADR_DIR)
    for target in (root / folder, root / folder / "README.md"):
        if not inside(root, target):
            raise _fail(AdrError(f"{target.relative_to(root).as_posix()} leads out of the repository"), 1, command)
    return root / folder, folder


@adr_app.command("new")
def adr_new(
    title: Annotated[str, typer.Argument(help="One line that states the decision.")],
    path: Annotated[Path, typer.Option("--path", help="The repository.")] = Path("."),
) -> None:
    """Create an ADR from the template, with a fresh ADR-YYYYMMDD-xxxx name, and update the index."""
    folder, label = _adr_folder(path, "adr new")
    try:
        created = new_adr(folder, title, label=label)
    except AdrError as error:
        raise _fail(error, 1, "adr new") from error
    typer.echo(one_line(f"Created {label}/{created.name}"))
    try:
        if write_index(folder, label=label):
            typer.echo("Index updated.")
    except AdrError as error:
        typer.echo(one_line(f"Index not updated: {error}"))


@adr_app.command("index")
def adr_index(path: Annotated[Path, typer.Option("--path", help="The repository.")] = Path(".")) -> None:
    """Regenerate the ADR index in the ADR folder's README.md (rerun it after a merge conflict there)."""
    folder, label = _adr_folder(path, "adr index")
    try:
        changed = write_index(folder, label=label)
    except AdrError as error:
        raise _fail(error, 1, "adr index") from error
    typer.echo("Index updated." if changed else "Index already current.")


@app.command()
def progress(
    count: Annotated[int, typer.Option("-n", help="How many of the latest progress entries to show.")] = 3,
    path: Annotated[Path, typer.Option("--path", help="The repository.")] = Path("."),
) -> None:
    """Now, Next and the latest progress entries, for people and agents. Changes nothing."""
    root, state = _repository(path, "progress")
    adopted = state.adopted.get("progress_dir") if state else None
    typer.echo(report(root, progress_dir=str(adopted) if adopted else None, count=count), nl=False)


@app.command()
def threads(
    number: Annotated[int, typer.Argument(help="The pull request's number.")],
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON result instead of text.")] = False,
    path: Annotated[Path, typer.Option("--path", help="The repository.")] = Path("."),
) -> None:
    """The open review threads of a pull request, through gh. Only reads: never replies or resolves."""
    from swerepo.github import GitHub, GitHubError
    from swerepo.threads import open_threads, render_text, to_dict

    if number < 1:
        raise _fail(UsageError("a pull request's number is 1 or more"), 2, "threads")
    root, _ = _repository(path, "threads")
    hub = GitHub.connect(root)
    if hub is None:
        raise _fail(UsageError("needs a GitHub remote (origin) and gh, logged in"), 2, "threads")
    try:
        found = open_threads(hub, number)
    except GitHubError as error:
        raise _fail(error, 1, "threads") from error
    if as_json:
        typer.echo(json.dumps(to_dict(number, found), indent=2, ensure_ascii=False))
    else:
        typer.echo("\n".join(one_line(line) for line in render_text(number, found).splitlines()))


def main() -> None:
    app()
