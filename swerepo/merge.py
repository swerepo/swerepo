"""The three-way merge `update` uses (spec §16) and its rule for action pins (ADR-20261123-f571).

`merge3` merges a person's file ("ours") with SWERepo's new render ("theirs") over the earlier render ("base").
Pins are settled first, line by line: a pin line that each side left alone or changed only as a pin is set, on all
three sides, to the newest of them, so pins never conflict and `update` never moves one backwards. A pin the person
lowered is their edit, and a pin the new render introduces (on an added line, or in place of another line) never
brings an older pin than the repository's. Then `git merge-file` merges the rest. Anything it can't merge is a
conflict: no text comes back, the file stays as it is, and conflict markers are never written. Anything but a clean,
parseable pin line is an ordinary edit, and one version pinned to two commits is never guessed.
"""

from __future__ import annotations

import difflib
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from packaging.version import InvalidVersion, Version

from swerepo.fingerprint import normalise

# `- uses: owner/action@<commit>  # v1.2.3`: the parts around the commit and the version must match exactly. The
# version starts with a digit: no second `v`, and no epoch (review M6-F02).
_PIN = re.compile(
    r"^(?P<lead>[ \t]*(?:-[ \t]+)?uses:[ \t]+)(?P<action>[^@\s#]+)@(?P<ref>\S+)(?P<gap>[ \t]+)"
    r"(?P<mark>#[ \t]*v)(?P<version>[0-9][^\s!]*)(?P<tail>[ \t]*)$"
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
TIMEOUT = 60


class MergeError(RuntimeError):
    """`git merge-file` couldn't run."""


@dataclass(frozen=True)
class Pin:
    skeleton: tuple[str, str, str, str, str]  # (lead, action, gap, mark, tail): all but the commit and the version
    commit: str
    version: Version  # for comparing
    raw: str  # as written: `2026.03.01` stays that, not `2026.3.1` (review M6-F02)

    @property
    def action(self) -> str:
        return self.skeleton[1]

    def line_with(self, other: Pin) -> str:
        """This line, pinned as `other` is."""
        lead, action, gap, mark, tail = self.skeleton
        return f"{lead}{action}@{other.commit}{gap}{mark}{other.raw}{tail}"


def pin(line: str) -> Pin | None:
    """The line as an action pin, or None: a `uses:` line whose ref is a full lowercase commit and whose comment
    is `# v<version>` with a version `packaging` reads (ADR-20261123-f571 point 1)."""
    match = _PIN.match(line)
    if match is None or not _COMMIT.match(match["ref"]):
        return None
    try:
        version = Version(match["version"])
    except InvalidVersion:
        return None
    skeleton = (match["lead"], match["action"], match["gap"], match["mark"], match["tail"])
    return Pin(skeleton, match["ref"], version, match["version"])


def _one_commit_per_version(pins: list[Pin]) -> bool:
    commits: dict[tuple[str, Version], set[str]] = {}
    for found in pins:
        commits.setdefault((found.action, found.version), set()).add(found.commit)
    return all(len(seen) == 1 for seen in commits.values())


def pins_only_newer(recorded: str, current: str) -> bool:
    """Whether `current` differs from `recorded` only by pins moved to newer versions, line for line, as `check`
    compares files (BOM, line endings, trailing spaces and final newlines aside: review M6-F04). One version pinned to
    two commits anywhere in `current`, or any other change, counts as an edit (point 3)."""
    old, new = normalise(recorded).split("\n"), normalise(current).split("\n")
    if len(old) != len(new):
        return False
    pins = [found for line in new if (found := pin(line)) is not None]
    if not _one_commit_per_version(pins):
        return False
    for before, after in zip(old, new, strict=True):
        if before == after:
            continue
        left, right = pin(before), pin(after)
        if left is None or right is None or left.skeleton != right.skeleton or right.version <= left.version:
            return False
    return True


@dataclass
class MergeResult:
    text: str | None  # the merged text; None when a conflict remains (the file stays as it is)
    conflicts: int = 0  # conflicts left: never written into the file
    pins_kept: list[str] = field(default_factory=list)  # actions whose newer pin was kept over the new render's


def _aligned(base: list[str], side: list[str]) -> dict[int, int]:
    """Which line of `side` stands where each line of `base` stood: unchanged lines, and lines changed one for one.
    Lines added or removed have none."""
    found = {}
    for kind, b1, b2, s1, s2 in difflib.SequenceMatcher(None, base, side, autojunk=False).get_opcodes():
        if kind == "equal" or (kind == "replace" and b2 - b1 == s2 - s1):
            found.update(zip(range(b1, b2), range(s1, s2), strict=True))
    return found


def _git_merge(base: str, ours: str, theirs: str) -> tuple[str, int]:
    with tempfile.TemporaryDirectory(prefix="swerepo-merge-") as folder:
        paths = []
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            path = Path(folder) / name
            path.write_bytes(text.encode("utf-8", errors="surrogateescape"))
            paths.append(str(path))
        try:
            done = subprocess.run(
                ["git", "merge-file", "-p", *paths], capture_output=True, check=False, timeout=TIMEOUT
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise MergeError(f"git merge-file didn't run ({type(error).__name__})") from error
    if not 0 <= done.returncode <= 127:  # the number of conflicts; a failure is negative, read as 255
        raise MergeError("git merge-file failed")
    return done.stdout.decode("utf-8", errors="surrogateescape"), done.returncode


def _settle(b: list[str], o: list[str], t: list[str]) -> tuple[int, set[str]]:
    """Settle the pins of all three sides in place. Returns (conflicts, actions whose newer pin was kept)."""
    to_ours, to_theirs = _aligned(b, o), _aligned(b, t)
    conflicts, kept = 0, set()
    for i, line in enumerate(b):
        j, k = to_ours.get(i), to_theirs.get(i)
        old = pin(line)
        if old is None or j is None or k is None or line == o[j] == t[k]:
            continue  # not a pin, removed on a side, or untouched everywhere (review M6-F02)
        mine, new = pin(o[j]), pin(t[k])
        if mine is None or new is None or old.skeleton != mine.skeleton or old.skeleton != new.skeleton:
            continue  # an ordinary edit on a side: git decides
        if mine.version < old.version:
            continue  # the person lowered it: their edit, kept or a conflict as git decides (review M6-F03)
        if not _one_commit_per_version([old, mine, new]):
            conflicts += 1  # one version, two commits: never guessed
            continue
        best = max((old, mine, new), key=lambda found: found.version)
        if new.version < best.version:
            kept.add(best.action)
        b[i] = o[j] = t[k] = mine.line_with(best)
    repository: dict[str, list[Pin]] = {}
    for line in o:
        if (found := pin(line)) is not None:
            repository.setdefault(found.action, []).append(found)
    if not _one_commit_per_version([found for pins in repository.values() for found in pins]):
        conflicts += 1  # the person's file pins one version to two commits, after settling too: never guessed
    from_theirs = {k: i for i, k in to_theirs.items()}
    for k in range(len(t)):  # pins the new render introduces: on added lines, or in place of another line
        found = pin(t[k])
        if found is None or found.action not in repository:
            continue
        i = from_theirs.get(k)
        earlier = pin(b[i]) if i is not None else None
        if earlier is not None and earlier.action == found.action:
            continue  # this action's pin line in the earlier render too: settled above, or the person's edit
        candidates = [*repository[found.action], found]
        if not _one_commit_per_version(candidates):
            conflicts += 1
            continue
        best = max(candidates, key=lambda other: other.version)
        if found.version < best.version:
            t[k] = found.line_with(best)
            kept.add(found.action)
    return conflicts, kept


def merge3(base: str, ours: str, theirs: str) -> MergeResult:
    """Merge the person's file (`ours`) with SWERepo's new render (`theirs`) over the earlier render (`base`).
    Line endings are compared as LF, and the result has the person's: CRLF when their file uses only CRLF, since
    templates render LF and a CRLF checkout would otherwise differ on every line (review M6-F01)."""
    crlf = "\r\n" in ours and ours.count("\n") == ours.count("\r\n")
    b, o, t = (text.replace("\r\n", "\n").split("\n") for text in (base, ours, theirs))
    conflicts, kept = _settle(b, o, t)
    if conflicts:
        return MergeResult(None, conflicts, sorted(kept))
    base, ours, theirs = "\n".join(b), "\n".join(o), "\n".join(t)
    merged, conflicts = (theirs, 0) if ours == base else _git_merge(base, ours, theirs)
    if conflicts:
        return MergeResult(None, conflicts, sorted(kept))
    return MergeResult(merged.replace("\n", "\r\n") if crlf else merged, 0, sorted(kept))
