"""`swerepo check --base` pull-request rules on real git histories (spec §6.5, §15; ADR-20261120-5e21)."""

import os
from pathlib import Path

import pytest
from repo_helpers import commit, git, git_init, make

from swerepo.check import MISSING, NOT_CHOSEN, OK, UNKNOWN, UsageError, run_check
from swerepo.fingerprint import fingerprint
from swerepo.state import FILE_NAME, Record, State

PYPROJECT = '[project]\nname = "demo"\ndependencies = ["typer>=0.12", "Tomli_W"]\n'


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """`main` with one commit, then a branch `feature` to change."""
    git_init(tmp_path)
    make(tmp_path, {
        "pyproject.toml": PYPROJECT,
        "docs/adr/README.md": "# ADRs\n",
        "docs/progress/20260101-start.md": "x\n",
        ".github/workflows/ci.yml": "jobs: {}\n",
        "app.py": "print('hi')\n",
    })  # fmt: skip
    commit(tmp_path, "start")
    git(tmp_path, "checkout", "-q", "-b", "feature")
    return tmp_path


def pr(repo: Path, **kwargs) -> dict[str, object]:
    report = run_check(repo, only=["docs"], base="main", **kwargs)
    return {f.item: f for f in report.findings if f.component == "pr"}


def test_a_change_without_a_progress_entry(repo: Path):
    make(repo, {"app.py": "print('changed')\n"})
    finding = pr(repo)["pr.progress"]
    assert finding.status == MISSING and finding.blocking


def test_a_progress_entry_added_even_uncommitted(repo: Path):
    make(repo, {"app.py": "print('changed')\n", "docs/progress/20260102-change.md": "x\n"})  # untracked
    assert pr(repo)["pr.progress"].status == OK
    commit(repo)
    assert pr(repo)["pr.progress"].status == OK


def test_editing_an_old_progress_entry_is_not_a_new_one(repo: Path):
    make(repo, {"docs/progress/20260101-start.md": "edited\n"})
    assert pr(repo)["pr.progress"].status == MISSING


@pytest.mark.parametrize("trailer", ["Progress: none", "progress:   NONE"])
def test_the_trailer_opts_out(repo: Path, trailer: str):
    make(repo, {"app.py": "print('typo')\n"})
    commit(repo, f"Fix a typo\n\n{trailer}")
    assert pr(repo)["pr.progress"].status == OK


def test_skip_progress_opts_out(repo: Path):
    make(repo, {"app.py": "print('changed')\n"})
    assert "--skip progress" in pr(repo, skip=("progress",))["pr.progress"].message


class TestDependencies:
    def test_a_new_dependency_needs_an_adr(self, repo: Path):
        make(repo, {"pyproject.toml": PYPROJECT.replace('"Tomli_W"', '"Tomli_W", "requests>=2"')})
        finding = pr(repo)["pr.dependencies"]
        assert finding.status == MISSING and "new dependency requests needs an ADR" in finding.message

    def test_with_an_adr_it_passes(self, repo: Path):
        make(repo, {
            "pyproject.toml": PYPROJECT.replace('"Tomli_W"', '"Tomli_W", "requests>=2"'),
            "docs/adr/ADR-20260102-beef-use-requests.md": "# Use requests\n",
        })  # fmt: skip
        assert pr(repo)["pr.dependencies"].status == OK

    @pytest.mark.parametrize(
        "change",
        [
            '["typer>=0.13", "Tomli_W"]',  # a version bump
            '["typer[all]>=0.12", "Tomli_W"]',  # extras
            '["typer>=0.12", "tomli-w"]',  # the same name, normalised (PEP 503)
            '["typer>=0.12"]',  # a removal
        ],
    )
    def test_changes_that_add_no_package_need_no_adr(self, repo: Path, change: str):
        make(repo, {"pyproject.toml": PYPROJECT.replace('["typer>=0.12", "Tomli_W"]', change)})
        assert "pr.dependencies" not in pr(repo)

    def test_an_unparsable_entry_is_unknown(self, repo: Path):
        make(repo, {"pyproject.toml": PYPROJECT.replace('"Tomli_W"', '"Tomli_W", "not a requirement!"')})
        assert pr(repo)["pr.dependencies"].status == UNKNOWN

    def test_editing_the_adr_readme_is_not_an_adr(self, repo: Path):
        make(repo, {
            "pyproject.toml": PYPROJECT.replace('"Tomli_W"', '"Tomli_W", "requests"'),
            "docs/adr/README.md": "# ADRs, edited\n",
        })  # fmt: skip
        assert pr(repo)["pr.dependencies"].status == MISSING


class TestWorkflows:
    def test_a_workflow_change_needs_an_adr(self, repo: Path):
        make(repo, {".github/workflows/ci.yml": "jobs: {weakened: {}}\n"})
        finding = pr(repo)["pr.workflows"]
        assert finding.status == MISSING and ".github/workflows/ci.yml" in finding.message

    def test_a_touched_but_unchanged_workflow_is_no_change(self, repo: Path):
        """Only the file time differs, so git's index is out of date: the diff still sees no change."""
        workflow = repo / ".github/workflows/ci.yml"
        stamp = workflow.stat().st_mtime_ns + 10**9
        os.utime(workflow, ns=(stamp, stamp))
        assert "pr.workflows" not in pr(repo)

    @pytest.mark.parametrize("change", ["add", "delete"])
    def test_adding_or_deleting_a_workflow_counts(self, repo: Path, change: str):
        if change == "add":
            make(repo, {".github/workflows/new.yml": "jobs: {}\n"})
        else:
            (repo / ".github/workflows/ci.yml").unlink()
        assert pr(repo)["pr.workflows"].status == MISSING

    def test_a_workflow_swerepo_added_needs_no_adr(self, repo: Path):
        written = "jobs: {ci-ok: {}}\n"
        state = State.new(version="0.0.1")
        state.set_file(
            ".github/workflows/swerepo-ci.yml", Record("ci/python@1", fingerprint(written), fingerprint(written))
        )
        state.save(repo, running="0.0.1")
        make(repo, {".github/workflows/swerepo-ci.yml": written})  # swerepo init's PR adds it
        assert "pr.workflows" not in pr(repo)
        make(repo, {".github/workflows/swerepo-ci.yml": written + "# a person's edit\n"})
        assert pr(repo)["pr.workflows"].status == MISSING

    def test_swerepos_own_change_needs_no_adr(self, repo: Path):
        written = "jobs: {from_swerepo: {}}\n"
        state = State.new(version="0.0.1")
        state.set_file(".github/workflows/ci.yml", Record("ci/python@1", fingerprint(written), fingerprint(written)))
        state.save(repo, running="0.0.1")
        make(repo, {".github/workflows/ci.yml": written})
        assert "pr.workflows" not in pr(repo)
        make(repo, {".github/workflows/ci.yml": written + "# and a person's edit\n"})
        assert pr(repo)["pr.workflows"].status == MISSING


class TestWhoIsSkipped:
    def test_an_exempt_author(self, repo: Path):
        make(repo, {"app.py": "print('bump')\n"})
        findings = pr(repo, author="dependabot[bot]")
        assert list(findings) == ["pr.skipped"] and findings["pr.skipped"].status == NOT_CHOSEN

    def test_exempt_authors_from_the_state_file(self, repo: Path):
        (repo / FILE_NAME).write_text('standard = 1\nswerepo = "0.0.1"\n[pr]\nexempt_authors = ["renovate[bot]"]\n')
        assert "pr.skipped" in pr(repo, author="renovate[bot]")
        assert "pr.skipped" not in pr(repo, author="dependabot[bot]")

    def test_lockfile_only_changes(self, repo: Path):
        make(repo, {"uv.lock": "version = 1\n"})
        assert list(pr(repo)) == ["pr.skipped"]

    def test_other_ecosystems_lockfiles(self, repo: Path):
        make(repo, {"Cargo.lock": "x\n", "web/go.sum": "x\n", "Gemfile.lock": "x\n"})
        assert pr(repo)["pr.skipped"].status == NOT_CHOSEN

    def test_no_changes(self, repo: Path):
        assert pr(repo)["pr.changes"].status == OK


def test_warn_only_mode_doesnt_block(repo: Path):
    (repo / FILE_NAME).write_text('standard = 1\nswerepo = "0.0.1"\n[pr]\nenforce = false\n')
    report = run_check(repo, only=["docs"], base="main")
    finding = next(f for f in report.findings if f.item == "pr.progress")
    assert finding.status == MISSING and not finding.blocking
    assert "(warning)" in report.render_text()


def test_an_unknown_base_is_wrong_usage(repo: Path):
    with pytest.raises(UsageError, match="no-such-branch"):
        run_check(repo, base="no-such-branch")


def test_base_needs_a_git_repository(tmp_path: Path):
    with pytest.raises(UsageError, match="needs a git repository"):
        run_check(tmp_path, base="main")


def test_untracking_an_old_progress_entry_is_not_a_new_one(repo: Path):
    git(repo, "rm", "-q", "--cached", "docs/progress/20260101-start.md")
    make(repo, {"app.py": "print('changed')\n"})
    assert pr(repo)["pr.progress"].status == MISSING


def test_when_git_cant_list_the_changes_it_says_so(repo: Path, monkeypatch):
    make(repo, {"app.py": "print('changed')\n"})

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("swerepo.prrules.shutil.copyfile", fail)
    findings = pr(repo)
    assert findings["pr.changes"].status == UNKNOWN and "pr.progress" not in findings


def test_base_runs_at_the_repository_top(repo: Path):
    make(repo, {"services/api/README.md": "x\n"})
    with pytest.raises(UsageError, match="top level"):
        run_check(repo / "services/api", base="main")


def test_a_project_that_isnt_a_table_is_unknown(repo: Path):
    make(repo, {"pyproject.toml": 'project = "oops"\n'})
    assert pr(repo)["pr.dependencies"].status == UNKNOWN


@pytest.mark.parametrize("same", [True, False])
def test_untracking_a_binary_file_compares_bytes(repo: Path, same: bool):
    blob, path = b"\x89PNG\r\n\x1a\n\xff\xfe", ".github/workflows/data.bin"
    (repo / path).write_bytes(blob)
    commit(repo, "add a binary file")
    git(repo, "branch", "-f", "main")  # the file is on main
    git(repo, "rm", "-q", "--cached", path)
    if not same:
        (repo / path).write_bytes(blob[:-1] + b"\xfd")  # also undecodable: must not compare equal as text
    make(repo, {"docs/progress/20260102-x.md": "x\n"})
    findings = pr(repo)  # bytes that aren't UTF-8 don't crash
    assert ("pr.workflows" in findings) is not same  # untracked but unchanged is no change; changed is "M"
