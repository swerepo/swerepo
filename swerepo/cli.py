"""The `swerepo` command line.

`check`, `init`, `update`, `diff`, `status`, `progress`, `adr`, `threads`, `privacy` and `hook`, for standard 1's six
components (SWEREPO-SPEC §7).
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer

from swerepo import __version__, github, standard
from swerepo import seamspec_component as ssc
from swerepo.adr import AdrError, new_adr, write_index
from swerepo.blocks import inside
from swerepo.check import UsageError, in_github_actions, job_blocks, one_line, run_check
from swerepo.init import (
    CANT_MERGE,
    CHANGED,
    CONFLICT,
    CURRENT,
    HOSTS,
    MERGE,
    MODE_MEANING,
    REWRITE,
    InitError,
    apply,
    apply_github,
    apply_seamspec,
    code_owner_refusal,
    has_github_remote,
    make_plan,
    noreply_warning,
    resolve_components,
    write_earned_spec,
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
            local=not ci,  # local git hooks exist only on a person's machine (ADR-20261123-24e0)
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


EDITORS_HELP = (
    "agents: the editors in use, comma-separated (claude, cursor, vscode, antigravity, gemini), or none; "
    "replaces the recorded ones"
)


APPLY_GITHUB_HELP = (
    "github: with --yes, also apply the ruleset and merge settings on GitHub (in a terminal you're shown each and "
    "asked; --yes alone never changes GitHub)"
)


def _interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _editor_names(text: str, given: str) -> list[str]:
    """Editor names from a comma- or space-separated list, without repeats; [] for `none` (review P8-A01)."""
    names = list(dict.fromkeys(h.strip().lower() for h in text.replace(" ", ",").split(",") if h.strip()))
    if not names:
        raise UsageError(f"{given}: name the editors ({', '.join(HOSTS)}), or none")
    if "none" in names and len(names) > 1:
        raise UsageError(f"{given}: none means no editor; it can't go with others")
    return [] if names == ["none"] else names


def _parse_editors(text: str | None, components: list[str]) -> list[str] | None:
    """`--editors claude,antigravity` (or `none`): the editors to set up and record; None when not given. Only with
    `agents`, which writes and records them, so they're never shown as recorded when they aren't (P8-A01, P8-A08)."""
    if text is None:
        return None
    if "agents" not in components:
        raise UsageError("--editors sets up and records the editors' files: it needs the agents component")
    return _editor_names(text, "--editors")


def _ask_hosts(detected: list[str]) -> list[str]:
    """Which editors the project uses (spec §6.6), pre-filled from what detection found."""
    while True:
        answer = typer.prompt(
            f"Editors in use ({', '.join(HOSTS)}; 'none' for none)", default=", ".join(detected) or "none"
        )
        try:
            names = _editor_names(answer, "editors")
        except UsageError as error:
            typer.echo(str(error))
            continue
        unknown = [h for h in names if h not in HOSTS]
        if not unknown:
            return names
        typer.echo(f"unknown editor {', '.join(unknown)} (known: {', '.join(HOSTS)})")


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


def _ask_github(ask: dict[str, str], refuse_owner: Callable[[str], str | None] | None = None) -> dict[str, object]:
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
        prompt = f"Code owner for governance files ({' or '.join(github.OWNER_EXAMPLES)}, or none)"
        while True:  # asked again until GitHub doesn't refuse it; offline, any well-formed owner (review P8-K)
            answer = typer.prompt(prompt, default=ask["code_owner"]).strip()
            refusal = refuse_owner(answer) if refuse_owner is not None else None
            if not refusal:
                break
            typer.echo(f"{answer}: {refusal}")
        answers["code_owner"] = answer
    return answers


def _ask_adopt(names: list[str], locked: list[tuple[str, str]]) -> dict[str, str]:
    """For each hygiene rule SWERepo would propose, whether a locked rule of the repository's own already covers it
    (ADR-20261124-cd64 point 6). Enter proposes SWERepo's."""
    ids = {rule_id for rule_id, _ in locked}
    typer.echo("Locked rules here:")
    for rule_id, title in locked:
        typer.echo(f"  {rule_id}  {one_line(title)}")
    answers: dict[str, str] = {}
    for name in names:
        while True:
            given = typer.prompt(f"A locked rule that covers hygiene/{name} (its id, or Enter to propose SWERepo's)",
                                 default="", show_default=False).strip()  # fmt: skip
            if not given or given in ids:
                break
            typer.echo(f"{given}: not one of the locked rules above")
        if given:
            answers[name] = given
    return answers


def _parse_adopt(given: list[str] | None) -> dict[str, str]:
    adopt: dict[str, str] = {}
    for item in given or []:
        name, sep, rule_id = item.partition("=")
        if not sep or not name.strip() or not rule_id.strip():
            raise UsageError(f"--adopt {item}: NAME=ID, for example privacy=inv_62d51113")
        adopt[name.strip()] = rule_id.strip()
    return adopt


def _seamspec_after(plan, path: Path, interactive: bool) -> list[str]:
    """SeamSpec's steps after the files: its own setup in this terminal, the hygiene proposals, the review if the
    person takes it now, then the earned spec (spec §13)."""
    if not (plan.seamspec_run or plan.seamspec_propose or plan.seamspec_spec or plan.seamspec_doctor):
        return []
    lines, ids = apply_seamspec(plan, path)
    if interactive:  # shown before the question about reviewing them; otherwise returned, so --json stays one object
        for line in lines:
            typer.echo(one_line(line))
        lines = []
    if ids and interactive and typer.confirm("Review the proposed rules now (seamspec review)?", default=True):
        found = ssc.command()
        if found:
            subprocess.run([found, "review"], cwd=path.resolve(), check=False)  # the person decides there
    elif ids:
        lines.append("Next: seamspec review, to approve or reject each proposed rule (SWERepo never approves)")
    written = write_earned_spec(path) if plan.seamspec_spec else None  # only when the plan holds it (review P7-F08)
    if written:
        lines.append(written)
    if plan.seamspec_doctor:  # update reports SeamSpec's own health last (ADR-20261124-cd64 point 8)
        doctor = ssc.doctor(path.resolve())
        if doctor is not None:
            errors, warnings = doctor
            said = (f"error in {', '.join(errors)}" if errors else f"warning in {', '.join(warnings)}" if warnings
                    else "healthy")  # fmt: skip
            lines.append(f"seamspec doctor: {said}")
    return lines


HELD_NEXT = ("Then apply the ruleset and merge settings on GitHub: swerepo init --only github in a terminal (each is "
             "shown first), or swerepo init --only github --yes --apply-github")  # fmt: skip


COPILOT_NOTE = (
    "Until a ruleset requests Copilot's review on the default branch, CI's copilot-review passes without "
    "waiting. To have Copilot review a pull request anyway: gh pr edit <number> --add-reviewer @copilot"
)


COPILOT_NOTE_OLD_JOB = (
    "swerepo-ci.yml's copilot-review still waits for Copilot's review on every pull request: run swerepo update "
    "--only ci and merge it. Until then, ask Copilot on each pull request: gh pr edit <number> --add-reviewer @copilot"
)


def _copilot_note(plan, path: Path, declined: bool) -> list[str]:
    """The note that CI doesn't wait for Copilot yet: where init or update leaves the ruleset unapplied (held for
    --apply-github, said no to in a terminal, or gh missing or logged out) and the workflow waits for Copilot's review
    (ADR-20261126-c228). Never under --no-copilot-review, and not before there is a GitHub repository."""
    try:
        state = State.load(path)
    except StateError:
        return []
    if state is None or state.values.get("ci_copilot_review") != "true":
        return []
    waiting = any(a.verb == "waiting" and a.component == "github" for a in plan.actions)
    logged_out = waiting and plan.github_remote is not None and plan.github_slug is None
    left = (plan.github_held or declined) and plan.copilot_unrequested
    if not (left or logged_out):
        return []
    try:
        text = (path / standard.CI_WORKFLOW).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    # the pass is promised only where the job on disk reads the rules; an older one still waits (PR #24 review)
    return [COPILOT_NOTE if "rules/branches/" in job_blocks(text).get("copilot-review", "") else COPILOT_NOTE_OLD_JOB]


def _apply_github(plan, path: Path, yes: bool) -> tuple[list[str], bool]:
    """Show each GitHub change as JSON and apply what the person says yes to (all of them with --yes). Also returns
    whether the person said no to the ruleset."""
    labels = {"ruleset": 'Apply ruleset "swerepo" on the default branch?', "settings": "Apply merge settings?"}
    chosen = []
    for name, data in plan.github_apply.items():
        if not yes:
            typer.echo(json.dumps(data, indent=2))
            if not typer.confirm(labels[name], default=False):
                continue
        chosen.append(name)
    declined = "ruleset" in plan.github_apply and "ruleset" not in chosen
    if not chosen:
        return ["GitHub: nothing applied (run `swerepo init --only github` again to apply)"], declined
    return [f"GitHub: {line}" for line in apply_github(plan, path, chosen)], declined


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
        str | None,
        typer.Option(
            "--code-owner", help=f"github: governance files' code owner, {' or '.join(github.OWNER_EXAMPLES)}."
        ),
    ] = None,
    copilot_review: Annotated[
        bool | None,
        typer.Option("--copilot-review/--no-copilot-review", help="github: request Copilot's review, and wait for it."),
    ] = None,
    adopt: Annotated[
        list[str] | None,
        typer.Option("--adopt", help="seamspec: NAME=ID, a locked rule of yours covering a hygiene rule."),
    ] = None,
    editors: Annotated[str | None, typer.Option("--editors", help=EDITORS_HELP)] = None,
    apply_github: Annotated[bool, typer.Option("--apply-github", help=APPLY_GITHUB_HELP)] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the plan and stop.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Apply without asking (for scripts).")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON result instead of text.")] = False,
    path: Annotated[Path, typer.Option("--path", help="The repository to set up.")] = Path("."),
) -> None:
    """Set the repository up to the standard: print the plan, then apply it. Never replaces your files.
    The components are `docs`, `agents`, `ci`, `security`, `github` and `seamspec`."""
    interactive = _interactive() and not as_json and not yes
    try:
        components, skipped = _selection(only, ctx.args)
        listed = [p.strip() for p in projects.split(",") if p.strip()] if projects is not None else None
        options = {
            "only": components,
            "skip": skipped,
            "with_governance": with_governance,
            "projects": listed,
            "mode": mode,
            "code_owner": code_owner,
            "copilot_review": copilot_review,
            "adopt": _parse_adopt(adopt),
            "terminal": interactive and not dry_run,
            "hosts": _parse_editors(editors, resolve_components(components, skipped)),
            "apply_github": apply_github or interactive,  # a terminal shows each change and asks first
        }  # a terminal shows each change and asks first
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
                refuse = lambda owner: code_owner_refusal(path, owner)  # noqa: E731
                asked.update(_ask_github(plan.github_ask, refuse))  # asks only what no flag or record decided
            if plan.seamspec_ask:
                asked["adopt"] = {**options["adopt"], **_ask_adopt(plan.seamspec_ask, plan.seamspec_locked)}
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
        github_lines, declined = _apply_github(plan, path, yes) if plan.github_apply else ([], False)
        seamspec_lines = _seamspec_after(plan, path, interactive)
    except InitError as error:
        raise _fail(error, 1, "init") from error
    if as_json:
        result = {**plan.to_dict(applied=True), "github": github_lines, "seamspec": seamspec_lines}
        typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
        raise typer.Exit(0)
    created = sum(1 for a in plan.changes if a.verb == "create")
    blocks = sum(1 for a in plan.changes if a.verb == "add block")
    rewritten = sum(1 for a in plan.changes if a.verb == "rewrite")
    again = f", {rewritten} rewritten" if rewritten else ""
    typer.echo(f"Applied: {created} file(s) created, {blocks} block(s) added{again}.")
    for line in [*github_lines, *seamspec_lines]:
        typer.echo(one_line(line))
    github_waits = any(a.verb == "waiting" and a.component == "github" for a in plan.actions)
    if plan.github_held:  # GitHub differs, and --yes alone never changes it (ADR-20261125-5f22 point 5)
        typer.echo("Next: review the changes (git status, git diff), commit them on a branch, open a pull request.")
        typer.echo(HELD_NEXT)
    elif github_waits and plan.github_remote:  # on GitHub, gh missing or logged out
        typer.echo("Next: review the changes (git status, git diff), commit them on a branch, open a pull request.")
        typer.echo("Then, with gh installed and logged in (gh auth login), apply the ruleset and merge settings:")
        typer.echo("  swerepo init --only github")
    elif github_waits:
        typer.echo("Next, as there is no GitHub repository yet (spec §12):")
        typer.echo("  1. commit these files on the default branch (the one commit straight to it)")
        typer.echo("  2. create the repository and push: gh repo create --source . --push")
        typer.echo("  3. apply the ruleset and merge settings: swerepo init --only github")
    else:
        typer.echo("Next: review the changes (git status, git diff), commit them on a branch, open a pull request.")
    for line in _copilot_note(plan, path, declined):
        typer.echo(line)
    warning = noreply_warning(path.resolve())
    if warning:
        typer.echo(warning)


def _update_plan(
    path: Path,
    components: list[str] | None,
    skipped: list[str],
    command: str,
    editors: str | None = None,
    **options: Any,
):
    """The update plan for the components SWERepo set up here (all of them, or those asked for)."""
    _, state = _repository(path, command)
    if state is None:
        raise UsageError("SWERepo hasn't set this repository up yet: run swerepo init")
    chosen = components if components is not None else list(state.components)
    resolve_components(components, skipped)  # a name no component has is wrong usage first (SeamSpec's reviewer)
    missing = [c for c in chosen if c not in state.components]
    if missing:
        raise UsageError(f"not set up here: {', '.join(missing)} (swerepo init --only {','.join(missing)})")
    hosts = _parse_editors(editors, [c for c in resolve_components(chosen, skipped) if c in state.components])
    return make_plan(path, only=chosen, skip=skipped, update=True, hosts=hosts, **options)


@app.command(context_settings=EXTRA_ARGS, epilog=SHORTHAND)
def update(
    ctx: typer.Context,
    only: Annotated[str | None, typer.Option("--only", help="Update only these components, comma-separated.")] = None,
    enforce_pr_rules: Annotated[
        bool, typer.Option("--enforce-pr-rules", help="Make the pull-request rules fail, not warn (spec §10).")
    ] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the plan and stop.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Apply without asking (for scripts).")] = False,
    merge: Annotated[
        bool, typer.Option("--merge", help="With --yes: also merge the update into files you edited.")
    ] = False,
    editors: Annotated[str | None, typer.Option("--editors", help=EDITORS_HELP)] = None,
    apply_github: Annotated[bool, typer.Option("--apply-github", help=APPLY_GITHUB_HELP)] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON result instead of text.")] = False,
    path: Annotated[Path, typer.Option("--path", help="The repository to update.")] = Path("."),
) -> None:
    """Bring what SWERepo manages up to the current templates: replace what nobody changed, merge the update into
    your edits (shown first), and report conflicts. Never touches your own files, never deletes one."""
    interactive = _interactive() and not as_json and not yes
    try:
        components, skipped = _selection(only, ctx.args)
        plan = _update_plan(path, components, skipped, "update", merge=merge or interactive,
                            enforce_pr_rules=enforce_pr_rules, terminal=interactive and not dry_run,
                            editors=editors, apply_github=apply_github or interactive)  # fmt: skip
    except UsageError as error:
        raise _fail(error, 2, "update") from error
    except InitError as error:
        raise _fail(error, 1, "update") from error
    if not as_json:
        typer.echo(plan.render_text())
        for action in plan.actions:
            if action.verb == MERGE and action.diff:  # a merge into a person's file is always shown first
                typer.echo("\n" + "\n".join(one_line(line) for line in action.diff.splitlines()))
    if dry_run or not plan.changes:
        if as_json:
            typer.echo(json.dumps(plan.to_dict(applied=False), indent=2, ensure_ascii=False))
        raise typer.Exit(0)
    if not yes and not interactive:
        if as_json:
            typer.echo(json.dumps(plan.to_dict(applied=False), indent=2, ensure_ascii=False))
        typer.echo("swerepo update: nothing applied: run it in a terminal to answer, or with --yes", err=True)
        raise typer.Exit(2)
    if not yes and not typer.confirm("Apply?", default=False):
        typer.echo("Nothing applied.")
        raise typer.Exit(0)
    try:
        apply(plan, path)
        github_lines, declined = _apply_github(plan, path, yes) if plan.github_apply else ([], False)
        seamspec_lines = _seamspec_after(plan, path, interactive)
    except InitError as error:
        raise _fail(error, 1, "update") from error
    if as_json:
        result = {**plan.to_dict(applied=True), "github": github_lines, "seamspec": seamspec_lines}
        typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
        raise typer.Exit(0)
    counts = {verb: sum(1 for a in plan.changes if a.verb == verb) for verb in (REWRITE, MERGE, "create", "add block")}
    typer.echo(f"Applied: {counts[REWRITE]} updated, {counts[MERGE]} merged, "
               f"{counts['create'] + counts['add block']} added.")  # fmt: skip
    for line in [*github_lines, *seamspec_lines]:
        typer.echo(one_line(line))
    left = sum(1 for a in plan.actions if a.verb in (CONFLICT, CANT_MERGE))
    if left:
        typer.echo(f"{left} file(s) left as they are: swerepo diff shows the change to make by hand.")
    typer.echo("Next: review the changes (git status, git diff), commit them on a branch, open a pull request.")
    if plan.github_held:
        typer.echo(HELD_NEXT)
    for line in _copilot_note(plan, path, declined):
        typer.echo(line)


@app.command()
def diff(
    files: Annotated[list[str] | None, typer.Argument(help="Only these files (default: all).")] = None,
    path: Annotated[Path, typer.Option("--path", help="The repository.")] = Path("."),
) -> None:
    """What `update` would change in files you edited, and, where your edits conflict with the update, the
    change to make by hand. Changes nothing."""
    try:
        plan = _update_plan(path, None, [], "diff", merge=True, read_github=False)
    except UsageError as error:
        raise _fail(error, 2, "diff") from error
    except InitError as error:
        raise _fail(error, 1, "diff") from error
    wanted = {f.replace("\\", "/").removeprefix("./") for f in files or []}  # as the plan names them (P6-F07)
    kinds = {
        MERGE: "merged into your edits",
        CONFLICT: "conflicts with your edits: make this change by hand",
        CANT_MERGE: "can't be merged (the earlier render can't be rebuilt): SWERepo's new version against yours",
    }
    shown = [a for a in plan.actions if a.verb in kinds and a.diff and (not wanted or a.path in wanted)]
    for action in shown:
        typer.echo(f"{action.path}: {kinds[action.verb]}")
        typer.echo("\n".join(one_line(line) for line in (action.diff or "").splitlines()))
    if not shown:
        typer.echo("Nothing to show: update changes no file you edited.")


@app.command()
def status(
    as_json: Annotated[bool, typer.Option("--json", help="Print one JSON result instead of text.")] = False,
    path: Annotated[Path, typer.Option("--path", help="The repository.")] = Path("."),
) -> None:
    """What SWERepo set up here, and what `update` would do: components, mode, versions, and how many managed
    files are current, outdated, edited or in conflict. Changes nothing."""
    try:
        _, state = _repository(path, "status")
        if state is None:
            raise UsageError("SWERepo hasn't set this repository up yet: run swerepo init")
        plan = _update_plan(path, None, [], "status", merge=True, read_github=False)
    except UsageError as error:
        raise _fail(error, 2, "status") from error
    except InitError as error:
        raise _fail(error, 1, "status") from error
    kinds = {CURRENT: "current", REWRITE: "outdated", MERGE: "edited, update merges cleanly",
             CONFLICT: "edited, conflicts with the update", CANT_MERGE: "edited, can't merge",
             CHANGED: "edited, nothing to update"}  # fmt: skip
    counts = {label: sum(1 for a in plan.actions if a.verb == verb and a.path) for verb, label in kinds.items()}
    result = {
        "components": list(state.components),
        "mode": state.mode,
        "standard": state.standard,
        "swerepo": {"recorded": state.swerepo_version, "running": __version__},
        "tools": dict(state.tools),
        "pr_rules": "enforced" if state.pr_enforce else "warnings",
        "files": counts,
    }
    if as_json:
        typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
        return
    typer.echo(f"SWERepo · status · {path.resolve().name}")
    typer.echo(f"  components  {', '.join(result['components'])}")
    typer.echo(f"  mode        {state.mode or 'not chosen'}")
    typer.echo(f"  standard    {state.standard} · SWERepo {state.swerepo_version} recorded, {__version__} running")
    if state.tools:
        typer.echo("  tools       " + ", ".join(f"{name} {version}" for name, version in sorted(state.tools.items())))
    typer.echo(f"  PR rules    {result['pr_rules']}")
    for label, count in counts.items():
        if count:
            typer.echo(f"  {count:>3}  {label}")
    if counts[kinds[REWRITE]] or counts[kinds[MERGE]]:
        typer.echo("Next: swerepo update")


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


@app.command()
def privacy(
    pre_push: Annotated[
        bool, typer.Option("--pre-push", help="Scan the commits git is about to push (refs on standard input).")
    ] = False,
    remote: Annotated[
        str | None, typer.Option("--remote", help="With --pre-push: the remote git is pushing to (the hook passes it).")
    ] = None,
    path: Annotated[Path, typer.Option("--path", help="The repository.")] = Path("."),
) -> None:
    """The privacy scan: keys, personal email addresses and home-folder paths, by kind and place, never what.
    Exit 1 when something is found."""
    from swerepo import hook
    from swerepo import privacy as scan

    root, state = _repository(path, "privacy")
    allow = state.privacy_allow_paths if state else []
    if not pre_push:
        found = scan.scan(root, allow)
        if found:
            typer.echo(f"swerepo privacy: {one_line(scan.summary(found))}", err=True)
            raise typer.Exit(1)
        typer.echo("swerepo privacy: nothing found")
        return
    try:
        hits = hook.pushed_hits(root, hook.parse_updates(sys.stdin.read()), allow, remote or None)
    except hook.HookError as error:
        raise _fail(error, 1, "privacy") from error
    if hits:
        where = scan.summary(hits, place="the commits being pushed")
        typer.echo(f"swerepo: push refused: {one_line(where)}", err=True)
        advice = (
            "swerepo: remove it from those commits (amend or rebase), or mark a line meant to be published with "
            f"'{scan.MARKER}'; git push --no-verify skips this check once."
        )
        typer.echo(advice, err=True)
        raise typer.Exit(1)


hook_app = typer.Typer(help="Local git hooks: the pre-push privacy scan (ADR-20261123-24e0).")
app.add_typer(hook_app, name="hook")


@hook_app.command("install")
def hook_install(path: Annotated[Path, typer.Option("--path", help="The repository.")] = Path(".")) -> None:
    """Install the pre-push hook that refuses a push adding a key, a personal email address or a home-folder path.
    Never replaces a pre-push hook of your own."""
    from swerepo import hook

    root, state = _repository(path, "hook install")
    try:
        done, message = hook.install(root, state.values.get("privacy_command") if state else None)
    except hook.HookError as error:
        raise _fail(error, 1, "hook install") from error
    typer.echo(message)
    if not done:
        raise typer.Exit(1)


def main() -> None:
    if sys.argv[1:2] == ["-u"]:  # `swerepo -u` is `swerepo update` (spec §7)
        sys.argv[1] = "update"
    app()
