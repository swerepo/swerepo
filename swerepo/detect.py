"""What a repository already has, before any plan (spec §10, §11; ADR-20261120-25b5).

Read-only: reads files and runs `git ls-files`, never writes, installs or uses the network. Problems
with the repository's own files (invalid TOML, an unreadable `requires-python`) are reported in
`Detection.errors`, never raised.
"""

from __future__ import annotations

import configparser
import json
import os
import re
import subprocess
import tomllib
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet

# Python minor versions standard 1 knows, oldest first.
KNOWN_PYTHONS = ("3.8", "3.9", "3.10", "3.11", "3.12", "3.13", "3.14")

# Folders that hold fixtures, examples or tooling, never shipped projects (ADR-20261120-25b5).
NON_PROJECT_DIRS = frozenset(
    {
        "tests",
        "test",
        "testing",
        "fixtures",
        "examples",
        "example",
        "docs",
        "doc",
        "tools",
        "scripts",
        "vendor",
        "third_party",
    }
)
# Never walked when git can't list the files.
SKIP_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", ".venv", "venv", ".tox", ".nox", "node_modules", "__pycache__",
        ".pytest_cache", ".ruff_cache", ".mypy_cache", "build", "dist", ".eggs", "site-packages",
    }
)  # fmt: skip

# Files that make their folder a project (ADR-20261120-25b5, review finding P1-F01).
PYTHON_MANIFESTS = frozenset({"pyproject.toml", "setup.py", "Pipfile"})
# setup.cfg and requirements*.txt make a sub-folder a Python project only beside Python source: on their
# own they are often just configuration (`ci/requirements.txt`). At the repository root they always count.
OTHER_MANIFESTS = {
    "tsconfig.json": "typescript", "package.json": "javascript", "go.mod": "go", "Cargo.toml": "rust",
    "pom.xml": "java", "build.gradle": "java", "build.gradle.kts": "java", "Gemfile": "ruby",
}  # fmt: skip
# When a folder has manifests of several kinds, the first in this order names it.
KIND_ORDER = ("python", "typescript", "javascript", "go", "rust", "java", "ruby")
LANGUAGE_MARKERS = {
    "pyproject.toml": "python", "setup.py": "python", "setup.cfg": "python", "uv.lock": "python",
    "poetry.lock": "python", "Pipfile": "python", "requirements.txt": "python",
    "package.json": "javascript", "tsconfig.json": "typescript", "go.mod": "go", "Cargo.toml": "rust",
    "pom.xml": "java", "build.gradle": "java", "build.gradle.kts": "java", "Gemfile": "ruby",
}  # fmt: skip
ADR_DIRS = ("docs/adr", "doc/adr", "docs/decisions", "doc/decisions", "docs/architecture/decisions", "adr")
NOT_ADRS = frozenset({"readme.md", "template.md", "index.md"})
DOCUMENTS = {
    "readme": ("README.md", "README.rst", "README.txt", "README"),
    "changelog": ("CHANGELOG.md", "CHANGES.md", "HISTORY.md", "NEWS.md", "CHANGELOG.rst", "CHANGES.rst"),
    "contributing": ("CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md", "CONTRIBUTING.rst"),
    "security": ("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md"),
    "license": ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"),
    "codeowners": (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"),
    "progress": ("docs/PROGRESS.md", "PROGRESS.md"),
    "pr_template": (".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md", "pull_request_template.md"),
}
AGENT_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursorrules", ".github/copilot-instructions.md")
OTHER_CI = (
    ".gitlab-ci.yml", ".circleci/config.yml", "azure-pipelines.yml", "Jenkinsfile", ".travis.yml",
    "bitbucket-pipelines.yml",
)  # fmt: skip
LINTERS = ("ruff", "black", "isort", "flake8", "pylint")
_PRE_COMMIT_ID = re.compile(r"^\s*(?:-\s*)?id:\s*['\"]?(ruff|ruff-format|ruff-check|black|isort|flake8|pylint)\b", re.M)
_CLASSIFIER = re.compile(r"^Programming Language :: Python :: (3\.\d+)$")


@dataclass(frozen=True)
class GitInfo:
    is_work_tree: bool  # inside a git work tree
    is_toplevel: bool  # the folder is the work tree's top level
    nested_repos: tuple[str, ...]  # other repositories inside the folder (up to two levels down)
    listed_by: str  # "git" or "walk"


@dataclass(frozen=True)
class PythonInfo:
    versions: tuple[str, ...]  # supported minor versions, from KNOWN_PYTHONS
    source: str | None  # where they were read, e.g. "pyproject.toml [project] requires-python"
    declared: str | None  # the declaration as written


@dataclass(frozen=True)
class ProjectRoot:
    path: str  # "." for the repository root
    kind: str  # one of KIND_ORDER: "python", "typescript", "javascript", "go", "rust", "java", "ruby"


@dataclass(frozen=True)
class SkippedProject:
    path: str
    reason: str


@dataclass(frozen=True)
class Workflow:
    path: str
    runs_pytest: bool
    runs_ruff: bool


@dataclass(frozen=True)
class AdrDir:
    path: str
    count: int


@dataclass(frozen=True)
class Linter:
    name: str
    configured_in: tuple[str, ...]


@dataclass(frozen=True)
class Detection:
    git: GitInfo
    languages: tuple[str, ...]
    python: PythonInfo
    projects: tuple[ProjectRoot, ...]  # the repository root first, when it is a project
    skipped_projects: tuple[SkippedProject, ...]
    is_monorepo: bool
    workflows: tuple[Workflow, ...]
    other_ci: tuple[str, ...]
    documents: dict[str, str]  # kind -> path, for each kind found
    adr_dirs: tuple[AdrDir, ...]
    agent_files: tuple[str, ...]
    hosts: tuple[str, ...]  # editors in use: claude, cursor, vscode, antigravity
    linters: tuple[Linter, ...]
    pytest_configured: bool
    seamspec: bool
    openspec: bool
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Plain JSON data (lists, not tuples) for `--json`; holds only repository-relative paths."""
        return json.loads(json.dumps(asdict(self)))


def detect(root: Path, *, ignore: tuple[str, ...] | list[str] = ()) -> Detection:
    """Detect what the repository at `root` has. `ignore`: extra folders that are not projects
    (`[projects] ignore` in `.swerepo.toml`)."""
    root = root.resolve()
    errors: list[str] = []
    git = _git_info(root)
    files = _git_files(root) if git.is_work_tree else None
    if files is None:  # not a work tree, or git couldn't list the files
        files = _walk_files(root)
        git = replace(git, listed_by="walk")
    present = set(files)

    pyproject = _read_toml(root, "pyproject.toml", errors) if "pyproject.toml" in present else {}
    setup_cfg = _read_ini(root, "setup.cfg", errors) if "setup.cfg" in present else None
    tox_ini = _read_ini(root, "tox.ini", errors) if "tox.ini" in present else None

    projects, skipped = _projects(files, ignore)
    return Detection(
        git=git,
        languages=_languages(files, projects),
        python=_python(pyproject, setup_cfg, errors),
        projects=projects,
        skipped_projects=skipped,
        is_monorepo=any(p.path != "." for p in projects),
        workflows=_workflows(root, files),
        other_ci=tuple(path for path in OTHER_CI if path in present),
        documents={
            kind: next(p for p in paths if p in present) for kind, paths in DOCUMENTS.items() if present & set(paths)
        },
        adr_dirs=_adr_dirs(files),
        agent_files=_agent_files(present, files),
        hosts=_hosts(root, files),
        linters=_linters(root, present, pyproject, setup_cfg, tox_ini),
        pytest_configured=_pytest_configured(present, pyproject, setup_cfg, tox_ini),
        seamspec=(root / ".seamspec" / "config.toml").is_file(),
        openspec=(root / "openspec").is_dir(),
        errors=tuple(errors),
    )


# --- listing files -------------------------------------------------------------------------------


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False, timeout=60
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return None


def _git_info(root: Path) -> GitInfo:
    nested = _nested_repos(root)
    result = _git(root, "rev-parse", "--show-toplevel")
    if result is None or result.returncode != 0:
        return GitInfo(is_work_tree=False, is_toplevel=False, nested_repos=nested, listed_by="walk")
    toplevel = Path(result.stdout.strip()).resolve()
    return GitInfo(is_work_tree=True, is_toplevel=toplevel == root, nested_repos=nested, listed_by="git")


def _git_files(root: Path) -> list[str] | None:
    """Tracked files plus untracked files that aren't ignored, that exist on disk, relative to root;
    None if git couldn't list them."""
    result = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if result is None or result.returncode != 0:
        return None
    names = [n for n in result.stdout.split("\0") if n]
    return sorted({name for name in names if (root / name).is_file()})


def _walk_files(root: Path) -> list[str]:
    found = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        base = Path(folder).relative_to(root)
        found.extend((base / name).as_posix() for name in names)
    return sorted(found)


def _nested_repos(root: Path, depth: int = 2) -> tuple[str, ...]:
    found: list[str] = []

    def visit(folder: Path, level: int) -> None:
        try:
            entries = sorted(os.scandir(folder), key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False) or entry.name in SKIP_DIRS:
                continue
            path = Path(entry.path)
            if (path / ".git").exists():
                found.append(path.relative_to(root).as_posix())
            elif level < depth:
                visit(path, level + 1)

    visit(root, 1)
    return tuple(found)


# --- reading project files -----------------------------------------------------------------------


def _read_toml(root: Path, name: str, errors: list[str]) -> dict[str, Any]:
    try:
        return tomllib.loads((root / name).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        errors.append(f"{name}: can't read it: {error}")
        return {}


def _read_ini(root: Path, name: str, errors: list[str]) -> configparser.ConfigParser | None:
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string((root / name).read_text(encoding="utf-8"), source=name)
    except (OSError, UnicodeDecodeError, configparser.Error) as error:
        errors.append(f"{name}: can't read it: {error}")
        return None
    return parser


# Patch releases probed per minor version: enough for pins (==3.11.4) and patch ranges (>=3.12.1,<3.12.8).
_PATCHES = (*range(30), 99)


def _supported(specifier: SpecifierSet) -> tuple[str, ...]:
    """Minor versions the specifier allows at least one patch release of."""
    return tuple(v for v in KNOWN_PYTHONS if any(specifier.contains(f"{v}.{patch}") for patch in _PATCHES))


def _python(pyproject: dict[str, Any], setup_cfg: configparser.ConfigParser | None, errors: list[str]) -> PythonInfo:
    project = pyproject.get("project", {}) if isinstance(pyproject.get("project"), dict) else {}
    declarations: list[tuple[str, str]] = []
    if isinstance(project.get("requires-python"), str):
        declarations.append(("pyproject.toml [project] requires-python", project["requires-python"]))
    if setup_cfg is not None and setup_cfg.has_option("options", "python_requires"):
        declarations.append(("setup.cfg [options] python_requires", setup_cfg.get("options", "python_requires")))
    for source, declared in declarations:
        try:
            return PythonInfo(versions=_supported(SpecifierSet(declared.strip())), source=source, declared=declared)
        except InvalidSpecifier:
            errors.append(f"{source}: {declared!r} is not a version specifier")
    classifiers = project.get("classifiers", [])
    if isinstance(classifiers, list):
        versions = {m[1] for c in classifiers if isinstance(c, str) and (m := _CLASSIFIER.fullmatch(c.strip()))}
        if versions:
            ordered = tuple(v for v in KNOWN_PYTHONS if v in versions)
            return PythonInfo(
                versions=ordered, source="pyproject.toml classifiers", declared=", ".join(sorted(versions))
            )
    return PythonInfo(versions=(), source=None, declared=None)


# --- projects and languages ----------------------------------------------------------------------


def _under(path: PurePosixPath, folder: str) -> bool:
    folder_parts = PurePosixPath(folder).parts
    if not folder_parts:  # "" or ".": never "everything"
        return False
    return path.parts[: len(folder_parts)] == folder_parts


def _projects(
    files: list[str], ignore: tuple[str, ...] | list[str]
) -> tuple[tuple[ProjectRoot, ...], tuple[SkippedProject, ...]]:
    # Folders with Python source anywhere below them (package and src/ layouts, review finding P1-F08),
    # not counting source under conventional non-project folders (ci/scripts/lint.py doesn't make ci/ one).
    python_source = {
        parent.as_posix()
        for name in files
        if name.endswith(".py") and not NON_PROJECT_DIRS.intersection(PurePosixPath(name).parts)
        for parent in PurePosixPath(name).parents
    }
    kinds: dict[str, set[str]] = {}
    skipped: dict[str, str] = {}
    for name in files:
        path = PurePosixPath(name)
        folder = path.parent
        key = folder.as_posix()
        kind = _manifest_kind(path.name, beside_python=key == "." or key in python_source)
        if kind is None:
            continue
        conventional = next((part for part in folder.parts if part in NON_PROJECT_DIRS), None)
        listed = next((f for f in ignore if _under(folder, f)), None)
        if key != "." and conventional:
            skipped[key] = f"under {conventional}/"
        elif key != "." and listed:
            skipped[key] = f"listed in [projects] ignore ({listed})"
        else:
            kinds.setdefault(key, set()).add(kind)
    ordered = sorted(kinds.items(), key=lambda item: (item[0] != ".", item[0]))
    projects = tuple(ProjectRoot(path=path, kind=next(k for k in KIND_ORDER if k in found)) for path, found in ordered)
    return projects, tuple(SkippedProject(path=p, reason=r) for p, r in sorted(skipped.items()))


def _manifest_kind(name: str, *, beside_python: bool) -> str | None:
    if name in PYTHON_MANIFESTS:
        return "python"
    if name == "setup.cfg" or (name.startswith("requirements") and name.endswith(".txt")):
        return "python" if beside_python else None
    return OTHER_MANIFESTS.get(name)


def _languages(files: list[str], projects: tuple[ProjectRoot, ...]) -> tuple[str, ...]:
    folders = {p.path for p in projects} | {"."}
    found = set()
    for name in files:
        path = PurePosixPath(name)
        language = LANGUAGE_MARKERS.get(path.name)
        if path.name.startswith("requirements") and path.suffix == ".txt":
            language = "python"
        if language and path.parent.as_posix() in folders:
            found.add(language)
    return tuple(sorted(found))


# --- CI, documents, agents -----------------------------------------------------------------------


def _workflows(root: Path, files: list[str]) -> tuple[Workflow, ...]:
    found = []
    for name in files:
        path = PurePosixPath(name)
        if path.parent.as_posix() == ".github/workflows" and path.suffix in (".yml", ".yaml"):
            try:
                text = (root / name).read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            found.append(Workflow(name, bool(re.search(r"\bpytest\b", text)), bool(re.search(r"\bruff\b", text))))
    return tuple(found)


def _adr_dirs(files: list[str]) -> tuple[AdrDir, ...]:
    found = []
    for folder in ADR_DIRS:
        count = sum(
            1
            for name in files
            if PurePosixPath(name).parent.as_posix() == folder
            and name.endswith(".md")
            and PurePosixPath(name).name.lower() not in NOT_ADRS
        )
        if count or any(_under(PurePosixPath(name), folder) for name in files):
            found.append(AdrDir(path=folder, count=count))
    return tuple(found)


def _agent_files(present: set[str], files: list[str]) -> tuple[str, ...]:
    found = [name for name in AGENT_FILES if name in present]
    if any(name.startswith(".cursor/rules/") for name in files):
        found.append(".cursor/rules")
    return tuple(found)


def _hosts(root: Path, files: list[str]) -> tuple[str, ...]:
    def has(name: str) -> bool:
        return name in files or (root / name).exists()

    hosts = []
    if has("CLAUDE.md") or (root / ".claude").is_dir():
        hosts.append("claude")
    if has(".cursorrules") or (root / ".cursor").is_dir():
        hosts.append("cursor")
    # Not .github/copilot-instructions.md: SWERepo writes it for Copilot review on GitHub, whatever the
    # editor (review finding P1-F05).
    if (root / ".vscode").is_dir() or any(name.startswith(".vscode/") for name in files):
        hosts.append("vscode")
    if has("GEMINI.md") or (root / ".agents").is_dir() or (root / ".agent").is_dir():
        hosts.append("antigravity")
    return tuple(hosts)


# --- linters and pytest --------------------------------------------------------------------------


def _tool(pyproject: dict[str, Any], name: str) -> bool:
    tool = pyproject.get("tool")
    return isinstance(tool, dict) and name in tool


def _linters(
    root: Path,
    present: set[str],
    pyproject: dict[str, Any],
    setup_cfg: configparser.ConfigParser | None,
    tox_ini: configparser.ConfigParser | None,
) -> tuple[Linter, ...]:
    where: dict[str, list[str]] = {name: [] for name in LINTERS}
    for name in LINTERS:
        if _tool(pyproject, name):
            where[name].append(f"pyproject.toml [tool.{name}]")
    for file_name, linter in (
        ("ruff.toml", "ruff"), (".ruff.toml", "ruff"), (".isort.cfg", "isort"), (".flake8", "flake8"),
        (".pylintrc", "pylint"), ("pylintrc", "pylint"),
    ):  # fmt: skip
        if file_name in present:
            where[linter].append(file_name)
    for parser, file_name in ((setup_cfg, "setup.cfg"), (tox_ini, "tox.ini")):
        for section in parser.sections() if parser is not None else ():
            linter = _INI_SECTIONS.get(section) or ("pylint" if section.startswith("pylint.") else None)
            if linter and f"{file_name} [{section.split('.')[0]}]" not in where[linter]:
                where[linter].append(f"{file_name} [{section.split('.')[0]}]")
    if ".pre-commit-config.yaml" in present:
        try:
            text = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        for hook in sorted(set(_PRE_COMMIT_ID.findall(text))):
            linter = "ruff" if hook.startswith("ruff") else hook
            if ".pre-commit-config.yaml" not in where[linter]:
                where[linter].append(".pre-commit-config.yaml")
    return tuple(Linter(name, tuple(places)) for name, places in where.items() if places)


_INI_SECTIONS = {"flake8": "flake8", "isort": "isort", "tool:isort": "isort", "pylint": "pylint"}


def _pytest_configured(
    present: set[str],
    pyproject: dict[str, Any],
    setup_cfg: configparser.ConfigParser | None,
    tox_ini: configparser.ConfigParser | None,
) -> bool:
    tool = pyproject.get("tool")
    in_pyproject = isinstance(tool, dict) and isinstance(tool.get("pytest"), dict)
    return (
        "pytest.ini" in present
        or ".pytest.ini" in present
        or in_pyproject
        or (setup_cfg is not None and setup_cfg.has_section("tool:pytest"))
        or (tox_ini is not None and tox_ini.has_section("pytest"))
    )
