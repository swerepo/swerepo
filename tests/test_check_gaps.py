"""Two `check` gaps found while dogfooding (review P8-K): the tools CI runs that `uv sync` won't install, and code
owners GitHub doesn't know. GitHub is a fake `gh` on PATH: nothing leaves the test."""

import datetime
import json
import re
from pathlib import Path

import pytest
from fake_gh import FakeGh
from repo_helpers import commit, git, git_init, make
from typer.testing import CliRunner

from swerepo import github
from swerepo.check import MISSING, OK, OWNER_FIX, UNKNOWN, Finding, _without_repeats, run_check
from swerepo.cli import app
from swerepo.init import NOTE, apply, make_plan

TODAY = datetime.date(2026, 11, 26)
BARE = '[project]\nname = "app"\nrequires-python = ">=3.12"\n'
TOOLS = BARE + '[dependency-groups]\ndev = ["pytest", "ruff"]\n'
WORKFLOW = ".github/workflows/swerepo-ci.yml"
CODEOWNERS = ".github/CODEOWNERS"
SLUG = "acme/app"
PERMISSION = f"GET repos/{SLUG}/collaborators/{{}}/permission"


def project_at(root: Path, pyproject: str = BARE, **files: str) -> Path:
    git_init(root)
    make(root, {"pyproject.toml": pyproject, "uv.lock": "version = 1\n", "tests/test_app.py": "def test_x(): pass\n",
                **files})  # fmt: skip
    return root


def plan(root: Path, only: list[str], **kwargs):
    return make_plan(root, today=TODAY, only=only, hosts=kwargs.pop("hosts", []), **kwargs)


def init(root: Path, only: list[str], **kwargs):
    found = plan(root, only, **kwargs)
    apply(found, root)
    return found


def notes(found, component: str) -> list[str]:
    return [a.note for a in found.actions if a.component == component and a.verb == NOTE]


def by_item(root: Path, **kwargs) -> dict[str, Finding]:
    return {f.item: f for f in run_check(root, **kwargs).findings}


# --- Gap 1: the tools CI runs that uv sync won't install ---------------------------------------------------------


class TestCiTools:
    def test_root_tools_missing_are_a_warning_in_init_s_words(self, tmp_path: Path):
        root = project_at(tmp_path / "app")
        written = init(root, ["ci"])
        note = next(n for n in notes(written, "ci") if n.startswith("not among"))
        finding = by_item(root, only=["ci"])["ci.tools"]
        assert finding.status == MISSING and not finding.blocking and finding.path is None
        assert (
            finding.message
            == note
            == ("not among the project's installed dependencies: pytest, ruff (uv add --dev pytest ruff)")
        )
        assert finding.fix == "uv add --dev pytest ruff"
        assert run_check(root, only=["ci"]).exit_code == 0

    def test_declared_tools_aren_t_reported(self, tmp_path: Path):
        root = project_at(tmp_path / "app", TOOLS)
        init(root, ["ci"])
        assert "ci.tools" not in by_item(root, only=["ci"])

    @pytest.mark.parametrize(
        "declared",
        [
            '[dependency-groups]\ntest = ["pytest", "ruff"]\n[tool.uv]\ndefault-groups = ["test"]\n',
            '[dependency-groups]\ndev = [{include-group = "lint"}, "pytest"]\nlint = ["ruff"]\n',
        ],
    )
    def test_default_groups_and_include_group_count(self, tmp_path: Path, declared: str):
        root = project_at(tmp_path / "app", BARE + declared)
        init(root, ["ci"])
        assert "ci.tools" not in by_item(root, only=["ci"])

    def test_an_optional_extra_is_named(self, tmp_path: Path):
        pyproject = BARE + '[project.optional-dependencies]\ndev = ["pytest"]\n[dependency-groups]\ndev = ["ruff"]\n'
        root = project_at(tmp_path / "app", pyproject)
        init(root, ["ci"])
        message = by_item(root, only=["ci"])["ci.tools"].message
        assert message.startswith("not among the project's installed dependencies: pytest (uv add --dev pytest)")
        assert "pytest is in the optional extra `dev`, which uv sync doesn't install" in message

    def test_kept_linters_are_named_and_ruff_isn_t(self, tmp_path: Path):
        pyproject = BARE + '[tool.black]\nline-length = 100\n[dependency-groups]\ndev = ["pytest"]\n'
        root = project_at(tmp_path / "app", pyproject)
        init(root, ["ci"])
        finding = by_item(root, only=["ci"])["ci.tools"]
        assert "black" in finding.message and "ruff" not in finding.message and finding.fix == "uv add --dev black"

    def test_gradual_ruff_needs_ruff(self, tmp_path: Path):
        root = project_at(tmp_path / "app", BARE + '[dependency-groups]\ndev = ["pytest"]\n')
        commit(root, "history")  # an existing codebase: gradual ruff
        init(root, ["ci"])
        assert by_item(root, only=["ci"])["ci.tools"].fix == "uv add --dev ruff"

    def test_a_listed_project_gets_its_own_finding_and_runnable_fix(self, tmp_path: Path):
        root = project_at(tmp_path / "app", TOOLS, **{"api/pyproject.toml": BARE, "api/tests/test_api.py": "x = 1\n"})
        written = init(root, ["ci"], projects=["api"])
        found = by_item(root, only=["ci"])
        finding = found["ci.tools.api"]
        assert finding.path == "api" and not finding.blocking and "ci.tools" not in found
        assert finding.fix == "uv add --directory api --dev pytest ruff"
        assert finding.message in notes(written, "ci")

    def test_a_makefile_doesn_t_change_what_ci_runs(self, tmp_path: Path):
        root = project_at(tmp_path / "app", Makefile="test:\n\tpytest\nlint:\n\truff check .\n")
        init(root, ["ci"])
        assert by_item(root, only=["ci"])["ci.tools"].status == MISSING

    def test_a_project_uv_can_t_install_is_left_out(self, tmp_path: Path):
        root = project_at(tmp_path / "app")
        init(root, ["ci"])
        (root / "uv.lock").unlink()
        make(root, {"poetry.lock": "# poetry\n"})
        assert "ci.tools" not in by_item(root, only=["ci"])

    def test_an_edited_workflow_is_left_out(self, tmp_path: Path):
        root = project_at(tmp_path / "app")
        init(root, ["ci"])
        text = (root / WORKFLOW).read_text()
        (root / WORKFLOW).write_text(text.replace("uv sync --locked", "uv sync --locked --all-extras"))
        assert "ci.tools" not in by_item(root, only=["ci"])

    def test_newer_action_pins_still_count_as_unchanged(self, tmp_path: Path):  # review P8-K06
        root = project_at(tmp_path / "app")
        init(root, ["ci"])
        text = (root / WORKFLOW).read_text()
        newer = r"\g<1>" + "f" * 40 + r"\g<2>99.0.0"
        bumped, count = re.subn(r"(uses: actions/checkout@)[0-9a-f]{40}(  # v)[0-9.]+", newer, text)
        assert count
        (root / WORKFLOW).write_text(bumped)
        report = run_check(root, only=["ci"])
        assert {f.item: f for f in report.findings}["ci.tools"].status == MISSING
        assert not [f for f in report.findings if f.path == WORKFLOW and "changed by you" in f.message]  # pins only

    def test_check_ci_warns_in_github_actions(self, tmp_path: Path, monkeypatch):
        root = project_at(tmp_path / "app")
        init(root, ["ci"])
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        result = CliRunner().invoke(app, ["check", "--path", str(root), "--only", "ci", "--ci"])
        assert result.exit_code == 0, result.output
        lines = result.output.splitlines()
        assert any(line.startswith("::warning ") and "ci: not among the project's" in line for line in lines)
        assert not any(line.startswith("::error ") for line in lines)

    def test_a_warning_never_hides_a_blocking_record_finding(self, tmp_path: Path):  # review P8-K04
        root = project_at(tmp_path / "app")
        init(root, ["ci"])
        pyproject = (root / "pyproject.toml").read_text()
        (root / "pyproject.toml").write_text(pyproject[: pyproject.index("# swerepo:begin")])
        report = run_check(root, only=["ci"])
        found = {f.item: f for f in report.findings}
        assert found["ci.tools"].status == MISSING and not found["ci.tools"].blocking
        removed = found["ci.block:pyproject.toml"]
        assert removed.status == MISSING and removed.blocking and report.exit_code == 1

    def test_without_repeats_keeps_a_blocking_record_behind_a_warning(self):
        warning = Finding("ci", "ci.x", MISSING, "w", "pyproject.toml", blocking=False)
        record = Finding("ci", "ci.block:pyproject.toml", MISSING, "removed", "pyproject.toml", blocking=True)
        assert _without_repeats([warning], [record]) == [record]
        blocking = Finding("ci", "ci.y", MISSING, "b", "pyproject.toml", blocking=True)
        assert _without_repeats([blocking], [record]) == []  # one line per missing file, as before
        ok = Finding("ci", "ci.z", OK, "ok", "pyproject.toml")
        assert _without_repeats([ok], [record]) == []  # a ✓ still de-duplicates, as before


class TestAgentsTools:
    def test_agents_without_ci_get_init_s_agents_note(self, tmp_path: Path):
        root = project_at(tmp_path / "app")
        written = init(root, ["agents"], hosts=["claude"])
        finding = by_item(root, only=["agents"])["agents.tools"]
        assert finding.status == MISSING and not finding.blocking
        assert finding.message in notes(written, "agents") and finding.fix == "uv add --dev pytest ruff"

    def test_said_once_ci_speaks_for_them(self, tmp_path: Path):
        root = project_at(tmp_path / "app")
        init(root, ["agents", "ci"], hosts=["claude"])
        found = by_item(root)
        assert "ci.tools" in found and "agents.tools" not in found
        assert "agents.tools" in by_item(root, only=["agents"])  # ci not checked in this run: agents speak

    def test_an_edited_workflow_hands_back_to_agents(self, tmp_path: Path):
        root = project_at(tmp_path / "app")
        init(root, ["agents", "ci"], hosts=["claude"])
        (root / WORKFLOW).write_text((root / WORKFLOW).read_text() + "# mine\n")
        found = by_item(root)
        assert "ci.tools" not in found and "agents.tools" in found

    def test_an_edited_agents_block_is_left_out(self, tmp_path: Path):
        root = project_at(tmp_path / "app")
        init(root, ["agents"], hosts=["claude"])
        text = (root / "AGENTS.md").read_text()
        (root / "AGENTS.md").write_text(text.replace("- Test: `uv run pytest`", "- Test: `uv run --all-extras pytest`"))
        assert "agents.tools" not in by_item(root, only=["agents"])

    def test_a_makefile_runs_its_own_tools(self, tmp_path: Path):
        root = project_at(tmp_path / "app", Makefile="test:\n\tpytest\nlint:\n\truff check .\n")
        init(root, ["agents"], hosts=["claude"])
        assert "agents.tools" not in by_item(root, only=["agents"])


def _merged(root: Path, path: str, text: str, kind: str = "file") -> None:
    """The file as `update --merge` leaves it: the person's edit merged in, the record's `written` following it while
    `rendered` stays SWERepo's."""
    from swerepo.blocks import file_fingerprint
    from swerepo.fingerprint import HTML, find_block, fingerprint
    from swerepo.state import Record, State

    (root / path).write_text(text)
    state = State.load(root)
    records = state.files() if kind == "file" else state.blocks()
    old = records[path]
    if kind == "file":
        written = file_fingerprint(text, old.template)
    else:
        written = fingerprint(find_block(text, style=HTML).content)
    (state.set_file if kind == "file" else state.set_block)(
        path, Record(old.template, old.rendered, written, old.inputs)
    )
    state.save(root)


class TestCopilotReviewPR25:
    """Copilot's review of PR #25."""

    def test_a_merged_workflow_or_agents_block_is_left_out(self, tmp_path: Path):
        root = project_at(tmp_path / "app")
        init(root, ["agents", "ci"], hosts=["claude"])
        workflow = (root / WORKFLOW).read_text().replace("uv sync", "uv sync --all-extras")
        _merged(root, WORKFLOW, workflow)  # an install step of the person's, merged in by update
        found = by_item(root)
        assert "ci.tools" not in found and "agents.tools" in found  # the merged workflow may install them
        agents = (root / "AGENTS.md").read_text().replace("- Install: `uv sync`", "- Install: `uv sync --all-extras`")
        _merged(root, "AGENTS.md", agents, kind="block")
        assert "agents.tools" not in by_item(root)

    def test_agents_md_s_own_tools_are_said_beside_ci_s(self, tmp_path: Path):
        root = project_at(tmp_path / "app", TOOLS)  # pytest and ruff installed: CI's tools are all there
        init(root, ["agents", "ci"], hosts=["claude"])
        text = (root / "AGENTS.md").read_text()
        lint = re.search(r"^- Lint: .*$", text, re.MULTILINE).group(0)
        recorded = text.replace(lint, "- Lint: `uv run black --check .`")  # an older record: black, as init wrote it
        _merged(root, "AGENTS.md", recorded, kind="block")
        from swerepo.state import Record, State

        state = State.load(root)
        old = state.blocks()["AGENTS.md"]
        state.set_block("AGENTS.md", Record(old.template, old.written, old.written, old.inputs))  # as rendered then
        state.save(root)
        found = by_item(root)
        assert "ci.tools" not in found
        assert found["agents.tools"].fix == "uv add --dev black"  # CI runs ruff; AGENTS.md still says black

    @pytest.mark.parametrize(("groups", "fix", "said"), [
        ('[tool.uv]\ndefault-groups = ["test"]\n', "uv add --group test ruff", ""),
        ('[tool.uv]\ndefault-groups = "all"\n', "uv add --dev ruff", ""),
        ('[tool.uv]\ndefault-groups = []\n', "uv add --dev pytest ruff", "default-groups leaves the dev group out"),
    ])  # fmt: skip
    def test_the_fix_goes_to_a_group_uv_sync_installs(self, tmp_path: Path, groups: str, fix: str, said: str):
        pyproject = BARE + '[dependency-groups]\ntest = ["pytest"]\n' + groups
        root = project_at(tmp_path / "app", pyproject)
        written = init(root, ["ci"])
        finding = by_item(root, only=["ci"])["ci.tools"]
        assert finding.fix == fix and fix in finding.message and said in finding.message
        assert finding.message in notes(written, "ci")  # init's plan says the same

    def test_a_listed_project_s_fix_uses_its_own_group(self, tmp_path: Path):
        root = project_at(tmp_path / "app", TOOLS)
        make(root, {"svc/pyproject.toml": BARE.replace('"app"', '"svc"')
                    + '[dependency-groups]\ntest = ["pytest"]\n[tool.uv]\ndefault-groups = ["test"]\n'})  # fmt: skip
        init(root, ["ci"], projects=["svc"])
        assert by_item(root, only=["ci"])["ci.tools.svc"].fix == "uv add --directory svc --group test ruff"

    def test_a_group_that_isn_t_a_name_is_never_used_or_repeated(self, tmp_path: Path):
        bad = "ops" + "@" + "acme.test"
        groups = f'[dependency-groups]\ntest = ["pytest"]\n[tool.uv]\ndefault-groups = ["{bad}", "test"]\n'
        root = project_at(tmp_path / "app", BARE + groups)
        init(root, ["ci"])
        finding = by_item(root, only=["ci"])["ci.tools"]
        assert (
            finding.fix == "uv add --group test ruff" and bad not in finding.message and "acme" not in finding.message
        )

    def test_an_extra_s_key_that_isn_t_a_name_is_never_repeated(self, tmp_path: Path):
        key = "dev" + "@" + "acme.test"
        root = project_at(tmp_path / "app", BARE + f'[project.optional-dependencies]\n"{key}" = ["pytest"]\n')
        init(root, ["ci"])
        message = by_item(root, only=["ci"])["ci.tools"].message
        assert "pytest is in an optional extra, which uv sync doesn't install" in message
        assert key not in message and "acme" not in message


# --- Gap 2: code owners GitHub doesn't know ------------------------------------------------------------------------


def block(*rules: str, after: str = "") -> str:
    return "# swerepo:begin\n" + "".join(f"{rule}\n" for rule in rules) + "# swerepo:end\n" + after


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return project_at(tmp_path / "app", TOOLS)


def on_github(tmp_path: Path, monkeypatch, root: Path, owner: str = "dev", kind: str = "User") -> FakeGh:
    git(root, "remote", "add", "origin", f"https://github.com/{SLUG}.git")
    fake = FakeGh(tmp_path / "fake-gh", monkeypatch)
    fake.set(f"GET repos/{SLUG}", {"owner": {"login": owner, "type": kind}, "default_branch": "main"})
    fake.set(f"GET repos/{SLUG}/rulesets", [])
    fake.set(f"GET repos/{SLUG}/dependency-graph/sbom", {"sbom": {}})
    return fake


@pytest.fixture
def gh(tmp_path: Path, monkeypatch, repo: Path) -> FakeGh:
    return on_github(tmp_path, monkeypatch, repo)


@pytest.fixture
def org(tmp_path: Path, monkeypatch, repo: Path) -> FakeGh:
    return on_github(tmp_path, monkeypatch, repo, "acme", "Organization")


def owners(root: Path, *rules: str, after: str = "") -> None:
    make(root, {CODEOWNERS: block(*rules, after=after)})


def live(root: Path) -> list[Finding]:
    return [f for f in run_check(root, only=["github"], read_github=True).findings if f.item == "github.code-owner"]


def permission(login: str, value: str, kind: str = "User") -> dict:
    pushes = value in ("admin", "write")
    return {"permission": value, "user": {"login": login, "type": kind, "permissions": {"push": pushes}}}


def gets(fake: FakeGh) -> list[str]:
    """The path of every `gh api` call."""
    found = []
    for call in fake.calls():
        if call["args"][:1] == ["api"]:
            found.append(next(a for a in call["args"][1:] if a.startswith(("repos/", "orgs/", "users/"))))
    return found


def accepts(call: dict) -> list[str]:
    return [a for a in call["args"] if a.startswith("Accept:")]


class TestCodeOwnerOnGitHub:
    def test_an_unknown_user_is_blocking(self, repo: Path, gh: FakeGh):
        owners(repo, "/.github/ @ghost")
        gh.fail(PERMISSION.format("ghost"), 404, "ghost is not a user")  # GitHub's 404, not "Not Found" (P8-K07)
        [finding] = live(repo)
        assert finding.status == MISSING and finding.blocking and finding.fix == OWNER_FIX
        assert finding.message == ".github/CODEOWNERS: code owner @ghost: no such GitHub user"

    @pytest.mark.parametrize(
        ("answer", "reason"),
        [
            (permission("acme", "none", "Organization"), "an organisation"),
            (permission("reader", "read"), "no write access to this repository"),
        ],
    )
    def test_an_organisation_or_no_write_access_is_blocking(self, repo: Path, gh: FakeGh, answer: dict, reason: str):
        login = answer["user"]["login"]
        owners(repo, f"/.github/ @{login}")
        gh.set(PERMISSION.format(login), answer)
        [finding] = live(repo)
        assert finding.status == MISSING and finding.blocking and reason in finding.message

    @pytest.mark.parametrize("value", ["write", "admin"])
    def test_write_access_is_fine(self, repo: Path, gh: FakeGh, value: str):
        owners(repo, "/.github/ @writer")
        gh.set(PERMISSION.format("writer"), permission("writer", value))
        [finding] = live(repo)
        assert finding.status == OK and "@writer" in finding.message

    def test_the_repository_s_owner_needs_no_call_whatever_its_case(self, repo: Path, gh: FakeGh):
        owners(repo, "/.github/ @Dev")
        [finding] = live(repo)
        assert finding.status == OK and not [p for p in gets(gh) if "collaborators" in p or p.startswith("users/")]

    @pytest.mark.parametrize(
        ("user", "status", "blocking"),
        [
            (None, MISSING, True),  # users/{login} answers 404: no such user
            ({"login": "acme", "type": "Organization"}, MISSING, True),
            ({"login": "someone", "type": "User"}, UNKNOWN, False),  # exists; its access can't be read
        ],
    )
    def test_without_push_access_users_still_tells_existence(self, repo: Path, gh: FakeGh, user, status, blocking):
        login = user["login"] if user else "nobody"
        owners(repo, f"/.github/ @{login}")
        gh.fail(PERMISSION.format(login), 403, "Must have push access to view collaborator permission.")  # P8-K02
        if user:
            gh.set(f"GET users/{login}", user)
        [finding] = live(repo)
        assert finding.status == status and finding.blocking is blocking

    def test_a_server_error_can_t_tell(self, repo: Path, gh: FakeGh):
        owners(repo, "/.github/ @writer")
        gh.fail(PERMISSION.format("writer"), 502, "Bad Gateway")
        [finding] = live(repo)
        assert finding.status == UNKNOWN and "can't tell" in finding.message

    def test_a_team_on_a_user_s_repository_is_wrong_with_no_call(self, repo: Path, gh: FakeGh):
        owners(repo, "/.github/ @acme/maintainers")  # gh: a user's repository
        [finding] = live(repo)
        assert finding.status == MISSING and "can't own files here" in finding.message
        assert not [p for p in gets(gh) if p.startswith("orgs/")]

    def test_a_team_of_another_organisation(self, repo: Path, org: FakeGh):
        owners(repo, "/.github/ @other/maintainers")
        [finding] = live(repo)
        assert finding.status == MISSING and not [p for p in gets(org) if p.startswith("orgs/")]

    @pytest.mark.parametrize(("listed", "status"), [(True, MISSING), (False, UNKNOWN)])
    def test_a_team_s_404_is_settled_by_listing_teams(self, repo: Path, org: FakeGh, listed: bool, status: str):
        owners(repo, "/.github/ @ACME/maintainers")
        if listed:
            org.set("GET orgs/ACME/teams", [])
        else:
            org.fail("GET orgs/ACME/teams", 403, "Must have admin rights to Repository.")  # a non-member (P8-K01)
        [finding] = live(repo)
        assert finding.status == status
        assert ("no team by that name" in finding.message) is listed

    @pytest.mark.parametrize(
        ("team", "access", "status", "reason"),
        [
            ({"privacy": "secret"}, {"permissions": {"push": True}}, MISSING, "a secret team"),
            ({"privacy": "closed"}, None, MISSING, "has no access to this repository"),  # 404
            ({"privacy": "closed"}, {"permissions": {"push": False, "pull": True}}, MISSING, "no write access"),
            ({"privacy": "closed"}, {"permissions": {"push": True}}, OK, "code owner on GitHub"),
        ],
    )
    def test_a_team_needs_to_be_visible_with_write_access(self, repo: Path, org: FakeGh, team, access, status, reason):
        owners(repo, "/.github/ @acme/maintainers")
        org.set("GET orgs/acme/teams/maintainers", team)
        if access is not None:
            org.set(f"GET orgs/acme/teams/maintainers/repos/{SLUG}", access)
        [finding] = live(repo)
        assert finding.status == status and reason in finding.message, finding.message
        api = [c for c in org.calls() if c["args"][:1] == ["api"]]
        assert all(len(accepts(c)) == 1 for c in api)  # exactly one Accept header per call (P8-K06)
        if access is not None and team["privacy"] != "secret":  # the media type that returns the team's permissions
            team_call = next(c for c in api if f"maintainers/repos/{SLUG}" in " ".join(c["args"]))
            assert accepts(team_call) == [f"Accept: {github.REPOSITORY_JSON}"]

    def test_check_reads_only_and_ci_doesn_t_call(self, repo: Path, gh: FakeGh):
        owners(repo, "/.github/ @ghost", "/docs/ @acme/x")
        gh.fail(PERMISSION.format("ghost"), 404, "ghost is not a user")
        run_check(repo, only=["github"], read_github=True)
        assert gh.methods() and set(gh.methods()) == {"GET"}
        before = len(gh.calls())
        result = CliRunner().invoke(app, ["check", "--path", str(repo), "--only", "github", "--ci"])
        assert result.exit_code in (0, 1) and len(gh.calls()) == before

    def test_not_logged_in_looks_nothing_up_and_says_so(self, repo: Path, gh: FakeGh):
        owners(repo, "/.github/ @ghost")
        gh.set("logged_in", False)
        found = {f.item: f for f in run_check(repo, only=["github"], read_github=True).findings}
        assert "github.code-owner" not in found and "code owner on GitHub: can't tell" in found["github.live"].message

    def test_an_email_owner_is_never_looked_up_or_printed(self, repo: Path, gh: FakeGh):
        owners(repo, "/.github/ owner@example.com")
        report = run_check(repo, only=["github"], read_github=True)
        assert not [f for f in report.findings if f.item == "github.code-owner"]
        assert "owner@example.com" not in json.dumps(report.to_dict()) + report.render_text()
        assert not [p for p in gets(gh) if "collaborators" in p or p.startswith("users/")]


class TestCodeOwnersBlock:  # read offline, so under --ci too (review P8-K03)
    def finding(self, root: Path) -> Finding:
        return by_item(root, only=["github"])["github.codeowners"]

    def test_comments_are_skipped(self, repo: Path, gh: FakeGh):
        owners(repo, "# was @login and @retired-user", "/.github/ @dev # was @retired")
        assert self.finding(repo).status == OK and live(repo)[0].status == OK
        assert not [p for p in gets(gh) if "retired" in p]

    @pytest.mark.parametrize(
        ("rules", "words"),
        [
            ((), "has no rules"),
            (("/.github/ @dev", "/docs/adr/"), "rule 2 of SWERepo's block names no owner"),
            (("/.github/ @Login",), "names @login, the code-owner question's example"),
            (("/.github/ @org/team",), "names @org/team"),
            (("/.github/ @bad@corp.example.com",), "rule 1 of SWERepo's block names an owner GitHub can't read"),
        ],
    )
    def test_a_broken_block_is_blocking(self, repo: Path, rules: tuple, words: str):
        owners(repo, *rules)
        finding = self.finding(repo)
        assert finding.status == MISSING and finding.blocking and words in finding.message, finding.message
        assert "bad@corp" not in finding.message

    def test_lines_after_the_block_don_t_mask_it(self, repo: Path):
        owners(repo, "/.github/ @login", after="/src/ @someone\n")
        finding = self.finding(repo)
        assert finding.status == MISSING and finding.blocking

    def test_a_fine_block_with_lines_after_it_is_changed_as_before(self, repo: Path):
        owners(repo, "/.github/ @dev", after="/src/ @someone\n")
        assert "can override governance owners" in self.finding(repo).message

    def test_the_example_fails_check_ci(self, repo: Path, monkeypatch):
        owners(repo, "/.github/ @login")
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        result = CliRunner().invoke(app, ["check", "--path", str(repo), "--only", "github", "--ci"])
        lines = result.output.splitlines()
        assert result.exit_code == 1 and any(line.startswith("::error ") and "@login" in line for line in lines)


# --- init, given a code owner ------------------------------------------------------------------------------------


def run_init(root: Path, *args: str, **kwargs):
    return CliRunner().invoke(app, ["init", "--path", str(root), "--only", "github", *args], **kwargs)


def terminal(monkeypatch) -> None:
    from swerepo import cli

    monkeypatch.setattr(cli, "_interactive", lambda: True)


class TestInitCodeOwner:
    def test_an_owner_github_says_doesn_t_exist_is_refused(self, repo: Path, gh: FakeGh):
        gh.fail(PERMISSION.format("ghost"), 404, "ghost is not a user")
        result = run_init(repo, "--yes", "--code-owner", "@ghost")
        assert result.exit_code == 2 and "no such GitHub user" in result.output
        assert not (repo / ".github").exists() and not (repo / ".swerepo.toml").exists()

    @pytest.mark.parametrize("owner", ["@login", "@Org/Team"])
    def test_the_question_s_examples_are_refused_offline(self, repo: Path, owner: str):
        result = run_init(repo, "--yes", "--code-owner", owner)
        assert result.exit_code == 2 and "question's example" in result.output and not (repo / ".github").exists()

    def test_a_team_of_another_org_is_refused(self, repo: Path, org: FakeGh):
        result = run_init(repo, "--yes", "--code-owner", "@other/team-a")
        assert result.exit_code == 2 and "can't own files here" in result.output

    def test_without_write_access_it_is_written_with_a_note(self, repo: Path, gh: FakeGh):
        gh.set(PERMISSION.format("reader"), permission("reader", "read"))
        found = plan(repo, ["github"], code_owner="@reader")
        assert any("code owner @reader: no write access" in n for n in notes(found, "github"))
        apply(found, repo)
        assert "@reader" in (repo / CODEOWNERS).read_text()

    @pytest.mark.parametrize("status", [403, 502])
    def test_an_owner_that_can_t_be_checked_is_accepted_with_a_note(self, repo: Path, gh: FakeGh, status: int):
        gh.fail(PERMISSION.format("alice"), status, "refused")
        gh.set("GET users/alice", {"login": "alice", "type": "User"})
        result = run_init(repo, "--yes", "--code-owner", "@alice")
        assert result.exit_code == 0, result.output
        assert "code owner @alice not checked on GitHub" in result.output
        assert "@alice" in (repo / CODEOWNERS).read_text()

    def test_offline_it_is_accepted_and_a_second_run_has_nothing_to_do(self, repo: Path):
        first = run_init(repo, "--yes", "--code-owner", "@alice")
        assert first.exit_code == 0 and "not checked on GitHub (needs gh, logged in)" in first.output
        second = run_init(repo, "--yes")
        assert second.exit_code == 0 and "Nothing to do." in second.output, second.output

    def test_the_repository_s_owner_needs_no_call(self, repo: Path, gh: FakeGh):
        assert run_init(repo, "--yes", "--code-owner", "@DEV").exit_code == 0
        assert not [p for p in gets(gh) if "collaborators" in p or p.startswith("users/")]

    def test_dry_run_only_reads(self, repo: Path, gh: FakeGh):
        gh.set(PERMISSION.format("writer"), permission("writer", "write"))
        assert run_init(repo, "--dry-run", "--code-owner", "@writer").exit_code == 0
        assert set(gh.methods()) == {"GET"} and any("collaborators/writer" in p for p in gets(gh))

    def test_a_terminal_asks_again_after_a_refused_answer(self, repo: Path, gh: FakeGh, monkeypatch):
        terminal(monkeypatch)
        gh.fail(PERMISSION.format("ghost"), 404, "ghost is not a user")
        result = run_init(repo, input="\n@ghost\n@login\n@dev\nn\n")
        assert result.exit_code == 0, result.output
        assert "@ghost: no such GitHub user" in result.output
        assert "@login: that's the question's example" in result.output
        assert "Code owner for governance files (@login or @org/team, or none)" in result.output

    @pytest.mark.parametrize("status", [403, 502])
    def test_a_terminal_accepts_what_it_can_t_check(self, repo: Path, gh: FakeGh, monkeypatch, status: int):
        terminal(monkeypatch)
        gh.fail(PERMISSION.format("alice"), status, "refused")
        gh.set("GET users/alice", {"login": "alice", "type": "User"})
        result = run_init(repo, input="\n@alice\nn\n")
        assert result.exit_code == 0, result.output
        assert "code owner @alice not checked on GitHub" in result.output


def record_example(root: Path) -> None:
    state = (root / ".swerepo.toml").read_text()
    (root / ".swerepo.toml").write_text(re.sub(r'code_owner = "[^"]*"', 'code_owner = "@login"', state))


class TestRecordedExample:  # the established repository's state (review P8-K05)
    def test_an_organisation_s_repository_offers_none(self, repo: Path, org: FakeGh, monkeypatch):
        assert run_init(repo, "--yes", "--mode", "team", "--code-owner", "@acme/maintainers").exit_code == 0
        record_example(repo)
        assert plan(repo, ["github"]).github_ask.get("code_owner") == "none"
        terminal(monkeypatch)
        result = run_init(repo, input="\nn\n")
        assert "(@login or @org/team, or none) [none]" in result.output, result.output

    def test_a_user_s_repository_offers_its_owner(self, repo: Path, gh: FakeGh):
        assert run_init(repo, "--yes", "--code-owner", "@dev").exit_code == 0
        record_example(repo)
        assert plan(repo, ["github"]).github_ask.get("code_owner") == "@dev"

    def test_without_a_terminal_nothing_is_written_from_it(self, repo: Path):
        assert run_init(repo, "--yes", "--mode", "team", "--code-owner", "@dev").exit_code == 0
        record_example(repo)
        (repo / CODEOWNERS).unlink()
        state, ruleset = (repo / ".swerepo.toml").read_bytes(), (repo / github.RULESET_FILE).read_bytes()
        result = run_init(repo, "--yes")
        assert result.exit_code == 0, result.output
        assert "the code-owner question's example" in result.output and not (repo / CODEOWNERS).exists()
        assert (repo / ".swerepo.toml").read_bytes() == state and (repo / github.RULESET_FILE).read_bytes() == ruleset
        assert "Nothing to do." in run_init(repo, "--yes").output

    def test_naming_a_real_owner_rewrites_the_block(self, repo: Path):
        assert run_init(repo, "--yes", "--code-owner", "@dev").exit_code == 0
        record_example(repo)
        assert run_init(repo, "--yes", "--code-owner", "@alice").exit_code == 0
        text = (repo / CODEOWNERS).read_text()
        assert "@alice" in text and "@dev" not in text


# --- GitHubError carries the status (review P8-K07) ----------------------------------------------------------------


class TestGitHubError:
    def test_status_from_json_or_stderr(self):
        assert github._status('{"message": "x is not a user", "status": "404"}', "") == 404
        assert github._status("", "gh: Must have push access. (HTTP 403)") == 403
        assert github._status("not json", "no status here") is None

    def test_a_404_with_another_message_is_not_found(self, repo: Path, gh: FakeGh):
        gh.fail("GET users/ghost", 404, "ghost is not a user")
        with pytest.raises(github.GitHubError) as raised:
            github.GitHub(SLUG).get("users/ghost")
        assert raised.value.not_found and raised.value.status == 404
        gh.fail("GET users/locked", 403, "Forbidden")
        with pytest.raises(github.GitHubError) as raised:
            github.GitHub(SLUG).get("users/locked")
        assert not raised.value.not_found and raised.value.status == 403


# --- Gemini's code review, round 3 (P8-K08 to P8-K11) ------------------------------------------------------------


VALID_INPUTS = {"python": ["3.12"], "install": "uv sync", "lint": "ruff", "linters": []}


class TestReviewRound3:
    @pytest.mark.parametrize("folder", ["../outside", "/abs", "api --index-url https://example.com", "a//b", "."])
    def test_k08_a_recorded_project_folder_must_be_one_swerepo_writes(self, folder: str):
        from swerepo import ci

        assert ci.Project.from_inputs(folder, VALID_INPUTS) is None
        assert ci.Project.from_inputs("services/api", VALID_INPUTS) is not None

    def test_k08_a_crafted_folder_in_the_record_is_never_read_or_echoed(self, tmp_path: Path):
        root = project_at(tmp_path / "app", TOOLS, **{"api/pyproject.toml": TOOLS, "api/tests/test_api.py": "x = 1\n"})
        init(root, ["ci"], projects=["api"])
        make(tmp_path, {"outside/pyproject.toml": BARE, "outside/uv.lock": "version = 1\n"})  # would be missing tools
        state = (root / ".swerepo.toml").read_text()
        assert '\\"folder\\":\\"api\\"' in state
        (root / ".swerepo.toml").write_text(state.replace('\\"folder\\":\\"api\\"', '\\"folder\\":\\"../outside\\"'))
        report = run_check(root, only=["ci"])
        assert not [f for f in report.findings if f.item.startswith("ci.tools")]
        assert "outside" not in json.dumps(report.to_dict())

    def test_k08_a_listed_project_linked_out_of_the_repository_isn_t_read(self, tmp_path: Path):
        root = project_at(tmp_path / "app", TOOLS, **{"api/pyproject.toml": TOOLS, "api/tests/test_api.py": "x = 1\n"})
        init(root, ["ci"], projects=["api"])
        make(tmp_path, {"outside/pyproject.toml": BARE, "outside/uv.lock": "version = 1\n"})
        for name in ("pyproject.toml", "tests/test_api.py"):
            (root / "api" / name).unlink()
        (root / "api" / "tests").rmdir()
        (root / "api").rmdir()
        (root / "api").symlink_to(tmp_path / "outside", target_is_directory=True)
        assert "ci.tools.api" not in by_item(root, only=["ci"])

    def test_k09_a_bare_uv_run_or_a_flag_is_never_a_tool(self):
        from swerepo.commands import uv_run_tools

        found = {"test": ["uv run   ", "uv run --frozen pytest", "uv run pytest"], "lint": ["uv run ruff check ."]}
        assert uv_run_tools(found) == ["pytest", "ruff"]
        assert uv_run_tools({"test": ["uv run me@example.com"], "lint": []}) == []

    def test_k09_agents_tools_reads_the_verified_block_not_values(self, tmp_path: Path):
        root = project_at(tmp_path / "app")
        init(root, ["agents"], hosts=["claude"])
        state = (root / ".swerepo.toml").read_text()
        edited = re.sub(r'^commands = ".*"$', 'commands = "- Test: `uv run   `\\\\n- Lint: `uv run --evil x`"', state,
                        flags=re.MULTILINE)  # fmt: skip
        assert edited != state
        (root / ".swerepo.toml").write_text(edited)
        finding = by_item(root, only=["agents"])["agents.tools"]  # no IndexError: the block's own commands
        assert finding.fix == "uv add --dev pytest ruff" and "evil" not in finding.message

    def test_k10_a_recorded_example_with_codeowners_removed_points_at_code_owner(self, repo: Path):
        assert run_init(repo, "--yes", "--code-owner", "@dev").exit_code == 0
        record_example(repo)
        (repo / CODEOWNERS).unlink()
        report = run_check(repo, only=["github"])
        finding = {f.item: f for f in report.findings}["github.codeowners"]
        assert finding.status == MISSING and finding.blocking and finding.fix == OWNER_FIX
        assert "question's example" in finding.message
        assert "swerepo init --only github;" not in (report.next_step() or "") + ";"
        assert OWNER_FIX in (report.next_step() or "")

    def test_k10_no_owner_named_suggests_no_example(self, repo: Path):
        assert run_init(repo, "--yes", "--code-owner", "none").exit_code == 0
        finding = by_item(repo, only=["github"])["github.codeowners"]
        assert not finding.blocking and "--code-owner …" in finding.message and "@login" not in finding.message

    def test_k11_an_escaped_space_stays_in_the_pattern(self, repo: Path):
        assert github.codeowners_rules("/docs/getting\\ started/ @dev\n") == [("/docs/getting\\ started/", ["@dev"])]
        owners(repo, "/docs/getting\\ started/ @dev")
        assert by_item(repo, only=["github"])["github.codeowners"].status == OK
