# SWERepo — Specification

**Status:** draft for the owner's review · **Version:** 0.16 (design) · **Date:** 2026-11-24
**Name:** SWERepo, command `swerepo`, at `github.com/swerepo/swerepo` (renamed from Golden Repo in v0.6, ADR-20261120-1a27)
**What changed:** Appendix A. **How the BLUEPRINT's ideas were handled:** Appendix B.

---

## Contents

1. [Summary](#1-summary)
2. [Problem](#2-problem)
3. [Goals and non-goals](#3-goals-and-non-goals)
4. [Who uses it, and how](#4-who-uses-it-and-how)
5. [Principles](#5-principles)
6. [The SWERepo standard](#6-the-swerepo-standard)
7. [Command line](#7-command-line)
8. [Components](#8-components)
9. [The state file: `.swerepo.toml`](#9-the-state-file-swerepotoml)
10. [Existing repositories](#10-existing-repositories)
11. [Monorepos](#11-monorepos)
12. [GitHub integration](#12-github-integration)
13. [SeamSpec integration](#13-seamspec-integration)
14. [Specs: SPEC.md](#14-specs-specmd)
15. [`swerepo check`](#15-swerepo-check)
16. [Updating](#16-updating)
17. [Safety, privacy and trust](#17-safety-privacy-and-trust)
18. [How it is built](#18-how-it-is-built)
19. [Open questions](#19-open-questions)
20. [Roadmap](#20-roadmap)
21. [Risks](#21-risks)
- [Appendix A: Revision history](#appendix-a-revision-history)
- [Appendix B: The BLUEPRINT's ideas](#appendix-b-the-blueprints-ideas)

---

## 1. Summary

**SWERepo sets up a repository the way an AI-assisted team should work, and keeps it that way.**

One command, `swerepo init`, brings a new or existing Python repository up to an agent-first engineering standard: strong CI, branch rules with code review, decision records (ADRs) and a progress log, instructions for AI agents (`AGENTS.md`, `CLAUDE.md`), a spec of what the project does (`SPEC.md`), and rules that agents can't quietly break (SeamSpec). `swerepo check` reports what a repository is missing. `swerepo update` (`-u`) brings it up to the latest standard, one part at a time, merging improvements into files people have edited where it can.

In one line: **a template tells you how to start; SWERepo also tells you where you stand, and brings you back.**

The standard (§6) is the product; the command line is how it is delivered.

---

## 2. Problem

- **Good engineering practice is spread across dozens of files and settings.** CI matrices, branch rules, review requirements, PR templates, decision records, changelogs, security policies. Most repositories have some of these, few have all, and almost none keep them current.
- **AI coding agents make the gaps expensive.** An agent with no written rules forgets agreements, rewrites tests to make them pass, commits personal data, adds a dependency for a ten-line problem, skips decision records and pushes straight to `main`. The practices that used to be "nice to have" are now how a team keeps control.
- **Templates only help on day one.** A template repository or a project generator creates files once. It can't tell you what an existing repository is missing, it can't update a repository when the standard improves, and GitHub's "Use this template" copies files only: no rulesets, no merge settings, no review rules.
- **Existing tools each cover one slice.** OpenSSF Scorecard scores security posture; github/safe-settings and the Probot Settings app manage GitHub settings as code across an organisation; Copier and cookiecutter generate projects. None of them writes rules for agents, adopts an existing repository's conventions, or checks and updates a single repository from a local command.
- **The owner has already worked out a standard the hard way.** SeamSpec's own repository (branches and PRs only, a Copilot review on every PR, an ADR for every decision, a progress log, a CI matrix with a single required check, a release workflow with a human approval step, SeamSpec enforcing its own rules) and lessons from dogfooding (privacy checks before commits, noreply commit emails, CI for a private repo). SWERepo turns that into something anyone can apply in minutes.

---

## 3. Goals and non-goals

**Goals (v0.1)**

1. `swerepo check` reports, without changing anything, which parts of the standard a repository meets, misses, or has changed (§15). Built first: it forces the standard to be exact enough for a machine to test.
2. `swerepo init` sets up a Python repository, new or existing, to the SWERepo standard (§6), asking before anything that leaves the repository.
3. `swerepo update` brings a repository up to the current standard, all at once or one component at a time (`-u --seamspec`), showing the plan first and merging into edited files where the merge is clean (§16).
4. Safe on established repositories: never overwrites a person's change, adds beside existing CI instead of editing it, adopts existing conventions (§10).
5. Works for one person and for teams: a `solo` and a `team` mode for branch rules (§12).
6. Every part optional; every run repeatable; every change shown before it is made.

**Non-goals**

- **Not a build system, package manager or framework.** It writes configuration and documents and calls other tools' setup commands; it doesn't replace uv, pytest, ruff or SeamSpec.
- **Not a release tool.** It never sets up publishing to PyPI or any other registry: a project that publishes sets that up itself (ADR-20261124-152d).
- **Not an AI tool.** SWERepo calls no language model. It writes instructions *for* agents; it doesn't run them (like SeamSpec's model-free core).
- **Not a policy engine for an organisation.** v0.1 works on one repository at a time. Running `check` across many repositories is a later feature (§20).
- **Not every language.** Python first. TypeScript next (§20).
- **Not a replacement for review.** It sets up the review process; people still review.
- **Not a lock against an agent using the person's own login.** It makes breaking the process visible; hard locks need a second identity (§17).

---

## 4. Who uses it, and how

| Who | Scenario | Commands |
|---|---|---|
| A developer starting a project | Empty folder or a fresh `uv init` project | `swerepo init` (offers `git init` if needed) |
| A team with an established repository | Years of history, existing CI, some docs, no agent instructions | `swerepo check`, then `swerepo init --only docs,agents`, … one PR per step |
| A solo developer with agents | Agents open PRs; the person reviews and merges | `swerepo init --mode solo`, or `--mode team` with agents under their own identity (§17) |
| A platform or DevEx team | Wants every repository in the company on the same standard | `swerepo check --json` in a script or in CI; later, a multi-repo report (§20) |
| Anyone, months later | The standard improved, or SeamSpec released a new version | `swerepo update`, or `swerepo -u --seamspec` |
| A maintainer keeping it honest | CI fails if the repository drifts from the standard or a PR skips the process | `swerepo check --ci --base <ref>` in the CI workflow (§15) |

---

## 5. Principles

1. **Show, then do.** Every command that changes something prints its plan first. `--dry-run` prints the plan and stops. Without a terminal, it never asks; it either has the flags it needs or stops.
2. **Never overwrite what a person changed.** SWERepo records a fingerprint of every file and block it writes (§9). A file nobody changed can be updated; a file someone edited is updated only by a clean three-way merge shown in the plan, and otherwise left alone and reported (§16).
3. **Add beside, don't edit.** In an existing repository, SWERepo adds its own workflow files and marked blocks; it doesn't rewrite your workflows, your README or your configuration.
4. **Ask before anything outside the repository.** GitHub settings, installing a tool, a network call to a service: each needs a yes, or an explicit flag. Nothing is ever committed, pushed, published or merged by SWERepo.
5. **Everything optional.** Each component (§8) can be skipped (`--no-seamspec`) or applied alone (`--only seamspec`).
6. **Repeatable.** Running `init` twice changes nothing the second time. `init` on a repository already at the standard is the same as `update`.
7. **Small, reviewable steps.** On an established repository, the recommended path is one component per pull request (§10).
8. **Honest reporting.** `check` says "missing", "changed by you", "outdated" or "can't tell (needs GitHub access)", never a vague score. The documentation says plainly what the rules can and can't stop (§17).
9. **Built for parallel work.** Several agents on several branches at once is the normal case. Nothing in the standard asks every PR to edit the same lines of the same file (§6.5).
10. **Few tools to install.** Python, uv, git and `gh`. Anything else (SeamSpec, scanners) belongs to an optional component or runs through `uvx`.
11. **Model-free, no telemetry.** No language model calls, no usage tracking, no data leaves the machine except the GitHub calls you approve.
12. **Dogfooded.** SWERepo's own repository is set up by SWERepo, and its CI runs `swerepo check --ci` on itself.

---

## 6. The SWERepo standard

The standard is versioned (`standard = 1` in v0.1) and listed in full here. Each item belongs to one component (§8).

**A new Python project after `swerepo init`, all components:**

```text
<project-root>/
├── AGENTS.md                      # the working rules (marked block)
├── CLAUDE.md                      # @AGENTS.md + SeamSpec's block
├── GEMINI.md                      # points to AGENTS.md (only if Antigravity or Gemini is used)
├── CHANGELOG.md  CONTRIBUTING.md  SECURITY.md  README.md
├── SPEC.md                        # what the project does and is for (§6.7)
├── .swerepo.toml                   # what SWERepo applied (§9)
├── docs/
│   ├── PROGRESS.md                # Now / Next (edited rarely)
│   ├── progress/                  # one entry per PR (§6.5)
│   ├── agents/                    # runbooks agents read on demand (§6.6)
│   ├── EARNED_SPEC.md             # rules SeamSpec enforces today (§6.8)
│   └── adr/                       # README (with generated index), TEMPLATE, ADRs
├── .github/
│   ├── swerepo/                # ruleset.json, repo-settings.json (§12)
│   ├── workflows/                 # swerepo-ci.yml, swerepo-privacy.yml
│   ├── copilot-instructions.md    # what Copilot review should and shouldn't comment on
│   ├── CODEOWNERS  pull_request_template.md  dependabot.yml  ISSUE_TEMPLATE/
└── .seamspec/                     # written by SeamSpec (§13)
```

### 6.1 Git and GitHub (component `github`)

- **Branch rules as code:** `.github/swerepo/ruleset.json` (the ruleset) and `.github/swerepo/repo-settings.json` (merge settings), committed and reviewed like any other change, applied through `gh` (§12). Two modes:
  - **`solo`**: changes only through pull requests; required status check `ci-ok` (§6.2); no force pushes; no branch deletion; Copilot code review requested on every pull request where the account has it; review threads must be resolved when Copilot review is on.
  - **`team`**: everything in `solo`, plus one approving review, stale approvals dismissed on push, and code-owner review (which, with the CODEOWNERS below, applies to governance files only).
- **Merge settings:** squash merging only; head branches deleted after merge. Auto-merge stays off (SWERepo never merges, and doesn't make merging unattended).
- `.github/copilot-instructions.md`: tells Copilot review to skip style that ruff already checks, and to comment on missing ADRs and progress entries, behaviour changes without tests or without a spec update (§6.7), changes to locked rules or CI, and security problems. Needed because resolved threads are required: every comment blocks the merge until answered.
- `.github/pull_request_template.md`: what changed, spec and decisions touched, checklist (tests pass locally, progress entry added, ADR if needed, spec updated when behaviour changed (§6.7), review threads answered).
- `.github/CODEOWNERS` for governance paths only: `/.github/`, `/.swerepo.toml`, `/AGENTS.md`, `/CLAUDE.md`, `/docs/adr/`, `/docs/agents/`, `/.seamspec/` and `/docs/EARNED_SPEC.md`. The spec (§6.7) is deliberately not among them: feature pull requests update it, without a code owner's review (ADR-20261124-4d76). The owner is asked for (default: the repository owner from `gh`), never guessed from git config.
  - The lines go in a marked block (`# swerepo:begin` … `# swerepo:end`) **at the end of the file**, in a new CODEOWNERS or an existing one, because in CODEOWNERS the last matching line wins. A team's own lines (per-folder owners) stay above the block.
  - If lines are later added below the block, `check` reports `~ CODEOWNERS: lines after the SWERepo block can override governance owners`, naming any that do.
- `.github/ISSUE_TEMPLATE/` for bugs and features.
- `.github/dependabot.yml`: weekly updates for GitHub Actions and Python dependencies, each new version proposed once it is 7 days old (`cooldown`), since a broken or malicious release is usually pulled by then. Security updates don't wait (ADR-20261123-cc8d).
- Commits under a noreply address: `check` warns when recent commits use a personal email address (lesson from SessionWalk), and also when the repository's `git config user.email` is one, so a new repository with no commits yet is caught before its first commit. `init` shows the same warning, with the command to set a noreply address for this repository, before it prints the steps that start with a commit (§12).

### 6.2 CI (component `ci`)

- `.github/workflows/swerepo-ci.yml`:
  - **lint**: ruff lint and format check, or the project's existing linters (§6.3);
  - **tests**: pytest through uv on Linux, on every Python version the project supports. The versions come from `requires-python` (for a new project, `>=3.11`, so 3.11 to 3.14), up to the newest version standard 1 knows; SWERepo never changes a declared range;
  - **tests-macos**: on pushes to `main` only (macOS minutes cost about ten times more on private repositories);
  - **workflow-audit**: `zizmor` on `.github/workflows/`, run through `uvx` at a pinned version;
  - **governance**: on pull requests, `swerepo check --ci --base <base branch> --author <login>` at a pinned SWERepo version (§15; an unreleased SWERepo doesn't add this job unless asked);
  - **seamspec**: SeamSpec's locked rules, inside `ci-ok` so a failing rule blocks the merge (ADR-20261122-4a06): `seamspec doctor --ci`, `seamspec verify --all --ci` and `seamspec spec --check docs/EARNED_SPEC.md` (§6.8) at the pinned SeamSpec version (`[tools] seamspec`). The job is always in the workflow: without `.seamspec/config.toml` it says so and passes, so setting SeamSpec up later needs no workflow change;
  - **dependency-review**: on pull requests to public repositories, GitHub's `dependency-review-action` (fails on new dependencies with known vulnerabilities). On private repositories it needs a paid GitHub plan, so the job is skipped there by a condition in the workflow;
  - **one lint and one test job per project** listed with `--projects` (§11);
  - **copilot-review**: where the `github` component turns Copilot review on, pull requests wait for Copilot's review (of any commit) inside `ci-ok`: the job asks GitHub every 30 seconds for up to 20 minutes, and a later push passes at once. A draft fails at once, and the workflow runs again when it is marked ready for review (ADR-20261123-a359). Pull requests opened by Dependabot (`dependabot[bot]`) pass at once while every commit is Dependabot's, verified and committed by GitHub itself, on a branch in the repository, and fail at once with any other commit: a dependency update's pull request holds only Dependabot's commits. GitHub never requests Copilot's review for them, and the person who merges reviews the update (ADR-20261123-cc8d);
  - **`ci-ok`**: a single aggregating job (`if: always()`) that reads every job's result: each must succeed, except a job skipped by design (macOS off pushes, governance off pull requests, dependency review off pull requests to public repositories), which must be skipped; failed, cancelled or unexpectedly skipped jobs fail it. The ruleset requires only `ci-ok`, so adding a job never means editing GitHub settings.
- **Installing the project:** `uv sync --locked` with a `uv.lock` (the project's own, or its uv workspace's), `uv sync` without. Projects uv can't install (Poetry's lock without uv's, no `pyproject.toml` or no `[project]` table) get no workflow in standard 1's first template, and the plan says why. Lint and tests run the project's own tools through `uv run`; the plan names those missing from its dependencies (`uv add --dev pytest ruff`), since SWERepo never edits dependencies.
- Actions pinned to commit SHAs, `permissions: contents: read` by default, `persist-credentials: false` on checkout, `concurrency` to cancel superseded runs, a `timeout-minutes` on every job.
- The type checker is an option (§19).

### 6.3 Code quality (component `ci`)

- Settings for ruff and pytest in a **marked block at the end of `pyproject.toml`** (`# swerepo:begin` … `# swerepo:end`; ADR-20261122-4a06): `[tool.ruff]` only when ruff is chosen and not configured, `[tool.pytest.ini_options]` only when the project has no pytest configuration. The person's text above it is kept byte for byte; if the block would clash with their TOML, it isn't added and the plan says so.
- **Projects that already lint.** SWERepo looks for existing linters and formatters (ruff, black, isort, flake8, pylint) in `pyproject.toml`, `setup.cfg`, `tox.ini`, `.flake8` and `.pre-commit-config.yaml`:
  - **ruff already configured:** its configuration is kept as it is; the lint job runs it.
  - **other tools found:** the person chooses (shown in the plan; the default is the first):
    1. **keep them**: no ruff settings are added; the lint job runs the detected tools through `uv run`, and they are recorded under `[adopted] linters`;
    2. **move to ruff gradually**: ruff settings are added, matched to the existing line length where it can be read (ruff takes the target version from `requires-python`), and ruff checks **only the Python files each change touches** (a pull request against its base, a push against the commit before it), so existing code isn't flagged all at once. SWERepo never reformats or edits code to make it pass.
  - **nothing found:** ruff, as for a new project.
- The pytest section is added only when the project has no pytest configuration of its own (`pytest.ini`, `setup.cfg`, `tox.ini`, `pyproject.toml`).
- **Locked SeamSpec tests are never linted or reformatted** (SeamSpec's ADR-20261013-c3f7). SeamSpec records a hash of each approved rule test, and any edit, even whitespace, counts as tampering. A `ruff format .` run by an agent would break every lock, and `seamspec init` doesn't add the exclusion to the repositories it sets up. So:
  - SWERepo's ruff settings include `extend-exclude = [".seamspec"]`;
  - with kept linters (black, flake8, …), the lint job passes the exclusion on the command line, and `check` reports `~` with the one-line change to make when a tool's own settings would still touch `.seamspec/` locally. SWERepo doesn't edit those tools' settings itself;
  - an existing ruff configuration that covers `.seamspec/` gets the same `~` report.
- Optional pre-commit configuration that runs the same checks locally.

### 6.4 Security and privacy (component `security`)

- `SECURITY.md`: how to report a vulnerability. The contact is asked for: GitHub's private vulnerability reporting (the default with a GitHub remote; no address is published, and the owner turns it on in the repository's settings), an email address, or a placeholder to fill in (ADR-20261122-a48e). Written once; the person's from then on.
- A privacy check (`.github/workflows/swerepo-privacy.yml` and the same check locally as `swerepo check --only security`): no personal email addresses, no home-folder paths, no obvious secrets (private keys and well-known token formats) in tracked files and in untracked files git would add. `[privacy] allow_paths` globs read as git's (`*` within a folder, `**` across folders). Findings name the file and line, never what was found. Lesson from SessionWalk, where personal details had to be removed from history. The workflow needs a SWERepo it can install, as the `governance` job does (§15); on pull requests, `governance` reports the same findings inside `ci-ok`.
  - **Allowed by default:** noreply addresses (`users.noreply.github.com`), reserved example domains (`example.com`, `example.org`, …), emails in `[project].authors` and `maintainers` in `pyproject.toml`, the contact in `SECURITY.md`, and placeholder home paths (`/Users/me`, `/home/user`, `C:\Users\you`, `~`).
  - **Allowed by the person:** files or globs listed under `[privacy] allow_paths` in `.swerepo.toml`, and a single line marked with a `swerepo: allow-privacy` comment. Allowances name files, never the addresses themselves, so no personal data goes into `.swerepo.toml`.
- **A pre-push privacy hook** (ADR-20261123-24e0): `swerepo hook install` writes a git `pre-push` hook that runs the same scan on the lines each commit about to be pushed adds, so a key, a personal email address or a home-folder path never reaches GitHub. It shows the kind, the commit and `file:line`, never what was found.
  - **Pre-push, not pre-commit,** because SeamSpec owns the pre-commit hook. A pre-push hook of the person's own is never replaced; the command prints the line to add to it instead.
  - **Runs SWERepo** through the recorded `privacy_command`, else `swerepo`.
  - **What counts as new:** commits the remote being pushed to doesn't have, and the lines a merge adds that no parent had.
  - **Fails closed** when SWERepo can't run. `git push --no-verify` skips it on purpose.
  - **Per clone:** hooks aren't tracked, so each clone installs its own; locally, `check` reminds as a warning, never with `--ci`.
- Guidance to turn on GitHub secret scanning and push protection (free on public repositories); `check` reports whether they are on when it can read the setting.
- `.gitignore` entries for local secrets and machine-specific files (`.env`, editor and agent machine configs), in a marked block.

### 6.5 Documents (component `docs`)

Designed so that parallel branches don't collide: each PR adds its own files, and shared indexes are generated.

- `README.md` when there is none: what it is, install, test, contributing. An existing README is never edited (principle 3; ADR-20261121-6c3d).
- `docs/adr/`: `README.md` (format, naming, and an index between `<!-- swerepo:adr-index:begin -->` markers, **generated** by `swerepo adr index`) and `TEMPLATE.md`. Naming follows SeamSpec's convention: `ADR-YYYYMMDD-xxxx-short-title.md` (the random `xxxx` keeps two branches from picking the same name), statuses `PROPOSED | ACCEPTED | SUPERSEDED | REJECTED`. `swerepo adr new "title"` creates one from the template. When two branches both add an ADR, the index conflict is fixed by rerunning `swerepo adr index`. An existing ADR folder is adopted instead (§10); its index is generated only if the person agrees.
- **Progress:**
  - `docs/PROGRESS.md`: **Now** and **Next**, short, edited only when priorities change.
  - `docs/progress/YYYYMMDD-<slug>.md`: **one new file per deliverable PR** (what was done, branch or PR, ADRs and locked rules touched, what's next). Never edited by later PRs, so parallel branches never conflict.
  - `swerepo progress` prints Now, Next and the latest entries, for people and agents.
- `CHANGELOG.md` in the Keep a Changelog format, with an `[Unreleased]` section (fragments instead: §19).
- `CONTRIBUTING.md`: branches and PRs only, branch naming, the PR template, ADR and progress rules, keeping the spec current (§6.7), how reviews are answered, which mode the repository uses and what it means (§17).
- `SPEC.md` (§6.7): a starter spec when the repository has none.
- `LICENSE` only when the person adds one: SWERepo never picks a license, and the plan notes when there is none (ADR-20261121-6c3d).
- **PR rules checked in CI** (`check --base`, §15):
  - every PR adds a progress entry, unless one of its commits carries the trailer `Progress: none` (for typo fixes and other small changes; it works in a local `check` as well as in CI);
  - a PR that adds a runtime dependency (a new name under `[project].dependencies`, not a version change) adds or changes an ADR in the same PR;
  - a PR that changes a CI workflow (`.github/workflows/`) adds or changes an ADR in the same PR, because weakening CI is a change to the process. Changes SWERepo made itself (the file matches the render recorded in `.swerepo.toml`) and changes by bots (Dependabot's action updates) don't count.
  - The spec (§6.7) has no pull-request rule: refactors and bug fixes change code without changing intended behaviour, and a warning on each of them would teach people to ignore warnings (ADR-20261124-4d76).

### 6.6 Agent instructions (component `agents`)

- **Which editors.** `init` asks which agents and editors the project uses (Claude Code, Cursor, VS Code Copilot, Antigravity or Gemini CLI), pre-filled from what it finds (`.cursor/`, `.vscode/`, `.agents/`, existing agent files), and records the answer under `[agents] hosts`. Files are written only for the editors chosen: no speculative `GEMINI.md`, because other tools read its presence as a sign that Antigravity is in use (SeamSpec does, §13).
- **One source, no copies.** The rules live in a marked SWERepo block (`<!-- swerepo:begin -->` … `<!-- swerepo:end -->`) in `AGENTS.md`, which Cursor, VS Code Copilot, Antigravity and others read directly. `CLAUDE.md` (when Claude Code is chosen) holds `@AGENTS.md` (Claude Code expands the import) beside SeamSpec's Claude block and anything already there. `GEMINI.md` (when Antigravity or Gemini is chosen) points to `AGENTS.md`. Nothing is duplicated, so nothing needs to be kept in sync.
- **With SeamSpec and several editors**, `AGENTS.md` also holds SeamSpec's block for the other editors (`/seamspec-*` commands) and `CLAUDE.md` its Claude block (`/seamspec:*`). Through the import, Claude Code reads both: the same protocol twice with two spellings of each command. Claude-only projects don't have this (no SeamSpec block in `AGENTS.md`). For mixed projects, whether it confuses agents is measured in a real session (§19.9); if it does, the fallback is to render SWERepo's block into both `AGENTS.md` and `CLAUDE.md` instead of importing. Both copies are fingerprinted, so `check` reports either one drifting.
- The block states the working rules, learned on SeamSpec and SessionWalk:
  1. Start by reading `docs/PROGRESS.md` and the latest entries in `docs/progress/` (or run `swerepo progress`).
  2. Never push to the default branch; one branch and one PR per piece of work.
  3. Add one progress entry in `docs/progress/` in the same PR as the work (`Progress: none` trailer only for trivial changes).
  4. Any change to the design, the process (CI workflows included), or the runtime dependencies gets an ADR (`swerepo adr new`).
  5. Run the full test suite before saying tests pass, even for docs-only changes.
  6. Before committing: no personal emails, home paths, keys or passwords in the change.
  7. Answer every review thread (fix it and reply with the commit, or reply why not) before asking for a merge; `swerepo threads <pr>` lists the open ones. (The block names `swerepo threads` from the template version that ships with it, Phase 5.)
  8. Never publish a package, approve a deployment or merge without the person's explicit go-ahead.
  9. When a test fails, fix the code; never weaken the test to make it pass (and, with SeamSpec, never edit a locked rule's test: request a supersede).
  10. A change to behaviour, CLI flags, APIs or configuration updates the spec (`SPEC.md`, or the adopted file, §6.7) in the same PR.
- **Commands** are listed in the block, so agents never guess them: install (`uv sync`), test (`uv run pytest`), lint (`uv run ruff check` and `uv run ruff format --check`), check (`swerepo check`). They are rendered from what the project uses; an existing Makefile or task runner is listed instead when one is detected.
- **Runbooks on demand:** step-by-step guides in `docs/agents/`, plain Markdown that every agent can read, so the block stays short. One line in the block points to them:
  - `prepare-pr.md`: branch, tests, progress entry, ADR if needed, the spec when behaviour changed, PR template; if the PR approves or supersedes SeamSpec rules, regenerate `docs/EARNED_SPEC.md` in the same PR (`seamspec spec --out docs/EARNED_SPEC.md`);
  - `address-review.md`: `swerepo threads`, fix or reply to each thread with the commit, summary comment;
  - `record-adr.md`: when an ADR is needed, `swerepo adr new`, index, superseding;
  - `update-spec.md`: what belongs in the spec and what doesn't; on an existing codebase, start from the part a change touches instead of describing everything at once.
  Editor-specific skills and slash commands that wrap these runbooks are a later option (§20); the runbooks stay the single source.
- Wording is kept short (a target of under 40 lines for the block): agents read it every session, and long instructions cost tokens and attention (§19.9).

### 6.7 Specs (components `docs` and `agents`)

- **`SPEC.md`** at the root: what the project does and is for, in short sections (purpose, who it's for, behaviours, out of scope, open questions). `docs` writes it from a starter template when the repository has no spec; it is the person's from then on (§14, ADR-20261124-4d76).
- **An existing spec is used** instead (§14): a root `SPEC.md` as it is, or a single `docs/SPEC.md` or root `*-SPEC.md` recorded as `[adopted] spec` (§9). When there are several, SWERepo lists them and the person records one.
- **Kept current by the agents' rule** (§6.6, rule 10), `prepare-pr.md`, `update-spec.md`, the PR template's checklist, Copilot's review instructions and CONTRIBUTING, not by a CI check.

### 6.8 Locked rules (component `seamspec`)

- SeamSpec set up through its own command (§13), in enforced mode, its locked rules run by the `seamspec` job in `swerepo-ci.yml` (§6.2; ADR-20261122-4a06). When SeamSpec needs a workflow of its own (the component without `ci`, or strict mode), SWERepo writes `.github/workflows/seamspec.yml` from its own template, with actions pinned to commits, so it passes the workflow audit. It runs the same steps as the `seamspec` job, `seamspec spec --check` included, and once written `update` keeps it current, also after `ci` is added; it isn't written when `requires-python` allows no Python version standard 1 knows (ADR-20261124-cd64).
- **`docs/EARNED_SPEC.md`**: the rules SeamSpec enforces today, written by `seamspec spec --out docs/EARNED_SPEC.md` and checked in CI with `seamspec spec --check docs/EARNED_SPEC.md`. Reviewers see a change to the enforced rules as a readable diff, next to what `SPEC.md` (§6.7) says was planned.
- The **hygiene rule pack** proposed as SeamSpec rules, for the person to approve, each only when its component is set up (ADR-20261124-cd64):
  1. `hygiene/privacy`: no personal email addresses or home-folder paths in tracked files (same allowances as §6.4, `[privacy] allow_paths` included). With `security`.
  2. `hygiene/adr-index`: every ADR file is listed in the ADR index (`[adopted] adr_dir` respected). With `docs`, and only when the ADR README has the index markers.
  3. `hygiene/changelog`: `CHANGELOG.md` keeps an `[Unreleased]` section. With `docs`.
  4. `hygiene/ci-tests`: the CI workflow still runs the test suite (`test`, and `test-<project>` for each listed project) and `ci-ok` still depends on each (so an agent can't quietly weaken CI). With `ci`.
- A rule the repository already locks for one of these is **adopted** instead of proposed again: `[seamspec.adopted]` in `.swerepo.toml` names it (§9).
- **The rule tests run in the target repository**, so they use only the Python standard library and pytest: no PyYAML or other packages the project may not have. Rule 4 checks the workflow by matching the text of the job and `needs:` lines SWERepo wrote, not by parsing YAML. The bundled tests pass ruff's check and format before they ship, since a locked test can't be tidied afterwards.

---

## 7. Command line

```
swerepo init     [--only C,...] [--no-C ...] [--mode solo|team] [--code-owner @LOGIN] [--no-copilot-review]
                 [--projects P,...] [--with-governance] [--adopt NAME=ID ...] [--dry-run] [--yes] [--path DIR] [--json]
swerepo check    [--only C,...] [--base REF] [--author LOGIN] [--skip progress] [--json] [--ci] [--path DIR]
swerepo update   [--only C,...] [--enforce-pr-rules] [--dry-run] [--yes] [--merge] [--path DIR] [--json]
swerepo -u       (short for `update`; `swerepo -u --seamspec` = `update --only seamspec`)
swerepo diff     [FILE ...] [--path DIR]   what update would change in files you edited, and any merge conflicts
swerepo status   [--path DIR] [--json]     components applied, mode, standard version, tool versions, files by state
swerepo progress [-n N]              Now, Next and the latest N progress entries
swerepo adr new TITLE                a new ADR from the template, with a fresh name
swerepo adr index                    regenerate the ADR index
swerepo threads PR                   open review threads of a PR, compact (read-only; through `gh`)
swerepo privacy [--pre-push]         the privacy scan; with --pre-push, of the commits git is about to push
swerepo hook install                 the pre-push privacy hook (never replaces a hook of yours)
swerepo --version
```

- **Components** (`C`): `docs`, `agents`, `ci`, `security`, `github`, `seamspec` (ADR-20261124-152d). `--only` selects; `--no-<component>` skips. `--seamspec` alone is shorthand for `--only seamspec` (and so for each component), on `init` and `check`.
- **`--mode`**: `solo` or `team` (§12). Default: `solo` for a repository owned by a user, `team` for one owned by an organisation; always shown in the plan.
- **`--code-owner`**: the CODEOWNERS owner of governance files, `@login` or `@org/team`, or `none` (§6.1). Default: the repository's owner when that is a user; never guessed from git config. Without one, CODEOWNERS isn't written, and `check` warns without failing.
- **`--no-copilot-review`**: a ruleset without Copilot review, and no wait for it in CI (§12).
- **Without a terminal**, `init` applies only with `--yes`; otherwise it prints the plan and exits `2` without writing (ADR-20261121-6c3d).
- **`--yes`** answers yes to SWERepo's own questions in scripts. It never answers another tool's consent (SeamSpec's consent to run tests stays a person's answer; §13).
- **`--json`** prints one machine-readable result (plan, changes, findings) for scripts.
- **`--projects`**: in a monorepo, the Python project folders that get their own CI jobs and settings (§11).
- **`--enforce-pr-rules`**: switches the pull-request rules from warnings to failures (§10).
- **`--with-governance`**: adds the `governance` CI job even when this SWERepo build is unreleased (§15).
- **`threads`** only reads: it never replies to or resolves a thread.
- **Exit codes:** `0` done or nothing to do; `1` `check` found something missing or `init/update` couldn't complete; `2` wrong usage.

**Example: a new project**

```
$ swerepo init
SWERepo · plan for /Users/me/code/invoices (new Python project, git: yes, GitHub: me/invoices, mode: solo)
  docs      create  SPEC.md, docs/adr/README.md, docs/adr/TEMPLATE.md, docs/PROGRESS.md, docs/progress/, CHANGELOG.md,
                    CONTRIBUTING.md
  agents    create  AGENTS.md (rules, commands), CLAUDE.md (@AGENTS.md), docs/agents/ (4 runbooks)   [editors: Claude Code, Cursor]
  ci        create  .github/workflows/swerepo-ci.yml (Python 3.11–3.14);  update pyproject.toml ([tool.ruff], [tool.pytest])
  security  create  SECURITY.md, .github/workflows/swerepo-privacy.yml;  update .gitignore
  github    create  .github/swerepo/ruleset.json, repo-settings.json, copilot-instructions.md,
                    PR template, CODEOWNERS (owner: me), issue templates, dependabot.yml
            ask     apply ruleset "swerepo" on main (PRs only, ci-ok required, Copilot review, threads resolved)
            ask     merge settings (squash only, delete merged branches)
  seamspec  run     seamspec init (asks its own questions);  propose 4 hygiene rules
Apply? [y/N]
```

---

## 8. Components

Each component has the same four parts: what it **writes**, what it **runs**, what it **asks**, and what `check` **looks for**.

| Component | Writes | Runs | Asks | Check looks for |
|---|---|---|---|---|
| `docs` | ADR folder (README with index, template), PROGRESS, `docs/progress/`, CHANGELOG, CONTRIBUTING, README and `SPEC.md` (when missing) | — | — (a missing license is noted, never picked) | each file present; a spec present (`SPEC.md` or the adopted one); ADR index matches the ADR files; CHANGELOG has `[Unreleased]`; with `--base`: progress entry added, ADR for new dependencies |
| `agents` | AGENTS.md block, CLAUDE.md import, GEMINI.md (each only for the editors chosen), `docs/agents/` runbooks | — | which agents and editors are in use | block and runbooks present and current; CLAUDE.md imports AGENTS.md; listed commands still exist |
| `ci` | `swerepo-ci.yml`; ruff and pytest settings (per project in a monorepo) | — | the type checker (§19); keep existing linters or move to ruff gradually | workflow present, current or merged; `ci-ok` aggregates every job; Python versions match `requires-python`; every project root covered by a required check or recorded as not covered |
| `security` | SECURITY.md, privacy workflow, `.gitignore` block | the privacy scan once, to report findings before committing | the security contact | files present; privacy scan clean; secret scanning on (if readable) |
| `github` | `.github/swerepo/*.json`, copilot-instructions, PR template, CODEOWNERS, issue templates, dependabot | `gh` to apply the ruleset and merge settings | **the mode, the code owner, the ruleset and the merge settings** (always shown first); extra required checks in a monorepo | files present; SWERepo's CODEOWNERS block last; ruleset applied, or waiting for a GitHub repository; live ruleset and settings match the committed files (needs `gh`); plan limits explained |
| `seamspec` | `docs/EARNED_SPEC.md` (through SeamSpec, after the first review; SeamSpec writes its other files) | `seamspec init`; `seamspec propose` for the rule pack; `seamspec review` if the person agrees; `seamspec spec --out` | SeamSpec asks its own consent; SWERepo asks before proposing and before starting the review | SeamSpec set up; CI pin matches the installed SeamSpec; plugin current; hygiene rules locked; earned spec current (`seamspec spec --check`) |

**Generated files** are rendered from templates bundled in the package, with a few values filled in (project name, Python versions, default branch, code owner, mode). Every released template version stays in the package, so an earlier render can always be rebuilt for a three-way merge (§16). Templates are plain files at `swerepo/templates/<component>/<name>/<version>[.<ext>]` with `@@name@@` placeholders and no logic; a missing value is an error, and a released version never changes (ADR-20261120-b25a).

---

## 9. The state file: `.swerepo.toml`

Committed with the repository, so every clone and CI knows what was applied.

```toml
standard = 1                      # version of the SWERepo standard
swerepo = "0.1.0"              # version that last wrote this file
components = ["docs", "agents", "ci", "security", "github", "seamspec"]
mode = "solo"

[values]                          # what templates were rendered with (all already in the repository's files)
project = "invoices"
python = ["3.11", "3.12", "3.13", "3.14"]
default_branch = "main"
ci_install = "uv sync --locked"   # how CI installs the project (§6.2)
lint = "ruff"                     # ruff | kept | gradual (§6.3)
governance_command = ""           # how swerepo-ci.yml runs SWERepo; "" until a released one can be pinned (§15)
privacy_command = ""              # the same for swerepo-privacy.yml (§6.4)
privacy_python = "3.14"           # the Python swerepo-privacy.yml runs on (each workflow keeps its own snapshot)
code_owner = "@me"

[files."docs/adr/TEMPLATE.md"]
template = "docs/adr-template@1"
rendered = "9f2c…"                # hash of the template's own output (the merge base)
written = "9f2c…"                 # hash of what SWERepo wrote (differs after a merge)

[files.".github/workflows/swerepo-ci.yml"]
template = "ci/python@1"
rendered = "a41b…"
written = "a41b…"

[blocks."AGENTS.md"]
template = "agents/block@1"
rendered = "0c7e…"                # of the block content only
written = "0c7e…"
inputs = { commands = "…", project = "invoices" }  # the values this render used, nothing more (§16)

[blocks."pyproject.toml"]            # ruff and pytest settings (§6.3)
template = "ci/pyproject@1"
rendered = "77d0…"
written = "77d0…"

[tools]
seamspec = "0.1.1"                # the version the CI workflow pins

[seamspec]
initialised = "0.1.2"             # the SeamSpec version `seamspec init` last ran with; an upgrade reruns it (§13)

[seamspec.adopted]                # hygiene rules a locked rule of the repository's own already covers (§6.8)
privacy = "inv_62d51113"

[adopted]
adr_dir = "doc/decisions"         # an existing convention SWERepo follows instead of its own (§10)
spec = "INVOICES-SPEC.md"         # the project's existing spec, instead of a new SPEC.md (§6.7)
progress_dir = "docs/changes"     # where per-PR progress entries go, if not docs/progress
linters = ["black", "flake8"]     # kept instead of ruff (§6.3)

[agents]
hosts = ["claude", "cursor"]      # editors chosen (§6.6); passed to `seamspec init --hosts`

[privacy]
allow_paths = ["tests/fixtures/**"]

[pr]
enforce = false                   # warn-only at first in an existing repository (§10)
warn_since = 2026-11-19
exempt_authors = ["dependabot[bot]"]
skip_progress_label = "no-progress"   # optional; the commit trailer `Progress: none` always works

[github]
applied = true                    # false until the ruleset and settings are applied (§12)
copilot_review = true             # the ruleset requests Copilot's review, and CI waits for it (ADR-20261123-a359)
extra_required_checks = []        # monorepo: other workflows' checks required beside ci-ok (§11)

[projects]                        # monorepos only (§11)
ignore = []                       # folders that are not projects, besides tests/, docs/, tools/ … (§11)
listed = []                       # Python projects with their own SWERepo jobs
not_covered = []                  # project roots knowingly outside every required check

[projects.inputs."services/api"]  # what a listed project's jobs were rendered from (§11)
python = ["3.12", "3.13", "3.14"]
install = "uv sync --locked"
lint = "ruff"                     # ruff | kept
linters = []
```

- **Hashes are of normalised content** (SHA-256, 64 hex characters, ADR-20261120-9495): UTF-8, no byte-order mark, LF line endings, trailing whitespace removed from each line, exactly one final newline. Line-ending conversion and end-of-file fixers don't make a file look edited. A formatter that changes more than that (reflowing Markdown, reformatting YAML) does, and `check` reports it as `~`; the generated files are written to pass ruff and common formatters unchanged.
- **What is recorded:** files SWERepo keeps current (the ADR README and TEMPLATE, the `docs/agents/` runbooks, workflows, settings) and its blocks. Starter files it writes once (README, PROGRESS, CHANGELOG, CONTRIBUTING, SPEC.md, the first progress entry) are the person's from then on and not recorded. The ADR README's generated index is left out of its hash (ADR-20261121-6c3d).
- **Edited or not:** a file whose current hash equals `written` was not edited since SWERepo last wrote it. Otherwise a person changed it, and `update` merges (§16).
- **Read and written with tomlkit**, so comments and unknown keys survive; validated on load; an older SWERepo never overwrites a file a newer one wrote (ADR-20261120-ecf7).
- **No secrets, no personal data** ever go in this file. `[values]` holds only what is already in the repository's own files.
- Deleting `.swerepo.toml` makes the next run treat every existing file as the person's own (safe default).

---

## 10. Existing repositories

Established repositories are a first-class case, not an afterthought.

**Detection, before any plan:**

| What | How | Effect |
|---|---|---|
| Project type | `pyproject.toml`, `setup.py`, `requirements*.txt`, `uv.lock`, `poetry.lock` | Python support level; other languages reported as unsupported in v0.1 |
| Python versions | `requires-python` (or classifiers) | CI matrix built from it; never changed |
| Linters and formatters | ruff, black, isort, flake8, pylint settings and pre-commit hooks | kept, or a gradual move to ruff, as the person chooses (§6.3) |
| Existing CI | `.github/workflows/*.yml`, other CI files | never edited; `swerepo-ci.yml` added beside; overlaps reported ("you already run pytest in `tests.yml`") |
| Existing docs | ADR-like folders (`docs/adr`, `doc/adr`, `docs/decisions`, `adr/`), CHANGELOG, CONTRIBUTING, SECURITY, a spec (`SPEC.md`, `docs/SPEC.md`, `<PROJECT>-SPEC.md`), a progress or status file | adopted and recorded under `[adopted]`; missing pieces only |
| Agent files | CLAUDE.md, AGENTS.md, GEMINI.md, `.cursor/rules`, `.github/copilot-instructions.md` | marked block or import added; existing text kept; conflicts reported (an existing `copilot-instructions.md` gets a marked block, not a new file) |
| Branch rules and merge settings | existing rulesets, classic branch protection, merge settings (through `gh`) | added to, never replaced; differences shown; changing merge settings is asked separately |
| Monorepo | several project roots (§11) | reported; repository-level parts set up once at the root; listed Python projects get their own jobs and settings; uncovered projects named |
| SeamSpec | `.seamspec/` | not re-initialised; checked and updated instead |

**PR rules start as warnings.** In an existing repository, the pull-request rules (§6.5: progress entry, ADR for new dependencies and workflow changes) start in warn-only mode (`[pr] enforce = false`): the `governance` job reports them as warnings on the PR without failing, so teammates' PRs don't start failing the day the CI PR merges. The team switches them on in a later PR, by setting `enforce = true` or running `swerepo update --enforce-pr-rules`. The switch is always a commit, never a date that passes: CI never starts failing on its own. `check` shows how long the rules have been warn-only (`warn_since`). New projects start with `enforce = true`.

**Not a git repository:** in an empty folder or a project without git, `init` offers `git init` (a yes, or `--yes`). In a folder that holds other repositories, it stops (SeamSpec 0.1.1's lesson).

**Recommended path for a team (printed by `check`):**

1. `swerepo check` — the report, shared with the team.
2. `swerepo init --only docs,agents` — one PR. Low risk, immediate value for agents.
3. `swerepo init --only ci,security` — one PR. New checks run beside the old ones; nothing old is removed.
4. `swerepo init --only seamspec` — one PR, plus the team reviewing the proposed rules in `seamspec review`.
5. `swerepo init --only github` — the ruleset and merge settings, once the new CI is trusted.

**What it never does in an existing repository:** edit an existing workflow, rewrite the README, rename folders, change Python versions the project already declares, remove anything, or rewrite git history.

**Large repositories:** the privacy scan and `check` read only tracked files and skip vendored and generated folders (configurable). SeamSpec rules should be few and fast at first (the rule pack plus a handful of critical rules), because locked tests run at every agent stop and every commit.

---

## 11. Monorepos

A **monorepo** holds several projects in one repository, for example `services/orders/`, `services/payments/` and `web/`, each with its own dependencies and tests.

- **Detection:** more than one project root below the repository root: folders with a project manifest, Python's (`pyproject.toml`, `setup.py`, `Pipfile`, or `setup.cfg` / `requirements*.txt` with Python source in the folder) or another language's (`package.json`, `go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle`, `Gemfile`). Folders under `tests/`, `test/`, `testing/`, `fixtures/`, `examples/`, `example/`, `docs/`, `doc/`, `tools/`, `scripts/`, `vendor/` and `third_party/` are not projects, nor are folders listed in `[projects] ignore`; files are listed through git, so ignored folders never count (ADR-20261120-25b5).
- **v0.1:**
  - reports the layout;
  - sets up the repository-level parts (docs, agents, security, GitHub, the CI aggregator) once, at the root. One ADR folder, one progress folder and one root `SPEC.md` serve every project; one progress file per PR keeps many teams from colliding;
  - adds a lint and test job per Python project only when `--projects` lists them (a folder with a `pyproject.toml`, also under a folder detection skips, such as `tools/`), each running in its own folder; the list is recorded under `[projects] listed`;
  - **settings per project:** ruff and pytest settings (§6.3) go into each listed project's own `pyproject.toml`, with that project's own linter detection and choice. Exception: when the root `pyproject.toml` already holds `[tool.ruff]` (for example a uv workspace root), the ruff settings go there once and projects inherit them, as ruff looks for the nearest configuration;
  - **projects outside `ci-ok`:** every project root not covered by a SWERepo job (unsupported languages such as TypeScript in v0.1, or Python projects not listed) is named in the plan. Its own existing CI keeps running, but the ruleset requires only `ci-ok`, so a failure there wouldn't block a merge. `init` lists the job names of the workflows that cover that folder and asks whether to require them too (recorded under `[github] extra_required_checks`, added to the ruleset beside `ci-ok`). The person can instead record the project as knowingly uncovered (`[projects] not_covered`). Until one of the two, `check` reports `✗ web/ not covered by any required check`;
  - for SeamSpec, explains its current limit (one test setup per repository; per-folder runners are on SeamSpec's roadmap) and sets it up for one project root the person chooses.
- **v0.2, Phase 10** (§20, ADR-20261124-2452): `swerepo adr new --scope <path>`, opt-in two-tier ADRs (the root `docs/adr/` for decisions across services, `services/<name>/docs/adr/` for each service's own), and full monorepo support, following SeamSpec's per-runner folders.
- **Two-tier specs, also v0.2, Phase 10** (ADR-20261124-4d76): a multi-service monorepo keeps a root `SPEC.md` for what spans services (system-wide behaviour, contracts between services) and `<service>/SPEC.md` in each listed service folder, beside that service's `docs/adr/`, so each team edits its own spec without merge conflicts. Inside a service, `<service>/SPEC.md` is the spec for that service's behaviour; the root `SPEC.md` covers what crosses services. The root file comes from a second template (`docs/spec-system@1`, listing the services and the contracts between them), each service's from `docs/spec@1`; a service that keeps its spec elsewhere is adopted under `[projects.adopted."<service>"] spec`. A single-service repository keeps one root `SPEC.md`.

---

## 12. GitHub integration

- **Through `gh`**, the GitHub CLI, using the person's own login. SWERepo stores no token.
- **No GitHub repository yet** (a new project): `init` writes the `github` files, marks the ruleset and merge settings as waiting in the plan ("waiting: no GitHub repository"), records `[github] applied = false`, and ends by printing the next steps for the person:
  1. commit the files to the default branch (the only commit that goes straight to it, since no rules exist yet);
  2. create the repository and push (`gh repo create --source . --push`); SWERepo never creates repositories or pushes;
  3. run `swerepo update --only github` to apply the ruleset and merge settings.
  Until then, `check` reports `✗ ruleset not applied (no GitHub repository yet)`.
- **On GitHub, but without `gh`** (not installed or not logged in): the plan says the settings wait for `gh`, and the next steps are the usual branch and pull request, then `gh auth login` and `swerepo init --only github`.
- **Settings as code.** The ruleset and merge settings live in `.github/swerepo/ruleset.json` and `repo-settings.json`. They are the source of truth: a person may edit them (SWERepo then treats them like any edited file), `init`/`update --only github` applies them, and `check` compares the live settings with them. Two edits are never applied, and `check` reports them: a ruleset renamed away from `swerepo`, and fields in `repo-settings.json` beyond the merge settings (such as `private`).
- **The ruleset** is named `swerepo`, so reruns find and update their own ruleset and never touch others. It targets the default branch. Long-lived environment branches (`develop`, `release`) protected the same way, with `deletion` and both squash and merge commits allowed, are planned for v0.2, Phase 9 (§20, ADR-20261124-2452).

| Rule | `solo` | `team` |
|---|---|---|
| Changes only through pull requests | ✓ | ✓ |
| Required status check `ci-ok` | ✓ | ✓ |
| No force pushes, no branch deletion | ✓ | ✓ |
| Copilot code review requested automatically (where available) | ✓ | ✓ |
| Review threads resolved before merge | ✓ (when Copilot review is on) | ✓ |
| Approving reviews required | 0 | 1 |
| Stale approvals dismissed on push | — | ✓ |
| Code-owner review (governance paths, §6.1) | — | ✓ (only once CODEOWNERS names a real owner) |
| Branch up to date before merge | — | — (option; costly with many PRs) |

- **Why two modes:** GitHub doesn't let a person approve their own pull request, so a required approval would stop a solo developer from ever merging. A Copilot review doesn't count as an approval.
- **`team` mode for one person:** when agents work under their own GitHub identity (§17), the person is not the author, can approve, and `team` mode gives a real lock.
- **Copilot review:** detected through the API where possible; when the account has no Copilot review, the ruleset is created without it (and without required thread resolution in `solo`), and `check` says so.
- **Always shown first:** the exact ruleset and settings as JSON, and a confirmation. `--yes` applies them in scripts; without a terminal and without `--yes`, they are skipped with the command to run.
- **Plan limits are explained, not hidden:** on a private repository on GitHub's Free plan, rulesets and required checks aren't enforced; `check` says "set up, but not enforced on this plan".
- **Bypass list:** empty by default (an admin bypass would show "merge anyway" to the admin).
- **`swerepo threads <pr>`** reads open review threads through `gh api graphql` and prints each with its file, line and last comment, so agents and people can answer every thread. It never replies or resolves.
- **How the settings are applied** (ADR-20261123-4e40): the JSON is built in Python (`github/ruleset@1`, `github/repo-settings@1`, versioned like templates), and what is applied is the committed file once it exists, a person's edits included. The ruleset named `swerepo` is updated in place when it exists, so a hand-made one is adopted, and created when it doesn't; other rulesets are never touched. `check` compares the live ruleset and merge settings with the committed files through `gh`, with GET requests only and never with `--ci`, and reports secret scanning, push protection and the dependency graph the same way.

---

## 13. SeamSpec integration

SWERepo uses SeamSpec only through its public command line; SeamSpec needs no changes.

- **Requires** the `seamspec` command. If missing, the plan prints how to install it (`uv tool install seamspec==<pin>`); SWERepo never installs or upgrades it, a change to the person's whole machine (ADR-20261124-cd64).
- **`init --only seamspec`** runs `seamspec init --mode enforced --no-ci --hosts <editors>` (its locked rules run in `swerepo-ci.yml`, §6.2; without the `ci` component it keeps SeamSpec's own workflow, `--ci`, and says nothing else runs them), passing the non-Claude editors chosen in the `agents` component (§6.6: `cursor`, `vscode`, `antigravity`), so SeamSpec sets up the same editors SWERepo does. Without `--hosts`, SeamSpec detects editors by their folders, which don't exist yet in a new project, and would treat a `GEMINI.md` as Antigravity. It runs in the person's terminal, so SeamSpec's own consent screen ("Allow automatic test runs?") is answered by the person: SWERepo never passes `--accept-auto-run`, and `--yes` never answers it. Without a terminal, or with `--yes`, it isn't run: the plan shows the command and the component waits until `.seamspec/config.toml` exists. `--mode enforced` is passed on a first setup only; an existing mode, `strict` included, is never lowered. A repository where SeamSpec is already set up is adopted without rerunning it (ADR-20261124-cd64).
- **Strict mode** always adds SeamSpec's own workflow and a CODEOWNERS block. SWERepo writes the workflow first from its own pinned template, which SeamSpec keeps; an unpinned one SeamSpec already wrote is reported, never replaced. SeamSpec's CODEOWNERS block is reported when it comes after SWERepo's governance block or still names `@your-team/leads` (a failure in `team` mode, where it would block merges). With `ci`, the locked rules run in both workflows (ADR-20261124-cd64).
- **`CLAUDE.md` and `AGENTS.md`:** SeamSpec keeps writing its own blocks; SWERepo's block and the `@AGENTS.md` import sit beside them, outside SeamSpec's markers.
- **The earned spec** (§6.8) is written **after** the first review, so it isn't empty and immediately stale:
  1. `init --only seamspec` runs `seamspec init`, then proposes the hygiene rules;
  2. it offers to run `seamspec review` in the person's terminal now (the person approves or rejects each rule; SWERepo never answers for them);
  3. after the review, it writes `docs/EARNED_SPEC.md` with `seamspec spec --out`. If the person postpones the review, it writes the file with the rules approved so far (none yet) and says to run `swerepo update --only seamspec` after reviewing, which regenerates it.
  CI runs `seamspec spec --check` at the pinned SeamSpec version: the `seamspec` job in `swerepo-ci.yml` (§6.2), or SWERepo's `seamspec.yml` without the `ci` component (§6.8). Whenever `seamspec review` later approves or supersedes rules, the same PR regenerates the file; CI fails if it doesn't.
- **The hygiene rule pack** (§6.8) is proposed with `seamspec propose --json -`, each rule with its test bundled in SWERepo (`hygiene/<name>@<version>`, recorded as the rule's origin reference), using only the standard library and pytest, linted, and checked to pass on the repository before proposing. A hygiene rule already covered by a locked rule of the repository's own is adopted instead: asked once per rule in a terminal, or given with `--adopt NAME=ID`, and recorded under `[seamspec.adopted]`. SWERepo never approves: the person runs `seamspec review`, ideally after the agent's `/seamspec:explain`.
- **`swerepo -u --seamspec`** brings a repository to the installed SeamSpec version:
  1. reports the installed SeamSpec version against the CI pin (no PyPI lookup: SWERepo makes no network call except through `gh`);
  2. tells the person to upgrade the tool itself (`uv tool upgrade seamspec`), a machine-wide change SWERepo doesn't make on its own;
  3. reruns `seamspec init` in the person's terminal (which moves the Claude Code plugin to the new version and refreshes SeamSpec's blocks and host files);
  4. moves the version pin to the installed version, never backwards: `[tools] seamspec`, the `seamspec==x.y.z` pin in `swerepo-ci.yml` (and in SWERepo's `seamspec.yml`, if any) and their records, together. `ci` is brought along for the pin only: its recorded workflow is rebuilt from its recorded template and inputs with only the pin changed, and nothing else of `ci` is touched. When a recorded workflow can't take the pin (a conflict, an earlier render that can't be rebuilt, or `--no-ci` leaving it out), the pin doesn't move either;
  5. runs `seamspec doctor` and reports the result.
- **`check`** reports: SeamSpec set up, mode, CI pin versus installed version, plugin current (from `seamspec doctor`), hygiene rules locked, adopted, proposed or missing, proposals waiting for review, the earned spec current, and strict mode's workflow and CODEOWNERS block. It runs only `seamspec --version`, `doctor --json` (naming the checks that warn, never SeamSpec's messages) and `spec --check`, which write nothing, and with `--ci` runs no SeamSpec command at all.

---

## 14. Specs: SPEC.md

- **One Markdown file and one rule** (ADR-20261124-4d76): the spec says what the project does, the ADRs say why it was decided that way, the progress entries say what each change did, and `docs/EARNED_SPEC.md` says what SeamSpec enforces today (§6.5, §6.8).
- **Written once, then the person's:** `docs` writes `SPEC.md` from the template `docs/spec@1` only when no spec exists, and never records or updates it (§9).
- **Finding the spec** (`init` and `update` alike; ADR-20261124-4d76, review P8-D04):
  1. `[adopted] spec`, when set, is the spec; nothing is looked for.
  2. Otherwise the candidates are the root `SPEC.md`, `docs/SPEC.md` and any root `*-SPEC.md`, whatever their case; `docs/EARNED_SPEC.md` never counts.
  3. None: the starter `SPEC.md` is written, and nothing is recorded.
  4. One: a root `SPEC.md` is kept as the default, with nothing recorded; any other is recorded as `[adopted] spec`.
  5. Several: none is guessed. The plan lists them and how to record one, no `SPEC.md` is written, and `check` reports `✗ docs.spec` until the person chooses.

  The path reaches the templates that name the spec, so recording it later brings them in line through `update`.
- **Kept current by the people and agents who change behaviour:** the agents block's rule 10, `prepare-pr.md`, the `update-spec.md` runbook and the PR template's checklist (§6.6, §6.1). A change to the spec alone needs no ADR.
- **What `check` looks for:** that the spec file exists (`docs.spec`). There is no pull-request rule comparing code changes with spec changes, by the owner's choice: refactors and bug fixes would trigger it constantly.
- **Not a governance path:** the spec isn't in SWERepo's CODEOWNERS block (§6.1).
- **OpenSpec** isn't part of standard 1. It was planned as an optional component, and its public documentation showed Node.js 22, skills installed in the person's home folder by default, old marker blocks removed from `CLAUDE.md` and `AGENTS.md` without asking, and usage statistics on by default. SeamSpec's OpenSpec importer stays planned for v0.2, Phase 12, for teams that use OpenSpec on their own (§20).

---

## 15. `swerepo check`

Read-only. Never changes a file, never calls GitHub without `gh` already logged in, never installs anything.

```
$ swerepo check
SWERepo · check · /Users/me/code/legacy-api (standard 1, mode: team)
  docs      ✓ ADRs (adopted: doc/decisions, 41 files, index matches)
            ✓ spec (adopted: LEGACY-API-SPEC.md)
            ✗ docs/PROGRESS.md missing
            ✓ CHANGELOG.md has [Unreleased]
  agents    ✗ AGENTS.md missing · ✓ CLAUDE.md (no import of AGENTS.md)
  ci        ✗ swerepo-ci.yml missing (you run pytest in tests.yml: kept)
  security  ✗ 2 personal email addresses in tracked files (README.md:12, setup.cfg:4)
  github    ✓ PR template · ✗ ruleset "swerepo" missing · ? Copilot review (no access to read it)
  seamspec  ✗ not set up
6 missing, 0 changed by you, 0 outdated. Next: swerepo init --only docs,agents
```

- **Statuses:** `✓` meets the standard · `✗` missing · `~` changed by you (kept) · `↑` outdated (an update is available) · `?` can't tell (says why) · `–` not chosen.
- **`--json`** gives the same findings for scripts and dashboards.
- **`--ci`** for a workflow: exits 1 on `✗` in chosen components; reports `↑` and `~` without failing. Never needs GitHub access (GitHub checks are skipped with `?`).
- **Pinned in CI.** `swerepo-ci.yml` runs a pinned SWERepo version (`uvx swerepo==x.y.z`), moved only by `swerepo update`. A new SWERepo release or standard never turns a repository's CI red by itself.
- **Before SWERepo is published** (as SeamSpec decided in its ADR-20261011-a9f3): a released SWERepo pins itself, as above. An unreleased build (a `.dev` or local version, which PyPI doesn't have) doesn't add the `governance` job, and says why. Asked for explicitly (`--with-governance`), it writes an install from the SWERepo repository (`uvx --from git+https://…@main swerepo`), with a comment and a line in the output saying the CI must be able to read that repository and what to change after the release. SWERepo's own repository runs `uv run swerepo` from its own checkout instead, so it always checks itself with the code under review.
- **`--base REF`** adds the pull-request rules (§6.5), comparing the working tree with `REF` (the merge base with it):
  - a new file in `docs/progress/` (or the adopted progress location), unless a commit since `REF` carries `Progress: none`; the workflow can also pass `--skip progress` when the PR has the label named in `[pr] skip_progress_label`;
  - an ADR added or changed when `[project].dependencies` gains a new package name;
  - an ADR added or changed when a file in `.github/workflows/` changed, except files that match SWERepo's recorded render;
  - the ADR index matches the ADR files.
  With `[pr] enforce = false` (existing repositories at first, §10), these findings are warnings: printed, shown as annotations on the PR, but not failing `--ci`.
  Skipped for pull requests by bots listed under `[pr] exempt_authors` (default `dependabot[bot]`, passed in by the workflow) while every commit on the branch is the bot's own, and for diffs that touch only lockfiles.
- **What this version checks** is listed in `swerepo/standard.py`. A check that only a later version adds would show as `?` naming that version, never silently skipped; standard 1 has none left (ADR-20261124-152d). The header names the folder, not its absolute path, and the commit-email check counts addresses without printing them (ADR-20261120-fc5a). `--base` runs at the repository's top level; its mechanics (merge base vs working tree, PEP 503 dependency names, `--author` for the bot exemption) are in ADR-20261120-5e21. `--json` prints one JSON value and nothing else, also with `--ci`.
- **No score.** A number invites gaming and hides what matters; the list says what to do next.

---

## 16. Updating

- **`swerepo update`** (`-u`) re-renders every applied component with the current templates and standard, and, for each file, block or section:
  - unchanged since SWERepo wrote it → replaced with the new render;
  - changed by a person → **three-way merge** with `git merge-file`: the base is the earlier render (rebuilt from the recorded template version and `[values]`, checked against `rendered`), "ours" is the person's file, "theirs" is the new render. A clean merge is shown as a diff in the plan and applied on the person's yes in a terminal; without one, only with `--yes --merge`, so `--yes` alone never merges into a person's edits. A workflow that differs only by newer action pins (Dependabot's) is updated with `--yes` alone (ADR-20261124-7afa). A conflict leaves the file as it is, is reported as `~ conflict`, and `swerepo diff` shows the change to apply by hand. SWERepo never writes conflict markers into a file;
  - new item in the standard → added (shown in the plan);
  - item removed from the standard → reported, never deleted automatically.
- **Per component:** `swerepo -u --seamspec`, `-u --ci`, `-u --agents`, …
- **Each record keeps the inputs its render used** (`inputs` in `.swerepo.toml`), so a partial run or a conflict never stops another file's earlier render from being rebuilt. `update` renders with the project as it is now: its commands, the Python versions `requires-python` allows, and SWERepo's own released CI pin (`init` keeps the recorded ones and notes the change); the default branch stays recorded. A merge or rewrite that would leave a JSON or TOML file unparseable is reported, never written. An earlier render whose fingerprint doesn't match the record is never merged against: the file is reported as "can't merge" and left alone.
- **The standard's changelog** ships with the package, so `update` can say why something changed ("standard 2: CI adds Python 3.15").
- **Version pins** of other tools (SeamSpec's CI pin, SWERepo's own pin in CI) are updated only through `update`, always shown first. **Action pins** (`uses: owner/action@<commit>  # v<version>`) are also moved forward by Dependabot. `update` keeps the newer of the repository's and the template's and never moves one backwards: one version pinned to two commits, or any other change on a pin line, is a conflict. `check` counts pins that are only newer as current (ADR-20261123-f571).

---

## 17. Safety, privacy and trust

- **No language model, no telemetry, no account.** SWERepo reads files, writes files and runs the commands listed in its plan.
- **Network:** only `gh` calls for GitHub (with the person's yes), the optional PyPI version lookup, and installing a missing tool (asked first).
- **Never** commits, pushes, merges, publishes, approves a deployment, approves a SeamSpec rule, resolves a review thread, or answers another tool's consent.
- **Personal data:** the privacy component exists because personal details leak into repositories; SWERepo itself writes no personal data (the code owner and security contact are asked for; commits are the person's own).
- **Refuses the wrong folder:** in a folder that holds other repositories, it stops; outside a git repository, it offers `git init` (§10).
- **Templates are data, not code:** rendering fills in values; it never executes anything from a template.

### What the rules can and can't stop

The rules make breaking the process **visible**; they make it **impossible** only where a different identity has to act.

- **An agent using the person's own GitHub login** (the usual set-up for Claude Code, Cursor and others on a laptop) can do anything the person can: reply to and resolve review threads, and merge once `ci-ok` passes and the required approvals are met (none in `solo` mode). The process still leaves a trail (the PR, the threads, the progress entries, SeamSpec's lock files), and `ci-ok` still has to pass, but nothing stops a merge.
- **Hard locks** are the rules that need someone else: a required approval (`team` mode), code-owner review on governance files, and SeamSpec's locked tests in CI (an agent can't change one without the change showing in the diff and failing verification).
- **For a hard lock as one person:** run agents under their own GitHub identity (a machine account, or a GitHub App) and use `team` mode with yourself as the code owner and approver. CONTRIBUTING explains this, and `check` reports the mode in place.
- **Editor hooks that block commands** (for example denying `git push` to `main`) are only speed bumps: there are many ways to write the same command. They are not part of standard 1 (§20); the server-side ruleset is the guard.

---

## 18. How it is built

- **Python ≥ 3.11, uv, a single package** (`swerepo`), command `swerepo`; dependencies kept small: a command-line library, a format-preserving TOML library, and the standard library. Three-way merges use `git merge-file` (git is already required).
- **Templates** under `swerepo/templates/<component>/`, versioned (`ci/python@1`); every released version kept.
- **Modules:** `detect` (§10), `plan` (what to change), `render` (templates and normalised hashes), `merge` (three-way), `apply` (writes, with fingerprints), `state` (`.swerepo.toml`), `check` (§15), `github` (`gh` calls, threads), `docs` (ADR index, progress), `tools` (the SeamSpec bridge), `cli`.
- **Tests:** pytest with fixture repositories (empty folder without git, fresh `uv init` project with no GitHub remote, an established project with its own CI, black and flake8, ADRs in `doc/decisions`, a CLAUDE.md and an existing CODEOWNERS, a monorepo with a TypeScript folder and a uv workspace root, two branches that each add an ADR and a progress entry), a fake `gh` and a fake `seamspec` on `PATH`, plus one test against the real SeamSpec. Merge tests cover clean merges, conflicts and line-ending changes.
- **Its own repository** is set up by SWERepo (dogfooding), uses SeamSpec on its own rules, and follows the process it installs: branches and PRs, Copilot review, ADRs, progress entries, a release workflow with a human approval (its own, never part of the standard: ADR-20261124-4699). It doubles as the public example of the standard.
- **Published on PyPI** only with the owner's explicit go-ahead for each release (as for SeamSpec).

---

## 19. Open questions

1. **Name.** *Decided:* **SWERepo**, package and command `swerepo` (ADR-20261120-1a27), renamed from the working name Golden Repo before anything was published: "golden repo" is a generic, crowded term, and the GitHub organisation name `goldenrepo` was taken. Reserved on PyPI with a 0.0.1 placeholder the owner publishes (ADR-20261119-d68b). (Earlier reasoning, still true: not `golden`, because "golden files" and "golden tests" already mean snapshot testing in Python.)
2. **Where it lives.** *Decided:* its own organisation, public: `github.com/swerepo/swerepo` (ADR-20261119-13fc, names from ADR-20261120-1a27).
3. **License.** *Decided:* Apache-2.0, like SeamSpec (ADR-20261119-7384).
4. **Type checker.** None by default, mypy, pyright or ty. Proposal: none in standard 1, offered as an option. *Planned:* opt-in `--typecheck ty|pyright|mypy` in v0.2, Phase 11 (ADR-20261124-2452).
5. **Secret scanning.** *Decided* (ADR-20261123-24e0): GitHub's secret scanning and push protection, plus SWERepo's privacy scan in CI and in a local pre-push hook. gitleaks stays an option for later, for git history and its longer list of formats (it's a separate binary).
6. **OpenSpec.** *Dropped from v0.1* (ADR-20261124-4d76): a native `SPEC.md` instead (§14). Its public documentation showed Node.js 22, skills in the person's home folder by default and usage statistics on by default.
7. **Copilot review in rulesets.** *Decided:* rule `copilot_code_review` (parameters `review_on_push`, `review_draft_pull_requests`); it requests a review when the pull request author has Copilot code review access, so the account check is GitHub's. This repository uses it on every pull request with resolved threads required (ADR-20261120-2e50).
8. **Should SWERepo create the branch and PR for each step** (`--pr`, through `gh`), or leave git to the person? Proposal: leave it to the person in v0.1. *Planned:* `--pr` per component in v0.2, Phase 11 (ADR-20261124-2452).
9. **Agent instructions length.** The target is under 40 lines; measure with real sessions how much is followed. In the same sessions, check whether Claude Code reading both SeamSpec blocks through `@AGENTS.md` (mixed-editor projects, §6.6) causes confusion; if it does, switch to rendering SWERepo's block into both files.
10. **Changelog fragments.** `CHANGELOG.md [Unreleased]` is edited by many PRs and conflicts like the old progress log did. Proposal: keep Keep a Changelog in standard 1; offer fragments (`changelog.d/`, compiled at release) as an option later. *Planned:* v0.2, Phase 11 (ADR-20261124-2452).
11. **Default mode for user-owned repositories with agent identities.** If SWERepo can tell that recent PRs come from a machine account, should it propose `team` mode?

---

## 20. Roadmap

**v0.1 — Python, one repository**
Built in this order: `check` (with `--base`); then `init`, `update`/`-u` with three-way merge, `diff`, `status`, `progress`, `adr`, `threads`; components `docs`, `agents`, `ci`, `security`, `github` (both modes); then `seamspec`; then the native `SPEC.md` in `docs` and `agents` (ADR-20261124-4d76). Six components in all: no `openspec` and no `release` (ADR-20261124-152d). Existing-repository detection and adoption; `.swerepo.toml`; tests on fixture repositories; dogfooded on its own repository and on one established repository of the owner's.

**v0.2**, in four phases after v0.1, each closed by a peer review (ADR-20261124-2452):
- **Phase 9, enterprise multi-branch governance:** long-lived environment branches (`develop` for staging, `release` for production) chosen with `--protected-branches`; protected in `ruleset.json` like the default branch, `deletion` included, so `delete_branch_on_merge` never deletes `develop`; `["squash", "merge"]` allowed in `ruleset.json` and `repo-settings.json` for clean `develop → release` merges; `swerepo-ci.yml`'s `push.branches` and the agent instructions kept in step (§12).
- **Phase 10, multi-service monorepos and federated ADRs:** `swerepo adr new --scope <path>`; opt-in two-tier ADRs when `--projects` lists several roots (the root `docs/adr/` for decisions across services, `services/<name>/docs/adr/` for each service's own, so teams don't collide on one index and CODEOWNERS works per service); full monorepo support (§11); two-tier specs, a root `SPEC.md` for what spans services and `<service>/SPEC.md` for each listed service (§11, ADR-20261124-4d76).
- **Phase 11, broader Python and ergonomics for agents:** Poetry and `requirements.txt` projects in CI; an opt-in type checker (`--typecheck ty|pyright|mypy`, §19.4); `swerepo progress new`; changelog fragments (§19.10); `--pr` per component (§19.8); editor command wrappers around the `docs/agents/` runbooks.
- **Phase 12, TypeScript and polyglot monorepos:** npm and pnpm, vitest and jest, biome, eslint and prettier, matching SeamSpec's presets; SeamSpec's OpenSpec importer once it ships.

**Later**
`swerepo check` across many repositories (an organisation report); more languages; GitLab and other forges; organisation-specific standards (a company's own additions on top of the standard). Optional components, each only if dogfooding shows it earns its cost: more local git hooks (pre-commit or prek: blocking commits on `main`; gitleaks; the privacy check already runs before a push, §6.4), editor hooks that block risky commands, architecture layer contracts (import-linter), coverage on changed lines, Conventional Commits.

---

## 21. Risks

| Risk | Mitigation |
|---|---|
| Many project templates and repository tools already exist (Copier, cookiecutter, OpenSSF Scorecard, safe-settings) | SWERepo's difference: agent-first (instructions, ADR and progress discipline, locked rules, review), works on existing repositories, checks and updates a single repository locally instead of generating once or scoring |
| The standard goes stale | Versioned standard with its own changelog; dogfooded on its own and the owner's repositories; `update` with merging makes improvements cheap to adopt |
| Teams resist a big change | `check` first, then one small PR per component; nothing removed or edited |
| Breaking someone's repository | Plans shown first, `--dry-run`, never overwriting edited files (clean merges only, shown first), never editing existing CI, fixtures for established repositories |
| Parallel branches conflicting on shared files | One progress file per PR; generated ADR index; random ADR suffixes |
| Files reported as edited when they weren't | Normalised hashes; generated files written to pass common formatters |
| A SWERepo release turning CI red | SWERepo pinned in CI; `↑` reported, not failed |
| A solo developer locked out of merging | `solo` mode by default on user-owned repositories |
| People believing the rules stop an agent that uses their login | §17 says plainly what is and isn't a lock; `check` reports the mode |
| Copilot review threads blocking merges with noise | `copilot-instructions.md` tuned to skip style; thread resolution required only where Copilot review is on |
| Dependence on other tools (gh, SeamSpec) changing | Use only their documented commands; test against fakes and one real version; report clearly when a tool is missing or too old (SeamSpec 0.1.1's `--json` lesson) |
| An existing codebase failing a new linter on day one | Existing linters kept by default; a move to ruff checks only the files each PR changes (§6.3) |
| Teammates' PRs failing new PR rules on day one | Warn-only mode in existing repositories, switched on by a commit (§10) |
| A monorepo project silently outside the required checks | Named in the plan; its checks required or knowingly recorded as not covered (§11) |
| Too many tools to install | Python, uv, git and `gh` only; others optional or through `uvx` |
| Two projects to maintain | Small scope for v0.1; shared release process and habits with SeamSpec |
| Over-long agent instructions | One short block in AGENTS.md, measured in real sessions (§19.9) |

---

## Appendix A: Revision history

### 0.15 → 0.16

Decisions for Phase 8 (the owner's, 2026-11-24):

1. **A native `SPEC.md` instead of OpenSpec** (ADR-20261124-4d76): `docs` writes a starter `SPEC.md` or adopts an existing spec (`[adopted] spec`); the agents block, `prepare-pr.md`, a new `update-spec.md` runbook and the PR template carry the rule that a change to behaviour updates it; `check` looks only for the file, with no pull-request rule; it stays out of CODEOWNERS; two-tier specs planned for v0.2, Phase 10 (§1, §6, §6.1, §6.5, §6.6, §6.7, §8, §9, §10, §11, §14, §19.6, §20).
2. **Six components** (ADR-20261124-152d): `openspec` and `release` removed; SWERepo never sets up package publishing (§3, §5, §7, §8, §9, §15, §18, §20, §21, Appendix B).
3. **SWERepo's own releases** (ADR-20261124-4699): `release.yml` in this repository only, publishing the approved, attested build through trusted publishing (§18).
4. **Two rules guard the shipped package** (ADR-20261124-41e9): nothing outside `swerepo/` in the wheel and no publishing in the code; released templates and the renders built in code never change, checked against every `v*` tag.
5. **After Gemini's design review** (`P8-D01` to `P8-D09`): how the spec is found when there are none, one or several candidates (§6.7, §14); Copilot's instructions and CONTRIBUTING mention the spec (§6.1, §6.5); §15's example and its rule for later checks; the release workflow's job graph, checksums, `main`-ancestry check, uncached setup, the locked rules at the tag and a protected `v*` tag (ADR-20261124-4699); each release's snapshot of the renders built in code, required and checked before its tag (ADR-20261124-41e9).

### 0.14 → 0.15

Decisions for Phase 7 and v0.2:

1. **The `seamspec` component** (ADR-20261124-cd64): `seamspec init` only in the person's terminal, never `--accept-auto-run`; SWERepo never installs or upgrades SeamSpec and makes no PyPI lookup; `--mode enforced` on a first setup only, strict never lowered; SeamSpec's own workflow, when needed, written by SWERepo with pinned actions; strict mode's CODEOWNERS block checked; the hygiene rules named, scoped to their components, and adopted when a locked rule already covers one (`--adopt`, `[seamspec.adopted]`); `-u --seamspec` moves the pin forward with `ci` brought along for it (§6.8, §7, §9, §13).
2. **v0.2 as Phases 9 to 12** (ADR-20261124-2452): multi-branch governance, multi-service monorepos and federated ADRs, broader Python and ergonomics for agents, TypeScript; editor wrappers around the runbooks move from Later to v0.2 (§11, §12, §19, §20).

### 0.13 → 0.14

Decisions from building Phase 6 (`update`, merge, `diff`, `status`):

1. **Merging into a person's edits needs a deliberate yes** (the owner's choice; ADR-20261124-7afa): a terminal yes after the diff, or `--yes --merge`; `--yes` alone never merges. Pins-only differences (Dependabot's) update with `--yes` alone (§7, §16).
2. **Action pins** (ADR-20261123-f571): `update` keeps the newer pin and never moves one backwards; one version pinned to two commits is a conflict; `check` counts newer pins alone as current (§16).
3. **Per-record `inputs`** (the owner's watchout; ADR-20261124-7afa point 10): each record keeps the values its render used, so shared `[values]` keys can move on without losing another file's merge base. Older records get them on the next `update` when they rebuild the recorded render, from `[values]` as recorded before the run. `update` renders with the project's current commands and Python versions, and moves SWERepo's own CI pin to a release (§9, §16).
4. **`diff` and `status`** take `--path`; `status` takes `--json`; neither calls GitHub (§7).

### 0.12 → 0.13

1. **Dependency bots and the Copilot wait** (the owner's choice; ADR-20261123-cc8d): pull requests by `dependabot[bot]` pass `copilot-review` at once, and Dependabot waits 7 days before proposing a new version (§6.1, §6.2).

### 0.11 → 0.12

1. **A pre-push privacy hook** (the owner's choice; ADR-20261123-24e0): `swerepo hook install` and `swerepo privacy --pre-push`. The scan runs before a push, so leaks are caught before they reach GitHub; `check` reports a missing hook locally (§6.4, §7). This answers open question 5 (§19).

### 0.10 → 0.11

Decisions from building Phase 5 (`init` for `github`; `threads`):

1. **The github component** (ADR-20261123-4e40): JSON settings built in Python and versioned like templates; a hand-made `swerepo` ruleset adopted; `check` reading GitHub only with `gh` and never with `--ci`; the dependency graph reported (§6.1, §12, §15).
2. **Merges wait for Copilot's review** (the owner's choice; ADR-20261123-a359): a `copilot-review` job inside `ci-ok`, in `ci/workflow@2` (§6.2).
3. **New flags** `--code-owner` and `--no-copilot-review`; `[github] copilot_review` (§7, §9).

### 0.9 → 0.10

Decisions from building Phase 4 (`init` for `ci` and `security`):

1. **SeamSpec's locked rules run inside `swerepo-ci.yml`** (the owner's choice; ADR-20261122-4a06): an always-present `seamspec` job under `ci-ok`, and `seamspec init --no-ci` (§6.2, §6.8, §13).
2. **The workflow** (ADR-20261122-4a06): composed from templates at one version number; `ci-ok` checks each job's result against what was expected; installs with uv; jobs per listed project (§6.2, §11).
3. **ruff and pytest settings as a marked block** at the end of `pyproject.toml`, replacing `[sections]` (§6.3, §9).
4. **The security component** (ADR-20261122-a48e): the contact defaults to GitHub's private vulnerability reporting; the privacy scan also reads untracked files git would add and reports obvious secrets, naming files and lines only (§6.4).

### 0.8 → 0.9

Decisions from building Phase 3 (`init` for `docs` and `agents`; `adr`; `progress`):

1. **How `init` applies** (ADR-20261121-6c3d): a plan first; managed files recorded, starter files not (§9); existing files only gain a marked block at the end; without a terminal, `--yes` or exit 2 (§7); an existing README is never edited and no license is picked (§6.5, §8); shorthand component flags on `init` and `check` (§7).
2. **`adr new`, `adr index`, `progress`** (ADR-20261121-0b7e): SeamSpec's ADR names, the index generated in file-name order with `SUPERSEDED by <id>`, progress read-only.

### 0.7 → 0.8

Decisions from building Phase 2 (`swerepo check`):

1. **The report** (ADR-20261120-fc5a): findings per component, chosen components, `?` for checks a later phase adds, exit codes, plain text and JSON, no absolute paths or email addresses in output (§15).
2. **Pull-request rules** (ADR-20261120-5e21): the diff is the working tree against the merge base; new dependencies by normalised name; `--author` (new flag, §7) for the bot exemption; `[adopted] progress_dir` (§9).
3. **From Phase 2's review:** `--base` runs at the repository's top level; `--json` with `--ci` prints JSON only; workflows SWERepo *added* are exempt like those it modified (as §6.5 already said).

### 0.6 → 0.7

Decisions from building Phase 1:

1. **Fingerprints:** SHA-256 of normalised UTF-8 text; marked blocks found by comment-style markers (ADR-20261120-9495, §9).
2. **Templates:** plain files with `@@name@@` placeholders, versioned by file name (ADR-20261120-b25a, §8).
3. **`.swerepo.toml`:** tomlkit, validated, never overwritten by an older SWERepo (ADR-20261120-ecf7, §9).
4. **Detection:** read-only, git-listed files, conventional non-project folders and `[projects] ignore`, Python versions read with `packaging` (ADR-20261120-25b5, §9, §11).

### 0.5 → 0.6

1. **Renamed from Golden Repo to SWERepo** (ADR-20261120-1a27): package and command `swerepo`; `.swerepo.toml`; `swerepo:begin` markers; `swerepo: allow-privacy`; `swerepo-ci.yml` and `swerepo-privacy.yml`; `.github/swerepo/`; the ruleset `swerepo`; "the SWERepo standard". Spec file renamed to `SWEREPO-SPEC.md`.
2. **Decided:** the license (Apache-2.0, ADR-20261119-7384), the name and hosting (§19.1, §19.2), reserving the PyPI name with a placeholder (ADR-20261119-d68b).

### 0.4 → 0.5

Implementation-time watchouts, checked against SeamSpec's source.

1. **Editors are asked, not assumed.** `init` asks which agents and editors are in use and writes `GEMINI.md` only for Antigravity or Gemini, since SeamSpec reads a `GEMINI.md` as Antigravity. The choice is passed to `seamspec init --hosts`. Mixed-editor projects, where Claude Code reads both SeamSpec blocks through the import, are measured in §19.9, with a fallback (§6.6, §13, §19.9).
2. **Unreleased SWERepo in CI:** no `governance` job unless asked (`--with-governance`, installing from the repository), following SeamSpec's ADR-20261011-a9f3; SWERepo's own repository uses `uv run swerepo` (§6.2, §7, §15).
3. **`.seamspec/` excluded from linting and formatting**: `extend-exclude` in SWERepo's ruff settings, a command-line exclusion for kept linters, and a `check` report when a tool would still touch locked tests (§6.3).
4. **Hygiene rule tests use only the standard library and pytest**, and ship ruff-clean (§6.8).
5. **`prepare-pr.md` says to regenerate `EARNED_SPEC.md`** when a PR approves or supersedes SeamSpec rules (§6.6).
6. **The commit email check also reads `git config user.email`**, so a repository with no commits is caught before its first one (§6.1).

### 0.3 → 0.4

Gaps found by walking through a new project, a mature repository and a monorepo step by step.

1. **No GitHub repository yet:** `init` writes the files, marks the ruleset as waiting, and prints the next steps (commit, `gh repo create --source . --push`, `swerepo update --only github`) (§12).
2. **The earned spec is written after the first `seamspec review`**, which `init` offers to start; postponing it writes the file with no rules and says how to regenerate (§13).
3. **Existing linters** (black, isort, flake8, pylint) are kept by default, or moved to ruff gradually by checking only the files each PR changes; existing ruff and pytest settings are kept (§6.3, §10).
4. **Warn-only PR rules** in existing repositories (`[pr] enforce = false`), switched on by a commit, never by a date (§10, §15, `--enforce-pr-rules`).
5. **CODEOWNERS lines in a marked block at the end of the file**, since the last matching line wins; `check` reports lines added after it (§6.1).
6. **Monorepo details:** ruff and pytest settings per project (or once at a root that already configures ruff), and every project root outside `ci-ok` named, with its own checks required or recorded as not covered (§11, `--projects`).

### 0.2 → 0.3

1. **Opting out of a progress entry** with the commit trailer `Progress: none` (or a label the workflow passes in), so trivial PRs don't fail `check --base` (§6.5, §9, §15).
2. **An ADR for CI workflow changes**, except changes SWERepo made itself and bot updates; no ADR for `openspec/specs/` changes (§6.5, §6.6, §15).
3. **CODEOWNERS** also covers `/openspec/specs/` (when OpenSpec is set up), `/docs/agents/` and `/docs/EARNED_SPEC.md` (§6.1).
4. **`docs/EARNED_SPEC.md`** in v0.1, written by `seamspec spec --out` and checked in CI with `seamspec spec --check`, both of which SeamSpec already has (§6.8, §13).
5. **Dependency review in CI and build provenance on release**, on public repositories; skipped with an explanation on private ones, where both need a paid GitHub plan (§6.2, §6.9).
6. **Agent runbooks in `docs/agents/`** (`prepare-pr`, `address-review`, `record-adr`) as plain Markdown, and the project's **commands** listed in the AGENTS.md block, instead of editor-specific skills or a justfile (§6.6).

### 0.1 → 0.2

1. **Parallel-safe documents.** Progress is one new file per PR in `docs/progress/` plus a rarely edited `PROGRESS.md` (Now, Next); the ADR index is generated (`swerepo adr index`). New commands `progress` and `adr` (§6.5, §7).
2. **Agent instructions in one place.** The rules live in `AGENTS.md`; `CLAUDE.md` imports it. No copies to keep in sync (§6.6).
3. **Solo and team modes** for the ruleset, with code-owner review and one approval in `team` mode (§12).
4. **Settings as code.** Ruleset and merge settings committed in `.github/swerepo/`; squash-only merging and deleting merged branches added (§6.1, §12).
5. **`copilot-instructions.md`** tuned for review, and resolved threads required where Copilot review is on (§6.1).
6. **CODEOWNERS for governance paths**, with an owner asked for instead of a placeholder (§6.1).
7. **Pull-request rules in CI** through `check --base`: a progress entry per PR, an ADR for every new runtime dependency (§6.5, §15).
8. **`check --ci` no longer fails on `↑`**, and SWERepo is pinned in CI (§15).
9. **Three-way merge in v0.1** through `git merge-file`, with every template version kept and render values recorded; `.swerepo.toml` records `rendered` and `written` hashes (§9, §16).
10. **Normalised hashes** so line endings and end-of-file fixers don't look like edits (§9).
11. **Privacy allowances** for noreply and example addresses, `pyproject.toml` authors, the security contact, placeholder paths, and listed files (§6.4).
12. **CI matrix from `requires-python`**, `workflow-audit` (zizmor) and `governance` jobs, `persist-credentials: false` (§6.2).
13. **`git init` offered** in a folder without git, instead of refusing (§10, §17).
14. **A plain statement of what the rules can and can't stop** (§17).
15. **Prior art named** (§2, §21); `check` built first (§3, §20); principles 9 and 10 added (§5); open questions 1, 7, 10 and 11 added or sharpened (§19).

---

## Appendix B: The BLUEPRINT's ideas

`GOLDENREPO-BLUEPRINT.md` proposed a larger design. This spec takes some of it, defers some and leaves some out.

| Idea | Decision | Why |
|---|---|---|
| Ruleset and repo settings as committed JSON, applied through `gh api` | **Taken** (§12) | Reviewable, diffable, and `check` can compare live settings with them |
| Squash-only merging, delete merged branches | **Taken** (§6.1) | Cheap, and keeps history readable |
| Review threads resolved before merge, with a tuned `copilot-instructions.md` | **Taken** (§6.1) | Makes Copilot review count; the tuning keeps noise from blocking merges |
| Approvals and code-owner review | **Taken as `team` mode** (§12) | As a default, a solo developer could never merge |
| CODEOWNERS on governance paths | **Taken** (§6.1) | A real lock in `team` mode |
| Dependency ADR gate | **Taken** (§6.5, §15) | Cheap to check, directly targets a common agent habit |
| PR threads helper | **Taken as `swerepo threads`** (§7, §12) | As a subcommand, no `just` needed |
| PROGRESS and ADR checks on the PR diff | **Taken** (§6.5, §15), with a `Progress: none` trailer to opt out and an ADR for workflow changes | A label alone can't be seen by a local `check`; the trailer can |
| zizmor workflow audit | **Taken** (§6.2) | Runs through `uvx`, nothing to install |
| `dependency-review-action` | **Taken**, public repositories only (§6.2) | Needs a paid plan on private repositories |
| SHA-pinned actions, `persist-credentials: false` | **Taken** (§6.2) | Standard hardening |
| `ci-ok` aggregator | **Already in 0.1**; skipped-by-design jobs allowed | macOS runs on `main` only |
| Same ~100-line preamble in AGENTS.md and CLAUDE.md, with `golden sync` and a parity check | **Replaced** by AGENTS.md + `@AGENTS.md` import (§6.6) | Cursor and VS Code read AGENTS.md directly; Claude Code expands the import. No copies, no sync |
| Copier for rendering and upgrades | **Not taken** | Built around whole generated projects; SWERepo adds pieces beside existing files and merges per file (§16) |
| `golden` as the command | **Not taken** (§19.1) | Clashes with "golden files" testing |
| TypeScript and polyglot stacks | **Deferred** to v0.2 (§20) | Python first |
| PROGRESS.md updated in every PR | **Changed** to one file per PR (§6.5) | A shared file edited by every PR conflicts across parallel branches |
| `docs/EARNED_SPEC.md` from `seamspec spec`, checked in CI | **Taken** (§6.8, §13) | SeamSpec already has `spec --out` and `spec --check`; one file and one CI step |
| justfile entry points | **Not taken**; commands listed in the AGENTS.md block instead (§6.6) | Another tool to install; listing the `uv run` commands solves "agents guess commands" |
| Cross-editor workflow skills (`/record-adr`, `/prepare-pr`, `/address-review`) | **Taken as plain runbooks** in `docs/agents/` (§6.6); editor wrappers deferred | Every agent can read Markdown; no per-editor formats to maintain |
| Local git hooks (pre-commit, commit-msg, pre-push) with prek, gitleaks, Conventional Commits | **Deferred**, optional (§20), except SWERepo's own pre-push privacy hook (§6.4, ADR-20261123-24e0) | Extra binaries, slower commits; CI is the guard |
| Editor hooks denying risky commands (`.agents/`, `.cursor/`, `.claude/`) | **Deferred**, optional (§17, §20) | Speed bumps only, and four host formats to maintain |
| Architecture layer contracts (import-linter) | **Deferred**, optional (§20) | A new project has no layers yet; generic contracts add little |
| Diff-coverage gate (≥ 85%) | **Deferred**, optional (§20) | Agents can meet a coverage number with tests that check nothing |
| `required_linear_history`, strict status checks | **Not taken** / option (§12) | Linear history follows from squash-only; strict checks force constant rebasing |
| SLSA build provenance on release | **Taken for SWERepo's own releases** (ADR-20261124-4699), not part of the standard | SWERepo sets up no publishing (ADR-20261124-152d) |
| `BRAINDUMP.md`, `docs/ARCHITECTURE.md` | **Not taken** in standard 1 | Not needed by the core process; easy to add later |
| Public showcase repository | **Taken** as SWERepo's own dogfooded repository (§18) | One repository, not two |
