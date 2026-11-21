"""Pull-request rules for `swerepo check --base REF` (SWEREPO-SPEC §6.5, §15; ADR-20261120-5e21).

The diff is the working tree (plus untracked files) against the merge base of REF and HEAD. The ADR
index rule needs no diff: the `docs` component checks it on every run.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import tomllib
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from swerepo import standard
from swerepo.check import MISSING, NOT_CHOSEN, OK, UNKNOWN, Finding, UsageError
from swerepo.fingerprint import fingerprint
from swerepo.state import DEFAULT_EXEMPT_AUTHORS

if TYPE_CHECKING:
    from swerepo.check import Context

LOCKFILES = frozenset({
    "uv.lock", "poetry.lock", "Pipfile.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "Cargo.lock", "go.sum", "Gemfile.lock",
})  # fmt: skip
_TRAILER = re.compile(r"^\s*progress:\s*none\s*$", re.IGNORECASE | re.MULTILINE)


def _worktree_diff(ctx: Context, merge_base: str) -> str | None:
    """`git diff --name-status` of the working tree against the merge base, run on a copy of the index;
    None when git or the copy fails (never an empty diff that would read as "no changes").

    `git diff` refreshes the index it reads and writes it back when file times are out of date, even
    with `--no-optional-locks`; on a copy, `.git/index` stays as it was (check changes nothing).
    """
    found = (ctx.git("rev-parse", "--git-path", "index") or "").strip()
    real = ctx.root / found if found else None
    with tempfile.TemporaryDirectory(prefix="swerepo-") as scratch:
        copy = Path(scratch) / "index"
        if real is not None and real.exists():
            try:
                shutil.copyfile(real, copy)
            except OSError:
                return None  # an empty index would show every tracked file as deleted
        return ctx.git("diff", "--name-status", "--no-renames", "-z", merge_base, index=copy)


def _changes(ctx: Context, merge_base: str) -> list[tuple[str, str]] | None:
    """(status letter, path) for every change against the merge base; untracked files count as added,
    except a file the merge base has (untracked with `git rm --cached`): changed if its text differs."""
    diff = _worktree_diff(ctx, merge_base)
    untracked = ctx.git("ls-files", "--others", "--exclude-standard", "-z")
    if diff is None or untracked is None:
        return None
    parts = [p for p in diff.split("\0") if p]
    changes = {path: status[0] for status, path in zip(parts[0::2], parts[1::2], strict=False)}
    for path in (p for p in untracked.split("\0") if p):
        if changes.get(path) != "D":
            changes[path] = "A"
        elif ctx.git_bytes("show", f"{merge_base}:{path}") == ctx.read_bytes(path):  # bytes: may be binary
            del changes[path]  # same text, just no longer tracked
        else:
            changes[path] = "M"
    return [(status, path) for path, status in changes.items()]


def _dependencies(text: str | None) -> tuple[set[str], list[str]]:
    """PEP 503-normalised names in [project].dependencies, and what can't be read (never the values)."""
    if text is None:
        return set(), []
    try:
        project = tomllib.loads(text).get("project", {})
    except tomllib.TOMLDecodeError:
        return set(), ["pyproject.toml isn't valid TOML"]
    if not isinstance(project, dict):
        return set(), ["[project] isn't a table"]
    deps = project.get("dependencies", [])
    if not isinstance(deps, list):
        return set(), ["[project].dependencies isn't a list"]
    names, bad = set(), []
    for number, entry in enumerate(deps, start=1):
        try:
            names.add(canonicalize_name(Requirement(str(entry)).name))
        except InvalidRequirement:
            # by position, never the text: an invalid entry may be a local path or a URL with an address
            bad.append(f"entry {number} of [project].dependencies isn't a valid requirement")
    return names, bad


def pr_findings(ctx: Context, *, base: str, author: str | None, skip_progress: bool) -> list[Finding]:
    c = "pr"
    if not ctx.detection.git.is_work_tree:
        raise UsageError("--base needs a git repository")
    if not ctx.detection.git.is_toplevel:
        raise UsageError("--base compares the whole repository: run it at the repository's top level")
    merge_base = (ctx.git("merge-base", base, "HEAD") or "").strip()
    if not merge_base:
        raise UsageError(f"--base {base}: git can't find a merge base with HEAD (fetch it, or check the name)")
    state = ctx.state
    enforce = state.pr_enforce if state else True
    exempt = state.exempt_authors if state else list(DEFAULT_EXEMPT_AUTHORS)
    if author and author in exempt:
        return [Finding(c, "pr.skipped", NOT_CHOSEN, f"pull-request rules skipped: {author} is an exempt author")]
    changes = _changes(ctx, merge_base)
    if changes is None:
        return [Finding(c, "pr.changes", UNKNOWN, f"git couldn't list the changes against {base}")]
    if not changes:
        return [Finding(c, "pr.changes", OK, f"no changes against {base}")]
    if all(PurePosixPath(path).name in LOCKFILES for _, path in changes):
        return [Finding(c, "pr.skipped", NOT_CHOSEN, "pull-request rules skipped: only lockfiles changed")]

    def ok(item: str, message: str, path: str | None = None) -> Finding:
        return Finding(c, item, OK, message, path)

    def missing(item: str, message: str, path: str | None = None) -> Finding:
        return Finding(c, item, MISSING, message, path, blocking=enforce)

    found: list[Finding] = []
    progress_dir = str(ctx.adopted.get("progress_dir") or standard.PROGRESS_DIR).rstrip("/")
    added_progress = [p for s, p in changes if s == "A" and p.startswith(progress_dir + "/") and p.endswith(".md")]
    messages = ctx.git("log", "--format=%B", f"{merge_base}..HEAD") or ""
    if added_progress:
        found.append(ok("pr.progress", f"progress entry added ({added_progress[0]})", added_progress[0]))
    elif skip_progress or _TRAILER.search(messages):
        found.append(
            ok("pr.progress", f"no progress entry needed ({'--skip progress' if skip_progress else 'Progress: none'})")
        )
    else:
        found.append(missing("pr.progress", f"no progress entry added in {progress_dir}/", progress_dir))

    adr_dir = str(ctx.adopted.get("adr_dir") or standard.ADR_DIR).rstrip("/")
    adr_changed = any(
        s in ("A", "M")
        and PurePosixPath(p).parent.as_posix() == adr_dir
        and p.endswith(".md")
        and PurePosixPath(p).name.lower() not in standard.NOT_ADRS
        for s, p in changes
    )

    old, _ = _dependencies(ctx.git("show", f"{merge_base}:pyproject.toml"))
    new, bad = _dependencies(ctx.read("pyproject.toml"))
    found.extend(Finding(c, "pr.dependencies", UNKNOWN, f"can't read dependencies: {e}", "pyproject.toml") for e in bad)
    added = sorted(new - old)
    if added:
        names = ", ".join(added)
        if adr_changed:
            found.append(ok("pr.dependencies", f"new dependency {names} with an ADR", "pyproject.toml"))
        else:
            found.append(missing("pr.dependencies", f"new dependency {names} needs an ADR", "pyproject.toml"))

    recorded = state.files() if state else {}
    workflows = []
    for status, path in changes:
        if not path.startswith(".github/workflows/"):
            continue
        record = recorded.get(path)
        if status in ("A", "M") and record is not None and fingerprint(ctx.read(path) or "") == record.written:
            continue  # SWERepo's own change (swerepo init or update)
        workflows.append(path)
    if workflows:
        names = ", ".join(workflows)
        if adr_changed:
            found.append(ok("pr.workflows", f"workflow change ({names}) with an ADR"))
        else:
            found.append(missing("pr.workflows", f"workflow change ({names}) needs an ADR", workflows[0]))
    return found
