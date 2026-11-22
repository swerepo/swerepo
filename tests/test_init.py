"""`swerepo init` for docs and agents on fixture repositories (spec §5, §6.5, §6.6, §10; ADR-20261121-6c3d)."""

import datetime
import json
import os
import time
from pathlib import Path

import pytest
from repo_helpers import commit, git, git_init, make, snapshot
from typer.testing import CliRunner

from swerepo import cli
from swerepo.check import MISSING, UsageError, run_check
from swerepo.cli import app
from swerepo.fingerprint import fingerprint
from swerepo.init import (
    ADD_BLOCK,
    ADOPT,
    CHANGED,
    CREATE,
    CURRENT,
    KEEP,
    LATER_VERB,
    OUTDATED,
    InitError,
    apply,
    make_plan,
)
from swerepo.render import TemplateStore
from swerepo.state import FILE_NAME, Record, State

TODAY = datetime.date(2026, 11, 21)
RUNBOOKS = [f"docs/agents/{n}.md" for n in ("prepare-pr", "address-review", "record-adr")]
MANAGED = ["docs/adr/README.md", "docs/adr/TEMPLATE.md", *RUNBOOKS]
STARTERS = [
    "README.md",
    "docs/PROGRESS.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "docs/progress/20261121-swerepo-init.md",
]


def init(root: Path, **kwargs):
    plan = make_plan(root, today=TODAY, **kwargs)
    apply(plan, root)
    return plan


def verbs(plan) -> dict[str, str]:
    return {a.path: a.verb for a in plan.actions if a.path}


@pytest.fixture
def new_project(tmp_path: Path) -> Path:
    git_init(tmp_path)
    make(tmp_path, {"pyproject.toml": '[project]\nname = "invoices"\n'})
    return tmp_path


class TestNewProject:
    def test_creates_the_docs_and_agents_files(self, new_project: Path):
        plan = init(new_project, hosts=["claude"])
        created = {p for p, v in verbs(plan).items() if v == CREATE}
        assert created >= {*MANAGED, *STARTERS, "AGENTS.md", "CLAUDE.md"}
        assert "# invoices" in (new_project / "README.md").read_text()
        assert (new_project / "CLAUDE.md").read_text() == "\n".join(
            ["<!-- swerepo:begin -->", "@AGENTS.md", "<!-- swerepo:end -->", ""]
        )
        agents = (new_project / "AGENTS.md").read_text()
        assert agents.startswith("# Agent instructions\n\n<!-- swerepo:begin -->\n## Working rules")
        assert "- Test: `uv run pytest`" in agents and "`docs/progress/`" in agents
        assert len(agents.splitlines()) < 40  # spec §6.6: short, read every session

    def test_check_then_finds_docs_and_agents_complete(self, new_project: Path):
        init(new_project, hosts=["claude"])
        report = run_check(new_project, only=["docs", "agents"])
        assert report.count(MISSING) == 0 and report.exit_code == 0

    def test_the_state_file_records_what_was_written(self, new_project: Path):
        init(new_project, hosts=["claude", "gemini"])
        state = State.load(new_project)
        assert state.components == ["docs", "agents"] and state.hosts == ["claude", "gemini"]
        assert set(state.files()) == set(MANAGED)  # starter files are the person's: not recorded
        assert set(state.blocks()) == {"AGENTS.md", "CLAUDE.md", "GEMINI.md"}
        assert state.values["project"] == "invoices" and state.pr_enforce  # a new project enforces the PR rules

    def test_running_it_again_changes_nothing(self, new_project: Path):
        init(new_project, hosts=["claude"])
        before = snapshot(new_project)
        plan = init(new_project)
        assert not plan.changes and plan.state_text is None
        assert {v for p, v in verbs(plan).items() if p in MANAGED} == {CURRENT}
        assert snapshot(new_project) == before

    def test_a_plan_writes_nothing(self, new_project: Path):
        before = snapshot(new_project)
        plan = make_plan(new_project, today=TODAY)
        assert plan.changes and snapshot(new_project) == before

    def test_not_a_git_repository_is_initialised(self, tmp_path: Path):
        make(tmp_path, {"pyproject.toml": '[project]\nname = "x"\n'})
        plan = init(tmp_path, hosts=[])
        assert plan.actions[0].verb == "git init" and (tmp_path / ".git").is_dir()

    def test_the_adr_index_lists_adrs_already_there(self, new_project: Path):
        make(new_project, {"docs/adr/ADR-20260101-abcd-first.md": "---\ntitle: First\nstatus: ACCEPTED\n---\n"})
        init(new_project, hosts=[])
        row = "| [ADR-20260101-abcd](ADR-20260101-abcd-first.md) | First | ACCEPTED |"
        assert row in (new_project / "docs/adr/README.md").read_text()
        assert run_check(new_project, only=["docs"]).exit_code == 0


class TestExistingRepository:
    @pytest.fixture
    def repo(self, tmp_path: Path) -> Path:
        git_init(tmp_path)
        make(tmp_path, {
            "pyproject.toml": '[project]\nname = "legacy"\n',
            "README.md": "# Legacy\n\nOurs.\n",
            "AGENTS.md": "# Our rules\n\nBe kind.\n",
            "CLAUDE.md": "Use tabs.\n",
            "CONTRIBUTING.md": "# Help\n",
            "CHANGELOG.md": "# Changes\n\n## 1.0\n",
        })  # fmt: skip
        commit(tmp_path, "start")
        return tmp_path

    def test_existing_files_keep_their_text_and_only_gain_a_block(self, repo: Path):
        names = ("README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "CHANGELOG.md")
        originals = {name: (repo / name).read_text() for name in names}
        plan = init(repo, hosts=["claude"])
        assert verbs(plan)["AGENTS.md"] == ADD_BLOCK and verbs(plan)["CLAUDE.md"] == ADD_BLOCK
        for name in ("README.md", "CONTRIBUTING.md", "CHANGELOG.md"):
            assert verbs(plan)[name] == KEEP and (repo / name).read_text() == originals[name]
        for name in ("AGENTS.md", "CLAUDE.md"):
            assert (repo / name).read_text().startswith(originals[name].rstrip("\n") + "\n\n<!-- swerepo:begin -->\n")

    def test_a_changelog_without_unreleased_is_kept_and_reported(self, repo: Path):
        action = next(a for a in make_plan(repo, today=TODAY).actions if a.path == "CHANGELOG.md")
        assert action.verb == KEEP and "[Unreleased]" in action.note

    def test_pull_request_rules_start_as_warnings(self, repo: Path):
        init(repo, hosts=[])
        state = State.load(repo)
        assert not state.pr_enforce and state.doc["pr"]["warn_since"] == TODAY

    def test_claude_md_that_already_imports_agents_md_is_kept(self, repo: Path):
        make(repo, {"CLAUDE.md": "@AGENTS.md\nMore.\n"})
        plan = init(repo, hosts=["claude"])
        assert verbs(plan)["CLAUDE.md"] == KEEP and (repo / "CLAUDE.md").read_text() == "@AGENTS.md\nMore.\n"

    def test_an_existing_adr_folder_is_adopted_not_added_to(self, repo: Path):
        make(repo, {"docs/decisions/0001-use-django.md": "# Use Django\n"})
        plan = init(repo, hosts=[])
        assert verbs(plan)["docs/decisions"] == ADOPT
        assert sorted(p.name for p in (repo / "docs/decisions").iterdir()) == ["0001-use-django.md"]
        assert State.load(repo).adopted["adr_dir"] == "docs/decisions"
        assert "`docs/decisions/`" in (repo / "AGENTS.md").read_text()

    def test_files_and_blocks_a_person_edited_are_kept(self, repo: Path):
        init(repo, hosts=["claude"])
        make(repo, {"docs/agents/prepare-pr.md": "# Our own way\n"})
        make(repo, {"AGENTS.md": (repo / "AGENTS.md").read_text().replace("## Commands", "## Our commands")})
        before = snapshot(repo)
        plan = init(repo)
        assert verbs(plan)["docs/agents/prepare-pr.md"] == CHANGED and verbs(plan)["AGENTS.md"] == CHANGED
        assert not plan.changes and snapshot(repo) == before

    def test_a_block_without_a_record_is_the_persons(self, repo: Path):
        make(repo, {"AGENTS.md": "<!-- swerepo:begin -->\nmine\n<!-- swerepo:end -->\n"})
        assert verbs(make_plan(repo, hosts=[]))["AGENTS.md"] == KEEP

    def test_broken_markers_are_reported_not_touched(self, repo: Path):
        make(repo, {"AGENTS.md": "<!-- swerepo:begin -->\nno end\n"})
        action = next(a for a in make_plan(repo, hosts=[]).actions if a.path == "AGENTS.md")
        assert action.verb == KEEP and "broken" in action.note


class TestChoices:
    def test_editors_decide_claude_and_gemini_files(self, new_project: Path):
        plan = make_plan(new_project, hosts=[])
        assert "CLAUDE.md" not in verbs(plan) and "GEMINI.md" not in verbs(plan)
        plan = make_plan(new_project, hosts=["antigravity"])
        assert verbs(plan)["GEMINI.md"] == CREATE and "CLAUDE.md" not in verbs(plan)

    def test_editors_default_to_what_detection_found(self, new_project: Path):
        make(new_project, {".claude/settings.json": "{}\n"})
        plan = make_plan(new_project)
        assert plan.hosts == ["claude"] and not plan.hosts_recorded

    def test_only_and_skip(self, new_project: Path):
        plan = make_plan(new_project, only=["agents"], hosts=[])
        assert {a.component for a in plan.actions} == {"agents", "state"}
        plan = make_plan(new_project, skip=["agents"])
        assert "agents" not in {a.component for a in plan.actions}

    def test_components_of_later_phases_are_listed_not_applied(self, new_project: Path):
        plan = make_plan(new_project, only=["ci"])
        assert [(a.component, a.verb) for a in plan.actions] == [("ci", LATER_VERB)]
        assert plan.state_text is None and not plan.changes

    def test_wrong_names_are_usage_errors(self, new_project: Path):
        with pytest.raises(UsageError, match="unknown component lint"):
            make_plan(new_project, only=["lint"])
        with pytest.raises(UsageError, match="unknown editor emacs"):
            make_plan(new_project, hosts=["emacs"])

    @pytest.mark.parametrize(
        ("files", "test", "lint"),
        [
            ({}, "`uv run pytest`", "`uv run ruff check .` and `uv run ruff format --check .`"),
            ({"poetry.lock": ""}, "`poetry run pytest`", "`poetry run ruff check .`"),
            ({"Makefile": "test:\n\tpytest\nlint:\n\truff check .\n"}, "`make test`", "`make lint`"),
            ({"setup.cfg": "[flake8]\nmax-line-length = 100\n"}, "`uv run pytest`", "`uv run flake8`"),
        ],
    )
    def test_commands_follow_the_project(self, new_project: Path, files: dict, test: str, lint: str):
        make(new_project, files)
        block = next(a for a in make_plan(new_project, hosts=[]).actions if a.path == "AGENTS.md").content
        assert f"- Test: {test}" in block and lint in block


class TestSafety:
    def test_a_newer_or_unreadable_state_file_stops_init(self, new_project: Path):
        make(new_project, {FILE_NAME: 'standard = 1\nswerepo = "99.0.0"\n'})
        with pytest.raises(InitError, match="Upgrade SWERepo"):
            make_plan(new_project)
        make(new_project, {FILE_NAME: "standard = \n"})
        with pytest.raises(InitError, match="Fix or remove it first"):
            make_plan(new_project)
        assert (new_project / FILE_NAME).read_text() == "standard = \n"

    def test_a_folder_of_repositories_stops_init(self, tmp_path: Path):
        git_init(tmp_path / "one")
        with pytest.raises(InitError, match="holds other repositories"):
            make_plan(tmp_path)

    def test_a_file_that_appears_after_the_plan_is_never_replaced(self, new_project: Path):
        plan = make_plan(new_project, hosts=[], today=TODAY)
        make(new_project, {"CONTRIBUTING.md": "# Written meanwhile\n"})
        with pytest.raises(InitError, match="appeared since the plan"):
            apply(plan, new_project)
        assert (new_project / "CONTRIBUTING.md").read_text() == "# Written meanwhile\n"

    def test_an_older_template_is_reported_outdated_not_rewritten(self, new_project: Path, tmp_path_factory):
        state = State.new(version="0.0.1")
        state.set_file("docs/adr/TEMPLATE.md", Record("docs/adr-template@1", fingerprint("v1\n"), fingerprint("v1\n")))
        state.save(new_project, running="0.0.1")
        make(new_project, {"docs/adr/TEMPLATE.md": "v1\n"})
        newer = tmp_path_factory.mktemp("templates")
        bundled = Path(str(TemplateStore().root))
        for template in bundled.rglob("*"):
            if template.is_file() and template.name[0].isdigit():
                make(newer, {template.relative_to(bundled).as_posix(): template.read_text()})
        make(newer, {"docs/adr-template/2.md": "v2\n"})
        plan = make_plan(new_project, hosts=[], store=TemplateStore(newer))
        assert verbs(plan)["docs/adr/TEMPLATE.md"] == OUTDATED
        assert (new_project / "docs/adr/TEMPLATE.md").read_text() == "v1\n"


class TestCommandLine:
    runner = CliRunner()

    def test_yes_applies_and_says_what_next(self, new_project: Path):
        result = self.runner.invoke(app, ["init", "--path", str(new_project), "--yes"])
        assert result.exit_code == 0, result.output
        assert "Applied:" in result.output and "commit them on a new branch" in result.output
        assert (new_project / FILE_NAME).is_file()

    def test_dry_run_and_no_terminal_write_nothing(self, new_project: Path):
        before = snapshot(new_project)
        dry = self.runner.invoke(app, ["init", "--path", str(new_project), "--dry-run"])
        assert dry.exit_code == 0 and "create    AGENTS.md" in dry.output
        stopped = self.runner.invoke(app, ["init", "--path", str(new_project)])
        assert stopped.exit_code == 2 and "--yes" in stopped.output
        assert snapshot(new_project) == before

    def test_in_a_terminal_it_asks_the_editors_then_to_apply(self, new_project: Path, monkeypatch):
        monkeypatch.setattr(cli, "_interactive", lambda: True)
        declined = self.runner.invoke(app, ["init", "--path", str(new_project)], input="antigravity\nn\n")
        assert declined.exit_code == 0 and "Nothing applied." in declined.output and "Antigravity" in declined.output
        assert not (new_project / FILE_NAME).exists()
        accepted = self.runner.invoke(app, ["init", "--path", str(new_project)], input="claude, gemini\ny\n")
        assert accepted.exit_code == 0 and State.load(new_project).hosts == ["claude", "gemini"]

    def test_json(self, new_project: Path):
        result = self.runner.invoke(app, ["init", "--path", str(new_project), "--yes", "--json"])
        data = json.loads(result.output)
        assert data["applied"] and data["components"] == ["docs", "agents", "ci", "security", "github", "seamspec"]
        assert {"component", "action", "path", "note"} == set(data["actions"][0])
        assert str(new_project) not in result.output

    def test_shorthand_flags(self, new_project: Path):
        result = self.runner.invoke(app, ["init", "--path", str(new_project), "--dry-run", "--docs"])
        assert "agents" not in result.output.split("\n", 1)[1] and "docs" in result.output
        result = self.runner.invoke(app, ["init", "--path", str(new_project), "--dry-run", "--no-agents", "--no-ci"])
        assert "AGENTS.md" not in result.output and "  ci " not in result.output
        assert self.runner.invoke(app, ["init", "--path", str(new_project), "--dcos"]).exit_code == 2
        assert self.runner.invoke(app, ["check", "--path", str(new_project), "--docs"]).exit_code in (0, 1)
        assert self.runner.invoke(app, ["check", "--path", str(new_project), "--lint"]).exit_code == 2

    def test_a_personal_git_email_gets_a_warning_without_the_address(self, new_project: Path):
        personal = "dev" + "@" + "mail.test.com"
        git(new_project, "config", "user.email", personal)
        result = self.runner.invoke(app, ["init", "--path", str(new_project), "--yes"])
        assert "isn't a noreply address" in result.output and personal not in result.output


class TestGeminiReviewRound1:
    """Phase 3 review findings (docs/reviews/phase-3.md), each reproduced before the fix."""

    def test_p3_f01_check_no_component_subtracts_from_the_chosen_ones(self, new_project: Path):
        runner = CliRunner()
        init(new_project, hosts=[])
        result = runner.invoke(app, ["check", "--path", str(new_project), "--no-agents"])
        lines = result.output.splitlines()[1:-1]
        rows = [line.split(maxsplit=1) for line in lines if line.startswith("  ") and line[2] != " "]
        assert result.exit_code == 0 and "agents" not in {label for label, _ in rows}
        assert all(rest.startswith("– not chosen") for label, rest in rows if label != "docs")  # nothing forced on
        assert runner.invoke(app, ["check", "--path", str(new_project), "--only", "", "--no-docs"]).exit_code == 2
        assert runner.invoke(app, ["check", "--path", str(new_project), "--docs", "--no-docs"]).exit_code == 2

    def test_p3_f02_crlf_file_gets_a_crlf_block(self, new_project: Path):
        (new_project / "AGENTS.md").write_bytes(b"# Rules\r\n\r\n")
        init(new_project, hosts=[])
        text = (new_project / "AGENTS.md").read_bytes()
        assert text.startswith(b"# Rules\r\n\r\n<!-- swerepo:begin -->\r\n") and b"\n" not in text.replace(b"\r\n", b"")

    def test_p3_f02_broken_index_markers_are_reported_not_a_crash(self, new_project: Path):
        init(new_project, hosts=[])
        readme = new_project / "docs/adr/README.md"
        readme.write_text(readme.read_text().replace("<!-- swerepo:adr-index:end -->\n", ""))
        assert verbs(make_plan(new_project))["docs/adr/README.md"] == CHANGED
        result = CliRunner().invoke(app, ["check", "--path", str(new_project), "--only", "docs"])
        assert result.exit_code == 1 and (result.exception is None or isinstance(result.exception, SystemExit))
        assert "markers are broken" in result.output

    def test_p3_f02_broken_markers_appearing_before_apply_are_an_init_error(self, new_project: Path):
        make(new_project, {"AGENTS.md": "# Ours\n"})
        plan = make_plan(new_project, hosts=[], today=TODAY)
        make(new_project, {"AGENTS.md": "# Ours\n<!-- swerepo:begin -->\n"})
        with pytest.raises(InitError, match="markers are broken"):
            apply(plan, new_project)

    def test_p3_f07_a_block_appearing_before_apply_is_never_doubled(self, new_project: Path):
        make(new_project, {"AGENTS.md": "# Ours\n"})
        plan = make_plan(new_project, hosts=[], today=TODAY)
        meanwhile = "# Ours\n<!-- swerepo:begin -->\nmine\n<!-- swerepo:end -->\n"
        make(new_project, {"AGENTS.md": meanwhile})
        with pytest.raises(InitError, match="got a SWERepo block since the plan"):
            apply(plan, new_project)
        assert (new_project / "AGENTS.md").read_text() == meanwhile

    def test_p3_f03_a_failed_git_init_never_shows_the_path(self, tmp_path: Path, monkeypatch):
        folder = tmp_path / "project"
        folder.mkdir()
        (folder / ".git").write_text("not a repository\n")  # git init fails on a file named .git
        plan = make_plan(folder, hosts=[], today=TODAY)
        with pytest.raises(InitError) as caught:
            apply(plan, folder)
        assert "git init failed" in str(caught.value) and str(tmp_path) not in str(caught.value)

    def test_p3_f04_existing_docs_still_get_a_progress_entry(self, tmp_path: Path):
        git_init(tmp_path)
        make(tmp_path, {
            "README.md": "# x\n", "docs/adr/README.md": "# Ours\n", "docs/adr/0001-x.md": "# X\n",
            "docs/PROGRESS.md": "p\n", "CHANGELOG.md": "# C\n\n## [Unreleased]\n", "CONTRIBUTING.md": "c\n",
        })  # fmt: skip
        commit(tmp_path, "start")
        plan = init(tmp_path, only=["docs"])
        assert verbs(plan)["docs/progress/20261121-swerepo-init.md"] == CREATE
        assert verbs(plan)["docs/adr"] == ADOPT  # a hand-written README without index markers: the person's folder
        assert run_check(tmp_path, only=["docs"]).exit_code == 0
        assert "recorded the components" in (tmp_path / "docs/progress/20261121-swerepo-init.md").read_text()

    def test_p3_f04_a_subfolder_of_a_repository_is_refused(self, new_project: Path):
        (new_project / "sub").mkdir()
        with pytest.raises(InitError, match="top level"):
            make_plan(new_project / "sub")

    def test_p3_f04_init_and_check_agree_on_changelog_and_gemini(self, new_project: Path):
        make(
            new_project,
            {"CHANGELOG.md": "# C\n\n## [Unreleased] - draft\n", "GEMINI.md": "See [AGENTS.md](AGENTS.md).\n"},
        )
        plan = make_plan(new_project, hosts=["gemini"])
        changelog = next(a for a in plan.actions if a.path == "CHANGELOG.md")
        assert "[Unreleased]" in changelog.note  # check reports it too
        assert verbs(plan)["GEMINI.md"] == KEEP

    def test_p3_f07_adopted_linters_decide_the_commands(self, new_project: Path):
        make(new_project, {"pyproject.toml": '[project]\nname = "x"\n[tool.ruff]\n'})
        state = State.new(version="0.0.1")
        state.doc.add("adopted", {"linters": ["black"]})
        state.save(new_project, running="0.0.1")
        block = next(a for a in make_plan(new_project, hosts=[]).actions if a.path == "AGENTS.md").content
        assert "`uv run black --check .`" in block and "ruff" not in block


def test_q4_changed_commands_are_noted_not_applied(new_project: Path):
    init(new_project, hosts=[])
    make(new_project, {"Makefile": "test:\n\tpytest\n"})
    before = snapshot(new_project)
    plan = init(new_project)
    notes = [a.note for a in plan.actions if a.verb == "note" and a.component == "agents"]
    assert notes and "commands changed" in notes[0] and not plan.changes and snapshot(new_project) == before


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads any file")
class TestUnreadableFiles:
    """P3-F09: unreadable files are errors naming the repository path, never a traceback or an absolute path."""

    def _locked(self, path: Path, text: str = "x\n") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(0)
        return path

    def test_an_unreadable_agents_md(self, new_project: Path):
        locked = self._locked(new_project / "AGENTS.md")
        try:
            result = CliRunner().invoke(app, ["init", "--path", str(new_project), "--dry-run"])
        finally:
            locked.chmod(0o644)
        assert result.exit_code == 1 and "AGENTS.md: can't read it (Permission denied)" in result.output
        assert str(new_project) not in result.output

    def test_an_unreadable_adr(self, new_project: Path):
        locked = self._locked(new_project / "docs/adr/ADR-20260101-abcd-t.md")
        try:
            result = CliRunner().invoke(app, ["init", "--path", str(new_project), "--dry-run"])
        finally:
            locked.chmod(0o644)
        assert result.exit_code == 1 and "docs/adr/ADR-20260101-abcd-t.md: can't read it" in result.output
        assert str(new_project) not in result.output

    def test_unreadable_progress_files(self, new_project: Path):
        locked = [
            self._locked(new_project / "docs/PROGRESS.md", "## Now\n"),
            self._locked(new_project / "docs/progress/20260101-a.md"),
        ]
        try:
            result = CliRunner().invoke(app, ["progress", "--path", str(new_project)])
        finally:
            for path in locked:
                path.chmod(0o644)
        assert result.exit_code == 0 and "docs/PROGRESS.md can't be read" in result.output
        assert "### 20260101-a.md" in result.output and str(new_project) not in result.output


class TestSeamSpecReviewOfInv8314036c:
    """Gaps SeamSpec's reviewer found in the proposed rule inv_8314036c, before the owner's approval."""

    @pytest.mark.parametrize("text", ["# Ours\n\n\n", "# Ours\r\n\r\n\r\n\r\n", "   ", "# Ours", "# Ours\n \n"])
    def test_the_persons_text_is_kept_exactly_trailing_blank_lines_too(self, new_project: Path, text: str):
        (new_project / "AGENTS.md").write_bytes(text.encode())
        init(new_project, hosts=[])
        now = (new_project / "AGENTS.md").read_bytes().decode()
        nl = "\r\n" if "\r\n" in text else "\n"
        rest = now[len(text) :]
        assert now.startswith(text) and rest.lstrip("\r\n").startswith("<!-- swerepo:begin -->" + nl)
        assert (text + rest[: len(rest) - len(rest.lstrip("\r\n"))]).endswith(
            nl + nl
        )  # exactly one blank line at least

    def test_p3_f10_blank_crlf_lines_inside_a_file_take_linear_time(self, new_project: Path):
        text = "# Ours\r\n" + "\r\n" * 28 + "# End\r\n"  # about a minute with the old regex, not forever
        (new_project / "AGENTS.md").write_bytes(text.encode())
        started = time.perf_counter()
        init(new_project, hosts=[])
        assert time.perf_counter() - started < 5  # seconds; the old code doubled its time per blank line
        assert (new_project / "AGENTS.md").read_bytes().decode().startswith(text + "\r\n<!-- swerepo:begin -->\r\n")

    def test_a_conflict_writes_nothing_at_all(self, new_project: Path):
        make(new_project, {"AGENTS.md": "# Ours\n"})
        plan = make_plan(new_project, hosts=[], today=TODAY)
        before = snapshot(new_project)
        make(new_project, {"docs/agents/record-adr.md": "# Meanwhile\n"})  # the last file the plan creates
        meanwhile = snapshot(new_project)
        with pytest.raises(InitError, match="nothing written"):
            apply(plan, new_project)
        assert snapshot(new_project) == meanwhile and set(meanwhile) - set(before) <= {
            "docs",
            "docs/agents",
            "docs/agents/record-adr.md",
        }
        assert (new_project / "AGENTS.md").read_text() == "# Ours\n" and not (new_project / FILE_NAME).exists()


class TestCopilotReviewOfPR6:
    """Copilot's review of PR #6 (docs/reviews/phase-3.md), each reproduced before the fix."""

    def test_a_link_out_of_the_repository_is_never_written_through(self, new_project: Path, tmp_path_factory):
        outside = tmp_path_factory.mktemp("outside")
        (outside / "theirs.md").write_text("# Theirs\n")
        (new_project / "AGENTS.md").symlink_to(outside / "theirs.md")
        (outside / "agents").mkdir()
        (new_project / "docs").mkdir()
        (new_project / "docs/agents").symlink_to(outside / "agents", target_is_directory=True)
        plan = init(new_project, hosts=[])
        assert verbs(plan)["AGENTS.md"] == KEEP and verbs(plan)["docs/agents/prepare-pr.md"] == KEEP
        assert (outside / "theirs.md").read_text() == "# Theirs\n" and list((outside / "agents").iterdir()) == []

    def test_a_link_that_appears_after_the_plan_stops_init(self, new_project: Path, tmp_path_factory):
        outside = tmp_path_factory.mktemp("outside")
        (outside / "theirs.md").write_text("# Theirs\n")
        make(new_project, {"AGENTS.md": "# Ours\n"})
        plan = make_plan(new_project, hosts=[], today=TODAY)
        (new_project / "AGENTS.md").unlink()
        (new_project / "AGENTS.md").symlink_to(outside / "theirs.md")
        with pytest.raises(InitError, match="out of the repository"):
            apply(plan, new_project)
        assert (outside / "theirs.md").read_text() == "# Theirs\n"

    def test_a_folder_that_became_a_file_stops_init_with_nothing_written(self, new_project: Path):
        make(new_project, {"AGENTS.md": "# Ours\n"})
        plan = make_plan(new_project, hosts=[], today=TODAY)
        make(new_project, {"docs/agents": "now a file\n"})
        with pytest.raises(InitError, match="isn't a folder any more"):
            apply(plan, new_project)
        assert (new_project / "AGENTS.md").read_text() == "# Ours\n" and not (new_project / FILE_NAME).exists()

    @pytest.mark.parametrize("meanwhile", ['# mine\nstandard = 1\nswerepo = "0.0.1"\ncomponents = ["docs"]\n', None])
    def test_a_state_file_changed_after_the_plan_is_never_overwritten(self, new_project: Path, meanwhile):
        if meanwhile is None:  # the other way round: there was one, and it was deleted
            make(new_project, {FILE_NAME: 'standard = 1\nswerepo = "0.0.1"\ncomponents = ["docs"]\n'})
        plan = make_plan(new_project, hosts=[], today=TODAY)
        if meanwhile is None:
            (new_project / FILE_NAME).unlink()
        else:
            make(new_project, {FILE_NAME: meanwhile})
        before = snapshot(new_project)
        with pytest.raises(InitError, match="changed since the plan"):
            apply(plan, new_project)
        assert snapshot(new_project) == before

    def test_a_block_that_would_land_in_an_unclosed_fence_is_not_added(self, new_project: Path):
        make(new_project, {"AGENTS.md": "# Ours\n~~~md\n"})
        for _ in range(2):
            plan = init(new_project, hosts=[])
            action = next(a for a in plan.actions if a.path == "AGENTS.md")
            assert action.verb == KEEP and "unclosed code fence" in action.note
        assert (new_project / "AGENTS.md").read_text() == "# Ours\n~~~md\n"
