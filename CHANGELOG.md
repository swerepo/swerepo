# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Package skeleton: `swerepo --version`, `python -m swerepo`.
- CI workflow with lint, tests on Python 3.11 to 3.14, macOS on `main`, workflow audit, SeamSpec, and a single required check `ci-ok`.
- ADRs for the build process, SeamSpec, packaging and CI; agent rules, contributing guide and progress log.
- Apache-2.0 license.
- Foundations for `check`, `init` and `update` (no new commands yet): fingerprints of generated files and marked blocks, the template store and renderer, the `.swerepo.toml` state file, and read-only project detection.
- `swerepo check`: a read-only report of what a repository meets, misses or has changed against standard 1, per component, as text or `--json`; `--only`, `--ci` (GitHub Actions annotations), and the pull-request rules with `--base`, `--author` and `--skip progress`. Exit 1 when something chosen is missing, 2 for wrong usage.
- `swerepo init` for the `docs` and `agents` components: prints a plan, then creates missing files and adds SWERepo's marked blocks, never replacing a file; `--dry-run`, `--yes`, `--only` and shorthand flags (`--docs`, `--no-agents`; also on `check`).
- `swerepo adr new` and `swerepo adr index`: ADR files named `ADR-YYYYMMDD-xxxx-title.md` and a generated index; `swerepo progress`: Now, Next and the latest progress entries.
- `swerepo init` for the `ci` component: `.github/workflows/swerepo-ci.yml` (lint, tests on the declared Python versions, macOS on pushes, zizmor, SeamSpec's locked rules, dependency review, governance, jobs per `--projects` folder, and `ci-ok` checking each job's result), and ruff and pytest settings as a marked block in `pyproject.toml`; kept linters or a gradual move to ruff; `--with-governance`.
- `swerepo init` for the `security` component: `SECURITY.md` (GitHub's private vulnerability reporting, an email address, or a placeholder), `.github/workflows/swerepo-privacy.yml` and a `.gitignore` block; a privacy scan of personal email addresses, home-folder paths and obvious secrets that names files and lines only.
- `swerepo check`: the Python matrix against `requires-python`, `ci-ok` waiting for every job, monorepo project coverage, kept linters skipping `.seamspec`, and the privacy scan.
- `swerepo init` for the `github` component: the ruleset and merge settings as code (`.github/swerepo/`), applied through `gh` after they are shown (a hand-made `swerepo` ruleset is adopted), Copilot review instructions, PR and issue templates, Dependabot and CODEOWNERS; `--mode`, `--code-owner`, `--no-copilot-review`. Pull requests wait for Copilot's review inside `ci-ok`.
- `swerepo threads <pr>`: the open review threads of a pull request, read-only.
- `swerepo check` reads GitHub through `gh` (never with `--ci`): the live ruleset and merge settings against the committed files, secret scanning and push protection, and the dependency graph.

### Fixed

- `swerepo check` (Copilot's review of PR #3): values from files can no longer start a GitHub Actions workflow command in the text report; an explicit empty `components` or `[agents] hosts` chooses nothing; a `tool` value that isn't a table no longer crashes; only `run:` commands count as running `seamspec verify`; errors and dependency findings no longer repeat paths or values from files.
