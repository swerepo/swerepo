---
id: ADR-20261121-6c3d
title: How swerepo init applies docs and agents - a plan first, managed and starter files, never replacing a file
status: ACCEPTED
date: 2026-11-21
scopes: ["swerepo/init.py", "swerepo/blocks.py", "swerepo/cli.py", "swerepo/templates/", "SWEREPO-SPEC.md"]
invariants: ["inv_8314036c", "inv_1002d669"]
supersedes: null
superseded_by: null
---

# ADR-20261121-6c3d: How swerepo init applies docs and agents

## Context

Phase 3 builds `swerepo init` for the `docs` and `agents` components (spec §6.5, §6.6, §7, §10) on Phase 1's templates, fingerprints and state file. The spec's principles bound it: show the plan, then do it (1); never overwrite what a person changed (2); add beside, don't edit (3); repeatable (6). The open points were which files SWERepo keeps current afterwards, how a block is added to an existing file, what happens without a terminal, and what the generated agent rules say.

## Decision

1. **Plan, then apply.** `make_plan` reads the repository and decides each file's action: `create`, `add block`, `keep` (yours), `current`, `changed` (by you), `outdated` (a newer template: `swerepo update`, Phase 6), `adopt`, `note`, or `later` (a component a later phase adds). It writes nothing, and builds the new `.swerepo.toml` in memory, so "nothing to do" is exact. `apply` writes that plan and nothing else.
2. **Managed and starter files.** *Managed* files are recorded in `.swerepo.toml` and kept current by `update`: the ADR folder's `README.md` and `TEMPLATE.md`, the three `docs/agents/` runbooks, and SWERepo's blocks in `AGENTS.md`, `CLAUDE.md` and `GEMINI.md`. *Starter* files are written once and are the person's from then on, never recorded: `README.md`, `docs/PROGRESS.md`, `CHANGELOG.md`, `CONTRIBUTING.md` and the first progress entry. They are meant to be edited, so recording them would make `check` report every edit.
3. **Never replace a file.** A missing file is created with exclusive creation (a file that appears between plan and apply stops the run). An existing file only ever gains SWERepo's marked block at its end: its whole text stays byte for byte, blank lines at its end included, and only the line breaks that make one blank line are added before the block. Every target is checked before anything is written, so a file or block that appeared since the plan stops the run with nothing written (no SWERepo content left behind unrecorded); each write checks again. An existing file without a record is the person's (`keep`); a recorded file or block whose fingerprint no longer matches is `changed` and left alone; broken markers are reported, not repaired. Files are read with their line endings as they are (`blocks.read_exact`), and the block is appended in the file's own line endings, so a CRLF file stays CRLF; lines are counted on CR, LF and CRLF only, as `find_block` counts them (Unicode line separators stay inside their line). Broken markers met while applying stop the run with an error, not a traceback. A failed `git init` is reported by exit status only, never with the folder's path. A file that can't be read stops the plan with an error naming its repository path.
4. **The generated ADR index is left out of the README's fingerprint** (`blocks.file_fingerprint`), and `check` uses the same function, so `swerepo adr index` never makes the README look edited.
5. **Values recorded:** the values the managed templates use (`project`, `adr_dir`, `progress_dir`, `commands`, `test_inline`) go into `[values]`, and later runs render with the recorded ones, so a template only becomes `outdated` when its version changes. Commands follow the project: uv by default, poetry with a `poetry.lock`, a Makefile's `install`, `test` and `lint` targets when present, kept linters (black, isort, flake8, pylint) instead of ruff. Linters recorded under `[adopted] linters` come before detected ones, as in `check`.
6. **Questions.** Editors are asked in a terminal, pre-filled from detection (`claude`, `cursor`, `vscode`, `antigravity`, `gemini`), and recorded under `[agents] hosts`; once recorded they aren't asked again. `CLAUDE.md` gets a block holding `@AGENTS.md` (Claude Code only); `GEMINI.md` gets a block that points to `AGENTS.md` and imports it (Antigravity or Gemini CLI), so nothing is copied. Then `Apply? [y/N]`. **Without a terminal**, `init` applies only with `--yes`; otherwise it prints the plan and exits 2 without writing. `--dry-run` prints the plan and exits 0.
7. **Existing repositories.** An ADR folder elsewhere (`docs/decisions`, …) is adopted (`[adopted] adr_dir`) and nothing is added to it; `swerepo adr new` and the agent rules use it. A new `.swerepo.toml` in a repository with commits starts the pull-request rules warn-only (`[pr] enforce = false`, `warn_since` today); with no commits, enforced (spec §10). Not a git repository: `git init` is part of the plan. A folder holding other repositories stops `init`. `docs/adr` itself is adopted the same way when its README is the person's own and has no index markers. A folder inside a git repository (not its top level) stops `init`: the repository-level files live once, at the root (spec §11).
8. **No license is ever picked**, and none is asked for in this version: the plan notes that there is none. **An existing README is never edited** (principle 3); the starter README is written only when there is none. Both change the spec (§6.5, §8).
9. **A progress entry for the pull request that adds SWERepo** (`<progress_dir>/YYYYMMDD-swerepo-init.md`) is part of any run that changes files with `docs` chosen, so that PR passes its own progress rule. Writing `.swerepo.toml` counts as a change here, so a repository whose docs were all there already still gets the entry.
10. **Shorthand flags:** `--docs` is `--only docs` and `--no-docs` skips docs, for every component, on `init` and `check`. They are read from the extra arguments and checked: anything else is a usage error (exit 2). On `check`, `--no-<component>` leaves a component out of the chosen ones (or of `--only`), never adding unchosen ones; nothing left to check is a usage error.
11. **The agents block** (21 lines plus the commands) states the nine working rules of spec §6.6. Rule 7 doesn't name `swerepo threads` until that command exists (Phase 5, a new template version). The `address-review` runbook says to leave resolving threads to the person who asked for the review.

**Alternatives considered:**
- **Record every file SWERepo writes.** Starter files are edited by design; `check` would report `~` forever, and `update` would fight the person's own progress notes.
- **Insert the block at the top of an existing file.** The person's title and intro come first; the end of the file is where an addition is least surprising and easiest to review.
- **Ask for a license and write its text.** License texts are long, legal text the person should choose and read; a note is honest and cheap.
- **Declare `--docs`, `--no-docs`, … as sixteen options.** The help would be unreadable; one epilog line says it, and unknown arguments are still rejected.

## Enforced Invariants

- `inv_8314036c` (proposed, critical): init never replaces or edits a file it didn't write, except adding its block at the end; a person's later edits are left alone; a file that appears between plan and apply is never replaced.
- `inv_1002d669` (proposed, critical): `init --dry-run` writes nothing, and a second `init` on a set-up repository writes nothing.

Both wait for the owner's approval.

## Consequences

- `swerepo check` after `init --only docs,agents` reports both components complete.
- Phase 6's `update` merges managed files and blocks only; starter files stay the person's.
- Every new managed template version needs `update` before `init` reports it `current` again.
