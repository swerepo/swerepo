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
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from swerepo import __version__, standard
from swerepo.adr import AdrError, list_adrs, with_index
from swerepo.blocks import ADR_INDEX, append_block, file_fingerprint, read_exact, wrap
from swerepo.check import _UNRELEASED, UsageError, one_line
from swerepo.detect import Detection, detect
from swerepo.fingerprint import HTML, BlockError, comment_style, find_block, fingerprint
from swerepo.render import TemplateStore
from swerepo.state import COMPONENTS, FILE_NAME, Record, State, StateError

AVAILABLE = ("docs", "agents")  # components this version of init applies
LATER = {"ci": 4, "security": 4, "github": 5, "seamspec": 7, "openspec": 8, "release": 8}
HOSTS = ("claude", "cursor", "vscode", "antigravity", "gemini")
HOST_NAMES = {
    "claude": "Claude Code", "cursor": "Cursor", "vscode": "VS Code Copilot", "antigravity": "Antigravity",
    "gemini": "Gemini CLI",
}  # fmt: skip
RECORDED_VALUES = ("project", "adr_dir", "progress_dir", "commands", "test_inline")  # managed templates use these

CREATE, ADD_BLOCK, GIT_INIT, WRITE_STATE = "create", "add block", "git init", "write"
KEEP, CURRENT, CHANGED, OUTDATED = "keep", "current", "changed", "outdated"
ADOPT, NOTE, LATER_VERB = "adopt", "note", "later"
CHANGING = (CREATE, ADD_BLOCK, GIT_INIT, WRITE_STATE)


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


def commands(root: Path, detection: Detection, adopted_linters: list[str] | None = None) -> dict[str, list[str]]:
    """The commands agents and people run, from what the project uses (spec §6.6): uv by default, poetry
    when it has a poetry.lock, a Makefile's `install`, `test` and `lint` targets when it has them, and the
    linters recorded under `[adopted] linters` (as `check` reads them) before the detected ones."""
    poetry = (root / "poetry.lock").is_file() and not (root / "uv.lock").is_file()
    runner, install = ("poetry run", "poetry install") if poetry else ("uv run", "uv sync")
    linters = set(adopted_linters) if adopted_linters else {linter.name for linter in detection.linters}
    if "ruff" in linters or not linters:
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
    root: Path, detection: Detection, adr_dir: str, progress_dir: str, adopted_linters: list[str] | None = None
) -> dict[str, str]:
    found = commands(root, detection, adopted_linters)
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


def _managed_file(ctx: _Context, component: str, path: str, template: str) -> Action:
    latest = ctx.store.latest(*template.split("/"))
    text = latest.render(ctx.values)
    rendered = file_fingerprint(text, latest.id)
    record = ctx.state.files().get(path) if ctx.state else None
    if not ctx.exists(path):
        if latest.id.startswith("docs/adr-readme@"):
            try:
                text = with_index(text, list_adrs(ctx.root / path.rsplit("/", 1)[0]))
            except AdrError as error:
                raise InitError(f"{path.rsplit('/', 1)[0]}/{error}") from error
        return Action(component, CREATE, path, content=text, record=Record(latest.id, rendered, rendered), kind="file")
    if record is None:
        return Action(component, KEEP, path, "yours: SWERepo didn't write it")
    if file_fingerprint(ctx.read(path), record.template) != record.written:
        return Action(component, CHANGED, path, "changed by you: kept")
    if record.template == latest.id and record.rendered == rendered:
        return Action(component, CURRENT, path)
    return Action(component, OUTDATED, path, f"{latest.id} is newer: swerepo update (Phase 6)")


def _managed_block(ctx: _Context, component: str, path: str, template: str, heading: str = "") -> Action:
    latest = ctx.store.latest(*template.split("/"))
    content = latest.render(ctx.values)
    rendered = fingerprint(content)
    record = ctx.state.blocks().get(path) if ctx.state else None
    new_record = Record(latest.id, rendered, rendered)
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
        return Action(component, ADD_BLOCK, path, content=content, record=new_record, kind="block")
    if record is None:
        return Action(component, KEEP, path, "has a SWERepo block SWERepo didn't record: kept")
    if fingerprint(block.content) != record.written:
        return Action(component, CHANGED, path, "block changed by you: kept")
    if record.template == latest.id and record.rendered == rendered:
        return Action(component, CURRENT, path, "SWERepo block")
    return Action(component, OUTDATED, path, f"{latest.id} is newer: swerepo update (Phase 6)")


def _starter(ctx: _Context, component: str, path: str, template: str, values: dict[str, str]) -> Action:
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
) -> Plan:
    """What `swerepo init` would do. Writes nothing."""
    components = resolve_components(only, skip)
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
    linters = [str(name) for name in (state.adopted.get("linters") or [])] if state else []
    computed = compute_values(root, detection, adr_dir, progress_dir, linters)
    ctx.values = {**computed, **{k: str(recorded[k]) for k in RECORDED_VALUES if isinstance(recorded.get(k), str)}}

    hosts_recorded = bool(state and state.hosts_chosen)
    chosen_hosts = hosts if hosts is not None else (state.hosts if hosts_recorded else list(detection.hosts))
    plan = Plan(root.name, components, chosen_hosts, hosts_recorded or hosts is not None)

    if not detection.git.is_work_tree:
        plan.actions.append(Action("repository", GIT_INIT, None, "not a git repository yet: git init"))
    for component in components:
        if component == "docs":
            plan.actions += _docs(ctx, adr_dir, adopted)
        elif component == "agents":
            plan.actions += _agents(ctx, chosen_hosts)
            if isinstance(recorded.get("commands"), str) and recorded["commands"] != computed["commands"]:
                note = "the project's commands changed since they were recorded: `swerepo update` (Phase 6)"
                plan.actions.append(Action("agents", NOTE, None, note))
        else:
            plan.actions.append(Action(component, LATER_VERB, None, f"init adds it from Phase {LATER[component]}"))

    applied = [c for c in components if c in AVAILABLE]
    plan.state_text = _new_state(ctx, plan, applied, adr_dir if adopted else None)
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


def _new_state(ctx: _Context, plan: Plan, applied: list[str], adopted_adr_dir: str | None) -> str | None:
    """The `.swerepo.toml` after this run, or None when it wouldn't change."""
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
    if ctx.state is None:  # spec §10: an existing repository starts with warn-only pull-request rules
        if _has_commits(ctx.root):
            state.set_pr_rules(enforce=False, warn_since=ctx.today)
        else:
            state.set_pr_rules(enforce=True)
    for action in plan.actions:
        if action.verb in (CREATE, ADD_BLOCK) and action.record is not None and action.path:
            (state.set_file if action.kind == "file" else state.set_block)(action.path, action.record)
    after = state.dumps()
    if after == before:
        return None
    plan.actions.append(Action("state", WRITE_STATE, FILE_NAME, "components: " + ", ".join(state.components)))
    return after


# --- applying -----------------------------------------------------------------------------------------


def _check_targets(plan: Plan, root: Path) -> None:
    """Before anything is written: every file to create is still missing, and every file to gain a block still
    has none. A conflict stops the run with nothing written, so no SWERepo content is left behind unrecorded."""
    for action in plan.actions:
        if action.path is None or action.verb not in (CREATE, ADD_BLOCK):
            continue
        target = root / action.path
        if action.verb == CREATE:
            if target.exists() or target.is_symlink():
                raise InitError(f"{action.path} appeared since the plan was made: nothing written; run init again")
            continue
        try:
            found = find_block(read_exact(target, errors="surrogateescape"), style=comment_style(action.path))
        except OSError as error:
            raise InitError(f"{action.path}: can't read it ({error.strerror or type(error).__name__})") from error
        except BlockError as error:
            raise InitError(f"{action.path}: SWERepo block markers are broken ({error}); nothing written") from error
        if found is not None:
            message = f"{action.path} got a SWERepo block since the plan was made: nothing written; run init again"
            raise InitError(message)


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
        if action.verb not in (CREATE, ADD_BLOCK) or action.path is None or action.content is None:
            continue
        target = root / action.path
        try:
            if action.verb == CREATE:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("x", encoding="utf-8", newline="", errors="surrogateescape") as handle:
                    handle.write(action.content)
            else:
                text = read_exact(target, errors="surrogateescape")
                try:
                    found = find_block(text, style=comment_style(action.path))
                except BlockError as error:
                    raise InitError(f"{action.path}: SWERepo block markers are broken ({error})") from error
                if found is not None:
                    raise InitError(f"{action.path} got a SWERepo block since the plan was made: run init again")
                updated = append_block(text, action.content, action.path)
                target.write_text(updated, encoding="utf-8", newline="", errors="surrogateescape")
        except FileExistsError as error:
            raise InitError(f"{action.path} appeared since the plan was made: run init again") from error
        except OSError as error:
            raise InitError(f"{action.path}: can't write it ({error.strerror or type(error).__name__})") from error
    if plan.state_text is not None:
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
