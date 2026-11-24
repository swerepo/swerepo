"""`swerepo init` and `check` for the `ci` component (spec §6.2, §6.3, §11; ADR-20261122-4a06)."""

import datetime
import tomllib
from pathlib import Path

import pytest
from repo_helpers import git, git_init, make, snapshot
from typer.testing import CliRunner

from swerepo import ci
from swerepo.check import MISSING, OK, UsageError, run_check, workflow_jobs
from swerepo.cli import app
from swerepo.init import ADD_BLOCK, CREATE, CURRENT, KEEP, NOTE, apply, make_plan
from swerepo.render import TemplateStore
from swerepo.state import State

TODAY = datetime.date(2026, 11, 22)
WORKFLOW = ".github/workflows/swerepo-ci.yml"
PYPROJECT = (
    '[project]\nname = "invoices"\nrequires-python = ">=3.12"\n\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
)


def init(root: Path, **kwargs):
    plan = make_plan(root, today=TODAY, hosts=[], **kwargs)
    apply(plan, root)
    return plan


def action(plan, path: str):
    return next(a for a in plan.actions if a.path == path)


def notes(plan, component: str = "ci") -> list[str]:
    return [a.note for a in plan.actions if a.component == component and a.verb == NOTE]


def ci_findings(root: Path) -> dict:
    return {f.item: f for f in run_check(root, only=["ci"]).findings}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    git_init(tmp_path)
    make(tmp_path, {"pyproject.toml": PYPROJECT, "uv.lock": "version = 1\n"})
    return tmp_path


class TestWorkflow:
    def test_a_new_project_gets_the_workflow_and_settings(self, project: Path):
        plan = init(project, only=["ci"])
        assert action(plan, WORKFLOW).verb == CREATE and action(plan, WORKFLOW).note == "Python 3.12–3.14; lint: ruff"
        text = (project / WORKFLOW).read_text()
        assert 'python: ["3.12", "3.13", "3.14"]' in text and "branches: [main]" in text
        assert text.count("run: uv sync --locked") == 4  # lint, test, test-macos, seamspec
        assert "uv run ruff check ." in text and "uvx zizmor==1.32.0" in text and "@@" not in text
        jobs = workflow_jobs(text)
        assert set(jobs["ci-ok"]) == set(jobs) - {"ci-ok"} and "governance" not in jobs  # unreleased: no governance
        pyproject = (project / "pyproject.toml").read_text()
        assert pyproject.startswith(PYPROJECT) and pyproject.endswith("# swerepo:end\n")  # the person's text first
        data = tomllib.loads(pyproject)
        assert data["tool"]["ruff"]["extend-exclude"] == [".seamspec"] and data["tool"]["pytest"]["ini_options"]

    def test_check_then_finds_ci_complete_and_a_rerun_changes_nothing(self, project: Path):
        init(project, only=["ci"])
        findings = ci_findings(project)
        assert findings.pop("ci.dependency-graph").status == "unknown"  # only gh can tell, and tests never call it
        assert all(f.status == OK for f in findings.values()), [f.message for f in findings.values()]
        assert findings["ci.python-matrix"].message == "tests Python 3.12–3.14, as the project declares"
        before = snapshot(project)
        plan = init(project, only=["ci"])
        assert not plan.changes and action(plan, WORKFLOW).verb == CURRENT and snapshot(project) == before
        assert action(plan, "pyproject.toml").verb == CURRENT  # its own block doesn't count as the person's ruff

    def test_the_rendered_workflow_is_what_was_recorded(self, project: Path):
        init(project, only=["ci"])
        state = State.load(project)
        values = state.values
        inputs = ci.Inputs(values["default_branch"], values["ci_install"], values["python"], values["lint"],
                           swerepo=values["governance_command"], seamspec=state.tools["seamspec"])  # fmt: skip
        template_id, text = ci.render_workflow(TemplateStore(), inputs)
        assert state.files()[WORKFLOW].template == template_id == "ci/workflow@2"
        assert (project / WORKFLOW).read_text() == text  # `update` can rebuild it from what's recorded

    def test_no_lock_file_no_python_declared_and_missing_tools(self, tmp_path: Path):
        git_init(tmp_path)
        make(tmp_path, {"pyproject.toml": '[project]\nname = "x"\n'})
        plan = make_plan(tmp_path, only=["ci"], hosts=[])
        text = action(plan, WORKFLOW).content
        assert "- run: uv sync\n" in text and 'python: ["3.11", "3.12", "3.13", "3.14"]' in text
        found = notes(plan)
        assert any(n.startswith("no requires-python declared") for n in found)
        assert "not among the project's installed dependencies: pytest, ruff (uv add --dev pytest ruff)" in found

    @pytest.mark.parametrize(
        ("files", "reason"),
        [
            ({}, "no pyproject.toml"),
            ({"pyproject.toml": "[tool.poetry]\nname = 'x'\n"}, "has no [project] table"),
            ({"pyproject.toml": '[project]\nname = "x"\n', "poetry.lock": ""}, "Poetry projects come in a later"),
            ({"pyproject.toml": '[project]\nname = "x"\nrequires-python = ">=3.99"\n'}, "allows none of the Python"),
        ],
    )
    def test_projects_it_cant_install_get_no_workflow(self, tmp_path: Path, files: dict, reason: str):
        git_init(tmp_path)
        make(tmp_path, files)
        plan = make_plan(tmp_path, only=["ci"], hosts=[])
        assert not any(a.path == WORKFLOW for a in plan.actions)
        assert any(reason in n for n in notes(plan)) and not plan.changes

    def test_the_default_branch_comes_from_the_remote(self, project: Path):
        git(project, "commit", "-q", "--allow-empty", "-m", "start")
        git(project, "branch", "-m", "trunk")
        assert ci.default_branch(project) == "main"  # trunk isn't a default branch name, and no remote says so
        git(project, "update-ref", "refs/remotes/origin/trunk", "HEAD")
        git(project, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        assert ci.default_branch(project) == "trunk"


class TestGovernance:
    def test_an_unreleased_swerepo_adds_it_only_when_asked(self, project: Path):
        plan = make_plan(project, only=["ci"], hosts=[])
        assert any(n.startswith("governance job: needs a released SWERepo") for n in notes(plan))
        plan = make_plan(project, only=["ci"], hosts=[], with_governance=True)
        text = action(plan, WORKFLOW).content
        assert f"run: {ci.SWEREPO_FROM_GITHUB} check --ci --base" in text
        assert "governance" in workflow_jobs(text)["ci-ok"]

    def test_a_released_swerepo_pins_itself(self, project: Path, monkeypatch):
        monkeypatch.setattr("swerepo.__version__", "1.2.3")
        assert ci.released() and not ci.released("1.2.4.dev0") and not ci.released("1.2.3+local")
        text = action(make_plan(project, only=["ci"], hosts=[]), WORKFLOW).content
        assert 'run: uvx swerepo==1.2.3 check --ci --base "origin/$BASE_REF" --author "$AUTHOR"' in text

    def test_swerepos_own_repository_checks_itself_with_its_checkout(self, project: Path):
        make(project, {"pyproject.toml": PYPROJECT.replace("invoices", "swerepo"), "swerepo/__init__.py": ""})
        text = action(make_plan(project, only=["ci"], hosts=[]), WORKFLOW).content
        assert "run: uv run --locked swerepo check --ci" in text

    def test_the_recorded_choice_is_kept_on_later_runs(self, project: Path):
        init(project, only=["ci"], with_governance=True)
        plan = init(project, only=["ci"])
        assert action(plan, WORKFLOW).verb == CURRENT and not plan.changes


class TestLinters:
    def test_kept_linters_run_in_ci_without_touching_seamspec(self, project: Path):
        make(project, {"setup.cfg": "[flake8]\nmax-line-length = 100\n", "pyproject.toml": PYPROJECT
                       + "\n[tool.black]\nline-length = 100\n"})  # fmt: skip
        plan = make_plan(project, only=["ci"], hosts=[])
        assert plan.lint_question  # the person may choose; the default keeps them
        apply(plan, project)
        text = (project / WORKFLOW).read_text()
        assert "uv run black --check --extend-exclude '\\.seamspec' ." in text
        assert "uv run flake8 --extend-exclude .seamspec" in text and "ruff" not in text
        state = State.load(project)
        assert state.adopted["linters"] == ["black", "flake8"] and state.values["lint"] == "kept"
        assert "[tool.ruff]" not in (project / "pyproject.toml").read_text()  # only pytest's settings
        assert not make_plan(project, only=["ci"], hosts=[]).lint_question  # recorded: not asked again

    def test_moving_to_ruff_gradually(self, project: Path):
        make(project, {"pyproject.toml": PYPROJECT + "\n[tool.black]\nline-length = 100\n"})
        init(project, only=["ci"], lint="gradual")
        text = (project / WORKFLOW).read_text()
        assert "xargs -0 uv run ruff check --force-exclude" in text and "black" not in text
        ruff = tomllib.loads((project / "pyproject.toml").read_text())["tool"]["ruff"]
        assert ruff == {"extend-exclude": [".seamspec"], "line-length": 100}  # black's line length
        assert not init(project, only=["ci"]).changes  # its own [tool.ruff] doesn't make ruff "configured"

    def test_an_existing_ruff_and_pytest_configuration_is_kept(self, project: Path):
        own = PYPROJECT + '\n[tool.ruff]\nline-length = 99\n\n[tool.pytest.ini_options]\naddopts = "-q"\n'
        make(project, {"pyproject.toml": own})
        plan = init(project, only=["ci"])
        assert action(plan, "pyproject.toml").verb == KEEP and (project / "pyproject.toml").read_text() == own

    def test_settings_that_would_clash_are_left_to_the_person(self, project: Path):
        own = 'tool = "not a table"\n' + PYPROJECT
        make(project, {"pyproject.toml": own})
        plan = init(project, only=["ci"])
        found = action(plan, "pyproject.toml")
        assert found.verb == KEEP and "add them yourself" in found.note
        assert (project / "pyproject.toml").read_text() == own

    def test_a_crlf_pyproject_gets_a_crlf_block(self, project: Path):
        (project / "pyproject.toml").write_bytes(PYPROJECT.replace("\n", "\r\n").encode())
        init(project, only=["ci"])
        data = (project / "pyproject.toml").read_bytes()
        assert data.startswith(PYPROJECT.replace("\n", "\r\n").encode()) and b"\n" not in data.replace(b"\r\n", b"")


class TestProjects:
    @pytest.fixture
    def monorepo(self, project: Path) -> Path:
        api = '[project]\nname = "api"\nrequires-python = ">=3.13"\n'
        files = {
            "services/api/pyproject.toml": api,
            "services/api/api/__init__.py": "",
            "tools/gen/pyproject.toml": '[project]\nname = "gen"\n',
            "web/package.json": "{}\n",
        }
        return make(project, files)

    def test_listed_projects_get_their_own_jobs_and_settings(self, monorepo: Path):
        plan = init(monorepo, only=["ci"], projects=["services/api", "tools/gen/"])
        text = (monorepo / WORKFLOW).read_text()
        jobs = workflow_jobs(text)
        assert {"lint-services-api", "test-services-api", "lint-tools-gen", "test-tools-gen"} <= set(jobs["ci-ok"])
        assert "working-directory: services/api" in text and 'python: ["3.13", "3.14"]' in text
        assert action(plan, "services/api/pyproject.toml").verb == ADD_BLOCK
        assert State.load(monorepo).projects_listed == ["services/api", "tools/gen"]
        assert any(n.startswith("web/ isn't covered by ci-ok: a javascript project") for n in notes(plan))
        findings = ci_findings(monorepo)
        assert findings["ci.projects:services/api"].status == OK and findings["ci.projects:web"].status == MISSING
        assert not init(monorepo, only=["ci"]).changes  # the recorded list is used again

    def test_an_unlisted_python_project_is_named(self, monorepo: Path):
        plan = make_plan(monorepo, only=["ci"], hosts=[])
        assert any(n.startswith("services/api/ isn't covered by ci-ok: --projects services/api") for n in notes(plan))

    @pytest.mark.parametrize("given", ["../elsewhere", "/abs/path", "services/../services/api", "web", "missing"])
    def test_projects_must_be_python_folders_inside_the_repository(self, monorepo: Path, given: str):
        with pytest.raises(UsageError, match="--projects"):
            make_plan(monorepo, only=["ci"], hosts=[], projects=[given])

    def test_projects_need_the_ci_component(self, monorepo: Path):
        with pytest.raises(UsageError, match="needs the ci component"):
            make_plan(monorepo, only=["docs"], hosts=[], projects=["services/api"])
        result = CliRunner().invoke(app, ["init", "--path", str(monorepo), "--only", "docs", "--projects", "x"])
        assert result.exit_code == 2


class TestCommandLine:
    def test_flags_and_the_linter_question(self, project: Path, monkeypatch):
        from swerepo import cli

        make(project, {"pyproject.toml": PYPROJECT + "\n[tool.black]\nline-length = 100\n"})
        monkeypatch.setattr(cli, "_interactive", lambda: True)
        runner = CliRunner()
        command = ["init", "--path", str(project), "--only", "ci", "--with-governance"]
        result = runner.invoke(app, command, input="gradual\ny\n")
        assert result.exit_code == 0, result.output
        assert "move to ruff gradually" in result.output
        text = (project / WORKFLOW).read_text()
        assert "ruff check --force-exclude" in text and "governance:" in text

    def test_check_reports_a_missing_workflow_and_matrix_drift(self, project: Path):
        assert ci_findings(project)["ci.workflow"].status == MISSING
        init(project, only=["ci"])
        make(project, {"pyproject.toml": (project / "pyproject.toml").read_text().replace(">=3.12", ">=3.11")})
        finding = ci_findings(project)["ci.python-matrix"]
        assert finding.message == "tests Python 3.12–3.14; the project declares 3.11–3.14: swerepo update"


class TestGeminiReviewRound1:
    """Phase 4 review findings (CODE_REVIEW.md), each reproduced before the fix."""

    def test_p4_f01_a_lock_file_above_counts_only_for_a_workspace_member(self, project: Path):
        make(project, {"services/api/pyproject.toml": '[project]\nname = "api"\n'})
        assert ci.install_command(project, "services/api") == ("uv sync", "")  # standalone: no lock of its own
        make(project, {"pyproject.toml": PYPROJECT + '\n[tool.uv.workspace]\nmembers = ["services/*"]\n'})
        assert ci.install_command(project, "services/api") == ("uv sync --locked", "")  # the workspace's lock
        make(project, {"pyproject.toml": PYPROJECT + '\n[tool.uv.workspace]\nmembers = ["services/*"]\n'
                       'exclude = ["services/api"]\n'})  # fmt: skip
        assert ci.install_command(project, "services/api") == ("uv sync", "")
        make(project, {"services/api/uv.lock": "version = 1\n"})
        assert ci.install_command(project, "services/api") == ("uv sync --locked", "")

    def test_p4_f02_asking_later_rewrites_an_unchanged_workflow_and_keeps_inputs_in_step(self, project: Path):
        make(project, {"services/api/pyproject.toml": '[project]\nname = "api"\n'})
        init(project, only=["ci"])
        plan = init(project, only=["ci"], projects=["services/api"], with_governance=True)
        assert action(plan, WORKFLOW).verb == "rewrite"
        text = (project / WORKFLOW).read_text()
        assert "test-services-api:" in text and "governance:" in text
        state = State.load(project)
        assert state.projects_listed == ["services/api"] and state.values["governance_command"]
        assert state.files()[WORKFLOW].written == state.files()[WORKFLOW].rendered
        assert not init(project, only=["ci"]).changes  # recorded inputs rebuild what was written
        assert ci_findings(project)["ci.projects:services/api"].status == OK

    def test_p4_f02_a_changed_workflow_keeps_its_inputs_and_says_why(self, project: Path):
        make(project, {"services/api/pyproject.toml": '[project]\nname = "api"\n'})
        init(project, only=["ci"])
        (project / WORKFLOW).write_text((project / WORKFLOW).read_text() + "# ours\n")
        before = State.load(project).dumps()
        plan = init(project, only=["ci"], projects=["services/api"])
        assert action(plan, WORKFLOW).verb == "changed" and "waits for it" in action(plan, WORKFLOW).note
        assert State.load(project).projects_listed == [] and "governance_command" in before
        assert (project / WORKFLOW).read_text().endswith("# ours\n")

    def test_p4_f02_a_rewrite_stops_if_the_file_changed_after_the_plan(self, project: Path):
        from swerepo.init import InitError

        make(project, {"services/api/pyproject.toml": '[project]\nname = "api"\n'})
        init(project, only=["ci"])
        plan = make_plan(project, only=["ci"], hosts=[], projects=["services/api"])
        (project / WORKFLOW).write_text("edited meanwhile\n")
        with pytest.raises(InitError, match="changed since the plan"):
            apply(plan, project)
        assert (project / WORKFLOW).read_text() == "edited meanwhile\n"

    def test_p4_f02_the_privacy_command_is_recorded_without_python_versions(self, tmp_path: Path):
        git_init(tmp_path)
        make(tmp_path, {"pyproject.toml": '[project]\nname = "x"\nrequires-python = ">=3.99"\n'})
        init(tmp_path, only=["security"], with_governance=True)
        assert State.load(tmp_path).values["privacy_command"] == ci.SWEREPO_FROM_GITHUB
        assert not init(tmp_path, only=["security"]).changes

    @pytest.mark.parametrize(
        ("table", "key", "value"),
        [
            ("tools", "seamspec", '"0.1.2\\n      - run: curl evil"'),
            ("tools", "seamspec", '"0.1.2 && curl evil"'),
            ("values", "ci_install", '"uv sync && curl evil"'),
            ("values", "governance_command", '"curl evil"'),
        ],
    )
    def test_p4_f03_recorded_values_never_reach_a_workflow_unchecked(self, project: Path, table, key, value):
        make(project, {".swerepo.toml": f'standard = 1\nswerepo = "0.0.1"\n[{table}]\n{key} = {value}\n'})
        try:
            plan = make_plan(project, only=["ci"], hosts=[])
        except Exception as error:  # the state file itself refuses it
            assert "must be a version" in str(error)
            return
        assert "curl evil" not in action(plan, WORKFLOW).content

    def test_p4_f03_unknown_kept_linters_fall_back_to_detection(self, project: Path):
        state = 'standard = 1\nswerepo = "0.0.1"\n[values]\nlint = "kept"\n[adopted]\nlinters = ["mypy"]\n'
        make(project, {".swerepo.toml": state})
        assert "uv run ruff check ." in action(make_plan(project, only=["ci"], hosts=[]), WORKFLOW).content

    def test_p4_f04_a_projects_own_linters_win_over_a_root_ruff(self, project: Path):
        api = '[project]\nname = "api"\n[tool.black]\nline-length = 100\n'
        make(
            project,
            {"pyproject.toml": PYPROJECT + "\n[tool.ruff]\nline-length = 100\n", "services/api/pyproject.toml": api},
        )
        text = action(make_plan(project, only=["ci"], hosts=[], projects=["services/api"]), WORKFLOW).content
        api = text.split("lint-services-api:")[1].split("test-services-api:")[0]
        assert "uv run black --check" in api and "ruff" not in api

    def test_p4_f07_gradual_lists_the_same_commands_on_every_run(self, project: Path):
        make(project, {"pyproject.toml": PYPROJECT + "\n[tool.black]\nline-length = 100\n"})
        apply(make_plan(project, today=TODAY, hosts=[], lint="gradual"), project)
        assert "uv run ruff check --force-exclude <changed .py files>" in (project / "AGENTS.md").read_text()
        again = make_plan(project, today=TODAY, hosts=[])
        assert not again.changes and not any("commands changed" in a.note for a in again.actions)

    def test_p4_f09_the_gradual_step_protects_file_names_and_new_branches(self, project: Path):
        make(project, {"pyproject.toml": PYPROJECT + "\n[tool.black]\nline-length = 100\n"})
        text = action(make_plan(project, only=["ci"], hosts=[], lint="gradual"), WORKFLOW).content
        assert 'ruff check --force-exclude -- < "$RUNNER_TEMP/changed"' in text
        assert '"$BEFORE" != "0000000000000000000000000000000000000000"' in text and "base=HEAD~1" in text


class TestGeminiReviewRound2:
    """Phase 4 review, round 2 (CODE_REVIEW.md)."""

    @pytest.mark.parametrize(
        ("members", "install"),
        [
            ('[".", "services/*"]', "uv sync --locked"),  # "." is the workspace root itself
            ('["services/**"]', "uv sync --locked"),
            ('[""]', "uv sync"),  # matches nothing, and no crash
            ('["/services/*"]', "uv sync"),  # not a relative glob: ignored, no crash
            ('["services/[ab]pi"]', "uv sync --locked"),
        ],
    )
    def test_p4_f10_workspace_globs_never_crash(self, project: Path, members: str, install: str):
        make(project, {"pyproject.toml": PYPROJECT + f"\n[tool.uv.workspace]\nmembers = {members}\n",
                       "services/api/pyproject.toml": '[project]\nname = "api"\n'})  # fmt: skip
        assert ci.install_command(project, "services/api") == (install, "")


class TestCopilotReviewPR8:
    """Copilot's review of PR #8, each reproduced before the fix."""

    def test_a_comment_at_column_0_doesnt_end_jobs(self):
        text = "jobs:\n  a:\n    steps: []\n# more jobs\n  b:\n    steps: []\n  ci-ok:\n    needs: [a]\n"
        assert list(workflow_jobs(text)) == ["a", "b", "ci-ok"]  # so ci-ok's missing `b` is seen

    def test_a_project_named_like_a_fixed_job_is_refused(self, project: Path):
        make(project, {"macos/pyproject.toml": '[project]\nname = "m"\n'})
        with pytest.raises(UsageError, match="test-macos, which swerepo-ci.yml already uses"):
            make_plan(project, only=["ci"], hosts=[], projects=["macos"])

    def test_each_projects_matrix_is_checked_against_its_own_declaration(self, project: Path):
        make(project, {"services/api/pyproject.toml": '[project]\nname = "api"\nrequires-python = ">=3.13"\n'})
        init(project, only=["ci"], projects=["services/api"])
        assert ci_findings(project)["ci.python-matrix:services/api"].status == OK
        make(project, {"services/api/pyproject.toml": '[project]\nname = "api"\nrequires-python = ">=3.12"\n'})
        finding = ci_findings(project)["ci.python-matrix:services/api"]
        assert finding.status == "outdated" and "declares 3.12–3.14" in finding.message
        workflow = project / WORKFLOW  # the root's matrix is read from the test job, not the first one anywhere
        workflow.write_text(workflow.read_text().replace("  lint:\n", '  lint:\n    strategy:\n      matrix:\n'
                                                         '        python: ["3.12", "3.13", "3.14"]\n', 1))  # fmt: skip
        make(project, {"pyproject.toml": PYPROJECT.replace(">=3.12", ">=3.11")})
        assert ci_findings(project)["ci.python-matrix"].status == "outdated"

    @pytest.mark.parametrize(
        ("tables", "missing"),
        [
            ('[project.optional-dependencies]\ndev = ["pytest", "ruff"]\n', True),  # extras: not installed
            ('[dependency-groups]\ntest = ["pytest", "ruff"]\n', True),  # not a default group
            ('[dependency-groups]\ntest = ["pytest", "ruff"]\n[tool.uv]\ndefault-groups = ["test"]\n', False),
            ('[dependency-groups]\ntest = ["pytest", "ruff"]\ndev = [{include-group = "test"}]\n', False),
            ('[tool.uv]\ndev-dependencies = ["pytest", "ruff"]\n', False),
        ],
    )
    def test_tools_count_only_when_uv_sync_installs_them(self, tmp_path: Path, tables: str, missing: bool):
        git_init(tmp_path)
        make(tmp_path, {"pyproject.toml": '[project]\nname = "x"\nrequires-python = ">=3.12"\n' + tables})
        found = notes(make_plan(tmp_path, only=["ci"], hosts=[]))
        assert any("not among the project's installed dependencies" in n for n in found) is missing

    def test_a_security_snapshot_doesnt_decide_cis_first_python_versions(self, project: Path):
        init(project, only=["security"], with_governance=True)
        privacy_before = (project / ".github/workflows/swerepo-privacy.yml").read_text()
        make(project, {"pyproject.toml": PYPROJECT.replace(">=3.12", ">=3.11")})
        plan = init(project, only=["ci", "security"])
        assert 'python: ["3.11", "3.12", "3.13", "3.14"]' in (project / WORKFLOW).read_text()
        assert action(plan, ".github/workflows/swerepo-privacy.yml").verb == CURRENT  # its own snapshot kept
        assert (project / ".github/workflows/swerepo-privacy.yml").read_text() == privacy_before
        values = State.load(project).values
        assert values["python"] == ["3.11", "3.12", "3.13", "3.14"] and values["privacy_python"] == "3.14"

    def test_a_projects_missing_tools_are_named_with_its_folder(self, project: Path):
        make(project, {"services/api/pyproject.toml": '[project]\nname = "api"\n'})
        found = notes(make_plan(project, only=["ci"], hosts=[], projects=["services/api"]))
        assert (
            "not among services/api/'s installed dependencies: pytest, ruff (uv add --dev pytest ruff in services/api)"
            in found
        )

    def test_a_projects_inputs_are_recorded_and_rebuild_its_jobs(self, project: Path):
        make(project, {"services/api/pyproject.toml": '[project]\nname = "api"\nrequires-python = ">=3.13"\n'})
        init(project, only=["ci"], projects=["services/api"])
        recorded = State.load(project).project_inputs["services/api"]
        assert recorded == {"python": ["3.13", "3.14"], "install": "uv sync", "lint": "ruff", "linters": []}
        api = project / "services/api/pyproject.toml"
        api.write_text(api.read_text().replace(">=3.13", ">=3.12"))  # only the declaration changes
        plan = init(project, only=["ci"])
        assert action(plan, WORKFLOW).verb == CURRENT and not plan.changes  # rebuilt from what was recorded
        bad = (project / ".swerepo.toml").read_text().replace('install = "uv sync"\nlint', 'install = "x"\nlint')
        make(project, {".swerepo.toml": bad})  # an invalid recording is never used: detection decides again
        assert ci.Project.from_inputs("services/api", State.load(project).project_inputs["services/api"]) is None
