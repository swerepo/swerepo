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
- `swerepo init` for the `seamspec` component: runs `seamspec init` in the person's terminal only (never `--accept-auto-run`; without a terminal the plan shows the command), never installs SeamSpec, and writes a pinned `seamspec.yml` when SeamSpec needs its own workflow. Proposes the hygiene rules (`privacy`, `adr-index`, `changelog`, `ci-tests`) with `seamspec propose`, each with its component, verified where the clone is trusted; a locked rule of the repository's own is adopted instead (`--adopt NAME=ID`, `[seamspec.adopted]`); a rule the person rejected is never proposed again. Writes `docs/EARNED_SPEC.md`.
- `swerepo check` for `seamspec`: the hygiene rules, proposals waiting, strict mode's workflow and CODEOWNERS block, and on a person's machine the CI pin against the installed SeamSpec, `seamspec doctor` and the earned spec. With `--ci` it runs no SeamSpec command.
- `swerepo update --only seamspec` moves the SeamSpec pin forward to the installed version, never back, with the CI workflow brought along for the pin only.
- `agents/address-review@3`: ask before resolving review threads, and resolve only on a yes.
- The project's spec, `SPEC.md`: `docs` writes a starter one or uses the spec a repository already has (a single `docs/SPEC.md` or root `*-SPEC.md` is recorded as `[adopted] spec`; several are listed, never guessed). The agents block, a new `update-spec.md` runbook, `prepare-pr.md`, the PR template, Copilot's review instructions and CONTRIBUTING say a change to behaviour, CLI flags, APIs or configuration updates it. `check` reports `docs.spec`.

### Changed

- Standard 1 has six components: `docs`, `agents`, `ci`, `security`, `github` and `seamspec`. `openspec` and `release` are gone, with their placeholders: SWERepo never sets up package publishing.
- The `seamspec` CI job and SWERepo's `seamspec.yml` fetch tags, so locked rules can read release tags.
- A codebase that has never been linted, in a repository with commits, moves to ruff gradually (only the files each change touches), so CI isn't red on day one; a new project still gets full ruff.
- A project without tests is warned: `init`'s plan and `check` (`ci.tests`, a warning) say the test job fails until there is one, and `prepare-pr.md` tells agents to write a real test, never to mask the job.
- `swerepo init` and `swerepo update` take `--editors claude,antigravity` (or `none`): the editors are set without the terminal question and recorded, replacing what was; the plan shows the change.
- When `agents` writes its commands without `ci` in the run, the plan says which tools `uv sync` won't install.
- The tools note names an optional extra `uv sync` doesn't install; a privacy finding about an address or a path says how to clear a placeholder; "dependency graph off" is said once.
- `swerepo init --yes` and `swerepo update --yes` no longer change GitHub: the ruleset and merge settings wait until `--yes --apply-github`, or a yes in a terminal after each is shown. `--apply-github` without `--yes` and without a terminal exits 2.
- A table another tool appends inside SWERepo's `pyproject.toml` block (such as uv's `[dependency-groups]`) is named with the fix, "move it above `# swerepo:begin`", and the file is left alone; the project's dependencies are read from the whole file.
- `swerepo check`'s "Next:" names what fixes each failing gap: `init` only for what it can write, then applying GitHub's settings, a command, or a step that is the person's. `--json` findings carry `fix`.
- `--editors` needs the `agents` component, counts a repeated name once, and refuses an empty list or `none` with other names. A dropped editor's file becomes the person's; choosing the editor again manages its unchanged block again, and an added non-Claude editor runs `seamspec init` again. The editors `seamspec init` set up are recorded (`[seamspec] hosts`) only once it succeeds, so one added while it waits is set up later. `[values] commands` moves on only when `AGENTS.md`'s block takes the new render, and `testpaths` set inside SWERepo's `pyproject.toml` block count. The tools note for `AGENTS.md` comes only for a project `uv sync` installs, for the tools its commands run through `uv run`, and once.
- CI's `copilot-review` passes at once while no active rule on the default branch requests Copilot's review (the ruleset not applied yet, or a private repository on GitHub Free), so the pull request that adds SWERepo doesn't wait 20 minutes for a review nothing requested; once a rule is there, every pull request waits as before. Any other failed read of the rules fails. `init` and `update` say so where they leave the ruleset unapplied, with `gh pr edit <number> --add-reviewer @copilot` to ask Copilot anyway, which the job's messages name too.

### Fixed

- `swerepo update --only <name>` with a name no component has is wrong usage, instead of advising `swerepo init --only <name>`.

### Fixed

- `GitHub.find_ruleset` reads every page of rulesets, not only the first 100. `swerepo update --only github` changes the CI workflow only for the Copilot wait, never for `ci`'s own updates. `init`'s plan says how to keep branches after a merge when it creates `repo-settings.json`.
- `swerepo check` (Copilot's review of PR #3): values from files can no longer start a GitHub Actions workflow command in the text report; an explicit empty `components` or `[agents] hosts` chooses nothing; a `tool` value that isn't a table no longer crashes; only `run:` commands count as running `seamspec verify`; errors and dependency findings no longer repeat paths or values from files.
