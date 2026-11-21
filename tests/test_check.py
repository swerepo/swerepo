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
        "jobs:\n  test:\n    steps:\n      - run: pytest\n      - run: seamspec verify --all\n"
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
    assert findings["ci.seamspec-excluded"].status == UNKNOWN  # checked from Phase 4 for other linters
    assert findings["agents.gemini"].status == MISSING  # Antigravity is in use, so GEMINI.md is needed
    assert by_item(report)["docs.chosen"].status == NOT_CHOSEN
    assert report.components == ["agents", "ci"]


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
        repo, {workflow: "jobs:\n  test:\n    steps:\n      - run: pytest  # seamspec verify --all\n  ci-ok:  # gate\n"}
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


def test_monorepo_coverage_is_a_later_check(repo: Path):
    make(repo, {"services/api/pyproject.toml": '[project]\nname = "api"\n'})
    finding = by_item(run_check(repo, only=["ci"]))["ci.projects"]
    assert finding.status == UNKNOWN and "Phase 4" in finding.message


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
