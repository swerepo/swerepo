"""The seamspec component (spec §6.8, §13; ADR-20261124-cd64), against a fake `seamspec` that logs every call."""

import ast
import datetime
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fake_seamspec import FakeSeamspec
from repo_helpers import commit, git_init, make, snapshot
from typer.testing import CliRunner

from swerepo import seamspec_component as ssc
from swerepo.check import CHANGED, MISSING, OK, OUTDATED, UsageError, run_check
from swerepo.cli import app
from swerepo.init import (
    ADOPT,
    CREATE,
    KEEP,
    NOTE,
    PROPOSE,
    RUN,
    WAITING,
    apply,
    apply_seamspec,
    make_plan,
    write_earned_spec,
)
from swerepo.render import TemplateStore
from swerepo.state import State

TODAY = datetime.date(2026, 11, 24)
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
STORE = TemplateStore()
SKIP_SEAMSPEC = ("seamspec",)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository set up by init with every component but seamspec, committed."""
    root = git_init(tmp_path / "app")
    make(root, {"pyproject.toml": PYPROJECT, "uv.lock": "version = 1\n", "CLAUDE.md": "# Mine\n"})
    apply(make_plan(root, today=TODAY, hosts=["claude", "cursor"], code_owner="@dev", contact="github",
                    skip=SKIP_SEAMSPEC), root)  # fmt: skip
    commit(root, "set up")
    return root


@pytest.fixture
def fake(tmp_path: Path, monkeypatch) -> FakeSeamspec:
    return FakeSeamspec(tmp_path / "fake-seamspec", monkeypatch)


def plan(root: Path, **kwargs):
    return make_plan(root, today=TODAY, only=["seamspec"], **kwargs)


def seamspec_actions(found):
    return [a for a in found.actions if a.component == "seamspec"]


def set_up_seamspec(root: Path, rules: dict[str, dict] | None = None, mode: str = "enforced") -> None:
    """SeamSpec as its own `init` leaves it, with these ledger entries."""
    make(root, {".seamspec/config.toml": f'mode = "{mode}"\n'})
    for rule_id, data in (rules or {}).items():
        make(root, {f".seamspec/invariants/{rule_id}.json": json.dumps({"id": rule_id, **data})})


class TestSetUp:
    def test_without_a_terminal_seamspec_waits_and_nothing_runs(self, repo: Path, fake: FakeSeamspec):
        found = plan(repo)
        waiting = [a for a in seamspec_actions(found) if a.verb == WAITING]
        assert waiting and "seamspec init --mode enforced --no-ci --hosts cursor" in waiting[0].note
        assert found.seamspec_run is None and not found.changes and found.state_text is None
        assert all(call["args"] == ["--version"] for call in fake.calls())

    def test_in_a_terminal_it_runs_attached_and_never_with_accept_auto_run(self, repo: Path, fake: FakeSeamspec):
        found = plan(repo, terminal=True)
        assert found.seamspec_run == ["init", "--mode", "enforced", "--no-ci", "--hosts", "cursor"]
        assert any(a.verb == RUN for a in seamspec_actions(found))
        assert sorted(found.seamspec_propose) == ["adr-index", "changelog", "ci-tests", "privacy"]
        apply(found, repo)
        lines, ids = apply_seamspec(found, repo)
        assert "SeamSpec set up." in lines and len(ids) == 4
        assert all("--accept-auto-run" not in call["args"] for call in fake.calls())
        assert "seamspec" in State.load(repo).components
        proposals = [json.loads(call["body"]) for call in fake.calls() if call["args"][:1] == ["propose"]]
        assert {p["origin_ref"] for p in proposals} == {f"swerepo:hygiene/{n}@1" for n in ssc.HYGIENE}
        assert fake.ran("verify") == [["verify", *[a for i in ids for a in ("--proposed", i)]]]

    def test_not_installed_says_how_and_never_installs(self, repo: Path):
        found = plan(repo, terminal=True)
        waiting = [a for a in seamspec_actions(found) if a.verb == WAITING]
        assert waiting and "uv tool install seamspec==" in waiting[0].note and found.seamspec_run is None

    def test_a_failed_setup_proposes_nothing(self, repo: Path, fake: FakeSeamspec):
        fake.set("init_fails", True)
        found = plan(repo, terminal=True)
        apply(found, repo)
        lines, ids = apply_seamspec(found, repo)
        assert ids == [] and "didn't finish" in lines[0] and fake.ran("propose") == []
        assert "seamspec" not in State.load(repo).components

    def test_without_ci_seamspec_gets_swerepos_pinned_workflow_and_ci_flag(self, tmp_path: Path, fake):
        root = git_init(tmp_path / "lib")
        make(root, {"pyproject.toml": PYPROJECT, "uv.lock": "version = 1\n"})
        found = make_plan(root, today=TODAY, only=["docs", "seamspec"], hosts=[], terminal=True)
        workflow = next(a for a in found.actions if a.path == ssc.WORKFLOW)
        assert workflow.verb == CREATE and not ssc.unpinned(workflow.content or "")
        assert "spec --check docs/EARNED_SPEC.md" in (workflow.content or "")  # Copilot on PR #19
        assert "--ci" in (found.seamspec_run or []) and "--no-ci" not in (found.seamspec_run or [])
        assert "ci-tests" not in found.seamspec_propose  # its component isn't set up

    def test_strict_mode_keeps_seamspecs_own_workflow_and_reports_it(self, repo: Path, fake: FakeSeamspec):
        set_up_seamspec(repo, mode="strict")
        unpinned = "jobs:\n  verify:\n    steps:\n      - uses: actions/checkout@v4\n"
        make(repo, {ssc.WORKFLOW: unpinned})
        workflow = next(a for a in plan(repo).actions if a.path == ssc.WORKFLOW)
        assert workflow.verb == KEEP and "workflow audit fails" in workflow.note
        assert (repo / ssc.WORKFLOW).read_text() == unpinned  # never replaced
        state = State.load(repo)
        state.set_components([*state.components, "seamspec"])
        state.save(repo)
        finding = next(f for f in run_check(repo, only=["seamspec"]).findings if f.item == "seamspec.workflow")
        assert finding.status == MISSING and finding.blocking

    def test_strict_mode_in_a_repository_without_its_workflow_gets_swerepos(self, repo: Path, fake):
        set_up_seamspec(repo, mode="strict")
        workflow = next(a for a in plan(repo).actions if a.path == ssc.WORKFLOW)
        assert workflow.verb == CREATE and not ssc.unpinned(workflow.content or "")


class TestHygiene:
    def test_adopted_rules_are_recorded_and_not_proposed(self, repo: Path, fake: FakeSeamspec):
        locked = {"status": "LOCKED", "title": "No personal data", "origin": {"ref": None}}
        set_up_seamspec(repo, {"inv_62d51113": locked})
        found = plan(repo, adopt={"privacy": "inv_62d51113"})
        assert ("seamspec", ADOPT) in [(a.component, a.verb) for a in found.actions]
        assert "privacy" not in found.seamspec_propose
        apply(found, repo)
        assert State.load(repo).seamspec_adopted == {"privacy": "inv_62d51113"}
        assert "privacy" not in plan(repo).seamspec_propose  # remembered

    def test_adopting_needs_a_hygiene_name_and_a_locked_rule(self, repo: Path, fake: FakeSeamspec):
        set_up_seamspec(repo, {"inv_aaaaaaaa": {"status": "PROPOSED", "title": "x", "origin": {}}})
        with pytest.raises(UsageError, match="not a hygiene rule"):
            plan(repo, adopt={"secrets": "inv_aaaaaaaa"})
        with pytest.raises(UsageError, match="not a locked SeamSpec rule"):
            plan(repo, adopt={"privacy": "inv_aaaaaaaa"})

    def test_a_terminal_asks_which_locked_rule_covers_each(self, repo: Path, fake: FakeSeamspec):
        set_up_seamspec(repo, {"inv_62d51113": {"status": "LOCKED", "title": "No personal data", "origin": {}}})
        found = plan(repo, terminal=True)
        assert sorted(found.seamspec_ask) == sorted(found.seamspec_propose)
        assert found.seamspec_locked == [("inv_62d51113", "No personal data")]

    def test_a_declined_rule_is_never_proposed_again(self, repo: Path, fake: FakeSeamspec):
        rejected = {"status": "REJECTED", "title": "x", "origin": {"ref": "swerepo:hygiene/changelog@1"}}
        set_up_seamspec(repo, {"inv_bbbbbbbb": rejected})
        found = plan(repo)
        assert "changelog" not in found.seamspec_propose
        assert any("declined" in a.note for a in seamspec_actions(found))
        state = State.load(repo)
        state.set_components([*state.components, "seamspec"])
        state.save(repo)
        status = next(f for f in run_check(repo, only=["seamspec"]).findings if f.item.endswith("changelog"))
        assert status.status == OK

    def test_a_proposed_rule_waits_and_is_not_proposed_twice(self, repo: Path, fake: FakeSeamspec):
        set_up_seamspec(repo)
        found = plan(repo)
        apply(found, repo)
        apply_seamspec(found, repo)
        again = plan(repo)
        assert again.seamspec_propose == [] and not [a for a in again.actions if a.verb == PROPOSE]
        finding = next(f for f in run_check(repo, only=["seamspec"]).findings if f.item.endswith("privacy"))
        assert finding.status == MISSING and not finding.blocking  # approving is the person's call

    def test_an_untrusted_clone_says_so(self, repo: Path, fake: FakeSeamspec):
        set_up_seamspec(repo)
        fake.set("verify_exit", 1)
        fake.set("verify_says", "This clone is not trusted (new tests). Run `seamspec trust`.")
        found = plan(repo)
        apply(found, repo)
        lines, ids = apply_seamspec(found, repo)
        assert ids and any("isn't trusted" in line for line in lines)

    def test_the_adr_index_rule_covers_the_adopted_adr_folder(self):
        rule = ssc.HYGIENE["adr-index"]
        assert ssc.proposal(rule, "", adr_dir="doc/decisions")["scope_paths"] == ["doc/decisions/", ".swerepo.toml"]
        assert ssc.proposal(ssc.HYGIENE["changelog"], "")["scope_paths"] == ["CHANGELOG.md"]

    def test_rules_follow_their_components(self, tmp_path: Path, fake: FakeSeamspec):
        root = git_init(tmp_path / "docs-only")
        make(root, {"pyproject.toml": PYPROJECT})
        set_up_seamspec(root)
        found = make_plan(root, today=TODAY, only=["docs", "seamspec"], hosts=[])
        assert sorted(found.seamspec_propose) == ["adr-index", "changelog"]


def run_rules(root: Path, folder: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "--noconftest", "-p", "no:cacheprovider", str(folder)],
                          cwd=root, capture_output=True, text=True, check=False)  # fmt: skip


class TestBundledRules:
    @pytest.mark.parametrize("name", list(ssc.HYGIENE))
    def test_standard_library_and_pytest_only(self, name: str):
        code = STORE.get(ssc.HYGIENE[name].template).render({})
        imported = set()
        for node in ast.walk(ast.parse(code)):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        assert imported <= set(sys.stdlib_module_names) | {"pytest"}, imported

    def test_each_passes_on_a_repository_init_sets_up(self, repo: Path):
        """The bundled tests run where SeamSpec keeps a rule's test, with only pytest: they pass on what init wrote."""
        set_up_seamspec(repo)
        folder = repo / ".seamspec" / "tests"
        folder.mkdir(parents=True)
        for name, rule in ssc.HYGIENE.items():
            (folder / f"test_hygiene_{name.replace('-', '_')}.py").write_text(STORE.get(rule.template).render({}))
        commit(repo, "the rules")  # the privacy rule reads tracked files
        done = run_rules(repo, folder)
        assert done.returncode == 0, done.stdout[-2000:]

    def test_p7_f05_privacy_accepts_a_security_policy_where_github_reads_it(self, repo: Path):
        set_up_seamspec(repo)
        folder = repo / ".seamspec" / "tests"
        folder.mkdir(parents=True)
        (folder / "test_privacy.py").write_text(STORE.get(ssc.HYGIENE["privacy"].template).render({}))
        (repo / "SECURITY.md").unlink(missing_ok=True)
        make(repo, {".github/SECURITY.md": "Report to security" + "@" + "mail.test.com\n"})
        commit(repo, "policy")
        assert run_rules(repo, folder).returncode == 0
        make(repo, {"README.md": "Write to alice" + "@" + "mail.test.com\n"})
        commit(repo, "readme")
        assert run_rules(repo, folder).returncode == 1  # anywhere else, still a finding

    def test_ci_tests_fails_when_ci_stops_needing_the_tests(self, repo: Path):
        set_up_seamspec(repo)
        folder = repo / ".seamspec" / "tests"
        folder.mkdir(parents=True)
        (folder / "test_ci.py").write_text(STORE.get(ssc.HYGIENE["ci-tests"].template).render({}))
        workflow = repo / ".github/workflows/swerepo-ci.yml"
        text = workflow.read_text()
        assert "needs: [lint, test, " in text
        workflow.write_text(text.replace("needs: [lint, test, ", "needs: [lint, "))
        done = run_rules(repo, folder)
        assert done.returncode == 1 and "ci-ok doesn't need test" in done.stdout


class TestCheck:
    def seamspec_chosen(self, repo: Path) -> None:
        state = State.load(repo)
        state.set_components([*state.components, "seamspec"])
        state.save(repo)

    def test_ci_mode_runs_no_seamspec_command_and_nothing_is_written(self, repo: Path, fake: FakeSeamspec):
        set_up_seamspec(repo)
        self.seamspec_chosen(repo)
        before = snapshot(repo)
        run_check(repo)
        assert fake.calls() == []  # without local=True: CI, or a library call
        run_check(repo, local=True)
        seen = {tuple(c["args"][:2]) for c in fake.calls()}
        assert seen <= {("--version",), ("doctor", "--json"), ("spec", "--check")}, seen
        assert snapshot(repo) == before

    def test_a_newer_seamspec_installed_is_reported(self, repo: Path, fake: FakeSeamspec):
        set_up_seamspec(repo)
        self.seamspec_chosen(repo)
        fake.set("version", "9.9.9")
        finding = next(f for f in run_check(repo, only=["seamspec"], local=True).findings if f.item == "seamspec.pin")
        assert finding.status == OUTDATED and "swerepo -u --seamspec" in finding.message

    def test_doctor_names_checks_never_messages(self, repo: Path, fake: FakeSeamspec):
        set_up_seamspec(repo)
        self.seamspec_chosen(repo)
        private = "/" + "Users/alice/project"
        fake.set("doctor", {"ok": False, "findings": [{"level": "error", "check": "machine path", "message": private}]})
        report = run_check(repo, only=["seamspec"], local=True)
        finding = next(f for f in report.findings if f.item == "seamspec.doctor")
        assert finding.status == MISSING and "machine path" in finding.message
        assert private not in json.dumps([f.message for f in report.findings])

    def test_strict_codeowners(self, repo: Path, fake: FakeSeamspec):
        set_up_seamspec(repo, mode="strict")
        self.seamspec_chosen(repo)
        codeowners = repo / ".github/CODEOWNERS"
        block = "# seamspec:begin (managed)\n/.seamspec/ @your-team/leads\n# seamspec:end\n"
        codeowners.write_text(codeowners.read_text() + block)
        assert len(ssc.codeowners_problems(codeowners.read_text())) == 2
        found = [f for f in run_check(repo, only=["seamspec"]).findings if f.item == "seamspec.codeowners"]
        assert found and not any(f.blocking for f in found)  # solo mode: a warning
        state = State.load(repo)
        state.set_mode("team")
        state.save(repo)
        found = [f for f in run_check(repo, only=["seamspec"]).findings if f.item == "seamspec.codeowners"]
        assert found and all(f.blocking for f in found)


class TestUpdatePin:
    def seamspec_here(self, repo: Path) -> None:
        set_up_seamspec(repo)
        state = State.load(repo)
        state.set_components([*state.components, "seamspec"])
        state.save(repo)
        commit(repo, "seamspec")

    def test_a_newer_seamspec_moves_the_pin_with_ci_along(self, repo: Path, fake: FakeSeamspec):
        self.seamspec_here(repo)
        fake.set("version", "0.2.0")
        found = make_plan(repo, today=TODAY, update=True, only=["seamspec"])
        workflow = next(a for a in found.actions if a.path == ".github/workflows/swerepo-ci.yml")
        assert "seamspec==0.2.0" in (workflow.content or "")
        apply(found, repo)
        assert State.load(repo).tools["seamspec"] == "0.2.0"
        assert "seamspec==0.2.0" in (repo / ".github/workflows/swerepo-ci.yml").read_text()
        assert all(f.status != CHANGED for f in run_check(repo, only=["ci"]).findings)

    @pytest.mark.parametrize("installed", ["0.1.1", "0.1.2", "0.3.0.dev0"])
    def test_the_pin_never_moves_back_or_to_a_development_build(self, repo: Path, fake: FakeSeamspec, installed):
        self.seamspec_here(repo)
        fake.set("version", installed)
        found = make_plan(repo, today=TODAY, update=True, only=["seamspec"])
        assert not any(a.path == ".github/workflows/swerepo-ci.yml" and a.changes for a in found.actions)

    def test_a_conflict_holds_the_pin_everywhere(self, repo: Path, fake: FakeSeamspec):
        self.seamspec_here(repo)
        workflow = repo / ".github/workflows/swerepo-ci.yml"
        line = next(x for x in workflow.read_text().splitlines() if "seamspec==" in x)
        workflow.write_text(workflow.read_text().replace(line, line + "  # mine"))  # the line the pin changes
        fake.set("version", "0.2.0")
        found = make_plan(repo, today=TODAY, update=True, only=["seamspec"], merge=True)
        apply(found, repo)
        assert State.load(repo).tools["seamspec"] == "0.1.2" and "seamspec==0.2.0" not in workflow.read_text()

    def test_strict_with_ci_holds_both_pins_on_a_conflict(self, repo: Path, fake: FakeSeamspec):
        """Strict mode with ci: both workflows pin SeamSpec. When swerepo-ci.yml can't take the new pin, SWERepo's
        seamspec.yml keeps the old one too, and so does .swerepo.toml (ADR-20261124-cd64 point 8)."""
        set_up_seamspec(repo, mode="strict")
        apply(make_plan(repo, today=TODAY, only=["seamspec"]), repo)  # SWERepo's seamspec.yml, recorded
        assert "seamspec==0.1.2" in (repo / ssc.WORKFLOW).read_text() and "seamspec" in State.load(repo).components
        commit(repo, "strict")
        workflow = repo / ".github/workflows/swerepo-ci.yml"
        line = next(x for x in workflow.read_text().splitlines() if "seamspec==" in x)
        workflow.write_text(workflow.read_text().replace(line, line + "  # mine"))
        fake.set("version", "0.2.0")
        apply(make_plan(repo, today=TODAY, update=True, only=["seamspec"], merge=True), repo)
        assert State.load(repo).tools["seamspec"] == "0.1.2"
        assert "seamspec==0.2.0" not in (repo / ssc.WORKFLOW).read_text()
        assert "seamspec==0.2.0" not in workflow.read_text()

    def test_the_command_line_takes_adopt(self, repo: Path, fake: FakeSeamspec):
        set_up_seamspec(repo, {"inv_62d51113": {"status": "LOCKED", "title": "x", "origin": {}}})
        args = ["init", "--path", str(repo), "--only", "seamspec", "--dry-run", "--adopt", "privacy=inv_62d51113"]
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0 and "adopted (inv_62d51113)" in result.output
        bad = CliRunner().invoke(app, ["init", "--path", str(repo), "--only", "seamspec", "--adopt", "privacy"])
        assert bad.exit_code == 2


class TestReviewP7:
    """Gemini's round 1 of the Phase 7 review."""

    def seamspec_chosen(self, root: Path) -> None:
        state = State.load(root)
        state.set_components([*state.components, "seamspec"])
        state.save(root)

    def test_p7_f01_a_seamspec_yml_that_cant_take_the_pin_holds_it_everywhere(self, repo: Path, fake: FakeSeamspec):
        set_up_seamspec(repo, mode="strict")
        apply(make_plan(repo, today=TODAY, only=["seamspec"]), repo)
        commit(repo, "strict")
        mine = (repo / ssc.WORKFLOW).read_text().replace("timeout-minutes: 15", "timeout-minutes: 20")
        (repo / ssc.WORKFLOW).write_text(mine)  # the person's edit: update waits for --merge
        fake.set("version", "0.2.0")
        found = make_plan(repo, today=TODAY, update=True, only=["seamspec"])
        assert any(a.verb == NOTE and "pin stays at 0.1.2" in a.note for a in found.actions)
        apply(found, repo)
        assert State.load(repo).tools["seamspec"] == "0.1.2"
        assert "seamspec==0.2.0" not in (repo / ".github/workflows/swerepo-ci.yml").read_text()
        assert (repo / ssc.WORKFLOW).read_text() == mine

    def test_p7_f02_seamspec_yml_is_recorded_after_init_only_docs(self, tmp_path: Path, fake: FakeSeamspec):
        root = git_init(tmp_path / "lib")
        make(root, {"pyproject.toml": PYPROJECT, "uv.lock": "version = 1\n"})
        apply(make_plan(root, today=TODAY, only=["docs"], hosts=[]), root)
        found = make_plan(root, today=TODAY, only=["seamspec"], hosts=[], terminal=True)
        apply(found, root)
        apply_seamspec(found, root)
        state = State.load(root)
        assert ssc.WORKFLOW in state.files() and state.tools.get("seamspec") == "0.1.2"
        assert "seamspec" in state.components and state.seamspec_initialised == "0.1.2"
        write_earned_spec(root)
        assert not make_plan(root, today=TODAY, only=["seamspec"], hosts=[]).changes  # SWERepo's own, kept current

    def test_p7_f02_a_fresh_repository_gets_its_state_file(self, tmp_path: Path, fake: FakeSeamspec):
        root = git_init(tmp_path / "fresh")
        make(root, {"pyproject.toml": PYPROJECT, "uv.lock": "version = 1\n"})
        found = make_plan(root, today=TODAY, only=["seamspec"], hosts=[], terminal=True)
        apply(found, root)
        apply_seamspec(found, root)
        state = State.load(root)
        assert state is not None and "seamspec" in state.components and ssc.WORKFLOW in state.files()

    def test_p7_f02_waiting_writes_nothing(self, tmp_path: Path, fake: FakeSeamspec):
        root = git_init(tmp_path / "lib")
        make(root, {"pyproject.toml": PYPROJECT, "uv.lock": "version = 1\n"})
        found = make_plan(root, today=TODAY, only=["seamspec"], hosts=[])  # no terminal: waits
        assert not found.changes and not any(a.path == ssc.WORKFLOW for a in found.actions)

    def test_p7_f03_the_earned_spec_is_never_written_through_a_link(self, repo: Path, fake: FakeSeamspec, tmp_path):
        set_up_seamspec(repo)
        outside = tmp_path / "elsewhere.md"
        (repo / ssc.EARNED_SPEC).unlink(missing_ok=True)
        (repo / ssc.EARNED_SPEC).symlink_to(outside)
        found = plan(repo)
        assert not found.seamspec_spec and any(a.path == ssc.EARNED_SPEC and a.verb == NOTE for a in found.actions)
        assert "not written" in (write_earned_spec(repo) or "")
        assert not outside.exists() and not fake.ran("spec")

    def test_p7_f03_set_up_without_seamspec_installed_waits(self, repo: Path):
        set_up_seamspec(repo)
        found = plan(repo)  # no seamspec command here (conftest)
        assert not [a for a in found.changes if a.component == "seamspec"]
        assert not found.seamspec_propose and not found.seamspec_spec and found.seamspec_run is None
        assert any(a.verb == WAITING and "isn't installed on this machine" in a.note for a in found.actions)

    def test_p7_f06_rules_without_a_subject_are_neither_proposed_nor_reported(self, repo: Path, fake):
        set_up_seamspec(repo)
        self.seamspec_chosen(repo)
        readme = repo / "docs/adr/README.md"
        readme.write_text("# ADRs\n")  # no index markers
        changelog = repo / "CHANGELOG.md"
        changelog.write_text("# Changelog\n")  # no [Unreleased]
        found = plan(repo)
        assert "adr-index" not in found.seamspec_propose and "changelog" not in found.seamspec_propose
        items = {f.item for f in run_check(repo, only=["seamspec"]).findings}
        assert "seamspec.hygiene.adr-index" not in items and "seamspec.hygiene.changelog" not in items
        readme.write_text("# ADRs\n<!-- swerepo:adr-index:begin -->\n")  # broken markers: no subject either
        assert "adr-index" not in plan(repo).seamspec_propose

    def test_p7_f06_a_first_run_follows_the_adopted_adr_folder(self, tmp_path: Path, fake: FakeSeamspec):
        root = git_init(tmp_path / "old")
        index = "# Decisions\n<!-- swerepo:adr-index:begin -->\n<!-- swerepo:adr-index:end -->\n"
        make(root, {"pyproject.toml": PYPROJECT, "doc/decisions/README.md": index,
                    "doc/decisions/0001-start.md": "# Start\n"})  # fmt: skip
        set_up_seamspec(root)
        found = make_plan(root, today=TODAY, only=["docs", "seamspec"], hosts=[])
        assert "adr-index" in found.seamspec_propose

    def test_p7_f06_an_unpinned_seamspec_workflow_is_reported_in_enforced_mode(self, repo: Path, fake):
        set_up_seamspec(repo)
        self.seamspec_chosen(repo)
        make(repo, {ssc.WORKFLOW: "jobs:\n  verify:\n    steps:\n      - uses: actions/checkout@v4\n"})
        assert any(a.verb == NOTE and "workflow audit fails" in a.note for a in plan(repo).actions)
        finding = next(f for f in run_check(repo, only=["seamspec"]).findings if f.item == "seamspec.workflow")
        assert finding.status == MISSING and finding.blocking

    def test_p7_f07_a_terminal_reruns_seamspec_init_after_yes_moved_the_pin(self, repo: Path, fake: FakeSeamspec):
        set_up_seamspec(repo)
        self.seamspec_chosen(repo)
        apply(plan(repo), repo)  # adopted as it is: initialised at 0.1.2
        assert State.load(repo).seamspec_initialised == "0.1.2"
        commit(repo, "seamspec")
        fake.set("version", "0.2.0")
        apply(make_plan(repo, today=TODAY, update=True, only=["seamspec"]), repo)  # --yes: no terminal
        assert State.load(repo).tools["seamspec"] == "0.2.0" and State.load(repo).seamspec_initialised == "0.1.2"
        found = make_plan(repo, today=TODAY, update=True, only=["seamspec"], terminal=True)
        assert found.seamspec_run is not None and "--mode" not in found.seamspec_run  # never lowers the mode
        assert found.seamspec_doctor and any("uv tool upgrade seamspec" in a.note for a in found.actions)
        apply_seamspec(found, repo)
        assert State.load(repo).seamspec_initialised == "0.2.0"
        assert make_plan(repo, today=TODAY, update=True, only=["seamspec"], terminal=True).seamspec_run is None

    def test_p7_f08_json_stays_one_object_and_the_spec_is_written_only_when_planned(self, repo: Path, fake):
        set_up_seamspec(repo)
        result = CliRunner().invoke(app, ["init", "--path", str(repo), "--yes", "--json", "--only", "seamspec"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)  # nothing printed before the object
        assert any("proposed as" in line for line in data["seamspec"])
        (repo / ssc.EARNED_SPEC).unlink(missing_ok=True)
        (repo / ssc.EARNED_SPEC).symlink_to(repo / "elsewhere.md")
        again = CliRunner().invoke(app, ["init", "--path", str(repo), "--yes", "--json", "--only", "seamspec"])
        result = json.loads(again.stdout)  # nothing else to apply: the plan alone, still one object
        assert again.exit_code == 0 and not any("not written" in line for line in result.get("seamspec", []))

    def test_p7_f09_a_first_state_file_from_seamspec_keeps_pr_rules_warn_only(self, tmp_path: Path, fake):
        root = git_init(tmp_path / "old")
        make(root, {"README.md": "# Old project\n"})  # no Python project: no seamspec.yml to write
        commit(root, "history")
        found = make_plan(root, today=TODAY, only=["seamspec"], hosts=[], terminal=True)
        assert found.state_text is None  # nothing for init itself to record
        apply(found, root)
        apply_seamspec(found, root)
        state = State.load(root)
        assert state is not None and "seamspec" in state.components and state.pr_enforce is False

    def test_p7_f10_an_adoption_counts_before_a_declined_proposal(self, repo: Path, fake: FakeSeamspec):
        rejected = {"status": "REJECTED", "title": "x", "origin": {"ref": "swerepo:hygiene/privacy@1"}}
        mine = {"status": "LOCKED", "title": "my privacy rule", "origin": {"ref": None}}
        set_up_seamspec(repo, {"inv_11111111": rejected, "inv_22222222": mine})
        assert ssc.Ledger.read(repo).hygiene("privacy", {"privacy": "inv_22222222"}) == ("adopted", "inv_22222222")
        assert ssc.Ledger.read(repo).hygiene("privacy", {}) == ("declined", "inv_11111111")
        found = plan(repo, adopt={"privacy": "inv_22222222"})
        assert any(a.verb == ADOPT and "inv_22222222" in a.note for a in found.actions)
