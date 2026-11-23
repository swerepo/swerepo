"""Detection on fixture repositories built per test (spec §18), plus this repository itself.

Fixtures are created in temporary folders rather than committed, so this repository never holds
project files that would make it look like a monorepo.
"""

import json
import subprocess
from pathlib import Path

import pytest

from swerepo.detect import detect

REPO = Path(__file__).resolve().parents[1]


def make(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def git_init(root: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    return {p.relative_to(root).as_posix(): (p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(root.rglob("*"))}


def test_an_empty_folder(tmp_path: Path):
    found = detect(tmp_path)
    assert found.git.is_work_tree is False and found.git.listed_by == "walk"
    assert found.projects == () and found.languages == () and not found.is_monorepo
    assert found.python.versions == () and found.python.source is None
    assert found.documents == {} and found.workflows == () and found.errors == ()


def test_a_new_uv_project(tmp_path: Path):
    git_init(tmp_path)
    make(tmp_path, {
        "pyproject.toml": '[project]\nname = "invoices"\nrequires-python = ">=3.11"\n',
        "main.py": "print('hi')\n",
        "README.md": "# invoices\n",
    })  # fmt: skip
    found = detect(tmp_path)
    assert found.git.is_work_tree and found.git.is_toplevel and found.git.listed_by == "git"
    assert found.languages == ("python",)
    assert found.python.versions == ("3.11", "3.12", "3.13", "3.14")
    assert found.python.source == "pyproject.toml [project] requires-python"
    assert [p.path for p in found.projects] == ["."]
    assert found.documents == {"readme": "README.md"}
    assert found.linters == () and found.pytest_configured is False


def test_an_established_repository(tmp_path: Path):
    git_init(tmp_path)
    make(tmp_path, {
        "setup.cfg": "[options]\npython_requires = >=3.9, <3.13\n\n[flake8]\nmax-line-length = 100\n\n[tool:pytest]\n",
        "setup.py": "from setuptools import setup\nsetup()\n",
        "pyproject.toml": "[tool.black]\nline-length = 100\n",
        ".pre-commit-config.yaml": "repos:\n  - repo: https://github.com/psf/black\n    hooks:\n      - id: black\n",
        ".github/workflows/tests.yml": "jobs:\n  test:\n    steps:\n      - run: pytest -q\n",
        ".github/workflows/release.yml": "jobs:\n  build:\n    steps:\n      - run: python -m build\n",
        ".gitlab-ci.yml": "test:\n  script: pytest\n",
        "doc/decisions/0001-use-postgres.md": "# Use Postgres\n",
        "doc/decisions/0002-drop-celery.md": "# Drop Celery\n",
        "doc/decisions/README.md": "# Decisions\n",
        "CLAUDE.md": "# Notes for Claude\n",
        ".cursor/rules/style.mdc": "be nice\n",
        "CHANGES.md": "# Changes\n",
        ".github/CONTRIBUTING.md": "# Contributing\n",
        ".gitignore": ".venv/\n",
        ".venv/lib/pyproject.toml": "[project]\nname = 'not-a-project'\n",
    })  # fmt: skip
    found = detect(tmp_path)
    assert found.python.versions == ("3.9", "3.10", "3.11", "3.12")
    assert found.python.source == "setup.cfg [options] python_requires"
    assert [(w.path, w.runs_pytest, w.runs_ruff) for w in found.workflows] == [
        (".github/workflows/release.yml", False, False),
        (".github/workflows/tests.yml", True, False),
    ]
    assert found.other_ci == (".gitlab-ci.yml",)
    assert [(a.path, a.count) for a in found.adr_dirs] == [("doc/decisions", 2)]
    assert found.agent_files == ("CLAUDE.md", ".cursor/rules")
    assert found.hosts == ("claude", "cursor")
    assert found.documents == {"changelog": "CHANGES.md", "contributing": ".github/CONTRIBUTING.md"}
    assert {linter.name: linter.configured_in for linter in found.linters} == {
        "black": ("pyproject.toml [tool.black]", ".pre-commit-config.yaml"),
        "flake8": ("setup.cfg [flake8]",),
    }
    assert found.pytest_configured is True
    assert [p.path for p in found.projects] == ["."]  # .venv is git-ignored, never a project
    assert not found.is_monorepo


def test_a_monorepo_with_tooling_and_fixtures(tmp_path: Path):
    git_init(tmp_path)
    make(tmp_path, {
        "README.md": "# shop\n",
        "services/orders/pyproject.toml": '[project]\nname = "orders"\n',
        "services/payments/pyproject.toml": '[project]\nname = "payments"\n',
        "web/package.json": "{}\n",
        "tools/release/pyproject.toml": '[project]\nname = "release-tool"\n',
        "tests/fixtures/sample/pyproject.toml": '[project]\nname = "sample"\n',
        "examples/demo/package.json": "{}\n",
    })  # fmt: skip
    found = detect(tmp_path)
    assert found.is_monorepo
    assert [(p.path, p.kind) for p in found.projects] == [
        ("services/orders", "python"),
        ("services/payments", "python"),
        ("web", "javascript"),
    ]
    assert [(s.path, s.reason) for s in found.skipped_projects] == [
        ("examples/demo", "under examples/"),
        ("tests/fixtures/sample", "under tests/"),
        ("tools/release", "under tools/"),
    ]
    assert found.languages == ("javascript", "python")


def test_a_polyglot_monorepo(tmp_path: Path):  # review finding P1-F01
    git_init(tmp_path)
    make(tmp_path, {
        "pyproject.toml": '[project]\nname = "app"\n',
        "gateway/go.mod": "module example.com/gateway\n",
        "ui/package.json": "{}\n",
        "ui/tsconfig.json": "{}\n",
        "engine/Cargo.toml": "[package]\n",
        "legacy/pom.xml": "<project/>\n",
        "site/Gemfile": "source 'https://rubygems.org'\n",
    })  # fmt: skip
    found = detect(tmp_path)
    assert found.is_monorepo
    assert [(p.path, p.kind) for p in found.projects] == [
        (".", "python"),
        ("engine", "rust"),
        ("gateway", "go"),
        ("legacy", "java"),
        ("site", "ruby"),
        ("ui", "typescript"),
    ]
    assert found.languages == ("go", "java", "javascript", "python", "ruby", "rust", "typescript")


def test_python_projects_without_pyproject(tmp_path: Path):  # P1-F01
    git_init(tmp_path)
    make(tmp_path, {
        "requirements.txt": "flask\n",
        "app.py": "",
        "services/api/requirements.txt": "fastapi\n",
        "services/api/main.py": "",
        "services/billing/setup.cfg": "[metadata]\nname = billing\n",
        "services/billing/billing.py": "",
        "services/jobs/Pipfile": "[packages]\n",
        "services/worker/requirements.txt": "celery\n",  # package layout (review finding P1-F08)
        "services/worker/worker/tasks.py": "",
        "services/legacy/setup.cfg": "[options]\npackages = find:\n",  # src/ layout (P1-F08)
        "services/legacy/src/legacy/core.py": "",
        "ci/requirements.txt": "tox\n",  # configuration, no Python source beside it: not a project
        "ci/scripts/lint.py": "",  # source under scripts/ doesn't make ci/ a project
        "deploy/setup.cfg": "[flake8]\n",
    })  # fmt: skip
    found = detect(tmp_path)
    assert [(p.path, p.kind) for p in found.projects] == [
        (".", "python"),
        ("services/api", "python"),
        ("services/billing", "python"),
        ("services/jobs", "python"),
        ("services/legacy", "python"),
        ("services/worker", "python"),
    ]


def test_a_requirements_only_repository_is_a_python_project(tmp_path: Path):  # P1-F01
    make(tmp_path, {"requirements.txt": "flask\n"})
    assert [(p.path, p.kind) for p in detect(tmp_path).projects] == [(".", "python")]


def test_ignore_entries_never_mean_everything(tmp_path: Path):  # P1-F06
    git_init(tmp_path)
    make(tmp_path, {"services/a/pyproject.toml": "", "services/b/pyproject.toml": ""})
    assert len(detect(tmp_path, ignore=["", "."]).projects) == 2


def test_falls_back_to_walking_when_git_cannot_list(tmp_path: Path, monkeypatch):  # P1-F06
    import swerepo.detect as detect_module

    git_init(tmp_path)
    make(tmp_path, {"pyproject.toml": '[project]\nname = "x"\n'})
    monkeypatch.setattr(detect_module, "_git_files", lambda root: None)
    found = detect(tmp_path)
    assert found.git.is_work_tree and found.git.listed_by == "walk"
    assert [p.path for p in found.projects] == ["."]


def test_projects_ignore_lists_extra_folders(tmp_path: Path):
    git_init(tmp_path)
    make(tmp_path, {
        "pyproject.toml": '[project]\nname = "app"\n',
        "sandbox/old/pyproject.toml": '[project]\nname = "old"\n',
        "sandboxes/pyproject.toml": '[project]\nname = "kept"\n',
    })  # fmt: skip
    found = detect(tmp_path, ignore=["sandbox"])
    assert [p.path for p in found.projects] == [".", "sandboxes"]  # a prefix of a name is not a match
    assert [(s.path, s.reason) for s in found.skipped_projects] == [
        ("sandbox/old", "listed in [projects] ignore (sandbox)")
    ]


def test_a_folder_holding_other_repositories(tmp_path: Path):
    git_init(tmp_path / "api")
    git_init(tmp_path / "clients" / "web")
    found = detect(tmp_path)
    assert found.git.is_work_tree is False
    assert found.git.nested_repos == ("api", "clients/web")


def test_a_subfolder_of_a_repository(tmp_path: Path):
    git_init(tmp_path)
    make(tmp_path, {"lib/pyproject.toml": '[project]\nname = "lib"\nrequires-python = ">=3.12"\n'})
    found = detect(tmp_path / "lib")
    assert found.git.is_work_tree and not found.git.is_toplevel
    assert [p.path for p in found.projects] == ["."]


@pytest.mark.parametrize(
    ("requires", "versions"),
    [
        (">=3.11", ("3.11", "3.12", "3.13", "3.14")),
        (">=3.9,<3.13", ("3.9", "3.10", "3.11", "3.12")),
        ("~=3.10", ("3.10", "3.11", "3.12", "3.13", "3.14")),
        ("==3.12.*", ("3.12",)),
        (">=3.10,!=3.12.*", ("3.10", "3.11", "3.13", "3.14")),
        (">=3.11.4", ("3.11", "3.12", "3.13", "3.14")),  # a later patch of 3.11 still supports 3.11
        ("<3.12.1,>=3.12", ("3.12",)),
        (" >= 3.13 ", ("3.13", "3.14")),
        (">=4", ()),
        ("==3.11.4", ("3.11",)),  # review finding P1-F06: patch pins
        (">=3.12.1,<3.12.8", ("3.12",)),
        ("!=3.11.0,>=3.11,<3.11.5", ("3.11",)),
    ],
)
def test_python_versions_from_requires_python(tmp_path: Path, requires, versions):
    make(tmp_path, {"pyproject.toml": f'[project]\nname = "x"\nrequires-python = "{requires}"\n'})
    assert detect(tmp_path).python.versions == versions


def test_python_versions_from_classifiers(tmp_path: Path):
    make(tmp_path, {
        "pyproject.toml": '[project]\nname = "x"\nclassifiers = [\n'
        '  "Programming Language :: Python :: 3.12",\n  "Programming Language :: Python :: 3.10",\n'
        '  "Programming Language :: Python :: 3 :: Only",\n]\n'
    })  # fmt: skip
    python = detect(tmp_path).python
    assert python.versions == ("3.10", "3.12") and python.source == "pyproject.toml classifiers"


def test_python_declared_only_in_setup_py_is_unknown(tmp_path: Path):
    make(tmp_path, {"setup.py": "setup(python_requires='>=3.11')\n"})
    found = detect(tmp_path)
    assert found.python.versions == () and found.python.source is None
    assert found.languages == ("python",)


def test_problems_are_reported_not_raised(tmp_path: Path):
    make(tmp_path, {
        "pyproject.toml": '[project]\nname = "x"\nrequires-python = "python3"\n[tool.ruff\n',
        "setup.cfg": "[options\n",
    })  # fmt: skip
    found = detect(tmp_path)
    assert any(e.startswith("pyproject.toml: can't read it") for e in found.errors)
    assert any(e.startswith("setup.cfg: can't read it") for e in found.errors)

    make(tmp_path, {"pyproject.toml": '[project]\nname = "x"\nrequires-python = "python3"\n', "setup.cfg": ""})
    found = detect(tmp_path)
    assert found.errors == ("pyproject.toml [project] requires-python: 'python3' is not a version specifier",)
    assert found.python.versions == ()


def test_editors_are_detected_from_their_folders_even_when_git_ignores_them(tmp_path: Path):
    git_init(tmp_path)
    make(tmp_path, {".gitignore": ".vscode/\n.agents/\n", ".vscode/settings.json": "{}\n", ".agents/x": "y\n"})
    assert detect(tmp_path).hosts == ("vscode", "antigravity")


def test_copilot_instructions_do_not_mean_vscode(tmp_path: Path):  # review finding P1-F05
    make(tmp_path, {"CLAUDE.md": "x\n", ".github/copilot-instructions.md": "review rules\n"})
    found = detect(tmp_path)
    assert found.hosts == ("claude",)
    assert ".github/copilot-instructions.md" in found.agent_files


def test_antigravitys_older_folder_name(tmp_path: Path):
    (tmp_path / ".agent").mkdir()
    assert detect(tmp_path).hosts == ("antigravity",)


def test_linters_and_pytest_in_ini_files(tmp_path: Path):  # P1-F05
    make(tmp_path, {
        "setup.cfg": "[tool:isort]\nprofile = black\n\n[pylint.messages_control]\ndisable = C0114\n",
        "tox.ini": "[pylint]\nmax-line-length = 100\n",
        ".pytest.ini": "[pytest]\n",
    })  # fmt: skip
    found = detect(tmp_path)
    assert {linter.name: linter.configured_in for linter in found.linters} == {
        "isort": ("setup.cfg [tool:isort]",),
        "pylint": ("setup.cfg [pylint]", "tox.ini [pylint]"),
    }
    assert found.pytest_configured


def test_detection_writes_nothing(tmp_path: Path):
    git_init(tmp_path)
    make(tmp_path, {"pyproject.toml": '[project]\nname = "x"\nrequires-python = ">=3.11"\n', "README.md": "x\n"})
    before = snapshot(tmp_path)
    detect(tmp_path)
    assert snapshot(tmp_path) == before


def test_the_result_is_plain_data_with_relative_paths(tmp_path: Path):
    git_init(tmp_path)
    make(tmp_path, {"services/a/pyproject.toml": "", "README.md": "x\n"})
    data = detect(tmp_path).to_dict()
    text = json.dumps(data)
    assert str(tmp_path) not in text
    assert data["projects"] == [{"path": "services/a", "kind": "python"}]


def test_this_repository():
    """Dogfooding: SWERepo's own repository (Phase 0 review note: tools/ is not a project)."""
    found = detect(REPO)
    assert not found.is_monorepo
    assert [p.path for p in found.projects] == ["."]
    assert ("tools/pypi-placeholder", "under tools/") in [(s.path, s.reason) for s in found.skipped_projects]
    assert found.python.versions == ("3.11", "3.12", "3.13", "3.14")
    assert {"AGENTS.md", "CLAUDE.md"} <= set(found.agent_files)
    assert [a.path for a in found.adr_dirs] == ["docs/adr"] and found.adr_dirs[0].count >= 13
    assert found.seamspec and found.pytest_configured
    assert [linter.name for linter in found.linters] == ["ruff"]
    # set up by swerepo init since ADR-20261123-d27b (the hand-written ci.yml before it)
    assert any(w.path == ".github/workflows/swerepo-ci.yml" and w.runs_pytest for w in found.workflows)
