"""What dogfooding on an established repository changed (ADR-20261125-5f22): a codebase never linted moves to ruff
gradually, a project without tests is warned, and three smaller fixes."""

import datetime
from pathlib import Path

import pytest
from fake_gh import FakeGh
from repo_helpers import commit, git, git_init, make

from swerepo import ci, privacy
from swerepo.check import MISSING, run_check
from swerepo.init import DEPENDENCY_GRAPH_NOTE, NOTE, apply, make_plan
from swerepo.render import TemplateStore
from swerepo.state import State

TODAY = datetime.date(2026, 11, 25)
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
SLUG = "acme/app"
WORKFLOW = ".github/workflows/swerepo-ci.yml"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = git_init(tmp_path / "app")
    make(root, {"pyproject.toml": PYPROJECT, "uv.lock": "version = 1\n", "tests/test_app.py": "def test_x(): pass\n"})
    return root


def ci_plan(root: Path, **kwargs):
    return make_plan(root, today=TODAY, only=["ci"], hosts=[], **kwargs)


def notes(plan, component: str = "ci") -> list[str]:
    return [a.note for a in plan.actions if a.component == component and a.verb == NOTE]


class TestNeverLinted:
    def test_an_existing_codebase_moves_to_ruff_gradually(self, project: Path):
        commit(project, "history")  # a repository with commits: an existing codebase
        found = ci_plan(project)
        workflow = next(a for a in found.actions if a.path == WORKFLOW)
        assert "lint: ruff on changed files" in workflow.note
        assert "ruff on the changed files" in (workflow.content or "")  # the gradual job, not ruff on everything
        assert any(n.startswith("lint: this codebase has never been linted") for n in notes(found))
        apply(found, project)
        assert State.load(project).values["lint"] == "gradual"
        assert not ci_plan(project).changes  # recorded: a second run keeps it

    def test_a_new_project_gets_full_ruff(self, project: Path):
        found = ci_plan(project)  # no commits yet
        workflow = next(a for a in found.actions if a.path == WORKFLOW)
        assert "lint: ruff" in workflow.note and "changed files" not in workflow.note
        assert "ruff on the changed files" not in (workflow.content or "")
        assert not any("never been linted" in n for n in notes(found))

    def test_a_recorded_choice_is_kept(self, project: Path):
        apply(ci_plan(project), project)  # full ruff, before any commit
        commit(project, "set up")
        assert State.load(project).values["lint"] == "ruff" and not ci_plan(project).changes

    def test_a_project_with_its_own_linter_is_still_asked(self, project: Path):
        make(project, {".flake8": "[flake8]\nmax-line-length = 100\n"})
        commit(project, "history")
        found = ci_plan(project)
        assert found.lint_question and not any("never been linted" in n for n in notes(found))


class TestNoTests:
    @pytest.mark.parametrize(
        ("files", "found"),
        [
            (["tests/test_app.py"], True),
            (["app/core_test.py"], True),
            (["test_main.py"], True),
            (["app/main.py", "tests/conftest.py", "tests/helpers.py", "testing.py"], False),
            ([], False),
        ],
    )
    def test_what_counts_as_a_test(self, files: list[str], found: bool):
        assert ci.has_tests(files) is found
        assert ci.has_tests(["services/api/tests/test_x.py"], "services/api") and not ci.has_tests(files, "web")

    def test_the_plan_and_check_warn_and_never_block(self, project: Path):
        (project / "tests" / "test_app.py").unlink()
        found = ci_plan(project)
        assert any(n.startswith("no tests yet: the test job fails until there is one") for n in notes(found))
        apply(found, project)
        report = run_check(project, only=["ci"])
        finding = next(f for f in report.findings if f.item == "ci.tests")
        assert finding.status == MISSING and not finding.blocking and "prepare-pr.md" in finding.message
        make(project, {"tests/test_first.py": "def test_first(): pass\n"})
        assert not any(f.item == "ci.tests" for f in run_check(project, only=["ci"]).findings)

    def test_the_runbook_tells_agents_to_write_one_never_to_mask_the_job(self):
        runbook = TemplateStore().latest("agents", "prepare-pr")
        assert runbook.id == "agents/prepare-pr@3"
        text = runbook.render({"test_inline": "`uv run pytest`", "progress_dir": "docs/progress", "spec": "SPEC.md"})
        assert "no tests collected" in text and "write a real test" in text
        assert "Never make the test job pass by masking it, skipping it or removing it" in text


class TestSmallerFixes:
    def test_the_tools_note_names_an_extra_uv_sync_skips(self, tmp_path: Path):
        root = git_init(tmp_path / "lib")
        extra = '[project]\nname = "lib"\nrequires-python = ">=3.12"\n'
        extra += '[project.optional-dependencies]\ndev = ["pytest>=8"]\n'
        make(root, {"pyproject.toml": extra, "tests/test_x.py": "def test_x(): pass\n"})
        note = next(n for n in notes(ci_plan(root)) if n.startswith("not among the project's installed"))
        assert "pytest is in the optional extra `dev`, which uv sync doesn't install" in note
        assert ci.extras_holding(root) == {"pytest": "dev"}

    def test_a_privacy_finding_says_how_to_clear_a_placeholder_never_for_a_key(self, project: Path):
        at = "@"  # assembled at run time, so this file holds no address
        make(project, {"tests/fixture.md": "contact alice" + at + "b.com\n"})
        found = make_plan(project, today=TODAY, only=["security"], hosts=[], contact="github")
        note = next(n for n in notes(found, "security") if n.startswith("privacy scan:"))
        assert privacy.NOT_PERSONAL in note and "b.com" not in note
        key = type("Hit", (), {"kind": "private key"})()
        assert privacy.how_to_clear([key]) == ""

    def test_the_dependency_graph_is_noted_once(self, project: Path, tmp_path: Path, monkeypatch):
        git(project, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
        fake = FakeGh(tmp_path / "fake-gh", monkeypatch)
        fake.set(f"GET repos/{SLUG}", {"owner": {"login": "dev", "type": "User"}, "allow_merge_commit": True,
                                       "allow_squash_merge": True, "allow_rebase_merge": True,
                                       "delete_branch_on_merge": False, "allow_auto_merge": False})  # fmt: skip
        fake.set(f"GET repos/{SLUG}/rulesets", [])
        fake.save()  # no SBOM answer: the graph is off
        both = make_plan(project, today=TODAY, only=["ci", "github"], hosts=[], code_owner="@dev")
        said = [a.note for a in both.actions if a.verb == NOTE and "dependency graph" in a.note]
        assert len(said) == 1 and "is off" in said[0]
        alone = ci_plan(project)  # without github nothing read the graph: ci's general note stays
        assert DEPENDENCY_GRAPH_NOTE in notes(alone)


class TestGeminiReviewP8G:
    """Gemini's review of the dogfooding fixes, round 1, each reproduced before the fix."""

    def test_g01_tests_pytest_skips_or_wont_look_for_dont_count(self, tmp_path: Path):
        hidden = [".seamspec/tests/test_inv_1.py", "build/test_x.py", "venv/lib/test_y.py", "pkg.egg/test_z.py"]
        assert not ci.has_tests(hidden)  # pytest never descends there by default
        assert not ci.has_tests(["scripts/test_connection.py"], testpaths=["tests"])
        assert ci.has_tests(["tests/unit/test_a.py"], testpaths=["tests"])
        root = tmp_path / "p"
        make(root, {"pyproject.toml": '[project]\nname = "p"\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'})
        assert ci.pytest_testpaths(root) == ["tests"]
        make(root, {"pytest.ini": "[pytest]\ntestpaths = checks\n"})  # pytest.ini is read first
        assert ci.pytest_testpaths(root) == ["checks"]
        assert not ci.project_has_tests(root, ["tests/test_a.py"]) and ci.project_has_tests(root, ["checks/test_a.py"])

    def test_g01_a_listed_project_without_tests_is_warned(self, project: Path):
        make(project, {"services/api/pyproject.toml": PYPROJECT.replace('"app"', '"api"'), "services/api/app.py": ""})
        found = ci_plan(project, projects=["services/api"])
        assert any(n.startswith("services/api/: no tests yet: its test-services-api job") for n in notes(found))
        apply(found, project)
        finding = next(f for f in run_check(project, only=["ci"]).findings if f.item == "ci.tests.services/api")
        assert finding.status == MISSING and not finding.blocking

    def test_g02_the_commands_are_recorded_only_with_the_agents_files(self, project: Path):
        commit(project, "history")
        apply(make_plan(project, today=TODAY, only=["ci", "agents"], hosts=[]), project)  # gradual
        gradual = State.load(project).values["commands"]
        assert "--force-exclude" in (project / "AGENTS.md").read_text()  # the agents run ruff on changed files
        state = State.load(project)
        state.set_value("lint", "ruff")  # the person, after fixing the codebase
        state.save(project)
        apply(make_plan(project, today=TODAY, only=["ci"], hosts=[], update=True), project)
        assert State.load(project).values["commands"] == gradual  # the agents' files still name these
        apply(make_plan(project, today=TODAY, only=["ci", "agents"], hosts=[], update=True), project)
        assert State.load(project).values["commands"] != gradual
        assert "--force-exclude" not in (project / "AGENTS.md").read_text()

    def test_g03_a_listed_project_never_linted_is_said_to_get_full_ruff(self, project: Path):
        make(project, {"services/api/pyproject.toml": PYPROJECT.replace('"app"', '"api"')})
        make(project, {"services/api/tests/test_api.py": "def test_api(): pass\n"})
        commit(project, "history")
        said = [n for n in notes(ci_plan(project, projects=["services/api"])) if n.startswith("services/api/: ruff")]
        assert said and "lint-services-api job fails until its code passes ruff" in said[0]

    def test_g04_no_way_out_with_a_key_among_the_findings(self):
        email, key = (type("Hit", (), {"kind": kind})() for kind in ("email address", "private key"))
        assert privacy.how_to_clear([email]) == privacy.NOT_PERSONAL
        assert privacy.how_to_clear([email, key]) == "" and privacy.how_to_clear([]) == ""

    def test_g05_a_new_repository_set_up_in_stages_stays_new(self, project: Path):
        apply(make_plan(project, today=TODAY, only=["docs", "agents"], hosts=[]), project)  # no commits yet
        commit(project, "docs and agents")
        assert State.load(project).started_new
        found = ci_plan(project)
        workflow = next(a for a in found.actions if a.path == WORKFLOW)
        assert "changed files" not in workflow.note and not any("never been linted" in n for n in notes(found))

    def test_g06_detection_keeps_its_listing_but_json_leaves_it_out(self, project: Path):
        from swerepo.detect import detect

        found = detect(project)
        assert "tests/test_app.py" in found.files and "files" not in found.to_dict()


class TestAppliedForReal:
    """Applying SWERepo to the established repository, step 1 (`docs` and `agents`; ADR-20261125-5f22 point 4)."""

    def test_editors_on_the_command_line_set_and_replace_the_recorded_ones(self, project: Path):
        from typer.testing import CliRunner

        from swerepo.cli import app

        runner = CliRunner()
        first = runner.invoke(app, ["init", "--path", str(project), "--only", "agents", "--editors", "antigravity",
                                    "--yes"])  # fmt: skip
        assert first.exit_code == 0, first.output
        assert State.load(project).hosts == ["antigravity"] and (project / "GEMINI.md").is_file()
        assert not (project / "CLAUDE.md").exists()
        same = runner.invoke(app, ["init", "--path", str(project), "--only", "agents", "--editors", "antigravity",
                                   "--dry-run"])  # fmt: skip
        assert "Nothing to do." in same.output
        added = runner.invoke(app, ["update", "--path", str(project), "--only", "agents", "--editors",
                                    "claude,antigravity", "--yes"])  # fmt: skip
        assert added.exit_code == 0, added.output
        assert "editors: antigravity → claude, antigravity" in added.output
        assert set(State.load(project).hosts) == {"claude", "antigravity"} and (project / "CLAUDE.md").is_file()
        reordered = make_plan(project, today=TODAY, only=["agents"], hosts=["antigravity", "claude"])
        assert not reordered.changes  # the same editors in another order change nothing
        none = make_plan(project, today=TODAY, only=["agents"], hosts=[])
        assert any(a.note.startswith("editors: claude, antigravity → none") for a in none.actions if a.verb == NOTE)
        cleared = runner.invoke(app, ["update", "--path", str(project), "--only", "agents", "--editors", "none",
                                      "--yes"])  # fmt: skip
        assert cleared.exit_code == 0 and State.load(project).hosts == [], cleared.output  # `none`: no editors
        bad = runner.invoke(app, ["init", "--path", str(project), "--editors", "emacs", "--dry-run"])
        assert bad.exit_code == 2 and "unknown editor emacs" in bad.output

    def test_the_agents_commands_must_run(self, tmp_path: Path):
        root = git_init(tmp_path / "lib")
        extra = '[project]\nname = "lib"\nrequires-python = ">=3.12"\n'
        extra += '[project.optional-dependencies]\ndev = ["pytest>=8"]\n'
        make(root, {"pyproject.toml": extra, "tests/test_x.py": "def test_x(): pass\n"})
        alone = make_plan(root, today=TODAY, only=["agents"], hosts=[])
        said = [n for n in notes(alone, "agents") if n.startswith("AGENTS.md's commands won't run yet")]
        assert said and "pytest, ruff" in said[0] and "optional extra `dev`" in said[0]
        both = make_plan(root, today=TODAY, only=["ci", "agents"], hosts=[])
        assert not [n for n in notes(both, "agents") if n.startswith("AGENTS.md's commands")]  # ci says it once
        apply(alone, root)
        assert not [n for n in notes(make_plan(root, today=TODAY, only=["agents"], hosts=[]), "agents")
                    if n.startswith("AGENTS.md's commands")]  # fmt: skip

    def test_the_next_step_says_a_branch(self, project: Path):
        from typer.testing import CliRunner

        from swerepo.cli import app

        done = CliRunner().invoke(app, ["init", "--path", str(project), "--only", "docs", "--yes"])
        assert "commit them on a branch," in done.output and "new branch" not in done.output


def cli(*args: str, terminal: bool = False, monkeypatch=None, given: str | None = None):
    from typer.testing import CliRunner

    from swerepo import cli as module
    from swerepo.cli import app

    if monkeypatch is not None:
        monkeypatch.setattr(module, "_interactive", lambda: terminal)
    return CliRunner().invoke(app, list(args), input=given)


class TestGeminiReviewP8A:
    """The design review of the dogfooding follow-up (CODE_REVIEW.md, P8-A01 to P8-A07)."""

    def test_a01_editors_need_the_agents_component(self, project: Path):
        done = cli("init", "--path", str(project), "--only", "docs,agents", "--editors", "antigravity", "--yes")
        assert done.exit_code == 0, done.output
        for command in (["update", "--only", "docs"], ["init", "--only", "ci"]):
            wrong = cli(*command, "--path", str(project), "--editors", "claude,antigravity", "--yes")
            assert wrong.exit_code == 2 and "needs the agents component" in wrong.output, wrong.output
        assert State.load(project).hosts == ["antigravity"]  # nothing recorded
        assert run_check(project, only=["agents"]).exit_code == 0
        apply(make_plan(project, today=TODAY, only=["docs"], hosts=["claude"]), project)  # editors without agents
        assert State.load(project).hosts == ["antigravity"]  # are recorded only with their files

    def test_a01_a_dropped_editors_file_stays_and_check_lets_it_go(self, project: Path):
        cli("init", "--path", str(project), "--only", "agents", "--editors", "claude,antigravity", "--yes")
        text = (project / "CLAUDE.md").read_text()
        dropped = cli("update", "--path", str(project), "--only", "agents", "--editors", "antigravity", "--yes")
        assert dropped.exit_code == 0 and "CLAUDE.md (yours now: its editor isn't chosen)" in dropped.output
        assert (project / "CLAUDE.md").read_text() == text and "CLAUDE.md" not in State.load(project).blocks()
        (project / "CLAUDE.md").write_text(text)
        again = cli("update", "--path", str(project), "--only", "agents", "--editors", "claude,antigravity", "--yes")
        assert again.exit_code == 0 and "adopt" in again.output and "managed again" in again.output
        assert (project / "CLAUDE.md").read_text() == text and "CLAUDE.md" in State.load(project).blocks()
        cli("update", "--path", str(project), "--only", "agents", "--editors", "antigravity", "--yes")
        (project / "CLAUDE.md").unlink()
        assert run_check(project, only=["agents"]).exit_code == 0  # its file is the person's: deleting it is fine

    def test_a01_a_dropped_editors_record_doesnt_fail_check_before_the_next_run(self, project: Path):
        cli("init", "--path", str(project), "--only", "agents", "--editors", "claude", "--yes")
        state = State.load(project)
        state.set_hosts([])  # an editor dropped by hand: the record of CLAUDE.md is still there
        state.save(project)
        (project / "CLAUDE.md").unlink()
        assert run_check(project, only=["agents"]).exit_code == 0

    @pytest.mark.parametrize(
        ("given", "said"),
        [("", "name the editors"), (",", "name the editors"), ("none,claude", "can't go with others")],
    )
    def test_a01_wrong_editor_lists_are_wrong_usage(self, project: Path, given: str, said: str):
        wrong = cli("init", "--path", str(project), "--only", "agents", "--editors", given, "--dry-run")
        assert wrong.exit_code == 2 and said in wrong.output

    def test_a01_repeated_editors_count_once(self, project: Path):
        done = cli("init", "--path", str(project), "--only", "agents", "--editors", "claude, claude", "--yes")
        assert done.exit_code == 0 and "(editors: Claude Code)" in done.output
        assert State.load(project).hosts == ["claude"]

    def test_a01_the_terminal_question_asks_again_after_a_wrong_answer(self, project: Path, monkeypatch):
        done = cli("init", "--path", str(project), "--only", "agents", terminal=True, monkeypatch=monkeypatch,
                   given="none,claude\nclaude,claude\ny\n")  # fmt: skip
        assert done.exit_code == 0, done.output
        assert "can't go with others" in done.output and State.load(project).hosts == ["claude"]

    def test_a01_an_added_editor_runs_seamspec_init_for_it(self, project: Path, monkeypatch):
        from swerepo import seamspec_component as ssc
        from swerepo.init import RUN, WAITING

        make(project, {".seamspec/config.toml": 'mode = "enforced"\n'})
        cli("init", "--path", str(project), "--only", "agents", "--editors", "claude", "--yes")
        monkeypatch.setattr(ssc, "command", lambda: "seamspec")
        monkeypatch.setattr(ssc, "installed_version", lambda root: None)
        monkeypatch.setattr(ssc.Ledger, "read", classmethod(lambda cls, root: _ledger()))
        added = make_plan(project, today=TODAY, only=["agents", "seamspec"], hosts=["claude", "antigravity"],
                          terminal=True)  # fmt: skip
        assert added.seamspec_run == ["init", "--ci", "--hosts", "antigravity"]
        assert any(a.verb == RUN for a in added.actions if a.component == "seamspec")
        waits = make_plan(project, today=TODAY, only=["agents", "seamspec"], hosts=["claude", "antigravity"])
        assert waits.seamspec_run is None and any(a.verb == WAITING for a in waits.actions)
        same = make_plan(project, today=TODAY, only=["agents", "seamspec"], hosts=["claude"], terminal=True)
        assert same.seamspec_run is None  # no editor added: SeamSpec isn't asked again

    def test_a08_editors_without_agents_are_wrong_usage_even_with_seamspec(self, project: Path):
        cli("init", "--path", str(project), "--only", "agents", "--editors", "claude", "--yes")
        wrong = cli("init", "--path", str(project), "--only", "seamspec", "--editors", "cursor", "--dry-run")
        assert wrong.exit_code == 2 and "needs the agents component" in wrong.output
        assert "recorded in .swerepo.toml" not in wrong.output and State.load(project).hosts == ["claude"]

    def test_a08_an_editor_added_where_none_were_recorded_runs_seamspec_init(self, project: Path, monkeypatch):
        from swerepo import seamspec_component as ssc

        cli("init", "--path", str(project), "--only", "docs", "--yes")  # set up, but no editors recorded
        assert not State.load(project).hosts_chosen
        monkeypatch.setattr(ssc, "command", lambda: "seamspec")
        monkeypatch.setattr(ssc, "installed_version", lambda root: None)
        monkeypatch.setattr(ssc.Ledger, "read", classmethod(lambda cls, root: _ledger()))
        added = make_plan(project, today=TODAY, only=["agents", "seamspec"], hosts=["antigravity"], terminal=True)
        assert added.seamspec_run == ["init", "--ci", "--hosts", "antigravity"]
        make(project, {".agents/rules.md": "x\n"})  # Antigravity detected: SeamSpec was set up with it
        detected = make_plan(project, today=TODAY, only=["agents", "seamspec"], terminal=True)
        assert detected.hosts == ["antigravity"] and detected.seamspec_run is None

    def test_a02_a07_the_agents_note_follows_what_agents_md_runs(self, tmp_path: Path):
        bare = '[project]\nname = "lib"\nrequires-python = ">=3.12"\n'

        def said(root: Path, only: list[str]) -> list[str]:
            found = make_plan(root, today=TODAY, only=only, hosts=[])
            return [a.note for a in found.actions if a.verb == NOTE and "not among" in a.note]

        root = git_init(tmp_path / "plain")
        make(root, {"pyproject.toml": bare})
        assert len(said(root, ["agents"])) == 1 and len(said(root, ["ci", "agents"])) == 1  # said once, either way
        apply(make_plan(root, today=TODAY, only=["ci"], hosts=[]), root)  # the workflow now kept: ci says nothing
        kept = said(root, ["ci", "agents"])
        assert len(kept) == 1 and kept[0].startswith("AGENTS.md's commands won't run yet")
        made = git_init(tmp_path / "make")
        make(made, {"pyproject.toml": bare, "Makefile": "install:\n\tuv sync\ntest:\n\tpytest\nlint:\n\truff .\n"})
        assert said(made, ["agents"]) == []  # make runs its own tools
        tested = git_init(tmp_path / "make-test")
        make(tested, {"pyproject.toml": bare, "Makefile": "test:\n\tpytest\n"})
        only_ruff = said(tested, ["agents"])
        assert len(only_ruff) == 1 and "ruff" in only_ruff[0] and "pytest" not in only_ruff[0]
        unbuilt = git_init(tmp_path / "no-project")
        make(unbuilt, {"pyproject.toml": '[build-system]\nrequires = ["uv_build"]\n'})
        assert said(unbuilt, ["agents"]) == []  # no [project]: uv sync can't install it, so no uv add advice
        poetry = git_init(tmp_path / "poetry")
        make(poetry, {"pyproject.toml": bare, "poetry.lock": ""})
        assert said(poetry, ["agents"]) == []  # uv sync doesn't install it


def _ledger():
    from swerepo import seamspec_component as ssc

    ledger = ssc.Ledger.__new__(ssc.Ledger)
    for name, value in (("set_up", True), ("mode", "enforced"), ("rules", {})):
        object.__setattr__(ledger, name, value)
    return ledger


def _github(project: Path, tmp_path: Path, monkeypatch) -> FakeGh:
    git(project, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
    fake = FakeGh(tmp_path / "fake-gh", monkeypatch)
    fake.set(f"GET repos/{SLUG}", {"owner": {"login": "dev", "type": "User"}, "allow_merge_commit": True})
    fake.set(f"GET repos/{SLUG}/rulesets", [])
    fake.set(f"GET repos/{SLUG}/dependency-graph/sbom", {"sbom": {}})
    fake.set(f"POST repos/{SLUG}/rulesets", {"id": 9})
    fake.set(f"PATCH repos/{SLUG}", {})
    return fake


def _changed(fake: FakeGh) -> list[str]:
    return [m for m in fake.methods() if m != "GET"]


class TestApplyGitHub:
    """#9: GitHub's settings change only when asked for by name (ADR-20261125-5f22 point 5)."""

    def test_yes_alone_writes_the_files_and_holds_the_settings(self, project: Path, tmp_path: Path, monkeypatch):
        fake = _github(project, tmp_path, monkeypatch)
        first = cli("init", "--path", str(project), "--only", "github", "--code-owner", "@dev", "--yes")
        assert first.exit_code == 0, first.output
        assert (project / ".github/swerepo/ruleset.json").is_file() and _changed(fake) == []
        assert "needs --apply-github" in first.output and "--yes --apply-github" in first.output
        assert State.load(project).github["applied"] is False
        again = cli("init", "--path", str(project), "--only", "github", "--yes")  # the second run (de_00bb3c21)
        assert again.exit_code == 0 and "Nothing to do." in again.output and _changed(fake) == []
        update = cli("update", "--path", str(project), "--only", "github", "--yes")
        assert update.exit_code == 0 and _changed(fake) == []
        report = run_check(project, only=["github"], read_github=True)
        assert any(f.fix == "apply-github" for f in report.findings if f.blocking)
        assert "--apply-github" in (report.next_step() or "") and "swerepo init --only github" in report.next_step()

    def test_apply_github_without_yes_or_a_terminal_changes_nothing(self, project: Path, tmp_path, monkeypatch):
        fake = _github(project, tmp_path, monkeypatch)
        cli("init", "--path", str(project), "--only", "github", "--code-owner", "@dev", "--yes")
        for command in ("init", "update"):
            stopped = cli(command, "--path", str(project), "--only", "github", "--apply-github")
            assert stopped.exit_code == 2 and _changed(fake) == [], stopped.output

    @pytest.mark.parametrize("command", ["init", "update"])
    def test_yes_with_apply_github_applies_both(self, project: Path, tmp_path, monkeypatch, command: str):
        fake = _github(project, tmp_path, monkeypatch)
        cli("init", "--path", str(project), "--only", "github", "--code-owner", "@dev", "--yes")
        done = cli(command, "--path", str(project), "--only", "github", "--yes", "--apply-github")
        assert done.exit_code == 0, done.output
        assert sorted(_changed(fake)) == ["PATCH", "POST"] and State.load(project).github["applied"] is True

    def test_a_terminal_shows_each_change_and_asks(self, project: Path, tmp_path: Path, monkeypatch):
        fake = _github(project, tmp_path, monkeypatch)
        done = cli("init", "--path", str(project), "--only", "github", "--code-owner", "@dev",
                   terminal=True, monkeypatch=monkeypatch, given="\ny\nn\nn\n")  # fmt: skip
        assert done.exit_code == 0, done.output
        assert 'Apply ruleset "swerepo" on the default branch?' in done.output and '"enforcement"' in done.output
        assert _changed(fake) == [] and State.load(project).github["applied"] is False


class TestForeignTables:
    """#10: a table another tool appends inside SWERepo's pyproject.toml block (review P8-A04)."""

    BARE = '[project]\nname = "app"\nrequires-python = ">=3.12"\ndependencies = []\n'

    def _inside(self, root: Path, table: str) -> str:
        text = (root / "pyproject.toml").read_text()
        end = text.index("# swerepo:end")
        text = text[:end] + table + text[end:]
        (root / "pyproject.toml").write_text(text)
        return text

    def test_uv_adds_inside_the_block(self, tmp_path: Path):
        root = git_init(tmp_path / "app")
        make(root, {"pyproject.toml": self.BARE, "tests/test_x.py": "def test_x(): pass\n"})
        apply(ci_plan(root), root)
        text = self._inside(root, '\n[dependency-groups]\ndev = ["pytest>=8", "ruff>=0.6"]\n')
        found = [f for f in run_check(root, only=["ci"]).findings if f.path == "pyproject.toml"]
        assert found[0].status == "changed" and "[dependency-groups]" in found[0].message
        assert "move it above # swerepo:begin" in found[0].message
        updated = cli("update", "--path", str(root), "--only", "ci", "--yes", "--merge")
        assert updated.exit_code == 0 and (root / "pyproject.toml").read_text() == text
        assert "Nothing to show" in cli("diff", "--path", str(root)).output  # never offered for deletion
        assert {"pytest", "ruff"} <= ci.installed_dependencies(root)  # read from the whole file
        assert not [n for n in notes(ci_plan(root)) if "not among" in n]

    def test_another_tools_table_and_a_broken_block(self, tmp_path: Path):
        root = git_init(tmp_path / "app")
        make(root, {"pyproject.toml": self.BARE})
        apply(ci_plan(root), root)
        before = (root / "pyproject.toml").read_text()
        self._inside(root, "\n[tool.uv]\npackage = false\n")
        assert "[tool.uv] inside SWERepo's block" in next(a.note for a in ci_plan(root).actions
                                                         if a.path == "pyproject.toml")  # fmt: skip
        (root / "pyproject.toml").write_text(before)
        self._inside(root, '\n[tool.ruff.lint]\nselect = ["E"]\n')  # ruff's own table: an ordinary edit
        own = next(f for f in run_check(root, only=["ci"]).findings if f.path == "pyproject.toml")
        assert own.message == "pyproject.toml (SWERepo block) changed by you (kept)"
        (root / "pyproject.toml").write_text(before)
        self._inside(root, "\nnot toml =\n")
        broken = next(f for f in run_check(root, only=["ci"]).findings if f.path == "pyproject.toml")
        assert "isn't valid TOML" in broken.message


class TestNextStep:
    """#11: check's "Next:" names what fixes each gap (review P8-A05)."""

    def test_only_person_side_gaps_get_no_init(self):
        from swerepo.check import APPLY_GITHUB, Finding, Report

        def report(*fixes: str) -> Report:
            found = [Finding("ci", f"x{i}", MISSING, "m", None, True, fix) for i, fix in enumerate(fixes)]
            return Report("app", None, True, ["ci"], found)

        graph = "turn on GitHub's dependency graph (Settings → Advanced Security)"
        assert report(graph, graph).next_step() == graph  # each step once
        assert report("init", graph).next_step() == f"swerepo init --only ci; {graph}"
        assert report("apply-github").next_step() == APPLY_GITHUB
        assert (
            Report("app", None, True, ["ci"], [Finding("ci", "w", MISSING, "m", None, False, graph)]).next_step()
            is None
        )

    def test_privacy_findings_are_the_persons_and_never_quoted(self, project: Path):
        make(project, {"notes.md": "write to someone" + "@" + "gmail.com\n"})
        report = run_check(project, only=["security"])
        scan = next(f for f in report.findings if f.item == "security.privacy-scan")
        assert scan.fix == "clear the privacy findings (swerepo privacy)"
        assert "gmail" not in (report.next_step() or "") and "clear the privacy findings" in report.next_step()

    def test_the_json_carries_the_fix(self, project: Path):
        done = cli("check", "--path", str(project), "--only", "docs", "--json")
        import json

        findings = json.loads(done.output)["findings"]
        assert findings and all("fix" in f for f in findings)


class TestGeminiReviewCode:
    """The code review of the dogfooding follow-up (CODE_REVIEW.md round 3, P8-A08 to P8-A10)."""

    def test_a09_failing_pull_request_rules_name_the_persons_step(self, tmp_path: Path):
        root = git_init(tmp_path / "app")
        make(root, {"pyproject.toml": PYPROJECT, "docs/progress/20260101-start.md": "x\n", "app.py": "x = 1\n",
                    ".swerepo.toml": "standard = 1\n[pr]\nenforce = true\n"})  # fmt: skip
        commit(root, "start")
        git(root, "checkout", "-q", "-b", "feature")
        make(root, {"app.py": "x = 2\n", ".github/workflows/new.yml": "jobs: {}\n",
                    "pyproject.toml": PYPROJECT.replace('"ruff"]', '"ruff", "httpx"]')})  # fmt: skip
        report = run_check(root, only=["docs"], base="main")
        pr = {f.item: f for f in report.findings if f.component == "pr" and f.blocking}
        assert set(pr) >= {"pr.progress", "pr.workflows"} and report.exit_code == 1
        assert all(f.fix != "init" for f in pr.values())
        step = report.next_step() or ""
        assert "add a progress entry" in step and "record an ADR (swerepo adr new)" in step
        assert step.count("record an ADR") == 1  # each step once

    @pytest.mark.parametrize("files", [{}, {"pyproject.toml": PYPROJECT, "poetry.lock": ""}])
    def test_a09_ci_init_cant_write_isnt_suggested(self, tmp_path: Path, files: dict):
        root = git_init(tmp_path / "app")
        make(root, files)
        report = run_check(root, only=["ci"])
        gaps = {f.item: f.fix for f in report.findings if f.blocking}
        assert set(gaps) == {"ci.workflow", "ci.linter"} and "init" not in gaps.values()
        assert "swerepo init --only ci --dry-run says why" in (report.next_step() or "")
        assert not (report.next_step() or "").startswith("swerepo init --only ci")

    def test_a09_an_unpinned_seamspec_workflow_and_an_edited_adr_readme(self, project: Path):
        from swerepo import seamspec_component as ssc

        make(project, {".seamspec/config.toml": 'mode = "enforced"\n',
                       ssc.WORKFLOW: "jobs:\n  x:\n    steps:\n      - uses: actions/checkout@v4\n"})  # fmt: skip
        pinned = [f for f in run_check(project, only=["seamspec"]).findings if f.item == "seamspec.workflow"]
        assert pinned and pinned[0].fix.endswith("pin them, or delete it and run swerepo init --only seamspec")
        cli("init", "--path", str(project), "--only", "docs", "--yes")
        (project / "docs/adr/README.md").write_text("# Decisions\n")  # SWERepo's README, edited: markers gone
        index = next(f for f in run_check(project, only=["docs"]).findings if f.item == "docs.adr-index")
        assert index.fix.startswith("put the ADR index markers back")
        fresh = git_init(project.parent / "fresh")  # not set up: init adopts the folder, so init is right
        make(fresh, {"docs/adr/README.md": "# Decisions\n", "docs/adr/0001-x.md": "x\n"})
        adr = [f for f in run_check(fresh, only=["docs"]).findings if f.item == "docs.adr-index"]
        assert all(f.fix == "init" for f in adr)


class TestCopilotReviewPR23:
    """Copilot's review of PR #23."""

    def test_testpaths_set_in_swerepos_block_count(self, tmp_path: Path):
        root = git_init(tmp_path / "app")
        make(root, {"pyproject.toml": '[project]\nname = "app"\nrequires-python = ">=3.12"\n',
                    "tests/conftest.py": "", "scripts/test_connection.py": "def test_x(): pass\n"})  # fmt: skip
        apply(ci_plan(root), root)
        text = (root / "pyproject.toml").read_text()
        assert "[tool.pytest.ini_options]\n" in text
        text = text.replace("[tool.pytest.ini_options]\n", '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
        (root / "pyproject.toml").write_text(text)  # a person's edit inside SWERepo's block
        assert ci.pytest_testpaths(root) == ["tests"]
        assert not ci.project_has_tests(root, ["tests/conftest.py", "scripts/test_connection.py"])
        tests = next(f for f in run_check(root, only=["ci"]).findings if f.item == "ci.tests")
        assert tests.status == MISSING and not tests.blocking

    def test_commands_move_on_only_with_the_file_that_names_them(self, project: Path):
        cli("init", "--path", str(project), "--only", "agents", "--editors", "none", "--yes")
        before = State.load(project).values["commands"]
        text = (project / "AGENTS.md").read_text()
        (project / "AGENTS.md").write_text(text.replace("## Working rules", "## Working rules (ours)"))
        make(project, {"Makefile": "test:\n\tuv run pytest\n"})
        kept = cli("update", "--path", str(project), "--only", "agents", "--yes")  # no --merge: the block is kept
        assert kept.exit_code == 0, kept.output
        assert "(ours)" in (project / "AGENTS.md").read_text()
        assert State.load(project).values["commands"] == before  # still what AGENTS.md says
        stale = make_plan(project, today=TODAY, only=["agents"], hosts=[])
        assert any("the project's commands changed since they were recorded" in a.note for a in stale.actions)
        merged = cli("update", "--path", str(project), "--only", "agents", "--yes", "--merge")
        assert merged.exit_code == 0 and "make test" in State.load(project).values["commands"], merged.output

    @pytest.mark.parametrize("succeeds", [True, False])
    def test_an_editor_added_while_seamspec_waits_is_set_up_later(self, project: Path, monkeypatch, succeeds: bool):
        import subprocess

        from swerepo import init as init_module
        from swerepo import seamspec_component as ssc
        from swerepo.init import apply_seamspec

        make(project, {".seamspec/config.toml": 'mode = "enforced"\n'})
        cli("init", "--path", str(project), "--only", "agents", "--editors", "claude", "--yes")
        monkeypatch.setattr(ssc, "command", lambda: "seamspec")
        monkeypatch.setattr(ssc, "installed_version", lambda root: None)
        monkeypatch.setattr(ssc.Ledger, "read", classmethod(lambda cls, root: _ledger()))
        waiting = make_plan(project, today=TODAY, only=["agents", "seamspec"], hosts=["claude", "antigravity"])
        assert waiting.seamspec_run is None  # no terminal: seamspec init waits
        apply(waiting, project)
        state = State.load(project)
        assert set(state.hosts) == {"claude", "antigravity"} and state.seamspec_hosts == []  # what SeamSpec has
        later = make_plan(project, today=TODAY, only=["seamspec"], terminal=True)  # a later run, in a terminal
        assert later.seamspec_run == ["init", "--ci", "--hosts", "antigravity"]
        later.seamspec_propose = []
        real = subprocess.run

        def fake_run(args, **kwargs):
            if args[:2] == ["seamspec", "init"]:
                return subprocess.CompletedProcess(args, 0 if succeeds else 1)
            return real(args, **kwargs)

        monkeypatch.setattr(init_module.subprocess, "run", fake_run)
        apply_seamspec(later, project)
        recorded = State.load(project).seamspec_hosts
        assert recorded == (["antigravity"] if succeeds else [])
        again = make_plan(project, today=TODAY, only=["seamspec"], terminal=True)
        assert (again.seamspec_run is None) is succeeds  # set up once it succeeded; asked again until then
