"""The pre-push privacy hook (spec §6.4; ADR-20261123-24e0): installing it, the scan of the commits being pushed,
and a real `git push` it refuses. Keys, addresses and paths are built at run time, so this file holds none."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from repo_helpers import commit, git, git_init, make
from typer.testing import CliRunner

from swerepo import hook
from swerepo.check import run_check
from swerepo.cli import app

KEY = "AKIA" + "Q" * 16  # the shape of an AWS access key
EMAIL = "alice" + "@" + "personal-mail.net"
HOME = "/Users/" + "alice" + "/notes.txt"
ZERO = "0" * 40


@pytest.fixture(autouse=True)
def no_personal_git_config(tmp_path: Path, monkeypatch):
    """The person's own git configuration (a global core.hooksPath, say) must not decide where hooks go."""
    empty = tmp_path / "gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = git_init(tmp_path / "app")
    make(root, {"README.md": "# app\n", "pyproject.toml": '[project]\nname = "app"\n'})
    commit(root, "start")
    return root


def head(root: Path) -> str:
    return git(root, "rev-parse", "HEAD").strip()


def push_input(local: str, remote: str = ZERO) -> list[tuple[str, str, str, str]]:
    return [("refs/heads/main", local, "refs/heads/main", remote)]


class TestScan:
    def test_a_key_in_a_new_commit_is_found_by_kind_and_place(self, repo: Path):
        before = head(repo)
        make(repo, {"config.py": f"name = 'app'\n\nkey = '{KEY}'\n", "notes.md": f"ask {EMAIL}\nsee {HOME}\n"})
        commit(repo, "settings")
        hits = hook.pushed_hits(repo, push_input(head(repo), before), [])
        assert [(h.kind, h.path, h.line) for h in hits] == [
            ("AWS access key", "config.py", 3), ("email address", "notes.md", 1), ("home-folder path", "notes.md", 2),
        ]  # fmt: skip
        assert all(h.commit == head(repo) for h in hits) and hits[0].where == f"{head(repo)[:7]} config.py:3"

    def test_only_what_the_push_adds_counts(self, repo: Path):
        make(repo, {"old.py": f"key = '{KEY}'\n"})
        commit(repo, "already on the remote")
        remote = head(repo)
        make(repo, {"old.py": "key = 'from the environment'\n", "new.py": "print('hi')\n"})
        commit(repo, "removes the key")
        assert hook.pushed_hits(repo, push_input(head(repo), remote), []) == []  # deleted lines don't count
        assert hook.pushed_hits(repo, [("refs/heads/x", ZERO, "refs/heads/x", remote)], []) == []  # a deletion

    def test_a_new_branch_sends_what_no_remote_has(self, repo: Path, tmp_path: Path):
        bare = tmp_path / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        git(repo, "remote", "add", "origin", str(bare))
        make(repo, {"legacy.py": f"key = '{KEY}'\n"})  # already on the remote: not this push's to answer for
        commit(repo, "legacy")
        git(repo, "push", "-q", "origin", "main")
        git(repo, "checkout", "-q", "-b", "feature")
        make(repo, {"a.py": f"key = '{KEY}'\n"})
        commit(repo, "first")
        make(repo, {"b.py": "x = 1\n"})
        commit(repo, "second")
        hits = hook.pushed_hits(repo, [("refs/heads/feature", head(repo), "refs/heads/feature", ZERO)], [])
        assert [(h.path, h.line) for h in hits] == [("a.py", 1)]  # main's commits aren't scanned again

    def test_the_same_allowances_as_ci(self, repo: Path):
        before = head(repo)
        make(repo, {
            "pyproject.toml": f'[project]\nname = "app"\nauthors = [{{ name = "A", email = "{EMAIL}" }}]\n',
            "SECURITY.md": f"Report to {EMAIL}\n",
            "docs/example.md": f"key = '{KEY}'  # swerepo: allow-privacy\n",
            "fixtures/keys.txt": f"{KEY}\n",
        })  # fmt: skip
        commit(repo, "allowed")
        assert hook.pushed_hits(repo, push_input(head(repo), before), ["fixtures/"]) == []
        assert [h.path for h in hook.pushed_hits(repo, push_input(head(repo), before), [])] == ["fixtures/keys.txt"]

    def test_line_numbers_follow_each_hunk_and_odd_lines_are_lines(self, repo: Path):
        make(repo, {"long.txt": "".join(f"line {n}\n" for n in range(1, 21))})
        commit(repo, "long")
        before = head(repo)
        lines = [f"line {n}\n" for n in range(1, 21)]
        lines[4] = f"++ {KEY}\n"  # an added line that reads `+++ …` in the diff
        lines.insert(15, f"+++ b/{KEY}\n")
        make(repo, {"long.txt": "".join(lines)})
        commit(repo, "edits")
        hits = hook.pushed_hits(repo, push_input(head(repo), before), [])
        assert [(h.path, h.line) for h in hits] == [("long.txt", 5), ("long.txt", 16)]

    def test_binary_files_are_skipped(self, repo: Path):
        before = head(repo)
        (repo / "blob.bin").write_bytes(b"\0\1" + KEY.encode() + b"\0")
        commit(repo, "binary")
        assert hook.pushed_hits(repo, push_input(head(repo), before), []) == []


class TestInstall:
    def test_installs_once_and_keeps_a_hook_of_yours(self, repo: Path):
        done, message = hook.install(repo, None)
        path = repo / ".git/hooks/pre-push"
        assert done and "installed" in message and os.access(path, os.X_OK)
        assert hook.is_ours(path.read_text()) and 'exec "$@" privacy --pre-push' in path.read_text()
        assert hook.install(repo, None) == (True, "pre-push hook: already installed")
        assert hook.status(repo) == "installed"
        path.write_text("#!/bin/sh\necho mine\n")
        done, message = hook.install(repo, None)
        assert not done and "kept" in message and 'swerepo privacy --pre-push --remote "${1:-}"' in message
        assert path.read_text() == "#!/bin/sh\necho mine\n" and hook.status(repo) == "other"

    def test_the_hooks_folder_git_uses(self, repo: Path):
        git(repo, "config", "core.hooksPath", ".githooks")
        hook.install(repo, None)
        assert (repo / ".githooks/pre-push").is_file() and not (repo / ".git/hooks/pre-push").exists()

    @pytest.mark.parametrize(
        ("recorded", "used"),
        [(None, "swerepo"), ("uv run --locked swerepo", "uv run --locked swerepo"), ("rm -rf ~; swerepo", "swerepo")],
    )
    def test_only_a_command_swerepo_writes_is_run(self, repo: Path, recorded, used):
        hook.install(repo, recorded)
        assert f"set -- {used}\n" in (repo / ".git/hooks/pre-push").read_text()

    def test_the_cli_refuses_to_replace_your_hook(self, repo: Path):
        (repo / ".git/hooks").mkdir(exist_ok=True)
        (repo / ".git/hooks/pre-push").write_text("#!/bin/sh\n")
        result = CliRunner().invoke(app, ["hook", "install", "--path", str(repo)])
        assert result.exit_code == 1 and "kept" in result.output


class TestCheck:
    def test_check_reminds_locally_never_in_ci(self, repo: Path):
        def finding(**kwargs):
            report = run_check(repo, only=["security"], **kwargs)
            return next((f for f in report.findings if f.item == "security.pre-push-hook"), None)

        assert finding() is None  # CI: no hooks there
        missing = finding(local=True)
        assert missing is not None and "swerepo hook install" in missing.message and not missing.blocking
        hook.install(repo, None)
        assert finding(local=True).message == "pre-push privacy hook installed"


class TestPush:
    """A real `git push` to a local bare repository, through the installed hook."""

    def test_a_push_adding_a_key_is_refused_and_says_where_not_what(self, repo: Path, tmp_path: Path):
        assert shutil.which("swerepo"), "the hook runs swerepo from PATH, as an installed tool would"
        bare = tmp_path / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        git(repo, "remote", "add", "origin", str(bare))
        hook.install(repo, None)
        clean = subprocess.run(["git", "-C", str(repo), "push", "-q", "origin", "main"], capture_output=True, text=True)
        assert clean.returncode == 0, clean.stderr
        make(repo, {"deploy.sh": f"export AWS_ACCESS_KEY_ID={KEY}\nmail {EMAIL}\n"})
        commit(repo, "deploy")
        refused = subprocess.run(["git", "-C", str(repo), "push", "origin", "main"], capture_output=True, text=True)
        assert refused.returncode != 0 and "push refused" in refused.stderr
        assert f"{head(repo)[:7]} deploy.sh:1" in refused.stderr and "deploy.sh:2" in refused.stderr
        assert KEY not in refused.stderr and EMAIL not in refused.stderr and "alice" not in refused.stderr
        remote_head = subprocess.run(["git", "-C", str(bare), "rev-parse", "main"], capture_output=True, text=True)
        assert remote_head.stdout.strip() != head(repo)  # nothing reached the remote
        skipped = subprocess.run(["git", "-C", str(repo), "push", "-q", "--no-verify", "origin", "main"],
                                 capture_output=True, text=True)  # fmt: skip
        assert skipped.returncode == 0  # git's own way to skip a hook, on purpose


class TestReviewH55:
    """The hook's review (H55), each finding reproduced before the fix."""

    def test_f01_a_hook_git_cant_run_is_reported_and_repaired(self, repo: Path):
        hook.install(repo, None)
        path = repo / ".git/hooks/pre-push"
        path.chmod(0o644)  # git skips it without a word
        assert hook.status(repo) == "not executable"
        found = next(f for f in run_check(repo, only=["security"], local=True).findings
                     if f.item == "security.pre-push-hook")  # fmt: skip
        assert "isn't executable" in found.message and not found.blocking
        assert hook.install(repo, None) == (True, "pre-push hook: made executable again (git skipped it)")
        assert os.access(path, os.X_OK) and hook.status(repo) == "installed"

    def test_f01_a_link_is_someone_elses_hook_for_status_and_install(self, repo: Path, tmp_path: Path):
        hook.install(repo, None)
        target = tmp_path / "shared-hook"
        target.write_text((repo / ".git/hooks/pre-push").read_text())  # even SWERepo's text, behind a link
        (repo / ".git/hooks/pre-push").unlink()
        (repo / ".git/hooks/pre-push").symlink_to(target)
        assert hook.status(repo) == "other"
        done, message = hook.install(repo, None)
        assert not done and "kept" in message and (repo / ".git/hooks/pre-push").is_symlink()

    def test_f02_a_secret_added_while_resolving_a_merge_is_found(self, repo: Path):
        make(repo, {"f.txt": "a\nb\nc\n"})
        commit(repo, "base")
        git(repo, "checkout", "-q", "-b", "side")
        make(repo, {"f.txt": "a\nside\nc\n", "side.txt": "clean\n"})
        commit(repo, "side")
        git(repo, "checkout", "-q", "main")
        make(repo, {"f.txt": "a\nmain\nc\n"})
        commit(repo, "main")
        before = head(repo)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", "merge", "-q",
                        "side"], capture_output=True)  # fmt: skip  # a conflict, resolved by hand below
        make(repo, {"f.txt": f"a\nresolved {KEY}\nc\n"})
        commit(repo, "merge")
        hits = hook.pushed_hits(repo, push_input(head(repo), before), [])
        assert [(h.commit, h.path, h.line) for h in hits] == [(head(repo), "f.txt", 2)]  # side's clean lines: none

    def test_f03_a_branch_on_one_remote_is_scanned_when_first_pushed_to_another(self, repo: Path, tmp_path: Path):
        for name in ("origin", "public"):
            subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / f"{name}.git")], check=True)
            git(repo, "remote", "add", name, str(tmp_path / f"{name}.git"))
        make(repo, {"internal.txt": f"key {KEY}\n"})
        commit(repo, "on the private remote only")
        git(repo, "push", "-q", "origin", "main")
        update = push_input(head(repo), ZERO)  # main is new to `public`
        assert [h.path for h in hook.pushed_hits(repo, update, [], "public")] == ["internal.txt"]
        assert hook.pushed_hits(repo, update, [], "origin") == []  # already there
        assert hook.pushed_hits(repo, update, [], None) == []  # no remote named: measured against all of them
        assert '--remote "$remote"' in hook.script("swerepo") and 'remote="${1:-}"' in hook.script("swerepo")

    def test_f05_the_input_is_read_strictly_and_homebrew_is_on_path(self):
        good = f"refs/heads/main {'a' * 40} refs/heads/main {ZERO}\n"
        assert hook.parse_updates(good + "\n") == [("refs/heads/main", "a" * 40, "refs/heads/main", ZERO)]
        assert hook.parse_updates(f"refs/heads/main {'b' * 64} refs/heads/main {'c' * 64}")  # SHA-256
        for bad in ("refs/heads/main HEAD refs/heads/main " + ZERO, "refs/heads/main " + "a" * 40, "x y z w"):
            with pytest.raises(hook.HookError):
                hook.parse_updates(bad)
        assert "/opt/homebrew/bin:/usr/local/bin" in hook.script("swerepo")

    def test_f06_file_names_git_quotes_or_ends_with_a_tab(self, repo: Path):
        before = head(repo)
        names = ("space file.py", 'quote "file".py', "back\\slash.py", "tab\tfile.py", "café.py", "plain.py")
        make(repo, {name: f"key = '{KEY}'\n" for name in names})
        commit(repo, "awkward names")
        hits = hook.pushed_hits(repo, push_input(head(repo), before), [])
        assert sorted(h.path for h in hits) == sorted(names)  # none skipped, none with a tab left on
        assert hook.pushed_hits(repo, push_input(head(repo), before), ["space file.py", "quote*"]) != []
        globs = [name.replace("\\", "?") for name in names]  # allow_paths reads a backslash as a folder separator
        assert hook.pushed_hits(repo, push_input(head(repo), before), globs) == []  # allow_paths matches each name
        assert hook._path_name('"b/caf\\303\\251 \\"x\\" \\\\ \\t.py"\t') == 'b/café "x" \\ \t.py'
