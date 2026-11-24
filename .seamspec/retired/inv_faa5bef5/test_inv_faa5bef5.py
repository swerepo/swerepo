"""Rule: pull requests wait for Copilot's review inside ci-ok (ADR-20261123-a359). The generated steps are run as
written with bash, jq and a fake `gh` and `sleep` on PATH, with the values the job's own `env:` block gives them;
the workflow is read from the text, without YAML."""

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
}


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
# Only the pull request's reviews, listed in full (--paginate), through the job's own --jq filter. Copilot's
# review shows up from the call numbered $FIRST_REVIEW_AT on; anything else asked is an error.
echo "$*" >> "$CALLS"
[ -n "${GH_TOKEN:-}" ] || { echo "gh: not logged in (no GH_TOKEN)" >&2; exit 4; }  # the job must hand gh its token
[ "$1" = "api" ] && [ "$2" = "repos/acme/app/pulls/1/reviews" ] || { echo '{"message": "Not Found"}'; exit 1; }
case " $* " in *" --paginate "*) ;; *) echo "not paginated" >&2; exit 1 ;; esac
filter=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--jq" ]; then filter="$2"; shift; fi
  shift
done
count=$(($(cat "$COUNT") + 1))
echo "$count" > "$COUNT"
if [ "$count" -ge "$FIRST_REVIEW_AT" ]; then jq -r "$filter" "$REVIEWS"; else jq -r "$filter" "$NONE"; fi
"""


def _fake_tools(folder: Path, reviews: list[str], env: dict[str, str], first_review_at: int = 1) -> dict[str, str]:
    """A `gh` answering only the reviews address, and a `sleep` that returns at once, so the wait runs in a moment."""
    folder.mkdir()
    listing = [{"id": n, "user": {"login": login}} for n, login in enumerate(reviews, start=1)]
    (folder / "reviews.json").write_text(json.dumps(listing))
    (folder / "none.json").write_text("[]")
    (folder / "count").write_text("0")
    for name, body in (("gh", GH), ("sleep", "#!/bin/sh\nexit 0\n")):
        (folder / name).write_text(body)
        (folder / name).chmod((folder / name).stat().st_mode | stat.S_IEXEC)
    return {**os.environ, **env, "PATH": f"{folder}{os.pathsep}{os.environ['PATH']}",
            "REVIEWS": str(folder / "reviews.json"), "NONE": str(folder / "none.json"),
            "COUNT": str(folder / "count"), "CALLS": str(folder / "calls"),
            "FIRST_REVIEW_AT": str(first_review_at)}  # fmt: skip


def _run(script: str, env: dict[str, str]) -> int:
    return subprocess.run(["bash", "-c", script], env=env, capture_output=True, check=False).returncode


def _ci_ok_passes(text: str, results: dict[str, str], event: str) -> bool:
    env = {**os.environ, "EVENT": event, "PRIVATE": "false",
           "NEEDS": json.dumps({job: {"result": result} for job, result in results.items()})}  # fmt: skip
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
    env = _job_env(job, GITHUB)  # DRAFT, NUMBER, REPOSITORY and the token, as the job maps them
    assert set(env) >= {"DRAFT", "NUMBER", "REPOSITORY", "GH_TOKEN"}
    assert _run(wait, _fake_tools(tmp_path / "a", ["dev", REVIEWER], env)) == 0
    later_review = _fake_tools(tmp_path / "r", ["dev", REVIEWER], env, first_review_at=2)
    assert _run(wait, later_review) == 0  # none on the first ask, Copilot's on the second: it waited and asked again
    assert len((tmp_path / "r/calls").read_text().splitlines()) == 2
    draft = {**_fake_tools(tmp_path / "d", [REVIEWER], env), "DRAFT": "true"}  # no review is requested on drafts
    assert _run(wait, draft) != 0 and not (tmp_path / "d/calls").exists()  # failed at once, without asking
    # no review, or only others' ("copilot" and "copilot[bot]" look alike but aren't the reviewer)
    for reviews in ([], ["dev", "copilot", "copilot[bot]"]):
        assert _run(wait, _fake_tools(tmp_path / f"b{len(reviews)}", reviews, env)) != 0

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
