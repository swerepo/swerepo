"""`swerepo threads <pr>`: the open review threads of a pull request (spec §7, §12; ADR-20261123-4e40 point 9).

Read-only: one GraphQL query through `gh`, never a reply or a resolve (spec §17). Each open thread is listed with
its file and line, whether the code moved on (outdated), who started it, and the first line of its last comment.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass

from swerepo.github import GitHub, GitHubError

QUERY = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          isResolved isOutdated path line originalLine
          first: comments(first: 1) { nodes { author { login } } }
          last: comments(last: 1) { nodes { author { login } body url } }
        }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class Thread:
    path: str
    line: int | None
    outdated: bool
    started_by: str
    last_by: str
    last: str  # the first line of the last comment
    url: str

    @property
    def where(self) -> str:
        return f"{self.path}:{self.line}" if self.line else self.path


def _graphql(hub: GitHub, number: int, after: str | None) -> dict:
    owner, name = hub.slug.split("/", 1)
    args = [hub.command, "api", "graphql", "-f", f"query={QUERY}", "-F", f"number={number}",
            "-f", f"owner={owner}", "-f", f"name={name}"]  # fmt: skip
    if after:
        args += ["-f", f"after={after}"]
    try:
        done = subprocess.run(args, capture_output=True, text=True, check=False, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GitHubError(f"review threads: gh didn't answer ({type(error).__name__})") from error
    try:
        data = json.loads(done.stdout) if done.stdout.strip() else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):  # "null" or a list: not an answer (review P5-F13)
        data = {}
    errors = [e.get("message") for e in (data.get("errors") or []) if isinstance(e, dict) and e.get("message")]
    if done.returncode != 0 or errors:  # gh writes GraphQL's errors to stdout, often with nothing on stderr (P5-F07)
        reason = errors[0] if errors else (done.stderr.strip().splitlines() or ["failed"])[-1]
        raise GitHubError(f"review threads of #{number}: {reason}")
    pull = ((data.get("data") or {}).get("repository") or {}).get("pullRequest")
    if pull is None:
        raise GitHubError(f"no pull request #{number} in {hub.slug}")
    return pull["reviewThreads"]


def open_threads(hub: GitHub, number: int) -> list[Thread]:
    """Every unresolved review thread of the pull request, in GitHub's order."""
    found: list[Thread] = []
    after: str | None = None
    while True:
        page = _graphql(hub, number, after)
        for node in page.get("nodes", []):
            if node.get("isResolved"):
                continue
            first = (node.get("first") or {}).get("nodes") or [{}]
            last = (node.get("last") or {}).get("nodes") or [{}]
            body = (last[0].get("body") or "").strip().splitlines()
            found.append(Thread(
                path=node.get("path") or "", line=node.get("line") or node.get("originalLine"),
                outdated=bool(node.get("isOutdated")),
                started_by=((first[0].get("author") or {}).get("login")) or "?",
                last_by=((last[0].get("author") or {}).get("login")) or "?",
                last=body[0][:160] if body else "", url=last[0].get("url") or "",
            ))  # fmt: skip
        info = page.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            return found
        after = info.get("endCursor")


def render_text(number: int, threads: list[Thread]) -> str:
    if not threads:
        return f"#{number}: no open review threads."
    lines = [f"#{number}: {len(threads)} open review thread{'' if len(threads) == 1 else 's'}"]
    for thread in threads:
        outdated = " (outdated)" if thread.outdated else ""
        lines.append(f"- {thread.where}{outdated} · started by {thread.started_by} · last: {thread.last_by}")
        if thread.last:
            lines.append(f"  {thread.last}")
        lines.append(f"  {thread.url}")
    return "\n".join(lines)


def to_dict(number: int, threads: list[Thread]) -> dict:
    return {"pull_request": number, "open": len(threads), "threads": [asdict(t) for t in threads]}
