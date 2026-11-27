"""`swerepo check`: what a repository meets, misses, or has changed (SWEREPO-SPEC §15; ADR-20261120-fc5a).

Read-only. Findings are computed first, then printed as text or JSON, so both say the same thing.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from swerepo import __version__, ci, github, merge, privacy, rebuild, standard
from swerepo import seamspec_component as ssc
from swerepo import spec as specs
from swerepo.blocks import file_fingerprint, inside
from swerepo.commands import uv_run_tools
from swerepo.detect import Detection, detect
from swerepo.fingerprint import HASH, HTML, BlockError, comment_style, find_block, fingerprint
from swerepo.render import TemplateError, TemplateStore, parse_id
from swerepo.state import COMPONENTS, FILE_NAME, Record, State, StateError

OK, MISSING, CHANGED, OUTDATED, UNKNOWN, NOT_CHOSEN = "ok", "missing", "changed", "outdated", "unknown", "not-chosen"
SYMBOL = {OK: "✓", MISSING: "✗", CHANGED: "~", OUTDATED: "↑", UNKNOWN: "?", NOT_CHOSEN: "–"}
GROUPS = ("repository", "state", *COMPONENTS, "pr")  # the order findings are printed in

_UNRELEASED = re.compile(r"^## \[Unreleased\](?:\([^)\n]+\))?[ \t]*$", re.MULTILINE)
_ADR_ID = re.compile(r"ADR-\d{8}-[0-9a-f]{4}")
_NOREPLY = ("users.noreply.github.com", "noreply.github.com")


class UsageError(ValueError):
    """Wrong usage: an unknown component, an unknown --skip value, a --base git can't resolve."""


INIT, APPLY = "init", "apply-github"  # what fixes a finding: `swerepo init`, or applying GitHub's settings


@dataclass(frozen=True)
class Finding:
    component: str
    item: str
    status: str
    message: str
    path: str | None = None
    blocking: bool = False  # a missing item that fails `check`; a warning is missing but doesn't block
    # what fixes it (ADR-20261125-5f22 point 5): "init" (a file or block SWERepo writes), "apply-github" (GitHub's
    # settings), or a short fixed step in plain words or a command, never the finding's own text (review P8-A05)
    fix: str = INIT


@dataclass
class Report:
    folder: str
    mode: str | None
    has_state: bool
    components: list[str]
    findings: list[Finding] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if any(f.blocking for f in self.findings) else 0

    def count(self, status: str) -> int:
        return sum(1 for f in self.findings if f.status == status)

    def next_step(self) -> str | None:
        """What fixes the blocking gaps: `init` for the first group of components it can fix, then each other step
        once, in the order found (ADR-20261125-5f22 point 5)."""
        blocking = [f for f in self.findings if f.blocking]
        gaps = {f.component for f in blocking if f.fix == INIT}
        steps = []
        for group in standard.RECOMMENDED_ORDER:
            chosen = [c for c in group if c in gaps]
            if chosen:
                steps.append(f"swerepo init --only {','.join(chosen)}")
                break
        for finding in blocking:
            step = APPLY_GITHUB if finding.fix == APPLY else finding.fix
            if finding.fix != INIT and step not in steps:
                steps.append(step)
        return "; ".join(steps) or None

    def summary(self) -> str:
        parts = [
            f"{self.count(MISSING)} missing",
            f"{self.count(CHANGED)} changed by you",
            f"{self.count(OUTDATED)} outdated",
            f"{self.count(UNKNOWN)} can't tell",
        ]
        step = self.next_step()
        return ", ".join(parts) + "." + (f" Next: {step}" if step else "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "standard": standard.STANDARD,
            "swerepo": __version__,
            "folder": self.folder,
            "mode": self.mode,
            "state_file": self.has_state,
            "components": self.components,
            "findings": [asdict(f) for f in self.findings],
            "summary": {status: self.count(status) for status in SYMBOL},
            "next": self.next_step(),
            "exit_code": self.exit_code,
        }

    def render_text(self) -> str:
        """Plain lines, no styling or wrapping (ADR-20261120-fc5a point 6)."""
        no_mode = "no mode set" if self.has_state else f"no {FILE_NAME} yet"
        note = f"mode: {self.mode}" if self.mode else no_mode
        lines = [f"SWERepo · check · {self.folder} (standard {standard.STANDARD}, {note})"]
        for group in GROUPS:
            for index, finding in enumerate(f for f in self.findings if f.component == group):
                label = group if index == 0 else ""
                warning = " (warning)" if finding.status == MISSING and not finding.blocking else ""
                lines.append(f"  {label:<9} {SYMBOL[finding.status]} {finding.message}{warning}")
        lines.append(self.summary())
        return "\n".join(one_line(line) for line in lines)

    def annotations(self) -> list[str]:
        """GitHub Actions annotation lines for missing items: errors when blocking, else warnings.
        Values are escaped as the runner expects, so a message can't end or add a workflow command."""
        out = []
        for f in self.findings:
            if f.status != MISSING:
                continue
            params = ([f"file={_escape(f.path, prop=True)}"] if f.path else []) + ["title=swerepo check"]
            kind = "error" if f.blocking else "warning"
            out.append(f"::{kind} {','.join(params)}::{_escape(f'{f.component}: {f.message}')}")
        return out


def one_line(text: str) -> str:
    """Text with CR and LF shown as `\\r` and `\\n`, so a value from a file (a mode, a folder or file
    name) can't start a new output line, which GitHub Actions would read as a workflow command."""
    return text.replace("\r", "\\r").replace("\n", "\\n")


def _escape(value: str, *, prop: bool = False) -> str:
    """Escape a workflow-command value (`%`, CR, LF; also `:` and `,` in a property)."""
    value = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return value.replace(":", "%3A").replace(",", "%2C") if prop else value


# --- context ---------------------------------------------------------------------------------------


@dataclass
class Context:
    root: Path
    detection: Detection
    state: State | None
    hub: github.GitHub | None = None  # GitHub through gh, when asked for and reachable (never with --ci)
    local: bool = False  # run on a person's machine, not in CI: local git hooks are worth reporting
    store: TemplateStore | None = None  # the templates, to tell Dependabot's newer pins from a person's edit
    checking: tuple[str, ...] = ()  # the components this run checks

    def exists(self, path: str) -> bool:
        return (self.root / path).is_file()

    def folder_has_files(self, folder: str) -> bool:
        base = self.root / folder
        return base.is_dir() and any(p.is_file() for p in base.rglob("*"))

    def read(self, path: str) -> str | None:
        try:
            return (self.root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    @property
    def adopted(self) -> dict[str, Any]:
        return self.state.adopted if self.state else {}

    def git(self, *args: str, index: Path | None = None) -> str | None:
        """Run a git command that reads only; its output as UTF-8 text (undecodable bytes replaced, never
        the locale's encoding). `index` points git at another index file (GIT_INDEX_FILE), for commands
        such as `git diff` that refresh the index they use."""
        out = self.git_bytes(*args, index=index)
        return None if out is None else out.decode("utf-8", errors="replace").replace("\r\n", "\n")

    def git_bytes(self, *args: str, index: Path | None = None) -> bytes | None:
        """Run a git command that reads only; its output as bytes (file contents, which may be binary)."""
        env = None if index is None else {**os.environ, "GIT_INDEX_FILE": str(index)}
        try:
            done = subprocess.run(
                ["git", "-C", str(self.root), *args], capture_output=True, check=False, timeout=60, env=env
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return done.stdout if done.returncode == 0 else None

    def read_bytes(self, path: str) -> bytes | None:
        try:
            return (self.root / path).read_bytes()
        except OSError:
            return None


def _ok(component: str, item: str, message: str, path: str | None = None) -> Finding:
    return Finding(component, item, OK, message, path)


def _missing(
    component: str, item: str, message: str, path: str | None = None, *, blocking: bool = True, fix: str = INIT
) -> Finding:
    return Finding(component, item, MISSING, message, path, blocking, fix)


def _present(ctx: Context, component: str, item: str, path: str, what: str | None = None) -> Finding:
    if ctx.exists(path):
        return _ok(component, item, f"{what} ({path})" if what else path, path)
    return _missing(component, item, f"{what} missing ({path})" if what else f"{path} missing", path)


# --- components ------------------------------------------------------------------------------------


def _spec(ctx: Context) -> Finding:
    """The spec exists: only that, with no rule on pull requests (ADR-20261124-4d76 points 4 and 5)."""
    c, found = "docs", specs.find(ctx.root, ctx.adopted.get("spec"), list(ctx.detection.files) or None)
    if found.several:
        return _missing(c, "docs.spec", specs.how_to_choose(found.several), fix="choose the project's spec")
    if found.path is None:
        return _missing(c, "docs.spec", f"{specs.DEFAULT} missing (what the project does and is for)", specs.DEFAULT)
    if not specs.within(ctx.root, found.path):  # missing, or a link out of the repository (review P8-F01)
        where = "leads out of the repository" if (ctx.root / found.path).exists() else "missing"
        message = f"{found.path} {where} (`[adopted] spec` names it)"
        return _missing(c, "docs.spec", message, found.path, fix="fix [adopted] spec in .swerepo.toml")
    return _ok(c, "docs.spec", f"spec ({'adopted: ' if found.adopted else ''}{found.path})", found.path)


def _docs(ctx: Context) -> list[Finding]:
    c, d = "docs", ctx.detection
    found: list[Finding] = []
    readme = d.documents.get("readme")
    if readme:
        found.append(_ok(c, "docs.readme", readme, readme))
    else:
        found.append(_missing(c, "docs.readme", "README missing", "README.md"))

    adopted_dir = ctx.adopted.get("adr_dir")
    detected = {a.path: a.count for a in d.adr_dirs}
    adr_dir = adopted_dir or next(iter(detected), standard.ADR_DIR)
    if adopted_dir and adopted_dir not in detected and (ctx.root / adopted_dir).is_dir():
        records = [p for p in (ctx.root / adopted_dir).glob("*.md") if p.name.lower() not in standard.NOT_ADRS]
        detected[adopted_dir] = len(records)  # detection looks in the usual folders only
    if adr_dir in detected:
        how = "adopted: " if adopted_dir else ""
        found.append(_ok(c, "docs.adr", f"ADRs ({how}{adr_dir}, {detected[adr_dir]} files)", adr_dir))
    else:
        found.append(_missing(c, "docs.adr", f"ADR folder missing ({adr_dir})", adr_dir))
    if adr_dir == standard.ADR_DIR and not adopted_dir:
        for name in ("README.md", "TEMPLATE.md"):
            path = f"{adr_dir}/{name}"
            if not ctx.exists(path):
                found.append(_missing(c, f"docs.adr-{name.lower()}", f"{path} missing", path))
        found.extend(_adr_index(ctx, adr_dir))

    found.append(_present(ctx, c, "docs.progress", standard.PROGRESS_FILE))
    progress_dir = ctx.adopted.get("progress_dir") or standard.PROGRESS_DIR
    if ctx.folder_has_files(progress_dir):
        found.append(_ok(c, "docs.progress-entries", f"progress entries in {progress_dir}/", progress_dir))
    else:
        found.append(_missing(c, "docs.progress-entries", f"{progress_dir}/ missing (one entry per PR)", progress_dir))

    found.append(_spec(ctx))

    changelog = d.documents.get("changelog")
    if not changelog:
        found.append(_missing(c, "docs.changelog", "CHANGELOG.md missing", "CHANGELOG.md"))
    elif _UNRELEASED.search(ctx.read(changelog) or ""):
        found.append(_ok(c, "docs.changelog", f"{changelog} has [Unreleased]", changelog))
    else:
        message = f"{changelog} has no [Unreleased] section"
        found.append(
            _missing(c, "docs.changelog", message, changelog, fix="add an [Unreleased] section to the changelog")
        )

    contributing = d.documents.get("contributing")
    if contributing:
        found.append(_ok(c, "docs.contributing", contributing, contributing))
    else:
        found.append(_missing(c, "docs.contributing", "CONTRIBUTING.md missing", "CONTRIBUTING.md"))
    license_file = d.documents.get("license")
    if license_file:
        found.append(_ok(c, "docs.license", license_file, license_file))
    else:
        found.append(Finding(c, "docs.license", NOT_CHOSEN, "no license chosen (SWERepo never picks one)"))
    return found


def _adr_index(ctx: Context, adr_dir: str) -> list[Finding]:
    readme = f"{adr_dir}/README.md"
    text = ctx.read(readme)
    if text is None:
        return []
    try:
        block = find_block(text, style=HTML, marker="swerepo:adr-index")
    except BlockError as error:
        message = f"{readme}: ADR index markers are broken ({error})"
        return [_missing("docs", "docs.adr-index", message, readme, fix="fix the ADR index markers")]
    if block is None:
        # init adopts a folder of the person's own, but keeps a README it wrote and the person edited (P8-A09)
        recorded = ctx.state is not None and readme in ctx.state.files()
        fix = "put the ADR index markers back in the ADR README, then swerepo adr index" if recorded else INIT
        return [_missing("docs", "docs.adr-index", f"{readme} has no generated ADR index", readme, fix=fix)]
    on_disk = {m.group(0) for p in (ctx.root / adr_dir).glob("ADR-*.md") if (m := _ADR_ID.match(p.name))}
    listed = set(_ADR_ID.findall(block.content))
    unlisted, stale = sorted(on_disk - listed), sorted(listed - on_disk)
    if not unlisted and not stale:
        return [_ok("docs", "docs.adr-index", f"ADR index matches ({len(on_disk)} ADRs)", readme)]
    problems = []
    if unlisted:
        problems.append("not listed: " + ", ".join(unlisted))
    if stale:
        problems.append("listed without a file: " + ", ".join(stale))
    message = f"ADR index out of date ({'; '.join(problems)})"
    return [_missing("docs", "docs.adr-index", message, readme, fix="swerepo adr index")]


MARKERS = "fix the broken SWERepo block markers"


def _block_finding(component: str, item: str, path: str, text: str) -> Finding:
    try:
        block = find_block(text, style=comment_style(path))
    except BlockError as error:
        return _missing(component, item, f"{path}: SWERepo block markers are broken ({error})", path, fix=MARKERS)
    if block is None:
        return _missing(component, item, f"{path} has no SWERepo block", path)
    return _ok(component, item, f"{path} has the SWERepo block", path)


def _agents(ctx: Context) -> list[Finding]:
    c = "agents"
    found: list[Finding] = []
    hosts = ctx.state.hosts if ctx.state and ctx.state.hosts_chosen else list(ctx.detection.hosts)
    text = ctx.read("AGENTS.md")
    if text is None:
        found.append(_missing(c, "agents.block", "AGENTS.md missing", "AGENTS.md"))
    else:
        found.append(_block_finding(c, "agents.block", "AGENTS.md", text))
    if "claude" in hosts:
        claude = ctx.read("CLAUDE.md")
        if claude is None:
            found.append(_missing(c, "agents.claude", "CLAUDE.md missing (Claude Code is in use)", "CLAUDE.md"))
        elif any(line.strip() == "@AGENTS.md" for line in claude.splitlines()):
            found.append(_ok(c, "agents.claude", "CLAUDE.md imports AGENTS.md", "CLAUDE.md"))
        else:
            found.append(_missing(c, "agents.claude", "CLAUDE.md doesn't import AGENTS.md (@AGENTS.md)", "CLAUDE.md"))
    if "antigravity" in hosts or "gemini" in hosts:
        gemini = ctx.read("GEMINI.md")
        if gemini is not None and "AGENTS.md" in gemini:
            found.append(_ok(c, "agents.gemini", "GEMINI.md points to AGENTS.md", "GEMINI.md"))
        else:
            found.append(_missing(c, "agents.gemini", "GEMINI.md missing or doesn't point to AGENTS.md", "GEMINI.md"))
    found.extend(_agents_tools(ctx))
    absent = [path for path in standard.RUNBOOKS if not ctx.exists(path)]
    if absent:
        names = ", ".join(Path(p).name for p in absent)
        found.append(_missing(c, "agents.runbooks", f"docs/agents/ runbooks missing: {names}", "docs/agents"))
    else:
        found.append(_ok(c, "agents.runbooks", "docs/agents/ runbooks", "docs/agents"))
    return found


def _ci_unchanged(ctx: Context) -> Record | None:
    """`swerepo-ci.yml`'s record while the file is as SWERepo wrote it, or differs only by newer action pins
    (Dependabot's, review P8-K06); None otherwise: an edited workflow may install differently, so what it runs
    can't be told (review P8-K)."""
    record = ctx.state.files().get(standard.CI_WORKFLOW) if ctx.state else None
    text = ctx.read(standard.CI_WORKFLOW) if record is not None else None
    if record is None or text is None:
        return None
    # as rendered, not merged: after `update --merge` the record's `written` holds the person's edits (PR #25 review)
    if record.written == record.rendered and file_fingerprint(text, record.template) == record.written:
        return record
    return record if ctx.store is not None and _only_newer_pins(ctx.store, record, text) else None


def _ci_projects(ctx: Context, record: Record) -> list[tuple[str, str, list[str]]]:
    """(folder, lint, kept linters) for each project the recorded workflow runs: the root, then each listed one. From
    the workflow's recorded inputs; for an older record without them, from `[values] lint`, `[adopted] linters` and
    `[projects.inputs]`, as `init` reads them."""
    try:
        inputs = rebuild.workflow_from(record.inputs) if record.inputs is not None else None
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        inputs = None
    if inputs is not None:
        listed = [(p.folder, p.lint, list(p.linters)) for p in inputs.projects]
        return [(".", inputs.lint, list(inputs.linters)), *listed]
    state = ctx.state
    assert state is not None  # a record comes from the state file
    recorded = state.values.get("lint")
    adopted = [str(name) for name in state.adopted.get("linters") or [] if name in ci.KEPT_LINT]
    lint = str(recorded) if recorded in ("ruff", "gradual") else "kept" if adopted else "ruff"
    found = [(".", lint, adopted if lint == "kept" else [])]
    for folder, values in state.project_inputs.items():
        project = ci.Project.from_inputs(folder, values)
        if project is not None:
            found.append((folder, project.lint, list(project.linters)))
    return found


def _ci_tools(ctx: Context) -> list[Finding]:
    """The tools each project's CI jobs run that `uv sync` won't install: a warning, never blocking (review P8-K):
    CI fails without them anyway, and the names read are declared ones, so a tool installed through another (pytest
    through pytest-cov) would be reported though CI runs it. The same text as `init`'s plan note."""
    record = _ci_unchanged(ctx)
    if record is None:
        return []
    found = []
    for folder, lint, linters in _ci_projects(ctx, record):
        if folder != "." and not inside(ctx.root, ctx.root / folder):  # never read through a link out (P8-K08)
            continue
        if ci.install_command(ctx.root, folder)[0] is None:  # Poetry's lock, no [project]: uv add is the wrong advice
            continue
        missing = ci.missing_tools(ctx.root, folder, ci.tools_needed(lint, linters))
        if missing:
            # never pyproject.toml's path, which would stand in for a record finding on it (review P8-K04)
            item, path = ("ci.tools", None) if folder == "." else (f"ci.tools.{folder}", folder)
            message = ci.missing_tools_note(ctx.root, folder, missing)
            fix = ci.tools_fix(ctx.root, folder, missing)
            found.append(_missing("ci", item, message, path, blocking=False, fix=fix))
    return found


_COMMANDS_LINE = re.compile(r"^- (Test|Lint): (.*)$", re.MULTILINE)


def _agents_tools(ctx: Context) -> list[Finding]:
    """The tools `AGENTS.md`'s test and lint commands run through `uv run` that `uv sync` won't install: a warning, as
    `init`'s plan says it (ADR-20261125-5f22 point 5). Read from the block itself, and only while it is as SWERepo
    wrote it, so the commands are the verified ones, never `[values]` edited apart from it (review P8-K09). Left out
    when `ci.tools` speaks for the same project in this run (review P8-K06); a Makefile target or Poetry runs its own
    tools."""
    record = ctx.state.blocks().get("AGENTS.md") if ctx.state else None
    text = ctx.read("AGENTS.md") if record is not None else None
    if record is None or text is None or ci.install_command(ctx.root)[0] is None:
        return []
    try:
        block = find_block(text, style=HTML)
    except BlockError:
        return []
    if block is None or record.written != record.rendered or fingerprint(block.content) != record.written:
        return []  # edited, or merged with the person's edits: the commands may install differently (PR #25 review)
    lines = {kind.lower(): re.findall(r"`([^`]+)`", rest) for kind, rest in _COMMANDS_LINE.findall(block.content)}
    needed = uv_run_tools({"test": lines.get("test", []), "lint": lines.get("lint", [])})
    ci_record = _ci_unchanged(ctx) if "ci" in ctx.checking else None
    if ci_record is not None:  # ci.tools speaks for the root's CI tools; AGENTS.md's others are said here (PR #25)
        root = next(((lint, kept) for folder, lint, kept in _ci_projects(ctx, ci_record) if folder == "."), None)
        covered = set(ci.tools_needed(*root)) if root is not None else set()
        needed = [tool for tool in needed if tool not in covered]
    missing = ci.missing_tools(ctx.root, ".", needed)
    if not missing:
        return []
    message = ci.AGENTS_TOOLS + ci.missing_tools_note(ctx.root, ".", missing)  # init's words (review P8-K)
    return [_missing("agents", "agents.tools", message, blocking=False, fix=ci.tools_fix(ctx.root, ".", missing))]


# How GitHub's settings get applied: in a terminal, shown and asked first; otherwise by name (ADR-20261125-5f22)
APPLY_GITHUB = "swerepo init --only github (in a terminal), or with --yes --apply-github"


def _ci_fix(ctx: Context) -> str:
    """`init` writes the CI and ruff's settings only for a project uv installs with a Python version standard 1
    knows; otherwise its plan says why, and that is the person's to change (review P8-A09)."""
    if ci.install_command(ctx.root)[0] is not None and ci.python_versions(ctx.detection)[0]:
        return INIT
    return "make the project one CI can install: swerepo init --only ci --dry-run says why it can't"


def _ci(ctx: Context) -> list[Finding]:
    c, d = "ci", ctx.detection
    found: list[Finding] = []
    text = ctx.read(standard.CI_WORKFLOW)
    if text is None:
        others = [w.path.rsplit("/", 1)[-1] for w in d.workflows if w.runs_pytest]
        note = f" (you run pytest in {', '.join(others)}: kept)" if others else ""
        found.append(
            _missing(c, "ci.workflow", f"swerepo-ci.yml missing{note}", standard.CI_WORKFLOW, fix=_ci_fix(ctx))
        )
    else:
        found.append(_ok(c, "ci.workflow", "swerepo-ci.yml", standard.CI_WORKFLOW))
        found.append(_ci_ok(text))
        found.extend(_python_matrix(ctx, text))
        files = list(ctx.detection.files)
        if not ci.project_has_tests(ctx.root, files):  # the test job fails without (ADR-20261125-5f22)
            message = "no tests yet: the test job fails until there is one (a real test: docs/agents/prepare-pr.md)"
            found.append(_missing(c, "ci.tests", message, blocking=False))
        for folder in ctx.state.projects_listed if ctx.state else []:  # each listed project's own job (P8-G01)
            if not ci.project_has_tests(ctx.root, files, folder):
                message = f"{folder}/: no tests yet: its test job fails until there is one"
                found.append(_missing(c, f"ci.tests.{folder}", message, folder, blocking=False))
        found.extend(_ci_tools(ctx))

    detected = {linter.name for linter in d.linters}
    kept = [str(name) for name in ctx.adopted.get("linters", [])]
    unfound = [name for name in kept if name not in detected]
    if "ruff" in detected:
        found.append(_ok(c, "ci.linter", "linting: ruff"))
    elif kept and unfound:
        message = f"linting: {', '.join(unfound)} kept, but no configuration found (pyproject, own files, pre-commit)"
        found.append(Finding(c, "ci.linter", UNKNOWN, message))
    elif kept or detected:
        found.append(_ok(c, "ci.linter", f"linting: {', '.join(kept or sorted(detected))} (kept)"))
    else:
        message = "no linter or formatter configured (ruff, or the project's own)"
        found.append(_missing(c, "ci.linter", message, fix=_ci_fix(ctx)))
    if d.seamspec:
        found.append(_seamspec_excluded(ctx, detected))
    if d.is_monorepo or (ctx.state is not None and ctx.state.projects_listed):
        found.extend(_projects_covered(ctx, text or ""))
    if text is not None and "dependency-review:" in text:
        found.append(_dependency_graph(ctx))
    # The wait belongs to the github component: without it, a ruleset is the person's own (review P5-F10).
    github_chosen = ctx.state is not None and "github" in ctx.state.components
    committed = _read_json(ctx, github.RULESET_FILE) if github_chosen and ctx.exists(github.RULESET_FILE) else None
    if text is not None and committed is not None:  # the committed ruleset decides
        found.append(_copilot_wait(github.has_copilot_review(committed), text))
    elif text is not None and github_chosen and "copilot_review" in ctx.state.github:
        found.append(_copilot_wait(ctx.state.github["copilot_review"] is True, text))
    return found


_JOB = re.compile(r"^  (?P<job>[A-Za-z_][\w-]*):\s*(?:#.*)?$")
_NEEDS_INLINE = re.compile(r"^    needs:\s*(?P<value>[^#]*?)\s*(?:#.*)?$")
_LIST_ITEM = re.compile(r"^      -\s*(?P<item>[\w-]+)\s*(?:#.*)?$")
_MATRIX = re.compile(r"^ +python:\s*\[(?P<items>[^\]]*)\]\s*(?:#.*)?$")


def workflow_jobs(text: str) -> dict[str, list[str]]:
    """The jobs of a workflow SWERepo wrote, each with its `needs:`, read from the text (two-space indents)."""
    jobs: dict[str, list[str]] = {}
    current: str | None = None
    in_jobs = in_needs_list = False
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue  # a comment, even at column 0, doesn't end `jobs:` (review: Copilot on PR #8)
        if not line.startswith(" ") and line.strip():
            in_jobs, current = line.split("#", 1)[0].strip() == "jobs:", None
            continue
        if not in_jobs:
            continue
        if job := _JOB.match(line):
            current, in_needs_list = job["job"], False
            jobs[current] = []
            continue
        if current is None:
            continue
        if needs := _NEEDS_INLINE.match(line):
            value = needs["value"].strip()
            in_needs_list = not value
            jobs[current] = [n.strip() for n in value.strip("[]").split(",") if n.strip()] if value else []
        elif in_needs_list and (item := _LIST_ITEM.match(line)):
            jobs[current].append(item["item"])
        elif line.strip() and not line.startswith("      "):
            in_needs_list = False
    return jobs


def _copilot_wait(review_on: bool, text: str) -> Finding:
    """swerepo-ci.yml waits for Copilot's review exactly when the github component turned it on (ADR-a359, P5-F01)."""
    c, item = "ci", "ci.copilot-review"
    waits = "copilot-review" in workflow_jobs(text).get("ci-ok", [])
    if review_on and not waits:
        message = "swerepo-ci.yml doesn't wait for the Copilot review the ruleset requests: swerepo init --only github"
        return _missing(c, item, message, standard.CI_WORKFLOW, fix="swerepo init --only github")
    if waits and not review_on:
        message = "swerepo-ci.yml waits for a Copilot review the ruleset doesn't request: every pull request would fail"
        fix = "make swerepo-ci.yml and the ruleset agree on Copilot's review"
        return _missing(c, item, message, standard.CI_WORKFLOW, fix=fix)
    message = "waits for Copilot's review" if waits else "no Copilot review to wait for"
    return _ok(c, item, message, standard.CI_WORKFLOW)


def _dependency_graph(ctx: Context) -> Finding:
    """Dependency review fails ci-ok while GitHub's dependency graph is off (PR #9; ADR-20261123-4e40 point 8)."""
    c, item = "ci", "ci.dependency-graph"
    if ctx.hub is None:
        return Finding(c, item, UNKNOWN, "dependency graph: can't tell (needs gh, logged in; never read with --ci)")
    try:
        if ctx.hub.repo().get("private") is True:  # dependency-review is skipped by design there (P5-F06)
            return _ok(c, item, "dependency graph: not needed (private repository: dependency-review is skipped)")
        if ctx.hub.dependency_graph():
            return _ok(c, item, "GitHub's dependency graph is on (dependency-review needs it)")
    except github.GitHubError as error:
        return Finding(c, item, UNKNOWN, f"dependency graph: can't read GitHub ({error})")
    message = "GitHub's dependency graph is off: dependency-review fails ci-ok (Settings → Advanced Security)"
    return _missing(c, item, message, fix="turn on GitHub's dependency graph (Settings → Advanced Security)")


CI_OK = "make ci-ok in swerepo-ci.yml wait for every job"


def _ci_ok(text: str) -> Finding:
    """`ci-ok` waits for every other job (spec §6.2): the ruleset requires only it."""
    c, item = "ci", "ci.ci-ok"
    jobs = workflow_jobs(text)
    if "ci-ok" not in jobs:
        return _missing(c, item, "swerepo-ci.yml has no ci-ok job", standard.CI_WORKFLOW, fix=CI_OK)
    left_out = [job for job in jobs if job != "ci-ok" and job not in jobs["ci-ok"]]
    if left_out:
        message = f"ci-ok doesn't wait for {', '.join(left_out)}: a failure there wouldn't block a merge"
        return _missing(c, item, message, standard.CI_WORKFLOW, fix=CI_OK)
    return _ok(c, item, "ci-ok waits for every job", standard.CI_WORKFLOW)


def _versions(items: list[str]) -> str:
    return f"{items[0]}–{items[-1]}" if len(items) > 1 else (items[0] if items else "none")


def job_blocks(text: str) -> dict[str, str]:
    """Each job's lines (two-space indents), by job name; comment lines left out."""
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    in_jobs = False
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and line.strip():
            in_jobs, current = line.split("#", 1)[0].strip() == "jobs:", None
            continue
        if in_jobs and (job := _JOB.match(line)):
            current = job["job"]
            blocks[current] = []
        elif in_jobs and current is not None:
            blocks[current].append(line)
    return {name: "\n".join(lines) for name, lines in blocks.items()}


def _python_matrix(ctx: Context, text: str) -> list[Finding]:
    """Each test job's matrix matches what its project declares (spec §6.2): the root's `test` job, and each listed
    project's `test-<name>` job against that project's own `requires-python` (review: Copilot on PR #8)."""
    c = "ci"
    blocks = job_blocks(text)
    listed = ctx.state.projects_listed if ctx.state else []
    found: list[Finding] = []
    for folder, job in ((".", "test"), *((f, "test-" + ci.Project(f, "", []).job) for f in listed)):
        item = "ci.python-matrix" if folder == "." else f"ci.python-matrix:{folder}"
        where = "" if folder == "." else f"{folder}/: "
        match = next((m for line in blocks.get(job, "").splitlines() if (m := _MATRIX.match(line))), None)
        if match is None:
            message = f"{where}can't find the Python versions of the {job} job in swerepo-ci.yml"
            found.append(Finding(c, item, UNKNOWN, message, standard.CI_WORKFLOW))
            continue
        tested = [v.strip().strip("'\"") for v in match["items"].split(",") if v.strip()]
        detection = ctx.detection if folder == "." else detect(ctx.root / folder)
        declared, _ = ci.python_versions(detection)
        if not declared:
            message = f"{where}requires-python allows no Python version standard 1 knows"
            found.append(Finding(c, item, UNKNOWN, message))
        elif tested == declared:
            message = f"{where}tests Python {_versions(tested)}, as the project declares"
            found.append(_ok(c, item, message, standard.CI_WORKFLOW))
        else:
            message = (
                f"{where}tests Python {_versions(tested)}; the project declares {_versions(declared)}: swerepo update"
            )
            found.append(Finding(c, item, OUTDATED, message, standard.CI_WORKFLOW))
    return found


def _projects_covered(ctx: Context, text: str) -> list[Finding]:
    """Every project root covered by a SWERepo job or recorded as not covered (spec §11)."""
    c = "ci"
    listed = ctx.state.projects_listed if ctx.state else []
    skipped = ctx.state.projects_not_covered if ctx.state else []
    github = ctx.state.doc.get("github") if ctx.state else None
    extra = list(github.get("extra_required_checks", [])) if github is not None else []
    jobs = workflow_jobs(text)
    found: list[Finding] = []
    # every project root detection found, and every listed folder, also those it skips (`tools/`; P4-F06)
    folders = dict.fromkeys([*(p.path for p in ctx.detection.projects if p.path != "."), *listed])
    for folder in folders:
        item = f"ci.projects:{folder}"
        job = ci.Project(folder, "", []).job
        if folder in listed and f"lint-{job}" in jobs and f"test-{job}" in jobs:
            found.append(_ok(c, item, f"{folder}/ has its own jobs in swerepo-ci.yml", folder))
        elif folder in listed:
            command = f"swerepo init --only ci --projects {','.join(listed)}"
            message = f"{folder}/ is listed, but swerepo-ci.yml lacks its lint or test job: {command}"
            found.append(_missing(c, item, message, folder, fix=command))
        elif folder in skipped:
            found.append(_ok(c, item, f"{folder}/ recorded as not covered", folder))
        elif extra:
            message = f"{folder}/: whether [github] extra_required_checks cover it can't be told from files"
            found.append(Finding(c, item, UNKNOWN, message, folder))
        else:
            fix = "give each project CI jobs (--projects), or record it as not covered"
            found.append(_missing(c, item, f"{folder}/ not covered by any required check", folder, fix=fix))
    return found


_SEAMSPEC_EXCLUDES = frozenset({".seamspec", ".seamspec/*", ".seamspec/**", "**/.seamspec", "**/.seamspec/**"})


def _strings(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _normal_exclude(entry: str) -> str:
    entry = entry.strip()
    while entry.startswith("./"):
        entry = entry[2:]
    return entry.rstrip("/")


def _seamspec_excluded(ctx: Context, linters: set[str]) -> Finding:
    """Locked SeamSpec tests must never be reformatted (SeamSpec ADR-20261013-c3f7, spec §6.3)."""
    c, item = "ci", "ci.seamspec-excluded"
    if "ruff" not in linters:
        if not linters:
            return Finding(c, item, UNKNOWN, "no linter found to check for .seamspec")
        touching = [name for name in sorted(linters) if not _settings_mention_seamspec(ctx, name)]
        if not touching:
            verb = "skips" if len(linters) == 1 else "skip"
            return _ok(c, item, f"{', '.join(sorted(linters))} {verb} .seamspec (their own settings)")
        message = (f"{', '.join(touching)} would touch locked SeamSpec tests when run locally: exclude .seamspec in "
                   "their settings (swerepo-ci.yml's lint job already does)")  # fmt: skip
        return Finding(c, item, CHANGED, message)
    for source in ("ruff.toml", ".ruff.toml", "pyproject.toml"):
        text = ctx.read(source)
        if text is None:
            continue
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            continue
        tool = data.get("tool", {})
        config = data if source != "pyproject.toml" else (tool.get("ruff") if isinstance(tool, dict) else None)
        if not isinstance(config, dict):
            continue
        excluded = [entry for key in ("exclude", "extend-exclude") for entry in _strings(config.get(key))]
        if any(_normal_exclude(entry) in _SEAMSPEC_EXCLUDES for entry in excluded):
            return _ok(c, item, f"ruff skips .seamspec ({source})", source)
        message = f'ruff would lint and reformat locked SeamSpec tests: add ".seamspec" to extend-exclude in {source}'
        return _missing(c, item, message, source, fix='add ".seamspec" to ruff\'s extend-exclude')
    return Finding(c, item, UNKNOWN, "can't find ruff's configuration to see whether it skips .seamspec")


def _settings_mention_seamspec(ctx: Context, linter: str) -> bool:
    """Whether a kept linter's own settings name `.seamspec` (spec §6.3), in every place it is configured."""
    places = next((found.configured_in for found in ctx.detection.linters if found.name == linter), ())
    for place in places:
        name, _, section = place.partition(" ")
        text = ctx.read(name) or ""
        if name == "pyproject.toml":
            try:
                tool = tomllib.loads(text).get("tool", {})
            except tomllib.TOMLDecodeError:
                return False
            text = repr(tool.get(linter, {})) if isinstance(tool, dict) else ""
        elif section:
            wanted = section.strip("[]")
            text = "\n".join(_ini_section(text, wanted))
        if ".seamspec" not in text:  # pre-commit too: its hooks take an `exclude:` (review P4-F06)
            return False
    return bool(places)


def _ini_section(text: str, wanted: str) -> list[str]:
    lines, inside_section = [], False
    for line in text.splitlines():
        if heading := re.match(r"^\[(?P<name>[^\]]+)\]", line.strip()):
            inside_section = heading["name"].split(".")[0] == wanted
        elif inside_section:
            lines.append(line)
    return lines


def _secret_scanning(ctx: Context) -> list[Finding]:
    """GitHub's secret scanning and push protection (spec §6.4), when gh can read them."""
    c, item = "security", "security.secret-scanning"
    if ctx.hub is None:
        return [Finding(c, item, UNKNOWN, "secret scanning: can't tell (needs gh, logged in; never read with --ci)")]
    try:
        analysis = ctx.hub.repo().get("security_and_analysis") or {}
    except github.GitHubError as error:
        return [Finding(c, item, UNKNOWN, f"secret scanning: can't read GitHub ({error})")]
    keys = ("secret_scanning", "secret_scanning_push_protection")
    states = {key: (analysis.get(key) or {}).get("status") for key in keys}
    if None in states.values():
        return [Finding(c, item, UNKNOWN, "secret scanning: GitHub doesn't show it to this login (admins only)")]
    off = [key.replace("_", " ") for key, status in states.items() if status != "enabled"]
    if off:
        return [_missing(c, item, f"{' and '.join(off)} off on GitHub (Settings → Advanced Security)", blocking=False)]
    return [_ok(c, item, "secret scanning and push protection on")]


def _pre_push_hook(ctx: Context) -> Finding:
    """The local pre-push privacy hook (ADR-20261123-24e0): reported on a person's machine, never in CI, and never
    blocking. Reads the hooks folder only."""
    from swerepo import hook

    c, item = "security", "security.pre-push-hook"
    try:
        found = hook.status(ctx.root)
    except hook.HookError:
        return Finding(c, item, UNKNOWN, "pre-push privacy hook: can't tell (git didn't answer)")
    if found == "installed":
        return _ok(c, item, "pre-push privacy hook installed")
    if found == "not executable":  # git skips it without a word (review H55-F01)
        return _missing(c, item, "pre-push privacy hook isn't executable, so git skips it (swerepo hook install)",
                        blocking=False)  # fmt: skip
    if found == "other":
        line = 'swerepo privacy --pre-push --remote "${1:-}"'  # the remote, too (review H55-F03)
        return _missing(c, item, f"a pre-push hook of your own: add `{line}` to it to scan pushes", blocking=False)
    return _missing(c, item, "pre-push privacy hook not installed (swerepo hook install)", blocking=False)


def _security(ctx: Context) -> list[Finding]:
    c = "security"
    policy = ctx.detection.documents.get("security") or ("SECURITY.md" if ctx.exists("SECURITY.md") else None)
    if policy:
        found = [_ok(c, "security.policy", policy, policy)]
    else:
        found = [_missing(c, "security.policy", "SECURITY.md missing", "SECURITY.md")]
    if ctx.exists(standard.PRIVACY_WORKFLOW):
        message = f"privacy workflow ({standard.PRIVACY_WORKFLOW})"
        found.append(_ok(c, "security.workflow", message, standard.PRIVACY_WORKFLOW))
    else:
        released = ci.released()
        how = "" if released else ": needs a released SWERepo, or swerepo init --with-governance"
        message = f"privacy workflow missing ({standard.PRIVACY_WORKFLOW}){how}"
        fix = INIT if released else "wait for a released SWERepo, or swerepo init --only security --with-governance"
        found.append(_missing(c, "security.workflow", message, standard.PRIVACY_WORKFLOW, fix=fix))
    text = ctx.read(".gitignore")
    if text is None:
        found.append(_missing(c, "security.gitignore", ".gitignore missing", ".gitignore"))
    else:
        found.append(_block_finding(c, "security.gitignore", ".gitignore", text))
    found.extend(_secret_scanning(ctx))
    if ctx.local:
        found.append(_pre_push_hook(ctx))
    hits = privacy.scan(ctx.root, ctx.state.privacy_allow_paths if ctx.state else [])
    if hits:
        fix = "clear the privacy findings (swerepo privacy)"
        found.append(_missing(c, "security.privacy-scan", privacy.summary(hits), hits[0].path, fix=fix))
    else:
        found.append(_ok(c, "security.privacy-scan", "privacy scan: nothing found"))
    return found


def _github(ctx: Context) -> list[Finding]:
    c, d = "github", ctx.detection
    found = [_present(ctx, c, f"github.{Path(path).stem}", path, what) for path, what in standard.GITHUB_FILES]
    template = d.documents.get("pr_template")
    if template:
        found.append(_ok(c, "github.pr-template", f"PR template ({template})", template))
    else:
        message = "PR template missing (.github/pull_request_template.md)"
        found.append(_missing(c, "github.pr-template", message, ".github/pull_request_template.md"))
    if ctx.folder_has_files(".github/ISSUE_TEMPLATE"):
        found.append(_ok(c, "github.issue-templates", "issue templates", ".github/ISSUE_TEMPLATE"))
    else:
        message = "issue templates missing (.github/ISSUE_TEMPLATE/)"
        found.append(_missing(c, "github.issue-templates", message, ".github/ISSUE_TEMPLATE"))
    found.append(_codeowners(ctx, d.documents.get("codeowners")))
    found.extend(_code_owner_live(ctx, d.documents.get("codeowners")))
    found.extend(_commit_email(ctx))
    found.extend(_github_live(ctx))
    return found


def _read_json(ctx: Context, path: str) -> dict[str, Any] | None:
    try:
        data = json.loads(ctx.read(path) or "")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _github_live(ctx: Context) -> list[Finding]:
    """The live ruleset and merge settings against the committed files (spec §12), read through gh with GET
    requests only, and never with --ci (ADR-20261123-4e40 point 7)."""
    c = "github"
    applied = ctx.state.github.get("applied") if ctx.state else None
    if ctx.hub is None:
        if applied is False and github.repository(ctx.root) is None:
            fix = "create the GitHub repository (gh repo create --source . --push)"
            return [_missing(c, "github.live", "ruleset not applied (no GitHub repository yet)", fix=fix)]
        message = ("ruleset, merge settings and code owner on GitHub: can't tell (needs gh, logged in; never read "
                   "with --ci)")  # fmt: skip
        return [Finding(c, "github.live", UNKNOWN, message)]
    found: list[Finding] = []
    pairs = (("github.ruleset", github.RULESET_FILE, "ruleset"), ("github.merge-settings", github.SETTINGS_FILE, None))
    for item, path, kind in pairs:
        if not ctx.exists(path):
            continue  # already reported missing by its own finding (P5-F02)
        committed = _read_json(ctx, path)
        if committed is None:
            found.append(Finding(c, item, UNKNOWN, f"can't compare with GitHub: {path} isn't readable JSON", path))
            continue
        problem = github.not_applicable(kind or "repo-settings", committed)
        if problem:  # init refuses to apply it, so it never matches GitHub (PR #10 review)
            fix = "fix the settings file SWERepo won't apply"
            found.append(_missing(c, item, f"{path}: {problem}: swerepo init won't apply it", path, fix=fix))
            continue
        try:
            live = ctx.hub.find_ruleset() if kind else ctx.hub.repo()
        except github.GitHubError as error:
            found.append(Finding(c, item, UNKNOWN, f"can't read GitHub ({error})", path))
            continue
        label = f'ruleset "{github.RULESET_NAME}"' if kind else "merge settings"
        if live is None:
            found.append(_missing(c, item, f"{label} not applied on GitHub: {APPLY_GITHUB}", path, fix=APPLY))
            continue
        compare = github.ruleset_differences if kind else github.settings_differences
        differences = compare(committed, live)
        if differences:
            verb = "differs" if kind else "differ"
            message = f"{label} on GitHub {verb} from {path} ({', '.join(differences)}): {APPLY_GITHUB}"
            found.append(_missing(c, item, message, path, fix=APPLY))
        else:
            found.append(_ok(c, item, f"{label} on GitHub {'matches' if kind else 'match'} {path}", path))
    return found


def _codeowners(ctx: Context, path: str | None) -> Finding:
    c, item = "github", "github.codeowners"
    if path is None:
        recorded = ctx.state.values.get("code_owner") if ctx.state else None
        if ctx.state is not None and "github" in ctx.state.components and not github.valid_owner(recorded):
            # init leaves CODEOWNERS out when nobody is named; that's a choice, not a failure (review P5-F03)
            message = "no CODEOWNERS: no code owner named (swerepo init --only github --code-owner …)"
            return _missing(c, item, message, ".github/CODEOWNERS", blocking=False)
        if github.example_owner(recorded):  # init writes nothing from the question's example: name an owner (P8-K10)
            message = (
                f"CODEOWNERS missing, and the recorded code owner {str(recorded).lower()} is the question's example"
            )
            return _missing(c, item, message, ".github/CODEOWNERS", fix=OWNER_FIX)
        return _missing(c, item, "CODEOWNERS missing (.github/CODEOWNERS)", ".github/CODEOWNERS")
    text = ctx.read(path) or ""
    try:
        block = find_block(text, style=HASH)
    except BlockError as error:
        return _missing(c, item, f"{path}: SWERepo block markers are broken ({error})", path, fix=MARKERS)
    if block is None:
        return _missing(c, item, f"{path} has no SWERepo block (governance owners)", path)
    problem = _block_owner_problem(block.content)  # the block first: never masked by the lines after it (P8-K03)
    if problem:
        return _missing(c, item, f"{path}: {problem}", path, fix=OWNER_FIX)
    # the same line breaks find_block counts: CR, LF, CRLF; not U+2028 or form feeds (review P5-F08)
    rest = re.split(r"\r\n|\r|\n", text)[block.end_line :]
    after = [line for line in rest if line.strip() and not line.lstrip().startswith("#")]
    if after:
        # path patterns only, never owners: a malformed line may start with an @handle or an email address
        patterns = ", ".join(token for line in after if "@" not in (token := line.split()[0]))
        named = f" ({patterns})" if patterns else ""
        message = f"{path}: rules after the SWERepo block can override governance owners{named}"
        return Finding(c, item, CHANGED, message, path)
    return _ok(c, item, f"{path}: governance block last", path)


OWNER_FIX = "name a code owner GitHub knows, with write access: swerepo init --only github --code-owner …"


def _block_owner_problem(content: str) -> str | None:
    """What's wrong with the owners in SWERepo's CODEOWNERS block, read offline, or None (review P8-K, P8-K03). A token
    GitHub can't read is named by its rule's place, never printed: it may be an address with a typo (inv_5e3b5ef3)."""
    rules = github.codeowners_rules(content)
    if not rules:
        return "SWERepo's block has no rules: the governance paths have no code owner"
    for number, (_, owners) in enumerate(rules, start=1):
        if not owners:
            return f"rule {number} of SWERepo's block names no owner: GitHub leaves that path unowned"
        for owner in owners:
            if github.example_owner(owner):
                return f"names {owner.lower()}, the code-owner question's example, not an owner"
            if not github.readable_owner(owner):
                return f"rule {number} of SWERepo's block names an owner GitHub can't read"
    return None


def _code_owner_live(ctx: Context, path: str | None) -> list[Finding]:
    """The owners in SWERepo's CODEOWNERS block, looked up on GitHub: they exist and can own files here (review P8-K).
    Read only, through gh with GET requests, never with --ci (ADR-20261123-4e40 point 7). An email owner isn't looked
    up or printed, and the prompt's examples are reported offline by `github.codeowners`."""
    text = ctx.read(path) if ctx.hub is not None and path is not None else None
    try:
        block = find_block(text, style=HASH) if text is not None else None
    except BlockError:
        return []
    if block is None:
        return []
    owners: list[str] = []
    for _, names in github.codeowners_rules(block.content):
        for owner in names:
            looked_up = github.valid_owner(owner) and not github.example_owner(owner)
            if looked_up and owner.lower() not in (o.lower() for o in owners):
                owners.append(owner)
    if not owners:
        return []
    c, item, found = "github", "github.code-owner", []
    for owner in owners:
        verdict, reason = ctx.hub.owner_verdict(owner)  # type: ignore[union-attr]
        if verdict in (github.OWNER_WRONG, github.OWNER_ACCESS):
            found.append(_missing(c, item, f"{path}: code owner {owner}: {reason}", path, fix=OWNER_FIX))
        elif verdict == github.OWNER_UNKNOWN:
            found.append(Finding(c, item, UNKNOWN, f"{path}: code owner {owner}: {reason}", path))
    if not found:
        named = ", ".join(owners)
        found.append(_ok(c, item, f"code owner{'s' if len(owners) > 1 else ''} on GitHub ({named})", path))
    return found


def _personal(email: str) -> bool:
    domain = email.rsplit("@", 1)[-1].lower()
    if any(domain == n or domain.endswith("." + n) for n in _NOREPLY):
        return False
    return not re.search(r"(^|\.)example(\.(com|org|net))?$", domain)


def _commit_email(ctx: Context) -> list[Finding]:
    """Commits under a noreply address (spec §6.1). Counts the addresses, never prints them
    (ADR-20261120-fc5a point 7). Warnings: past commits can't be fixed without rewriting history."""
    c = "github"
    if not ctx.detection.git.is_work_tree:
        return []
    found: list[Finding] = []
    configured = (ctx.git("config", "user.email") or "").strip()
    if configured and _personal(configured):
        found.append(_missing(c, "github.email", "git user.email isn't a noreply address", blocking=False))
    recent = [e for e in (ctx.git("log", "-20", "--format=%ae") or "").splitlines() if e]
    personal = sum(1 for e in recent if _personal(e))
    if personal:
        message = f"{personal} of the last {len(recent)} commits use an address that isn't a noreply one"
        found.append(_missing(c, "github.commit-email", message, blocking=False))
    elif recent:
        found.append(_ok(c, "github.commit-email", "recent commits use a noreply address"))
    return found


def _seamspec(ctx: Context) -> list[Finding]:
    c = "seamspec"
    config = ctx.read(".seamspec/config.toml")
    if config is None:
        return [_missing(c, "seamspec.setup", "SeamSpec not set up", ".seamspec")]
    found = [_ok(c, "seamspec.setup", "SeamSpec set up", ".seamspec/config.toml")]
    try:
        mode = tomllib.loads(config).get("mode")
    except tomllib.TOMLDecodeError:
        mode = None
    if mode in ("enforced", "strict"):
        found.append(_ok(c, "seamspec.mode", f"mode: {mode}", ".seamspec/config.toml"))
    else:
        message = f"mode: {mode or 'unknown'} (locked rules don't block)"
        fix = "set SeamSpec's mode to enforced or strict (seamspec init)"
        found.append(_missing(c, "seamspec.mode", message, ".seamspec/config.toml", fix=fix))
    found.append(_present(ctx, c, "seamspec.earned-spec", standard.EARNED_SPEC))
    runners = [
        w.path for w in ctx.detection.workflows if any(_runs_seamspec_verify(r) for r in _runs(ctx.read(w.path)))
    ]
    if runners:
        found.append(_ok(c, "seamspec.ci", f"CI runs the locked rules ({', '.join(Path(p).name for p in runners)})"))
    else:
        found.append(_missing(c, "seamspec.ci", "no workflow runs `seamspec verify`"))
    return found + _seamspec_rules(ctx) + _seamspec_workflows(ctx, mode) + _seamspec_local(ctx)


def _seamspec_rules(ctx: Context) -> list[Finding]:
    """The hygiene rules (ADR-20261124-cd64 points 5 and 6) and the proposals waiting for review, from SeamSpec's own
    files. A rule not yet approved only warns: approving is the person's call."""
    c, ledger = "seamspec", ssc.Ledger.read(ctx.root)
    chosen = set(ctx.state.components) if ctx.state else set()
    adopted = ctx.state.seamspec_adopted if ctx.state else {}
    found = []
    adr_dir = str(ctx.adopted.get("adr_dir") or "docs/adr")
    for rule in ssc.HYGIENE.values():
        status, rule_id = ledger.hygiene(rule.name, adopted)
        if rule.component not in chosen or (status == "missing" and not ssc.applies(ctx.root, rule.name, adr_dir)):
            continue  # no subject here yet: init wouldn't propose it either (review P7-F06)
        item, label = f"seamspec.hygiene.{rule.name}", f"hygiene/{rule.name}"
        if status in ("locked", "adopted", "declined"):
            word = {"locked": "locked", "adopted": "adopted", "declined": "declined by you"}[status]
            found.append(_ok(c, item, f"{label}: {word} ({rule_id})"))
        elif status == "proposed":
            message = f"{label}: proposed ({rule_id}), waiting for seamspec review"
            found.append(_missing(c, item, message, blocking=False))
        elif status == "adopted-not-locked":
            message = f"{label}: [seamspec.adopted] names {rule_id}, which isn't locked here"
            found.append(_missing(c, item, message, fix="name a locked rule under [seamspec.adopted]"))
        else:
            message = f"{label}: not proposed yet (swerepo init --only seamspec)"
            found.append(_missing(c, item, message, blocking=False))
    waiting = ledger.waiting()
    if waiting:
        message = f"{len(waiting)} proposal(s) waiting for your review: seamspec review"
        found.append(_missing(c, "seamspec.waiting", message, blocking=False))
    return found


def _seamspec_workflows(ctx: Context, mode: object) -> list[Finding]:
    """SeamSpec's own workflow, unpinned, in any mode (review P7-F06), and strict mode's CODEOWNERS block
    (ADR-20261124-cd64 points 3 and 4)."""
    c, found = "seamspec", []
    workflow = ctx.read(ssc.WORKFLOW)
    if workflow is not None and ssc.unpinned(workflow):
        how = "pin them, or delete it and run swerepo init --only seamspec"  # init keeps a file it finds (P8-A09)
        message = f"{ssc.WORKFLOW}: actions not pinned to commits, so the workflow audit fails ({how})"
        found.append(_missing(c, "seamspec.workflow", message, ssc.WORKFLOW, fix=f"{ssc.WORKFLOW}: {how}"))
    if mode != "strict":
        return found
    owners = ctx.read(github.CODEOWNERS)
    team = bool(ctx.state and ctx.state.mode == "team")
    for problem in ssc.codeowners_problems(owners or ""):
        message = f"{github.CODEOWNERS}: {problem}"
        fix = "fix CODEOWNERS for SeamSpec's strict mode"
        found.append(_missing(c, "seamspec.codeowners", message, github.CODEOWNERS, blocking=team, fix=fix))
    return found


def _seamspec_local(ctx: Context) -> list[Finding]:
    """On a person's machine only (never with --ci): the installed SeamSpec against the CI pin, `seamspec doctor`,
    and whether the earned spec is current. Each of these commands only reads (ADR-20261124-cd64 point 9)."""
    if not ctx.local or ssc.command() is None:
        return []
    c, found = "seamspec", []
    pinned = ctx.state.tools.get("seamspec") if ctx.state else None
    installed = ssc.installed_version(ctx.root)
    if ssc.newer(installed, pinned):
        message = f"SeamSpec {installed} installed, CI pins {pinned}: swerepo -u --seamspec"
        found.append(Finding(c, "seamspec.pin", OUTDATED, message))
    elif installed:
        found.append(_ok(c, "seamspec.pin", f"SeamSpec {installed} installed; CI pins {pinned or 'none recorded'}"))
    doctor = ssc.doctor(ctx.root)
    if doctor is not None:
        errors, warnings = doctor
        # the checks' names only: SeamSpec's own messages can name machine paths, which check never prints
        if errors:
            message = f"seamspec doctor: error in {', '.join(errors)} (seamspec doctor --json shows why)"
            found.append(_missing(c, "seamspec.doctor", message, fix="fix what seamspec doctor reports"))
        elif warnings:
            message = f"seamspec doctor: warning in {', '.join(warnings)} (seamspec doctor --json shows why)"
            found.append(_missing(c, "seamspec.doctor", message, blocking=False))
        else:
            found.append(_ok(c, "seamspec.doctor", "seamspec doctor: healthy"))
    if ctx.exists(ssc.EARNED_SPEC):
        current = ssc.run_read(["spec", "--check", ssc.EARNED_SPEC], ctx.root)
        if current is not None and current.returncode != 0:
            command = f"seamspec spec --out {ssc.EARNED_SPEC}"
            message = f"{ssc.EARNED_SPEC} is out of date: {command}"
            found.append(_missing(c, "seamspec.earned-spec-current", message, ssc.EARNED_SPEC, fix=command))
    return found


_STEPS_KEY = re.compile(r"^ *steps:\s*(?:#.*)?$")
_ITEM = re.compile(r"^(?P<dash> *-\s+)(?P<rest>.*)$")
_KEY = re.compile(r"^(?P<key>[A-Za-z_][\w-]*):(?:\s+(?P<value>.*?))?\s*$")
# uv and uvx options that take a value, so the value isn't read as the command
_OPTIONS_WITH_VALUES = frozenset({
    "--from", "--with", "--with-requirements", "--with-editable", "--python", "-p", "--project", "--directory",
    "--extra", "--group", "--env-file", "--package",
})  # fmt: skip


def _runs(text: str | None) -> list[str]:
    """The shell commands of a workflow's steps: the `run` key of each item of a `steps:` list, one line or
    a block (`|`, `>`). Step names, other keys, `env` values (even one named `run`) and comments never
    count (Copilot's review of PR #3 and #4)."""
    lines, runs, index = (text or "").splitlines(), [], 0
    steps_indent: int | None = None  # column of the current `steps:` key
    step_dash: int | None = None  # column of the dash that starts each step
    step_col: int | None = None  # column of the current step's keys
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = _indent(line)
        # a line at or left of `steps:` ends the list, except a dash at its column (a list YAML doesn't indent)
        dash_at_steps = indent == steps_indent and line.lstrip().startswith("-")
        if steps_indent is not None and indent <= steps_indent and not dash_at_steps:
            steps_indent = step_dash = step_col = None
        if steps_indent is None and _STEPS_KEY.match(line):  # a `steps:` inside a step is an argument
            steps_indent, step_dash, step_col = indent, None, None
            continue
        if steps_indent is None:
            continue
        body, col = line[indent:], indent
        item = _ITEM.match(line)
        if item:
            if step_dash is None:
                step_dash = indent
            if indent != step_dash:
                continue  # a list inside a step (`with:` arguments), not a step
            body, col = item.group("rest"), len(item.group("dash"))
            step_col = col
        key = _KEY.match(body)
        if key is None or key.group("key") != "run" or col != step_col:
            continue
        value = _without_comments(key.group("value") or "").strip()
        if value[:1] in ("|", ">"):
            block = []
            while index < len(lines) and (not lines[index].strip() or _indent(lines[index]) > col):
                block.append(lines[index].strip())
                index += 1
            runs.append((" " if value.startswith(">") else "\n").join(b for b in block if b))
        else:
            runs.append(value.strip("'\""))
    return runs


def _runs_seamspec_verify(command: str) -> bool:
    """Whether a shell command runs `seamspec verify` as a command, directly or through `uv run`, `uvx`,
    `uv tool run` or `python -m`; not as an argument (`echo seamspec verify`) or in a comment."""
    script = command.replace("\\\n", " ")
    for segment in re.split(r"&&|\|\||[;|&\n]", script):
        try:
            words = shlex.split(segment, comments=True)
        except ValueError:
            continue
        while words and re.fullmatch(r"[A-Za-z_]\w*=.*", words[0]):
            words = words[1:]  # VAR=value before the command
        while True:
            if words[:2] == ["uv", "run"]:
                words = _skip_options(words[2:])
            elif words[:3] == ["uv", "tool", "run"]:
                words = _skip_options(words[3:])
            elif words[:1] == ["uvx"]:
                words = _skip_options(words[1:])
            elif len(words) > 2 and re.fullmatch(r"python[\d.]*", words[0]) and words[1] == "-m":
                words = words[2:]
            else:
                break
        if words and re.fullmatch(r"seamspec(?:==\S+)?", words[0]) and words[1:2] == ["verify"]:
            return True
    return False


def _skip_options(words: list[str]) -> list[str]:
    while words and words[0].startswith("-"):
        words = words[2:] if words[0] in _OPTIONS_WITH_VALUES else words[1:]
    return words


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _without_comments(text: str | None) -> str:
    """YAML text without comment lines and trailing ` # comments` (a `#` inside a string may be cut too,
    which can only turn a ✓ into a ✗, never the reverse)."""
    lines = []
    for line in (text or "").splitlines():
        code = re.split(r"(?:^|\s)#", line, maxsplit=1)[0]
        lines.append(code)
    return "\n".join(lines)


CHECKERS = {
    "docs": _docs,
    "agents": _agents,
    "ci": _ci,
    "security": _security,
    "github": _github,
    "seamspec": _seamspec,
}


# --- records in .swerepo.toml ----------------------------------------------------------------------


def _record_findings(ctx: Context, chosen: list[str], store: TemplateStore) -> list[Finding]:
    assert ctx.state is not None
    found: list[Finding] = []
    hosts = ctx.state.hosts if ctx.state.hosts_chosen else list(ctx.detection.hosts)
    for kind, records in (("file", ctx.state.files()), ("block", ctx.state.blocks())):
        for path, record in sorted(records.items()):
            component = record.template.split("/", 1)[0]
            if component == "agents" and path in standard.EDITOR_FILES and not standard.editor_chosen(path, hosts):
                continue  # an editor dropped: its file is the person's now (review P8-A01)
            if component in chosen:
                found.append(_record(ctx, kind, path, record, component, store))
    return found


def _record(ctx: Context, kind: str, path: str, record: Record, component: str, store: TemplateStore) -> Finding:
    item = f"{component}.{kind}:{path}"
    text = ctx.read(path)
    if text is None:
        return _missing(component, item, f"{path} removed (SWERepo wrote it)", path)
    label = path if kind == "file" else f"{path} (SWERepo block)"
    if kind == "block":
        try:
            block = find_block(text, style=comment_style(path))
        except BlockError as error:
            return _missing(component, item, f"{path}: SWERepo block markers are broken ({error})", path, fix=MARKERS)
        if block is None:
            return _missing(component, item, f"{path}: SWERepo block removed", path)
        text = block.content
    seen = file_fingerprint(text, record.template) if kind == "file" else fingerprint(text)
    pins = ""
    if seen != record.written:
        if not (kind == "file" and path.startswith(".github/workflows/") and _only_newer_pins(store, record, text)):
            foreign = ci.foreign_note(text) if kind == "block" and Path(path).name == "pyproject.toml" else ""
            if foreign:  # another tool's table appended inside the block (review P8-A04)
                return Finding(component, item, CHANGED, f"{label}: {foreign}", path)
            return Finding(component, item, CHANGED, f"{label} changed by you (kept)", path)
        pins = ", newer action pins"
    try:
        _, name, version = parse_id(record.template)
        if github.is_builder(record.template):  # JSON built in Python, versioned like a template (ADR-4e40)
            latest = [int(github.latest(name).rsplit("@", 1)[1])]
        else:
            latest = store.versions(component, name)
    except TemplateError:
        latest = []
    if not latest:
        return Finding(component, item, UNKNOWN, f"{label}: template {record.template} isn't in this SWERepo", path)
    if latest[-1] > version:
        message = f"{label}: {record.template} → @{latest[-1]} available (swerepo update)"
        return Finding(component, item, OUTDATED, message, path)
    return _ok(component, item, f"{label} (current{pins})", path)


def _only_newer_pins(store: TemplateStore, record: Record, text: str) -> bool:
    """Whether the workflow differs from SWERepo's render only by action pins moved to newer versions (Dependabot's;
    ADR-20261123-f571 point 3): the render rebuilt exactly from the record's inputs, with update's own code. Also
    after an `update` kept a newer pin, where `written` differs from `rendered` (P6-F03): any edit of the person's
    beyond pins still counts. Reads nothing but the templates."""
    if record.inputs is None:
        return False
    base = rebuild.rebuild(store, record.template, record.inputs)
    return (
        base is not None
        and file_fingerprint(base, record.template) == record.rendered
        and merge.pins_only_newer(base, text)
    )


def _without_repeats(findings: list[Finding], records: list[Finding]) -> list[Finding]:
    """Record findings, minus a ✓ or ✗ for a path the component already reported as ✓ or ✗: one line,
    and one count, per missing file. Changed, outdated and unknown records always show, and a warning never hides
    a blocking record finding (review P8-K04)."""

    def covers(f: Finding, r: Finding) -> bool:
        same = bool(f.path) and (f.component, f.path) == (r.component, r.path)
        return same and (f.status == OK or (f.status == MISSING and (f.blocking or not r.blocking)))

    return [r for r in records if r.status not in (OK, MISSING) or not any(covers(f, r) for f in findings)]


# --- running ---------------------------------------------------------------------------------------


def chosen_components(state: State | None, detection: Detection) -> list[str]:
    if state is not None and state.components_chosen:  # an empty list chooses nothing (ADR-fc5a point 2)
        chosen = set(state.components)
    else:
        chosen = set(standard.DEFAULT_COMPONENTS)
    return [c for c in COMPONENTS if c in chosen]


def run_check(
    root: Path,
    *,
    only: list[str] | None = None,
    base: str | None = None,
    author: str | None = None,
    skip: tuple[str, ...] = (),
    store: TemplateStore | None = None,
    exclude: tuple[str, ...] = (),
    read_github: bool = False,
    local: bool = False,
) -> Report:
    """Check the repository at `root`. `exclude`: components to leave out (`--no-<component>`), from `only`
    or, without it, from the chosen ones. Raises UsageError for wrong usage (exit 2)."""
    if only is not None and not only:
        raise UsageError(f"--only needs at least one component (known: {', '.join(COMPONENTS)})")
    unknown = [c for c in [*(only or []), *exclude] if c not in COMPONENTS]
    if unknown:
        raise UsageError(f"unknown component {', '.join(unknown)} (known: {', '.join(COMPONENTS)})")
    bad_skip = [s for s in skip if s != "progress"]
    if bad_skip:
        raise UsageError(f"--skip takes 'progress', not {', '.join(bad_skip)}")
    root = root.resolve()
    if not root.is_dir():
        raise UsageError(f"{root.name}: not a folder")
    findings: list[Finding] = []

    state: State | None = None
    try:
        state = State.load(root)
    except StateError as error:
        findings.append(_missing("state", "state.read", str(error), FILE_NAME, fix=f"fix {FILE_NAME}"))
    newer = state.written_by_newer() if state else None
    if newer:
        findings.append(Finding("state", "state.newer", UNKNOWN, f"{FILE_NAME}: {newer}; upgrade SWERepo", FILE_NAME))

    detection = detect(root, ignore=state.project_ignore if state else ())
    if not detection.git.is_work_tree:
        message = "not a git repository: commit and pull-request checks skipped"
        if detection.git.nested_repos:
            message = f"this folder holds other repositories ({', '.join(detection.git.nested_repos)}): check one"
        findings.append(Finding("repository", "repository.git", UNKNOWN, message))
    elif not detection.git.is_toplevel:
        message = "a folder inside a git repository: files are looked for here, not at the repository's top"
        findings.append(Finding("repository", "repository.git", UNKNOWN, message))
    hub = github.GitHub.connect(root) if read_github else None  # read-only GET requests (ADR-20261123-4e40)
    chosen = chosen_components(state, detection)
    checking = tuple(c for c in COMPONENTS if c not in exclude and (c in only if only is not None else c in chosen))
    ctx = Context(root=root, detection=detection, state=state, hub=hub, local=local and detection.git.is_work_tree,
                  store=store or TemplateStore(), checking=checking)  # fmt: skip
    for component in COMPONENTS:
        if component in exclude or (only is not None and component not in only):
            continue
        if component not in chosen and only is None:
            findings.append(Finding(component, f"{component}.chosen", NOT_CHOSEN, "not chosen"))
            continue
        findings.extend(CHECKERS[component](ctx))
    checked = [c for c in COMPONENTS if c in (chosen if only is None else only) and c not in exclude]
    if state is not None and not newer:
        findings.extend(_without_repeats(findings, _record_findings(ctx, checked, ctx.store or TemplateStore())))
    if base is not None:
        from swerepo.prrules import pr_findings  # needs git history; kept apart from the file checks

        findings.extend(pr_findings(ctx, base=base, author=author, skip_progress="progress" in skip))
    return Report(folder=root.name, mode=state.mode if state else None, has_state=state is not None,
                  components=checked, findings=findings)  # fmt: skip


def in_github_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"
