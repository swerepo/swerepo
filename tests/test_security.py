"""`swerepo init` and `check` for the `security` component, and the privacy scan (spec §6.4; ADR-20261122-a48e).

Personal data and secrets in these tests are assembled at run time, so this file never holds them literally
(the repository's own privacy rule scans it)."""

import datetime
from pathlib import Path

import pytest
from repo_helpers import commit, git, git_init, make
from typer.testing import CliRunner

from swerepo import privacy
from swerepo.check import MISSING, OK, run_check
from swerepo.cli import app
from swerepo.init import CREATE, KEEP, NOTE, apply, contact_text, make_plan

TODAY = datetime.date(2026, 11, 22)
AT = "@"
PERSONAL = "dev" + AT + "mail.test.com"
HOME = "/" + "Users/alice/project"
PRIVACY_WORKFLOW = ".github/workflows/swerepo-privacy.yml"


def init(root: Path, **kwargs):
    plan = make_plan(root, only=["security"], today=TODAY, hosts=[], **kwargs)
    apply(plan, root)
    return plan


def notes(plan) -> list[str]:
    return [a.note for a in plan.actions if a.verb == NOTE]


def security(root: Path) -> dict:
    return {f.item: f for f in run_check(root, only=["security"]).findings}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    git_init(tmp_path)
    make(tmp_path, {"pyproject.toml": '[project]\nname = "invoices"\n', "README.md": "# invoices\n"})
    return tmp_path


class TestPolicy:
    def test_private_reporting_with_a_github_remote(self, project: Path):
        git(project, "remote", "add", "origin", "https://github.com/acme/invoices.git")
        plan = init(project)
        assert "on this repository's **Security** tab" in (project / "SECURITY.md").read_text()
        assert any("turn on GitHub's private vulnerability reporting" in n for n in notes(plan))

    def test_a_placeholder_without_one_and_an_email_when_given(self, project: Path):
        plan = make_plan(project, only=["security"], hosts=[])
        policy = next(a for a in plan.actions if a.path == "SECURITY.md")
        assert policy.verb == CREATE and "still to be decided" in policy.content and plan.contact_question
        address = "security" + AT + "invoices.test.com"
        init(project, contact=address)
        assert f"Please email {address}." in (project / "SECURITY.md").read_text()
        assert security(project)["security.privacy-scan"].status == OK  # the published contact is allowed
        assert contact_text("not an address") == contact_text("placeholder")

    def test_an_existing_policy_is_kept(self, project: Path):
        make(project, {".github/SECURITY.md": "# Ours\n"})
        commit(project)
        plan = init(project)
        assert next(a for a in plan.actions if a.path == ".github/SECURITY.md").verb == KEEP
        assert not (project / "SECURITY.md").exists() and security(project)["security.policy"].status == OK


class TestWorkflowAndIgnoredFiles:
    def test_the_privacy_workflow_needs_an_installable_swerepo(self, project: Path):
        plan = init(project)
        assert any(n.startswith(f"{PRIVACY_WORKFLOW} not written: needs a released SWERepo") for n in notes(plan))
        finding = security(project)["security.workflow"]
        assert finding.status == MISSING and "--with-governance" in finding.message
        init(project, with_governance=True)
        text = (project / PRIVACY_WORKFLOW).read_text()
        assert "swerepo check --only security --ci" in text and "@@" not in text
        assert security(project)["security.workflow"].status == OK

    def test_gitignore_gains_a_block_and_keeps_its_lines(self, project: Path):
        make(project, {".gitignore": "dist/\n"})
        init(project)
        text = (project / ".gitignore").read_text()
        assert text.startswith("dist/\n\n# swerepo:begin\n") and ".env\n.env.*\n!.env.example\n" in text
        assert security(project)["security.gitignore"].status == OK
        assert not init(project).changes  # a rerun changes nothing


class TestPrivacyScan:
    def test_findings_name_the_file_and_line_never_what_was_found(self, project: Path):
        key = "AKIA" + "ABCDEFGHIJKLMNOP"
        make(project, {"notes.md": f"# Notes\nmail {PERSONAL}\npath {HOME}\n", "config.py": f"KEY = '{key}'\n"})
        commit(project)
        plan = make_plan(project, only=["security"], hosts=[])
        scan = next(n for n in notes(plan) if n.startswith("privacy scan"))
        assert "1 AWS access key, 1 email address, 1 home-folder path" in scan
        assert "config.py:1, notes.md:2, notes.md:3" in scan
        result = CliRunner().invoke(app, ["check", "--path", str(project), "--only", "security", "--json"])
        assert result.exit_code == 1 and "notes.md:2" in result.output
        for secret in (PERSONAL, HOME, key, "alice"):
            assert secret not in result.output and secret not in scan

    def test_untracked_files_git_would_add_are_scanned_and_ignored_ones_not(self, project: Path):
        make(project, {"draft.md": f"{PERSONAL}\n", ".gitignore": "local/\n", "local/mine.md": f"{PERSONAL}\n"})
        hits = privacy.scan(project)
        assert [h.where for h in hits] == ["draft.md:1"]

    def test_allowances(self, project: Path):
        declared = "maintainer" + AT + "invoices.test.com"
        make(
            project,
            {
                "pyproject.toml": f'[project]\nname = "x"\nauthors = [{{email = "{declared}"}}]\n',
                "a.md": f"{declared}\n{PERSONAL}  # swerepo: allow-privacy\nsomeone{AT}users.noreply.github.com\n",
                "b.md": f"git{AT}github.com:acme/x.git\n/" + "Users/me/code\nyou" + AT + "example.org\n",
                "tests/fixtures/data.md": f"{PERSONAL}\n",
                "image.bin": f"\0{PERSONAL}",
            },
        )
        assert [h.where for h in privacy.scan(project, ["tests/fixtures/**"])] == []
        assert [h.where for h in privacy.scan(project, ["tests/fixtures"])] == []  # a folder names what's in it
        assert [h.where for h in privacy.scan(project)] == ["tests/fixtures/data.md:1"]
        make(project, {".swerepo.toml": 'standard = 1\nswerepo = "0.0.1"\n[privacy]\nallow_paths = ["tests/**"]\n'})
        assert security(project)["security.privacy-scan"].status == OK

    @pytest.mark.parametrize(
        ("line", "kind"),
        [
            ("-----BEGIN RSA " + "PRIVATE KEY-----", "private key"),
            ("-----BEGIN " + "PRIVATE KEY-----", "private key"),
            ("token = 'gh" + "p_" + "a" * 36 + "'", "GitHub token"),
            ("xox" + "b-1234567890-abcdef", "Slack token"),
            ("sk_" + "live_" + "a" * 24, "Stripe live key"),
            ("AI" + "za" + "A" * 35, "Google API key"),
            ("sk-" + "ant-" + "a" * 30, "Anthropic API key"),
            ("C:" + "\\\\Users\\\\alice\\\\x", "home-folder path"),
            ("/" + "home/alice/.config", "home-folder path"),
        ],
    )
    def test_kinds(self, line: str, kind: str):
        assert privacy.line_kinds("x.py", line, set()) == [kind]

    @pytest.mark.parametrize(
        "line",
        ["AKIA_short", "ghp_short", "sk-not-a-key", "/" + "home/user/x", "C:" + "\\Users\\you", "x" + AT + "1.2.3"],
    )
    def test_ordinary_text_isnt_flagged(self, line: str):
        assert privacy.line_kinds("x.py", line, set()) == []

    def test_a_summary_names_at_most_ten_places(self):
        hits = [privacy.Hit("email address", f"f{i}.md", 1) for i in range(12)]
        assert privacy.summary(hits).endswith("f9.md:1, and 2 more)") and privacy.summary(hits).startswith("12 email")


class TestGeminiReviewRound1:
    """Phase 4 review findings (CODE_REVIEW.md), each reproduced before the fix."""

    @pytest.mark.parametrize(
        ("path", "glob", "allowed"),
        [
            ("docs/x.md", "docs/*.md", True),
            ("docs/sub/x.md", "docs/*.md", False),  # `*` stays within a folder
            ("a/b/x.md", "*.md", False),
            ("tests/data.md", "tests/**/data.md", True),  # `**` may be no folder at all
            ("tests/a/b/data.md", "tests/**/data.md", True),
            ("fixtures/data.md", "**/fixtures/**", True),
            ("tests/fixtures/x.md", "tests/fixtures", True),  # a folder covers what's in it
            ("tests/fixtures/x.md", "./tests/fixtures/", True),
            ("tests/fixturesx.md", "tests/fixtures", False),
        ],
    )
    def test_p4_f05_allow_paths_globs_respect_folders(self, path: str, glob: str, allowed: bool):
        assert privacy.allowed_path(path, [glob]) is allowed

    @pytest.mark.parametrize("policy", [".github/SECURITY.md", "docs/SECURITY.md"])
    def test_p4_f05_the_contact_in_any_policy_place_is_allowed(self, project: Path, policy: str):
        make(project, {policy: f"Email security{AT}invoices.test.com.\nNot {HOME}.\n"})
        hits = privacy.scan(project)
        assert [(h.path, h.kind) for h in hits] == [(policy, "home-folder path")]  # only the email is allowed

    def test_p4_f06_a_linter_only_in_pre_commit_must_skip_seamspec_there_too(self, project: Path):
        hooks = "repos:\n- repo: x\n  hooks:\n  - id: black\n"
        make(project, {".seamspec/config.toml": 'mode = "enforced"\n', ".pre-commit-config.yaml": hooks})
        finding = {f.item: f for f in run_check(project, only=["ci"]).findings}["ci.seamspec-excluded"]
        assert finding.status == "changed" and finding.message.startswith("black would touch")
        make(project, {".pre-commit-config.yaml": hooks + "    exclude: ^\\.seamspec/\n"})
        finding = {f.item: f for f in run_check(project, only=["ci"]).findings}["ci.seamspec-excluded"]
        assert finding.status == OK and finding.message == "black skips .seamspec (their own settings)"

    def test_p4_f06_listed_projects_outside_detection_are_checked(self, project: Path):
        make(project, {"tools/gen/pyproject.toml": '[project]\nname = "gen"\n'})
        apply(make_plan(project, only=["ci"], hosts=[], projects=["tools/gen"]), project)
        workflow = project / ".github/workflows/swerepo-ci.yml"
        assert {f.item: f for f in run_check(project, only=["ci"]).findings}["ci.projects:tools/gen"].status == OK
        workflow.write_text(workflow.read_text().replace("lint-tools-gen:", "lint-other:"))
        finding = {f.item: f for f in run_check(project, only=["ci"]).findings}["ci.projects:tools/gen"]
        assert finding.status == MISSING and "--projects tools/gen" in finding.message  # the lint job alone counts

    def test_p4_f06_the_privacy_workflow_is_reported_once_with_its_path(self, project: Path):
        init(project, with_governance=True)
        found = [f for f in run_check(project, only=["security"]).findings if f.path == PRIVACY_WORKFLOW]
        assert len(found) == 1 and found[0].item == "security.workflow"

    @pytest.mark.parametrize(
        ("line", "kind"),
        [
            ("sk-" + "proj-" + "a" * 48, "OpenAI API key"),
            ("sk-" + "svcacct-" + "a" * 48, "OpenAI API key"),
            ("sk-" + "a" * 20 + "T3Blbk" + "FJ" + "b" * 20, "OpenAI API key"),
            ("pypi-" + "AgEIcHlwaS5vcmc" + "x" * 60, "PyPI token"),
            ("hf_" + "a" * 34, "Hugging Face token"),
        ],
    )
    def test_p4_f08_current_token_formats(self, line: str, kind: str):
        assert privacy.line_kinds("x.py", line, set()) == [kind]


class TestGeminiReviewRound2:
    """Phase 4 review, round 2 (CODE_REVIEW.md)."""

    @pytest.mark.parametrize("glob", ["*" * 30 + "b", "*a" * 20 + "*b", "**/" * 20 + "nope", "?" * 40 + "b"])
    def test_p4_f11_globs_take_linear_time(self, glob: str):
        import time

        started = time.perf_counter()
        for path in ("a" * 60 + ".py", "/".join(["d"] * 40) + "/" + "a" * 60 + ".py"):
            assert not privacy.allowed_path(path, [glob])
        assert time.perf_counter() - started < 0.5  # exponential backtracking took seconds at a third of this size

    @pytest.mark.parametrize("glob", ["docs//fixtures", "docs/./fixtures", "./docs/fixtures/", "docs/**/**/fixtures"])
    def test_p4_f11_empty_and_dot_parts_are_dropped(self, glob: str):
        assert privacy.allowed_path("docs/fixtures/x.md", [glob])

    @pytest.mark.parametrize("glob", ["", ".", "/", "./"])
    def test_p4_f11_an_empty_glob_allows_nothing(self, glob: str):
        assert not privacy.allowed_path("docs/x.md", [glob])


class TestCopilotReviewPR8:
    """Copilot's review of PR #8."""

    @pytest.mark.parametrize("end", ["-", "_", "A"])
    def test_a_google_key_may_end_in_any_key_character(self, end: str):
        assert privacy.line_kinds("x.py", '"AI' + "za" + "A" * 34 + end + '"', set()) == ["Google API key"]
        assert privacy.line_kinds("x.py", '"AI' + "za" + "A" * 36 + '"', set()) == []  # too long: not this format
