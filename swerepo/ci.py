"""The `ci` component's renders (spec §6.2, §6.3, §11; ADR-20261122-4a06).

What `.github/workflows/swerepo-ci.yml` and SWERepo's settings block in `pyproject.toml` hold, and the values
they are rendered with. Templates hold no logic: the workflow template `ci/workflow@N` has placeholders for the
parts that vary, and its optional parts are templates at the same version number (`ci/lint@N`,
`ci/job-governance@N`, …), so one version names the whole render. This module reads files and runs read-only
git and `seamspec --version` commands; it writes nothing.
"""

from __future__ import annotations

import configparser
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

import swerepo
from swerepo.blocks import replace_block_content
from swerepo.detect import KNOWN_PYTHONS, Detection
from swerepo.fingerprint import HASH, BlockError, find_block
from swerepo.globs import Glob
from swerepo.render import Template, TemplateError, TemplateStore

WORKFLOW = "ci/workflow"
PYPROJECT = "ci/pyproject"
LINT_MODES = ("ruff", "kept", "gradual")
DEFAULT_PYTHONS = ("3.11", "3.12", "3.13", "3.14")  # a new project's `requires-python = ">=3.11"` (spec §6.2)
SEAMSPEC_PIN = "0.1.2"  # the SeamSpec standard 1 was built with, when none is installed or recorded
SWEREPO_FROM_GITHUB = "uvx --from git+https://github.com/swerepo/swerepo@main swerepo"
SWEREPO_OWN_CHECKOUT = "uv run --locked swerepo"
# The jobs `ci-ok` waits for, before the optional ones (governance, then one lint and one test job per project).
BASE_JOBS = ("lint", "test", "test-macos", "workflow-audit", "seamspec", "dependency-review")
FIXED_JOBS = frozenset({*BASE_JOBS, "governance", "copilot-review", "ci-ok"})  # names a project's jobs may never take
# Kept linters in CI, each told to skip locked SeamSpec tests on its command line (spec §6.3).
KEPT_LINT = {
    "black": "black --check --extend-exclude '\\.seamspec' .",
    "isort": "isort --check-only --extend-skip .seamspec .",
    "flake8": "flake8 --extend-exclude .seamspec",
    "pylint": "pylint --recursive=y --ignore=.seamspec .",
}
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")  # branch and folder names written into YAML unquoted
_VERSION_OUTPUT = re.compile(r"\b(\d+\.\d+(?:\.\d+)?(?:[a-z]+\d+)?)\b")


def released(version: str | None = None) -> bool:
    """Whether this SWERepo (or `version`) is one PyPI can have: not a `.dev` build and not a local version."""
    try:
        parsed = Version(version or swerepo.__version__)
    except InvalidVersion:
        return False
    return not parsed.is_devrelease and parsed.local is None


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return {}


def own_repository(root: Path) -> bool:
    """Whether this is SWERepo's own repository, which checks itself with its own checkout (spec §15)."""
    project = _read_toml(root / "pyproject.toml").get("project")
    name = project.get("name") if isinstance(project, dict) else None
    return name == "swerepo" and (root / "swerepo" / "__init__.py").is_file()


def swerepo_command(root: Path, *, with_governance: bool) -> tuple[str, str]:
    """The command CI runs SWERepo with, or "" when there is none, and a note for the plan (spec §15)."""
    if own_repository(root):
        return SWEREPO_OWN_CHECKOUT, ""
    if released():
        return f"uvx swerepo=={swerepo.__version__}", ""
    if with_governance:
        return SWEREPO_FROM_GITHUB, "installs SWERepo from its GitHub repository's main branch: pin a release later"
    return "", f"needs a released SWERepo (this is {swerepo.__version__}); --with-governance installs it from GitHub"


def _git(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False, timeout=60
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def default_branch(root: Path) -> str:
    """The branch pushes are checked on: the remote's default branch, else `main` or `master` if that is the
    branch checked out, else `main`. Only plain names are written into the workflow."""
    remote = _git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD") or ""
    if remote.startswith("origin/"):
        name = remote.removeprefix("origin/")
    else:
        current = _git(root, "branch", "--show-current") or ""
        name = current if current in ("main", "master") else "main"
    return name if _SAFE_NAME.fullmatch(name) else "main"


INSTALLS = ("uv sync", "uv sync --locked")


def _workspace_root(root: Path, base: Path) -> Path | None:
    """The uv workspace above `base` (up to the repository root) that has it as a member, if any: `uv sync` in a
    member uses the workspace's lock file, while a project outside every workspace has its own (review P4-F01)."""
    for folder in base.parents:
        if folder != root and root not in folder.parents:
            break
        uv = _tool(_read_toml(folder / "pyproject.toml"), "uv")
        workspace = uv.get("workspace") if isinstance(uv, dict) else None
        if not isinstance(workspace, dict):
            continue
        # matched as text, never through Path.glob, which raises on ".", "" or "/x" (review P4-F10)
        member = base.relative_to(folder).as_posix()
        members, excluded = (
            [g for g in workspace.get(key, []) if isinstance(g, str) and not g.startswith("/")]
            for key in ("members", "exclude")
        )
        inside = any(Glob(g).matches(member) for g in members)
        return folder if inside and not any(Glob(g).matches(member) for g in excluded) else None
    return None


def install_command(root: Path, folder: str = ".") -> tuple[str | None, str]:
    """How CI installs the project in `folder`, or None and the reason it can't (ADR-20261122-4a06 point 6)."""
    base = root / folder
    where = "" if folder == "." else f"{folder}/"
    data = _read_toml(base / "pyproject.toml")
    if not (base / "pyproject.toml").is_file():
        return None, f"no {where}pyproject.toml: swerepo-ci.yml installs the project with uv"
    if not isinstance(data.get("project"), dict):
        return None, f"{where}pyproject.toml has no [project] table: uv can't install it"
    workspace = _workspace_root(root, base) if folder != "." else None
    locked = (base / "uv.lock").is_file() or (workspace is not None and (workspace / "uv.lock").is_file())
    if (base / "poetry.lock").is_file() and not locked:
        return None, f"{where}poetry.lock: swerepo-ci.yml installs with uv; Poetry projects come in a later version"
    return ("uv sync --locked" if locked else "uv sync"), ""


_PIN = re.compile(r"^[0-9][0-9A-Za-z.+!-]*$")


def valid_pin(version: object) -> bool:
    """A version written into a workflow command: a plain PEP 440 version, nothing else (review P4-F03)."""
    if not isinstance(version, str) or not _PIN.fullmatch(version):
        return False
    try:
        Version(version)
    except InvalidVersion:
        return False
    return True


def valid_swerepo_command(command: object) -> bool:
    """One of the commands standard 1 writes for running SWERepo in CI (review P4-F03)."""
    if command in ("", SWEREPO_OWN_CHECKOUT, SWEREPO_FROM_GITHUB):
        return True
    if not isinstance(command, str) or not command.startswith("uvx swerepo=="):
        return False
    version = command.removeprefix("uvx swerepo==")
    return valid_pin(version) and released(version)


def python_versions(detection: Detection) -> tuple[list[str], str]:
    """The test matrix and a note: from `requires-python` (or classifiers), or 3.11 to 3.14 when none is declared."""
    found = list(detection.python.versions)
    if found:
        return found, ""
    if detection.python.source:
        known = f"{KNOWN_PYTHONS[0]}–{KNOWN_PYTHONS[-1]}"
        return [], f"{detection.python.source} allows none of the Python versions standard 1 knows ({known})"
    return list(DEFAULT_PYTHONS), "no requires-python declared: tests run on 3.11–3.14; declare it in pyproject.toml"


def matrix(versions: list[str]) -> str:
    return "[" + ", ".join(f'"{v}"' for v in versions) + "]"


def seamspec_pin(recorded: str | None) -> str:
    """The SeamSpec version CI pins: the recorded one, else the installed one, else standard 1's. Only a plain
    version is written into the workflow."""
    if valid_pin(recorded):
        return str(recorded)
    from swerepo import seamspec_component  # the one place SWERepo finds SeamSpec (Phase 7 review of the rules)

    command = seamspec_component.command()
    if command:
        try:
            done = subprocess.run([command, "--version"], capture_output=True, text=True, check=False, timeout=60)
            match = _VERSION_OUTPUT.search(done.stdout) if done.returncode == 0 else None
            if match and valid_pin(match[1]):
                return match[1]
        except (OSError, subprocess.TimeoutExpired):
            pass
    return SEAMSPEC_PIN


# --- what the project already configures -----------------------------------------------------------------


def without_block(text: str) -> str:
    """A TOML text without SWERepo's block content, to see what the person configured themselves."""
    try:
        if find_block(text, style=HASH) is None:
            return text
        return replace_block_content(text, "", style=HASH, marker="swerepo")
    except BlockError:
        return text


def _own_pyproject(base: Path) -> dict[str, Any]:
    try:
        text = (base / "pyproject.toml").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        return tomllib.loads(without_block(text))
    except tomllib.TOMLDecodeError:
        return {}


def _tool(data: dict[str, Any], name: str) -> Any:
    tool = data.get("tool")
    return tool.get(name) if isinstance(tool, dict) else None


def ruff_configured(root: Path, folder: str = ".", *, inherit: bool = True) -> bool:
    """Whether ruff has a configuration of the person's for `folder`: a ruff.toml, or `[tool.ruff]` outside
    SWERepo's block, in the folder or, with `inherit` (ruff looks upwards), the repository root."""
    for base in dict.fromkeys([root / folder, *([root] if inherit else [])]):
        if (base / "ruff.toml").is_file() or (base / ".ruff.toml").is_file():
            return True
        if isinstance(_tool(_own_pyproject(base), "ruff"), dict):
            return True
    return False


def pytest_configured(root: Path, folder: str = ".") -> bool:
    """Whether the project in `folder` configures pytest itself (outside SWERepo's block), spec §6.3."""
    base = root / folder
    if (base / "pytest.ini").is_file() or (base / ".pytest.ini").is_file():
        return True
    if isinstance(_tool(_own_pyproject(base), "pytest"), dict):
        return True
    for name, section in (("setup.cfg", "tool:pytest"), ("tox.ini", "pytest")):
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(base / name, encoding="utf-8")
        except (configparser.Error, UnicodeDecodeError):
            continue
        if parser.has_section(section):
            return True
    return False


def line_length(root: Path, folder: str = ".") -> str | None:
    """The line length the project's black or flake8 uses, for ruff's settings when moving to ruff (spec §6.3)."""
    base = root / folder
    black = _tool(_own_pyproject(base), "black")
    if isinstance(black, dict) and isinstance(black.get("line-length"), int):
        return str(black["line-length"])
    for name in (".flake8", "setup.cfg", "tox.ini"):
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(base / name, encoding="utf-8")
        except (configparser.Error, UnicodeDecodeError):
            continue
        value = parser.get("flake8", "max-line-length", fallback="").strip()
        if value.isdigit():
            return value
    return None


def installed_dependencies(root: Path, folder: str = ".") -> set[str]:
    """The packages `uv sync` installs for the project in `folder` (normalised names): its dependencies and its
    default dependency groups (`[tool.uv] default-groups`, else `dev`, which also holds uv's older
    `dev-dependencies`), with `include-group` followed. Extras (`[project.optional-dependencies]`) and other
    groups aren't installed by `uv sync`, so they don't count (review: Copilot on PR #8)."""
    data = _own_pyproject(root / folder)
    project = data.get("project") if isinstance(data.get("project"), dict) else {}
    groups = data.get("dependency-groups") if isinstance(data.get("dependency-groups"), dict) else {}
    uv = _tool(data, "uv") if isinstance(_tool(data, "uv"), dict) else {}
    defaults = uv.get("default-groups", ["dev"])
    if defaults == "all":
        chosen = list(groups)
    else:
        chosen = [g for g in defaults if isinstance(g, str)] if isinstance(defaults, list) else []
    found: list[Any] = list(project.get("dependencies", [])) if isinstance(project.get("dependencies"), list) else []
    if "dev" in chosen and isinstance(uv.get("dev-dependencies"), list):
        found += uv["dev-dependencies"]
    seen: set[str] = set()
    while chosen:
        group = chosen.pop()
        if group in seen:
            continue
        seen.add(group)
        for entry in groups.get(group, []) if isinstance(groups.get(group), list) else []:
            if isinstance(entry, dict) and isinstance(entry.get("include-group"), str):
                chosen.append(entry["include-group"])
            else:
                found.append(entry)
    names = set()
    for entry in found:
        if isinstance(entry, str):
            try:
                names.add(canonicalize_name(Requirement(entry).name))
            except InvalidRequirement:
                continue
    return names


# --- rendering -------------------------------------------------------------------------------------------


@dataclass
class Project:
    folder: str
    install: str
    python: list[str]
    lint: str = "ruff"  # "ruff" or "kept"
    linters: list[str] = field(default_factory=list)  # kept ones

    @property
    def lint_runs(self) -> list[str]:
        return lint_runs(self.lint, self.linters)

    @property
    def inputs(self) -> dict[str, str | list[str]]:
        """What `.swerepo.toml` records for this project (`[projects.inputs."<folder>"]`)."""
        return {"python": self.python, "install": self.install, "lint": self.lint, "linters": self.linters}

    @classmethod
    def from_inputs(cls, folder: str, values: dict[str, Any]) -> Project | None:
        """A project from its recorded inputs, or None if they aren't ones standard 1 writes (P4-F03)."""
        python, install = values.get("python"), values.get("install")
        lint, linters = values.get("lint"), values.get("linters", [])
        if not (isinstance(python, list) and python and all(v in KNOWN_PYTHONS for v in python)):
            return None
        if install not in INSTALLS or lint not in ("ruff", "kept"):
            return None
        if not isinstance(linters, list) or not all(name in KEPT_LINT for name in linters):
            return None
        if lint == "kept" and not linters:
            return None
        return cls(folder, str(install), [str(v) for v in python], str(lint), [str(n) for n in linters])

    @property
    def job(self) -> str:
        return re.sub(r"[^a-z0-9-]+", "-", self.folder.lower()).strip("-")


@dataclass
class Inputs:
    """What swerepo-ci.yml is rendered from (recorded in `.swerepo.toml` so `update` can rebuild it)."""

    default_branch: str
    install: str
    python: list[str]
    lint: str  # one of LINT_MODES
    linters: list[str] = field(default_factory=list)  # kept ones, when lint == "kept"
    swerepo: str = ""  # the governance job's SWERepo command; "" for no governance job
    seamspec: str = SEAMSPEC_PIN
    projects: list[Project] = field(default_factory=list)
    copilot_review: bool = False  # merges wait for Copilot's review (ADR-20261123-a359; from the github component)


def lint_runs(lint: str, linters: list[str]) -> list[str]:
    """The lint job's commands: ruff's two, or each kept linter's."""
    if lint == "kept":
        return [f"uv run {KEPT_LINT[name]}" for name in sorted(linters) if name in KEPT_LINT]
    return ["uv run ruff check .", "uv run ruff format --check ."]


def _steps(commands: list[str]) -> str:
    return "\n".join(f"      - run: {command}" for command in commands)


def _fragment(store: TemplateStore, name: str, version: int, values: dict[str, str]) -> str:
    return store.get(f"ci/{name}@{version}").render(values).rstrip("\n")


def workflow_template(store: TemplateStore) -> Template:
    return store.latest(*WORKFLOW.split("/"))


def render_workflow(store: TemplateStore, inputs: Inputs, version: int | None = None) -> tuple[str, str]:
    """(template id, text) of swerepo-ci.yml."""
    template = store.get(f"{WORKFLOW}@{version}") if version else workflow_template(store)
    main = inputs.python[-1]
    values = {"python_main": main, "install": inputs.install}
    if inputs.lint == "gradual":
        lint_steps = _fragment(store, "lint-gradual", template.version, values)
    else:
        runs = _steps(lint_runs(inputs.lint, inputs.linters))
        lint_steps = _fragment(store, "lint", template.version, {**values, "lint_runs": runs})
    jobs, needs = [], list(BASE_JOBS)
    if inputs.swerepo:
        jobs.append(_fragment(store, "job-governance", template.version, {**values, "swerepo": inputs.swerepo}))
        needs.append("governance")
    if inputs.copilot_review:
        if template.version < 2:
            raise TemplateError(f"{template.id} has no copilot-review job: it comes with ci/workflow@2")
        jobs.append(_fragment(store, "job-copilot-review", template.version, {}))
        needs.append("copilot-review")
    for project in inputs.projects:
        project_values = {
            "folder": project.folder,
            "job": project.job,
            "install": project.install,
            "python_main": project.python[-1],
            "python_matrix": matrix(project.python),
            "lint_runs": _steps(project.lint_runs),
        }
        jobs.append(_fragment(store, "job-project", template.version, project_values))
        needs += [f"lint-{project.job}", f"test-{project.job}"]
    text = template.render(
        {
            **values,
            "default_branch": inputs.default_branch,
            "python_matrix": matrix(inputs.python),
            "lint_steps": lint_steps,
            "seamspec": inputs.seamspec,
            "optional_jobs": ("\n" + "\n\n".join(jobs) + "\n") if jobs else "",
            "ci_ok_needs": "[" + ", ".join(needs) + "]",
        }
    )
    return template.id, text


def settings_block(
    store: TemplateStore, *, ruff: bool, pytest: bool, ruff_line_length: str | None, version: int | None = None
) -> tuple[str, str] | None:
    """(template id, block content) of SWERepo's settings in a pyproject.toml, or None when it needs none."""
    template = store.get(f"{PYPROJECT}@{version}") if version else store.latest(*PYPROJECT.split("/"))
    tables = []
    if ruff:
        length = f"line-length = {ruff_line_length}" if ruff_line_length else "# line-length: ruff's default"
        tables.append(_fragment(store, "ruff", template.version, {"ruff_line_length": length}))
    if pytest:
        tables.append(_fragment(store, "pytest", template.version, {}))
    if not tables:
        return None
    return template.id, template.render({"tables": "\n\n".join(tables)})


def valid_folder(folder: str) -> bool:
    """A project folder SWERepo can write into a workflow: plain names, relative, no `..`."""
    parts = folder.split("/")
    return bool(_SAFE_NAME.fullmatch(folder)) and all(p not in ("", ".", "..") for p in parts)
