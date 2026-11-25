"""`swerepo update` (spec §16; ADR-20261124-7afa): the earlier render rebuilt from each record's inputs, untouched
items rewritten, a person's edits merged only with a deliberate yes, conflicts reported and never written."""

import datetime
import json
import sys
import tomllib
from pathlib import Path

import pytest
from fake_gh import FakeGh
from repo_helpers import commit, git, git_init, make
from typer.testing import CliRunner

from swerepo import cli
from swerepo.blocks import file_fingerprint, replace_block_content
from swerepo.cli import app
from swerepo.fingerprint import HASH, HTML, find_block, fingerprint
from swerepo.init import CANT_MERGE, CONFLICT, CURRENT, KEEP, MERGE, REWRITE, apply, make_plan
from swerepo.rebuild import rebuild
from swerepo.render import TemplateStore
from swerepo.state import Record, State

TODAY = datetime.date(2026, 11, 24)
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
STORE = TemplateStore()
WORKFLOW = ".github/workflows/swerepo-ci.yml"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = git_init(tmp_path / "app")
    make(root, {"pyproject.toml": PYPROJECT, "uv.lock": "version = 1\n", "CLAUDE.md": "# Mine\n"})
    apply(make_plan(root, today=TODAY, hosts=["claude"], code_owner="@dev", contact="github"), root)
    commit(root, "set up")
    return root


def plan(root: Path, **kwargs):
    return make_plan(root, today=TODAY, update=True, **kwargs)


def action(found, path: str):
    return next(a for a in found.actions if a.path == path)


def agents_block(root: Path) -> str:
    block = find_block((root / "AGENTS.md").read_text(), style=HTML)
    assert block is not None
    return block.content


def as_older_agents_block(root: Path) -> str:
    """Put AGENTS.md's block back to `agents/block@1`, as a repository set up before @2 would have it."""
    state = State.load(root)
    record = state.blocks()["AGENTS.md"]
    old = STORE.get("agents/block@1").render(record.inputs or {})
    text = (root / "AGENTS.md").read_text()
    (root / "AGENTS.md").write_text(replace_block_content(text, old, style=HTML, marker="swerepo"))
    state.set_block("AGENTS.md", Record("agents/block@1", fingerprint(old), fingerprint(old), record.inputs))
    state.save(root)
    return old


class TestInputs:
    def test_every_record_init_writes_rebuilds_exactly(self, repo: Path):
        """The base `update` merges against: every record's inputs give back the render it recorded."""
        state = State.load(repo)
        records = {**state.files(), **state.blocks()}
        assert len(records) >= 10 and all(record.inputs is not None for record in records.values())
        for path, record in records.items():
            text = rebuild(STORE, record.template, record.inputs or {})
            assert text is not None, path
            mark = fingerprint(text) if path in state.blocks() else file_fingerprint(text, record.template)
            assert mark == record.rendered, path


class TestUpdate:
    def test_a_second_update_has_nothing_to_do(self, repo: Path):
        assert not plan(repo).changes

    def test_an_untouched_outdated_block_is_rewritten(self, repo: Path):
        as_older_agents_block(repo)
        found = action(plan(repo), "AGENTS.md")
        latest = STORE.latest("agents", "block").id
        assert found.verb == REWRITE and found.record is not None and found.record.template == latest
        apply(plan(repo), repo)
        assert fingerprint(agents_block(repo)) == State.load(repo).blocks()["AGENTS.md"].written
        assert not plan(repo).changes

    def test_a_persons_edit_is_merged_only_with_a_yes(self, repo: Path):
        old = as_older_agents_block(repo)
        text = (repo / "AGENTS.md").read_text()
        mine = old.replace("\n", "\nA rule of my own.\n", 1)  # an edit at the top, away from @2's changes
        (repo / "AGENTS.md").write_text(replace_block_content(text, mine, style=HTML, marker="swerepo"))
        waiting = action(plan(repo), "AGENTS.md")
        assert waiting.verb == KEEP and "--merge" in waiting.note and waiting.diff
        merged = action(plan(repo, merge=True), "AGENTS.md")
        assert merged.verb == MERGE and "A rule of my own." in (merged.content or "")
        assert "swerepo threads" in (merged.content or "")  # @2's change came in too
        apply(plan(repo, merge=True), repo)
        assert "A rule of my own." in agents_block(repo) and "swerepo threads" in agents_block(repo)
        assert not plan(repo, merge=True).changes

    def test_a_conflict_is_reported_and_the_file_left_alone(self, repo: Path):
        old = as_older_agents_block(repo)
        new = STORE.latest("agents", "block").render(State.load(repo).blocks()["AGENTS.md"].inputs or {})
        changed = [a for a, b in zip(old.splitlines(), new.splitlines(), strict=False) if a != b]
        assert changed, "@1 and @2 differ somewhere"
        text = (repo / "AGENTS.md").read_text()
        (repo / "AGENTS.md").write_text(text.replace(changed[0], changed[0] + " (mine)"))
        before = (repo / "AGENTS.md").read_bytes()
        found = action(plan(repo, merge=True), "AGENTS.md")
        assert found.verb == CONFLICT and "swerepo diff" in found.note and found.diff
        apply(plan(repo, merge=True), repo)
        assert (repo / "AGENTS.md").read_bytes() == before and b"<<<<<<<" not in before

    def test_no_merge_against_a_base_that_doesnt_rebuild(self, repo: Path):
        as_older_agents_block(repo)
        state = State.load(repo)
        record = state.blocks()["AGENTS.md"]
        wrong = Record(record.template, fingerprint("something else"), record.written, record.inputs)
        state.set_block("AGENTS.md", wrong)
        state.save(repo)
        text = (repo / "AGENTS.md").read_text()
        (repo / "AGENTS.md").write_text(text.replace("## ", "## Mine: ", 1))
        found = action(plan(repo, merge=True), "AGENTS.md")
        assert found.verb == CANT_MERGE and "can't be rebuilt" in found.note

    def test_an_older_record_gets_the_inputs_that_rebuild_it(self, repo: Path):
        """The owner's idea: before [values] moves on, an older record without inputs gets them, when they give
        back its render."""
        state = State.load(repo)
        record = state.files()[WORKFLOW]
        state.set_file(WORKFLOW, Record(record.template, record.rendered, record.written))
        state.save(repo)
        found = plan(repo)
        workflow = action(found, WORKFLOW)
        assert workflow.backfill and workflow.record is not None and workflow.record.inputs == record.inputs
        apply(found, repo)
        assert State.load(repo).files()[WORKFLOW].inputs == record.inputs

    def test_update_brings_in_the_projects_new_commands(self, repo: Path):
        """init keeps the recorded commands; update renders with the project's current ones (point 10)."""
        recorded = State.load(repo).values["commands"]
        make(repo, {"Makefile": "test:\n\tpytest\n"})
        assert any("commands changed" in a.note for a in make_plan(repo, today=TODAY).actions)
        found = plan(repo)
        assert action(found, "AGENTS.md").verb == REWRITE and "make test" in (action(found, "AGENTS.md").content or "")
        apply(found, repo)
        state = State.load(repo)
        assert state.values["commands"] != recorded and "make test" in agents_block(repo)
        assert (state.blocks()["AGENTS.md"].inputs or {})["commands"] == state.values["commands"]
        assert not plan(repo).changes

    def test_an_older_edited_record_still_merges_after_the_commands_move(self, repo: Path):
        """The owner's backfill: an older record without inputs is rebuilt from `[values]` as recorded before the
        run, so the project's new commands don't take away its merge base."""
        old = as_older_agents_block(repo)
        state = State.load(repo)
        record = state.blocks()["AGENTS.md"]
        state.set_block("AGENTS.md", Record(record.template, record.rendered, record.written))  # no inputs: older
        state.save(repo)
        text = (repo / "AGENTS.md").read_text()
        (repo / "AGENTS.md").write_text(text.replace(old, old.replace("\n", "\nA rule of my own.\n", 1)))
        make(repo, {"Makefile": "test:\n\tpytest\n"})
        found = action(plan(repo, merge=True), "AGENTS.md")
        assert found.verb == MERGE, found.note
        content = found.content or ""
        assert "A rule of my own." in content and "make test" in content and "swerepo threads" in content
        assert found.record is not None and found.record.inputs is not None
        assert "make test" in found.record.inputs["commands"]  # the new render's inputs are recorded

    def test_an_item_the_standard_dropped_is_reported_and_kept(self, repo: Path):
        """ADR-20261124-7afa point 5: never deleted; its record stays, so `check` still knows it."""
        state = State.load(repo)
        mark = fingerprint("# Old\n")
        state.set_file("docs/agents/old-runbook.md", Record("agents/old-runbook@1", mark, mark))
        state.save(repo)
        (repo / "docs/agents/old-runbook.md").write_text("# Old\n")
        found = plan(repo)
        dropped = action(found, "docs/agents/old-runbook.md")
        assert dropped.verb == KEEP and "no longer in the standard" in dropped.note and not found.changes
        others = plan(repo, only=["docs"])  # another component's run doesn't report agents' items
        assert all(a.path != "docs/agents/old-runbook.md" for a in others.actions)
        apply(found, repo)
        assert (repo / "docs/agents/old-runbook.md").read_text() == "# Old\n"
        assert "docs/agents/old-runbook.md" in State.load(repo).files()


class TestPins:
    def test_dependabots_pins_alone_update_without_merge(self, repo: Path):
        """A workflow that differs from SWERepo's render only by newer pins was Dependabot's: no --merge needed."""
        state = State.load(repo)
        record = state.files()[WORKFLOW]
        older_inputs = {**(record.inputs or {}), "seamspec": "0.1.1"}  # an earlier render, with an older SeamSpec
        older = rebuild(STORE, record.template, older_inputs)
        assert older is not None
        line = next(line for line in older.splitlines() if "actions/checkout@" in line)
        newer = line.split("@")[0] + "@" + "f" * 40 + "  # v99.0.0"
        (repo / WORKFLOW).write_text(older.replace(line, newer))  # Dependabot moved the pins
        mark = file_fingerprint(older, record.template)
        state.set_file(WORKFLOW, Record(record.template, mark, mark, older_inputs))
        state.save(repo)
        found = action(plan(repo), WORKFLOW)  # no merge=True
        assert found.verb == MERGE and "newer action pins" in found.note
        assert newer in (found.content or "") and "seamspec==0.1.1" not in (found.content or "")


class TestCommands:
    def test_yes_alone_never_merges_into_your_edits(self, repo: Path):
        old = as_older_agents_block(repo)
        text = (repo / "AGENTS.md").read_text()
        (repo / "AGENTS.md").write_text(text.replace(old, old.replace("\n", "\nA rule of my own.\n", 1)))
        before = (repo / "AGENTS.md").read_bytes()
        result = CliRunner().invoke(app, ["update", "--path", str(repo), "--yes"])
        assert result.exit_code == 0, result.output
        assert (repo / "AGENTS.md").read_bytes() == before and "--merge" in result.output
        result = CliRunner().invoke(app, ["update", "--path", str(repo), "--yes", "--merge"])
        assert result.exit_code == 0, result.output
        assert "1 merged" in result.output and "A rule of my own." in agents_block(repo)
        assert "+" in result.output and "swerepo threads" in result.output  # the merge was shown

    def test_u_is_update(self, repo: Path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["swerepo", "-u", "--path", str(repo), "--dry-run"])
        with pytest.raises(SystemExit) as done:
            cli.main()
        assert done.value.code == 0

    def test_diff_shows_the_change_to_make_by_hand(self, repo: Path):
        old = as_older_agents_block(repo)
        new = STORE.latest("agents", "block").render(State.load(repo).blocks()["AGENTS.md"].inputs or {})
        first = next(a for a, b in zip(old.splitlines(), new.splitlines(), strict=False) if a != b)
        text = (repo / "AGENTS.md").read_text()
        (repo / "AGENTS.md").write_text(text.replace(first, first + " (mine)"))
        before = sorted((p, p.stat().st_mtime_ns) for p in repo.rglob("*") if ".git/" not in str(p))
        result = CliRunner().invoke(app, ["diff", "--path", str(repo)])
        assert result.exit_code == 0 and "AGENTS.md: conflicts with your edits" in result.output
        assert "SWERepo's new version" in result.output
        status = CliRunner().invoke(app, ["status", "--path", str(repo), "--json"])
        assert status.exit_code == 0
        assert json.loads(status.output)["files"]["edited, conflicts with the update"] == 1
        after = sorted((p, p.stat().st_mtime_ns) for p in repo.rglob("*") if ".git/" not in str(p))
        assert before == after  # diff and status only read

    def test_update_can_switch_the_pull_request_rules_on(self, repo: Path):
        state = State.load(repo)
        state.set_pr_rules(enforce=False, warn_since=TODAY)
        state.save(repo)
        apply(plan(repo, enforce_pr_rules=True), repo)
        assert State.load(repo).pr_enforce is True

    def test_update_needs_a_set_up_repository_and_known_components(self, tmp_path: Path, repo: Path):
        bare = git_init(tmp_path / "bare")
        assert CliRunner().invoke(app, ["update", "--path", str(bare)]).exit_code == 2
        state = State.load(repo)
        state.set_components(["docs"])
        state.save(repo)
        result = CliRunner().invoke(app, ["update", "--path", str(repo), "--only", "ci"])
        assert result.exit_code == 2 and "not set up here: ci" in result.output
        unknown = CliRunner().invoke(app, ["update", "--path", str(repo), "--only", "release"])
        assert unknown.exit_code == 2 and "unknown component release" in unknown.output  # never "init --only release"


class TestCheck:
    def test_newer_pins_alone_are_current(self, repo: Path):
        """ADR-20261123-f571 point 3: Dependabot's newer pins aren't "changed by you"; anything more is."""
        from swerepo.check import CHANGED, run_check

        def changed() -> bool:
            return any(f.path == WORKFLOW and f.status == CHANGED for f in run_check(repo, only=["ci"]).findings)

        text = (repo / WORKFLOW).read_text()
        line = next(line for line in text.splitlines() if "actions/checkout@" in line)
        version = line.rsplit("# v", 1)[1]
        newer = line.split("@")[0] + "@" + "f" * 40 + "  # v99.0.0"
        (repo / WORKFLOW).write_text(text.replace(line, newer))
        assert not changed()
        same_version = line.split("@")[0] + "@" + "e" * 40 + f"  # v{version}"
        (repo / WORKFLOW).write_text(text.replace(line, same_version))  # one version, another commit
        assert changed()
        (repo / WORKFLOW).write_text(text.replace(line, newer).replace("name: swerepo-ci", "name: mine"))
        assert changed()


SETTINGS = ".github/swerepo/repo-settings.json"


def older_settings(root: Path, edit) -> str:
    """repo-settings.json as an older render (merge commits allowed) wrote it, then edited by `edit`."""
    state = State.load(root)
    record = state.files()[SETTINGS]
    older_inputs = {**(record.inputs or {}), "merge_methods": "merge,squash"}
    older = rebuild(STORE, record.template, older_inputs)
    assert older is not None and older != (root / SETTINGS).read_text()
    (root / SETTINGS).write_text(edit(older))
    mark = file_fingerprint(older, record.template)
    state.set_file(SETTINGS, Record(record.template, mark, mark, older_inputs))
    state.save(root)
    return older


class TestReviewP6:
    def test_p6_f01_a_merge_that_breaks_the_json_is_a_conflict(self, repo: Path):
        """A text merge can be clean and still leave invalid JSON: never written."""
        older_settings(repo, lambda text: text.replace('"PR_BODY"', '"PR_BODY",'))  # a trailing comma, far away
        before = (repo / SETTINGS).read_bytes()
        found = action(plan(repo, merge=True, only=["github"]), SETTINGS)
        assert found.verb == CONFLICT and "unparseable as JSON" in found.note
        apply(plan(repo, merge=True, only=["github"]), repo)
        assert (repo / SETTINGS).read_bytes() == before

    def test_p6_f01_a_toml_block_that_would_break_the_file_isnt_written(self, repo: Path):
        """An older settings block, and a key of the person's after it: valid now, but the new block ends in a
        table holding the same key. Never written."""
        state = State.load(repo)
        record = state.blocks()["pyproject.toml"]
        text = (repo / "pyproject.toml").read_text()
        older = "x = 1\n"
        text = replace_block_content(text, older, style=HASH, marker="swerepo") + 'addopts = ["-q"]\n'
        (repo / "pyproject.toml").write_text(text)
        assert tomllib.loads(text)  # valid before the update
        mark = fingerprint(older)
        state.set_block("pyproject.toml", Record("ci/pyproject@1", mark, mark, record.inputs))
        state.save(repo)
        before = (repo / "pyproject.toml").read_bytes()
        found = action(plan(repo, only=["ci"]), "pyproject.toml")
        assert found.verb == CANT_MERGE and "unparseable as TOML" in found.note
        apply(plan(repo, only=["ci"]), repo)
        assert (repo / "pyproject.toml").read_bytes() == before

    def test_p6_f01_the_merged_settings_are_what_github_gets(self, repo: Path, tmp_path: Path, monkeypatch):
        slug = "acme/app"
        git(repo, "remote", "add", "origin", f"https://github.com/{slug}.git")
        fake = FakeGh(tmp_path / "fake-gh", monkeypatch)
        fake.set(f"GET repos/{slug}", {"owner": {"login": "dev", "type": "User"}, "allow_merge_commit": True,
                                       "allow_squash_merge": True, "allow_rebase_merge": False,
                                       "delete_branch_on_merge": True, "allow_auto_merge": False})  # fmt: skip
        fake.set(f"GET repos/{slug}/rulesets", [])
        fake.set(f"GET repos/{slug}/dependency-graph/sbom", {"sbom": {}})
        mine = '"delete_branch_on_merge": false'
        older_settings(repo, lambda text: text.replace('"delete_branch_on_merge": true', mine))
        found = plan(repo, merge=True, only=["github"])
        assert action(found, SETTINGS).verb == MERGE and mine in (action(found, SETTINGS).content or "")
        applied = found.github_apply["settings"]
        assert applied["delete_branch_on_merge"] is False  # the person's edit
        assert applied["allow_merge_commit"] is False  # the update's

    def test_p6_f02_update_keeps_the_adr_index(self, repo: Path):
        from swerepo.adr import write_index

        readme = "docs/adr/README.md"
        front = "---\nid: ADR-20261124-abcd\ntitle: Use Postgres\nstatus: ACCEPTED\ndate: 2026-11-24\n---\n"
        (repo / "docs/adr/ADR-20261124-abcd-use-postgres.md").write_text(front + "\n# Use Postgres\n")
        write_index(repo / "docs/adr")
        assert "ADR-20261124-abcd" in (repo / readme).read_text()
        state = State.load(repo)
        record = state.files()[readme]
        text = (repo / readme).read_text()
        older = text.replace("\n", "\nAn older template's line.\n", 1)  # as an older docs/adr-readme wrote it
        (repo / readme).write_text(older)
        mark = file_fingerprint(older, record.template)
        state.set_file(readme, Record(record.template, mark, mark, record.inputs))
        state.save(repo)  # SWERepo's render alone, nobody changed it: update rewrites it
        found = action(plan(repo), readme)
        assert found.verb == REWRITE and "ADR-20261124-abcd" in (found.content or "")
        apply(plan(repo), repo)
        assert "ADR-20261124-abcd" in (repo / readme).read_text()
        from swerepo.check import CHANGED, MISSING, run_check

        report = run_check(repo, only=["docs"])
        assert not [f for f in report.findings if f.status in (CHANGED, MISSING)], report.findings

    def test_p6_f03_dependabots_pins_are_current_everywhere(self, repo: Path):
        """No template change pending: check, status and update all call a pins-only workflow current; and check
        still does after an update kept a newer pin (written != rendered)."""
        from swerepo.check import CHANGED, run_check

        text = (repo / WORKFLOW).read_text()
        line = next(line for line in text.splitlines() if "actions/checkout@" in line)
        newer = line.split("@")[0] + "@" + "f" * 40 + "  # v98.0.0"
        (repo / WORKFLOW).write_text(text.replace(line, newer))
        found = action(plan(repo), WORKFLOW)
        assert found.verb == CURRENT and "newer action pins" in found.note
        status = CliRunner().invoke(app, ["status", "--path", str(repo), "--json"])
        assert json.loads(status.output)["files"].get("current", 0) >= 1
        assert json.loads(status.output)["files"]["edited, nothing to update"] == 0
        state = State.load(repo)
        record = state.files()[WORKFLOW]
        kept = file_fingerprint((repo / WORKFLOW).read_text(), record.template)
        state.set_file(WORKFLOW, Record(record.template, record.rendered, kept, record.inputs))  # update kept v98
        state.save(repo)
        newest = line.split("@")[0] + "@" + "e" * 40 + "  # v99.0.0"
        (repo / WORKFLOW).write_text(text.replace(line, newest))  # Dependabot's next bump
        assert not any(f.path == WORKFLOW and f.status == CHANGED for f in run_check(repo, only=["ci"]).findings)

    def test_p6_f03_pins_only_is_for_workflows(self, repo: Path):
        from swerepo.check import CHANGED, run_check

        path = ".github/dependabot.yml"
        assert path in State.load(repo).files()
        text = (repo / path).read_text()
        (repo / path).write_text(text + "# uses: actions/checkout@" + "f" * 40 + "  # v99.0.0\n")
        assert any(f.path == path and f.status == CHANGED for f in run_check(repo, only=["github"]).findings)

    def test_p6_f04_a_partial_update_keeps_every_older_records_base(self, repo: Path):
        """Older records without inputs, the project's commands changed: `update --only docs` backfills the agents
        records too, before moving `commands` on, so a later `update --only agents --merge` still merges."""
        old = as_older_agents_block(repo)
        state = State.load(repo)
        for path, record in state.files().items():
            state.set_file(path, Record(record.template, record.rendered, record.written))
        for path, record in state.blocks().items():
            state.set_block(path, Record(record.template, record.rendered, record.written))
        state.save(repo)
        recorded = state.values["commands"]
        text = (repo / "AGENTS.md").read_text()
        (repo / "AGENTS.md").write_text(text.replace(old, old.replace("\n", "\nA rule of my own.\n", 1)))
        make(repo, {"Makefile": "test:\n\tpytest\n"})
        apply(plan(repo, only=["docs"]), repo)
        after = State.load(repo)
        assert after.values["commands"] != recorded  # moved on
        assert (after.blocks()["AGENTS.md"].inputs or {}).get("commands") == recorded  # but the base was kept
        found = action(plan(repo, only=["agents"], merge=True), "AGENTS.md")
        assert found.verb == MERGE, found.note

    def test_p6_f05_a_check_name_with_a_comma_rebuilds(self):
        from swerepo import github
        from swerepo.rebuild import github_inputs

        settings = github.Settings("team", "@dev", extra_checks=("test (ubuntu-latest, 3.12)", "web"))
        for name in ("ruleset", "repo-settings"):
            template_id, text = github.render(name, settings)
            assert rebuild(STORE, template_id, github_inputs(settings)) == text
        older = {**github_inputs(settings), "extra_checks": "web,docs"}  # recorded before the fix
        assert '"docs"' in (rebuild(STORE, "github/ruleset@1", older) or "")

    def test_p6_f06_update_follows_requires_python(self, repo: Path):
        """check says "swerepo update" for a matrix that no longer matches requires-python: update then fixes it."""
        from swerepo.check import OUTDATED, run_check

        def matrix_outdated() -> bool:
            return any(
                f.item == "ci.python-matrix" and f.status == OUTDATED for f in run_check(repo, only=["ci"]).findings
            )

        text = (repo / "pyproject.toml").read_text()
        (repo / "pyproject.toml").write_text(text.replace('requires-python = ">=3.12"', 'requires-python = ">=3.13"'))
        assert matrix_outdated()
        assert not any(a.path == WORKFLOW and a.changes for a in make_plan(repo, today=TODAY).actions)  # init: kept
        apply(plan(repo), repo)
        assert not matrix_outdated()
        assert State.load(repo).values["python"] == ["3.13", "3.14"]
        assert not plan(repo).changes

    def test_p6_f06_update_moves_swerepos_own_pin_to_a_release(self, unreleased, repo: Path, monkeypatch):
        from swerepo import ci

        monkeypatch.setattr(ci, "released", lambda *_: True)
        found = plan(repo)
        workflow = action(found, WORKFLOW)
        assert workflow.verb == REWRITE and "uvx swerepo==" in (workflow.content or "")
        assert "uvx swerepo==" not in (repo / WORKFLOW).read_text()

    def test_p6_f07_diff_shows_what_cant_be_merged_and_never_calls_github(
        self, repo: Path, tmp_path: Path, monkeypatch
    ):
        git(repo, "remote", "add", "origin", "https://github.com/acme/app.git")
        fake = FakeGh(tmp_path / "fake-gh", monkeypatch)
        as_older_agents_block(repo)
        state = State.load(repo)
        record = state.blocks()["AGENTS.md"]
        state.set_block("AGENTS.md", Record(record.template, fingerprint("not it"), record.written, record.inputs))
        state.save(repo)
        text = (repo / "AGENTS.md").read_text()
        (repo / "AGENTS.md").write_text(text.replace("## ", "## Mine: ", 1))
        result = CliRunner().invoke(app, ["diff", "./AGENTS.md", "--path", str(repo)])
        assert result.exit_code == 0 and "AGENTS.md: can't be merged" in result.output
        assert "swerepo threads" in result.output  # SWERepo's new version, to bring in by hand
        windows = CliRunner().invoke(app, ["diff", ".\\AGENTS.md", "--path", str(repo)])  # as typed on Windows
        assert windows.exit_code == 0 and "AGENTS.md: can't be merged" in windows.output
        assert CliRunner().invoke(app, ["status", "--path", str(repo)]).exit_code == 0
        assert fake.calls() == []  # diff and status show files only: no gh call at all

    def test_p6_f08_update_only_github_leaves_cis_own_updates(self, repo: Path):
        """github alone brings ci along only for the Copilot wait (P5-F01), never for ci's own updates."""
        text = (repo / "pyproject.toml").read_text()
        (repo / "pyproject.toml").write_text(text.replace('requires-python = ">=3.12"', 'requires-python = ">=3.13"'))
        before = {path: (repo / path).read_bytes() for path in (WORKFLOW, "pyproject.toml")}
        found = plan(repo, only=["github"])
        assert not any(a.path in before and a.changes for a in found.actions)
        apply(found, repo)
        assert all((repo / path).read_bytes() == data for path, data in before.items())
        assert State.load(repo).values["python"] == ["3.12", "3.13", "3.14"]  # still ci's to change
        assert action(plan(repo, only=["ci"]), WORKFLOW).verb == REWRITE  # ci itself does


class TestCopilotPR18:
    """Copilot's review of PR #18."""

    def test_a_merged_rule_survives_a_later_template_change(self, repo: Path):
        """After a merge, `written` != `rendered`: a later change is merged too, with consent, never rewritten."""
        old = as_older_agents_block(repo)
        text = (repo / "AGENTS.md").read_text()
        (repo / "AGENTS.md").write_text(text.replace(old, old.replace("\n", "\nA rule of my own.\n", 1)))
        apply(plan(repo, merge=True), repo)
        assert "A rule of my own." in agents_block(repo)
        make(repo, {"Makefile": "test:\n\tpytest\n"})  # the project's commands change: the block renders anew
        waiting = action(plan(repo), "AGENTS.md")
        assert waiting.verb == KEEP and "--merge" in waiting.note  # --yes alone: never rewritten over the rule
        apply(plan(repo), repo)
        assert "A rule of my own." in agents_block(repo)
        apply(plan(repo, merge=True), repo)
        assert "A rule of my own." in agents_block(repo) and "make test" in agents_block(repo)

    def test_kept_dependabot_pins_survive_a_later_template_change(self, repo: Path):
        text = (repo / WORKFLOW).read_text()
        line = next(line for line in text.splitlines() if "actions/checkout@" in line)
        newer = line.split("@")[0] + "@" + "f" * 40 + "  # v99.0.0"
        (repo / WORKFLOW).write_text(text.replace(line, newer))
        state = State.load(repo)
        record = state.files()[WORKFLOW]
        kept = file_fingerprint((repo / WORKFLOW).read_text(), record.template)
        state.set_file(WORKFLOW, Record(record.template, record.rendered, kept, record.inputs))  # an update kept v99
        state.save(repo)
        pyproject = (repo / "pyproject.toml").read_text()
        (repo / "pyproject.toml").write_text(pyproject.replace('">=3.12"', '">=3.13"'))  # the workflow renders anew
        found = action(plan(repo), WORKFLOW)
        assert found.verb == MERGE and newer in (found.content or "")  # pins only: --yes alone, pins kept
        assert '"3.12"' not in (found.content or "")

    def test_a_merge_keeps_bytes_that_arent_utf8(self, repo: Path):
        runbook = "docs/agents/address-review.md"
        state = State.load(repo)
        record = state.files()[runbook]
        old = STORE.get("agents/address-review@1").render(record.inputs or {})
        (repo / runbook).write_bytes(old.encode() + b"\nNote: caf\xe9\n")  # a Latin-1 line of the person's
        mark = file_fingerprint(old, "agents/address-review@1")
        state.set_file(runbook, Record("agents/address-review@1", mark, mark, record.inputs))
        state.save(repo)
        result = CliRunner().invoke(app, ["update", "--path", str(repo), "--yes", "--merge", "--json"])
        assert result.exit_code == 0, result.output
        data = (repo / runbook).read_bytes()
        assert b"caf\xe9" in data and b"swerepo threads" in data

    def test_an_older_workflow_record_still_merges_after_requires_python_moves(self, repo: Path):
        state = State.load(repo)
        record = state.files()[WORKFLOW]
        state.set_file(WORKFLOW, Record(record.template, record.rendered, record.written))  # no inputs: older
        state.save(repo)
        text = (repo / WORKFLOW).read_text()
        assert "name: swerepo-ci" in text
        (repo / WORKFLOW).write_text(text.replace("name: swerepo-ci", "name: mine", 1))
        pyproject = (repo / "pyproject.toml").read_text()
        (repo / "pyproject.toml").write_text(pyproject.replace('">=3.12"', '">=3.13"'))
        found = action(plan(repo, merge=True), WORKFLOW)
        assert found.verb == MERGE, found.note
        assert "name: mine" in (found.content or "") and '"3.12"' not in (found.content or "")

    def test_an_empty_python_matrix_cant_be_rebuilt(self, repo: Path):
        record = State.load(repo).files()[WORKFLOW]
        assert rebuild(STORE, record.template, {**(record.inputs or {}), "python": ""}) is None
        state = State.load(repo)
        state.set_file(WORKFLOW, Record(record.template, record.rendered, record.written,
                                        {**(record.inputs or {}), "python": ""}))  # fmt: skip
        state.save(repo)
        assert CliRunner().invoke(app, ["status", "--path", str(repo)]).exit_code == 0
        assert CliRunner().invoke(app, ["diff", "--path", str(repo)]).exit_code == 0
