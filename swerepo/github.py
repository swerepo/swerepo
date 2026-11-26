"""The `github` component (spec §6.1, §12; ADR-20261123-4e40): the ruleset and merge settings as code, and GitHub
reached through `gh` with the person's own login.

The ruleset and merge settings are JSON, built here rather than from text templates (the templates README allows
it for structured files). Each builder is named like a template, `github/ruleset@1`, and never changes once
released, so `update` can rebuild an earlier render. Reading GitHub only ever sends GET requests; changing it is
`apply_ruleset` and `apply_settings`, which `init` calls after the person said yes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RULESET_NAME = "swerepo"
RULESET_FILE = ".github/swerepo/ruleset.json"
SETTINGS_FILE = ".github/swerepo/repo-settings.json"
CODEOWNERS = ".github/CODEOWNERS"
COPILOT_REVIEWER = "copilot-pull-request-reviewer[bot]"
# Governance paths a code owner reviews in team mode (spec §6.1).
GOVERNANCE_PATHS = (
    "/.github/", "/.swerepo.toml", "/AGENTS.md", "/CLAUDE.md", "/docs/adr/", "/docs/agents/", "/.seamspec/",
    "/docs/EARNED_SPEC.md",
)  # fmt: skip
OWNER = re.compile(r"^@[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:/[A-Za-z0-9][A-Za-z0-9._-]*)?$")
# github.com itself, not a look-alike host: from the start of the URL, an optional user, the host (review P5-F06)
_REMOTE = re.compile(
    r"^(?:(?:https?|ssh|git)://(?:[^@/]+@)?|[^@/:]+@)?github\.com(?::\d+)?[:/]"
    r"(?P<owner>[A-Za-z0-9-]+)/(?P<repo>[A-Za-z0-9._-]+?)(?:\.git)?/?$"
)


class GitHubError(RuntimeError):
    """A `gh` call failed. The message names the request, never a token or a local path."""

    def __init__(self, message: str, *, not_found: bool = False) -> None:
        super().__init__(message)
        self.not_found = not_found  # GitHub answered 404, as opposed to a timeout, a limit or a refusal


@dataclass(frozen=True)
class Settings:
    """What the ruleset is built from (recorded in `.swerepo.toml`: `mode`, `[github]`)."""

    mode: str  # "solo" or "team"
    code_owner: str | None  # "@login" or "@org/team"; None: no CODEOWNERS, no code-owner review
    copilot_review: bool = True
    extra_checks: tuple[str, ...] = ()
    merge_methods: tuple[str, ...] = ("squash",)


# --- builders (named and versioned like templates) ---------------------------------------------------------


def _ruleset_v1(settings: Settings) -> dict[str, Any]:
    team = settings.mode == "team"
    pull_request = {
        "allowed_merge_methods": list(settings.merge_methods),
        "dismiss_stale_reviews_on_push": team,
        "require_code_owner_review": team and settings.code_owner is not None,
        "require_last_push_approval": False,
        "required_approving_review_count": 1 if team else 0,
        "required_review_thread_resolution": team or settings.copilot_review,
    }
    checks = [{"context": "ci-ok"}, *({"context": name} for name in settings.extra_checks)]
    rules: list[dict[str, Any]] = [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "pull_request", "parameters": pull_request},
        {"type": "required_status_checks",
         "parameters": {"required_status_checks": checks, "strict_required_status_checks_policy": False}},
    ]  # fmt: skip
    if settings.copilot_review:
        params = {"review_draft_pull_requests": False, "review_on_push": False}
        rules.append({"type": "copilot_code_review", "parameters": params})
    return {
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "bypass_actors": [],
        "rules": rules,
    }


def _repo_settings_v1(settings: Settings) -> dict[str, Any]:
    squash = "squash" in settings.merge_methods
    return {
        "allow_squash_merge": squash,
        "allow_merge_commit": "merge" in settings.merge_methods,
        "allow_rebase_merge": "rebase" in settings.merge_methods,
        "allow_auto_merge": False,  # SWERepo never merges, and doesn't make merging unattended (spec §6.1)
        "delete_branch_on_merge": True,
        **({"squash_merge_commit_title": "PR_TITLE", "squash_merge_commit_message": "PR_BODY"} if squash else {}),
    }


BUILDERS: dict[str, Callable[[Settings], dict[str, Any]]] = {
    "github/ruleset@1": _ruleset_v1,
    "github/repo-settings@1": _repo_settings_v1,
}


def is_builder(template_id: str) -> bool:
    return template_id in BUILDERS


def latest(name: str) -> str:
    versions = sorted(int(t.rsplit("@", 1)[1]) for t in BUILDERS if t.startswith(f"github/{name}@"))
    return f"github/{name}@{versions[-1]}"


def as_text(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2) + "\n"


def render(name: str, settings: Settings, template_id: str | None = None) -> tuple[str, str]:
    """(builder id, JSON text) for `ruleset` or `repo-settings`."""
    builder = template_id or latest(name)
    return builder, as_text(BUILDERS[builder](settings))


def codeowners_lines(owner: str) -> str:
    paths = list(GOVERNANCE_PATHS)
    width = max(len(p) for p in paths) + 1
    return "\n".join(f"{path:<{width}}{owner}" for path in paths)


NO_OWNER = "none"  # the person's explicit "no code owner" (recorded, so the repository owner isn't proposed again)


def valid_owner(owner: object) -> bool:
    return isinstance(owner, str) and bool(OWNER.fullmatch(owner))


def has_copilot_review(ruleset: dict[str, Any]) -> bool:
    """Whether a ruleset requests Copilot's review: what decides whether CI waits for one (review P5-F10)."""
    rules = ruleset.get("rules") if isinstance(ruleset, dict) else None
    return any(isinstance(rule, dict) and rule.get("type") == "copilot_code_review" for rule in rules or [])


def ruleset_mode(ruleset: dict[str, Any]) -> str | None:
    """The mode a committed ruleset is in: `team` when it requires an approval, `solo` otherwise; None when it has no
    pull-request rule to tell from (review P5-F14)."""
    rules = ruleset.get("rules") if isinstance(ruleset, dict) else None
    for rule in rules or []:
        if isinstance(rule, dict) and rule.get("type") == "pull_request":
            count = (rule.get("parameters") or {}).get("required_approving_review_count", 0)
            return "team" if isinstance(count, int) and count >= 1 else "solo"
    return None


# What `repo-settings.json` may hold: the repository's merge settings, nothing else (spec §12). A field outside it
# (`private`, `visibility`, `name`, ...) would make applying the file change more than merging (PR #10 review).
MERGE_SETTINGS = frozenset({
    "allow_squash_merge", "allow_merge_commit", "allow_rebase_merge", "allow_auto_merge", "allow_update_branch",
    "delete_branch_on_merge", "squash_merge_commit_title", "squash_merge_commit_message", "merge_commit_title",
    "merge_commit_message", "use_squash_pr_title_as_default",
})  # fmt: skip


def not_applicable(name: str, data: dict[str, Any]) -> str | None:
    """Why a committed `ruleset` or `repo-settings` file can't be applied as it is, or None: a ruleset must keep the
    name `swerepo` (renamed, later runs couldn't find it and would make another), and the settings may hold merge
    settings only (PR #10 review)."""
    if name == "ruleset":
        if data.get("name") != RULESET_NAME:
            return f'its name is {json.dumps(data.get("name"))[:60]}, not "{RULESET_NAME}"'
        return None
    others = sorted(key for key in data if key not in MERGE_SETTINGS)
    if others:
        return "it holds fields that aren't merge settings (" + ", ".join(k[:40] for k in others[:5]) + ")"
    return None


def ruleset_changes(differences: list[str]) -> list[str]:
    """`ruleset_differences` read from the side of applying the committed file: a rule only GitHub has will be
    removed by the update, so say so (review P5-F01 question 3)."""
    return [f"removes {d.removesuffix(' added')}" if d.endswith(" added") else d for d in differences]


# --- GitHub through gh -------------------------------------------------------------------------------------


def repository(root: Path) -> str | None:
    """`owner/name` of the repository's GitHub remote (`origin`), read from git without the network."""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True, check=False,
            timeout=60,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = _REMOTE.search(done.stdout.strip()) if done.returncode == 0 else None
    return f"{match['owner']}/{match['repo']}" if match else None


@dataclass
class GitHub:
    """One repository on GitHub, through the `gh` command and the person's own login."""

    slug: str  # owner/name
    command: str = field(default_factory=lambda: shutil.which("gh") or "gh")
    _repo: dict[str, Any] | None = field(default=None, repr=False)

    @classmethod
    def connect(cls, root: Path) -> GitHub | None:
        """The repository's GitHub, or None without a github.com remote, `gh`, or a `gh` login."""
        slug = repository(root)
        command = shutil.which("gh")
        if slug is None or command is None:
            return None
        try:
            done = subprocess.run([command, "auth", "status"], capture_output=True, check=False, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return cls(slug, command) if done.returncode == 0 else None

    def _run(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        args = [self.command, "api", "-X", method, path, "-H", "Accept: application/vnd.github+json"]
        if body is not None:
            args += ["--input", "-"]
        try:
            done = subprocess.run(
                args, input=json.dumps(body) if body is not None else None, capture_output=True, text=True,
                check=False, timeout=120,
            )  # fmt: skip
        except (OSError, subprocess.TimeoutExpired) as error:
            raise GitHubError(f"{method} {path}: gh didn't answer ({type(error).__name__})") from error
        if done.returncode != 0:
            reason = _reason(done.stdout, done.stderr)
            raise GitHubError(f"{method} {path}: {reason}", not_found=reason.startswith("Not Found"))
        try:
            return json.loads(done.stdout) if done.stdout.strip() else None
        except json.JSONDecodeError as error:
            raise GitHubError(f"{method} {path}: not JSON") from error

    def get(self, path: str) -> Any:
        return self._run("GET", path)

    # reading
    def repo(self) -> dict[str, Any]:
        """The repository's settings, read once per GitHub object (check asks several times)."""
        if self._repo is None:
            self._repo = self.get(f"repos/{self.slug}")
        return self._repo

    def branch_requests_copilot(self, branch: str) -> bool:
        """Whether GitHub's active rules on `branch` include Copilot's review: the question CI's copilot-review
        asks, so an active ruleset that leaves the branch out counts as requesting nothing (PR #24 review)."""
        if not branch:
            raise GitHubError("no default branch to read the rules of")
        path = f"repos/{self.slug}/rules/branches/{urllib.parse.quote(branch, safe='')}?per_page=100"
        rules = self.get(path)
        return isinstance(rules, list) and any(
            isinstance(rule, dict) and rule.get("type") == "copilot_code_review" for rule in rules
        )

    def owner_login(self) -> tuple[str, str]:
        """(login, "User" or "Organization") of the repository's owner."""
        owner = self.repo().get("owner", {})
        return str(owner.get("login", "")), str(owner.get("type", ""))

    def find_ruleset(self) -> dict[str, Any] | None:
        """The repository's ruleset named `swerepo`, in full, or None. Every page is read, 100 at a time: a
        `swerepo` ruleset past the first page must be found, or init would create a second one."""
        page = 1
        while True:
            entries = self.get(f"repos/{self.slug}/rulesets?includes_parents=false&per_page=100&page={page}") or []
            for entry in entries:
                if entry.get("name") == RULESET_NAME:
                    return self.get(f"repos/{self.slug}/rulesets/{entry['id']}")
            if len(entries) < 100:
                return None
            page += 1

    def dependency_graph(self) -> bool:
        """Whether the dependency graph is on: its SBOM can be read only then. Only GitHub's 404 means "off";
        any other failure is raised, so it reads as "can't tell" (review P5-F06)."""
        try:
            self.get(f"repos/{self.slug}/dependency-graph/sbom")
        except GitHubError as error:
            if error.not_found:
                return False
            raise
        return True

    # changing (after the person's yes)
    def apply_ruleset(self, ruleset: dict[str, Any]) -> str:
        """Update the ruleset named `swerepo`, or create it. Other rulesets are never touched, and a ruleset by
        another name is never sent."""
        problem = not_applicable("ruleset", ruleset)
        if problem:
            raise GitHubError(f"ruleset not sent: {problem}")
        existing = self.find_ruleset()
        if existing is None:
            self._run("POST", f"repos/{self.slug}/rulesets", ruleset)
            return "created"
        self._run("PUT", f"repos/{self.slug}/rulesets/{existing['id']}", ruleset)
        return "updated"

    def apply_settings(self, settings: dict[str, Any]) -> None:
        """Change the repository's merge settings, and only those."""
        problem = not_applicable("repo-settings", settings)
        if problem:
            raise GitHubError(f"merge settings not sent: {problem}")
        self._run("PATCH", f"repos/{self.slug}", settings)
        self._repo = None


def _reason(stdout: str, stderr: str) -> str:
    """GitHub's message from a failed `gh api` call, on one line."""
    try:
        message = json.loads(stdout).get("message")
    except (json.JSONDecodeError, AttributeError):
        message = None
    text = message or stderr.strip().splitlines()[-1:] or ["failed"]
    return (text if isinstance(text, str) else text[0]).replace("\n", " ")[:200]


# --- comparing the live settings with the committed files ---------------------------------------------------


def ruleset_differences(committed: dict[str, Any], live: dict[str, Any]) -> list[str]:
    """What the live ruleset has differently from the committed one, by rule and field. Fields GitHub adds
    (ids, links, dates, parameters SWERepo doesn't set) are ignored."""
    found = [key for key in ("target", "enforcement") if committed.get(key) != live.get(key)]
    if _ref(committed) != _ref(live):
        found.append("branches")
    if (committed.get("bypass_actors") or []) != (live.get("bypass_actors") or []):
        found.append("bypass_actors")
    live_rules = {rule.get("type"): rule for rule in live.get("rules", [])}
    for rule in committed.get("rules", []):
        kind = rule.get("type")
        other = live_rules.pop(kind, None)
        if other is None:
            found.append(f"{kind} missing")
            continue
        for key, value in (rule.get("parameters") or {}).items():
            if _normal(key, value) != _normal(key, (other.get("parameters") or {}).get(key)):
                found.append(f"{kind}.{key}")
    found += [f"{kind} added" for kind in live_rules]
    return found


def _ref(ruleset: dict[str, Any]) -> tuple[list[str], list[str]]:
    ref = (ruleset.get("conditions") or {}).get("ref_name") or {}
    return sorted(ref.get("include", [])), sorted(ref.get("exclude", []))


def _normal(key: str, value: Any) -> Any:
    if key == "required_status_checks" and isinstance(value, list):
        return sorted(str(check.get("context")) for check in value if isinstance(check, dict))
    if isinstance(value, list):
        return sorted(map(str, value))
    return value


def settings_differences(committed: dict[str, Any], live: dict[str, Any]) -> list[str]:
    return [key for key, value in committed.items() if live.get(key) != value]
