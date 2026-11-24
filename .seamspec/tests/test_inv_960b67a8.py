"""Rule: the pre-push privacy hook refuses a push whose new commits add a key, a personal email address or a
home-folder path, says where and never what, and is never installed over a hook of the person's own
(ADR-20261123-24e0; SWEREPO-SPEC §6.4). A real `git push` to a local bare repository; nothing leaves the test.
The push runs this checkout's `swerepo` (the one next to the Python running the test), never another installed
copy. Keys, addresses and paths are built at run time, so this file holds none."""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from swerepo import hook
from swerepo.cli import app

KEY = "AKIA" + "Z" * 16
TOKEN = "ghp_" + "a1" * 18
EMAIL = "bob" + "@" + "home-mail.org"
HOME = "/home/" + "bob" + "/secrets.txt"
# The secrets, and pieces of each: none may appear in what the hook prints.
NEVER = (KEY, TOKEN, EMAIL, HOME, "bob", KEY[4:12], TOKEN[4:12], "home-mail", "secrets.txt")


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    base = ["git", "-c", "commit.gpgsign=false", "-c", "user.name=t", "-c", "user.email=t@example.com"]
    return subprocess.run([*base, "-C", str(root), *args], capture_output=True, text=True, check=check)


def _commit(root: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    _git(root, "add", "-A")
    _git(root, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _on_remote(bare: Path, branch: str) -> str:
    return subprocess.run(["git", "-C", str(bare), "rev-parse", "-q", "--verify", f"refs/heads/{branch}"],
                          capture_output=True, text=True).stdout.strip()  # fmt: skip


def _refused(root: Path, bare: Path, branch: str, commit: str, kind: str, place: str) -> None:
    before = _on_remote(bare, branch)
    pushed = _git(root, "push", "origin", branch, check=False)
    assert pushed.returncode != 0 and "push refused" in pushed.stderr, (kind, pushed.stderr)
    assert kind in pushed.stderr and f"{commit[:7]} {place}" in pushed.stderr, pushed.stderr
    printed = pushed.stdout + pushed.stderr  # everything the hook printed, on either stream
    for piece in NEVER:
        assert piece not in printed, (kind, piece)  # where, never what
    assert _on_remote(bare, branch) == before  # nothing reached the remote


def _setup(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    empty = tmp_path / "gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))  # no hooks path or settings of the person's own
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    here = Path(sys.executable).parent  # this checkout's environment, where its swerepo is installed
    monkeypatch.setenv("PATH", f"{here}{os.pathsep}{os.environ['PATH']}")
    found = shutil.which("swerepo")
    assert found and Path(found).parent == here, "the push must run this checkout's swerepo"
    root, bare = tmp_path / "app", tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    _git(root, "remote", "add", "origin", str(bare))
    _commit(root, {"pyproject.toml": '[project]\nname = "app"\n'}, "start")
    return root, bare


def test_a_push_adding_a_secret_is_refused_by_kind_and_place(tmp_path: Path, monkeypatch):
    root, bare = _setup(tmp_path, monkeypatch)
    installed = CliRunner().invoke(app, ["hook", "install", "--path", str(root)])
    assert installed.exit_code == 0, installed.output
    assert os.access(root / ".git/hooks/pre-push", os.X_OK)
    assert _git(root, "push", "-q", "origin", "main", check=False).returncode == 0  # a new branch, clean
    for kind, line in (("AWS access key", f"key = '{KEY}'"), ("GitHub token", f"token: {TOKEN}"),
                       ("email address", f"contact: {EMAIL}"), ("home-folder path", f"see {HOME}")):  # fmt: skip
        commit = _commit(root, {"settings.txt": f"first line\n{line}\n"}, kind)
        _refused(root, bare, "main", commit, kind, "settings.txt:2")
        _git(root, "-c", "core.hooksPath=/dev/null", "reset", "-q", "--hard", "HEAD~1")

    # a secret in an earlier commit, with clean commits after it, still stops the push
    leaked = _commit(root, {"deploy.sh": f"echo start\nexport KEY={KEY}\n"}, "deploy")
    _commit(root, {"README.md": "# app\n"}, "readme")
    _refused(root, bare, "main", leaked, "AWS access key", "deploy.sh:2")
    _git(root, "-c", "core.hooksPath=/dev/null", "reset", "-q", "--hard", "HEAD~2")

    # a new branch carrying a secret
    _git(root, "checkout", "-q", "-b", "feature")
    carried = _commit(root, {"notes.md": f"ask {EMAIL}\n"}, "notes")
    _refused(root, bare, "feature", carried, "email address", "notes.md:1")
    _git(root, "checkout", "-q", "main")

    # a clean push to the existing branch goes through, and arrives
    clean = _commit(root, {"README.md": "# app\n\nNothing secret here.\n"}, "clean")
    pushed = _git(root, "push", "-q", "origin", "main", check=False)
    assert pushed.returncode == 0, pushed.stderr
    assert _on_remote(bare, "main") == clean


def test_a_pre_push_hook_of_your_own_is_never_replaced(tmp_path: Path, monkeypatch):
    root, _ = _setup(tmp_path, monkeypatch)
    hooks = root / ".git/hooks"
    hooks.mkdir(exist_ok=True)
    hint = 'swerepo privacy --pre-push --remote "${1:-}"'  # the line to add, with the remote git pushes to
    mine = b"#!/bin/sh\r\necho mine\r\n"
    (hooks / "pre-push").write_bytes(mine)
    (hooks / "pre-push").chmod(0o750)
    result = CliRunner().invoke(app, ["hook", "install", "--path", str(root)])
    assert result.exit_code == 1 and hint in result.output, result.output
    assert (hooks / "pre-push").read_bytes() == mine  # byte for byte, line endings included
    assert stat.S_IMODE((hooks / "pre-push").stat().st_mode) == 0o750  # and its mode

    # a hook that is a link to a shared one is the person's too, even when it looks like SWERepo's own (here an
    # older one, not executable): neither the link nor what it points to changes
    shared = tmp_path / "shared-pre-push"
    looks_ours = hook.script("swerepo").replace("privacy --pre-push", "privacy --pre-push --old").encode()
    shared.write_bytes(looks_ours)
    shared.chmod(0o644)
    (hooks / "pre-push").unlink()
    (hooks / "pre-push").symlink_to(shared)
    result = CliRunner().invoke(app, ["hook", "install", "--path", str(root)])
    assert result.exit_code == 1 and hint in result.output, result.output
    assert (hooks / "pre-push").is_symlink() and os.readlink(hooks / "pre-push") == str(shared)
    assert shared.read_bytes() == looks_ours and stat.S_IMODE(shared.stat().st_mode) == 0o644
