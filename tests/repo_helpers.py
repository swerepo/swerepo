"""Helpers for building fixture repositories inside a test's temporary folder (spec §18)."""

import subprocess
from pathlib import Path

# git settings for commits made by tests: no hooks or signing from the person's own configuration.
GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]
TEST_EMAIL = "t@example.com"


def make(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def git(root: Path, *args: str, email: str = TEST_EMAIL) -> str:
    done = subprocess.run(
        [*GIT, "-c", f"user.email={email}", "-C", str(root), *args], capture_output=True, text=True, check=True
    )  # fmt: skip
    return done.stdout


def git_init(root: Path) -> Path:
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    return root


def commit(root: Path, message: str = "change", *, email: str = TEST_EMAIL) -> None:
    git(root, "add", "-A", email=email)
    git(root, "commit", "-q", "--allow-empty", "-m", message, email=email)


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    return {p.relative_to(root).as_posix(): (p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(root.rglob("*"))}
