---
id: ADR-20261120-25b5
title: Detection is read-only, lists files through git, skips conventional non-project folders, and reads Python versions with packaging
status: ACCEPTED
date: 2026-11-20
scopes: ["swerepo/detect.py", "pyproject.toml", "SWEREPO-SPEC.md"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261120-25b5: Detection is read-only, lists files through git, skips conventional non-project folders, and reads Python versions with packaging

## Context

Before any plan, SWERepo detects what a repository already has (spec §10): project type and Python versions, existing CI, ADRs and other documents, agent files and editors, linters, SeamSpec and OpenSpec, and monorepo layout (§11). The Phase 0 review noted a real trap: this repository has a second `pyproject.toml` in `tools/pypi-placeholder/`, and its tests will create fixture projects, so naive detection would call it a monorepo. Python versions must come from `requires-python` (§6.2), which uses PEP 440 specifiers.

## Decision

1. **Read-only.** Detection reads files and runs `git ls-files`; it never writes, installs or calls the network. Malformed files (invalid TOML, an unreadable `requires-python`) are reported in the result, never raised.
2. **Files are listed through git** when the folder is a git work tree (`git ls-files -co --exclude-standard`: tracked plus untracked-but-not-ignored), so `.venv`, build output and anything git-ignored never count. Without git, or if git fails to list them, a walk that skips `.git`, virtual environments, `node_modules`, caches and build folders.
3. **Project roots** are folders holding a project manifest (review finding P1-F01): for Python `pyproject.toml`, `setup.py` or `Pipfile`, and `setup.cfg` or `requirements*.txt` when the folder holds Python source in it or below it (package and `src/` layouts, P1-F08; source under conventional non-project folders doesn't count) or is the repository root, since on their own they are often just configuration (`ci/requirements.txt`); for other languages `package.json` (JavaScript, or TypeScript with `tsconfig.json`), `go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle(.kts)` and `Gemfile`. A folder with several kinds is named by the first of Python, TypeScript, JavaScript, Go, Rust, Java, Ruby. Sub-project roots below the repository root are a monorepo (§11), **except** folders whose path contains a conventional non-project folder: `tests`, `test`, `testing`, `fixtures`, `examples`, `example`, `docs`, `doc`, `tools`, `scripts`, `vendor`, `third_party`. These hold fixtures, examples and tooling, not shipped projects.
4. **`[projects] ignore`** in `.swerepo.toml`: extra repository-relative folders (and everything below them) that are not projects. Plain folder paths, not globs: Python 3.11 has no full glob matching (`PurePath.full_match` is 3.13+), and folder prefixes are enough.
5. **Python versions** come from `[project] requires-python` in `pyproject.toml`, else `python_requires` in `setup.cfg`, else `Programming Language :: Python :: 3.X` classifiers. `setup.py` is never executed (spec §17), so a version declared only there is reported as unknown. A minor version is supported when the specifier allows any of its patch releases 0 to 29 or 99, so patch pins (`==3.11.4`) and patch ranges (`>=3.12.1,<3.12.8`) work (review finding P1-F06); checked with the **`packaging`** library against a known list, 3.8 to 3.14 in standard 1.
6. **What is reported:** languages; Python versions and where they came from; CI workflows and other CI systems, with whether each workflow runs pytest or ruff (a text search, for overlap reports); ADR folders (`docs/adr`, `doc/adr`, `docs/decisions`, `doc/decisions`, `docs/architecture/decisions`, `adr`) with their ADR counts; README, CHANGELOG, CONTRIBUTING, SECURITY, LICENSE, CODEOWNERS and progress files; agent files and the editors they suggest (from `CLAUDE.md` and `.claude/`, `.cursorrules` and `.cursor/`, `.vscode/`, `GEMINI.md`, `.agents/` and `.agent/`; not from `.github/copilot-instructions.md`, which SWERepo writes for Copilot review on GitHub whatever the editor, P1-F05); linters and formatters (ruff, black, isort, flake8, pylint) and pytest configuration; SeamSpec and OpenSpec; whether the folder is a git work tree and whether it holds other repositories; the project roots and whether it is a monorepo.
7. **A new runtime dependency: `packaging`** (pure Python, no dependencies, the reference implementation of PEP 440 used by pip). Hand-parsing version specifiers would get edge cases wrong (`~=`, `!=3.12.*`, local versions).

**Alternatives considered:**
- **Heuristics to tell tooling from projects** (for example "has tests" or "has a source package"). `tools/pypi-placeholder/` has a package, so they fail on this very repository; conventional folder names plus an explicit ignore list are predictable.
- **Globs in `[projects] ignore`.** See point 4.
- **Walk every folder instead of asking git.** Slower on large repositories, and needs its own copy of `.gitignore` rules to avoid `.venv` and build output.
- **Execute or parse `setup.py`** for versions. Executing project code is ruled out by the spec; parsing it is unreliable.

## Enforced Invariants

inv_bee7349a (proposed in Phase 1): detection never writes to the repository, with or without git.

## Consequences

- A monorepo whose real projects live under `tools/` or `examples/` needs `[projects] ignore` reversed; that case gets an "include" option only if dogfooding shows it is needed.
- The known Python list moves with the standard (standard 2 may add 3.15).
- `packaging` ships with SWERepo.
