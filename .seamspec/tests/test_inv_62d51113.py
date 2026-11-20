"""Locked rule: no personal email addresses or home-folder paths in tracked files.

Allowed (SWEREPO-SPEC §6.4): GitHub noreply addresses, reserved example domains, `git@` in SSH remotes,
emails in pyproject.toml's [project] authors and maintainers, emails in SECURITY.md (the reporting
contact), placeholder home folders such as /Users/me or /home/user, and any line marked with
`swerepo: allow-privacy`.
"""

import re
import subprocess
import tomllib
from pathlib import Path

# The repository root is the folder that holds .seamspec/config.toml, wherever SeamSpec keeps this file
# (.seamspec/proposed/<id>/ while proposed, .seamspec/tests/ once locked, or a copy of the staged tree).
ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".seamspec" / "config.toml").is_file())

MARKER = "swerepo: allow-privacy"
EMAIL = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b")
NOREPLY_DOMAINS = ("users.noreply.github.com", "noreply.github.com")
EXAMPLE_DOMAIN = re.compile(r"(^|\.)example(\.(com|org|net))?$")
# Backslashes may be escaped (JSON, TOML, Python strings); a user name starts with a letter, digit or "_".
HOME = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\+Users\\+)([A-Za-z0-9_][A-Za-z0-9._-]*)")
PLACEHOLDER_USERS = {"me", "user", "you", "username", "name", "runner", "runneradmin", "Shared"}
# Never part of the repository's own content, if the fallback walk below meets them.
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}


def _tracked_files() -> list[Path]:
    """Tracked files. Inside a git checkout ask git; in the commit gate's copy of the staged tree
    (which has no .git) every file there is a staged file."""
    if (ROOT / ".git").exists():
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, text=True, check=True
        ).stdout
        return [ROOT / name for name in out.split("\0") if name]
    files = []
    for path in ROOT.rglob("*"):
        parts = path.relative_to(ROOT).parts
        if SKIP_DIRS.intersection(parts) or parts[:2] == (".seamspec", ".local"):
            continue
        if path.is_file():
            files.append(path)
    return files


def _text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:  # listed by git but deleted in the working tree
        return None
    if b"\0" in data[:8192]:
        return None  # binary
    return data.decode("utf-8", errors="replace")


def _declared_emails() -> set[str]:
    """Emails the project publishes on purpose: pyproject.toml's [project] authors and maintainers."""
    try:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8")).get("project", {})
    except (OSError, tomllib.TOMLDecodeError):
        return set()
    people = project.get("authors", []) + project.get("maintainers", [])
    return {p["email"].lower() for p in people if isinstance(p, dict) and isinstance(p.get("email"), str)}


def _allowed_email(match: re.Match[str], line: str, declared: set[str]) -> bool:
    local, domain = match.group(1), match.group(2).lower()
    if f"{local}@{domain}".lower() in declared:
        return True
    if any(domain == d or domain.endswith("." + d) for d in NOREPLY_DOMAINS) or EXAMPLE_DOMAIN.search(domain):
        return True
    ssh_remote = line[match.end() : match.end() + 1] == ":" or line[: match.start()].endswith("ssh://")
    return local == "git" and ssh_remote


def _line_findings(rel: str, line: str, declared: set[str]) -> list[str]:
    if MARKER in line:
        return []
    found = []
    if rel != "SECURITY.md":
        emails = [m for m in EMAIL.finditer(line) if not _allowed_email(m, line, declared)]
        found += [f"email address at {m.group(2)}" for m in emails]
    found += ["home-folder path" for user in HOME.findall(line) if user.rstrip(".") not in PLACEHOLDER_USERS]
    return found


def _findings() -> list[str]:
    declared = _declared_emails()
    found = []
    for path in _tracked_files():
        text = _text(path)
        if text is None:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(text.splitlines(), start=1):
            found += [f"{rel}:{number}: {what}" for what in _line_findings(rel, line, declared)]
    return found


def test_no_personal_emails_or_home_paths_in_tracked_files():
    assert _findings() == []


def test_the_scan_flags_personal_data_and_allows_the_exceptions():
    # Samples are assembled at run time, so this file never contains them literally.
    at, users, home = "@", "/" + "Users/", "/" + "home/"
    flagged = [
        "alice" + at + "mail.test.com",
        "contact: alice" + at + "evilnoreply.github.com",
        "git" + at + "mail.test.com wrote",
        users + "alice/project",
        home + "alice/.config",
        '"C:\\\\' + 'Users\\\\alice\\\\project"',
    ]
    allowed = [
        "someone" + at + "users.noreply.github.com",
        "you" + at + "example.org",
        "git" + at + "github.com:owner/repo.git",
        "ssh://git" + at + "github.com/owner/repo",
        users + "me/code",
        "see " + home + "user.",
        users + "...",
        "alice" + at + "mail.test.com  # " + MARKER,
        "maintainer" + at + "declared.test.com",
    ]
    declared = {"maintainer" + at + "declared.test.com"}
    for line in flagged:
        assert _line_findings("README.md", line, declared), line
    for line in allowed:
        assert not _line_findings("README.md", line, declared), line
    assert not _line_findings("SECURITY.md", "report to alice" + at + "mail.test.com", declared)
    assert _line_findings("SECURITY.md", users + "alice", declared)
