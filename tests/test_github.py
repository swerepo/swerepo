"""The `github` component, `check` against GitHub, `swerepo threads`, and the Copilot review wait
(spec §6.1, §12; ADR-20261123-4e40, ADR-20261123-a359). GitHub is a fake `gh` on PATH: nothing leaves the test."""

import datetime
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fake_gh import FakeGh
from repo_helpers import commit, git, git_init, make
from typer.testing import CliRunner

from swerepo import github
from swerepo.check import MISSING, OK, run_check, workflow_jobs
from swerepo.cli import app
from swerepo.init import APPLY, CURRENT, KEEP, WAITING, apply, apply_github, make_plan
from swerepo.state import State

TODAY = datetime.date(2026, 11, 23)
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
WORKFLOW = ".github/workflows/swerepo-ci.yml"
SLUG = "acme/app"


def action(plan, path):
    return next(a for a in plan.actions if a.path == path)


def notes(plan):
    return [a.note for a in plan.actions if a.component == "github" and a.verb in ("note", WAITING, APPLY, CURRENT)]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "app"
    root.mkdir()
    git_init(root)
    make(root, {"pyproject.toml": PYPROJECT, "uv.lock": "version = 1\n"})
    return root


@pytest.fixture
def gh(tmp_path: Path, monkeypatch, project: Path) -> FakeGh:
    """The project on GitHub (as acme/app, owned by a user), with gh logged in."""
    git(project, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
    fake = FakeGh(tmp_path / "fake-gh", monkeypatch)
    fake.set(f"GET repos/{SLUG}", {"owner": {"login": "dev", "type": "User"}, "allow_merge_commit": True,
                                   "allow_squash_merge": True, "allow_rebase_merge": True,
                                   "delete_branch_on_merge": False, "allow_auto_merge": False})  # fmt: skip
    fake.set(f"GET repos/{SLUG}/rulesets", [])
    fake.set(f"GET repos/{SLUG}/dependency-graph/sbom", {"sbom": {}})
    fake.set(f"POST repos/{SLUG}/rulesets", {"id": 7})
    fake.set(f"PATCH repos/{SLUG}", {})
    return fake


def plan_for(root: Path, **kwargs):
    return make_plan(root, only=["github"], today=TODAY, hosts=[], **kwargs)


class TestRuleset:
    def test_solo_and_team(self):
        solo = github.BUILDERS["github/ruleset@1"](github.Settings("solo", "@dev"))
        rules = {rule["type"]: rule.get("parameters") for rule in solo["rules"]}
        assert solo["name"] == "swerepo" and solo["bypass_actors"] == []
        assert solo["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]
        assert rules["pull_request"]["required_approving_review_count"] == 0
        assert rules["pull_request"]["required_review_thread_resolution"] is True  # Copilot review is on
        assert rules["pull_request"]["allowed_merge_methods"] == ["squash"]
        assert rules["required_status_checks"]["required_status_checks"] == [{"context": "ci-ok"}]
        assert rules["copilot_code_review"] == {"review_draft_pull_requests": False, "review_on_push": False}
        team = github.BUILDERS["github/ruleset@1"](github.Settings("team", "@dev", extra_checks=("web",)))
        pull = next(r["parameters"] for r in team["rules"] if r["type"] == "pull_request")
        assert pull["required_approving_review_count"] == 1 and pull["require_code_owner_review"]
        assert pull["dismiss_stale_reviews_on_push"]
        checks = next(r for r in team["rules"] if r["type"] == "required_status_checks")["parameters"]
        assert [c["context"] for c in checks["required_status_checks"]] == ["ci-ok", "web"]

    def test_without_copilot_review_or_a_code_owner(self):
        ruleset = github.BUILDERS["github/ruleset@1"](github.Settings("solo", None, copilot_review=False))
        assert "copilot_code_review" not in {rule["type"] for rule in ruleset["rules"]}
        pull = next(r["parameters"] for r in ruleset["rules"] if r["type"] == "pull_request")
        assert not pull["required_review_thread_resolution"]  # solo without Copilot: nothing to resolve
        team = github.BUILDERS["github/ruleset@1"](github.Settings("team", None))
        assert not next(r for r in team["rules"] if r["type"] == "pull_request")["parameters"][
            "require_code_owner_review"
        ]  # no real owner named: code-owner review would block every merge

    def test_merge_settings(self):
        settings = github.BUILDERS["github/repo-settings@1"](github.Settings("solo", None))
        assert settings["allow_squash_merge"] and not settings["allow_merge_commit"]
        assert not settings["allow_rebase_merge"] and settings["delete_branch_on_merge"]
        assert settings["allow_auto_merge"] is False

    def test_differences_ignore_what_github_adds(self):
        committed = github.BUILDERS["github/ruleset@1"](github.Settings("solo", "@dev"))
        live = json.loads(json.dumps(committed))
        live.update(id=7, source="acme/app", created_at="x")
        for rule in live["rules"]:
            if rule["type"] == "pull_request":
                rule["parameters"]["required_reviewers"] = []  # a parameter SWERepo doesn't set
        assert github.ruleset_differences(committed, live) == []
        next(r for r in live["rules"] if r["type"] == "pull_request")["parameters"]["allowed_merge_methods"] = [
            "merge", "squash"]  # fmt: skip
        live["rules"] = [r for r in live["rules"] if r["type"] != "copilot_code_review"]
        assert github.ruleset_differences(committed, live) == [
            "pull_request.allowed_merge_methods", "copilot_code_review missing"]  # fmt: skip


class TestInitWithoutGitHub:
    def test_files_are_written_and_the_ruleset_waits(self, project: Path):
        plan = plan_for(project, code_owner="@dev")
        apply(plan, project)
        for path in (".github/swerepo/ruleset.json", ".github/swerepo/repo-settings.json",
                     ".github/copilot-instructions.md", ".github/dependabot.yml",
                     ".github/pull_request_template.md", ".github/ISSUE_TEMPLATE/bug.md",
                     ".github/ISSUE_TEMPLATE/feature.md", ".github/CODEOWNERS"):  # fmt: skip
            assert (project / path).is_file(), path
        assert any(n.startswith("ruleset and merge settings: waiting") for n in notes(plan))
        assert "package-ecosystem: uv" in (project / ".github/dependabot.yml").read_text()
        codeowners = (project / ".github/CODEOWNERS").read_text()
        assert codeowners.rstrip().endswith("# swerepo:end") and "/docs/adr/" in codeowners and "@dev" in codeowners
        state = State.load(project)
        assert state.mode == "solo" and state.values["code_owner"] == "@dev"
        assert state.github == {"copilot_review": True, "applied": False}
        assert not plan_for(project).changes  # a second run: nothing to do

    def test_no_code_owner_no_codeowners(self, project: Path):
        plan = plan_for(project)
        assert not (project / ".github/CODEOWNERS").exists() and not any(a.path == ".github/CODEOWNERS"
                                                                         for a in plan.actions)  # fmt: skip
        assert any(n.startswith("CODEOWNERS not written") for n in notes(plan))

    def test_existing_files_are_kept_or_gain_a_block(self, project: Path):
        theirs = {".github/CODEOWNERS": "/src/ @team\n", ".github/copilot-instructions.md": "# Ours\n",
                  ".github/PULL_REQUEST_TEMPLATE.md": "# Ours\n", ".github/ISSUE_TEMPLATE/x.md": "x\n"}  # fmt: skip
        make(project, theirs)
        commit(project)
        plan = plan_for(project, code_owner="@dev")
        apply(plan, project)
        assert (project / ".github/CODEOWNERS").read_text().startswith("/src/ @team\n\n# swerepo:begin")
        assert (project / ".github/copilot-instructions.md").read_text().startswith("# Ours\n\n<!-- swerepo:begin")
        assert action(plan, ".github/PULL_REQUEST_TEMPLATE.md").verb == KEEP
        assert action(plan, ".github/ISSUE_TEMPLATE").verb == KEEP
        assert run_check(project, only=["github"]).count(MISSING) <= 1  # only "ruleset not applied"

    @pytest.mark.parametrize("owner", ["dev", "@", "@dev/", "@a b", "@-dev"])
    def test_a_code_owner_must_be_a_login_or_team(self, project: Path, owner: str):
        from swerepo.check import UsageError

        with pytest.raises(UsageError, match="--code-owner"):
            plan_for(project, code_owner=owner)

    def test_pip_projects_get_pip_updates(self, tmp_path: Path):
        git_init(tmp_path)
        make(tmp_path, {"pyproject.toml": PYPROJECT})
        apply(plan_for(tmp_path), tmp_path)
        assert "package-ecosystem: pip" in (tmp_path / ".github/dependabot.yml").read_text()


class TestInitWithGitHub:
    def test_defaults_come_from_the_owner(self, project: Path, gh: FakeGh):
        plan = plan_for(project)
        state_mode = next(n for n in notes(plan) if n.startswith("mode:"))
        assert state_mode.startswith("mode: solo") and plan.github_question
        assert "@dev" in action(plan, ".github/CODEOWNERS").content  # the owner, never git config
        gh.set(f"GET repos/{SLUG}", {"owner": {"login": "acme", "type": "Organization"}})
        plan = plan_for(project)
        assert next(n for n in notes(plan) if n.startswith("mode:")).startswith("mode: team")
        assert not any(a.path == ".github/CODEOWNERS" for a in plan.actions)  # an organisation isn't an owner

    def test_the_plan_shows_what_it_would_apply_and_writes_nothing_to_github(self, project: Path, gh: FakeGh):
        plan = plan_for(project)
        assert plan.github_slug == SLUG and set(plan.github_apply) == {"ruleset", "settings"}
        assert any(n.startswith('ruleset "swerepo" on the default branch (create)') for n in notes(plan))
        assert any("allow_merge_commit" in n for n in notes(plan))
        assert set(gh.methods()) == {"GET"}

    def test_yes_applies_both_and_records_it(self, project: Path, gh: FakeGh):
        result = CliRunner().invoke(app, ["init", "--path", str(project), "--only", "github", "--yes"])
        assert result.exit_code == 0, result.output
        assert (
            'GitHub: ruleset "swerepo" created' in result.output and "GitHub: merge settings applied" in result.output
        )
        posted = next(c for c in gh.calls() if c["args"][2:4] == ["POST", f"repos/{SLUG}/rulesets"])
        assert json.loads(posted["body"])["name"] == "swerepo"
        patched = next(c for c in gh.calls() if c["args"][2:4] == ["PATCH", f"repos/{SLUG}"])
        assert json.loads(patched["body"])["allow_merge_commit"] is False
        assert State.load(project).github["applied"] is True

    def test_a_ruleset_named_swerepo_is_adopted_and_others_left_alone(self, project: Path, gh: FakeGh):
        gh.set(f"GET repos/{SLUG}/rulesets", [{"id": 3, "name": "theirs"}, {"id": 7, "name": "swerepo"}])
        gh.set(f"GET repos/{SLUG}/rulesets/7", {"id": 7, "name": "swerepo", "rules": []})
        gh.set(f"PUT repos/{SLUG}/rulesets/7", {"id": 7})
        plan = plan_for(project)
        apply(plan, project)
        assert apply_github(plan, project, ["ruleset"]) == ['ruleset "swerepo" updated']
        changed = [c["args"][2:4] for c in gh.calls() if c["args"][2:3] in (["PUT"], ["POST"], ["PATCH"], ["DELETE"])]
        assert changed == [["PUT", f"repos/{SLUG}/rulesets/7"]]  # not ruleset 3, and not the settings (not chosen)
        assert State.load(project).github["applied"] is False  # the settings are still to apply

    def test_nothing_applied_without_yes_and_without_a_terminal(self, project: Path, gh: FakeGh):
        result = CliRunner().invoke(app, ["init", "--path", str(project), "--only", "github"])
        assert result.exit_code == 2 and set(gh.methods()) == {"GET"}

    def test_a_current_ruleset_and_settings_need_nothing(self, project: Path, gh: FakeGh):
        settings = github.Settings("solo", "@dev")
        gh.set(f"GET repos/{SLUG}/rulesets", [{"id": 7, "name": "swerepo"}])
        gh.set(f"GET repos/{SLUG}/rulesets/7", {"id": 7, **github.BUILDERS["github/ruleset@1"](settings)})
        gh.set(f"GET repos/{SLUG}", {"owner": {"login": "dev", "type": "User"},
                                     **github.BUILDERS["github/repo-settings@1"](settings)})  # fmt: skip
        plan = plan_for(project)
        assert not plan.github_apply and {a.verb for a in plan.actions if a.path is None and a.verb != "note"} == {
            CURRENT
        }

    def test_dependency_graph_off_is_noted(self, project: Path, gh: FakeGh):
        del gh.responses[f"GET repos/{SLUG}/dependency-graph/sbom"]
        gh.save()
        assert any("dependency graph is off" in n for n in notes(plan_for(project)))


class TestCheckAgainstGitHub:
    def _applied(self, project: Path, gh: FakeGh) -> None:
        apply(plan_for(project, code_owner="@dev"), project)
        settings = github.Settings("solo", "@dev")
        gh.set(f"GET repos/{SLUG}/rulesets", [{"id": 7, "name": "swerepo"}])
        gh.set(f"GET repos/{SLUG}/rulesets/7", {"id": 7, **github.BUILDERS["github/ruleset@1"](settings)})
        repo = {"owner": {"login": "dev", "type": "User"}, **github.BUILDERS["github/repo-settings@1"](settings),
                "security_and_analysis": {"secret_scanning": {"status": "enabled"},
                                          "secret_scanning_push_protection": {"status": "enabled"}}}  # fmt: skip
        gh.set(f"GET repos/{SLUG}", repo)

    def test_live_settings_match_and_check_only_reads(self, project: Path, gh: FakeGh):
        self._applied(project, gh)
        before = len(gh.calls())
        report = run_check(project, only=["github", "security"], read_github=True)
        findings = {f.item: f for f in report.findings}
        assert findings["github.ruleset"].status == OK and findings["github.merge-settings"].status == OK
        assert findings["security.secret-scanning"].status == OK
        assert set(gh.methods()[before:]) == {"GET"}

    def test_drift_on_github_is_missing(self, project: Path, gh: FakeGh):
        self._applied(project, gh)
        gh.responses[f"GET repos/{SLUG}"]["allow_merge_commit"] = True
        gh.responses[f"GET repos/{SLUG}"]["security_and_analysis"]["secret_scanning_push_protection"] = {
            "status": "disabled"}  # fmt: skip
        gh.save()
        findings = {f.item: f for f in run_check(project, only=["github", "security"], read_github=True).findings}
        assert findings["github.merge-settings"].status == MISSING
        assert "allow_merge_commit" in findings["github.merge-settings"].message
        assert findings["security.secret-scanning"].message.startswith("secret scanning push protection off")

    def test_ci_never_calls_gh(self, project: Path, gh: FakeGh):
        self._applied(project, gh)
        before = len(gh.calls())
        result = CliRunner().invoke(app, ["check", "--path", str(project), "--ci"])
        assert len(gh.calls()) == before and "can't tell (needs gh" in result.output

    def test_without_a_github_repository_the_ruleset_is_not_applied(self, project: Path):
        apply(plan_for(project), project)
        finding = {f.item: f for f in run_check(project, read_github=True).findings}["github.live"]
        assert finding.status == MISSING and finding.message == "ruleset not applied (no GitHub repository yet)"

    def test_builders_count_as_known_templates(self, project: Path):
        apply(plan_for(project), project)
        messages = [f.message for f in run_check(project, only=["github"]).findings]
        assert not [m for m in messages if "isn't in this SWERepo" in m]  # github/ruleset@1 is a builder, known
        assert any(m == ".github/swerepo/ruleset.json (current)" or "ruleset as code" in m for m in messages)


THREADS = {"data": {"repository": {"pullRequest": {"reviewThreads": {
    "pageInfo": {"hasNextPage": False, "endCursor": None},
    "nodes": [
        {"isResolved": True, "isOutdated": False, "path": "a.py", "line": 1, "originalLine": 1,
         "first": {"nodes": [{"author": {"login": "copilot"}}]},
         "last": {"nodes": [{"author": {"login": "dev"}, "body": "Fixed.", "url": "u1"}]}},
        {"isResolved": False, "isOutdated": True, "path": "b.py", "line": None, "originalLine": 12,
         "first": {"nodes": [{"author": {"login": "copilot"}}]},
         "last": {"nodes": [{"author": {"login": "copilot"}, "body": "This breaks.\nDetails.", "url": "u2"}]}},
    ]}}}}}  # fmt: skip


class TestThreads:
    def test_open_threads_only(self, project: Path, gh: FakeGh):
        gh.set("graphql", THREADS)
        result = CliRunner().invoke(app, ["threads", "5", "--path", str(project)])
        assert result.exit_code == 0, result.output
        assert "#5: 1 open review thread" in result.output and "b.py:12 (outdated)" in result.output
        assert "This breaks." in result.output and "a.py" not in result.output and "Details." not in result.output
        data = json.loads(CliRunner().invoke(app, ["threads", "5", "--path", str(project), "--json"]).output)
        assert data["open"] == 1 and data["threads"][0]["started_by"] == "copilot"
        assert set(gh.methods()) <= {"GET"}  # only the GraphQL query besides: never a reply or a resolve
        assert all("resolveReviewThread" not in " ".join(c["args"]) for c in gh.calls())

    def test_without_github_it_is_wrong_usage(self, project: Path):
        assert CliRunner().invoke(app, ["threads", "5", "--path", str(project)]).exit_code == 2

    def test_a_missing_pull_request_is_an_error(self, project: Path, gh: FakeGh):
        gh.set("graphql", {"data": {"repository": {"pullRequest": None}}})
        result = CliRunner().invoke(app, ["threads", "99", "--path", str(project)])
        assert result.exit_code == 1 and "no pull request #99" in result.output


class TestCopilotReviewWait:
    def test_the_job_waits_inside_ci_ok_when_github_turns_review_on(self, project: Path):
        apply(make_plan(project, only=["ci", "github"], today=TODAY, hosts=[]), project)
        text = (project / WORKFLOW).read_text()
        assert "copilot-review" in workflow_jobs(text)["ci-ok"] and "copilot-pull-request-reviewer[bot]" in text
        assert "pull-requests: read" in text and "sleep 30" in text

    def test_no_wait_without_copilot_review(self, project: Path):
        apply(make_plan(project, only=["ci", "github"], today=TODAY, hosts=[], copilot_review=False), project)
        assert "copilot-review" not in workflow_jobs((project / WORKFLOW).read_text())

    def test_applying_github_later_rewrites_an_unchanged_workflow(self, project: Path):
        apply(make_plan(project, only=["ci"], today=TODAY, hosts=[]), project)
        assert "copilot-review" not in workflow_jobs((project / WORKFLOW).read_text())
        plan = make_plan(project, only=["ci", "github"], today=TODAY, hosts=[])
        assert action(plan, WORKFLOW).verb == "rewrite"
        apply(plan, project)
        assert "copilot-review" in workflow_jobs((project / WORKFLOW).read_text())["ci-ok"]

    @pytest.mark.skipif(not shutil.which("jq"), reason="ci-ok's step runs jq")
    @pytest.mark.parametrize(("event", "result", "passes"), [
        ("pull_request", "success", True), ("pull_request", "skipped", False), ("pull_request", "failure", False),
        ("push", "skipped", True), ("push", "success", False),
    ])  # fmt: skip
    def test_ci_ok_expects_the_wait_on_pull_requests_only(self, project: Path, event, result, passes):
        apply(make_plan(project, only=["ci", "github"], today=TODAY, hosts=[]), project)
        text = (project / WORKFLOW).read_text()
        script = "\n".join(
            line[10:] for line in text.split("\n  ci-ok:\n", 1)[1].split("        run: |\n", 1)[1].splitlines()
        )
        needs = workflow_jobs(text)["ci-ok"]
        expected = {"test-macos": "success" if event == "push" else "skipped",
                    "governance": "success" if event == "pull_request" else "skipped",
                    "dependency-review": "success" if event == "pull_request" else "skipped"}  # fmt: skip
        results = {job: expected.get(job, "success") for job in needs} | {"copilot-review": result}
        env = {**os.environ, "EVENT": event, "PRIVATE": "false",
               "NEEDS": json.dumps({j: {"result": r} for j, r in results.items()})}  # fmt: skip
        done = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=False)
        assert (done.returncode == 0) is passes, done.stdout


class TestGeminiReviewRound1:
    """Phase 5 review findings (CODE_REVIEW.md), each reproduced before the fix."""

    def test_p5_f01_applying_github_alone_brings_ci_along(self, project: Path):
        apply(make_plan(project, only=["ci"], today=TODAY, hosts=[]), project)
        plan = plan_for(project, code_owner="@dev")
        assert action(plan, WORKFLOW).verb == "rewrite"
        apply(plan, project)
        assert "copilot-review" in workflow_jobs((project / WORKFLOW).read_text())["ci-ok"]
        state = State.load(project)
        assert state.values["ci_copilot_review"] == "true" and state.github["copilot_review"] is True
        assert not make_plan(project, only=["ci"], today=TODAY, hosts=[]).changes  # recorded inputs rebuild it
        finding = {f.item: f for f in run_check(project, only=["ci"]).findings}["ci.copilot-review"]
        assert finding.status == OK

    def test_p5_f01_check_reports_a_workflow_that_doesnt_wait(self, project: Path):
        apply(make_plan(project, only=["ci"], today=TODAY, hosts=[]), project)
        (project / WORKFLOW).write_text((project / WORKFLOW).read_text() + "# ours\n")  # changed: not rewritten
        apply(plan_for(project, code_owner="@dev"), project)
        finding = {f.item: f for f in run_check(project, only=["ci"]).findings}["ci.copilot-review"]
        assert finding.status == MISSING and "doesn't wait for the Copilot review" in finding.message

    def test_p5_f02_the_committed_files_are_what_gets_applied(self, project: Path, gh: FakeGh):
        theirs = github.BUILDERS["github/repo-settings@1"](github.Settings("solo", None))
        theirs["allow_merge_commit"] = True  # the person's own choice, edited into the file
        make(project, {".github/swerepo/repo-settings.json": json.dumps(theirs)})
        plan = plan_for(project, mode="team")  # the build for team would differ: the file wins
        assert action(plan, ".github/swerepo/repo-settings.json").verb == KEEP
        assert plan.github_apply["settings"]["allow_merge_commit"] is True
        make(project, {".github/swerepo/repo-settings.json": "[not an object]"})
        plan = plan_for(project)
        assert "settings" not in plan.github_apply
        assert any("isn't a JSON object: nothing applied" in n for n in notes(plan))

    def test_p5_f02_applied_turns_true_when_github_already_matches(self, project: Path, gh: FakeGh):
        apply(plan_for(project, code_owner="@dev"), project)  # GitHub reachable but different: applied = false
        assert State.load(project).github["applied"] is False
        settings = github.Settings("solo", "@dev")
        gh.set(f"GET repos/{SLUG}/rulesets", [{"id": 7, "name": "swerepo"}])
        gh.set(f"GET repos/{SLUG}/rulesets/7", {"id": 7, **github.BUILDERS["github/ruleset@1"](settings)})
        gh.set(f"GET repos/{SLUG}", {"owner": {"login": "dev", "type": "User"},
                                     **github.BUILDERS["github/repo-settings@1"](settings)})  # fmt: skip
        plan = plan_for(project)
        assert not plan.github_apply
        apply(plan, project)
        assert State.load(project).github["applied"] is True

    def test_p5_f02_a_missing_settings_file_is_reported_once(self, project: Path, gh: FakeGh):
        apply(plan_for(project, code_owner="@dev"), project)
        (project / ".github/swerepo/repo-settings.json").unlink()
        messages = [f.message for f in run_check(project, only=["github"], read_github=True).findings]
        assert not [m for m in messages if "isn't readable JSON" in m]
        assert any(m.startswith("merge settings as code missing") for m in messages)

    def test_p5_f03_no_code_owner_is_a_warning_not_a_failure(self, project: Path):
        apply(plan_for(project), project)
        finding = {f.item: f for f in run_check(project, only=["github"]).findings}["github.codeowners"]
        assert finding.status == MISSING and not finding.blocking and "--code-owner" in finding.message

    def test_p5_f04_questions_use_the_detected_defaults_and_none_means_none(self, project: Path, gh: FakeGh,
                                                                            monkeypatch):  # fmt: skip
        from swerepo import cli

        monkeypatch.setattr(cli, "_interactive", lambda: True)
        plan = plan_for(project)
        assert plan.github_ask == {"mode": "solo", "code_owner": "@dev"}  # the user who owns it
        result = CliRunner().invoke(app, ["init", "--path", str(project), "--only", "github"], input="\nnone\nn\n")
        assert result.exit_code == 0, result.output
        assert "Code owner" in result.output and "[@dev]" in result.output
        plan = plan_for(project, code_owner="none")
        assert not any(a.path == ".github/CODEOWNERS" for a in plan.actions)
        assert any("no code owner, as you chose" in n for n in notes(plan))
        apply(plan, project)
        assert State.load(project).values["code_owner"] == "none"
        assert not any(a.path == ".github/CODEOWNERS" for a in plan_for(project).actions)  # never proposed again
        gh.set(f"GET repos/{SLUG}", {"owner": {"login": "acme", "type": "Organization"}})
        other = project.parent / "org"
        other.mkdir()
        git_init(other)
        make(other, {"pyproject.toml": PYPROJECT})
        git(other, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
        assert plan_for(other).github_ask["mode"] == "team"  # an organisation's default, not a fixed "solo"
        assert plan_for(other, mode="solo").github_ask == {"code_owner": "none"}  # --mode still asks the owner

    def test_p5_f05_drafts_dont_wait_and_ready_for_review_runs_again(self, project: Path):
        apply(make_plan(project, only=["ci", "github"], today=TODAY, hosts=[]), project)
        text = (project / WORKFLOW).read_text()
        assert "types: [opened, synchronize, reopened, ready_for_review]" in text
        job = text.split("  copilot-review:\n", 1)[1]
        assert "DRAFT: ${{ github.event.pull_request.draft }}" in job
        assert job.index('if [ "${DRAFT:-false}" = "true" ]') < job.index("for attempt in")  # before any wait

    @pytest.mark.parametrize(
        ("url", "slug"),
        [
            ("https://github.com/acme/app.git", "acme/app"),
            ("git@github.com:acme/app.git", "acme/app"),
            ("ssh://git@github.com/acme/app", "acme/app"),
            ("https://evilgithub.com/victim/repo.git", None),
            ("https://github.com.evil.test/victim/repo", None),
            ("git@evilgithub.com:victim/repo.git", None),
        ],
    )
    def test_p5_f06_only_github_itself_counts(self, project: Path, url: str, slug: str | None):
        from swerepo.init import has_github_remote

        git(project, "remote", "add", "origin", url)
        assert github.repository(project) == slug and has_github_remote(project) is (slug is not None)

    def test_p5_f06_private_repositories_dont_need_the_dependency_graph(self, project: Path, gh: FakeGh):
        apply(make_plan(project, only=["ci"], today=TODAY, hosts=[]), project)
        del gh.responses[f"GET repos/{SLUG}/dependency-graph/sbom"]
        gh.responses[f"GET repos/{SLUG}"]["private"] = True
        gh.save()
        finding = {f.item: f for f in run_check(project, only=["ci"], read_github=True).findings}
        assert finding["ci.dependency-graph"].status == OK and "not needed" in finding["ci.dependency-graph"].message

    def test_p5_f06_only_a_404_means_off(self, project: Path, gh: FakeGh):
        hub = github.GitHub.connect(project)
        assert hub is not None and hub.dependency_graph() is True
        del gh.responses[f"GET repos/{SLUG}/dependency-graph/sbom"]  # the fake answers 404 "Not Found"
        gh.save()
        assert hub.dependency_graph() is False
        gh.set(f"GET repos/{SLUG}/dependency-graph/sbom", None)
        (gh.folder / "gh").write_text('#!/bin/sh\necho \'{"message": "Bad Gateway"}\'\nexit 1\n')
        with pytest.raises(github.GitHubError) as raised:  # a 502 isn't "off": it's raised, so check says "?"
            hub.dependency_graph()
        assert not raised.value.not_found

    def test_p5_f07_threads_reports_graphqls_own_message(self, project: Path, gh: FakeGh):
        gh.set("graphql", {"errors": [{"message": "Could not resolve to a PullRequest with the number of 99."}]})
        result = CliRunner().invoke(app, ["threads", "99", "--path", str(project)])
        assert result.exit_code == 1 and "Could not resolve to a PullRequest" in result.output
        assert CliRunner().invoke(app, ["threads", "0", "--path", str(project)]).exit_code == 2

    def test_p5_f08_unicode_line_breaks_above_the_block_dont_shift_it(self, project: Path):
        make(project, {".github/CODEOWNERS": "# note here\n\n# swerepo:begin\n/.github/ @dev\n# swerepo:end\n"})
        finding = {f.item: f for f in run_check(project, only=["github"]).findings}["github.codeowners"]
        assert finding.status == OK

    def test_p5_f09_rulesets_are_listed_100_at_a_time(self, project: Path, gh: FakeGh):
        plan_for(project)
        listed = [c["args"] for c in gh.calls() if any("/rulesets?" in a for a in c["args"])]
        assert listed and all("per_page=100" in " ".join(args) for args in listed)

    def test_init_says_which_extra_rules_an_update_removes(self):
        assert github.ruleset_changes(["merge_queue added", "pull_request.x"]) == [
            "removes merge_queue", "pull_request.x"]  # fmt: skip


class TestGeminiReviewRound2:
    """Phase 5 review, round 2 (CODE_REVIEW.md), each reproduced before the fix."""

    def _set_up(self, project: Path) -> None:
        apply(make_plan(project, only=["ci", "github"], today=TODAY, hosts=[], code_owner="@dev"), project)

    def test_p5_f10_turning_copilot_review_off_rewrites_the_ruleset_and_the_workflow(self, project: Path):
        self._set_up(project)
        plan = plan_for(project, copilot_review=False)
        assert action(plan, ".github/swerepo/ruleset.json").verb == "rewrite"
        apply(plan, project)
        ruleset = json.loads((project / ".github/swerepo/ruleset.json").read_text())
        assert not github.has_copilot_review(ruleset)
        assert "copilot-review" not in workflow_jobs((project / WORKFLOW).read_text())
        assert State.load(project).github["copilot_review"] is False
        assert {f.item: f for f in run_check(project, only=["ci"]).findings}["ci.copilot-review"].status == OK

    def test_p5_f10_a_new_mode_goes_into_the_ruleset_or_isnt_recorded(self, project: Path):
        self._set_up(project)
        apply(plan_for(project, mode="team"), project)
        ruleset = json.loads((project / ".github/swerepo/ruleset.json").read_text())
        pull = next(r["parameters"] for r in ruleset["rules"] if r["type"] == "pull_request")
        assert pull["required_approving_review_count"] == 1 and State.load(project).mode == "team"
        ruleset_file = project / ".github/swerepo/ruleset.json"
        ruleset_file.write_text(
            ruleset_file.read_text().replace('"enforcement": "active"', '"enforcement": "evaluate"')
        )
        plan = plan_for(project, mode="solo")  # the person changed ruleset.json: it isn't rewritten
        assert action(plan, ".github/swerepo/ruleset.json").verb == "changed"
        assert "isn't in it: edit it yourself" in action(plan, ".github/swerepo/ruleset.json").note
        apply(plan, project)
        assert State.load(project).mode == "team"  # not recorded: the ruleset still says team

    def test_p5_f10_a_committed_ruleset_without_copilot_review_gets_no_wait(self, project: Path):
        mine = github.BUILDERS["github/ruleset@1"](github.Settings("solo", None, copilot_review=False))
        make(project, {".github/swerepo/ruleset.json": github.as_text(mine)})
        apply(make_plan(project, only=["ci", "github"], today=TODAY, hosts=[]), project)
        assert "copilot-review" not in workflow_jobs((project / WORKFLOW).read_text())  # the ruleset decides
        assert State.load(project).github["copilot_review"] is False
        assert {f.item: f for f in run_check(project, only=["ci"]).findings}["ci.copilot-review"].status == OK

    def test_p5_f10_check_reads_the_committed_ruleset(self, project: Path):
        self._set_up(project)
        mine = github.BUILDERS["github/ruleset@1"](github.Settings("solo", "@dev", copilot_review=False))
        make(project, {".github/swerepo/ruleset.json": github.as_text(mine)})  # edited by hand: no Copilot review
        finding = {f.item: f for f in run_check(project, only=["ci"]).findings}["ci.copilot-review"]
        assert finding.status == MISSING and "doesn't request" in finding.message

    def test_p5_f11_swereposs_own_pr_template_is_compared_not_called_yours(self, project: Path):
        apply(plan_for(project), project)
        assert action(plan_for(project), ".github/pull_request_template.md").verb == CURRENT

    def test_p5_f12_no_rewrite_when_the_wait_doesnt_change(self, project: Path):
        apply(make_plan(project, only=["ci"], today=TODAY, hosts=[]), project)
        plan = plan_for(project, copilot_review=False)  # no wait before, none now: nothing to rewrite
        assert action(plan, WORKFLOW).verb == CURRENT
        self._set_up(project)
        assert action(make_plan(project, today=TODAY, hosts=[]), WORKFLOW).verb == CURRENT  # a plain init

    def test_p5_f12_no_ci_is_respected(self, project: Path):
        apply(make_plan(project, only=["ci"], today=TODAY, hosts=[]), project)
        plan = make_plan(project, skip=["ci"], today=TODAY, hosts=[])
        assert not any(a.component == "ci" for a in plan.actions)

    @pytest.mark.parametrize("answer", [None, [], "text"])
    def test_p5_f13_a_non_object_answer_is_an_error_not_a_crash(self, project: Path, gh: FakeGh, answer):
        gh.set("graphql", answer)
        result = CliRunner().invoke(app, ["threads", "1", "--path", str(project)])
        assert result.exit_code == 1 and "no pull request #1" in result.output

    def test_p5_f12_a_version_1_workflow_isnt_rewritten_unless_the_wait_changes(self, project: Path, tmp_path: Path):
        from swerepo.render import TemplateStore

        bundled = Path(str(TemplateStore().root))
        old = tmp_path / "templates-v1"  # the templates as Phase 4 shipped them: no version 2
        for template in bundled.rglob("*"):
            if template.is_file() and template.name[0].isdigit() and not template.name.startswith("2"):
                make(old, {template.relative_to(bundled).as_posix(): template.read_text()})
        apply(make_plan(project, only=["ci"], today=TODAY, hosts=[], store=TemplateStore(old)), project)
        assert State.load(project).files()[WORKFLOW].template == "ci/workflow@1"
        plan = plan_for(project, copilot_review=False)  # no wait before or after: update's job, not init's
        assert action(plan, WORKFLOW).verb == "outdated"
        plan = plan_for(project)  # Copilot review on: the wait is what changes, so the unchanged file is rewritten
        assert action(plan, WORKFLOW).verb == "rewrite"

    def test_p5_f10_a_ruleset_without_the_github_component_isnt_checked_against_ci(self, project: Path):
        apply(make_plan(project, only=["ci"], today=TODAY, hosts=[]), project)
        ruleset = github.BUILDERS["github/ruleset@1"](github.Settings("solo", None))  # requests Copilot's review
        make(project, {".github/swerepo/ruleset.json": github.as_text(ruleset)})  # the person's own, by hand
        assert "ci.copilot-review" not in {f.item for f in run_check(project, only=["ci"]).findings}


class TestGeminiReviewRound3:
    """Phase 5 review, round 3 (CODE_REVIEW.md), each reproduced before the fix."""

    def test_p5_f10_a_new_code_owner_rewrites_an_unchanged_codeowners_block(self, project: Path):
        make(project, {".github/CODEOWNERS": "/src/ @team\n"})
        apply(plan_for(project, code_owner="@dev"), project)
        plan = plan_for(project, mode="team", code_owner="@acme/devs")
        assert action(plan, ".github/CODEOWNERS").verb == "rewrite"
        apply(plan, project)
        text = (project / ".github/CODEOWNERS").read_text()
        assert text.startswith("/src/ @team\n\n# swerepo:begin\n")  # the person's lines stay byte for byte
        assert "@acme/devs" in text and "@dev\n" not in text
        assert State.load(project).values["code_owner"] == "@acme/devs"
        assert not plan_for(project).changes  # recorded block matches: nothing to do

    def test_p5_f10_a_changed_codeowners_block_keeps_the_recorded_owner(self, project: Path):
        apply(plan_for(project, code_owner="@dev"), project)
        codeowners = project / ".github/CODEOWNERS"
        codeowners.write_text(codeowners.read_text().replace("/docs/adr/", "/decisions/"))  # edited inside the block
        plan = plan_for(project, code_owner="@acme/devs")
        found = action(plan, ".github/CODEOWNERS")
        assert found.verb == "changed" and "the code owner you gave isn't in it" in found.note
        apply(plan, project)
        assert State.load(project).values["code_owner"] == "@dev" and "@acme/devs" not in codeowners.read_text()

    def test_p5_f10_a_block_edited_after_the_plan_stops_the_rewrite(self, project: Path):
        from swerepo.init import InitError

        apply(plan_for(project, code_owner="@dev"), project)
        plan = plan_for(project, code_owner="@acme/devs")
        codeowners = project / ".github/CODEOWNERS"
        codeowners.write_text(codeowners.read_text().replace("@dev", "@someone"))
        with pytest.raises(InitError, match="changed since the plan"):
            apply(plan, project)
        assert "@someone" in codeowners.read_text() and "@acme/devs" not in codeowners.read_text()

    def test_p5_f14_a_kept_rulesets_mode_is_shown_and_recorded(self, project: Path, gh: FakeGh):
        solo = github.BUILDERS["github/ruleset@1"](github.Settings("solo", None))
        make(project, {".github/swerepo/ruleset.json": github.as_text(solo)})  # hand-written, never recorded
        gh.set(f"GET repos/{SLUG}", {"owner": {"login": "acme", "type": "Organization"}})  # team by default
        plan = plan_for(project)
        assert next(n for n in notes(plan) if n.startswith("mode:")).startswith("mode: solo")
        assert plan.github_ask["mode"] == "solo"  # the question's default too
        apply(plan, project)
        assert State.load(project).mode == "solo"
        assert github.ruleset_mode(github.BUILDERS["github/ruleset@1"](github.Settings("team", "@x"))) == "team"
        assert github.ruleset_mode({"rules": [{"type": "deletion"}]}) is None


class TestCopilotReviewPR10:
    """Copilot's review of PR #10, each reproduced before the fix."""

    def _edit(self, project: Path, path: str, **changes) -> None:
        file = project / path
        file.write_text(json.dumps({**json.loads(file.read_text()), **changes}))

    def test_a_renamed_ruleset_is_never_sent(self, project: Path, gh: FakeGh):
        apply(plan_for(project, code_owner="@dev"), project)
        self._edit(project, github.RULESET_FILE, name="other")
        plan = plan_for(project)
        assert "ruleset" not in plan.github_apply and "settings" in plan.github_apply
        assert any('ruleset.json: its name is "other", not "swerepo": nothing applied' in n for n in notes(plan))
        apply(plan, project)
        apply_github(plan, project, ["ruleset", "settings"])
        assert State.load(project).github["applied"] is False  # the ruleset still isn't on GitHub
        sent = [c["args"][2:4] for c in gh.calls() if c["args"][2:3] in (["PUT"], ["POST"])]
        assert sent == []
        findings = run_check(project, only=["github"], read_github=True).findings
        assert any(f.status == MISSING and "won't apply it" in f.message and "other" in f.message for f in findings)
        with pytest.raises(github.GitHubError, match="not sent"):
            github.GitHub(SLUG).apply_ruleset({"name": "other", "rules": []})
        assert [c for c in gh.calls() if c["args"][2:3] in (["PUT"], ["POST"])] == []

    def test_settings_beyond_merging_are_never_sent(self, project: Path, gh: FakeGh):
        apply(plan_for(project, code_owner="@dev"), project)
        self._edit(project, github.SETTINGS_FILE, private=False, visibility="public")
        plan = plan_for(project)
        assert "settings" not in plan.github_apply
        expected = f"{github.SETTINGS_FILE}: it holds fields that aren't merge settings (private, visibility)"
        assert any(n.startswith(expected) and n.endswith("nothing applied from it") for n in notes(plan))
        findings = run_check(project, only=["github"], read_github=True).findings
        assert any(f.status == MISSING and "private, visibility" in f.message for f in findings)
        with pytest.raises(github.GitHubError, match="not sent"):
            github.GitHub(SLUG).apply_settings({"allow_squash_merge": True, "private": False})
        assert not [c for c in gh.calls() if c["args"][2:3] == ["PATCH"]]
        # every field the builders write is a merge setting
        for mode in ("solo", "team"):
            built = github.BUILDERS["github/repo-settings@1"](
                github.Settings(mode, "@dev", merge_methods=("squash", "merge"))
            )
            assert github.not_applicable("repo-settings", built) is None

    def test_on_github_without_gh_the_next_steps_keep_the_pull_request(self, project: Path, gh: FakeGh):
        gh.set("logged_in", False)
        command = ["init", "--path", str(project), "--only", "github", "--yes", "--code-owner", "@dev"]
        result = CliRunner().invoke(app, command)
        assert result.exit_code == 0, result.output
        assert "gh isn't installed or logged in" in result.output
        assert "commit them on a new branch, open a pull request" in result.output and "gh auth login" in result.output
        assert "default branch" not in result.output and "gh repo create" not in result.output

    def test_without_a_github_repository_the_next_steps_create_it(self, project: Path):
        command = ["init", "--path", str(project), "--only", "github", "--yes", "--code-owner", "@dev"]
        result = CliRunner().invoke(app, command)
        assert result.exit_code == 0, result.output
        assert "no GitHub repository yet" in result.output and "gh repo create --source . --push" in result.output

    def test_applied_is_kept_when_github_cant_be_read(self, project: Path, gh: FakeGh):
        settings = github.Settings("solo", "@dev")
        gh.set(f"GET repos/{SLUG}/rulesets", [{"id": 7, "name": "swerepo"}])
        gh.set(f"GET repos/{SLUG}/rulesets/7", {"id": 7, **github.BUILDERS["github/ruleset@1"](settings)})
        gh.set(f"GET repos/{SLUG}", {"owner": {"login": "dev", "type": "User"},
                                     **github.BUILDERS["github/repo-settings@1"](settings)})  # fmt: skip
        apply(plan_for(project, code_owner="@dev"), project)
        assert State.load(project).github["applied"] is True
        state = State.load(project)
        state.set_github("applied", False)
        state.save(project)
        del gh.responses[f"GET repos/{SLUG}/rulesets"]  # listing rulesets is refused (a 403, say)
        gh.save()
        plan = plan_for(project)
        assert plan.github_compared is None and not plan.github_apply
        apply(plan, project)
        assert State.load(project).github["applied"] is False  # kept, not turned true by an empty plan

    def test_applied_needs_both_files_compared(self, project: Path, gh: FakeGh):
        settings = github.Settings("solo", "@dev")
        gh.set(f"GET repos/{SLUG}", {"owner": {"login": "dev", "type": "User"},
                                     **github.BUILDERS["github/repo-settings@1"](settings)})  # fmt: skip
        make(project, {github.RULESET_FILE: "[not an object]"})
        plan = plan_for(project, code_owner="@dev")
        assert plan.github_compared is False and not plan.github_apply  # the settings already match
        apply(plan, project)
        assert State.load(project).github["applied"] is False
        # and apply_github doesn't record it either, even when what it was asked to apply went through
        plan.github_apply["settings"] = github.BUILDERS["github/repo-settings@1"](settings)
        apply_github(plan, project, ["ruleset", "settings"])
        assert State.load(project).github["applied"] is False


class TestDogfoodGithub:
    """Found by applying github to SWERepo's own repository: the plan asked to edit files that already held the
    choices given."""

    def _kept(self, project: Path, settings: github.Settings, owner_line: str) -> None:
        make(project, {
            ".github/swerepo/ruleset.json": github.as_text(github.BUILDERS["github/ruleset@1"](settings)),
            ".github/CODEOWNERS": f"# owners\n# swerepo:begin (by hand)\n/.github/   {owner_line}\n"
                                  f"/AGENTS.md  {owner_line}\n# swerepo:end\n",
        })  # fmt: skip

    def test_no_edit_asked_when_the_kept_files_hold_the_choices(self, project: Path):
        self._kept(project, github.Settings("solo", "@dev"), "@dev")
        plan = plan_for(project, mode="solo", code_owner="@dev")
        assert action(plan, ".github/swerepo/ruleset.json").note == "yours: SWERepo didn't write it"
        assert "isn't in it" not in action(plan, ".github/CODEOWNERS").note

    def test_the_edit_names_only_what_the_kept_files_lack(self, project: Path):
        self._kept(project, github.Settings("solo", "@dev"), "@dev")
        plan = plan_for(project, mode="team", code_owner="@other", copilot_review=True)
        note = action(plan, ".github/swerepo/ruleset.json").note
        assert "what you gave (--mode, --code-owner) isn't in it" in note  # Copilot review: already there
        assert "the code owner you gave isn't in it" in action(plan, ".github/CODEOWNERS").note
        plan = plan_for(project, mode="solo", copilot_review=False)
        assert "what you gave (--no-copilot-review) isn't in it" in action(plan, ".github/swerepo/ruleset.json").note
        make(project, {".github/swerepo/ruleset.json": "[not an object]"})
        plan = plan_for(project, mode="solo")
        assert "what you gave (--mode) isn't in it" in action(plan, ".github/swerepo/ruleset.json").note


class TestCopilotReviewPR11:
    """Copilot's review of PR #11, each reproduced before the fix."""

    def _ruleset(self, project: Path, ruleset) -> None:
        text = ruleset if isinstance(ruleset, str) else github.as_text(ruleset)
        make(project, {".github/swerepo/ruleset.json": text})  # hand-written, never recorded

    def test_links_out_of_the_repository_are_kept_not_read(self, project: Path, tmp_path: Path):
        (project / ".github/swerepo").mkdir(parents=True)
        (project / ".github/CODEOWNERS").symlink_to(tmp_path / "missing-codeowners")
        (project / ".github/swerepo/ruleset.json").symlink_to(tmp_path / "missing-ruleset.json")
        result = CliRunner().invoke(app, ["init", "--path", str(project), "--only", "github", "--dry-run",
                                          "--mode", "solo", "--code-owner", "@dev"])  # fmt: skip
        assert result.exit_code == 0, result.output
        assert result.output.count("a link out of the repository") == 2 and "isn't in it" not in result.output

    def test_the_fallback_keeps_the_flag_as_given(self, project: Path):
        self._ruleset(project, "[not an object]")
        note = action(plan_for(project, copilot_review=False), github.RULESET_FILE).note
        assert "what you gave (--no-copilot-review) isn't in it" in note

    def test_the_kept_rulesets_mode_decides_when_none_is_given(self, project: Path):
        team = github.BUILDERS["github/ruleset@1"](github.Settings("team", None))  # no code-owner review
        self._ruleset(project, team)
        note = action(plan_for(project, code_owner="@dev"), github.RULESET_FILE).note  # a user's repo: solo default
        assert "what you gave (--code-owner) isn't in it" in note

    def test_no_code_owner_is_compared_too(self, project: Path):
        self._ruleset(project, github.BUILDERS["github/ruleset@1"](github.Settings("team", None)))
        plan = plan_for(project, mode="team", code_owner="none")
        assert "isn't in it" not in action(plan, github.RULESET_FILE).note  # already without code-owner review
        self._ruleset(project, github.BUILDERS["github/ruleset@1"](github.Settings("team", "@dev")))
        plan = plan_for(project, mode="team", code_owner="none")
        assert "what you gave (--code-owner) isn't in it" in action(plan, github.RULESET_FILE).note
        plan = plan_for(project, mode="team", code_owner="@dev")
        assert "isn't in it" not in action(plan, github.RULESET_FILE).note
