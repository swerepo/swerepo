---
id: ADR-20261125-5f22
title: A codebase never linted moves to ruff gradually, and a project without tests is warned
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-25
scopes: ["SWEREPO-SPEC.md", "swerepo/init.py", "swerepo/check.py", "swerepo/ci.py", "swerepo/cli.py", "swerepo/github.py", "swerepo/privacy.py", "swerepo/state.py", "swerepo/detect.py", "swerepo/standard.py", "swerepo/seamspec_component.py", "swerepo/templates/agents/prepare-pr/"]
invariants: ["inv_197d9002", "inv_260277fe", "inv_81872dfe"]  # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261125-5f22: A codebase never linted moves to ruff gradually, and a project without tests is warned

## Context

Phase 8 dogfoods SWERepo on an established repository of the owner's (ADR-20261124-152d point 5). `swerepo check` and `swerepo init --dry-run` there, and a full `init` on a throwaway `uv init` project, changed nothing they shouldn't have. But they showed two ways the CI SWERepo writes would fail on its very first pull request, for reasons the person's change has nothing to do with:

1. **A codebase that has never been linted.** With no linter found, spec §6.3 adds ruff "as for a new project", so the `lint` job checks every file. On the repository dogfooded, ruff reports 19 problems and would reformat 44 files, so `ci-ok` is red from day one. The gradual move to ruff (checking only the files each change touches) already exists, but only for projects leaving another linter.
2. **A project without tests.** pytest exits 5 when it collects no tests, so the `test` job fails on a fresh `uv init` project. The job can't be made to pass by masking it, and it shouldn't be: the CI-tests rule (`hygiene/ci-tests`) forbids `|| true` and the like. But nothing told the person why it fails, or told an agent what to do instead. An agent asked to make CI green could reach for exactly the masking the rule forbids.

The owner decided on 2026-11-25: gradual ruff for a codebase never linted, and a warning plus an instruction for agents when there are no tests.

## Decision

1. **A codebase never linted moves to ruff gradually.**
   - **When:** a project with no linter of its own (no ruff, black, isort, flake8 or pylint configuration) in a repository that already has commits.
   - **What:** `init` chooses the gradual move to ruff (§6.3) instead of full ruff. Ruff's settings are added, and the `lint` job checks only the Python files each change touches, so existing code isn't flagged all at once. The plan says why, and how to check every file later: fix the codebase in one pull request, then set `lint = "ruff"` under `[values]` in `.swerepo.toml` and run `swerepo update --only ci,agents`, so the agents' commands follow the workflow (review P8-G02).
   - **A repository without commits** (a new project) still gets full ruff.
   - **A recorded choice is kept**, so repositories already set up don't change.
   - **Projects listed with `--projects`** keep full ruff, and the plan says so for one never linted, naming the job that will fail; per-project gradual linting comes with v0.2's monorepo work (Phase 10; review P8-G03).
2. **A project without tests is warned, and agents are told what to do.**
   - **`init`'s plan** notes "no tests yet: the `test` job fails until there is one (pytest exits 5 when it collects none)" when it writes the workflow.
   - **`check`** reports `ci.tests` as a warning that never fails `--ci`, while no file looks like a pytest test (`test_*.py` or `*_test.py`, listed as detection lists files).
   - **`agents/prepare-pr@3`**, the runbook agents read before a pull request, adds to its test step: if pytest says "no tests collected", write a real test for the behaviour the change touches (the spec's behaviours are a good start), and never make the test job pass by masking it, skipping it or removing it. Repositories get it through `update`.
   - **SWERepo writes no test itself:** it doesn't write a project's code, and a placeholder test would pass for the real thing.
3. **Smaller fixes from the same run:**
   - **The tools note** names the optional extra a tool is declared in. `uv sync` doesn't install extras, so pytest in `[project.optional-dependencies] dev` doesn't count, and the plan now says so.
   - **A privacy finding** says how to clear it, without saying what was found: use a reserved example domain such as `example.com`, mark the line `swerepo: allow-privacy`, or list the file under `[privacy] allow_paths`.
   - **"Dependency graph off" is said once:** when `github` reads GitHub's dependency graph, `ci`'s general note about it is dropped.

4. **Applying it for real, step 1 (`docs` and `agents`), showed two more gaps** (the owner's choice, 2026-11-25):
   - **Editors on the command line:** `init` and `update` take `--editors claude,antigravity` (or `none`). It sets the editors without the terminal question and records them, replacing what was recorded; the plan shows the change. Before, an agent running `init --yes` got no editor files, and a recorded choice could be changed only by editing `.swerepo.toml`. The list is compared as a set, so a different order changes nothing. Dropping an editor leaves its file in place, since SWERepo never deletes one.
   - **The agents' commands must run:** when `agents` writes its block and `ci` isn't part of the run, the plan says which tools `uv sync` won't install, as `ci`'s plan does. The commands themselves stay the ones CI runs.
   - **Wording:** after applying, `init` and `update` say to commit on a branch, not on a new one.

5. **Applying the rest (`ci`, `security`, `github`) showed four more gaps** (the owner's choices, 2026-11-25, after Gemini's design review `P8-A01` to `P8-A07`):
   - **GitHub's settings change only when asked for by name.** `init` and `update` take `--apply-github`.
     - `--yes` alone writes the files and never changes GitHub: the ruleset and merge settings show as waiting ("needs `--apply-github`"), aren't counted as changes, and `[github] applied` stays false, so a second run says "Nothing to do.".
     - `--yes --apply-github` applies them, sending exactly the committed files, as `--yes` did before.
     - In a terminal each change is shown as JSON and asked about, whatever the flags. Without a terminal, `--apply-github` without `--yes` exits 2.
     - It follows `update --merge`'s consent model (ADR-20261124-7afa). Before, a second run with `--yes`, meant only as a check, applied the settings on the established repository against the owner's no (SeamSpec dead end `de_00bb3c21`).
   - **A table another tool appends inside SWERepo's `pyproject.toml` block.**
     - The block owns the tables under `tool.ruff` and `tool.pytest`, so editing those stays an ordinary edit.
     - Anything else (uv's `[dependency-groups]`, another tool's `[tool.x]`) is named by `check`, `init` and `update` with the fix, "move it above `# swerepo:begin`"; a block that isn't valid TOML is named as such.
     - The file is then left byte for byte: never merged, rewritten, or offered for deletion by `swerepo diff`. SWERepo never moves the table itself (spec §5).
     - The project's dependencies are read from the whole file, falling back to the file without the block when it doesn't parse.
   - **`check`'s "Next:" names what fixes each gap.**
     - Each finding carries `fix`: `init`, `apply-github`, or a short fixed step (a command such as `swerepo adr index`, or the person's step, such as turning on the dependency graph), set where the finding is made. `--json` shows it.
     - "Next:" suggests `swerepo init --only …` only for gaps `init` can write, then each other step once.
     - The steps are fixed phrases, never a finding's own text, so nothing found (an address, a path) is repeated there (`inv_ab57c6ff`, `inv_5e3b5ef3`).
   - **`--editors`, tightened:**
     - it needs `agents` in the run, which writes and records the editors' files, so a run without it never shows them as recorded (review P8-A08);
     - a repeated name counts once, and an empty list or `none` with other names is wrong usage, also at the terminal question;
     - a dropped editor's file stays and is the person's now: its record goes on the next `agents` run, and `check` doesn't miss it meanwhile;
     - choosing it again manages its block again when the block is as SWERepo wrote it;
     - an added non-Claude editor (beyond those recorded, or detected when none are) runs `seamspec init` again where SeamSpec is set up and in the run.
   - **The `AGENTS.md` tools note** comes only for a project `uv sync` installs, for the tools its commands run through `uv run` (a Makefile target or Poetry runs its own), and once: it is added after every component is planned, unless `ci` already said it.

**Alternatives considered:**
- **Full ruff, with a warning in the plan.** CI stays red until someone runs ruff over the whole codebase in one large, noisy pull request that clutters `git blame`.
- **Asking in the plan, gradual or full.** One more question at the first run, and a run without a terminal still needs a default; gradual is the safe one.
- **A starter test written by SWERepo.** Green at once, but it is code SWERepo would be writing, and a placeholder the CI-tests rule would treat as the real test.
- **No `test` job until tests exist.** It weakens the standard, needs a special case in `ci-ok`, and the CI-tests rule would fail.
- **Applying GitHub's settings as a command of its own** (`swerepo github apply`), instead of `--apply-github`. One more command to learn, and `init` would still need to say how; a flag beside `--merge` keeps one consent model.
- **Moving ruff's settings to `ruff.toml`** so `uv add` can't append inside SWERepo's block. pytest's settings would stay in `pyproject.toml` and catch the same appends, and it changes released template families; an idea for v0.2.

## Enforced Invariants

Locked by the owner on 2026-11-25, after a read by SeamSpec's reviewer:
- **`inv_197d9002`, a codebase never linted isn't red on day one:** for the root project, gradual ruff for an existing codebase, full ruff for a new project (in one run or in stages), and a recorded choice kept in both directions, also where SWERepo would choose the other. What `--projects` folders get is left out, so v0.2 can bring them gradual linting.
- **`inv_260277fe`, missing tests never fail `check --ci`:** `ci.tests` is missing but not blocking, `check --ci` exits 0 with warning annotations and no error, a `.seamspec/` test doesn't silence it, and it goes once a test exists. It says what the code checks: files named `test_*.py` or `*_test.py`, outside pytest's default skipped folders, under `testpaths` when set, not a project's own `python_files` or `norecursedirs`, since the warning never blocks.

Both check structure (recorded values, the job's commands, findings, exit codes, annotation kinds), never the plan's wording, which ordinary tests cover (the owner's watchouts). Someone editing `[pr]` by hand changes what SWERepo recorded about the repository's start, and with it the lint default for a repository whose lint isn't recorded yet; that is left as a deliberate edit, not tested.

Locked by the owner on 2026-11-25 for point 5, after Gemini's code review and a read by SeamSpec's reviewer:
- **`inv_81872dfe`, GitHub's settings change only when asked for by name** (critical), replacing `inv_ef31cc79` (superseded): every read-only promise of `inv_ef31cc79` with the same checks, plus `--yes` alone on a first and second `init` and on `update` changing nothing, in a terminal too, a terminal's yes to both changing only the `swerepo` ruleset and merge settings with the committed files, `--apply-github` without `--yes` or a terminal exiting 2, and `init` and `update` with `--yes --apply-github` sending exactly the committed files to the `swerepo` ruleset and merge settings only.

The CI-tests rule (`hygiene/ci-tests`, locked here as `inv_11ce8c5b`) already forbids masking the test job; the instruction to agents points them away from it.

## Consequences

- An established repository gets a green `ci-ok` on its first pull request, and its codebase reaches ruff's standard file by file, as part of normal work.
- A new project's CI is red until its first test exists. The plan, `check` and the agents' runbook all say why, and what to write.
- The test for "existing" is the same one the pull-request rules use for warn-only mode: the repository has commits (§10).
