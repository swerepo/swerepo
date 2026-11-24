"""`swerepo init` for the `docs` and `agents` components (spec §5, §6.5, §6.6, §7, §10; ADR-20261121-6c3d).

Two steps. `make_plan` reads the repository and decides, file by file, what to create, which marked block to
add, and what to leave alone; it writes nothing, and builds the new `.swerepo.toml` in memory. `apply` writes
exactly that plan. Existing files are never replaced: SWERepo only creates missing files and adds its own
marked block to an existing one (principles 2 and 3).

Two kinds of files:
- **managed** (recorded in `.swerepo.toml`, kept current by `swerepo update`): the ADR README and TEMPLATE,
  the `docs/agents/` runbooks, and SWERepo's blocks in AGENTS.md, CLAUDE.md and GEMINI.md;
- **starter** (written once, the person's from then on, never recorded): README.md, docs/PROGRESS.md,
  CHANGELOG.md, CONTRIBUTING.md and the first progress entry.
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from swerepo import __version__, ci, github, privacy, standard
from swerepo.adr import AdrError, list_adrs, with_index
from swerepo.blocks import ADR_INDEX, append_block, file_fingerprint, inside, read_exact, replace_block_content, wrap
from swerepo.check import _UNRELEASED, UsageError, one_line
from swerepo.detect import KNOWN_PYTHONS, Detection, detect
from swerepo.fingerprint import HTML, BlockError, comment_style, find_block, fingerprint
from swerepo.render import TemplateStore
from swerepo.state import COMPONENTS, FILE_NAME, Record, State, StateError

AVAILABLE = ("docs", "agents", "ci", "security", "github")  # components this version of init applies
LATER = {"seamspec": 7, "openspec": 8, "release": 8}
HOSTS = ("claude", "cursor", "vscode", "antigravity", "gemini")
HOST_NAMES = {
    "claude": "Claude Code", "cursor": "Cursor", "vscode": "VS Code Copilot", "antigravity": "Antigravity",
    "gemini": "Gemini CLI",
}  # fmt: skip
RECORDED_VALUES = ("project", "adr_dir", "progress_dir", "commands", "test_inline")  # managed templates use these

CREATE, ADD_BLOCK, GIT_INIT, WRITE_STATE, REWRITE = "create", "add block", "git init", "write", "rewrite"
APPLY, WAITING = "apply", "waiting"  # GitHub settings, applied through gh after the files (ADR-20261123-4e40)
KEEP, CURRENT, CHANGED, OUTDATED = "keep", "current", "changed", "outdated"
ADOPT, NOTE, LATER_VERB = "adopt", "note", "later"
CHANGING = (CREATE, ADD_BLOCK, GIT_INIT, WRITE_STATE, REWRITE, APPLY)


class InitError(RuntimeError):
    """init can't go on: an unreadable or newer `.swerepo.toml`, a folder of repositories, a failed write."""


@dataclass
class Action:
    component: str
    verb: str
    path: str | None = None
    note: str = ""
    content: str | None = None  # the whole file (create) or the block's content (add block)
    record: Record | None = None  # what `.swerepo.toml` records; None for starter files
    kind: str | None = None  # "file" or "block" when recorded
    expect: str | None = None  # rewrite: the fingerprint the file must still have (SWERepo's, unchanged)

    @property
    def changes(self) -> bool:
        return self.verb in CHANGING

    def to_dict(self) -> dict[str, Any]:
        return {"component": self.component, "action": self.verb, "path": self.path, "note": self.note}


@dataclass
class Plan:
    folder: str
    components: list[str]
    hosts: list[str]
    hosts_recorded: bool
    actions: list[Action] = field(default_factory=list)
    state_text: str | None = None  # the new .swerepo.toml, or None if it doesn't change
    state_before: str | None = None  # .swerepo.toml as the plan read it (None: there was none)
    lint_question: bool = False  # other linters found and nothing recorded: keep them, or move to ruff gradually
    contact_question: bool = False  # SECURITY.md to create: who to report vulnerabilities to
    github_question: bool = False  # the github component with its mode or code owner neither given nor recorded
    github_ask: dict[str, str] = field(default_factory=dict)  # what to ask ("mode", "code_owner") and its default
    github_apply: dict[str, dict[str, Any]] = field(default_factory=dict)  # "ruleset", "settings": JSON to apply
    github_slug: str | None = None  # owner/name, when the repository is on GitHub and gh is logged in
    github_remote: str | None = None  # owner/name of the github.com remote, with or without gh (PR #10 review)
    # GitHub read and compared: None when it couldn't be read; False when read but a settings file couldn't be
    # compared (missing, not JSON, or not applicable); True when both files were compared (PR #10 review)
    github_compared: bool | None = None

    @property
    def changes(self) -> list[Action]:
        return [a for a in self.actions if a.changes]

    def to_dict(self, *, applied: bool) -> dict[str, Any]:
        return {
            "swerepo": __version__,
            "folder": self.folder,
            "components": self.components,
            "editors": self.hosts,
            "actions": [a.to_dict() for a in self.actions],
            "changes": len(self.changes),
            "applied": applied,
        }

    def render_text(self) -> str:
        editors = ", ".join(HOST_NAMES.get(h, h) for h in self.hosts) or "none"
        how = "" if self.hosts_recorded else " (detected)"
        lines = [f"SWERepo · init · {self.folder} (editors: {editors}{how})"]
        for group in ("repository", *COMPONENTS, "state"):
            for index, action in enumerate(a for a in self.actions if a.component == group):
                label = group if index == 0 else ""
                target = action.path or ""
                note = f" ({action.note})" if action.note and target else action.note
                lines.append(f"  {label:<10} {action.verb:<9} {target}{note}".rstrip())
        count = len(self.changes)
        lines.append(f"{count} change{'' if count == 1 else 's'}." if count else "Nothing to do.")
        return "\n".join(one_line(line) for line in lines)


# --- values and commands ------------------------------------------------------------------------------


def _project_name(root: Path) -> str:
    try:
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        data = {}
    project = data.get("project")
    name = project.get("name") if isinstance(project, dict) else None
    return name if isinstance(name, str) and name.strip() else root.name


def _make_targets(root: Path) -> set[str]:
    try:
        text = (root / "Makefile").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return set(re.findall(r"^(install|test|lint|check)\s*:", text, re.MULTILINE))


_KEPT_LINT = {"black": "black --check .", "isort": "isort --check-only .", "flake8": "flake8", "pylint": "pylint ."}


def commands(
    root: Path, detection: Detection, adopted_linters: list[str] | None = None, lint_mode: str | None = None
) -> dict[str, list[str]]:
    """The commands agents and people run, from what the project uses (spec §6.6): uv by default, poetry
    when it has a poetry.lock, a Makefile's `install`, `test` and `lint` targets when it has them, and the
    linters recorded under `[adopted] linters` (as `check` reads them) before the detected ones. `lint_mode`
    (the `ci` component's choice) decides between ruff and kept linters, the same on every run (P4-F07)."""
    poetry = (root / "poetry.lock").is_file() and not (root / "uv.lock").is_file()
    runner, install = ("poetry run", "poetry install") if poetry else ("uv run", "uv sync")
    linters = set(adopted_linters) if adopted_linters else {linter.name for linter in detection.linters}
    if lint_mode == "gradual":
        files = "--force-exclude <changed .py files>"
        lint = [f"{runner} ruff check {files}", f"{runner} ruff format --check {files}"]
    elif lint_mode == "ruff" or (lint_mode is None and ("ruff" in linters or not linters)):
        lint = [f"{runner} ruff check .", f"{runner} ruff format --check ."]
    else:
        lint = [f"{runner} {_KEPT_LINT[name]}" for name in sorted(linters) if name in _KEPT_LINT]
    targets = _make_targets(root)
    return {
        "install": ["make install" if "install" in targets else install],
        "test": ["make test" if "test" in targets else f"{runner} pytest"],
        "lint": ["make lint"] if "lint" in targets else lint,
        "check": ["swerepo check"],
    }


def _code(items: list[str]) -> str:
    quoted = [f"`{item}`" for item in items]
    return quoted[0] if len(quoted) == 1 else ", ".join(quoted[:-1]) + " and " + quoted[-1]


def compute_values(
    root: Path,
    detection: Detection,
    adr_dir: str,
    progress_dir: str,
    adopted_linters: list[str] | None = None,
    lint_mode: str | None = None,
) -> dict[str, str]:
    found = commands(root, detection, adopted_linters, lint_mode)
    listed = [
        f"- Install: {_code(found['install'])}",
        f"- Test: {_code(found['test'])}",
        *([f"- Lint: {_code(found['lint'])}"] if found["lint"] else []),
        f"- Check the standard: {_code(found['check'])}",
    ]
    return {
        "project": _project_name(root),
        "adr_dir": adr_dir,
        "progress_dir": progress_dir,
        "commands": "\n".join(listed),
        "test_inline": _code(found["test"] + found["lint"]),
        "install": "\n".join(found["install"]),
        "test_lines": "\n".join(found["test"] + found["lint"]),
    }


# --- planning -----------------------------------------------------------------------------------------


def resolve_components(only: list[str] | None, skip: list[str] | tuple[str, ...] = ()) -> list[str]:
    """The components this run is about: `only`, or every component; minus `skip`. Wrong names are usage errors."""
    unknown = [c for c in [*(only or []), *skip] if c not in COMPONENTS]
    if unknown:
        raise UsageError(f"unknown component {', '.join(unknown)} (known: {', '.join(COMPONENTS)})")
    if only is not None and not only:
        raise UsageError(f"--only needs at least one component (known: {', '.join(COMPONENTS)})")
    chosen = list(only) if only is not None else list(COMPONENTS[:6])
    return [c for c in COMPONENTS if c in chosen and c not in skip]


@dataclass
class _Context:
    root: Path
    detection: Detection
    state: State | None
    store: TemplateStore
    values: dict[str, str]
    today: datetime.date

    def exists(self, path: str) -> bool:
        return (self.root / path).is_file()

    def read(self, path: str) -> str:
        try:
            return read_exact(self.root / path, errors="surrogateescape")
        except OSError as error:  # the reason only: the error's own text names the absolute path
            raise InitError(f"{path}: can't read it ({error.strerror or type(error).__name__})") from error


def _managed_file(
    ctx: _Context, component: str, path: str, template: str, render: tuple[str, str] | None = None
) -> Action:
    """A file SWERepo keeps current: created when missing, otherwise compared with its record. `render`:
    (template id, text) rendered by the component itself, for files built from several templates."""
    if not inside(ctx.root, ctx.root / path):
        return Action(component, KEEP, path, _OUTSIDE)
    if render is None:
        latest = ctx.store.latest(*template.split("/"))
        template_id, text = latest.id, latest.render(ctx.values)
    else:
        template_id, text = render
    rendered = file_fingerprint(text, template_id)
    record = ctx.state.files().get(path) if ctx.state else None
    if not ctx.exists(path):
        if template_id.startswith("docs/adr-readme@"):
            try:
                text = with_index(text, list_adrs(ctx.root / path.rsplit("/", 1)[0]))
            except AdrError as error:
                raise InitError(f"{path.rsplit('/', 1)[0]}/{error}") from error
        record = Record(template_id, rendered, rendered)
        return Action(component, CREATE, path, content=text, record=record, kind="file")
    if record is None:
        return Action(component, KEEP, path, "yours: SWERepo didn't write it")
    if file_fingerprint(ctx.read(path), record.template) != record.written:
        return Action(component, CHANGED, path, "changed by you: kept")
    if record.template == template_id and record.rendered == rendered:
        return Action(component, CURRENT, path)
    return Action(component, OUTDATED, path, f"{template_id} renders differently now: swerepo update (Phase 6)")


_OUTSIDE = "a link out of the repository: SWERepo doesn't write there"


def _managed_block(
    ctx: _Context,
    component: str,
    path: str,
    template: str,
    heading: str = "",
    render: tuple[str, str] | None = None,
) -> Action:
    """SWERepo's marked block in a file: added when missing, otherwise compared with its record. `render`:
    (template id, block content) rendered by the component itself."""
    if not inside(ctx.root, ctx.root / path):
        return Action(component, KEEP, path, _OUTSIDE)
    if render is None:
        latest = ctx.store.latest(*template.split("/"))
        template_id, content = latest.id, latest.render(ctx.values)
    else:
        template_id, content = render
    rendered = fingerprint(content)
    record = ctx.state.blocks().get(path) if ctx.state else None
    new_record = Record(template_id, rendered, rendered)
    if not ctx.exists(path):
        whole = heading + wrap(content, path)
        return Action(component, CREATE, path, "SWERepo block", content=whole, record=new_record, kind="block")
    text = ctx.read(path)
    try:
        block = find_block(text, style=comment_style(path))
    except BlockError as error:
        return Action(component, KEEP, path, f"SWERepo block markers are broken ({error}): fix them first")
    if block is None:
        if path == "CLAUDE.md" and any(line.strip() == "@AGENTS.md" for line in text.splitlines()):
            return Action(component, KEEP, path, "already imports AGENTS.md")
        if path == "GEMINI.md" and "AGENTS.md" in text:  # what check accepts (spec §6.6: points to AGENTS.md)
            return Action(component, KEEP, path, "already points to AGENTS.md")
        if not _block_findable(text, content, path):
            return Action(component, KEEP, path, "ends inside an unclosed code fence: close it, then run init again")
        return Action(component, ADD_BLOCK, path, content=content, record=new_record, kind="block")
    if record is None:
        return Action(component, KEEP, path, "has a SWERepo block SWERepo didn't record: kept")
    if fingerprint(block.content) != record.written:
        return Action(component, CHANGED, path, "block changed by you: kept")
    if record.template == template_id and record.rendered == rendered:
        return Action(component, CURRENT, path, "SWERepo block")
    return Action(component, OUTDATED, path, f"{template_id} renders differently now: swerepo update (Phase 6)")


def _block_findable(text: str, content: str, path: str) -> bool:
    """Whether the block, once appended, can be found again: not if the text ends inside an unclosed Markdown
    fence, where every later run would append another copy (review: Copilot on PR #6)."""
    try:
        return find_block(append_block(text, content, path), style=comment_style(path)) is not None
    except BlockError:
        return False


def _starter(ctx: _Context, component: str, path: str, template: str, values: dict[str, str]) -> Action:
    if not inside(ctx.root, ctx.root / path):
        return Action(component, KEEP, path, _OUTSIDE)
    if ctx.exists(path):
        return Action(component, KEEP, path, "yours")
    text = ctx.store.latest(*template.split("/")).render(values)
    return Action(component, CREATE, path, content=text)


def _adr_dir(ctx: _Context) -> tuple[str, bool]:
    """The ADR folder, and whether it is an existing one SWERepo adopts instead of its own."""
    adopted = ctx.state.adopted.get("adr_dir") if ctx.state else None
    if adopted:
        return str(adopted), True
    found = [a.path for a in ctx.detection.adr_dirs]
    if not found:
        return standard.ADR_DIR, False
    if standard.ADR_DIR not in found:
        return found[0], True
    readme = f"{standard.ADR_DIR}/README.md"
    recorded = ctx.state is not None and readme in ctx.state.files()
    if ctx.exists(readme) and not recorded and not _has_index_markers(ctx.read(readme)):
        return standard.ADR_DIR, True  # a person's own ADR folder: follow it, add nothing (spec §6.5, §10)
    return standard.ADR_DIR, False


def _has_index_markers(text: str) -> bool:
    try:
        return find_block(text, style=HTML, marker=ADR_INDEX) is not None
    except BlockError:
        return True  # markers are there, broken: check reports them; don't treat the folder as foreign


def _progress_link(progress_dir: str) -> str:
    """The progress folder as a link from docs/PROGRESS.md."""
    return progress_dir.removeprefix("docs/") if progress_dir.startswith("docs/") else f"../{progress_dir}"


def _docs(ctx: _Context, adr_dir: str, adopted: bool) -> list[Action]:
    c, d = "docs", ctx.detection
    actions: list[Action] = []
    readme = d.documents.get("readme")
    if readme:
        actions.append(Action(c, KEEP, readme, "yours"))
    else:
        actions.append(_starter(ctx, c, "README.md", "docs/project-readme", ctx.values))
    if adopted:
        count = len([p for p in (ctx.root / adr_dir).glob("*.md") if p.name.lower() not in standard.NOT_ADRS])
        files = f"{count} file{'' if count == 1 else 's'}"
        actions.append(Action(c, ADOPT, adr_dir, f"your ADR folder, {files}: followed, nothing added to it"))
    else:
        actions.append(_managed_file(ctx, c, f"{adr_dir}/README.md", "docs/adr-readme"))
        actions.append(_managed_file(ctx, c, f"{adr_dir}/TEMPLATE.md", "docs/adr-template"))
    progress = d.documents.get("progress")
    if progress and progress != standard.PROGRESS_FILE:
        actions.append(Action(c, KEEP, progress, f"yours; standard 1 expects {standard.PROGRESS_FILE}"))
    else:
        values = {**ctx.values, "progress_link": _progress_link(ctx.values["progress_dir"])}
        actions.append(_starter(ctx, c, standard.PROGRESS_FILE, "docs/progress-index", values))
    changelog = d.documents.get("changelog")
    if changelog is None:
        actions.append(_starter(ctx, c, "CHANGELOG.md", "docs/changelog", ctx.values))
    elif not _UNRELEASED.search(ctx.read(changelog)):
        actions.append(Action(c, KEEP, changelog, "yours; add an `## [Unreleased]` section (check asks for one)"))
    else:
        actions.append(Action(c, KEEP, changelog, "yours"))
    contributing = d.documents.get("contributing")
    if contributing:
        actions.append(Action(c, KEEP, contributing, "yours"))
    else:
        actions.append(_starter(ctx, c, "CONTRIBUTING.md", "docs/contributing", ctx.values))
    if not d.documents.get("license"):
        actions.append(Action(c, NOTE, None, "no LICENSE: init never picks one; add the license you choose"))
    return actions


def _agents(ctx: _Context, hosts: list[str]) -> list[Action]:
    c = "agents"
    actions = [_managed_block(ctx, c, "AGENTS.md", "agents/block", "# Agent instructions\n\n")]
    if "claude" in hosts:
        actions.append(_managed_block(ctx, c, "CLAUDE.md", "agents/claude"))
    if {"antigravity", "gemini"} & set(hosts):
        actions.append(_managed_block(ctx, c, "GEMINI.md", "agents/gemini"))
    for path in standard.RUNBOOKS:
        actions.append(_managed_file(ctx, c, path, f"agents/{Path(path).stem}"))
    return actions


# --- ci and security (ADR-20261122-4a06, ADR-20261122-a48e) -------------------------------------------------


@dataclass
class _Workflows:
    """What the `ci` and `security` workflows share: the default branch and Python versions, from `[values]` once
    recorded (renders stay stable; changes are `update`'s, Phase 6), else from the repository; and the command CI
    would run SWERepo with now (each workflow records its own, P4-F02)."""

    default_branch: str
    python: list[str]  # what the project declares now; each workflow keeps its own recorded snapshot
    python_note: str
    swerepo: str  # the command CI would run SWERepo with; "" for none
    swerepo_note: str
    with_governance: bool


def _workflows(ctx: _Context, *, with_governance: bool) -> _Workflows:
    recorded = ctx.state.values if ctx.state else {}
    branch = recorded.get("default_branch")
    if not isinstance(branch, str) or not ci.valid_folder(branch):
        branch = ci.default_branch(ctx.root)
    python, python_note = ci.python_versions(ctx.detection)
    command, note = ci.swerepo_command(ctx.root, with_governance=with_governance)
    return _Workflows(str(branch), [str(v) for v in python], python_note, command, note, with_governance)


def _recorded(ctx: _Context, path: str, name: str) -> object:
    """A workflow's own recorded input: only while that workflow is recorded, so one workflow's snapshot never
    decides another's first render (review: Copilot on PR #8)."""
    if ctx.state is None or path not in ctx.state.files():
        return None
    return ctx.state.values.get(name)


def _valid_python(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(v, str) and v in KNOWN_PYTHONS for v in value)


def _command(ctx: _Context, shared: _Workflows, name: str) -> tuple[str, str]:
    """The SWERepo command for one workflow: its recorded one (a valid one; P4-F03), unless none was recorded or
    `--with-governance` asks for one where there was none."""
    recorded = ctx.state.values.get(name) if ctx.state else None
    if ci.valid_swerepo_command(recorded) and (recorded or not shared.with_governance):
        return str(recorded), ("" if recorded else shared.swerepo_note)
    return shared.swerepo, shared.swerepo_note


def _rewrite_if_asked(ctx: _Context, action: Action, render: tuple[str, str], asked: bool) -> Action:
    """A managed file whose render changed because the person asked for it in this run (`--projects`,
    `--with-governance`) is rewritten, if SWERepo wrote it and nobody changed it since (review P4-F02). Anything
    else stays `outdated` for `update` (Phase 6)."""
    record = ctx.state.files().get(action.path or "") if ctx.state else None
    if not asked or action.verb != OUTDATED or record is None:
        return action
    template_id, text = render
    rendered = file_fingerprint(text, template_id)
    note = "unchanged since SWERepo wrote it: rewritten with what you asked for"
    return Action(action.component, REWRITE, action.path, note, content=text,
                  record=Record(template_id, rendered, rendered), kind="file", expect=record.written)  # fmt: skip


def _rewrite_block_if_asked(ctx: _Context, action: Action, render: tuple[str, str], asked: bool) -> Action:
    """SWERepo's block, rewritten in place when the person asked for its new content in this run (`--code-owner`)
    and nobody changed the block since SWERepo wrote it (review P5-F10). Anything else stays as it is."""
    record = ctx.state.blocks().get(action.path or "") if ctx.state else None
    if not asked or action.verb != OUTDATED or record is None:
        return action
    template_id, content = render
    rendered = fingerprint(content)
    note = "SWERepo block unchanged since it was written: rewritten with what you asked for"
    return Action(action.component, REWRITE, action.path, note, content=content,
                  record=Record(template_id, rendered, rendered), kind="block", expect=record.written)  # fmt: skip


WRITTEN = (CREATE, REWRITE, CURRENT)  # a workflow's recorded inputs match it after this run


@dataclass
class _CiResult:
    actions: list[Action]
    inputs: ci.Inputs | None  # None: no workflow can be written yet
    written: bool  # the workflow is created, rewritten or current: its inputs may be recorded


def _lint_mode(ctx: _Context, choice: str | None) -> tuple[str, list[str], bool]:
    """(mode, kept linters, whether the person has a choice to make) for the root project (spec §6.3). Recorded
    choices are used again; kept linters only if standard 1 knows how to run them (P4-F03)."""
    recorded = ctx.state.values.get("lint") if ctx.state else None
    adopted = [str(n) for n in (ctx.state.adopted.get("linters") or []) if n in ci.KEPT_LINT] if ctx.state else []
    if recorded in ("ruff", "gradual"):
        return str(recorded), [], False
    if adopted:
        return "kept", adopted, False
    names = {linter.name for linter in ctx.detection.linters}
    others = sorted(name for name in names if name in ci.KEPT_LINT)
    if "ruff" in names or not others:
        return "ruff", [], False
    mode = "gradual" if choice == "gradual" else "kept"
    return mode, others if mode == "kept" else [], True


def _toml_problem(text: str, content: str, path: str, ruff: bool, pytest: bool) -> str | None:
    """Why SWERepo's settings block can't be added to this pyproject.toml, or None: the result must be valid TOML
    holding every one of the person's values unchanged (ADR-20261122-4a06 point 8)."""
    try:
        before = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return "isn't valid TOML: fix it, then run init again"
    try:
        after = tomllib.loads(append_block(text, content, path))
    except tomllib.TOMLDecodeError:
        return "SWERepo's [tool.ruff] or [tool.pytest] settings would clash with its own: add them yourself"
    tool = after.get("tool", {})
    if ruff:
        tool.pop("ruff", None)
    if pytest and isinstance(tool.get("pytest"), dict):
        tool["pytest"].pop("ini_options", None)
        if not tool["pytest"] and "pytest" not in before.get("tool", {}):
            tool.pop("pytest")
    if not tool and "tool" not in before:
        after.pop("tool", None)
    return None if after == before else "SWERepo's settings would change its values: add them yourself"


def _settings(ctx: _Context, folder: str, lint: str) -> Action:
    """SWERepo's ruff and pytest settings, as a marked block at the end of the project's pyproject.toml."""
    c = "ci"
    path = "pyproject.toml" if folder == "." else f"{folder}/pyproject.toml"
    ruff = lint in ("ruff", "gradual") and not ci.ruff_configured(ctx.root, folder)
    pytest = not ci.pytest_configured(ctx.root, folder)
    length = ci.line_length(ctx.root, folder) if lint == "gradual" else None
    render = ci.settings_block(ctx.store, ruff=ruff, pytest=pytest, ruff_line_length=length)
    if render is None:
        return Action(c, KEEP, path, "ruff and pytest settings: yours")
    action = _managed_block(ctx, c, path, render[0], render=render)
    if action.verb == ADD_BLOCK:
        problem = _toml_problem(ctx.read(path), action.content or "", path, ruff, pytest)
        if problem:
            return Action(c, KEEP, path, problem)
    if action.verb in (ADD_BLOCK, CREATE):
        tables = [name for name, on in (("[tool.ruff]", ruff), ("[tool.pytest.ini_options]", pytest)) if on]
        action.note = ", ".join(tables)
    return action


def _missing_tools(ctx: _Context, folder: str, lint: str, linters: list[str]) -> str:
    """A note naming the tools a project's jobs run that `uv sync` there won't install, or ""."""
    needed = ["pytest", *(["ruff"] if lint in ("ruff", "gradual") else linters)]
    missing = [name for name in needed if name not in ci.installed_dependencies(ctx.root, folder)]
    if not missing:
        return ""
    where = "the project's" if folder == "." else f"{folder}/'s"
    run = "" if folder == "." else f" in {folder}"
    return f"not among {where} installed dependencies: {', '.join(missing)} (uv add --dev {' '.join(missing)}{run})"


def _project_inputs(ctx: _Context, folders: list[str]) -> tuple[list[Action], list[ci.Project]]:
    """Jobs and settings for the Python projects listed with `--projects` (spec §11). A project's recorded inputs
    are used while the workflow is recorded, so its jobs rebuild as written (review: Copilot on PR #8)."""
    actions: list[Action] = []
    projects: list[ci.Project] = []
    recorded = ctx.state.project_inputs if ctx.state and standard.CI_WORKFLOW in ctx.state.files() else {}
    for folder in folders:
        project = ci.Project.from_inputs(folder, recorded[folder]) if folder in recorded else None
        if project is None:
            install, note = ci.install_command(ctx.root, folder)
            found = detect(ctx.root / folder)
            python, python_note = ci.python_versions(found)
            if install is None or not python:
                actions.append(Action("ci", NOTE, None, f"{folder}/ gets no jobs: {note or python_note}"))
                continue
            names = {linter.name for linter in found.linters}
            others = sorted(name for name in names if name in ci.KEPT_LINT)
            # the project's own choice: a root [tool.ruff] doesn't make a black project a ruff one (P4-F04)
            own_ruff = "ruff" in names or ci.ruff_configured(ctx.root, folder, inherit=False)
            lint = "ruff" if own_ruff or not others else "kept"
            project = ci.Project(folder, install, python, lint, others if lint == "kept" else [])
            note = _missing_tools(ctx, folder, project.lint, project.linters)  # each project installs on its own
            if note:
                actions.append(Action("ci", NOTE, None, note))
        projects.append(project)
        actions.append(_settings(ctx, folder, project.lint))
    return actions, projects


def _listed_projects(ctx: _Context, projects: list[str] | None) -> list[str]:
    """`--projects`, else `[projects] listed`: each a repository folder with a pyproject.toml (spec §11)."""
    folders = projects if projects is not None else (ctx.state.projects_listed if ctx.state else [])
    checked: list[str] = []
    for given in folders:
        folder = given.strip().strip("/")
        if not ci.valid_folder(folder):
            raise UsageError("--projects: each project is a folder inside the repository, written with '/'")
        if not inside(ctx.root, ctx.root / folder) or not (ctx.root / folder / "pyproject.toml").is_file():
            raise UsageError(f"--projects: {folder} has no pyproject.toml")
        if folder not in checked:
            checked.append(folder)
    jobs = [ci.Project(f, "", []).job for f in checked]
    if len(set(jobs)) != len(jobs):
        raise UsageError("--projects: two folders would give jobs the same name")
    for folder, job in zip(checked, jobs, strict=True):
        taken = {f"lint-{job}", f"test-{job}"} & ci.FIXED_JOBS  # `macos` would make a second test-macos
        if taken:
            raise UsageError(f"--projects: {folder} would give a job the name {', '.join(sorted(taken))}, "
                             "which swerepo-ci.yml already uses")  # fmt: skip
    return checked


def _coverage_notes(ctx: _Context, listed: list[str]) -> list[Action]:
    """Every project root no SWERepo job covers, named (spec §11)."""
    skipped = set(ctx.state.projects_not_covered) if ctx.state else set()
    notes = []
    for project in ctx.detection.projects:
        if project.path == "." or project.path in listed or project.path in skipped:
            continue
        if project.kind == "python":
            how = f"--projects {project.path} gives it jobs"
        else:
            how = f"a {project.kind} project: require its own workflow's checks (github, Phase 5)"
        notes.append(Action("ci", NOTE, None, f"{project.path}/ isn't covered by ci-ok: {how}, or list it "
                                              "under [projects] not_covered"))  # fmt: skip
    return notes


def _ci(
    ctx: _Context,
    shared: _Workflows,
    lint_mode: tuple[str, list[str]],
    projects: list[str] | None,
    copilot: bool = False,
    *,
    asked: bool = False,
) -> _CiResult:
    """`asked`: the github component runs now, so its Copilot wait may rewrite an unchanged workflow."""
    c = "ci"
    actions: list[Action] = []
    install, install_note = ci.install_command(ctx.root)
    recorded_python = _recorded(ctx, standard.CI_WORKFLOW, "python")
    python = [str(v) for v in recorded_python] if _valid_python(recorded_python) else shared.python  # type: ignore[union-attr]
    python_note = "" if python is not shared.python else shared.python_note
    if install is None or not python:
        reason = install_note or python_note
        actions.append(Action(c, NOTE, None, f"{standard.CI_WORKFLOW} not written: {reason}"))
        return _CiResult(actions, None, False)
    recorded_install = _recorded(ctx, standard.CI_WORKFLOW, "ci_install")
    if recorded_install in ci.INSTALLS:  # only the commands standard 1 writes (P4-F03)
        install = str(recorded_install)
    lint, linters = lint_mode
    recorded_copilot = _recorded(ctx, standard.CI_WORKFLOW, "ci_copilot_review")
    recorded_wait = recorded_copilot == "true"  # a version 1 workflow recorded none: it doesn't wait
    if not asked and recorded_copilot in ("true", "false"):  # its own recorded flag: renders stay the recorded ones
        copilot = recorded_wait
    # the github component asks for a rewrite only when the wait itself changes (review P5-F12)
    asked = asked and (copilot != recorded_wait or standard.CI_WORKFLOW not in (ctx.state.files() if ctx.state else {}))
    listed = _listed_projects(ctx, projects)
    project_actions, project_inputs = _project_inputs(ctx, listed)
    seamspec = ci.seamspec_pin(ctx.state.tools.get("seamspec") if ctx.state else None)
    governance, governance_note = _command(ctx, shared, "governance_command")
    inputs = ci.Inputs(shared.default_branch, install, python, lint, linters, governance, seamspec,
                       project_inputs, copilot)  # fmt: skip
    versions = f"{python[0]}–{python[-1]}" if len(python) > 1 else python[0]
    render = ci.render_workflow(ctx.store, inputs)
    workflow = _managed_file(ctx, c, standard.CI_WORKFLOW, ci.WORKFLOW, render=render)
    workflow = _rewrite_if_asked(ctx, workflow, render, projects is not None or shared.with_governance or asked)
    if workflow.verb == CREATE:
        how = {"ruff": "ruff", "kept": ", ".join(linters) + " (kept)", "gradual": "ruff on changed files"}[lint]
        workflow.note = f"Python {versions}; lint: {how}"
    elif workflow.verb in (OUTDATED, CHANGED) and (projects is not None or shared.with_governance):
        workflow.note += "; what you asked for (--projects, --with-governance) waits for it"
    actions.append(workflow)
    actions.append(_settings(ctx, ".", lint))
    actions += project_actions
    for note in (python_note, f"governance job: {governance_note}" if governance_note else ""):
        if note:
            actions.append(Action(c, NOTE, None, note))
    missing = _missing_tools(ctx, ".", lint, linters)
    if missing and workflow.verb == CREATE:
        actions.append(Action(c, NOTE, None, missing))
    others = [w.path for w in ctx.detection.workflows if w.path != standard.CI_WORKFLOW]
    if workflow.verb == CREATE:  # the gap PR #9 found (ADR-20261123-4e40 point 8)
        note = "dependency-review needs GitHub's dependency graph turned on (Settings → Advanced Security)"
        actions.append(Action(c, NOTE, None, note))
    if others and workflow.verb == CREATE:
        audit = "uvx zizmor==1.32.0 --offline .github/workflows"
        note = f"workflow-audit also audits {', '.join(others)}: run `{audit}` before merging"
        actions.append(Action(c, NOTE, None, note))
    actions += _coverage_notes(ctx, listed)
    return _CiResult(actions, inputs, workflow.verb in WRITTEN)


CONTACTS = ("github", "placeholder")  # or an email address the person types
_CONTACT_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def has_github_remote(root: Path) -> bool:
    """Whether `origin` is on github.com itself (the same anchored test as the github component; P5-F06)."""
    return github.repository(root) is not None


def contact_text(contact: str) -> str:
    """The reporting paragraph of SECURITY.md (ADR-20261122-a48e point 1)."""
    if contact == "github":
        return (
            "Please report it privately through GitHub: on this repository's **Security** tab, choose "
            "**Report a vulnerability**."
        )
    if _CONTACT_EMAIL.fullmatch(contact):
        return f"Please email {contact}."
    return (
        "_How to report a vulnerability privately is still to be decided: give an email address here, or turn on "
        "GitHub's private vulnerability reporting and point to it._"
    )


def _security(ctx: _Context, shared: _Workflows, contact: str | None) -> tuple[list[Action], tuple[str, str] | None]:
    """The component's actions, and the privacy workflow's SWERepo command and Python version when it is created,
    rewritten or current (to record), else None."""
    c = "security"
    actions: list[Action] = []
    policy = ctx.detection.documents.get("security")
    if policy or ctx.exists("SECURITY.md"):
        actions.append(Action(c, KEEP, policy or "SECURITY.md", "yours"))
    else:
        chosen = contact or ("github" if has_github_remote(ctx.root) else "placeholder")
        action = _starter(ctx, c, "SECURITY.md", "security/policy", {**ctx.values, "contact": contact_text(chosen)})
        actions.append(action)
        if action.verb == CREATE and chosen == "github":
            note = "turn on GitHub's private vulnerability reporting in the repository's security settings"
            actions.append(Action(c, NOTE, None, note))
    command, note = _command(ctx, shared, "privacy_command")
    written: tuple[str, str] | None = None
    if command:
        template = ctx.store.latest("security", "privacy-workflow")
        recorded_python = _recorded(ctx, standard.PRIVACY_WORKFLOW, "privacy_python")
        main = str(recorded_python) if recorded_python in KNOWN_PYTHONS else (shared.python or ci.DEFAULT_PYTHONS)[-1]
        values = {"default_branch": shared.default_branch, "python_main": main, "swerepo": command}
        render = (template.id, template.render(values))
        workflow = _managed_file(ctx, c, standard.PRIVACY_WORKFLOW, "security/privacy-workflow", render=render)
        workflow = _rewrite_if_asked(ctx, workflow, render, shared.with_governance)
        actions.append(workflow)
        written = (command, main) if workflow.verb in WRITTEN else None
    else:
        actions.append(Action(c, NOTE, None, f"{standard.PRIVACY_WORKFLOW} not written: {note}"))
    actions.append(_managed_block(ctx, c, ".gitignore", "security/gitignore"))
    hits = privacy.scan(ctx.root, ctx.state.privacy_allow_paths if ctx.state else [])
    if hits:
        message = f"privacy scan: {privacy.summary(hits)}: fix them before committing"
    else:
        message = "privacy scan: nothing found"
    actions.append(Action(c, NOTE, None, message))
    return actions, written


# --- github (ADR-20261123-4e40) --------------------------------------------------------------------------


MODE_MEANING = {
    "solo": "pull requests only, ci-ok required, Copilot review, threads resolved; no approval needed",
    "team": "solo's rules, plus one approval, stale approvals dismissed and code-owner review",
}


@dataclass
class _GitHubChoice:
    settings: github.Settings
    hub: github.GitHub | None
    ask_mode: bool  # neither given nor recorded: a terminal asks, with `settings.mode` as the default
    ask_owner: bool  # likewise for the code owner, with `settings.code_owner` (or none) as the default
    owner_none: bool = False  # the person said "none": no CODEOWNERS, and the repository owner isn't proposed
    owner_given: bool = False  # --code-owner (or its question) answered in this run


def _github_choice(
    ctx: _Context, mode: str | None, code_owner: str | None, copilot_review: bool | None
) -> _GitHubChoice:
    """The mode, code owner and Copilot review: given now, else recorded, else the defaults (spec §12)."""
    state = ctx.state
    hub = github.GitHub.connect(ctx.root)
    owner_login, owner_type = ("", "")
    if hub is not None:
        try:
            owner_login, owner_type = hub.owner_login()
        except github.GitHubError:
            hub = None
    recorded_mode = state.mode if state else None
    chosen = mode or recorded_mode or ("team" if owner_type == "Organization" else "solo")
    if chosen not in ("solo", "team"):
        raise UsageError(f"--mode {chosen}: solo or team")
    if code_owner is not None and code_owner != github.NO_OWNER and not github.valid_owner(code_owner):
        raise UsageError("--code-owner: a GitHub @login or @org/team, or none")
    recorded_owner = state.values.get("code_owner") if state else None
    given = code_owner if code_owner is not None else recorded_owner
    owner_none = given == github.NO_OWNER  # said once, kept: never replaced by the repository owner (P5-F04)
    owner = given if github.valid_owner(given) else None
    if owner is None and not owner_none and owner_type == "User" and github.valid_owner(f"@{owner_login}"):
        owner = f"@{owner_login}"
    recorded_copilot = state.github.get("copilot_review") if state else None
    copilot = copilot_review if copilot_review is not None else recorded_copilot is not False
    extra = tuple(str(c) for c in (state.github.get("extra_required_checks") or [])) if state else ()
    ask_mode = mode is None and recorded_mode is None
    ask_owner = code_owner is None and recorded_owner is None
    settings = github.Settings(chosen, owner, copilot, extra)
    return _GitHubChoice(settings, hub, ask_mode, ask_owner, owner_none, code_owner is not None)


@dataclass
class _SettingsFiles:
    """`ruleset.json` and `repo-settings.json` as this run leaves them, decided before the CI workflow so the
    workflow follows the ruleset (review P5-F10)."""

    actions: list[Action]
    rendered: dict[str, dict[str, Any] | None]  # what is applied: the committed file, or this run's build
    ruleset_verb: str  # CREATE, REWRITE or CURRENT: the ruleset holds this run's settings
    refused: set[str] = field(default_factory=set)  # files read but never applied (github.not_applicable)

    @property
    def applicable(self) -> dict[str, dict[str, Any] | None]:
        """What may be sent to GitHub: the rendered files, without the refused ones."""
        return {name: None if name in self.refused else data for name, data in self.rendered.items()}

    @property
    def copilot_review(self) -> bool | None:
        ruleset = self.rendered.get("ruleset")
        return github.has_copilot_review(ruleset) if isinstance(ruleset, dict) else None

    @property
    def mode(self) -> str | None:
        """The mode the ruleset applied in this run is in (review P5-F14)."""
        ruleset = self.rendered.get("ruleset")
        return github.ruleset_mode(ruleset) if isinstance(ruleset, dict) else None


def _settings_files(ctx: _Context, choice: _GitHubChoice, explicit: bool) -> _SettingsFiles:
    """The settings files: created when missing; an unchanged ruleset.json SWERepo wrote is rewritten when the person
    gives --mode, --code-owner or --copilot-review in this run (review P5-F10); otherwise the committed file is the
    source of truth and is what gets applied (P5-F02)."""
    c, actions = "github", []
    rendered: dict[str, dict[str, Any] | None] = {}
    refused: set[str] = set()
    ruleset_verb = KEEP
    for name, path in (("ruleset", github.RULESET_FILE), ("repo-settings", github.SETTINGS_FILE)):
        render = github.render(name, choice.settings)
        action = _managed_file(ctx, c, path, render[0], render=render)
        if name == "ruleset":
            action = _rewrite_if_asked(ctx, action, render, explicit)
            ruleset_verb = action.verb
            if action.verb in (CHANGED, KEEP, OUTDATED) and explicit:
                action.note += "; what you gave (--mode, --code-owner, --copilot-review) isn't in it: edit it yourself"
        actions.append(action)
        if action.verb in (CREATE, REWRITE):
            rendered[name] = json.loads(render[1])
        else:
            try:
                committed = json.loads(ctx.read(path)) if ctx.exists(path) else None
            except json.JSONDecodeError:
                committed = None
            rendered[name] = committed if isinstance(committed, dict) else None
            if rendered[name] is None:
                actions.append(Action(c, NOTE, None, f"{path} isn't a JSON object: nothing applied from it"))
            elif problem := github.not_applicable(name, rendered[name]):
                refused.add(name)  # never sent: a renamed ruleset, or settings beyond merging (PR #10 review)
                actions.append(Action(c, NOTE, None, f"{path}: {problem}: nothing applied from it"))
    return _SettingsFiles(actions, rendered, ruleset_verb, refused)


def _github(ctx: _Context, choice: _GitHubChoice, plan: Plan, files: _SettingsFiles) -> list[Action]:
    c, settings = "github", choice.settings
    shown = files.mode if files.ruleset_verb not in (CREATE, REWRITE) and files.mode else settings.mode
    source = " (from the committed ruleset.json)" if shown != settings.mode or files.ruleset_verb == KEEP else ""
    note = f"mode: {shown} ({MODE_MEANING[shown]}){source}"
    actions = [Action(c, NOTE, None, note), *files.actions]
    rendered = files.applicable
    instructions = ".github/copilot-instructions.md"
    if ctx.exists(instructions) and not (ctx.state and instructions in ctx.state.files()):
        actions.append(_managed_block(ctx, c, instructions, "github/copilot-instructions"))
    else:
        actions.append(_managed_file(ctx, c, instructions, "github/copilot-instructions"))
    ecosystem = "uv" if (ctx.root / "uv.lock").is_file() else "pip"
    dependabot = ctx.store.latest("github", "dependabot")
    render = (dependabot.id, dependabot.render({"python_ecosystem": ecosystem}))
    actions.append(_managed_file(ctx, c, ".github/dependabot.yml", "github/dependabot", render=render))
    existing_template = ctx.detection.documents.get("pr_template")
    if existing_template and not (ctx.state and existing_template in ctx.state.files()):  # SWERepo's own: compared
        actions.append(Action(c, KEEP, existing_template, "yours"))
    else:
        test = ctx.values.get("test_lines", "uv run pytest").splitlines()[0]
        values = {**ctx.values, "test_command": test}
        template = ctx.store.latest("github", "pr-template")
        render = (template.id, template.render(values))
        actions.append(_managed_file(ctx, c, ".github/pull_request_template.md", "github/pr-template", render=render))
    if any(p.is_file() for p in (ctx.root / ".github/ISSUE_TEMPLATE").glob("*")):
        actions.append(Action(c, KEEP, ".github/ISSUE_TEMPLATE", "yours"))
    else:
        for name, kind in (("bug", "issue-bug"), ("feature", "issue-feature")):
            actions.append(_starter(ctx, c, f".github/ISSUE_TEMPLATE/{name}.md", f"github/{kind}", ctx.values))
    if settings.code_owner:
        path = ctx.detection.documents.get("codeowners") or github.CODEOWNERS
        template = ctx.store.latest("github", "codeowners")
        lines = github.codeowners_lines(settings.code_owner, openspec=ctx.detection.openspec)
        render = (template.id, template.render({"lines": lines}))
        block = _managed_block(ctx, c, path, "github/codeowners", render=render)
        block = _rewrite_block_if_asked(ctx, block, render, choice.owner_given)
        if block.verb in (CHANGED, KEEP, OUTDATED) and choice.owner_given:
            block.note += "; the code owner you gave isn't in it: edit it yourself"
        actions.append(block)
    elif choice.owner_none:
        actions.append(Action(c, NOTE, None, "CODEOWNERS not written: no code owner, as you chose"))
    else:
        note = "CODEOWNERS not written: name the code owner (--code-owner @login or @org/team)"
        actions.append(Action(c, NOTE, None, note))
    actions += _github_apply(ctx, choice, rendered, plan)
    return actions


def _github_apply(
    ctx: _Context, choice: _GitHubChoice, rendered: dict[str, dict[str, Any] | None], plan: Plan
) -> list[Action]:
    """The ruleset and merge settings to apply through gh, compared with what GitHub has now (read-only)."""
    c, hub = "github", choice.hub
    plan.github_remote = hub.slug if hub is not None else github.repository(ctx.root)
    if hub is None:
        if plan.github_remote is None:
            note = "ruleset and merge settings: waiting: no GitHub repository yet"
        else:  # on GitHub, but gh is missing or not logged in (PR #10 review)
            note = "ruleset and merge settings: waiting: gh isn't installed or logged in (gh auth login)"
        return [Action(c, WAITING, None, note)]
    plan.github_slug = hub.slug
    actions = []
    try:
        live_ruleset = hub.find_ruleset()
        live_repo = hub.repo()
    except github.GitHubError as error:
        return [Action(c, NOTE, None, f"can't read GitHub's settings ({error}): nothing applied")]
    wanted, settings = rendered["ruleset"], rendered["repo-settings"]
    plan.github_compared = wanted is not None and settings is not None
    if wanted is None:
        ruleset_changes = []
    else:
        ruleset_changes = github.ruleset_differences(wanted, live_ruleset) if live_ruleset else ["new"]
    if ruleset_changes and wanted is not None:
        plan.github_apply["ruleset"] = wanted
        what = "create" if live_ruleset is None else "update: " + ", ".join(github.ruleset_changes(ruleset_changes))
        actions.append(Action(c, APPLY, None, f'ruleset "{github.RULESET_NAME}" on the default branch ({what})'))
    else:
        actions.append(Action(c, CURRENT, None, f'ruleset "{github.RULESET_NAME}" on GitHub'))
    settings_changes = github.settings_differences(settings, live_repo) if settings is not None else []
    if settings_changes and settings is not None:
        plan.github_apply["settings"] = settings
        actions.append(Action(c, APPLY, None, "merge settings (" + ", ".join(settings_changes) + ")"))
    elif settings is not None:
        actions.append(Action(c, CURRENT, None, "merge settings on GitHub"))
    try:
        graph = live_repo.get("private") is True or hub.dependency_graph()
    except github.GitHubError:
        graph = True  # can't tell: check says so; the plan doesn't guess
    if not graph:
        note = "GitHub's dependency graph is off: dependency-review needs it (Settings → Advanced Security)"
        actions.append(Action(c, NOTE, None, note))
    return actions


def apply_github(plan: Plan, root: Path, which: list[str]) -> list[str]:
    """Apply the GitHub settings the person said yes to ("ruleset", "settings"), then record
    `[github] applied` when nothing is left to apply. Returns what was done, one line each."""
    hub = github.GitHub.connect(root)
    if hub is None or hub.slug != plan.github_slug:
        raise InitError("GitHub isn't reachable as it was when the plan was made: nothing applied; run init again")
    done = []
    try:
        if "ruleset" in which and "ruleset" in plan.github_apply:
            how = hub.apply_ruleset(plan.github_apply["ruleset"])
            done.append(f'ruleset "{github.RULESET_NAME}" {how}')
        if "settings" in which and "settings" in plan.github_apply:
            hub.apply_settings(plan.github_apply["settings"])
            done.append("merge settings applied")
    except github.GitHubError as error:
        raise InitError(f"GitHub: {error}") from error
    if plan.github_compared and set(plan.github_apply) <= set(which):  # both files compared, all applied
        state = State.load(root.resolve())
        if state is not None and state.github.get("applied") is not True:
            state.set_github("applied", True)
            state.save(root.resolve())
    return done


def _has_commits(root: Path) -> bool:
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", "HEAD"],
            capture_output=True, check=False, timeout=60,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def make_plan(
    root: Path,
    *,
    only: list[str] | None = None,
    skip: list[str] | tuple[str, ...] = (),
    hosts: list[str] | None = None,
    store: TemplateStore | None = None,
    today: datetime.date | None = None,
    with_governance: bool = False,
    projects: list[str] | None = None,
    lint: str | None = None,
    contact: str | None = None,
    mode: str | None = None,
    code_owner: str | None = None,
    copilot_review: bool | None = None,
) -> Plan:
    """What `swerepo init` would do. Writes nothing. `lint`: "kept" or "gradual" when other linters are found
    (spec §6.3); `contact`: "github", "placeholder" or an email address for SECURITY.md (ADR-20261122-a48e)."""
    components = resolve_components(only, skip)
    if projects is not None and "ci" not in components:
        raise UsageError("--projects gives Python projects their own CI jobs: it needs the ci component")
    if lint is not None and lint not in ("kept", "gradual"):
        raise UsageError(f"lint choice {lint!r}: kept or gradual")
    unknown_hosts = [h for h in hosts or [] if h not in HOSTS]
    if unknown_hosts:
        raise UsageError(f"unknown editor {', '.join(unknown_hosts)} (known: {', '.join(HOSTS)})")
    root = root.resolve()
    if not root.is_dir():
        raise UsageError(f"{root.name}: not a folder")
    try:
        state = State.load(root)
    except StateError as error:
        raise InitError(f"{error}. Fix or remove it first.") from error
    newer = state.written_by_newer() if state else None
    if newer:
        raise InitError(f"{FILE_NAME}: {newer}. Upgrade SWERepo.")
    detection = detect(root, ignore=state.project_ignore if state else ())
    if not detection.git.is_work_tree and detection.git.nested_repos:
        names = ", ".join(detection.git.nested_repos)
        raise InitError(f"this folder holds other repositories ({names}): run init in one of them")
    if detection.git.is_work_tree and not detection.git.is_toplevel:
        raise InitError("this folder is inside a git repository: run init at the repository's top level (spec §11)")

    recorded = state.values if state else {}
    ctx = _Context(root, detection, state, store or TemplateStore(), {}, today or datetime.date.today())
    adr_dir, adopted = _adr_dir(ctx)
    progress_dir = str((state.adopted.get("progress_dir") if state else None) or standard.PROGRESS_DIR)
    # The lint choice first, so the commands the agents block lists match the CI it gets (P4-F07).
    lint_mode, kept, lint_question = _lint_mode(ctx, lint)
    computed = compute_values(root, detection, adr_dir, progress_dir, kept, lint_mode)
    ctx.values = {**computed, **{k: str(recorded[k]) for k in RECORDED_VALUES if isinstance(recorded.get(k), str)}}

    hosts_recorded = bool(state and state.hosts_chosen)
    chosen_hosts = hosts if hosts is not None else (state.hosts if hosts_recorded else list(detection.hosts))
    plan = Plan(root.name, components, chosen_hosts, hosts_recorded or hosts is not None)
    plan.state_before = _state_text(root)

    if not detection.git.is_work_tree:
        plan.actions.append(Action("repository", GIT_INIT, None, "not a git repository yet: git init"))
    choice = _github_choice(ctx, mode, code_owner, copilot_review) if "github" in components else None
    # Merges wait for Copilot's review where the github component turns it on (ADR-20261123-a359). Applying
    # github alone also brings a recorded, unchanged swerepo-ci.yml along (review P5-F01).
    explicit = mode is not None or code_owner is not None or copilot_review is not None
    files = _settings_files(ctx, choice, explicit) if choice is not None else None
    if choice is not None and files is not None:
        if choice.ask_mode:  # a kept ruleset's own mode is the default, not the owner-type guess (P5-F14)
            from_file = files.ruleset_verb not in (CREATE, REWRITE) and files.mode is not None
            plan.github_ask["mode"] = files.mode if from_file and files.mode else choice.settings.mode
        if choice.ask_owner:
            plan.github_ask["code_owner"] = choice.settings.code_owner or github.NO_OWNER
        plan.github_question = bool(plan.github_ask)
    if files is not None and files.copilot_review is not None:
        copilot = files.copilot_review  # the ruleset the repository commits decides (P5-F10)
    elif choice is not None:
        copilot = choice.settings.copilot_review
    else:
        copilot = bool(state and state.github.get("copilot_review"))
    ci_along = (choice is not None and "ci" not in components and "ci" not in skip
                and state is not None and "ci" in state.components)  # fmt: skip
    if ci_along:
        components = [c for c in COMPONENTS if c in {*components, "ci"}]
    shared = _workflows(ctx, with_governance=with_governance) if {"ci", "security"} & set(components) else None
    ci_result: _CiResult | None = None
    privacy: tuple[str, str] | None = None  # the privacy workflow's command and Python version, when written
    for component in components:
        if component == "ci" and shared is not None:
            ci_result = _ci(ctx, shared, (lint_mode, kept), projects, copilot, asked=choice is not None)
            plan.actions += ci_result.actions
            plan.lint_question = lint_question and ci_result.inputs is not None
        elif component == "security" and shared is not None:
            security_actions, privacy = _security(ctx, shared, contact)
            plan.actions += security_actions
            plan.contact_question = any(a.path == "SECURITY.md" and a.verb == CREATE for a in plan.actions)
        elif component == "github" and choice is not None and files is not None:
            plan.actions += _github(ctx, choice, plan, files)
        elif component == "docs":
            plan.actions += _docs(ctx, adr_dir, adopted)
        elif component == "agents":
            plan.actions += _agents(ctx, chosen_hosts)
            if isinstance(recorded.get("commands"), str) and recorded["commands"] != computed["commands"]:
                note = "the project's commands changed since they were recorded: `swerepo update` (Phase 6)"
                plan.actions.append(Action("agents", NOTE, None, note))
        else:
            plan.actions.append(Action(component, LATER_VERB, None, f"init adds it from Phase {LATER[component]}"))

    # A component counts as applied when init could write it: ci without a workflow isn't recorded as chosen.
    applied = [
        c for c in components if c in AVAILABLE and not (c == "ci" and (ci_result is None or not ci_result.inputs))
    ]
    plan.state_text = _new_state(ctx, plan, applied, adr_dir if adopted else None, shared, ci_result, privacy, choice,
                                 files)  # fmt: skip
    if "docs" in applied and any(a.changes for a in plan.actions):  # writing .swerepo.toml counts
        _progress_entry(ctx, plan, applied, progress_dir)
    return plan


def _progress_entry(ctx: _Context, plan: Plan, applied: list[str], progress_dir: str) -> None:
    """The progress entry for the pull request that adds SWERepo, so its own PR rule passes (spec §6.5)."""
    path = f"{progress_dir}/{ctx.today:%Y%m%d}-swerepo-init.md"
    created = [a.path for a in plan.actions if a.verb == CREATE and a.path]
    blocks = [a.path for a in plan.actions if a.verb == ADD_BLOCK and a.path]
    parts = []
    if created:
        parts.append("created " + ", ".join(f"`{p}`" for p in [*created, path]))
    if blocks:
        parts.append("added SWERepo's block to " + ", ".join(f"`{p}`" for p in blocks))
    values = {**ctx.values, "date": f"{ctx.today:%Y-%m-%d}", "components": ", ".join(applied)}
    values["summary"] = "; ".join(parts) or "recorded the components in `.swerepo.toml`"
    plan.actions.append(_starter(ctx, "docs", path, "docs/progress-entry", values))


def _new_state(
    ctx: _Context,
    plan: Plan,
    applied: list[str],
    adopted_adr_dir: str | None,
    shared: _Workflows | None = None,
    ci_result: _CiResult | None = None,
    privacy: tuple[str, str] | None = None,
    choice: _GitHubChoice | None = None,
    files: _SettingsFiles | None = None,
) -> str | None:
    """The `.swerepo.toml` after this run, or None when it wouldn't change. A workflow's inputs are recorded only
    when it is created, rewritten or current, so they always rebuild what was written (P4-F02)."""
    if not applied:
        return None
    before = ctx.state.dumps() if ctx.state else None
    state = State.parse(before) if before is not None else State.new()
    state.set_components([c for c in COMPONENTS if c in {*state.components, *applied}])
    for name in RECORDED_VALUES:
        if state.values.get(name) != ctx.values[name]:
            state.set_value(name, ctx.values[name])
    if "agents" in applied and (not state.hosts_chosen or state.hosts != plan.hosts):
        state.set_hosts(plan.hosts)
    if adopted_adr_dir and state.adopted.get("adr_dir") != adopted_adr_dir:
        state.set_adopted("adr_dir", adopted_adr_dir)
    inputs = ci_result.inputs if ci_result and ci_result.written else None
    values: dict[str, str | list[str]] = {}
    if shared is not None and (inputs is not None or privacy is not None):
        values["default_branch"] = shared.default_branch
    if privacy is not None:
        values.update(privacy_command=privacy[0], privacy_python=privacy[1])
    if inputs is not None:  # each workflow's own snapshot (review: Copilot on PR #8)
        values.update(python=inputs.python, ci_install=inputs.install, lint=inputs.lint,
                      governance_command=inputs.swerepo,
                      ci_copilot_review="true" if inputs.copilot_review else "false")  # fmt: skip
    for name, value in values.items():
        if state.values.get(name) != value:
            state.set_value(name, value)
    if inputs is not None:
        if inputs.lint == "kept" and state.adopted.get("linters") != inputs.linters:
            state.set_adopted_linters(inputs.linters)
        listed = [project.folder for project in inputs.projects]
        if listed != state.projects_listed and (listed or state.projects_listed):
            state.set_projects_listed(listed)
        project_inputs = {project.folder: project.inputs for project in inputs.projects}
        if project_inputs != state.project_inputs and (project_inputs or state.project_inputs):
            state.set_project_inputs(project_inputs)
        if state.tools.get("seamspec") != inputs.seamspec:
            state.set_tool("seamspec", inputs.seamspec)
    if choice is not None and "github" in applied:
        settings = choice.settings
        # The choices are recorded only where the files carry them: the mode and Copilot review when ruleset.json
        # was written with them (or nothing is recorded yet), the code owner when CODEOWNERS was. Copilot review is
        # what the committed ruleset says (review P5-F10).
        written = files is not None and files.ruleset_verb in (CREATE, REWRITE, CURRENT)
        mode_now = settings.mode if written else (files.mode if files is not None and files.mode else None)
        if mode_now is None and state.mode is None:
            mode_now = settings.mode
        if mode_now and state.mode != mode_now:
            state.set_mode(mode_now)
        owner = settings.code_owner or (github.NO_OWNER if choice.owner_none else None)
        path = ctx.detection.documents.get("codeowners") or github.CODEOWNERS  # by path: kind is set on writes only
        codeowners = [a for a in plan.actions if a.component == "github" and a.path == path]
        owner_written = not codeowners or codeowners[0].verb in (CREATE, ADD_BLOCK, CURRENT, REWRITE)
        if owner and state.values.get("code_owner") != owner and (owner_written or "code_owner" not in state.values):
            state.set_value("code_owner", owner)
        copilot = files.copilot_review if files is not None and files.copilot_review is not None else None
        if copilot is None:
            copilot = settings.copilot_review
        if state.github.get("copilot_review") != copilot:
            state.set_github("copilot_review", copilot)
        # applied: GitHub was read, both files were compared, and nothing is left to apply; kept as it was when
        # GitHub couldn't be read (P5-F02, PR #10 review); false when nothing is recorded yet
        if plan.github_compared is not None:
            applied_now = plan.github_compared and not plan.github_apply
        else:
            applied_now = state.github.get("applied", False)
        if state.github.get("applied") != applied_now:
            state.set_github("applied", applied_now)
    if ctx.state is None:  # spec §10: an existing repository starts with warn-only pull-request rules
        if _has_commits(ctx.root):
            state.set_pr_rules(enforce=False, warn_since=ctx.today)
        else:
            state.set_pr_rules(enforce=True)
    for action in plan.actions:
        if action.verb in (CREATE, ADD_BLOCK, REWRITE) and action.record is not None and action.path:
            (state.set_file if action.kind == "file" else state.set_block)(action.path, action.record)
    after = state.dumps()
    if after == before:
        return None
    plan.actions.append(Action("state", WRITE_STATE, FILE_NAME, "components: " + ", ".join(state.components)))
    return after


# --- applying -----------------------------------------------------------------------------------------


def _state_text(root: Path) -> str | None:
    """`.swerepo.toml` as it is now, or None when there is none."""
    path = root / FILE_NAME
    if not path.exists() and not path.is_symlink():
        return None
    try:
        return read_exact(path, errors="surrogateescape")
    except OSError as error:
        raise InitError(f"{FILE_NAME}: can't read it ({error.strerror or type(error).__name__})") from error


def _check_target(action: Action, root: Path) -> None:
    """One target, as it is now: inside the repository, its folders still folders, still missing (create) or
    still without a block, and with a block that can be found once added (add block)."""
    path = action.path or ""
    target = root / path
    if not inside(root, target):
        raise InitError(f"{path} leads out of the repository: nothing written")
    if action.verb == REWRITE:
        _check_unchanged(action, target)
        return
    if action.verb == CREATE:
        for folder in target.relative_to(root).parents:
            if folder != Path(".") and (root / folder).exists() and not (root / folder).is_dir():
                raise InitError(f"{folder.as_posix()} isn't a folder any more: nothing written; run init again")
        if target.exists() or target.is_symlink():
            raise InitError(f"{path} appeared since the plan was made: nothing written; run init again")
        return
    try:
        text = read_exact(target, errors="surrogateescape")
        found = find_block(text, style=comment_style(path))
    except OSError as error:
        raise InitError(f"{path}: can't read it ({error.strerror or type(error).__name__})") from error
    except BlockError as error:
        raise InitError(f"{path}: SWERepo block markers are broken ({error}); nothing written") from error
    if found is not None:
        raise InitError(f"{path} got a SWERepo block since the plan was made: nothing written; run init again")
    if not _block_findable(text, action.content or "", path):
        raise InitError(f"{path} ends inside an unclosed code fence: nothing written; close it, then run init again")


def _check_unchanged(action: Action, target: Path) -> None:
    """A file to rewrite must still be what SWERepo wrote: a person's edit since the plan stops the run."""
    try:
        text = read_exact(target, errors="surrogateescape")
    except OSError as error:
        raise InitError(f"{action.path}: can't read it ({error.strerror or type(error).__name__})") from error
    if action.kind == "block":
        try:
            block = find_block(text, style=comment_style(action.path or ""))
        except BlockError:
            block = None
        seen = fingerprint(block.content) if block is not None else None
    else:
        seen = file_fingerprint(text, action.record.template if action.record else "")
    if target.is_symlink() or seen != action.expect:
        raise InitError(f"{action.path} changed since the plan was made: nothing written; run init again")


def _check_targets(plan: Plan, root: Path) -> None:
    """Before anything is written: every target as `_check_target` wants it, and `.swerepo.toml` exactly as the
    plan read it (a person may edit it while init waits at `Apply?`). A conflict stops the run with nothing
    written, so no SWERepo content is left behind unrecorded and no one's edit is lost."""
    for action in plan.actions:
        if action.path is not None and action.verb in (CREATE, ADD_BLOCK, REWRITE):
            _check_target(action, root)
    if _state_text(root) != plan.state_before:
        raise InitError(f"{FILE_NAME} changed since the plan was made: nothing written; run init again")


def apply(plan: Plan, root: Path) -> None:
    """Write the plan. Every target is checked first, so a conflict writes nothing; each write checks again
    (exclusive creation, a re-read before a block), so a file that appears even then is never replaced."""
    root = root.resolve()
    _check_targets(plan, root)
    for action in plan.actions:
        if action.verb == GIT_INIT:
            try:  # the error names neither the folder nor git's output, which hold the absolute path
                done = subprocess.run(["git", "init", "-q", str(root)], check=False, capture_output=True, timeout=60)
            except (OSError, subprocess.SubprocessError) as error:
                reason = error.strerror if isinstance(error, OSError) and error.strerror else type(error).__name__
                raise InitError(f"git init failed ({reason})") from error
            if done.returncode != 0:
                raise InitError(f"git init failed (exit status {done.returncode})")
    for action in plan.actions:
        if action.verb not in (CREATE, ADD_BLOCK, REWRITE) or action.path is None or action.content is None:
            continue
        target = root / action.path
        if not inside(root, target):
            raise InitError(f"{action.path} leads out of the repository: run init again")
        try:
            if action.verb == CREATE:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("x", encoding="utf-8", newline="", errors="surrogateescape") as handle:
                    handle.write(action.content)
            elif action.verb == REWRITE:
                _check_unchanged(action, target)  # again, just before writing
                if action.kind == "block":  # only the block's lines change; the person's text stays byte for byte
                    text = read_exact(target, errors="surrogateescape")
                    style = comment_style(action.path)
                    updated = replace_block_content(text, action.content, style=style, marker="swerepo")
                    target.write_text(updated, encoding="utf-8", newline="", errors="surrogateescape")
                else:
                    target.write_text(action.content, encoding="utf-8", newline="")
            else:
                text = read_exact(target, errors="surrogateescape")
                try:
                    found = find_block(text, style=comment_style(action.path))
                except BlockError as error:
                    raise InitError(f"{action.path}: SWERepo block markers are broken ({error})") from error
                if found is not None:
                    raise InitError(f"{action.path} got a SWERepo block since the plan was made: run init again")
                if not _block_findable(text, action.content, action.path):
                    raise InitError(f"{action.path} ends inside an unclosed code fence: close it, then run init again")
                updated = append_block(text, action.content, action.path)
                target.write_text(updated, encoding="utf-8", newline="", errors="surrogateescape")
        except FileExistsError as error:
            raise InitError(f"{action.path} appeared since the plan was made: run init again") from error
        except OSError as error:
            raise InitError(f"{action.path}: can't write it ({error.strerror or type(error).__name__})") from error
    if plan.state_text is not None:
        if _state_text(root) != plan.state_before:
            raise InitError(f"{FILE_NAME} changed while init was writing: not saved; run init again")
        try:
            State.parse(plan.state_text).save(root)
        except StateError as error:
            raise InitError(str(error)) from error


def noreply_warning(root: Path) -> str | None:
    """A warning when this repository's git email isn't a noreply address (spec §6.1). Never prints it."""
    from swerepo.check import _personal

    try:
        done = subprocess.run(
            ["git", "-C", str(root), "config", "user.email"], capture_output=True, text=True, check=False, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    email = done.stdout.strip()
    if done.returncode != 0 or not email or not _personal(email):
        return None
    return (
        "Your git user.email isn't a noreply address. Before the first commit, set one for this repository:\n"
        "  git config user.email ID+USERNAME@users.noreply.github.com   (from github.com/settings/emails)"
    )
