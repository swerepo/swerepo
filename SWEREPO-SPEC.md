# SWERepo — Specification

**Status:** draft for the owner's review · **Version:** 0.8 (design) · **Date:** 2026-11-20
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
14. [OpenSpec integration](#14-openspec-integration)
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

One command, `swerepo init`, brings a new or existing Python repository up to an agent-first engineering standard: strong CI, branch rules with code review, decision records (ADRs) and a progress log, instructions for AI agents (`AGENTS.md`, `CLAUDE.md`), specs (OpenSpec, optional), and rules that agents can't quietly break (SeamSpec). `swerepo check` reports what a repository is missing. `swerepo update` (`-u`) brings it up to the latest standard, one part at a time, merging improvements into files people have edited where it can.

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

- **Not a build system, package manager or framework.** It writes configuration and documents and calls other tools' setup commands; it doesn't replace uv, pytest, ruff, OpenSpec or SeamSpec.
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
5. **Everything optional.** Each component (§8) can be skipped (`--no-openspec`) or applied alone (`--only seamspec`).
6. **Repeatable.** Running `init` twice changes nothing the second time. `init` on a repository already at the standard is the same as `update`.
7. **Small, reviewable steps.** On an established repository, the recommended path is one component per pull request (§10).
8. **Honest reporting.** `check` says "missing", "changed by you", "outdated" or "can't tell (needs GitHub access)", never a vague score. The documentation says plainly what the rules can and can't stop (§17).
9. **Built for parallel work.** Several agents on several branches at once is the normal case. Nothing in the standard asks every PR to edit the same lines of the same file (§6.5).
10. **Few tools to install.** Python, uv, git and `gh`. Anything else (SeamSpec, OpenSpec, scanners) belongs to an optional component or runs through `uvx`.
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
├── .swerepo.toml                   # what SWERepo applied (§9)
├── docs/
│   ├── PROGRESS.md                # Now / Next (edited rarely)
│   ├── progress/                  # one entry per PR (§6.5)
│   ├── agents/                    # runbooks agents read on demand (§6.6)
│   ├── EARNED_SPEC.md             # rules SeamSpec enforces today (§6.8)
│   └── adr/                       # README (with generated index), TEMPLATE, ADRs
├── .github/
│   ├── swerepo/                # ruleset.json, repo-settings.json (§12)
│   ├── workflows/                 # swerepo-ci.yml, swerepo-privacy.yml, (release.yml)
│   ├── copilot-instructions.md    # what Copilot review should and shouldn't comment on
│   ├── CODEOWNERS  pull_request_template.md  dependabot.yml  ISSUE_TEMPLATE/
├── .seamspec/                     # written by SeamSpec (§13)
└── openspec/                      # written by OpenSpec, if chosen (§14)
```

### 6.1 Git and GitHub (component `github`)

- **Branch rules as code:** `.github/swerepo/ruleset.json` (the ruleset) and `.github/swerepo/repo-settings.json` (merge settings), committed and reviewed like any other change, applied through `gh` (§12). Two modes:
  - **`solo`**: changes only through pull requests; required status check `ci-ok` (§6.2); no force pushes; no branch deletion; Copilot code review requested on every pull request where the account has it; review threads must be resolved when Copilot review is on.
  - **`team`**: everything in `solo`, plus one approving review, stale approvals dismissed on push, and code-owner review (which, with the CODEOWNERS below, applies to governance files only).
- **Merge settings:** squash merging only; head branches deleted after merge. Auto-merge stays off (SWERepo never merges, and doesn't make merging unattended).
- `.github/copilot-instructions.md`: tells Copilot review to skip style that ruff already checks, and to comment on missing ADRs and progress entries, behaviour changes without tests, changes to locked rules or CI, and security problems. Needed because resolved threads are required: every comment blocks the merge until answered.
- `.github/pull_request_template.md`: what changed, spec and decisions touched, checklist (tests pass locally, progress entry added, ADR if needed, review threads answered).
- `.github/CODEOWNERS` for governance paths only: `/.github/`, `/.swerepo.toml`, `/AGENTS.md`, `/CLAUDE.md`, `/docs/adr/`, `/docs/agents/`, `/.seamspec/`, `/docs/EARNED_SPEC.md`, and `/openspec/specs/` when OpenSpec is set up. The owner is asked for (default: the repository owner from `gh`), never guessed from git config.
  - The lines go in a marked block (`# swerepo:begin` … `# swerepo:end`) **at the end of the file**, in a new CODEOWNERS or an existing one, because in CODEOWNERS the last matching line wins. A team's own lines (per-folder owners) stay above the block.
  - If lines are later added below the block, `check` reports `~ CODEOWNERS: lines after the SWERepo block can override governance owners`, naming any that do.
- `.github/ISSUE_TEMPLATE/` for bugs and features.
- `.github/dependabot.yml`: weekly updates for GitHub Actions and Python dependencies.
- Commits under a noreply address: `check` warns when recent commits use a personal email address (lesson from SessionWalk), and also when the repository's `git config user.email` is one, so a new repository with no commits yet is caught before its first commit. `init` shows the same warning, with the command to set a noreply address for this repository, before it prints the steps that start with a commit (§12).

### 6.2 CI (component `ci`)

- `.github/workflows/swerepo-ci.yml`:
  - **lint**: ruff lint and format check, or the project's existing linters (§6.3);
  - **tests**: pytest through uv on Linux, on every Python version the project supports. The versions come from `requires-python` (for a new project, `>=3.11`, so 3.11 to 3.14), up to the newest version standard 1 knows; SWERepo never changes a declared range;
  - **tests-macos**: on pushes to `main` only (macOS minutes cost about ten times more on private repositories);
  - **workflow-audit**: `zizmor` on `.github/workflows/`, run through `uvx` at a pinned version;
  - **governance**: on pull requests, `swerepo check --ci --base <base branch>` at a pinned SWERepo version (§15; an unreleased SWERepo doesn't add this job unless asked), and, when SeamSpec is set up, `seamspec spec --check docs/EARNED_SPEC.md` at the pinned SeamSpec version (§6.8);
  - **dependency-review**: on pull requests to public repositories, GitHub's `dependency-review-action` (fails on new dependencies with known vulnerabilities). On private repositories it needs a paid GitHub plan, so the job is skipped there by a condition in the workflow and `check` says "not available on this plan";
  - **`ci-ok`**: a single aggregating job (`if: always()`) that passes only when every job passed, or was skipped by design (macOS on pull requests, dependency review on private repositories); failed or cancelled jobs fail it. The ruleset requires only `ci-ok`, so adding a job never means editing GitHub settings.
- Actions pinned to commit SHAs, `permissions: contents: read` by default, `persist-credentials: false` on checkout, `concurrency` to cancel superseded runs, a `timeout-minutes` on every job.
- The type checker is an option (§19).

### 6.3 Code quality (component `ci`)

- `pyproject.toml` sections for ruff (lint rules and format) and pytest, merged into an existing file at table level without touching other sections or formatting.
- **Projects that already lint.** SWERepo looks for existing linters and formatters (ruff, black, isort, flake8, pylint) in `pyproject.toml`, `setup.cfg`, `tox.ini`, `.flake8` and `.pre-commit-config.yaml`:
  - **ruff already configured:** its configuration is kept as it is; the lint job runs it.
  - **other tools found:** the person chooses (shown in the plan; the default is the first):
    1. **keep them**: no ruff settings are added; the lint job runs the detected tools through `uv run`, and they are recorded under `[adopted] linters`;
    2. **move to ruff gradually**: ruff settings are added, matched to the existing line length and target version where they can be read, and on pull requests ruff checks **only the files the PR changes**, so existing code isn't flagged all at once. SWERepo never reformats or edits code to make it pass.
  - **nothing found:** ruff, as for a new project.
- The pytest section is added only when the project has no pytest configuration of its own (`pytest.ini`, `setup.cfg`, `tox.ini`, `pyproject.toml`).
- **Locked SeamSpec tests are never linted or reformatted** (SeamSpec's ADR-20261013-c3f7). SeamSpec records a hash of each approved rule test, and any edit, even whitespace, counts as tampering. A `ruff format .` run by an agent would break every lock, and `seamspec init` doesn't add the exclusion to the repositories it sets up. So:
  - SWERepo's ruff settings include `extend-exclude = [".seamspec"]`;
  - with kept linters (black, flake8, …), the lint job passes the exclusion on the command line, and `check` reports `~` with the one-line change to make when a tool's own settings would still touch `.seamspec/` locally. SWERepo doesn't edit those tools' settings itself;
  - an existing ruff configuration that covers `.seamspec/` gets the same `~` report.
- Optional pre-commit configuration that runs the same checks locally.

### 6.4 Security and privacy (component `security`)

- `SECURITY.md`: how to report a vulnerability (the contact is asked for; a placeholder if none is given).
- A privacy check (`.github/workflows/swerepo-privacy.yml` and the same check locally as `swerepo check --only security`): no personal email addresses, no home-folder paths, no obvious secrets in tracked files. Lesson from SessionWalk, where personal details had to be removed from history.
  - **Allowed by default:** noreply addresses (`users.noreply.github.com`), reserved example domains (`example.com`, `example.org`, …), emails in `[project].authors` and `maintainers` in `pyproject.toml`, the contact in `SECURITY.md`, and placeholder home paths (`/Users/me`, `/home/user`, `C:\Users\you`, `~`).
  - **Allowed by the person:** files or globs listed under `[privacy] allow_paths` in `.swerepo.toml`, and a single line marked with a `swerepo: allow-privacy` comment. Allowances name files, never the addresses themselves, so no personal data goes into `.swerepo.toml`.
- Guidance to turn on GitHub secret scanning and push protection (free on public repositories); `check` reports whether they are on when it can read the setting.
- `.gitignore` entries for local secrets and machine-specific files (`.env`, editor and agent machine configs), in a marked block.

### 6.5 Documents (component `docs`)

Designed so that parallel branches don't collide: each PR adds its own files, and shared indexes are generated.

- `README.md` sections (only added where missing): what it is, install, develop, test, contributing.
- `docs/adr/`: `README.md` (format, naming, and an index between `<!-- swerepo:adr-index:begin -->` markers, **generated** by `swerepo adr index`) and `TEMPLATE.md`. Naming follows SeamSpec's convention: `ADR-YYYYMMDD-xxxx-short-title.md` (the random `xxxx` keeps two branches from picking the same name), statuses `PROPOSED | ACCEPTED | SUPERSEDED | REJECTED`. `swerepo adr new "title"` creates one from the template. When two branches both add an ADR, the index conflict is fixed by rerunning `swerepo adr index`. An existing ADR folder is adopted instead (§10); its index is generated only if the person agrees.
- **Progress:**
  - `docs/PROGRESS.md`: **Now** and **Next**, short, edited only when priorities change.
  - `docs/progress/YYYYMMDD-<slug>.md`: **one new file per deliverable PR** (what was done, branch or PR, ADRs and locked rules touched, what's next). Never edited by later PRs, so parallel branches never conflict.
  - `swerepo progress` prints Now, Next and the latest entries, for people and agents.
- `CHANGELOG.md` in the Keep a Changelog format, with an `[Unreleased]` section (fragments instead: §19).
- `CONTRIBUTING.md`: branches and PRs only, branch naming, the PR template, ADR and progress rules, how reviews are answered, which mode the repository uses and what it means (§17).
- `LICENSE` only when the person chooses one (asked; never assumed).
- **PR rules checked in CI** (`check --base`, §15):
  - every PR adds a progress entry, unless one of its commits carries the trailer `Progress: none` (for typo fixes and other small changes; it works in a local `check` as well as in CI);
  - a PR that adds a runtime dependency (a new name under `[project].dependencies`, not a version change) adds or changes an ADR in the same PR;
  - a PR that changes a CI workflow (`.github/workflows/`) adds or changes an ADR in the same PR, because weakening CI is a change to the process. Changes SWERepo made itself (the file matches the render recorded in `.swerepo.toml`) and changes by bots (Dependabot's action updates) don't count.
  - Changes to `openspec/specs/` don't need an ADR: OpenSpec's proposal is already the record of that decision.

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
  7. Answer every review thread (fix it and reply with the commit, or reply why not) before asking for a merge; `swerepo threads <pr>` lists the open ones.
  8. Never publish a package, approve a deployment or merge without the person's explicit go-ahead.
  9. When a test fails, fix the code; never weaken the test to make it pass (and, with SeamSpec, never edit a locked rule's test: request a supersede).
- **Commands** are listed in the block, so agents never guess them: install (`uv sync`), test (`uv run pytest`), lint (`uv run ruff check` and `uv run ruff format --check`), check (`swerepo check`). They are rendered from what the project uses; an existing Makefile or task runner is listed instead when one is detected.
- **Runbooks on demand:** step-by-step guides in `docs/agents/`, plain Markdown that every agent can read, so the block stays short. One line in the block points to them:
  - `prepare-pr.md`: branch, tests, progress entry, ADR if needed, PR template; if the PR approves or supersedes SeamSpec rules, regenerate `docs/EARNED_SPEC.md` in the same PR (`seamspec spec --out docs/EARNED_SPEC.md`);
  - `address-review.md`: `swerepo threads`, fix or reply to each thread with the commit, summary comment;
  - `record-adr.md`: when an ADR is needed, `swerepo adr new`, index, superseding.
  Editor-specific skills and slash commands that wrap these runbooks are a later option (§20); the runbooks stay the single source.
- Wording is kept short (a target of under 40 lines for the block): agents read it every session, and long instructions cost tokens and attention (§19.9).

### 6.7 Specs (component `openspec`, optional)

- OpenSpec set up through its own command (§14), for teams that write specs before code.

### 6.8 Locked rules (component `seamspec`)

- SeamSpec set up through its own command (§13), in enforced mode with its CI workflow.
- **`docs/EARNED_SPEC.md`**: the rules SeamSpec enforces today, written by `seamspec spec --out docs/EARNED_SPEC.md` and checked in CI with `seamspec spec --check docs/EARNED_SPEC.md`. Reviewers see a change to the enforced rules as a readable diff, next to what `openspec/specs/` says was planned.
- The **hygiene rule pack** proposed as SeamSpec rules, for the person to approve:
  1. No personal email addresses or home-folder paths in tracked files (same allowances as §6.4).
  2. Every ADR file is listed in the ADR index.
  3. `CHANGELOG.md` keeps an `[Unreleased]` section.
  4. The CI workflow still runs the test suite and `ci-ok` still depends on it (so an agent can't quietly weaken CI).
- **The rule tests run in the target repository**, so they use only the Python standard library and pytest: no PyYAML or other packages the project may not have. Rule 4 checks the workflow by matching the text of the job and `needs:` lines SWERepo wrote, not by parsing YAML. The bundled tests pass ruff's check and format before they ship, since a locked test can't be tidied afterwards.

### 6.9 Releases (component `release`, optional, for packages)

- `.github/workflows/release.yml`: on a `v*` tag, checks the tag matches the code and the changelog has a dated entry, runs the tests, builds, and publishes to PyPI through trusted publishing, pausing on a protected environment until a person approves (SeamSpec's release process).
- **Build provenance:** on public repositories, `actions/attest-build-provenance` signs a record of how each built file was made, so users can check a release came from this workflow. On private repositories it needs a paid GitHub plan; the step is skipped there by a condition in the workflow and `check` says so.

---

## 7. Command line

```
swerepo init     [--only C,...] [--no-C ...] [--mode solo|team] [--projects P,...] [--dry-run] [--yes] [--path DIR] [--json]
swerepo check    [--only C,...] [--base REF] [--author LOGIN] [--skip progress] [--json] [--ci] [--path DIR]
swerepo update   [--only C,...] [--enforce-pr-rules] [--dry-run] [--yes] [--path DIR] [--json]
swerepo -u       (short for `update`; `swerepo -u --seamspec` = `update --only seamspec`)
swerepo diff     [FILE ...]          what update would change in files you edited, and any merge conflicts
swerepo status                       components applied, mode, standard version, tool versions
swerepo progress [-n N]              Now, Next and the latest N progress entries
swerepo adr new TITLE                a new ADR from the template, with a fresh name
swerepo adr index                    regenerate the ADR index
swerepo threads PR                   open review threads of a PR, compact (read-only; through `gh`)
swerepo --version
```

- **Components** (`C`): `docs`, `agents`, `ci`, `security`, `github`, `seamspec`, `openspec`, `release`. `--only` selects; `--no-<component>` skips. `--seamspec` alone is shorthand for `--only seamspec` (and so for each component).
- **`--mode`**: `solo` or `team` (§12). Default: `solo` for a repository owned by a user, `team` for one owned by an organisation; always shown in the plan.
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
  docs      create  docs/adr/README.md, docs/adr/TEMPLATE.md, docs/PROGRESS.md, docs/progress/, CHANGELOG.md, CONTRIBUTING.md
  agents    create  AGENTS.md (rules, commands), CLAUDE.md (@AGENTS.md), docs/agents/ (3 runbooks)   [editors: Claude Code, Cursor]
  ci        create  .github/workflows/swerepo-ci.yml (Python 3.11–3.14);  update pyproject.toml ([tool.ruff], [tool.pytest])
  security  create  SECURITY.md, .github/workflows/swerepo-privacy.yml;  update .gitignore
  github    create  .github/swerepo/ruleset.json, repo-settings.json, copilot-instructions.md,
                    PR template, CODEOWNERS (owner: me), issue templates, dependabot.yml
            ask     apply ruleset "swerepo" on main (PRs only, ci-ok required, Copilot review, threads resolved)
            ask     merge settings (squash only, delete merged branches)
  seamspec  run     seamspec init (asks its own questions);  propose 4 hygiene rules
  openspec  skip    (not installed; `swerepo init --only openspec` after installing it)
Apply? [y/N]
```

---

## 8. Components

Each component has the same four parts: what it **writes**, what it **runs**, what it **asks**, and what `check` **looks for**.

| Component | Writes | Runs | Asks | Check looks for |
|---|---|---|---|---|
| `docs` | ADR folder (README with index, template), PROGRESS, `docs/progress/`, CHANGELOG, CONTRIBUTING, README sections | — | a license, if none | each file present; ADR index matches the ADR files; CHANGELOG has `[Unreleased]`; with `--base`: progress entry added, ADR for new dependencies |
| `agents` | AGENTS.md block, CLAUDE.md import, GEMINI.md (each only for the editors chosen), `docs/agents/` runbooks | — | which agents and editors are in use | block and runbooks present and current; CLAUDE.md imports AGENTS.md; listed commands still exist |
| `ci` | `swerepo-ci.yml`; ruff and pytest settings (per project in a monorepo) | — | the type checker (§19); keep existing linters or move to ruff gradually | workflow present, current or merged; `ci-ok` aggregates every job; Python versions match `requires-python`; every project root covered by a required check or recorded as not covered |
| `security` | SECURITY.md, privacy workflow, `.gitignore` block | the privacy scan once, to report findings before committing | the security contact | files present; privacy scan clean; secret scanning on (if readable) |
| `github` | `.github/swerepo/*.json`, copilot-instructions, PR template, CODEOWNERS, issue templates, dependabot | `gh` to apply the ruleset and merge settings | **the mode, the code owner, the ruleset and the merge settings** (always shown first); extra required checks in a monorepo | files present; SWERepo's CODEOWNERS block last; ruleset applied, or waiting for a GitHub repository; live ruleset and settings match the committed files (needs `gh`); plan limits explained |
| `seamspec` | `docs/EARNED_SPEC.md` (through SeamSpec, after the first review; SeamSpec writes its other files) | `seamspec init`; `seamspec propose` for the rule pack; `seamspec review` if the person agrees; `seamspec spec --out` | SeamSpec asks its own consent; SWERepo asks before proposing and before starting the review | SeamSpec set up; CI pin matches the installed SeamSpec; plugin current; hygiene rules locked; earned spec current (`seamspec spec --check`) |
| `openspec` | — (OpenSpec writes its own files) | OpenSpec's init command | before installing it, if missing | OpenSpec set up |
| `release` | `release.yml` | — | the PyPI project name; asks whether this is a package at all | workflow present; protected environment exists (if readable) |

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

[sections."pyproject.toml"."tool.ruff"]
template = "ci/ruff@1"
rendered = "77d0…"
written = "77d0…"

[tools]
seamspec = "0.1.1"                # the version the CI workflow pins
openspec = "absent"

[adopted]
adr_dir = "doc/decisions"         # an existing convention SWERepo follows instead of its own (§10)
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
extra_required_checks = []        # monorepo: other workflows' checks required beside ci-ok (§11)

[projects]                        # monorepos only (§11)
ignore = []                       # folders that are not projects, besides tests/, docs/, tools/ … (§11)
listed = []                       # Python projects with their own SWERepo jobs
not_covered = []                  # project roots knowingly outside every required check
```

- **Hashes are of normalised content** (SHA-256, 64 hex characters, ADR-20261120-9495): UTF-8, no byte-order mark, LF line endings, trailing whitespace removed from each line, exactly one final newline. Line-ending conversion and end-of-file fixers don't make a file look edited. A formatter that changes more than that (reflowing Markdown, reformatting YAML) does, and `check` reports it as `~`; the generated files are written to pass ruff and common formatters unchanged.
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
| Existing docs | ADR-like folders (`docs/adr`, `doc/adr`, `docs/decisions`, `adr/`), CHANGELOG, CONTRIBUTING, SECURITY, a progress or status file | adopted and recorded under `[adopted]`; missing pieces only |
| Agent files | CLAUDE.md, AGENTS.md, GEMINI.md, `.cursor/rules`, `.github/copilot-instructions.md` | marked block or import added; existing text kept; conflicts reported (an existing `copilot-instructions.md` gets a marked block, not a new file) |
| Branch rules and merge settings | existing rulesets, classic branch protection, merge settings (through `gh`) | added to, never replaced; differences shown; changing merge settings is asked separately |
| Monorepo | several project roots (§11) | reported; repository-level parts set up once at the root; listed Python projects get their own jobs and settings; uncovered projects named |
| SeamSpec / OpenSpec | `.seamspec/`, `openspec/` | not re-initialised; checked and updated instead |

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
  - sets up the repository-level parts (docs, agents, security, GitHub, the CI aggregator) once, at the root. One ADR folder and one progress folder serve every project; one progress file per PR keeps many teams from colliding;
  - adds a lint and test job per Python project only when `--projects` lists them, each running in its own folder;
  - **settings per project:** ruff and pytest settings (§6.3) go into each listed project's own `pyproject.toml`, with that project's own linter detection and choice. Exception: when the root `pyproject.toml` already holds `[tool.ruff]` (for example a uv workspace root), the ruff settings go there once and projects inherit them, as ruff looks for the nearest configuration;
  - **projects outside `ci-ok`:** every project root not covered by a SWERepo job (unsupported languages such as TypeScript in v0.1, or Python projects not listed) is named in the plan. Its own existing CI keeps running, but the ruleset requires only `ci-ok`, so a failure there wouldn't block a merge. `init` lists the job names of the workflows that cover that folder and asks whether to require them too (recorded under `[github] extra_required_checks`, added to the ruleset beside `ci-ok`). The person can instead record the project as knowingly uncovered (`[projects] not_covered`). Until one of the two, `check` reports `✗ web/ not covered by any required check`;
  - for SeamSpec, explains its current limit (one test setup per repository; per-folder runners are on SeamSpec's roadmap) and sets it up for one project root the person chooses.
- **Later:** full monorepo support (§20), following SeamSpec's per-runner folders.

---

## 12. GitHub integration

- **Through `gh`**, the GitHub CLI, using the person's own login. SWERepo stores no token.
- **No GitHub repository yet** (a new project): `init` writes the `github` files, marks the ruleset and merge settings as waiting in the plan ("waiting: no GitHub repository"), records `[github] applied = false`, and ends by printing the next steps for the person:
  1. commit the files to the default branch (the only commit that goes straight to it, since no rules exist yet);
  2. create the repository and push (`gh repo create --source . --push`); SWERepo never creates repositories or pushes;
  3. run `swerepo update --only github` to apply the ruleset and merge settings.
  Until then, `check` reports `✗ ruleset not applied (no GitHub repository yet)`.
- **Settings as code.** The ruleset and merge settings live in `.github/swerepo/ruleset.json` and `repo-settings.json`. They are the source of truth: a person may edit them (SWERepo then treats them like any edited file), `init`/`update --only github` applies them, and `check` compares the live settings with them.
- **The ruleset** is named `swerepo`, so reruns find and update their own ruleset and never touch others. It targets the default branch.

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

---

## 13. SeamSpec integration

SWERepo uses SeamSpec only through its public command line; SeamSpec needs no changes.

- **Requires** the `seamspec` command. If missing, SWERepo says how to install it (`uv tool install seamspec`) and asks before installing it itself.
- **`init --only seamspec`** runs `seamspec init --mode enforced --ci --hosts <editors>`, passing the non-Claude editors chosen in the `agents` component (§6.6: `cursor`, `vscode`, `antigravity`), so SeamSpec sets up the same editors SWERepo does. Without `--hosts`, SeamSpec detects editors by their folders, which don't exist yet in a new project, and would treat a `GEMINI.md` as Antigravity. It runs in the person's terminal, so SeamSpec's own consent screen ("Allow automatic test runs?") is answered by the person. `--yes` never answers it.
- **`CLAUDE.md` and `AGENTS.md`:** SeamSpec keeps writing its own blocks; SWERepo's block and the `@AGENTS.md` import sit beside them, outside SeamSpec's markers.
- **The earned spec** (§6.8) is written **after** the first review, so it isn't empty and immediately stale:
  1. `init --only seamspec` runs `seamspec init`, then proposes the hygiene rules;
  2. it offers to run `seamspec review` in the person's terminal now (the person approves or rejects each rule; SWERepo never answers for them);
  3. after the review, it writes `docs/EARNED_SPEC.md` with `seamspec spec --out`. If the person postpones the review, it writes the file with the rules approved so far (none yet) and says to run `swerepo update --only seamspec` after reviewing, which regenerates it.
  The `governance` CI job runs `seamspec spec --check` at the pinned SeamSpec version. Whenever `seamspec review` later approves or supersedes rules, the same PR regenerates the file; CI fails if it doesn't.
- **The hygiene rule pack** (§6.8) is proposed with `seamspec propose --json -`, each rule with its test bundled in SWERepo, linted, and checked to pass on the repository before proposing. SWERepo never approves: the person runs `seamspec review`, ideally after the agent's `/seamspec:explain`.
- **`swerepo -u --seamspec`** brings a repository to the installed SeamSpec version:
  1. reports the installed SeamSpec version, and the latest on PyPI if the person allows the lookup;
  2. tells the person to upgrade the tool itself (`uv tool upgrade seamspec`), a machine-wide change SWERepo doesn't make on its own;
  3. reruns `seamspec init` (which moves the Claude Code plugin to the new version and refreshes SeamSpec's blocks and host files);
  4. updates the version pin in SeamSpec's CI workflow (`seamspec==x.y.z`), which `seamspec init` keeps as it is;
  5. runs `seamspec doctor` and reports the result.
- **`check`** reports: SeamSpec set up, mode, CI pin versus installed version, plugin current (from `seamspec doctor`), hygiene rules locked, proposals waiting for review.

---

## 14. OpenSpec integration

- **Optional**, off unless chosen or already present. OpenSpec is a separate open-source tool for writing specs before code; it runs on Node.js.
- **Install and folder layout are taken from OpenSpec's public documentation only** (clean room: SWERepo never reads or copies OpenSpec's code). Before v0.1, confirm from those docs: the package name and install command, the init command and whether it can run without questions, the folders it creates, and how it treats an existing codebase.
- **SWERepo runs OpenSpec's own init** and records only that it was applied; it doesn't generate OpenSpec files itself.
- **Agent block:** when OpenSpec is set up, the `agents` block adds one line on when to use it (a change that needs a proposal first).
- **Relation to SeamSpec:** OpenSpec specifies before code; SeamSpec locks behaviour after code. A later SeamSpec version imports OpenSpec requirements as proposed rules (SeamSpec's roadmap); SWERepo will offer it once it exists.

---

## 15. `swerepo check`

Read-only. Never changes a file, never calls GitHub without `gh` already logged in, never installs anything.

```
$ swerepo check
SWERepo · check · /Users/me/code/legacy-api (standard 1, mode: team)
  docs      ✓ ADRs (adopted: doc/decisions, 41 files, index matches)
            ✗ docs/PROGRESS.md missing
            ✓ CHANGELOG.md has [Unreleased]
  agents    ✗ AGENTS.md missing · ✓ CLAUDE.md (no import of AGENTS.md)
  ci        ✗ swerepo-ci.yml missing (you run pytest in tests.yml: kept)
  security  ✗ 2 personal email addresses in tracked files (README.md:12, setup.cfg:4)
  github    ✓ PR template · ✗ ruleset "swerepo" missing · ? Copilot review (no access to read it)
  seamspec  ✗ not set up
  openspec  – not chosen
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
  Skipped for pull requests by bots listed under `[pr] exempt_authors` (default `dependabot[bot]`, passed in by the workflow) and for diffs that touch only lockfiles.
- **What this version checks** is listed in `swerepo/standard.py`; checks a later phase adds show as `?` naming that phase, never silently skipped. The header names the folder, not its absolute path, and the commit-email check counts addresses without printing them (ADR-20261120-fc5a). `--base` runs at the repository's top level; its mechanics (merge base vs working tree, PEP 503 dependency names, `--author` for the bot exemption) are in ADR-20261120-5e21. `--json` prints one JSON value and nothing else, also with `--ci`.
- **No score.** A number invites gaming and hides what matters; the list says what to do next.

---

## 16. Updating

- **`swerepo update`** (`-u`) re-renders every applied component with the current templates and standard, and, for each file, block or section:
  - unchanged since SWERepo wrote it → replaced with the new render;
  - changed by a person → **three-way merge** with `git merge-file`: the base is the earlier render (rebuilt from the recorded template version and `[values]`, checked against `rendered`), "ours" is the person's file, "theirs" is the new render. A clean merge is shown as a diff in the plan and applied on yes. A conflict leaves the file as it is, is reported as `~ conflict`, and `swerepo diff` shows the change to apply by hand. SWERepo never writes conflict markers into a file;
  - new item in the standard → added (shown in the plan);
  - item removed from the standard → reported, never deleted automatically.
- **Per component:** `swerepo -u --seamspec`, `-u --ci`, `-u --agents`, …
- **The standard's changelog** ships with the package, so `update` can say why something changed ("standard 2: CI adds Python 3.15").
- **Version pins** of other tools (SeamSpec's CI pin, SWERepo's own pin in CI, action SHAs) are updated only through `update`, always shown first.

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
- **Modules:** `detect` (§10), `plan` (what to change), `render` (templates and normalised hashes), `merge` (three-way), `apply` (writes, with fingerprints), `state` (`.swerepo.toml`), `check` (§15), `github` (`gh` calls, threads), `docs` (ADR index, progress), `tools` (SeamSpec, OpenSpec bridges), `cli`.
- **Tests:** pytest with fixture repositories (empty folder without git, fresh `uv init` project with no GitHub remote, an established project with its own CI, black and flake8, ADRs in `doc/decisions`, a CLAUDE.md and an existing CODEOWNERS, a monorepo with a TypeScript folder and a uv workspace root, two branches that each add an ADR and a progress entry), a fake `gh` and a fake `seamspec`/`openspec` on `PATH`, plus one test against the real SeamSpec. Merge tests cover clean merges, conflicts and line-ending changes.
- **Its own repository** is set up by SWERepo (dogfooding), uses SeamSpec on its own rules, and follows the process it installs: branches and PRs, Copilot review, ADRs, progress entries, a release workflow with a human approval. It doubles as the public example of the standard.
- **Published on PyPI** only with the owner's explicit go-ahead for each release (as for SeamSpec).

---

## 19. Open questions

1. **Name.** *Decided:* **SWERepo**, package and command `swerepo` (ADR-20261120-1a27), renamed from the working name Golden Repo before anything was published: "golden repo" is a generic, crowded term, and the GitHub organisation name `goldenrepo` was taken. Reserved on PyPI with a 0.0.1 placeholder the owner publishes (ADR-20261119-d68b). (Earlier reasoning, still true: not `golden`, because "golden files" and "golden tests" already mean snapshot testing in Python.)
2. **Where it lives.** *Decided:* its own organisation, public: `github.com/swerepo/swerepo` (ADR-20261119-13fc, names from ADR-20261120-1a27).
3. **License.** *Decided:* Apache-2.0, like SeamSpec (ADR-20261119-7384).
4. **Type checker.** None by default, mypy, pyright or ty. Proposal: none in standard 1, offered as an option.
5. **Secret scanning.** GitHub's own secret scanning plus the privacy check only, or also a local scanner (for example gitleaks) as an option. Proposal: GitHub's plus the privacy check; a local scanner with the pre-commit option later (it's a separate binary).
6. **OpenSpec details** (§14), confirmed from its public docs before building that component.
7. **Copilot review in rulesets.** *Decided:* rule `copilot_code_review` (parameters `review_on_push`, `review_draft_pull_requests`); it requests a review when the pull request author has Copilot code review access, so the account check is GitHub's. This repository uses it on every pull request with resolved threads required (ADR-20261120-2e50).
8. **Should SWERepo create the branch and PR for each step** (`--pr`, through `gh`), or leave git to the person? Proposal: leave it to the person in v0.1; consider `--pr` later.
9. **Agent instructions length.** The target is under 40 lines; measure with real sessions how much is followed. In the same sessions, check whether Claude Code reading both SeamSpec blocks through `@AGENTS.md` (mixed-editor projects, §6.6) causes confusion; if it does, switch to rendering SWERepo's block into both files.
10. **Changelog fragments.** `CHANGELOG.md [Unreleased]` is edited by many PRs and conflicts like the old progress log did. Proposal: keep Keep a Changelog in standard 1; offer fragments (`changelog.d/`, compiled at release) as an option once the release component needs it.
11. **Default mode for user-owned repositories with agent identities.** If SWERepo can tell that recent PRs come from a machine account, should it propose `team` mode?

---

## 20. Roadmap

**v0.1 — Python, one repository**
Built in this order: `check` (with `--base`); then `init`, `update`/`-u` with three-way merge, `diff`, `status`, `progress`, `adr`, `threads`; components `docs`, `agents`, `ci`, `security`, `github` (both modes); then `seamspec`; `openspec` if its docs confirm a clean non-interactive init; `release` optional. Existing-repository detection and adoption; `.swerepo.toml`; tests on fixture repositories; dogfooded on its own repository and on one established repository of the owner's.

**v0.2**
TypeScript (npm/pnpm, vitest/jest, eslint/prettier), matching SeamSpec's presets; monorepo projects; `--pr` to open one pull request per component; the OpenSpec importer once SeamSpec ships it; changelog fragments (§19.10).

**Later**
`swerepo check` across many repositories (an organisation report); more languages; GitLab and other forges; organisation-specific standards (a company's own additions on top of the standard). Optional components, each only if dogfooding shows it earns its cost: local git hooks (pre-commit or prek: blocking commits on `main` and running the privacy check first, gitleaks later), editor hooks that block risky commands, editor skills and slash commands that wrap the `docs/agents/` runbooks, architecture layer contracts (import-linter), coverage on changed lines, Conventional Commits.

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
| Dependence on other tools (gh, SeamSpec, OpenSpec) changing | Use only their documented commands; test against fakes and one real version; report clearly when a tool is missing or too old (SeamSpec 0.1.1's `--json` lesson) |
| An existing codebase failing a new linter on day one | Existing linters kept by default; a move to ruff checks only the files each PR changes (§6.3) |
| Teammates' PRs failing new PR rules on day one | Warn-only mode in existing repositories, switched on by a commit (§10) |
| A monorepo project silently outside the required checks | Named in the plan; its checks required or knowingly recorded as not covered (§11) |
| Too many tools to install | Python, uv, git and `gh` only; others optional or through `uvx` |
| Two projects to maintain | Small scope for v0.1; shared release process and habits with SeamSpec |
| Over-long agent instructions | One short block in AGENTS.md, measured in real sessions (§19.9) |

---

## Appendix A: Revision history

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
| Local git hooks (pre-commit, commit-msg, pre-push) with prek, gitleaks, Conventional Commits | **Deferred**, optional (§20) | Extra binaries, slower commits; CI is the guard |
| Editor hooks denying risky commands (`.agents/`, `.cursor/`, `.claude/`) | **Deferred**, optional (§17, §20) | Speed bumps only, and four host formats to maintain |
| Architecture layer contracts (import-linter) | **Deferred**, optional (§20) | A new project has no layers yet; generic contracts add little |
| Diff-coverage gate (≥ 85%) | **Deferred**, optional (§20) | Agents can meet a coverage number with tests that check nothing |
| `required_linear_history`, strict status checks | **Not taken** / option (§12) | Linear history follows from squash-only; strict checks force constant rebasing |
| SLSA build provenance on release | **Taken**, public repositories only (§6.9) | A few lines in the optional release workflow; needs a paid plan on private repositories |
| `BRAINDUMP.md`, `docs/ARCHITECTURE.md` | **Not taken** in standard 1 | Not needed by the core process; easy to add later |
| Public showcase repository | **Taken** as SWERepo's own dogfooded repository (§18) | One repository, not two |
