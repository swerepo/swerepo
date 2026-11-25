"""The project's spec (spec §6.7, §14; ADR-20261124-4d76): the starter `SPEC.md`, or the spec already there."""

import datetime
from pathlib import Path

import pytest
from repo_helpers import commit, git_init, make, snapshot

from swerepo import spec as specs
from swerepo.check import MISSING, OK, run_check
from swerepo.init import ADOPT, CREATE, KEEP, NOTE, apply, make_plan
from swerepo.state import State, StateError

TODAY = datetime.date(2026, 11, 25)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = git_init(tmp_path / "invoices")
    make(root, {"pyproject.toml": '[project]\nname = "invoices"\n'})
    return root


def plan(root: Path, **kwargs):
    return make_plan(root, today=TODAY, only=["docs"], hosts=[], **kwargs)


def spec_action(found):
    """The plan's one line about the spec: the file it follows or writes, or the note when it can't choose."""
    for a in found.actions:
        about_spec = (a.path or "").lower().endswith("spec.md") or (a.verb == NOTE and "spec" in a.note)
        if a.component == "docs" and about_spec:
            return a
    raise AssertionError("no spec action in the plan")


def docs_spec(root: Path):
    return next(f for f in run_check(root, only=["docs"]).findings if f.item == "docs.spec")


class TestLookup:
    @pytest.mark.parametrize(
        ("files", "path", "adopt", "several"),
        [
            ([], None, None, ()),
            (["SPEC.md"], "SPEC.md", None, ()),
            (["docs/SPEC.md"], "docs/SPEC.md", "docs/SPEC.md", ()),
            (["INVOICES-SPEC.md"], "INVOICES-SPEC.md", "INVOICES-SPEC.md", ()),
            (["spec.md"], "spec.md", "spec.md", ()),  # not the default's spelling: recorded, so templates name it
            (["docs/EARNED_SPEC.md"], None, None, ()),  # SeamSpec's enforced rules are never the spec
            (["SPEC.md", "docs/SPEC.md"], None, None, ("SPEC.md", "docs/SPEC.md")),
            (["A-SPEC.md", "B-SPEC.md"], None, None, ("A-SPEC.md", "B-SPEC.md")),
        ],
    )
    def test_the_five_steps(self, tmp_path: Path, files, path, adopt, several):
        make(tmp_path, {name: "# x\n" for name in files})
        found = specs.find(tmp_path)
        assert (found.path, found.adopt, found.several) == (path, adopt, several)
        assert found.name == (path or "SPEC.md")

    def test_adopted_wins_and_nothing_is_looked_for(self, tmp_path: Path):
        make(tmp_path, {"SPEC.md": "# x\n", "docs/SPEC.md": "# y\n"})
        found = specs.find(tmp_path, "docs/design.md")
        assert (found.path, found.adopted, found.several) == ("docs/design.md", True, ())


class TestInit:
    def test_no_spec_gets_the_starter_and_nothing_is_recorded(self, project: Path):
        found = plan(project)
        action = spec_action(found)
        assert (action.path, action.verb) == ("SPEC.md", CREATE) and "# invoices · Specification" in action.content
        apply(found, project)
        assert "spec" not in State.load(project).adopted
        assert docs_spec(project).status == OK
        commit(project, "set up")
        before = snapshot(project)
        again = plan(project)
        assert not again.changes and spec_action(again).verb == KEEP  # inv_1002d669: a second run changes nothing
        apply(again, project)
        assert snapshot(project) == before

    def test_an_existing_spec_is_never_replaced(self, project: Path):
        make(project, {"SPEC.md": "Mine.\n"})
        apply(plan(project), project)
        assert (project / "SPEC.md").read_text() == "Mine.\n"

    def test_a_single_other_spec_is_adopted(self, project: Path):
        make(project, {"INVOICES-SPEC.md": "# Ours\n"})
        found = plan(project)
        assert (spec_action(found).path, spec_action(found).verb) == ("INVOICES-SPEC.md", ADOPT)
        apply(found, project)
        assert State.load(project).adopted["spec"] == "INVOICES-SPEC.md"
        assert not (project / "SPEC.md").exists()
        assert docs_spec(project).message == "spec (adopted: INVOICES-SPEC.md)"
        assert not plan(project).changes

    def test_update_adopts_the_spec_of_a_repository_set_up_before(self, project: Path):
        make(project, {"SPEC.md": "# x\n"})
        apply(plan(project), project)
        (project / "SPEC.md").rename(project / "INVOICES-SPEC.md")  # as a repository with its own spec
        found = make_plan(project, today=TODAY, only=["docs"], hosts=[], update=True)
        assert spec_action(found).verb == ADOPT
        apply(found, project)
        assert State.load(project).adopted["spec"] == "INVOICES-SPEC.md"

    def test_several_are_listed_never_guessed(self, project: Path):
        make(project, {"SPEC.md": "# a\n", "docs/SPEC.md": "# b\n"})
        found = plan(project)
        note = spec_action(found)
        assert note.verb == NOTE and "SPEC.md, docs/SPEC.md" in note.note and "[adopted]" in note.note
        apply(found, project)
        assert "spec" not in State.load(project).adopted
        finding = docs_spec(project)
        assert finding.status == MISSING and "SPEC.md, docs/SPEC.md" in finding.message
        state = State.load(project)
        state.set_adopted("spec", "docs/SPEC.md")  # the person chooses
        state.save(project)
        assert docs_spec(project).status == OK

    def test_an_adopted_spec_that_is_gone_is_reported(self, project: Path):
        apply(plan(project), project)
        state = State.load(project)
        state.set_adopted("spec", "docs/DESIGN.md")
        state.save(project)
        assert spec_action(plan(project)).verb == NOTE
        finding = docs_spec(project)
        assert finding.status == MISSING and "docs/DESIGN.md" in finding.message


def test_adopted_spec_is_a_checked_path():
    with pytest.raises(StateError, match="adopted.spec"):
        State.new().set_adopted("spec", "../elsewhere.md")


class TestReviewP8:
    """Gemini's implementation review, round 1, each reproduced before the fix."""

    def test_f01_files_git_ignores_never_count(self, project: Path):
        make(project, {".gitignore": "DRAFT-SPEC.md\n", "DRAFT-SPEC.md": "# scratch\n", "SPEC.md": "# x\n"})
        assert specs.find(project) == specs.Found("SPEC.md")
        assert docs_spec(project).status == OK
        make(project, {"-SPEC.md": "# no name\n"})  # `-SPEC.md` alone names no project
        assert specs.candidates(project) == ["SPEC.md"]

    def test_f01_links_count_only_inside_the_repository(self, project: Path, tmp_path: Path):
        outside = tmp_path / "elsewhere"
        make(outside, {"SPEC.md": "# not ours\n"})
        (project / "docs").symlink_to(outside, target_is_directory=True)
        assert specs.find(project) == specs.Found(None)  # docs/ leads out: not a candidate
        (project / "docs").unlink()
        (project / "THEIRS-SPEC.md").symlink_to(outside / "SPEC.md")  # a file leading out: not one either
        assert specs.find(project) == specs.Found(None)
        (project / "THEIRS-SPEC.md").unlink()
        make(project, {"real.md": "# ours\n"})
        (project / "SPEC.md").symlink_to("real.md")
        assert specs.find(project) == specs.Found("SPEC.md") and docs_spec(project).status == OK
        assert spec_action(plan(project)).verb == KEEP  # init and check agree

    def test_f01_an_adopted_spec_through_a_link_out_is_refused(self, project: Path, tmp_path: Path):
        make(tmp_path / "elsewhere", {"SPEC.md": "# not ours\n"})
        (project / "THEIRS-SPEC.md").symlink_to(tmp_path / "elsewhere" / "SPEC.md")
        assert specs.candidates(project) == []
        state = State.new()
        state.set_adopted("spec", "THEIRS-SPEC.md")
        state.save(project)
        action = spec_action(plan(project))
        assert action.verb == KEEP and "link out of the repository" in action.note
        finding = docs_spec(project)
        assert finding.status == MISSING and "leads out of the repository" in finding.message

    def test_f01_a_broken_link_is_never_written_through(self, project: Path):
        (project / "SPEC.md").symlink_to("missing.md")
        found = plan(project)
        action = spec_action(found)
        assert action.verb == KEEP and "isn't there" in action.note
        apply(found, project)  # no "appeared since the plan was made"
        assert (project / "SPEC.md").is_symlink() and not (project / "missing.md").exists()
        assert docs_spec(project).status == MISSING

    @pytest.mark.parametrize("only", ["agents", "github"])
    def test_f02_a_run_without_docs_records_the_spec_its_files_name(self, project: Path, only: str):
        make(project, {"INVOICES-SPEC.md": "# Ours\n"})
        found = make_plan(project, today=TODAY, only=[only], hosts=[], code_owner="@dev", contact="github")
        adopt = [a for a in found.actions if a.verb == ADOPT and a.path == "INVOICES-SPEC.md"]
        assert adopt and adopt[0].component == only
        apply(found, project)
        assert State.load(project).adopted["spec"] == "INVOICES-SPEC.md"
        make(project, {"docs/SPEC.md": "# a second one\n"})  # recorded: a new candidate changes nothing
        again = make_plan(project, today=TODAY, only=[only], hosts=[], code_owner="@dev", contact="github")
        assert not again.changes


class TestCopilotPR22:
    """Copilot's review of PR #22, each reproduced before the fix."""

    def test_the_docs_folder_matches_whatever_its_case(self, project: Path):
        make(project, {"Docs/SPEC.md": "# Ours\n"})
        assert specs.find(project) == specs.Found("Docs/SPEC.md", adopt="Docs/SPEC.md")
        found = plan(project)
        assert spec_action(found).verb == ADOPT and not any(a.path == "SPEC.md" for a in found.actions)
        assert docs_spec(project).status == OK

    @pytest.mark.parametrize("only", ["agents", "github"])
    def test_a_run_without_docs_lists_several_specs_too(self, project: Path, only: str):
        make(project, {"A-SPEC.md": "# a\n", "B-SPEC.md": "# b\n"})
        found = make_plan(project, today=TODAY, only=[only], hosts=[], code_owner="@dev", contact="github")
        notes = [a for a in found.actions if a.verb == NOTE and "several specs" in a.note]
        assert len(notes) == 1 and notes[0].component == only and "A-SPEC.md, B-SPEC.md" in notes[0].note
        both = make_plan(project, today=TODAY, only=["docs", only], hosts=[], code_owner="@dev", contact="github")
        assert len([a for a in both.actions if a.verb == NOTE and "several specs" in a.note]) == 1  # once, by docs
