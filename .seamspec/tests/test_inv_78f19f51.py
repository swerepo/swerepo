"""Rule: pull requests wait for Copilot's review inside ci-ok (ADR-20261123-a359), except Dependabot's, for which
GitHub never requests one: they pass with only Dependabot's own commits, committed by GitHub, and fail at once with
any other (ADR-20261123-cc8d). The generated steps are run as written with bash, jq and a fake `gh` and `sleep` on
PATH, with the values the job's own `env:` block gives them; the workflow is read from the text, without YAML."""

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from swerepo.cli import app
from swerepo.init import apply, make_plan

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]
WORKFLOW = ".github/workflows/swerepo-ci.yml"
REVIEWER = "copilot-pull-request-reviewer[bot]"
# What GitHub gives the job's env: block, for a pull request #1 in acme/app.
GITHUB = {
    "${{ github.token }}": "x",
    "${{ github.repository }}": "acme/app",
    "${{ github.event.pull_request.number }}": "1",
    "${{ github.event.pull_request.draft }}": "false",
    "${{ github.event.pull_request.user.login }}": "dev",
    "${{ github.event.pull_request.head.repo.full_name }}": "acme/app",
}
AUTHOR = "${{ github.event.pull_request.user.login }}"
HEAD_REPO = "${{ github.event.pull_request.head.repo.full_name }}"
DRAFT = "${{ github.event.pull_request.draft }}"
BOT = "dependabot[bot]"
# Not Dependabot: people, look-alike names (`dependabotb` matches an unquoted `dependabot[bot]` glob), and other
# bots: Renovate (its commits aren't committed by GitHub, so its name could be faked) and a coding agent
STILL_WAIT = ("dev", "dependabot", "dependabotb", "dependabot[bot]x", "xdependabot[bot]", "renovate[bot]",
              "copilot-swe-agent[bot]")  # fmt: skip


def _repo(root: Path) -> Path:
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "app"\nrequires-python = ">=3.12"\n')
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    return root


def _jobs(text: str) -> dict[str, str]:
    body = text.split("\njobs:\n", 1)[1]
    return {
        m[1]: part
        for part in re.split(r"(?m)^(?=  [A-Za-z_][\w-]*:\s*$)", body)
        if (m := re.match(r"^  ([\w-]+):", part))
    }


def _script(job: str) -> str:
    lines = []
    for line in job.split("        run: |\n", 1)[1].splitlines():
        if line and not line.startswith("          "):
            break
        lines.append(line[10:])
    return "\n".join(lines) + "\n"


def _job_env(job: str, github: dict[str, str]) -> dict[str, str]:
    """The step's env: block, with GitHub's expressions replaced by what GitHub would give."""
    block = job.split("        env:\n", 1)[1].split("        run: |", 1)[0]
    found = {}
    for line in block.splitlines():
        name, _, value = line.strip().partition(": ")
        assert value in github, f"{name} reads {value}, which this test doesn't know"
        found[name] = github[value]
    return found


def _needs(text: str) -> list[str]:
    match = re.search(r"^  ci-ok:\n    if: always\(\)\n    needs: \[([^\]]*)\]", text, re.MULTILINE)
    assert match, "ci-ok runs always and names its needs"
    return [n.strip() for n in match[1].split(",")]


GH = """#!/bin/sh
# Only the pull request's reviews and commits, each listed in full (--paginate), through the job's own --jq filter.
# Copilot's review shows up from the reviews call numbered $FIRST_REVIEW_AT on; anything else asked is an error.
echo "$*" >> "$CALLS"
[ -n "${GH_TOKEN:-}" ] || { echo "gh: not logged in (no GH_TOKEN)" >&2; exit 4; }  # the job must hand gh its token
[ "$1" = "api" ] || { echo '{"message": "Not Found"}'; exit 1; }
case " $* " in *" --paginate "*) ;; *) echo "not paginated" >&2; exit 1 ;; esac
endpoint="$2"
filter=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--jq" ]; then filter="$2"; shift; fi
  shift
done
case "$endpoint" in
  repos/acme/app/pulls/1/commits) jq -r "$filter" "$COMMITS"; exit $? ;;
  repos/acme/app/pulls/1/reviews) ;;
  *) echo '{"message": "Not Found"}'; exit 1 ;;
esac
count=$(($(cat "$COUNT") + 1))
echo "$count" > "$COUNT"
if [ "$count" -ge "$FIRST_REVIEW_AT" ]; then jq -r "$filter" "$REVIEWS"; else jq -r "$filter" "$NONE"; fi
"""


class _Environment(dict):
    """The environment a step runs with. Never shown: a failing assertion would print every variable, keys and
    tokens included, into the test's output and CI logs."""

    def __repr__(self) -> str:
        return "<environment>"


def _fake_tools(folder: Path, reviews: list[str], env: dict[str, str], first_review_at: int = 1,
                commits: list[tuple[str | None, bool, str | None]] = ()) -> dict[str, str]:  # fmt: skip
    """A `gh` answering only the reviews and commits addresses, and a `sleep` that returns at once, so the wait runs
    in a moment. `commits`: (the author's login, or None when GitHub links no account; the signature verified; the
    committer's login: `web-flow` is GitHub itself, which commits and signs Dependabot's commits)."""
    folder.mkdir()
    listing = [{"id": n, "user": {"login": login}} for n, login in enumerate(reviews, start=1)]
    (folder / "reviews.json").write_text(json.dumps(listing))
    pushed = [{"author": {"login": login} if login else None, "committer": {"login": by} if by else None,
               "commit": {"verification": {"verified": verified}}} for login, verified, by in commits]  # fmt: skip
    (folder / "commits.json").write_text(json.dumps(pushed))
    (folder / "none.json").write_text("[]")
    (folder / "count").write_text("0")
    for name, body in (("gh", GH), ("sleep", '#!/bin/sh\necho "$*" >> "$SLEEPS"\nexit 0\n')):
        (folder / name).write_text(body)
        (folder / name).chmod((folder / name).stat().st_mode | stat.S_IEXEC)
    return _Environment({**os.environ, **env, "PATH": f"{folder}{os.pathsep}{os.environ['PATH']}",
            "REVIEWS": str(folder / "reviews.json"), "NONE": str(folder / "none.json"),
            "COUNT": str(folder / "count"), "CALLS": str(folder / "calls"), "COMMITS": str(folder / "commits.json"),
            "SLEEPS": str(folder / "sleeps"),
            "FIRST_REVIEW_AT": str(first_review_at)})  # fmt: skip


def _lines(path: Path) -> list[str]:
    """What a fake tool recorded, one call per line; nothing when it was never called."""
    return path.read_text().splitlines() if path.exists() else []


def _run(script: str, env: dict[str, str]) -> int:
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, check=False).returncode


def _ci_ok_passes(text: str, results: dict[str, str], event: str) -> bool:
    env = _Environment({**os.environ, "EVENT": event, "PRIVATE": "false",
                        "NEEDS": json.dumps({job: {"result": result} for job, result in results.items()})})  # fmt: skip
    return _run(_script(_jobs(text)["ci-ok"]), env) == 0


@pytest.mark.parametrize("later", [False, True])
def test_pull_requests_wait_for_copilots_review(tmp_path: Path, later: bool):
    assert shutil.which("bash") and shutil.which("jq"), "bash and jq run the generated steps"
    root = _repo(tmp_path / "app")
    if later:  # ci first, then github on its own: the unchanged workflow gets the wait
        apply(make_plan(root, only=["ci"], hosts=[]), root)
        apply(make_plan(root, only=["github"], hosts=[]), root)
    else:
        apply(make_plan(root, only=["ci", "github"], hosts=[]), root)
    text = (root / WORKFLOW).read_text()
    needs, job = _needs(text), _jobs(text).get("copilot-review", "")
    assert "copilot-review" in needs and job
    assert "    if: github.event_name == 'pull_request'\n" in job  # pull requests only: skipped on pushes
    # may read the pull request's reviews, nothing more: the permissions block holds that one line only
    granted = []
    for line in job.split("    permissions:\n", 1)[1].splitlines():
        if not line.startswith("      "):
            break
        granted.append(line.strip())
    assert granted == ["pull-requests: read"], granted
    # the pull request trigger itself lists ready_for_review: a draft made ready runs again
    triggers = r"\non:\n  pull_request:\n(?:    #.*\n)*    types: \[opened, synchronize, reopened, ready_for_review\]\n"
    assert re.search(triggers, text)

    wait = _script(job)
    env = _job_env(job, GITHUB)  # DRAFT, NUMBER, REPOSITORY, the author, its branch's repository and the token

    def as_github_gives(**changed: str) -> dict[str, str]:  # through the job's own env: mapping, not by its names
        return _job_env(job, {**GITHUB, **changed})

    assert set(env) >= {"DRAFT", "NUMBER", "REPOSITORY", "GH_TOKEN", "AUTHOR", "HEAD_REPO"}
    assert _run(wait, _fake_tools(tmp_path / "a", ["dev", REVIEWER], env)) == 0
    later_review = _fake_tools(tmp_path / "r", ["dev", REVIEWER], env, first_review_at=2)
    assert _run(wait, later_review) == 0  # none on the first ask, Copilot's on the second: it waited and asked again
    assert len((tmp_path / "r/calls").read_text().splitlines()) == 2
    draft = _fake_tools(tmp_path / "d", [REVIEWER], as_github_gives(**{DRAFT: "true"}))  # no review on drafts
    assert _run(wait, draft) != 0 and not (tmp_path / "d/calls").exists()  # failed at once, without asking
    # Dependabot's draft too: drafts are decided first, whoever opened them
    own = [(BOT, True, "web-flow")]
    bot_draft = _fake_tools(tmp_path / "bd", [], as_github_gives(**{DRAFT: "true", AUTHOR: BOT}), commits=own)
    assert _run(wait, bot_draft) != 0 and not (tmp_path / "bd/calls").exists()
    # no review, or only others' ("copilot" and "copilot[bot]" look alike but aren't the reviewer)
    for reviews in ([], ["dev", "copilot", "copilot[bot]"]):
        assert _run(wait, _fake_tools(tmp_path / f"b{len(reviews)}", reviews, env)) != 0
    # Dependabot's pull request passes at once while every commit is its own, committed and signed by GitHub, and
    # its branch is in this repository: it asks GitHub for the commits only, never for reviews
    own = [(BOT, True, "web-flow"), (BOT, True, "web-flow")]
    assert _run(wait, _fake_tools(tmp_path / "bot", [], as_github_gives(**{AUTHOR: BOT}), commits=own)) == 0
    calls = (tmp_path / "bot/calls").read_text().splitlines()
    assert len(calls) == 1 and "repos/acme/app/pulls/1/commits" in calls[0], calls
    # anything else on Dependabot's pull request fails at once, Copilot's review or not: no waiting, no asking for
    # reviews. Changes by people or agents go in a pull request of their own, which waits for Copilot.
    for index, (commits, head) in enumerate([
        ([(BOT, True, "web-flow"), ("dev", True, "dev")], "acme/app"),  # a person's commit on its branch
        ([(BOT, True, "web-flow"), (None, True, None)], "acme/app"),  # a commit linked to no account
        ([(BOT, False, "web-flow")], "acme/app"),  # Dependabot's name, but not verified
        ([(BOT, True, "dev")], "acme/app"),  # Dependabot's name, verified, but someone else's commit
        ([(BOT, True, None)], "acme/app"),  # Dependabot's name, verified, committer unknown
        ([(BOT, True, "web-flow")], "someone/app"),  # from a fork
        ([], "acme/app"),  # no commits listed
    ]):  # fmt: skip
        mapped = as_github_gives(**{AUTHOR: BOT, HEAD_REPO: head})
        folder = tmp_path / f"x{index}"
        assert _run(wait, _fake_tools(folder, [REVIEWER], mapped, commits=commits)) != 0, (commits, head)
        assert not (folder / "sleeps").exists(), (commits, head)  # failed at once
        assert not [c for c in _lines(folder / "calls") if "/reviews" in c], (commits, head)  # never asked
    for index, author in enumerate(STILL_WAIT):  # they wait: asked exactly 40 times with a pause after each, then fail
        commits = [(author, True, "web-flow")]
        tools = _fake_tools(tmp_path / f"w{index}", [], as_github_gives(**{AUTHOR: author}), commits=commits)
        assert _run(wait, tools) != 0, author
        asked = [c for c in _lines(tmp_path / f"w{index}/calls") if "/reviews" in c]
        paused = _lines(tmp_path / f"w{index}/sleeps")
        assert (len(asked), len(paused)) == (40, 40), (author, len(asked), len(paused))

    expected = {"test-macos": "skipped", "governance": "success", "dependency-review": "success"}
    pr = {name: expected.get(name, "success") for name in needs}
    assert _ci_ok_passes(text, pr, "pull_request")
    for wrong in ("failure", "cancelled", "skipped"):
        assert not _ci_ok_passes(text, {**pr, "copilot-review": wrong}, "pull_request"), wrong
    push = {**pr, "test-macos": "success", "governance": "skipped", "dependency-review": "skipped"}
    assert _ci_ok_passes(text, {**push, "copilot-review": "skipped"}, "push")
    assert not _ci_ok_passes(text, {**push, "copilot-review": "success"}, "push")


def test_no_wait_with_no_copilot_review(tmp_path: Path):
    root = _repo(tmp_path / "app")
    result = CliRunner().invoke(app, ["init", "--path", str(root), "--only", "ci,github", "--no-copilot-review",
                                      "--yes"])  # fmt: skip
    assert result.exit_code == 0, result.output
    text = (root / WORKFLOW).read_text()
    assert "copilot-review" not in _needs(text) and "copilot-review" not in _jobs(text)


def test_turning_copilot_review_off_later_removes_the_wait(tmp_path: Path):
    root = _repo(tmp_path / "app")
    runner = CliRunner()
    first = runner.invoke(app, ["init", "--path", str(root), "--only", "ci,github", "--yes"])
    assert first.exit_code == 0, first.output
    assert "copilot-review" in _needs((root / WORKFLOW).read_text())  # it waited
    off = runner.invoke(app, ["init", "--path", str(root), "--only", "github", "--no-copilot-review", "--yes"])
    assert off.exit_code == 0, off.output
    text = (root / WORKFLOW).read_text()
    assert "copilot-review" not in _needs(text) and "copilot-review" not in _jobs(text)


def test_the_committed_ruleset_decides(tmp_path: Path):
    """A ruleset the repository commits without Copilot review: no wait, whatever the defaults say."""
    root = _repo(tmp_path / "app")
    ruleset = {"name": "swerepo", "target": "branch", "enforcement": "active", "bypass_actors": [],
               "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
               "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}]}  # fmt: skip
    (root / ".github/swerepo").mkdir(parents=True)
    (root / ".github/swerepo/ruleset.json").write_text(json.dumps(ruleset, indent=2) + "\n")
    apply(make_plan(root, only=["ci", "github"], hosts=[]), root)
    text = (root / WORKFLOW).read_text()
    assert "copilot-review" not in _needs(text) and "copilot-review" not in _jobs(text)
