"""The pre-push privacy hook (spec §6.4; ADR-20261123-24e0): the privacy scan run on the lines each commit about to be
pushed adds, so a key, a personal email address or a home-folder path never reaches GitHub.

A pre-push hook, not pre-commit: SeamSpec owns the pre-commit hook. `install` writes a hook file of SWERepo's own
and never replaces anyone else's. `pushed_hits` only reads git. Like every privacy finding, a hit names the kind,
the commit and the place, never the text that matched (inv_5e3b5ef3, inv_ab57c6ff).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from swerepo import ci, privacy
from swerepo.globs import compile_all

NAME = "pre-push"
SIGNATURE = "# Installed by swerepo hook install"
ZERO = re.compile(r"^0+$")
OBJECT = re.compile(r"^[0-9a-f]{40,64}$")  # a SHA-1 or SHA-256 object id
# A hunk header, plain (`@@ -a,b +c,d @@`) or combined for a merge (`@@@ -a,b -c,d +e,f @@@`): one `@` more than
# the merge has parents, and as many columns of +/- before each line.
_HUNK = re.compile(r"^(@{2,}) (?:-\d+(?:,\d+)? )+\+(\d+)(?:,\d+)? \1")
TIMEOUT = 120


class HookError(RuntimeError):
    """The hook can't be installed, or the commits can't be read. The message names no absolute path."""


@dataclass(frozen=True)
class PushHit:
    kind: str
    commit: str  # the full id
    path: str
    line: int

    @property
    def where(self) -> str:
        return f"{self.commit[:7]} {self.path}:{self.line}"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "-c", "core.quotepath=false", *args], capture_output=True, check=False,
            timeout=TIMEOUT,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired) as error:
        raise HookError(f"git {args[0]}: didn't answer ({type(error).__name__})") from error


# --- installing ---------------------------------------------------------------------------------------------


def hooks_dir(root: Path) -> Path:
    """The folder git runs hooks from: `core.hooksPath` when set, else the repository's own, worktrees included."""
    done = _git(root, "rev-parse", "--git-path", "hooks")
    if done.returncode != 0:
        raise HookError("not a git repository")
    folder = Path(done.stdout.decode("utf-8", errors="surrogateescape").strip())
    return folder if folder.is_absolute() else (root / folder)


def command(recorded: object) -> str:
    """How the hook runs SWERepo: the privacy workflow's recorded command when it is one SWERepo writes (so never an
    arbitrary string from a file), else `swerepo` on PATH."""
    return str(recorded) if recorded and ci.valid_swerepo_command(recorded) else "swerepo"


def script(run: str) -> str:
    return f"""#!/bin/sh
{SIGNATURE} (SWEREPO-SPEC §6.4, ADR-20261123-24e0). Remove this file to uninstall.
# Refuses a push whose new commits add a key, a personal email address or a home-folder path.
# `git push --no-verify` skips it; the privacy workflow still checks on GitHub.
# GUI git clients often start hooks without the places uv and its tools live: ~/.local/bin, and Homebrew's
PATH="${{PATH:+$PATH:}}$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin"
remote="${{1:-}}"  # the remote's name (or its URL, for a push to a URL): what "already there" is measured against
set -- {run}
if ! command -v "$1" >/dev/null 2>&1; then
  echo "swerepo: $1 isn't installed, so this push can't be checked. Not pushing." >&2
  echo "swerepo: install it, or push with --no-verify to skip this check once." >&2
  exit 1
fi
exec "$@" privacy --pre-push --remote "$remote"
"""


def is_ours(text: str) -> bool:
    lines = text.splitlines()
    return len(lines) > 1 and lines[1].startswith(SIGNATURE)


def status(root: Path) -> str:
    """ "installed"; "not executable" (SWERepo's, but git skips a hook it can't run); "missing"; or "other": a
    pre-push hook that isn't SWERepo's, a link included, as `install` sees it (review H55-F01). Reads only."""
    path = hooks_dir(root) / NAME
    if path.is_symlink():
        return "other"
    if not path.is_file():
        return "missing"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "other"
    if not is_ours(text):
        return "other"
    return "installed" if os.access(path, os.X_OK) else "not executable"


def install(root: Path, recorded_command: object) -> tuple[bool, str]:
    """Write SWERepo's pre-push hook. Returns (done, message): a hook of someone else's is never replaced."""
    folder = hooks_dir(root)
    path = folder / NAME
    wanted = script(command(recorded_command))
    shown = f"{NAME} hook"
    if path.exists() or path.is_symlink():
        try:
            current = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        except OSError as error:
            raise HookError(f"{shown}: can't read it ({error.strerror or type(error).__name__})") from error
        if not is_ours(current) or path.is_symlink():
            line = f'{command(recorded_command)} privacy --pre-push --remote "${{1:-}}"'  # the remote: H55-F03
            return False, f"{shown}: one of yours is there, so it is kept. To scan pushes, add this line to it: {line}"
        if current == wanted:
            if os.access(path, os.X_OK):
                return True, f"{shown}: already installed"
            try:  # git skips a hook it can't run, without a word (review H55-F01)
                path.chmod(0o755)
            except OSError as error:
                raise HookError(
                    f"{shown}: can't make it executable ({error.strerror or type(error).__name__})"
                ) from error
            return True, f"{shown}: made executable again (git skipped it)"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(wanted, encoding="utf-8")
        path.chmod(0o755)
    except OSError as error:
        raise HookError(f"{shown}: can't write it ({error.strerror or type(error).__name__})") from error
    return True, f"{shown}: installed (pushes are scanned for keys, personal emails and home-folder paths)"


# --- scanning a push ---------------------------------------------------------------------------------------


def parse_updates(text: str) -> list[tuple[str, str, str, str]]:
    """git's pre-push input: one `<local ref> <local sha> <remote ref> <remote sha>` per line. Anything else is
    refused rather than skipped, so a push is never let through unread (review H55-F05)."""
    updates = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 4 or not (OBJECT.match(parts[1]) and OBJECT.match(parts[3])):
            raise HookError("git's list of refs to push isn't in the expected form: not pushing")
        updates.append((parts[0], parts[1], parts[2], parts[3]))
    return updates


def _remotes(root: Path) -> set[str]:
    done = _git(root, "remote")
    return set(done.stdout.decode("utf-8", errors="replace").split()) if done.returncode == 0 else set()


def _commits(root: Path, local: str, remote: str, remote_name: str | None) -> list[str]:
    """The commits this update sends, oldest first: those after the remote's, or for a branch new to that remote,
    those its remote-tracking branches don't have. Measured against the remote being pushed to when it is a configured
    one, so a branch already on `origin` is still scanned when first pushed to another remote (review H55-F03); else
    against every remote."""
    if not ZERO.match(remote):
        done = _git(root, "rev-list", "--reverse", f"{remote}..{local}")
        if done.returncode == 0:
            return done.stdout.decode().split()
    known = f"--remotes={remote_name}" if remote_name and remote_name in _remotes(root) else "--remotes"
    done = _git(root, "rev-list", "--reverse", local, "--not", known)  # a new branch, or the remote not fetched
    if done.returncode != 0:
        raise HookError(f"can't list the commits to push ({local[:7]})")
    return done.stdout.decode().split()


_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}


def _path_name(text: str) -> str:
    """A file name as a `+++` line gives it: git ends a name holding a space or a quoted character with a tab, and
    C-quotes a name holding `"`, `\\` or a control character, with octal escapes for other bytes (review H55-F06)."""
    text = text.rstrip("\t")  # a tab inside a name is always quoted, so a raw one only ever ends it
    if not (len(text) >= 2 and text.startswith('"') and text.endswith('"')):
        return text
    out, index, body = bytearray(), 0, text[1:-1]
    while index < len(body):
        char = body[index]
        if char != "\\" or index + 1 == len(body):
            out += char.encode("utf-8", errors="surrogateescape")
            index += 1
            continue
        following, octal = body[index + 1], body[index + 1 : index + 4]
        if len(octal) == 3 and all(c in "01234567" for c in octal):  # a byte, as \303\251 for "é"
            out.append(int(octal, 8) & 0xFF)
            index += 4
        else:
            out.append(_ESCAPES.get(following, ord(following) if following.isascii() else 63))
            index += 2
    return out.decode("utf-8", errors="replace")


def _added_lines(root: Path, commit: str) -> list[tuple[str, int, str]]:
    """(path, line number, text) of every line the commit adds: against its parent (everything, for a first commit),
    and for a merge, the lines no parent had, such as a conflict resolved by hand (`--cc`, review H55-F02). Lines a
    merge takes from one parent come from that parent's own commits, which are scanned in turn. Binary files aren't
    listed."""
    done = _git(root, "diff-tree", "--cc", "-U0", "--no-commit-id", "--root", "--no-renames", "--no-ext-diff",
                "--no-color", "--no-textconv", "-r", commit)  # fmt: skip
    if done.returncode != 0:
        raise HookError(f"can't read commit {commit[:7]}")
    found: list[tuple[str, int, str]] = []
    path: str | None = None
    number, cols = 0, 1  # cols: one column of +/- per parent (2 for a merge of two)
    header = False  # between `diff` and the first hunk: an added line `++ x` also reads `+++ x`
    for raw in done.stdout.decode("utf-8", errors="replace").split("\n"):
        if raw.startswith(("diff --git ", "diff --cc ", "diff --combined ")):
            path, header = None, True
        elif header and raw.startswith("+++ "):
            name = _path_name(raw[4:])
            path = name[2:] if name.startswith("b/") else None  # /dev/null: the file was deleted
        elif header and raw.startswith("--- "):
            continue
        elif (hunk := _HUNK.match(raw)) is not None:
            number, cols, header = int(hunk[2]), len(hunk[1]) - 1, False
        elif not header and path is not None and raw[:cols] and set(raw[:cols]) <= {"+", "-", " "}:
            marks = raw[:cols]
            if marks == "+" * cols:  # in no parent: added by this commit
                found.append((path, number, raw[cols:]))
            if "-" not in marks:  # a line of the result
                number += 1
    return found


def pushed_hits(
    root: Path, updates: list[tuple[str, str, str, str]], allow_paths: list[str], remote_name: str | None = None
) -> list[PushHit]:
    """Every privacy finding in the lines the pushed commits add, by the same rules as the scan in CI. `remote_name`:
    the remote git is pushing to (the hook's first argument)."""
    root = root.resolve()
    declared = privacy.declared_emails(root)
    allowed = compile_all(allow_paths)
    seen: set[str] = set()
    hits: list[PushHit] = []
    for _local_ref, local, _remote_ref, remote in updates:
        if ZERO.match(local):
            continue  # a deleted branch sends nothing
        for commit in _commits(root, local, remote, remote_name):
            if commit in seen:
                continue
            seen.add(commit)
            for path, number, line in _added_lines(root, commit):
                if any(glob.matches(path, contents=True) for glob in allowed):
                    continue
                hits += [PushHit(kind, commit, path, number) for kind in privacy.line_kinds(path, line, declared)]
    return hits
