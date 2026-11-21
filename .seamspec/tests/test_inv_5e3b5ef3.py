"""Rule: in a repository where git's configured email and a commit use a personal address, a CODEOWNERS
line after SWERepo's block is just that address, and .swerepo.toml can't be read (the error names its
absolute path), `swerepo check` output (text, `--json`, `--ci` annotations on GitHub Actions, each with
the pull-request rules `--base`) contains neither the address nor the checked folder's absolute path,
its parent's, or the home folder (ADR-20261120-fc5a point 7; SWEREPO-SPEC §15)."""

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from swerepo.cli import app

AT = "@"
PERSONAL = "dev" + AT + "mail.test.com"  # built, so the repository's own privacy scan doesn't see it
GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]


def test_output_never_shows_paths_or_personal_emails(tmp_path: Path, monkeypatch):
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / "README.md").write_text("# x\n")
    (repo / ".swerepo.toml").write_text('standard = 1\nswerepo = "0.0.1"\n')
    (repo / ".github").mkdir()
    (repo / ".github/CODEOWNERS").write_text(f"# swerepo:begin\n/.github/ @o\n# swerepo:end\n{PERSONAL}\n")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run([*GIT, "-C", str(repo), "config", "user.email", PERSONAL], check=True)
    subprocess.run([*GIT, "-C", str(repo), "add", "-A"], check=True)
    subprocess.run([*GIT, "-C", str(repo), "commit", "-qm", "start"], check=True)
    subprocess.run([*GIT, "-C", str(repo), "checkout", "-q", "-b", "feature"], check=True)
    (repo / "app.py").write_text("print('x')\n")  # a change without a progress entry: a pull-request finding

    original = Path.read_text

    def refuse(self, *args, **kwargs):  # .swerepo.toml can't be read: the error names its absolute path
        if self.name == ".swerepo.toml":
            raise PermissionError(13, "Permission denied", str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", refuse)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    runs = [
        CliRunner().invoke(app, ["check", "--path", str(repo), "--base", "main", *extra])
        for extra in ([], ["--ci"], ["--json"], ["--json", "--ci"])
    ]
    cases = (
        ".swerepo.toml: can't read it",  # the unreadable state file
        "git user.email isn't a noreply address",  # the configured email
        "commits use an address that isn't a noreply one",  # the commit's email
        "can override governance owners",  # the CODEOWNERS line
        "no progress entry added",  # the pull-request rules ran
    )
    for run in runs:
        out = run.output
        assert run.exit_code == 1 and all(case in out for case in cases)  # each case did come up
        for path in (repo, repo.resolve(), tmp_path, tmp_path.resolve(), Path.home()):
            assert str(path) not in out
        assert PERSONAL not in out
