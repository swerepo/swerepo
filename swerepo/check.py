"""`swerepo check`: what a repository meets, misses, or has changed (SWEREPO-SPEC §15; ADR-20261120-fc5a).

Read-only. Findings are computed first, then printed as text or JSON, so both say the same thing.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from swerepo import __version__, ci, privacy, standard
from swerepo.blocks import file_fingerprint
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


@dataclass(frozen=True)
class Finding:
    component: str
    item: str
    status: str
    message: str
    path: str | None = None
    blocking: bool = False  # a missing item that fails `check`; a warning is missing but doesn't block


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
        gaps = {f.component for f in self.findings if f.blocking}
        for group in standard.RECOMMENDED_ORDER:
            chosen = [c for c in group if c in gaps]
            if chosen:
                return f"swerepo init --only {','.join(chosen)}"
        return None

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


def _missing(component: str, item: str, message: str, path: str | None = None, *, blocking: bool = True) -> Finding:
    return Finding(component, item, MISSING, message, path, blocking)


def _present(ctx: Context, component: str, item: str, path: str, what: str | None = None) -> Finding:
    if ctx.exists(path):
        return _ok(component, item, f"{what} ({path})" if what else path, path)
    return _missing(component, item, f"{what} missing ({path})" if what else f"{path} missing", path)


# --- components ------------------------------------------------------------------------------------


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

    changelog = d.documents.get("changelog")
    if not changelog:
        found.append(_missing(c, "docs.changelog", "CHANGELOG.md missing", "CHANGELOG.md"))
    elif _UNRELEASED.search(ctx.read(changelog) or ""):
        found.append(_ok(c, "docs.changelog", f"{changelog} has [Unreleased]", changelog))
    else:
        found.append(_missing(c, "docs.changelog", f"{changelog} has no [Unreleased] section", changelog))

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
        return [_missing("docs", "docs.adr-index", f"{readme}: ADR index markers are broken ({error})", readme)]
    if block is None:
        return [_missing("docs", "docs.adr-index", f"{readme} has no generated ADR index", readme)]
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
    return [_missing("docs", "docs.adr-index", f"ADR index out of date ({'; '.join(problems)})", readme)]


def _block_finding(component: str, item: str, path: str, text: str) -> Finding:
    try:
        block = find_block(text, style=comment_style(path))
    except BlockError as error:
        return _missing(component, item, f"{path}: SWERepo block markers are broken ({error})", path)
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
    absent = [path for path in standard.RUNBOOKS if not ctx.exists(path)]
    if absent:
        names = ", ".join(Path(p).name for p in absent)
        found.append(_missing(c, "agents.runbooks", f"docs/agents/ runbooks missing: {names}", "docs/agents"))
    else:
        found.append(_ok(c, "agents.runbooks", "docs/agents/ runbooks", "docs/agents"))
    return found


def _ci(ctx: Context) -> list[Finding]:
    c, d = "ci", ctx.detection
    found: list[Finding] = []
    text = ctx.read(standard.CI_WORKFLOW)
    if text is None:
        others = [w.path.rsplit("/", 1)[-1] for w in d.workflows if w.runs_pytest]
        note = f" (you run pytest in {', '.join(others)}: kept)" if others else ""
        found.append(_missing(c, "ci.workflow", f"swerepo-ci.yml missing{note}", standard.CI_WORKFLOW))
    else:
        found.append(_ok(c, "ci.workflow", "swerepo-ci.yml", standard.CI_WORKFLOW))
        found.append(_ci_ok(text))
        found.extend(_python_matrix(ctx, text))

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
        found.append(_missing(c, "ci.linter", "no linter or formatter configured (ruff, or the project's own)"))
    if d.seamspec:
        found.append(_seamspec_excluded(ctx, detected))
    if d.is_monorepo or (ctx.state is not None and ctx.state.projects_listed):
        found.extend(_projects_covered(ctx, text or ""))
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


def _ci_ok(text: str) -> Finding:
    """`ci-ok` waits for every other job (spec §6.2): the ruleset requires only it."""
    c, item = "ci", "ci.ci-ok"
    jobs = workflow_jobs(text)
    if "ci-ok" not in jobs:
        return _missing(c, item, "swerepo-ci.yml has no ci-ok job", standard.CI_WORKFLOW)
    left_out = [job for job in jobs if job != "ci-ok" and job not in jobs["ci-ok"]]
    if left_out:
        message = f"ci-ok doesn't wait for {', '.join(left_out)}: a failure there wouldn't block a merge"
        return _missing(c, item, message, standard.CI_WORKFLOW)
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
            message = (f"{folder}/ is listed, but swerepo-ci.yml lacks its lint or test job: "
                       f"swerepo init --only ci --projects {','.join(listed)}")  # fmt: skip
            found.append(_missing(c, item, message, folder))
        elif folder in skipped:
            found.append(_ok(c, item, f"{folder}/ recorded as not covered", folder))
        elif extra:
            message = f"{folder}/: whether [github] extra_required_checks cover it can't be told from files"
            found.append(Finding(c, item, UNKNOWN, message, folder))
        else:
            found.append(_missing(c, item, f"{folder}/ not covered by any required check", folder))
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
        return _missing(c, item, message, source)
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
        how = "" if ci.released() else ": needs a released SWERepo, or swerepo init --with-governance"
        message = f"privacy workflow missing ({standard.PRIVACY_WORKFLOW}){how}"
        found.append(_missing(c, "security.workflow", message, standard.PRIVACY_WORKFLOW))
    text = ctx.read(".gitignore")
    if text is None:
        found.append(_missing(c, "security.gitignore", ".gitignore missing", ".gitignore"))
    else:
        found.append(_block_finding(c, "security.gitignore", ".gitignore", text))
    hits = privacy.scan(ctx.root, ctx.state.privacy_allow_paths if ctx.state else [])
    if hits:
        found.append(_missing(c, "security.privacy-scan", privacy.summary(hits), hits[0].path))
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
    found.extend(_commit_email(ctx))
    return found


def _codeowners(ctx: Context, path: str | None) -> Finding:
    c, item = "github", "github.codeowners"
    if path is None:
        return _missing(c, item, "CODEOWNERS missing (.github/CODEOWNERS)", ".github/CODEOWNERS")
    text = ctx.read(path) or ""
    try:
        block = find_block(text, style=HASH)
    except BlockError as error:
        return _missing(c, item, f"{path}: SWERepo block markers are broken ({error})", path)
    if block is None:
        return _missing(c, item, f"{path} has no SWERepo block (governance owners)", path)
    after = [line for line in text.splitlines()[block.end_line :] if line.strip() and not line.lstrip().startswith("#")]
    if after:
        # path patterns only, never owners: a malformed line may start with an @handle or an email address
        patterns = ", ".join(token for line in after if "@" not in (token := line.split()[0]))
        named = f" ({patterns})" if patterns else ""
        message = f"{path}: rules after the SWERepo block can override governance owners{named}"
        return Finding(c, item, CHANGED, message, path)
    return _ok(c, item, f"{path}: governance block last", path)


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
        found.append(_missing(c, "seamspec.mode", message, ".seamspec/config.toml"))
    found.append(_present(ctx, c, "seamspec.earned-spec", standard.EARNED_SPEC))
    runners = [
        w.path for w in ctx.detection.workflows if any(_runs_seamspec_verify(r) for r in _runs(ctx.read(w.path)))
    ]
    if runners:
        found.append(_ok(c, "seamspec.ci", f"CI runs the locked rules ({', '.join(Path(p).name for p in runners)})"))
    else:
        found.append(_missing(c, "seamspec.ci", "no workflow runs `seamspec verify`"))
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


def _openspec(ctx: Context) -> list[Finding]:
    if ctx.detection.openspec:
        return [_ok("openspec", "openspec.setup", "OpenSpec set up", "openspec")]
    return [_missing("openspec", "openspec.setup", "OpenSpec not set up", "openspec")]


def _release(ctx: Context) -> list[Finding]:
    return [_present(ctx, "release", "release.workflow", standard.RELEASE_WORKFLOW, "release workflow")]


CHECKERS = {
    "docs": _docs,
    "agents": _agents,
    "ci": _ci,
    "security": _security,
    "github": _github,
    "seamspec": _seamspec,
    "openspec": _openspec,
    "release": _release,
}


# --- records in .swerepo.toml ----------------------------------------------------------------------


def _record_findings(ctx: Context, chosen: list[str], store: TemplateStore) -> list[Finding]:
    assert ctx.state is not None
    found: list[Finding] = []
    for kind, records in (("file", ctx.state.files()), ("block", ctx.state.blocks())):
        for path, record in sorted(records.items()):
            component = record.template.split("/", 1)[0]
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
            return _missing(component, item, f"{path}: SWERepo block markers are broken ({error})", path)
        if block is None:
            return _missing(component, item, f"{path}: SWERepo block removed", path)
        text = block.content
    seen = file_fingerprint(text, record.template) if kind == "file" else fingerprint(text)
    if seen != record.written:
        return Finding(component, item, CHANGED, f"{label} changed by you (kept)", path)
    try:
        _, name, version = parse_id(record.template)
        latest = store.versions(component, name)
    except TemplateError:
        latest = []
    if not latest:
        return Finding(component, item, UNKNOWN, f"{label}: template {record.template} isn't in this SWERepo", path)
    if latest[-1] > version:
        message = f"{label}: {record.template} → @{latest[-1]} available (swerepo update)"
        return Finding(component, item, OUTDATED, message, path)
    return _ok(component, item, f"{label} (current)", path)


def _without_repeats(findings: list[Finding], records: list[Finding]) -> list[Finding]:
    """Record findings, minus a ✓ or ✗ for a path the component already reported as ✓ or ✗: one line,
    and one count, per missing file. Changed, outdated and unknown records always show."""
    reported = {(f.component, f.path) for f in findings if f.path and f.status in (OK, MISSING)}
    return [r for r in records if r.status not in (OK, MISSING) or (r.component, r.path) not in reported]


# --- running ---------------------------------------------------------------------------------------


def chosen_components(state: State | None, detection: Detection) -> list[str]:
    if state is not None and state.components_chosen:  # an empty list chooses nothing (ADR-fc5a point 2)
        chosen = set(state.components)
    else:
        chosen = set(standard.DEFAULT_COMPONENTS)
        if detection.openspec:
            chosen.add("openspec")
        if any(w.path == standard.RELEASE_WORKFLOW for w in detection.workflows):
            chosen.add("release")
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
        findings.append(_missing("state", "state.read", str(error), FILE_NAME))
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
    ctx = Context(root=root, detection=detection, state=state)

    chosen = chosen_components(state, detection)
    for component in COMPONENTS:
        if component in exclude or (only is not None and component not in only):
            continue
        if component not in chosen and only is None:
            findings.append(Finding(component, f"{component}.chosen", NOT_CHOSEN, "not chosen"))
            continue
        findings.extend(CHECKERS[component](ctx))
        for item, what, phase in standard.LATER.get(component, ()):
            findings.append(Finding(component, item, UNKNOWN, f"{what}: checked from Phase {phase}"))
    checked = [c for c in COMPONENTS if c in (chosen if only is None else only) and c not in exclude]
    if state is not None and not newer:
        findings.extend(_without_repeats(findings, _record_findings(ctx, checked, store or TemplateStore())))
    if base is not None:
        from swerepo.prrules import pr_findings  # needs git history; kept apart from the file checks

        findings.extend(pr_findings(ctx, base=base, author=author, skip_progress="progress" in skip))
    return Report(folder=root.name, mode=state.mode if state else None, has_state=state is not None,
                  components=checked, findings=findings)  # fmt: skip


def in_github_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"
