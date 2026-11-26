"""The `seamspec` component (spec §6.8, §13; ADR-20261124-cd64).

SWERepo uses SeamSpec only through its public command line, and reads SeamSpec's own files to know where it stands:
`.seamspec/config.toml` for the mode, and the ledger's `.seamspec/invariants/*.json` for each rule's status and origin.
Reading never writes. `seamspec init` runs only in the person's terminal, never with `--accept-auto-run`; SWERepo
never installs, upgrades or trusts SeamSpec for the person.

The hygiene rules are tests SWERepo ships as versioned templates (`seamspec/hygiene-<name>@<version>`), proposed
with `seamspec propose --json -` and the origin reference `swerepo:hygiene/<name>@<version>`, so a later run
recognises them. A rule the repository already locks for the same behaviour is adopted instead (`[seamspec.adopted]`).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from packaging.version import InvalidVersion, Version

from swerepo.blocks import ADR_INDEX, inside
from swerepo.fingerprint import HTML, BlockError, find_block
from swerepo.state import HYGIENE_RULES

CONFIG = ".seamspec/config.toml"
INVARIANTS = ".seamspec/invariants"
WORKFLOW = ".github/workflows/seamspec.yml"
EARNED_SPEC = "docs/EARNED_SPEC.md"
ORIGIN = "swerepo:hygiene/"
TIMEOUT = 120
PLACEHOLDER_OWNER = "@your-team/leads"  # what SeamSpec's strict CODEOWNERS block holds until a person replaces it
_VERSION = re.compile(r"(\d+(?:\.\d+)+\S*)")
_UNRELEASED = re.compile(r"^##\s*\[Unreleased\]", re.IGNORECASE | re.MULTILINE)  # as hygiene/changelog@1 reads it
_UNPINNED = re.compile(r"^\s*(?:-\s+)?uses:\s*(?!\./)[^@\s]+@(?![0-9a-f]{40}\b)\S+", re.MULTILINE)


@dataclass(frozen=True)
class Hygiene:
    name: str
    component: str  # proposed only when this component is set up
    version: int
    title: str
    assertion: str
    scope_paths: tuple[str, ...]

    @property
    def template(self) -> str:
        return f"seamspec/hygiene-{self.name}@{self.version}"

    @property
    def origin_ref(self) -> str:
        return f"{ORIGIN}{self.name}@{self.version}"


HYGIENE = {
    rule.name: rule
    for rule in (
        Hygiene(
            "privacy", "security", 1,
            "No personal email addresses or home-folder paths in tracked files",
            "Every tracked text file is free of personal email addresses and home-folder paths. Allowed: GitHub "
            "noreply addresses, reserved example domains, git@ in SSH remotes, emails declared in pyproject.toml's "
            "[project] authors and maintainers, emails in SECURITY.md, placeholder home folders (/Users/me, "
            "/home/user, C:\\Users\\you, runner, Shared), any line marked 'swerepo: allow-privacy', and the files "
            "or folders under [privacy] allow_paths in .swerepo.toml. A finding names the file, line and kind, "
            "never what was found.",
            ("**/*",),
        ),
        Hygiene(
            "adr-index", "docs", 1,
            "Every ADR is listed in the ADR index, and the index lists no ADR without a file",
            "Every ADR file (ADR-YYYYMMDD-xxxx-title.md) in the ADR folder ([adopted] adr_dir in .swerepo.toml, else "
            "docs/adr) is listed once in its README.md's index between the swerepo:adr-index markers, by its own row's "
            "link to the file ([ADR-YYYYMMDD-xxxx](file.md) in the first cell; an ID named elsewhere in a row doesn't "
            "count), and the index links no file that doesn't exist.",
            ("docs/adr/", ".swerepo.toml"),
        ),
        Hygiene(
            "changelog", "docs", 1,
            "CHANGELOG.md keeps an [Unreleased] section",
            "CHANGELOG.md exists and has a '## [Unreleased]' heading (Keep a Changelog), so every change has a place "
            "to be recorded before a release.",
            ("CHANGELOG.md",),
        ),
        Hygiene(
            "ci-tests", "ci", 1,
            "CI still runs the tests, and ci-ok still needs them",
            "In .github/workflows/swerepo-ci.yml, a test job, and a test-<project> job for every folder in "
            ".swerepo.toml's [projects] listed, each runs `uv run pytest` as a command of its own at the top of its "
            "step's script, is not switched off (if: false) and not allowed to fail (continue-on-error: true) at job "
            "or step level, and isn't masked (||, ;, a pipe, &, --version, --help, --collect-only, && unless it is "
            "the script's last command). ci-ok's needs names each of them, and ci-ok still fails when one fails: it "
            "runs if: always(), isn't allowed to fail, and has a step that reads the jobs' results (NEEDS: "
            "${{ toJSON(needs) }}) into a variable and then runs `if [ -n \"$var\" ]; then` with a non-zero `exit` "
            "before any other. Both steps stop at their first failing command: GitHub's own bash or sh, no set +e, "
            "and no exit before them.",
            (".github/workflows/swerepo-ci.yml", ".swerepo.toml"),
        ),
    )
}  # fmt: skip
assert tuple(HYGIENE) == HYGIENE_RULES


@dataclass(frozen=True)
class Rule:
    id: str
    status: str  # PROPOSED | LOCKED | SUPERSEDED | REJECTED
    title: str
    origin_ref: str | None


@dataclass
class Ledger:
    """What SeamSpec's own files say, read without writing anything."""

    set_up: bool = False
    mode: str | None = None
    rules: dict[str, Rule] = field(default_factory=dict)

    @classmethod
    def read(cls, root: Path) -> Ledger:
        config = root / CONFIG
        if not config.is_file():
            return cls()
        try:
            mode = tomllib.loads(config.read_text(encoding="utf-8")).get("mode")
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            mode = None
        rules = {}
        folder = root / INVARIANTS
        for path in sorted(folder.glob("inv_*.json")) if folder.is_dir() else []:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                continue
            if not isinstance(data, dict) or not isinstance(data.get("id"), str):
                continue
            origin = data.get("origin") if isinstance(data.get("origin"), dict) else {}
            ref = origin.get("ref") if isinstance(origin.get("ref"), str) else None
            rules[data["id"]] = Rule(data["id"], str(data.get("status", "")), str(data.get("title", "")), ref)
        return cls(True, mode if isinstance(mode, str) else None, rules)

    def locked(self) -> list[Rule]:
        return [rule for rule in self.rules.values() if rule.status == "LOCKED"]

    def waiting(self) -> list[Rule]:
        return [rule for rule in self.rules.values() if rule.status == "PROPOSED"]

    def hygiene(self, name: str, adopted: dict[str, str]) -> tuple[str, str | None]:
        """(status, rule id) of a hygiene rule: locked, proposed, adopted, adopted-not-locked, declined (the person
        rejected or retired SWERepo's rule: never proposed again) or missing. An adoption the person made counts
        before an earlier SWERepo rule they declined (review P7-F10)."""
        prefix = f"{ORIGIN}{name}@"

        def ours(*statuses: str) -> Rule | None:
            for status in statuses:
                for rule in self.rules.values():
                    if rule.status == status and (rule.origin_ref or "").startswith(prefix):
                        return rule
            return None

        if found := ours("LOCKED", "PROPOSED"):
            return ("locked" if found.status == "LOCKED" else "proposed"), found.id
        if name in adopted:
            rule = self.rules.get(adopted[name])
            return ("adopted" if rule is not None and rule.status == "LOCKED" else "adopted-not-locked"), adopted[name]
        if found := ours("REJECTED", "SUPERSEDED"):
            return "declined", found.id
        return "missing", None


def _text(root: Path, path: str) -> str | None:
    target = root / path
    if not inside(root, target) or target.is_symlink() or not target.is_file():
        return None
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def applies(root: Path, name: str, adr_dir: str) -> bool:
    """Whether a hygiene rule has its subject in the repository as it is, so its test can pass from the start
    (review P7-F06): the ADR README with one intact index, a CHANGELOG.md with `## [Unreleased]`, swerepo-ci.yml.
    The same answer for `init` (with what its plan creates) and `check`."""
    if name == "adr-index":
        readme = _text(root, f"{adr_dir.rstrip('/')}/README.md")
        try:
            return readme is not None and find_block(readme, style=HTML, marker=ADR_INDEX) is not None
        except BlockError:
            return False
    if name == "changelog":
        changelog = _text(root, "CHANGELOG.md")
        return changelog is not None and _UNRELEASED.search(changelog) is not None
    if name == "ci-tests":
        return _text(root, ".github/workflows/swerepo-ci.yml") is not None
    return True


def safe_target(root: Path, path: str) -> bool:
    """Whether SeamSpec may write `path` for SWERepo: inside the repository, and not a link (review P7-F03)."""
    target = root / path
    return inside(root, target) and not target.is_symlink()


def command() -> str | None:
    """The `seamspec` command on PATH, or None."""
    return shutil.which("seamspec")


def released(version: str | None) -> bool:
    """A version CI can install: plain, not a development or local build."""
    if not version:
        return False
    try:
        parsed = Version(version)
    except InvalidVersion:
        return False
    return not (parsed.is_devrelease or parsed.local)


def newer(installed: str | None, pinned: str | None) -> bool:
    """Whether `installed` is a released version newer than `pinned` (the pin only ever moves forward)."""
    if not released(installed):
        return False
    try:
        return pinned is None or Version(str(installed)) > Version(pinned)
    except InvalidVersion:
        return True


def run_read(args: list[str], root: Path) -> subprocess.CompletedProcess[str] | None:
    """A SeamSpec command that only reads (`--version`, `doctor`, `status`, `spec --check`), or None when it can't
    run. Its output is captured, never shown as is."""
    found = command()
    if found is None:
        return None
    try:
        return subprocess.run([found, *args], cwd=root, capture_output=True, text=True, check=False, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None


def doctor(root: Path) -> tuple[list[str], list[str]] | None:
    """`seamspec doctor --json`: the names of the checks with errors, and of those with warnings, or None when it
    can't run or its output can't be read. Only names: its messages can hold machine paths."""
    done = run_read(["doctor", "--json"], root)
    try:
        data = json.loads(done.stdout) if done is not None else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        return None
    names: dict[str, list[str]] = {"error": [], "warning": []}
    for finding in data["findings"]:
        if isinstance(finding, dict) and finding.get("level") in names:
            name = re.sub(r"[^A-Za-z0-9 _-]", "", str(finding.get("check", "")))[:40] or "unnamed"
            if name not in names[finding["level"]]:
                names[finding["level"]].append(name)
    return names["error"], names["warning"]


def installed_version(root: Path) -> str | None:
    done = run_read(["--version"], root)
    match = _VERSION.search(done.stdout) if done is not None and done.returncode == 0 else None
    return match[1] if match else None


def own_hosts(hosts: list[str]) -> list[str]:
    """The editors `seamspec init` sets up through `--hosts` (Claude Code is its default)."""
    return [host for host in hosts if host in ("cursor", "vscode", "antigravity")]


def init_args(*, first: bool, ci: bool, hosts: list[str]) -> list[str]:
    """`seamspec init`'s arguments (ADR-20261124-cd64 point 1). Never `--accept-auto-run`: the consent is the
    person's, answered in their terminal."""
    args = ["init"]
    if first:
        args += ["--mode", "enforced"]  # an existing mode, strict included, is never lowered
    args.append("--no-ci" if ci else "--ci")
    others = own_hosts(hosts)
    if others:
        args += ["--hosts", ",".join(others)]
    return args


def unpinned(text: str) -> bool:
    """Whether a workflow uses an action by tag or branch rather than by commit (the workflow audit's
    `unpinned-uses`)."""
    return _UNPINNED.search(text) is not None


def codeowners_problems(text: str) -> list[str]:
    """Strict mode's CODEOWNERS block (ADR-20261124-cd64 point 4): after SWERepo's block, the last matching line
    wins, so SeamSpec's would take `/.seamspec/` from the code owner; its placeholder team doesn't exist."""
    lines = text.splitlines()
    theirs = [i for i, line in enumerate(lines) if line.strip().startswith("# seamspec:begin")]
    ours = [i for i, line in enumerate(lines) if line.strip().startswith("# swerepo:begin")]
    problems = []
    if theirs and ours and theirs[0] > ours[0]:
        problems.append("SeamSpec's block comes after SWERepo's: move it above, so the code owner's lines win")
    if theirs and any(PLACEHOLDER_OWNER in line for line in lines[theirs[0] :] if not line.lstrip().startswith("#")):
        problems.append(f"SeamSpec's block still names {PLACEHOLDER_OWNER}: put the code owner there")
    return problems


def proposal(rule: Hygiene, harness: str, *, adr_dir: str = "docs/adr") -> dict[str, object]:
    """What `seamspec propose --json -` reads for a hygiene rule. The ADR index rule's scope is the repository's own
    ADR folder, so SeamSpec's `doctor` finds the files it covers."""
    scope = [f"{adr_dir.rstrip('/')}/", ".swerepo.toml"] if rule.name == "adr-index" else list(rule.scope_paths)
    return {
        "title": rule.title,
        "assertion": rule.assertion,
        "scope_paths": scope,
        "runner": "pytest",
        "harness_code": harness,
        "origin_type": "manual",
        "origin_text": f"SWERepo's hygiene rule pack (spec §6.8, ADR-20261124-cd64): {rule.template}.",
        "origin_ref": rule.origin_ref,
    }
