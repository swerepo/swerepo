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

### Fixed

- `swerepo check` (Copilot's review of PR #3): values from files can no longer start a GitHub Actions workflow command in the text report; an explicit empty `components` or `[agents] hosts` chooses nothing; a `tool` value that isn't a table no longer crashes; only `run:` commands count as running `seamspec verify`; errors and dependency findings no longer repeat paths or values from files.
