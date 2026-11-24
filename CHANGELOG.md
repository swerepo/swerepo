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
- `swerepo init` for the `github` component: the ruleset and merge settings as code (`.github/swerepo/`), applied through `gh` after they are shown (a hand-made `swerepo` ruleset is adopted), Copilot review instructions, PR and issue templates, Dependabot and CODEOWNERS; `--mode`, `--code-owner`, `--no-copilot-review`. Pull requests wait for Copilot's review inside `ci-ok`, except Dependabot's own; Dependabot proposes a new version once it is a week old.
- `swerepo threads <pr>`: the open review threads of a pull request, read-only.
- `swerepo hook install`: a git pre-push hook that refuses a push whose new commits add a key, a personal email address or a home-folder path, by kind and place, never what; `swerepo privacy [--pre-push]` runs the scan on its own. `check` reminds locally when the hook is missing.
- `swerepo check` reads GitHub through `gh` (never with `--ci`): the live ruleset and merge settings against the committed files, secret scanning and push protection, and the dependency graph. A renamed ruleset or settings beyond merging are never applied, and `check` reports them. `init` asks to edit a kept ruleset or CODEOWNERS block only for the choices it lacks.
- `swerepo update` (`-u`): rewrites what SWERepo wrote and nobody changed with the current templates; merges the new templates into files a person edited, against the earlier render rebuilt from `.swerepo.toml`, only after a yes in a terminal or with `--yes --merge`, and leaves a conflict or an earlier render it can't rebuild alone, never writing conflict markers. Items no longer in the standard are reported, never deleted. Renders with the project's current commands and Python versions, and moves SWERepo's own CI pin to a release. A merge that would leave a JSON or TOML file unparseable is reported, never written. Action pins are never moved backwards, and Dependabot's newer pins alone update with `--yes`. `--only`, shorthand flags, `--dry-run`, `--json`, `--enforce-pr-rules`.
- `swerepo diff [FILE ...]`: the merge `update` would make in files you edited, or the change to make by hand for a conflict. `swerepo status [--json]`: components, mode, versions, and managed files by state. Both read only.
- `.swerepo.toml` records keep the inputs their render used (`inputs`), so `update` can rebuild each one's earlier render; `update` adds them to older records.
- `swerepo check` counts a workflow that differs only by newer action pins as current.

### Fixed

- `GitHub.find_ruleset` reads every page of rulesets, not only the first 100. `swerepo update --only github` changes the CI workflow only for the Copilot wait, never for `ci`'s own updates. `init`'s plan says how to keep branches after a merge when it creates `repo-settings.json`.
- `swerepo check` (Copilot's review of PR #3): values from files can no longer start a GitHub Actions workflow command in the text report; an explicit empty `components` or `[agents] hosts` chooses nothing; a `tool` value that isn't a table no longer crashes; only `run:` commands count as running `seamspec verify`; errors and dependency findings no longer repeat paths or values from files.
