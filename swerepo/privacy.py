"""The privacy scan (spec §6.4; ADR-20261122-a48e): personal email addresses, home-folder paths and obvious
secrets in a repository's files: tracked ones, and untracked ones git would add.

The allowances are those of this repository's locked privacy rule (inv_62d51113), plus `[privacy] allow_paths`.
Findings name the kind, the file and the line, never the text that matched: `check` output reaches CI logs and
pull-request annotations, and printing a leaked address would publish it again (inv_5e3b5ef3). Read-only:
`git ls-files` doesn't write git's index.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from swerepo.globs import compile_all

MARKER = "swerepo: allow-privacy"
MAX_BYTES = 2_000_000  # larger files are data, not text a person wrote
EMAIL = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b")
NOREPLY_DOMAINS = ("users.noreply.github.com", "noreply.github.com")
EXAMPLE_DOMAIN = re.compile(r"(^|\.)example(\.(com|org|net))?$")
# Backslashes may be escaped (JSON, TOML, Python strings); a user name starts with a letter, digit or "_".
HOME = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\+Users\\+)([A-Za-z0-9_][A-Za-z0-9._-]*)")
PLACEHOLDER_USERS = frozenset({"me", "user", "you", "username", "name", "runner", "runneradmin", "Shared"})
# Well-known secret formats: specific prefixes and lengths, so ordinary text doesn't match.
SECRETS = (
    ("private key", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b")),
    ("Stripe live key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    # Project, service-account and admin keys, and the legacy format with its fixed middle (review P4-F08).
    ("OpenAI API key", re.compile(r"\bsk-(?:(?:proj|svcacct|admin)-[A-Za-z0-9_-]{40,}|[A-Za-z0-9]{20}T3BlbkFJ)")),
    ("PyPI token", re.compile(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{50,}")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{34,}\b")),
)
# Where a project publishes its security contact on purpose (detection's SECURITY.md places, P4-F05).
POLICY_PATHS = frozenset({"security.md", ".github/security.md", "docs/security.md"})
# Never the repository's own content, if the walk without git meets them.
SKIP_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"})


@dataclass(frozen=True)
class Hit:
    kind: str  # "email address", "home-folder path", or a secret's name
    path: str  # repository-relative, POSIX
    line: int

    @property
    def where(self) -> str:
        return f"{self.path}:{self.line}"


def _tracked(root: Path) -> list[str]:
    """Tracked files and those git would add (untracked, not ignored), as detection lists them; or every file
    outside tool folders when the folder isn't a repository."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, check=False, timeout=60,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        done = None
    if done is not None and done.returncode == 0:
        names = done.stdout.decode("utf-8", errors="surrogateescape").split("\0")
        return sorted({name for name in names if name})
    files = []
    for path in root.rglob("*"):
        parts = path.relative_to(root).parts
        if not SKIP_DIRS.intersection(parts) and path.is_file() and not path.is_symlink():
            files.append(path.relative_to(root).as_posix())
    return sorted(files)


def _text(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:  # listed by git, but deleted or unreadable in the working tree
        return None
    if b"\0" in data[:8192]:
        return None  # binary
    return data.decode("utf-8", errors="replace")


def declared_emails(root: Path) -> set[str]:
    """Addresses the project publishes on purpose: `[project]` authors and maintainers in pyproject.toml."""
    try:
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")).get("project", {})
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return set()
    if not isinstance(project, dict):
        return set()
    people = [p for key in ("authors", "maintainers") if isinstance(project.get(key), list) for p in project[key]]
    return {p["email"].lower() for p in people if isinstance(p, dict) and isinstance(p.get("email"), str)}


def _allowed_email(match: re.Match[str], line: str, declared: set[str]) -> bool:
    local, domain = match[1], match[2].lower()
    if f"{local}@{domain}".lower() in declared:
        return True
    if any(domain == d or domain.endswith("." + d) for d in NOREPLY_DOMAINS) or EXAMPLE_DOMAIN.search(domain):
        return True
    ssh_remote = line[match.end() : match.end() + 1] == ":" or line[: match.start()].endswith("ssh://")
    return local == "git" and ssh_remote


def line_kinds(path: str, line: str, declared: set[str]) -> list[str]:
    """What a line holds that shouldn't be published, by kind."""
    if MARKER in line:
        return []
    kinds = []
    if path.lower() not in POLICY_PATHS:  # the security contact is published on purpose
        kinds += ["email address" for m in EMAIL.finditer(line) if not _allowed_email(m, line, declared)]
    kinds += ["home-folder path" for user in HOME.findall(line) if user.rstrip(".") not in PLACEHOLDER_USERS]
    kinds += [name for name, pattern in SECRETS if pattern.search(line)]
    return kinds


def allowed_path(path: str, globs: list[str]) -> bool:
    """Whether `[privacy] allow_paths` names this file or a folder holding it (git's glob rules, `globs.Glob`)."""
    return any(glob.matches(path, contents=True) for glob in compile_all(globs))


def scan(root: Path, allow_paths: list[str] | None = None) -> list[Hit]:
    """Every finding in the repository's tracked text files, in file and line order."""
    root = root.resolve()
    declared = declared_emails(root)
    allowed = compile_all(allow_paths or [])  # once, not per file (P4-F11)
    hits = []
    for path in _tracked(root):
        if any(glob.matches(path, contents=True) for glob in allowed):
            continue
        text = _text(root / path)
        if text is None:
            continue
        for number, line in enumerate(re.split(r"\r\n|\r|\n", text), start=1):
            hits += [Hit(kind, path, number) for kind in line_kinds(path, line, declared)]
    return hits


def _plural(kind: str, count: int) -> str:
    if count == 1:
        return f"1 {kind}"
    return f"{count} {kind}es" if kind.endswith("ss") else f"{count} {kind}s"


def summary(hits: list[Hit], *, shown: int = 10) -> str:
    """One line: counts by kind, then where, never what (`2 email addresses, 1 home-folder path …: a.md:3, …`)."""
    counts: dict[str, int] = {}
    for hit in hits:
        counts[hit.kind] = counts.get(hit.kind, 0) + 1
    kinds = ", ".join(_plural(kind, n) for kind, n in counts.items())
    places = list(dict.fromkeys(hit.where for hit in hits))
    more = f", and {len(places) - shown} more" if len(places) > shown else ""
    return f"{kinds} in tracked files ({', '.join(places[:shown])}{more})"
