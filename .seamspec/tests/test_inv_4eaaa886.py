"""Rule: the bundled hygiene tests use only the standard library and pytest, pass ruff, pass on a repository `swerepo
init` set up, and each fails on the breakage it guards (ADR-20261124-cd64 point 5; spec §6.8; review P7-F04, P7-F05)."""

import ast
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from swerepo import seamspec_component
from swerepo.cli import app
from swerepo.render import TemplateStore

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".seamspec" / "config.toml").is_file())
GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t",
       "-c", "user.email=t@example.com"]  # fmt: skip
PYPROJECT = '[project]\nname = "app"\nrequires-python = ">=3.12"\n[dependency-groups]\ndev = ["pytest", "ruff"]\n'
FILES = {name: f"test_{name.replace('-', '_')}.py" for name in ("privacy", "adr-index", "changelog", "ci-tests")}


def _code(name: str) -> str:
    return TemplateStore().get(seamspec_component.HYGIENE[name].template).render({})


def test_standard_library_and_pytest_only_and_ruff_clean(tmp_path: Path):
    assert sorted(seamspec_component.HYGIENE) == sorted(FILES)
    for name in seamspec_component.HYGIENE:
        code, imported = _code(name), set()
        for node in ast.walk(ast.parse(code)):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        assert imported <= set(sys.stdlib_module_names) | {"pytest"}, (name, imported)
        target = tmp_path / FILES[name]
        target.write_text(code)
        settings = str(ROOT / "pyproject.toml")
        for args in (["check"], ["format", "--check"]):
            done = subprocess.run([sys.executable, "-m", "ruff", *args, "--config", settings, str(target)],
                                  capture_output=True, text=True, check=False)  # fmt: skip
            assert done.returncode == 0, (name, args, done.stdout)


def _exit(root: Path, name: str) -> int:
    """pytest's exit status for one rule's test, run alone."""
    target = root / ".seamspec" / "tests" / FILES[name]
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "--noconftest", "-p", "no:cacheprovider",
                           str(target)], cwd=root, capture_output=True, text=True, check=False).returncode  # fmt: skip


def _all_pass(root: Path) -> None:
    for name in FILES:
        assert _exit(root, name) == 0, name


def _git(root: Path, *args: str) -> None:
    subprocess.run([*GIT, "-C", str(root), *args], check=True)


def test_they_pass_where_init_set_up_and_fail_on_what_they_guard(tmp_path: Path):
    root = tmp_path / "app"
    root.mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / "uv.lock").write_text("version = 1\n")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    done = CliRunner().invoke(app, ["init", "--path", str(root), "--yes", "--code-owner", "@dev"])
    assert done.exit_code == 0, done.output
    (root / ".seamspec" / "tests").mkdir(parents=True)
    (root / ".seamspec" / "config.toml").write_text('mode = "enforced"\n')
    for name in FILES:
        (root / ".seamspec" / "tests" / FILES[name]).write_text(_code(name))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "set up")
    _all_pass(root)  # as init left it

    policy = root / "SECURITY.md"
    if policy.exists():
        policy.unlink()
    (root / ".github" / "SECURITY.md").write_text("Report to security" + "@" + "mail.test.com\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "policy where GitHub also reads it")
    _all_pass(root)

    readme = root / "README.md"
    original = readme.read_text() if readme.exists() else ""
    readme.write_text(original + "\nSee " + "/" + "home/alice/notes\n")
    _git(root, "add", "-A")
    assert _exit(root, "privacy") == 1
    readme.write_text(original)
    _git(root, "add", "-A")

    adr = root / "docs" / "adr" / "ADR-20260101-abcd-unlisted.md"
    adr.write_text("# Unlisted\n")
    assert _exit(root, "adr-index") == 1
    adr.unlink()

    changelog = root / "CHANGELOG.md"
    text = changelog.read_text()
    changelog.write_text(text.replace("[Unreleased]", "[1.0.0]"))
    assert _exit(root, "changelog") == 1
    changelog.write_text(text)

    workflow = root / ".github" / "workflows" / "swerepo-ci.yml"
    ci = workflow.read_text()
    step = "      - run: uv run pytest\n"
    head = "  ci-ok:\n    if: always()\n"
    judge = ci[ci.index("  ci-ok:\n") :]
    judge = judge[judge.index("    steps:\n") + len("    steps:\n") :]
    assert "needs: [lint, test, " in ci and step in ci and head in ci and "toJSON(needs)" in judge
    for weakened in (
        ci.replace("needs: [lint, test, ", "needs: [lint, "),
        ci.replace(step, step + "        continue-on-error: true\n", 1),
        ci.replace(step, "      - run: uv run pytest || true\n", 1),
        ci.replace(step, "      - run: >\n          uv run pytest\n          || true\n", 1),
        ci.replace(judge, "      - run: echo ok\n"),  # ci-ok passes whatever the jobs did
        ci.replace(head, "  ci-ok:\n"),  # skipped when a job fails, which GitHub counts as passed
    ):
        workflow.write_text(weakened)
        assert _exit(root, "ci-tests") == 1
    workflow.write_text(ci)
    _all_pass(root)
