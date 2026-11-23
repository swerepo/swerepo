"""`swerepo check` on fixture repositories (spec §15, ADR-20261120-fc5a)."""

import json
from pathlib import Path

import pytest
from click import unstyle
from repo_helpers import commit, git, git_init, make, snapshot
from typer.testing import CliRunner

from swerepo.check import CHANGED, MISSING, NOT_CHOSEN, OK, OUTDATED, UNKNOWN, Finding, Report, UsageError, run_check
from swerepo.cli import app
from swerepo.fingerprint import fingerprint
from swerepo.render import TemplateStore
from swerepo.state import FILE_NAME, Record, State

ADR = "ADR-20260101-abcd"
# A repository that meets every standard-1 item this version checks.
STANDARD_FILES = {
    "README.md": "# demo\n",
    "docs/adr/README.md": (
        f"# ADRs\n<!-- swerepo:adr-index:begin -->\n| [{ADR}]({ADR}-x.md) |\n<!-- swerepo:adr-index:end -->\n"
    ),
    "docs/adr/TEMPLATE.md": "# Template\n",
    f"docs/adr/{ADR}-x.md": "# A decision\n",
    "docs/PROGRESS.md": "# Progress\n",
    "docs/progress/20260101-start.md": "# Start\n",
    "CHANGELOG.md": "# Changelog\n\n## [Unreleased]\n",
    "CONTRIBUTING.md": "# Contributing\n",
    "LICENSE": "Apache-2.0\n",
    "AGENTS.md": "# Rules\n<!-- swerepo:begin -->\nrules\n<!-- swerepo:end -->\n",
    "CLAUDE.md": "@AGENTS.md\n",
    ".claude/settings.json": "{}\n",  # Claude Code is in use even when CLAUDE.md is missing
    "docs/agents/prepare-pr.md": "x\n",
    "docs/agents/address-review.md": "x\n",
    "docs/agents/record-adr.md": "x\n",
    ".github/workflows/swerepo-ci.yml": (
        'jobs:\n  test:\n    strategy:\n      matrix:\n        python: ["3.11", "3.12", "3.13", "3.14"]\n'
        "    steps:\n      - run: pytest\n      - run: seamspec verify --all\n"
        "  ci-ok:\n    needs: [test]\n"
    ),
    "pyproject.toml": (
        '[project]\nname = "demo"\nrequires-python = ">=3.11"\n\n[tool.ruff]\nextend-exclude = [".seamspec"]\n'
    ),
    "SECURITY.md": "# Security\n",
    ".github/workflows/swerepo-privacy.yml": "jobs: {}\n",
    ".gitignore": "# swerepo:begin\n.env\n# swerepo:end\n",
    ".github/swerepo/ruleset.json": "{}\n",
    ".github/swerepo/repo-settings.json": "{}\n",
    ".github/copilot-instructions.md": "x\n",
    ".github/dependabot.yml": "version: 2\n",
    ".github/pull_request_template.md": "x\n",
    ".github/ISSUE_TEMPLATE/bug.md": "x\n",
    ".github/CODEOWNERS": "/src/ @team\n# swerepo:begin\n/.github/ @owner\n# swerepo:end\n",
    ".seamspec/config.toml": 'mode = "enforced"\n',
    "docs/EARNED_SPEC.md": "# Spec\n",
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git_init(tmp_path)
    make(tmp_path, STANDARD_FILES)
    commit(tmp_path, "start")
    return tmp_path


def by_item(report):
    return {f.item: f for f in report.findings}


def test_a_repository_that_meets_the_standard(repo: Path):
    report = run_check(repo)
    assert report.exit_code == 0
    assert report.count(MISSING) == 0
    assert {f.status for f in report.findings} <= {OK, UNKNOWN, NOT_CHOSEN}
    later = [f.message for f in report.findings if f.status == UNKNOWN]
    assert later and all("checked from Phase" in m for m in later)  # honest about what isn't checked yet
    assert by_item(report)["openspec.chosen"].status == NOT_CHOSEN
    assert report.next_step() is None


def test_an_empty_folder(tmp_path: Path):
    report = run_check(tmp_path)
    assert report.exit_code == 1
    assert by_item(report)["repository.git"].status == UNKNOWN
    assert report.next_step() == "swerepo init --only docs,agents"
    assert by_item(report)["docs.license"].status == NOT_CHOSEN  # a license is asked for, never assumed


@pytest.mark.parametrize(
    ("remove", "item"),
    [
        ("docs/PROGRESS.md", "docs.progress"),
        ("docs/progress/20260101-start.md", "docs.progress-entries"),
        ("CONTRIBUTING.md", "docs.contributing"),
        ("docs/adr/TEMPLATE.md", "docs.adr-template.md"),
        ("CLAUDE.md", "agents.claude"),
        ("docs/agents/record-adr.md", "agents.runbooks"),
        (".github/workflows/swerepo-ci.yml", "ci.workflow"),
        ("SECURITY.md", "security.policy"),
        (".github/workflows/swerepo-privacy.yml", "security.workflow"),
        (".github/dependabot.yml", "github.dependabot"),
        (".github/pull_request_template.md", "github.pr-template"),
        (".github/ISSUE_TEMPLATE/bug.md", "github.issue-templates"),
        (".github/CODEOWNERS", "github.codeowners"),
        ("docs/EARNED_SPEC.md", "seamspec.earned-spec"),
    ],
)
def test_each_missing_file_is_reported(repo: Path, remove: str, item: str):
    (repo / remove).unlink()
    report = run_check(repo)
    finding = by_item(report)[item]
    assert finding.status == MISSING and finding.blocking
    assert report.exit_code == 1


@pytest.mark.parametrize(
    ("path", "text", "item", "message"),
    [
        ("CHANGELOG.md", "# Changelog\n", "docs.changelog", "has no [Unreleased] section"),
        ("AGENTS.md", "# Rules\n", "agents.block", "AGENTS.md has no SWERepo block"),
        ("AGENTS.md", "<!-- swerepo:begin -->\n", "agents.block", "markers are broken"),
        ("CLAUDE.md", "# Notes\n", "agents.claude", "doesn't import AGENTS.md"),
        (".github/workflows/swerepo-ci.yml", "jobs: {}\n", "ci.ci-ok", "has no ci-ok job"),
        (".gitignore", ".env\n", "security.gitignore", ".gitignore has no SWERepo block"),
        (".github/CODEOWNERS", "/src/ @team\n", "github.codeowners", "has no SWERepo block"),
        (".seamspec/config.toml", 'mode = "advisory"\n', "seamspec.mode", "mode: advisory"),
        ("pyproject.toml", '[project]\nname = "demo"\n\n[tool.ruff]\nline-length = 100\n', "ci.seamspec-excluded",
         'add ".seamspec" to extend-exclude'),
    ],
)  # fmt: skip
def test_each_wrong_file_is_reported(repo: Path, path: str, text: str, item: str, message: str):
    make(repo, {path: text})
    finding = by_item(run_check(repo))[item]
    assert finding.status == MISSING and message in finding.message


def test_the_adr_index_must_match_the_adr_files(repo: Path):
    make(repo, {"docs/adr/ADR-20260202-beef-y.md": "# Another\n"})
    index = STANDARD_FILES["docs/adr/README.md"].replace(ADR, "ADR-20260303-dead")
    make(repo, {"docs/adr/README.md": index})
    finding = by_item(run_check(repo))["docs.adr-index"]
    assert finding.status == MISSING
    assert "not listed: ADR-20260101-abcd, ADR-20260202-beef" in finding.message
    assert "listed without a file: ADR-20260303-dead" in finding.message


def test_an_adopted_adr_folder_has_no_index_requirement(tmp_path: Path):
    make(tmp_path, {"doc/decisions/0001-use-postgres.md": "# x\n"})
    findings = by_item(run_check(tmp_path, only=["docs"]))
    assert findings["docs.adr"].status == OK and "doc/decisions, 1 files" in findings["docs.adr"].message
    assert "docs.adr-index" not in findings


def test_codeowners_lines_after_the_block_are_reported_as_changed(repo: Path):
    make(repo, {".github/CODEOWNERS": STANDARD_FILES[".github/CODEOWNERS"] + "/.github/ @someone-else\n"})
    finding = by_item(run_check(repo))["github.codeowners"]
    assert finding.status == CHANGED and not finding.blocking


def test_commit_emails_are_warnings_and_never_printed(repo: Path):
    personal = "person" + "@" + "mail.test"  # assembled: no address in this file
    make(repo, {"notes.md": "x\n"})
    commit(repo, "by a person", email=personal)
    git(repo, "config", "user.email", personal)
    report = run_check(repo)
    findings = by_item(report)
    assert findings["github.email"].status == MISSING and not findings["github.email"].blocking
    assert "1 of the last 2 commits" in findings["github.commit-email"].message
    assert report.exit_code == 0  # warnings don't fail
    assert personal not in report.render_text() and personal not in json.dumps(report.to_dict())


def test_kept_linters_and_editors_from_the_state_file(repo: Path):
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n[tool.black]\nline-length = 100\n')
    (repo / FILE_NAME).write_text(
        'standard = 1\nswerepo = "0.0.1"\ncomponents = ["ci", "agents"]\n'
        '[agents]\nhosts = ["claude", "antigravity"]\n[adopted]\nlinters = ["black"]\n',
        encoding="utf-8",
    )
    report = run_check(repo)
    findings = by_item(report)
    assert findings["ci.linter"].message == "linting: black (kept)"
    excluded = findings["ci.seamspec-excluded"]  # black's own settings don't skip locked SeamSpec tests (spec §6.3)
    assert excluded.status == CHANGED and excluded.message.startswith("black would touch locked SeamSpec tests")
    assert findings["agents.gemini"].status == MISSING  # Antigravity is in use, so GEMINI.md is needed
    assert by_item(report)["docs.chosen"].status == NOT_CHOSEN
    assert report.components == ["agents", "ci"]
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n[tool.black]\nextend-exclude = "\\\\.seamspec"\n')
    assert by_item(run_check(repo))["ci.seamspec-excluded"].status == OK


def test_kept_linters_in_ini_files_and_their_seamspec_settings(repo: Path):
    make(repo, {"pyproject.toml": '[project]\nname = "demo"\n', "setup.cfg": "[flake8]\nmax-line-length = 100\n"})
    finding = by_item(run_check(repo, only=["ci"]))["ci.seamspec-excluded"]
    assert finding.status == CHANGED and "flake8" in finding.message
    make(repo, {"setup.cfg": "[flake8]\nextend-exclude = .seamspec\n[isort]\nprofile = black\n"})
    finding = by_item(run_check(repo, only=["ci"]))["ci.seamspec-excluded"]
    assert finding.status == CHANGED and finding.message.startswith("isort would touch")  # flake8 now skips it


def test_only_checks_the_named_components(repo: Path):
    report = run_check(repo, only=["docs"])
    assert {f.component for f in report.findings} == {"docs"}
    with pytest.raises(UsageError, match="unknown component lint"):
        run_check(repo, only=["lint"])
    with pytest.raises(UsageError, match="at least one component"):
        run_check(repo, only=[])


def test_a_kept_linter_without_configuration_is_unknown(repo: Path):
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    (repo / FILE_NAME).write_text(
        'standard = 1\nswerepo = "0.0.1"\ncomponents = ["ci"]\n[adopted]\nlinters = ["black"]\n'
    )
    finding = by_item(run_check(repo))["ci.linter"]
    assert finding.status == UNKNOWN and "black kept, but no configuration found" in finding.message


@pytest.mark.parametrize(
    ("entries", "status"),
    [
        ('[".seamspec"]', OK),
        ('["./.seamspec/"]', OK),
        ('[".seamspec/**"]', OK),
        ('[".seamspec/proposed"]', MISSING),  # ruff would still reformat .seamspec/tests/
        ('[".seamspec-old"]', MISSING),
        ("true", MISSING),  # not a list: no crash
    ],
)
def test_ruff_must_skip_all_of_seamspec(repo: Path, entries: str, status: str):
    make(repo, {"pyproject.toml": f'[project]\nname = "demo"\n\n[tool.ruff]\nextend-exclude = {entries}\n'})
    assert by_item(run_check(repo, only=["ci"]))["ci.seamspec-excluded"].status == status


def test_yaml_comments_dont_count(repo: Path):
    workflow = ".github/workflows/swerepo-ci.yml"
    make(
        repo,
        {
            workflow: "jobs:\n  test:\n    steps:\n      - run: pytest  # seamspec verify --all\n"
            "  ci-ok:  # gate\n    needs: [test]  # every job\n"
        },
    )
    findings = by_item(run_check(repo))
    assert findings["ci.ci-ok"].status == OK  # a comment after the job name is fine
    assert findings["seamspec.ci"].status == MISSING  # `seamspec verify` only in a comment


def test_an_adopted_adr_folder_anywhere(repo: Path):
    make(repo, {"decisions/0001-use-pg.md": "x\n", "decisions/0002-use-uv.md": "x\n", "decisions/README.md": "x\n"})
    (repo / FILE_NAME).write_text(
        'standard = 1\nswerepo = "0.0.1"\ncomponents = ["docs"]\n[adopted]\nadr_dir = "decisions"\n'
    )
    finding = by_item(run_check(repo))["docs.adr"]
    assert finding.status == OK and finding.message == "ADRs (adopted: decisions, 2 files)"


def test_codeowners_names_the_overriding_patterns_not_the_owners(repo: Path):
    personal = "dev" + "@" + "mail.test.com"  # a malformed line: an owner with no pattern
    codeowners = f"# swerepo:begin\n/.github/ @owner\n# swerepo:end\n/docs/ @someone\n{personal}\n@team\n"
    make(repo, {".github/CODEOWNERS": codeowners})
    finding = by_item(run_check(repo))["github.codeowners"]
    assert finding.status == CHANGED and finding.message.endswith("governance owners (/docs/)")
    make(repo, {".github/CODEOWNERS": f"# swerepo:begin\n/.github/ @owner\n# swerepo:end\n{personal}\n"})
    message = by_item(run_check(repo))["github.codeowners"].message
    assert message.endswith("can override governance owners") and personal not in message


def test_a_subfolder_of_a_repository_is_noted(repo: Path):
    make(repo, {"services/api/README.md": "x\n"})
    finding = by_item(run_check(repo / "services/api"))["repository.git"]
    assert finding.status == UNKNOWN and "inside a git repository" in finding.message


def test_every_monorepo_project_is_covered_or_recorded(repo: Path):
    make(repo, {"services/api/pyproject.toml": '[project]\nname = "api"\n', "web/package.json": "{}\n"})
    findings = by_item(run_check(repo, only=["ci"]))
    assert findings["ci.projects:services/api"].message == "services/api/ not covered by any required check"
    assert findings["ci.projects:web"].status == MISSING
    state = 'standard = 1\nswerepo = "0.0.1"\ncomponents = ["ci"]\n'
    make(repo, {FILE_NAME: state + '[projects]\nlisted = ["services/api"]\nnot_covered = ["web"]\n'})
    findings = by_item(run_check(repo, only=["ci"]))
    assert findings["ci.projects:services/api"].status == MISSING  # listed, but the workflow has no jobs for it
    assert findings["ci.projects:web"].status == OK and "recorded as not covered" in findings["ci.projects:web"].message
    workflow = STANDARD_FILES[".github/workflows/swerepo-ci.yml"].replace(
        "  ci-ok:\n    needs: [test]",
        "  lint-services-api:\n    steps: []\n  test-services-api:\n    steps: []\n"
        "  ci-ok:\n    needs: [test, lint-services-api, test-services-api]",
    )
    make(repo, {".github/workflows/swerepo-ci.yml": workflow})
    findings = by_item(run_check(repo, only=["ci"]))
    assert findings["ci.projects:services/api"].status == OK and findings["ci.ci-ok"].status == OK
    make(repo, {FILE_NAME: state + '[github]\nextra_required_checks = ["web-tests"]\n'})
    assert by_item(run_check(repo, only=["ci"]))["ci.projects:web"].status == UNKNOWN


def test_ci_ok_must_wait_for_every_job(repo: Path):
    workflow = ".github/workflows/swerepo-ci.yml"
    make(repo, {workflow: "jobs:\n  lint:\n    steps: []\n  test:\n    steps: []\n  ci-ok:\n    needs: [test]\n"})
    finding = by_item(run_check(repo, only=["ci"]))["ci.ci-ok"]
    assert finding.status == MISSING and finding.message.startswith("ci-ok doesn't wait for lint")
    make(repo, {workflow: "jobs:\n  lint:\n    steps: []\n  ci-ok:\n    needs:\n      - lint\n    steps: []\n"})
    assert by_item(run_check(repo, only=["ci"]))["ci.ci-ok"].status == OK  # a block list counts too


@pytest.mark.parametrize(
    ("requires", "status"),
    [(">=3.11", OK), (">=3.12", OUTDATED), (None, OK), (">=3.99", UNKNOWN)],
)
def test_the_python_matrix_follows_requires_python(repo: Path, requires: str | None, status: str):
    declared = f'requires-python = "{requires}"\n' if requires else ""
    make(repo, {"pyproject.toml": f'[project]\nname = "demo"\n{declared}[tool.ruff]\nextend-exclude = [".seamspec"]\n'})
    assert by_item(run_check(repo, only=["ci"]))["ci.python-matrix"].status == status  # none declared: 3.11–3.14


def test_a_component_named_with_only_is_checked_even_if_not_chosen(repo: Path):
    report = run_check(repo, only=["openspec"])
    assert by_item(report)["openspec.setup"].status == MISSING


class TestStateFile:
    def test_an_unreadable_state_file_blocks(self, repo: Path):
        (repo / FILE_NAME).write_text("standard = \n", encoding="utf-8")
        finding = by_item(run_check(repo))["state.read"]
        assert finding.status == MISSING and finding.blocking

    def test_a_newer_state_file_is_unknown_not_an_error(self, repo: Path):
        (repo / FILE_NAME).write_text('standard = 1\nswerepo = "99.0.0"\ncomponents = ["docs", "future"]\n')
        report = run_check(repo)
        assert by_item(report)["state.newer"].status == UNKNOWN
        assert "upgrade SWERepo" in by_item(report)["state.newer"].message

    @pytest.fixture
    def store(self, tmp_path_factory) -> TemplateStore:
        root = tmp_path_factory.mktemp("templates")
        make(root, {"docs/progress/1.md": "v1\n", "docs/progress/2.md": "v2\n"})
        return TemplateStore(root)

    def test_records(self, repo: Path, store: TemplateStore):
        current, old = fingerprint(STANDARD_FILES["docs/PROGRESS.md"]), fingerprint("other")
        state = State.new(version="0.0.1")
        state.set_components(["docs", "agents"])
        state.set_file("docs/PROGRESS.md", Record("docs/progress@2", current, current))
        state.set_file("CONTRIBUTING.md", Record("docs/progress@1", old, old))
        state.set_file("docs/PROGRESS-copy.md", Record("docs/progress@2", current, current))
        state.set_file("LICENSE", Record("docs/license@1", fingerprint("Apache-2.0\n"), fingerprint("Apache-2.0\n")))
        block = fingerprint("rules\n")
        state.set_block("AGENTS.md", Record("agents/block@1", block, block))
        state.save(repo, running="0.0.1")
        findings = by_item(run_check(repo, store=store))
        assert findings["docs.progress"].status == OK
        assert "docs.file:docs/PROGRESS.md" not in findings  # current: the docs line already says ✓
        assert findings["docs.file:CONTRIBUTING.md"].status == CHANGED
        assert findings["docs.file:docs/PROGRESS-copy.md"].status == MISSING
        assert findings["docs.file:LICENSE"].status == UNKNOWN  # template unknown to this version
        assert findings["agents.block:AGENTS.md"].status == UNKNOWN  # unchanged, template not in the store
        make(repo, {"AGENTS.md": "<!-- swerepo:begin -->\nmy rules\n<!-- swerepo:end -->\n"})
        assert by_item(run_check(repo, store=store))["agents.block:AGENTS.md"].status == CHANGED

    def test_a_deleted_recorded_file_is_one_finding(self, repo: Path, store: TemplateStore):
        current = fingerprint(STANDARD_FILES["docs/PROGRESS.md"])
        state = State.new(version="0.0.1")
        state.set_components(["docs"])
        state.set_file("docs/PROGRESS.md", Record("docs/progress@2", current, current))
        state.save(repo, running="0.0.1")
        (repo / "docs/PROGRESS.md").unlink()
        report = run_check(repo, store=store)
        assert [f.item for f in report.findings if f.path == "docs/PROGRESS.md"] == ["docs.progress"]
        assert report.count(MISSING) == 1

    def test_an_os_error_never_shows_the_path(self, repo: Path, monkeypatch):
        (repo / FILE_NAME).write_text('standard = 1\nswerepo = "0.0.1"\n')
        original = Path.read_text

        def refuse(self, *args, **kwargs):
            if self.name == FILE_NAME:
                raise PermissionError(13, "Permission denied", str(self))
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", refuse)
        report = run_check(repo)
        assert by_item(report)["state.read"].message == f"{FILE_NAME}: can't read it: Permission denied"
        assert str(repo) not in report.render_text() and str(repo) not in json.dumps(report.to_dict())

    def test_an_outdated_record(self, repo: Path, store: TemplateStore):
        current = fingerprint(STANDARD_FILES["docs/PROGRESS.md"])
        state = State.new(version="0.0.1")
        state.set_components(["docs"])
        state.set_file("docs/PROGRESS.md", Record("docs/progress@1", current, current))
        state.save(repo, running="0.0.1")
        finding = by_item(run_check(repo, store=store))["docs.file:docs/PROGRESS.md"]
        assert finding.status == OUTDATED and "@2 available" in finding.message


def test_check_writes_nothing(repo: Path):
    git(repo, "checkout", "-q", "-b", "feature")
    make(repo, {"docs/progress/20260102-more.md": "x\n"})
    before = snapshot(repo)
    run_check(repo)
    run_check(repo, base="main", author="someone")
    assert snapshot(repo) == before


class TestCommandLine:
    runner = CliRunner()

    def test_text_output_and_exit_code(self, repo: Path):
        result = self.runner.invoke(app, ["check", "--path", str(repo)])
        out = unstyle(result.stdout)
        assert result.exit_code == 0
        assert out.startswith(f"SWERepo · check · {repo.name} (standard 1, no .swerepo.toml yet)")
        assert "  docs      ✓ README.md" in out
        assert str(repo) not in out  # the folder's name, never its absolute path

    def test_missing_items_exit_1(self, repo: Path):
        (repo / "SECURITY.md").unlink()
        result = self.runner.invoke(app, ["check", "--path", str(repo)])
        assert result.exit_code == 1 and "✗ SECURITY.md missing" in result.stdout

    def test_json(self, repo: Path):
        result = self.runner.invoke(app, ["check", "--path", str(repo), "--json", "--only", "docs,ci"])
        data = json.loads(result.stdout)
        assert data["standard"] == 1 and data["exit_code"] == 0 and data["components"] == ["docs", "ci"]
        assert {"component", "item", "status", "message", "path", "blocking"} <= set(data["findings"][0])
        assert str(repo) not in result.stdout

    def test_wrong_usage_exits_2(self, repo: Path):
        result = self.runner.invoke(app, ["check", "--path", str(repo), "--only", "lint"])
        assert result.exit_code == 2
        assert self.runner.invoke(app, ["check", "--path", str(repo), "--skip", "adr"]).exit_code == 2
        assert self.runner.invoke(app, ["check", "--path", str(repo), "--only", ""]).exit_code == 2
        assert self.runner.invoke(app, ["check", "--path", str(repo), "--base", "no-such-ref"]).exit_code == 2

    def test_annotations_on_github_actions_with_ci(self, repo: Path, monkeypatch):
        (repo / "SECURITY.md").unlink()
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        out = self.runner.invoke(app, ["check", "--path", str(repo), "--ci"]).stdout
        assert "::error file=SECURITY.md,title=swerepo check::security: SECURITY.md missing" in out
        monkeypatch.delenv("GITHUB_ACTIONS")
        assert "::error" not in self.runner.invoke(app, ["check", "--path", str(repo), "--ci"]).stdout

    def test_json_with_ci_on_github_actions_is_only_json(self, repo: Path, monkeypatch):
        (repo / "SECURITY.md").unlink()
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        result = self.runner.invoke(app, ["check", "--path", str(repo), "--ci", "--json"])
        assert json.loads(result.stdout)["exit_code"] == 1

    def test_annotation_values_are_escaped(self):
        finding = Finding("state", "state.read", MISSING, "bad: 100%\nline two\r", "a,b:c.toml", blocking=True)
        report = Report(folder="x", mode=None, has_state=True, components=[], findings=[finding])
        assert report.annotations() == [
            "::error file=a%2Cb%3Ac.toml,title=swerepo check::state: bad: 100%25%0Aline two%0D"
        ]


class TestCopilotReviewOfPR3:
    """Findings from Copilot's review of PR #3, each reproduced before the fix (docs/reviews/phase-2.md)."""

    def test_a_newline_in_a_value_cant_start_a_workflow_command(self, repo: Path, monkeypatch):
        (repo / FILE_NAME).write_text('standard = 1\nswerepo = "99.0.0"\nmode = "x\\n::error::injected"\n')
        assert not [line for line in run_check(repo).render_text().splitlines() if line.startswith("::")]
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        runner = CliRunner()
        out = runner.invoke(app, ["check", "--path", str(repo), "--ci"]).output
        assert "mode: x\\n::error::injected" in out and "\n::error::injected" not in out
        usage = runner.invoke(app, ["check", "--path", str(repo), "--only", "docs,x\n::error::y"])
        assert usage.exit_code == 2 and "\n::error::y" not in usage.output

    def test_an_explicit_empty_hosts_list_chooses_no_editor(self, repo: Path):
        (repo / "CLAUDE.md").unlink()  # .claude/ is still there
        (repo / FILE_NAME).write_text(
            'standard = 1\nswerepo = "0.0.1"\ncomponents = ["agents"]\n[agents]\nhosts = []\n'
        )
        assert "agents.claude" not in by_item(run_check(repo))

    def test_an_explicit_empty_component_list_chooses_nothing(self, repo: Path):
        (repo / FILE_NAME).write_text('standard = 1\nswerepo = "0.0.1"\ncomponents = []\n')
        report = run_check(repo)
        assert report.components == [] and report.exit_code == 0
        assert by_item(report)["docs.chosen"].status == NOT_CHOSEN

    def test_a_tool_value_that_isnt_a_table(self, repo: Path):
        make(repo, {
            "pyproject.toml": 'tool = "oops"\n',
            ".pre-commit-config.yaml": "repos:\n- repo: x\n  hooks:\n  - id: ruff\n",
        })  # fmt: skip
        assert by_item(run_check(repo, only=["ci"]))["ci.seamspec-excluded"].status == UNKNOWN

    @pytest.mark.parametrize(
        ("steps", "status"),
        [
            ("      - name: seamspec verify\n        run: pytest\n", MISSING),  # a step's name isn't a command
            ("      - run: pytest\n        env:\n          NOTE: seamspec verify\n", MISSING),
            ("      - run: |\n          pytest\n          # seamspec verify --all\n", MISSING),
            ("      - run: echo hi # seamspec verify\n", MISSING),
            ("      - run: uv run seamspec verify --all --ci\n", OK),
            ("      - run: uvx seamspec==0.1.1 verify --all\n", OK),
            ("      - name: rules\n        run: |\n          uv sync\n          uv run seamspec verify --all\n", OK),
            ('      - run: "seamspec verify"\n', OK),
            # Copilot's review of PR #4: arguments, `env` keys named `run`, and keys after a block don't count
            ("      - run: echo seamspec verify\n", MISSING),
            ("      - run: pytest\n        env:\n          run: seamspec verify\n", MISSING),
            ("      - run: |\n          pytest\n        env:\n          NOTE: seamspec verify\n", MISSING),
            ("      - uses: x/y@v1\n        with:\n          steps:\n            - run: seamspec verify\n", MISSING),
            ("      - run: uv run --frozen seamspec verify --all\n", OK),
            ("      - run: FOO=1 uv run seamspec verify\n", OK),
            ("      - run: cd app && uvx --from seamspec==0.1.1 seamspec verify\n", OK),
            ("      - run: python -m seamspec verify\n", OK),
            ("      - run: >\n          uv run\n          seamspec verify\n", OK),
            ("      - run: pytest\n  b:\n    steps:\n    - name: rules\n      run: uv run seamspec verify --all\n", OK),
        ],
    )
    def test_only_a_run_step_counts_as_running_the_locked_rules(self, repo: Path, steps: str, status: str):
        make(repo, {".github/workflows/swerepo-ci.yml": f"jobs:\n  t:\n    steps:\n{steps}  ci-ok:\n    needs: [t]\n"})
        assert by_item(run_check(repo, only=["seamspec"]))["seamspec.ci"].status == status

    def test_a_rejected_path_in_the_state_file_isnt_repeated(self, repo: Path):
        home = "/home/" + "alice/decisions"
        (repo / FILE_NAME).write_text(f'standard = 1\nswerepo = "0.0.1"\n[adopted]\nadr_dir = "{home}"\n')
        report = run_check(repo)
        assert (
            by_item(report)["state.read"].message
            == ".swerepo.toml: adopted.adr_dir: a path must be relative and use '/'"
        )
        assert home not in report.render_text() and home not in json.dumps(report.to_dict())
        (repo / FILE_NAME).write_text(
            f'standard = 1\nswerepo = "0.0.1"\n[files."{home}"]\ntemplate = "docs/x@1"\nrendered = "x"\nwritten = "x"\n'
        )
        message = by_item(run_check(repo))["state.read"].message
        assert message.startswith(".swerepo.toml: files: a path must be relative") and home not in message
