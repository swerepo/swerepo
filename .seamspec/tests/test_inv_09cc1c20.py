"""Rule: ci-ok waits for every job in the swerepo-ci.yml that init writes, and its step fails unless each job
did what was expected (ADR-20261122-4a06; SWEREPO-SPEC §6.2). The step is run as written, with bash and jq (both
on GitHub's runners), on sample results; it is read from the text, without a YAML library."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from swerepo.init import apply, make_plan

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]
WORKFLOW = ".github/workflows/swerepo-ci.yml"
PYPROJECT = '[project]\nname = "x"\nrequires-python = ">=3.12"\n'
BY_DESIGN = {  # job: the event (and repository visibility) in which it runs; otherwise it must be skipped
    "test-macos": lambda event, private: event == "push",
    "governance": lambda event, private: event == "pull_request",
    "dependency-review": lambda event, private: event == "pull_request" and not private,
}


def _jobs(text: str) -> dict[str, list[str]]:
    jobs: dict[str, list[str]] = {}
    current = None
    in_jobs = False
    for line in text.splitlines():
        if line and not line.startswith(" "):
            in_jobs = line.strip() == "jobs:"
            continue
        if in_jobs and (job := re.match(r"^  ([A-Za-z_][\w-]*):\s*(?:#.*)?$", line)):
            current = job[1]
            jobs[current] = []
        elif current and (needs := re.match(r"^    needs:\s*\[([^\]]*)\]", line)):
            jobs[current] = [n.strip() for n in needs[1].split(",") if n.strip()]
    return jobs


def _step(text: str) -> str:
    """The shell script of ci-ok's step, as GitHub would run it."""
    ci_ok = text.split("\n  ci-ok:\n", 1)[1]
    script = ci_ok.split("        run: |\n", 1)[1]
    lines = []
    for line in script.splitlines():
        if line and not line.startswith("          "):
            break
        lines.append(line[10:])
    return "\n".join(lines) + "\n"


def _passes(script: str, results: dict[str, str], event: str, private: bool) -> bool:
    needs = json.dumps({job: {"result": result, "outputs": {}} for job, result in results.items()})
    env = {**os.environ, "NEEDS": needs, "EVENT": event, "PRIVATE": "true" if private else "false"}
    done = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=False)
    return done.returncode == 0


def _expected(jobs: list[str], event: str, private: bool) -> dict[str, str]:
    return {j: ("success" if BY_DESIGN.get(j, lambda e, p: True)(event, private) else "skipped") for j in jobs}


def _check(text: str) -> None:
    assert shutil.which("bash") and shutil.which("jq"), "bash and jq are needed to run ci-ok's step"
    jobs = _jobs(text)
    others = set(jobs) - {"ci-ok"}
    assert "ci-ok" in jobs and len(others) >= 6 and set(jobs["ci-ok"]) == others
    assert re.search(r"^  ci-ok:\n    if: always\(\)$", text, re.MULTILINE)
    script = _step(text)
    needs = jobs["ci-ok"]
    for event, private in (("pull_request", False), ("pull_request", True), ("push", False)):
        good = _expected(needs, event, private)
        assert _passes(script, good, event, private), (event, private)
        for job in needs:
            for wrong in ("failure", "cancelled", "skipped", "success"):
                if wrong != good[job]:
                    results = {**good, job: wrong}
                    assert not _passes(script, results, event, private), (event, private, job, wrong)


def _repo(root: Path, extra: str) -> Path:
    (root / "pyproject.toml").write_text(PYPROJECT + extra)
    (root / "services/api").mkdir(parents=True)
    (root / "services/api/pyproject.toml").write_text('[project]\nname = "api"\n')
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    return root


@pytest.mark.parametrize(
    ("extra", "options"),
    [
        ("", {}),
        ("\n[tool.black]\nline-length = 100\n", {}),
        ("\n[tool.black]\nline-length = 100\n", {"lint": "gradual"}),
        ("", {"with_governance": True, "projects": ["services/api"]}),
    ],
)
def test_ci_ok_waits_for_every_job_and_fails_on_any_wrong_result(tmp_path: Path, extra: str, options: dict):
    root = _repo(tmp_path, extra)
    apply(make_plan(root, only=["ci"], hosts=[], **options), root)
    _check((root / WORKFLOW).read_text())


def test_jobs_asked_for_later_are_waited_for_too(tmp_path: Path):
    root = _repo(tmp_path, "")
    apply(make_plan(root, only=["ci"], hosts=[]), root)
    apply(make_plan(root, only=["ci"], hosts=[], with_governance=True, projects=["services/api"]), root)
    text = (root / WORKFLOW).read_text()
    _check(text)
    assert {"governance", "lint-services-api", "test-services-api"} <= set(_jobs(text)["ci-ok"])
