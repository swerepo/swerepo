"""The Copilot wait before the ruleset is applied (ADR-20261126-c228, review P8-C): `copilot-review` reads the default
branch's rules once and passes when nothing requests Copilot's review, and init says so where it leaves the ruleset
unapplied. The job's steps run as written with bash, jq and a fake `gh` and `sleep`; the locked rule's test goes
further (inv_78f19f51 and its replacement)."""

import datetime
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from fake_gh import FakeGh
from repo_helpers import git, git_init, make

from swerepo import github
from swerepo.cli import COPILOT_NOTE
from swerepo.init import apply, make_plan

TODAY = datetime.date(2026, 11, 26)
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
SLUG = "acme/app"
WORKFLOW = ".github/workflows/swerepo-ci.yml"
REVIEWER = "copilot-pull-request-reviewer[bot]"
GITHUB = {  # what GitHub gives the job's env: block, for pull request #1 in acme/app
    "${{ github.token }}": "x",
    "${{ github.repository }}": SLUG,
    "${{ github.event.pull_request.number }}": "1",
    "${{ github.event.pull_request.draft }}": "false",
    "${{ github.event.pull_request.user.login }}": "dev",
    "${{ github.event.pull_request.head.repo.full_name }}": SLUG,
    "${{ github.event.repository.default_branch }}": "main",
    "${{ github.event.repository.private }}": "false",
}
DEFAULT_BRANCH = "${{ github.event.repository.default_branch }}"
PRIVATE = "${{ github.event.repository.private }}"
UPGRADE = "Upgrade to GitHub Pro or make this repository public to enable this feature."
# SWERepo's own ruleset's rules, in its order (swerepo/github.py), over two pages as --paginate reads them
APPLIED = [[{"type": "deletion"}, {"type": "non_fast_forward"}],
           [{"type": "pull_request"}, {"type": "required_status_checks"},
            {"type": "copilot_code_review", "ruleset_id": 7}]]  # fmt: skip
LOOK_ALIKES = [[{"type": "deletion", "ruleset_source": "copilot_code_review"}],
               [{"type": "copilot_review"}, {"type": "copilot_code_review_x"}]]  # fmt: skip


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = git_init(tmp_path / "app")
    make(root, {"pyproject.toml": PYPROJECT, "uv.lock": "version = 1\n", "tests/test_app.py": "def test_x(): pass\n"})
    return root


def cli(*args: str, terminal: bool = False, monkeypatch=None, given: str | None = None):
    from typer.testing import CliRunner

    from swerepo import cli as module
    from swerepo.cli import app

    if monkeypatch is not None:
        monkeypatch.setattr(module, "_interactive", lambda: terminal)
    return CliRunner().invoke(app, list(args), input=given)


def _github(project: Path, tmp_path: Path, monkeypatch, live: dict | None = None) -> FakeGh:
    """The project on GitHub as acme/app, with gh logged in; `live`: GitHub's own `swerepo` ruleset, if any."""
    git(project, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
    fake = FakeGh(tmp_path / "fake-gh", monkeypatch)
    fake.set(f"GET repos/{SLUG}", {"owner": {"login": "dev", "type": "User"}, "allow_merge_commit": True})
    fake.set(f"GET repos/{SLUG}/rulesets", [{"id": 9, "name": "swerepo"}] if live else [])
    if live:
        fake.set(f"GET repos/{SLUG}/rulesets/9", live)
    fake.set(f"GET repos/{SLUG}/dependency-graph/sbom", {"sbom": {}})
    fake.set(f"POST repos/{SLUG}/rulesets", {"id": 9})
    fake.set(f"PUT repos/{SLUG}/rulesets/9", {"id": 9})
    fake.set(f"PATCH repos/{SLUG}", {})
    return fake


INIT = ("init", "--only", "ci,github", "--code-owner", "@dev", "--mode", "solo")


class TestTheNote:
    """init and update say that CI doesn't wait for Copilot yet wherever they leave the ruleset unapplied (P8-C05)."""

    def test_held_for_apply_github(self, project: Path, tmp_path: Path, monkeypatch):
        _github(project, tmp_path, monkeypatch)
        done = cli(*INIT, "--path", str(project), "--yes")
        assert done.exit_code == 0, done.output
        assert "--yes --apply-github" in done.output and COPILOT_NOTE in done.output
        assert "gh pr edit <number> --add-reviewer @copilot" in COPILOT_NOTE

    def test_update_held_for_apply_github(self, project: Path, tmp_path: Path, monkeypatch):
        _github(project, tmp_path, monkeypatch)
        assert cli(*INIT, "--path", str(project), "--yes").exit_code == 0
        (project / ".github/swerepo/ruleset.json").unlink()  # something for update to do
        done = cli("update", "--path", str(project), "--only", "github", "--yes")
        assert done.exit_code == 0, done.output
        assert COPILOT_NOTE in done.output

    def test_a_terminal_no_to_the_ruleset(self, project: Path, tmp_path: Path, monkeypatch):
        _github(project, tmp_path, monkeypatch)
        done = cli(*INIT, "--path", str(project), terminal=True, monkeypatch=monkeypatch,
                   given="y\nn\nn\n")  # fmt: skip
        assert done.exit_code == 0, done.output
        assert 'Apply ruleset "swerepo"' in done.output and COPILOT_NOTE in done.output

    def test_a_terminal_yes_to_the_ruleset_gets_no_note(self, project: Path, tmp_path: Path, monkeypatch):
        fake = _github(project, tmp_path, monkeypatch)
        done = cli(*INIT, "--path", str(project), terminal=True, monkeypatch=monkeypatch,
                   given="y\ny\nn\n")  # fmt: skip
        assert done.exit_code == 0, done.output
        assert "POST" in fake.methods() and COPILOT_NOTE not in done.output

    def test_gh_logged_out(self, project: Path, tmp_path: Path, monkeypatch):
        fake = _github(project, tmp_path, monkeypatch)
        fake.set("logged_in", False)
        done = cli(*INIT, "--path", str(project), "--yes")
        assert done.exit_code == 0, done.output
        assert "gh isn't installed or logged in" in done.output and COPILOT_NOTE in done.output

    def test_applied_with_apply_github_gets_no_note(self, project: Path, tmp_path: Path, monkeypatch):
        _github(project, tmp_path, monkeypatch)
        done = cli(*INIT, "--path", str(project), "--yes", "--apply-github")
        assert done.exit_code == 0, done.output
        assert COPILOT_NOTE not in done.output

    def test_never_with_no_copilot_review(self, project: Path, tmp_path: Path, monkeypatch):
        _github(project, tmp_path, monkeypatch)
        done = cli(*INIT, "--path", str(project), "--no-copilot-review", "--yes")
        assert done.exit_code == 0, done.output
        assert "--yes --apply-github" in done.output and COPILOT_NOTE not in done.output

    def test_never_with_no_copilot_review_and_gh_logged_out(self, project: Path, tmp_path: Path, monkeypatch):
        fake = _github(project, tmp_path, monkeypatch)
        fake.set("logged_in", False)
        done = cli(*INIT, "--path", str(project), "--no-copilot-review", "--yes")
        assert done.exit_code == 0, done.output
        assert "gh isn't installed or logged in" in done.output and COPILOT_NOTE not in done.output

    def test_not_before_a_github_repository_exists(self, project: Path):
        done = cli(*INIT, "--path", str(project), "--yes")
        assert done.exit_code == 0, done.output
        assert "gh repo create" in done.output and COPILOT_NOTE not in done.output

    @pytest.mark.parametrize(("enforcement", "noted"), [("disabled", True), ("evaluate", True), ("active", False)])
    def test_only_an_active_ruleset_on_github_requests_copilot(self, project: Path, tmp_path, monkeypatch,
                                                              enforcement: str, noted: bool):  # fmt: skip
        """GitHub's `swerepo` ruleset with Copilot's rule requests nothing unless it is active (P8-C07)."""
        live = github.BUILDERS["github/ruleset@1"](github.Settings("solo", "@dev"))
        _github(project, tmp_path, monkeypatch, live={**live, "id": 9, "enforcement": enforcement})
        done = cli(*INIT, "--path", str(project), "--yes")
        assert done.exit_code == 0, done.output
        assert "--yes --apply-github" in done.output and (COPILOT_NOTE in done.output) is noted, done.output

    def test_not_when_githubs_ruleset_already_requests_copilot(self, project: Path, tmp_path, monkeypatch):
        """Only the merge settings are held: GitHub's ruleset already requests Copilot, so CI waits already."""
        live = github.BUILDERS["github/ruleset@1"](github.Settings("solo", "@dev"))
        _github(project, tmp_path, monkeypatch, live={**live, "id": 9})
        done = cli(*INIT, "--path", str(project), "--yes")
        assert done.exit_code == 0, done.output
        assert "--yes --apply-github" in done.output and COPILOT_NOTE not in done.output


# The job, run as written


def _job(text: str) -> str:
    return text.split("\n  copilot-review:\n", 1)[1].split("\n\n", 1)[0]


def _script(job: str) -> str:
    lines = []
    for line in job.split("        run: |\n", 1)[1].splitlines():
        if line and not line.startswith("          "):
            break
        lines.append(line[10:])
    return "\n".join(lines) + "\n"


def _env(job: str, given: dict[str, str]) -> dict[str, str]:
    block = job.split("        env:\n", 1)[1].split("        run: |", 1)[0]
    found = {}
    for line in block.splitlines():
        name, _, value = line.strip().partition(": ")
        assert value in given, f"{name} reads {value}, which this test doesn't know"
        found[name] = given[value]
    return found


# A fake gh: the rules page by page through the job's own --jq filter (as --paginate does), or a failure as gh gives
# it (the error body on stdout, `gh: … (HTTP 403)` on stderr, exit 1); the reviews; anything else is a 404.
GH = """#!/bin/sh
echo "$*" >> "$CALLS"
endpoint="$2"
filter=""
while [ $# -gt 0 ]; do
  if [ "$1" = "--jq" ]; then filter="$2"; shift; fi
  shift
done
case "$endpoint" in
  */rules/branches/*)
    if [ -n "${RULES_FAIL:-}" ]; then
      cat "$RULES_FAIL_BODY"; echo "$RULES_FAIL" >&2; exit 1
    fi
    for page in "$RULES"/page-*.json; do jq -r "$filter" "$page" || exit 1; done ;;
  */reviews) jq -r "$filter" "$REVIEWS" ;;
  *) echo '{"message": "Not Found"}'; echo "gh: Not Found (HTTP 404)" >&2; exit 1 ;;
esac
"""


class _Environment(dict):
    def __repr__(self) -> str:  # never print the environment into a failing test's output
        return "<environment>"


def _tools(folder: Path, env: dict[str, str], pages: list[list[dict]], reviews: list[str] = (),
           fail: str | None = None) -> _Environment:  # fmt: skip
    folder.mkdir()
    (folder / "rules").mkdir()
    for number, page in enumerate(pages, start=1):
        (folder / f"rules/page-{number}.json").write_text(json.dumps(page))
    (folder / "reviews.json").write_text(json.dumps([{"id": n, "user": {"login": r}} for n, r in enumerate(reviews)]))
    (folder / "body.json").write_text(json.dumps({"message": UPGRADE, "status": "403"}))
    for name, body in (("gh", GH), ("sleep", '#!/bin/sh\necho "$*" >> "$SLEEPS"\n')):
        (folder / name).write_text(body)
        (folder / name).chmod((folder / name).stat().st_mode | stat.S_IEXEC)
    return _Environment({**os.environ, **env, "PATH": f"{folder}{os.pathsep}{os.environ['PATH']}",
                         "CALLS": str(folder / "calls"), "SLEEPS": str(folder / "sleeps"),
                         "RULES": str(folder / "rules"), "REVIEWS": str(folder / "reviews.json"),
                         "RULES_FAIL": fail or "", "RULES_FAIL_BODY": str(folder / "body.json")})  # fmt: skip


def _lines(path: Path) -> list[str]:
    return path.read_text().splitlines() if path.exists() else []


@pytest.fixture
def job(project: Path) -> str:
    apply(make_plan(project, only=["ci", "github"], today=TODAY, hosts=[]), project)
    return _job((project / WORKFLOW).read_text())


class TestTheJob:
    def run(self, job: str, folder: Path, pages, reviews=(), fail=None, **changed: str):
        assert shutil.which("bash") and shutil.which("jq"), "bash and jq run the generated steps"
        tools = _tools(folder, _env(job, {**GITHUB, **changed}), pages, reviews, fail)
        result = subprocess.run(["bash", "-c", _script(job)], env=tools, capture_output=True, text=True, check=False)
        calls = _lines(folder / "calls")
        rules = [c for c in calls if "/rules/branches/" in c]
        return result, rules, [c for c in calls if "/reviews" in c], _lines(folder / "sleeps")

    def test_values_come_through_env_never_inside_the_script(self, job: str):
        assert "${{" not in _script(job)
        assert {"DEFAULT_BRANCH", "PRIVATE"} <= set(_env(job, GITHUB))
        assert "pull_request.base" not in job  # the default branch decides, never the pull request's base
        granted = job.split("    permissions:\n", 1)[1].split("\n    steps:", 1)[0].split()
        assert granted == ["pull-requests:", "read"]

    def test_no_copilot_rule_passes_at_once(self, job: str, tmp_path: Path):
        for index, pages in enumerate(([[{"type": "deletion"}]], [[]], LOOK_ALIKES)):
            result, rules, reviews, paused = self.run(job, tmp_path / f"n{index}", pages)
            assert result.returncode == 0, result.stdout + result.stderr
            assert len(rules) == 1 and "--paginate" in rules[0] and not reviews and not paused, pages
            assert "the ruleset isn't applied" in result.stdout and "--add-reviewer @copilot" in result.stdout

    def test_a_copilot_rule_on_a_later_page_waits(self, job: str, tmp_path: Path):
        result, rules, reviews, paused = self.run(job, tmp_path / "w", APPLIED)
        assert result.returncode != 0 and len(rules) == 1 and (len(reviews), len(paused)) == (40, 40)
        assert "gh pr edit 1 --add-reviewer @copilot" in result.stdout
        result, rules, reviews, _ = self.run(job, tmp_path / "r", APPLIED, reviews=["dev", REVIEWER])
        assert result.returncode == 0 and len(rules) == 1 and len(reviews) == 1

    @pytest.mark.parametrize(("branch", "asked"), [("main", "main"), ("release/1.0", "release%2F1.0"),
                                                   ("fix#1", "fix%231"), ("100%", "100%25")])  # fmt: skip
    def test_the_default_branch_is_one_encoded_path_segment(self, job: str, tmp_path: Path, branch: str, asked: str):
        result, rules, _, _ = self.run(job, tmp_path / "b", [[]], **{DEFAULT_BRANCH: branch})
        assert result.returncode == 0 and len(rules) == 1, rules
        assert rules[0].split()[1] == f"repos/{SLUG}/rules/branches/{asked}", rules

    def test_an_empty_default_branch_fails_without_asking(self, job: str, tmp_path: Path):
        result, rules, reviews, _ = self.run(job, tmp_path / "e", [[]], **{DEFAULT_BRANCH: ""})
        assert result.returncode != 0 and not rules and not reviews

    @pytest.mark.parametrize(("private", "error", "passes"), [
        ("true", f"gh: {UPGRADE} (HTTP 403)", True),  # a private repository on GitHub Free: no rulesets there
        ("false", f"gh: {UPGRADE} (HTTP 403)", False),  # never on a public repository
        ("true", "gh: Resource not accessible by integration (HTTP 403)", False),  # another 403
        # Near the Free-plan answer, and each fails: only gh's exact stderr passes (fails closed if GitHub changes it)
        ("true", "gh: Upgrade to GitHub Pro to enable this feature. (HTTP 403)", False),  # another Upgrade message
        ("true", f"gh: {UPGRADE} See the docs. (HTTP 403)", False),  # more text before the status
        ("true", f"gh: {UPGRADE} (HTTP 403) Retry later.", False),  # more text after it
        ("true", f"gh: {UPGRADE} (HTTP 403)\ngh: something else", False),  # the line among others
        ("true", f"warning: something\ngh: {UPGRADE} (HTTP 403)", False),
        ("true", f"gh: {UPGRADE.lower()} (HTTP 403)", False),  # another case
        ("true", f"gh: {UPGRADE} (HTTP 404)", False),
        ("true", "gh: Not Found (HTTP 404)", False),
        ("false", "gh: Bad credentials (HTTP 401)", False),
        ("true", "gh: Bad credentials (HTTP 401)", False),  # private: only the exact Free-plan answer passes
        ("false", "gh: Server Error (HTTP 500)", False),
        ("true", "gh: Server Error (HTTP 500)", False),
    ])  # fmt: skip
    def test_a_failed_read_fails_but_for_githubs_free_plan(self, job: str, tmp_path, private, error, passes):
        result, rules, reviews, paused = self.run(job, tmp_path / "f", [[]], fail=error, **{PRIVATE: private})
        assert (result.returncode == 0) is passes, result.stdout + result.stderr
        assert len(rules) == 1 and not reviews and not paused
        if passes:
            assert "aren't available on this private repository's plan" in result.stdout
        else:
            assert error in result.stderr

    def test_no_temporary_file_is_left_behind(self, job: str, tmp_path: Path):
        """Every way out of the step removes the file holding gh's error, keeping its exit status (P8-C06). A
        `mktemp` on PATH makes its file in the test's folder: macOS's own ignores TMPDIR without a template."""
        cases = {  # name: (rules, reviews, failed read, private, passes)
            "no rule": ([[]], [], None, "false", True),
            "reviewed": (APPLIED, [REVIEWER], None, "false", True),
            "no review": (APPLIED, [], None, "false", False),
            "free plan": ([[]], [], f"gh: {UPGRADE} (HTTP 403)", "true", True),
            "failed read": ([[]], [], "gh: Server Error (HTTP 500)", "false", False),
        }
        for name, (pages, reviews, fail, private, passes) in cases.items():
            temporary = tmp_path / f"tmp-{name}"
            temporary.mkdir()
            tools = _tools(tmp_path / name, _env(job, {**GITHUB, PRIVATE: private}), pages, reviews, fail)
            tools["TMPDIR"] = str(temporary)
            mktemp = tmp_path / name / "mktemp"
            mktemp.write_text('#!/bin/sh\nf="$TMPDIR/tmp.$$"\n: > "$f"\necho "$f"\n')
            mktemp.chmod(mktemp.stat().st_mode | stat.S_IEXEC)
            done = subprocess.run(["bash", "-c", _script(job)], env=tools, capture_output=True, text=True, check=False)
            assert (done.returncode == 0) is passes, (name, done.stdout + done.stderr)
            assert list(temporary.iterdir()) == [], name

    def test_drafts_and_dependabot_never_read_the_rules(self, job: str, tmp_path: Path):
        draft = "${{ github.event.pull_request.draft }}"
        result, rules, reviews, _ = self.run(job, tmp_path / "d", [[]], **{draft: "true"})
        assert result.returncode != 0 and not rules and not reviews
        author = "${{ github.event.pull_request.user.login }}"
        result, rules, _, _ = self.run(job, tmp_path / "bot", [[]], **{author: "dependabot[bot]"})
        assert result.returncode != 0 and not rules  # no commits listed: it fails at once, rules never read
