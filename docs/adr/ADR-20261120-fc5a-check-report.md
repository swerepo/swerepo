---
id: ADR-20261120-fc5a
title: How swerepo check reports: findings per component, honest "?" for what this version can't check, exit codes, and no personal data in output
status: ACCEPTED
date: 2026-11-20
scopes: ["swerepo/check.py", "swerepo/prrules.py", "swerepo/standard.py", "swerepo/cli.py", "SWEREPO-SPEC.md"]
invariants: ["inv_294c48c9", "inv_5e3b5ef3"]
supersedes: null
superseded_by: null
---

# ADR-20261120-fc5a: How swerepo check reports

## Context

`swerepo check` (spec §15) is the first real command and the first user of Phase 1's modules. It is read-only and reports, per component, what meets the standard (`✓`), is missing (`✗`), was changed by a person (`~`), is outdated (`↑`), can't be told (`?`) or isn't chosen (`–`). Some checks the spec lists need parts that later phases build: the privacy scanner (Phase 4, `security`), the generated CI workflow's Python matrix (Phase 4, `ci`), live GitHub settings through `gh` (Phase 5, `github`), and SeamSpec's own health (`seamspec doctor`, Phase 7). `check` runs in CI logs and terminals people paste from, so its output must not leak personal data.

## Decision

1. **A finding** is: component, item (a short stable key such as `docs.progress`), status, a one-line message, an optional repository-relative path, and whether it blocks. Findings are computed first, then printed as text or JSON, so both say the same thing.
2. **Which components are checked:** those in `.swerepo.toml` `components`; without a state file, the default set `docs, agents, ci, security, github, seamspec`, plus `openspec` when `openspec/` exists and `release` when a release workflow exists. Others show `– not chosen`. `--only` narrows the list; an unknown component name is wrong usage (exit 2).
3. **Standard-1 items checked in this version** (`swerepo/standard.py` lists them): presence and structure of every file the standard names; `CHANGELOG.md` has `[Unreleased]`; the ADR index matches the ADR files (when the folder is SWERepo's own); `AGENTS.md` has the SWERepo block; `CLAUDE.md` imports `AGENTS.md` and `GEMINI.md` exists when those editors are in use; `swerepo-ci.yml` has a `ci-ok` job; ruff (or kept linters) is configured and excludes `.seamspec`; `.gitignore` has the SWERepo block; `CODEOWNERS` keeps the SWERepo block last; the git commit email (configured and recent commits) is a noreply address; SeamSpec is set up, enforced, its earned spec exists and some workflow runs `seamspec verify`; OpenSpec and release workflows when chosen; and every file and block recorded in `.swerepo.toml` (`✓` unchanged, `~` changed by a person, `↑` an older template version than the latest, `✗` gone, `?` template unknown to this version). A file recorded in `.swerepo.toml` that the component already reports as `✓` or `✗` isn't reported twice (one line, one count); its `~`, `↑` and `?` always show. A kept linter (`[adopted] linters`) that has no configuration SWERepo can find is `?`, not `✓` (it may run from CI alone). `[adopted] adr_dir` may be any folder. Ruff must exclude all of `.seamspec` (`.seamspec`, `.seamspec/**` and the like), not a part of it; YAML comments don't count as running `seamspec verify`. Checking a folder inside a repository says so (`?`). In a monorepo, whether every project is covered by a required check is `?` until Phase 4.
4. **Checks a later phase adds are listed as `?`**, with the phase that adds them ("privacy scan: checked from Phase 4"), not silently left out: a `✓` on a component must never claim more than was checked. These `?` lines disappear as the phases land.
5. **Exit codes** (spec §7): `0` when nothing chosen is `✗`; `1` when something chosen is `✗` (blocking); `2` for wrong usage. `~`, `↑`, `?` and `–` never fail. `--ci` additionally never calls GitHub and, on GitHub Actions, prints `::error` / `::warning` annotation lines for `✗` findings. `--only` with no component is wrong usage. Annotation values are escaped as GitHub expects (`%`, CR, LF; `:` and `,` in the file property), and `--json` prints one JSON value only: with `--ci` on Actions, no annotation lines follow it.
6. **Text output is plain:** `typer.echo` of fixed-width lines, no Rich styling or wrapping, so logs and tests read the same everywhere (PR #1's lesson). **JSON** has stable status names (`ok`, `missing`, `changed`, `outdated`, `unknown`, `not-chosen`), the findings, a summary and the exit code.
7. **No personal data in output.** The header names the folder, not its absolute path (a home path would appear in CI logs and pasted reports). The commit-email check reports how many commits use a non-noreply address, never the address. An error reading `.swerepo.toml` gives the reason without the file's path (an `OSError`'s text names the absolute path). CODEOWNERS findings name the path patterns of overriding rules, never a token with `@` (an owner, or a malformed line that is only an email address). Git's output is read as UTF-8 (undecodable bytes replaced), and file contents from git are compared as bytes.
8. **A state file that can't be read** is one blocking `✗` ("`.swerepo.toml`: …") and record checks are skipped; **a newer SWERepo's state file** is a `?` ("upgrade SWERepo") and record checks are skipped (ADR-20261120-ecf7).
9. **Next step:** the summary line suggests `swerepo init --only …` for the first components with `✗`, in the recommended order of spec §10 (`docs,agents`, then `ci,security`, then `seamspec`, then `github`).
10. **Read-only means git's index too.** `git diff` against the working tree refreshes the index it reads and writes it back when file times are out of date, even with `git --no-optional-locks` (the switch does not cover `git diff`; tested with git 2.50). The pull-request rules therefore run that one diff with `GIT_INDEX_FILE` pointing at a temporary copy of the index; every other git call `check` makes (`rev-parse`, `ls-files`, `merge-base`, `log`, `show`, `config`) was probed and writes nothing. Found by the earned rule's test before it was proposed. **Known limit:** in a repository using git's split index (`core.splitIndex`, `update-index --split-index`), git itself refreshes the shared index file's modification time whenever any command reads the index (even `git ls-files`); its content never changes. `splitIndex.maxPercentChange=100` and `core.splitIndex=false` don't prevent it (tested with git 2.50), so SWERepo can't, and the read-only rules' tests use a normal index.

**Alternatives considered:**
- **Leave unimplemented checks out of the report.** A component would show only `✓` lines while its hardest checks never ran.
- **Rich tables.** Styled, wrapped output differs by terminal and broke a test on GitHub Actions (PR #1).
- **Fail on `~` or `↑` too.** A person's deliberate change or a newer template is not a defect (spec §15).
- **Print the absolute path** as the spec's first example did. Leaks the home folder into logs.
- **`git diff-index` without refreshing,** which never writes. With an out-of-date index it reports every touched-but-unchanged file as modified, so a workflow someone merely touched would need an ADR.
- **`git --no-optional-locks diff`.** Tried first; `git diff` still rewrote the index.

## Enforced Invariants

- `inv_5e3b5ef3` (proposed, critical): with a personal git email (configured and in a commit), an email-only CODEOWNERS line and an unreadable `.swerepo.toml`, `check` output (text, `--json`, `--ci` annotations, each with `--base`) contains no absolute path, home folder or personal email address. Worded for the cases its test covers, not "never". Waiting for the owner's approval.
- `inv_294c48c9` (proposed, critical): `swerepo check` never writes to the folder it checks, not even git's index, with `--base` and outside git. Waiting for the owner's approval.

## Consequences

- The report grows phase by phase without its format changing.
- `swerepo.standard` is the one place the list of standard-1 items lives; Phase 3's `init` uses the same list to know what to create.
