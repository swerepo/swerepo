# 2026-11-25 · Dogfooding on an established repository, and what it changed

**Branch:** `phase-8/dogfooding`

## Done

- **Dogfooded, read-only, on an established repository of the owner's:**
  - **the repository:** a Python package at its root, no CI, no linter, `pytest` in an optional extra;
  - **`check` and `init --dry-run`** changed nothing in it, its git status included;
  - **a throwaway `uv init` project** went through `init`, `check`, a second `init` and `update` cleanly (ruff, `ruff format` and zizmor pass on what SWERepo wrote).
- **Two ways CI would have been red on day one, fixed as the owner chose (ADR-20261125-5f22):**
  - **A codebase never linted moves to ruff gradually:** a repository with commits and no linter gets ruff on the files each change touches (19 problems and 44 files to reformat there otherwise). A new project still gets full ruff, a recorded choice is kept, and the plan says how to check every file later.
  - **A project without tests is warned:** the plan notes it, `check` reports `ci.tests` as a warning that never fails `--ci`, and `agents/prepare-pr@3` tells agents to write a real test, never to mask, skip or remove the job. SWERepo writes no test itself.
- **Smaller fixes:**
  - the tools note names an optional extra `uv sync` doesn't install;
  - a privacy finding about an address or a path says how to clear a placeholder in `init`'s plan. `check`'s finding stays exactly where-only, as the locked `inv_ab57c6ff` requires, and the hint never shows for a key;
  - "dependency graph off" is said once when `github` reads it.
- **Spec v0.17:** §6.2, §6.3, §6.4, §6.6, §8, Appendix A.
- **Dogfooded here:** `update` brought `prepare-pr@3` in.
- **Tests:** `tests/test_dogfooding.py`. Each change was broken on purpose and caught: nine breakages.

- **Gemini's review** (`P8-G01` to `P8-G06`, in `CODE_REVIEW.md`), each fixed and each fix broken on purpose and caught:
  - `has_tests` follows pytest's discovery (no `.seamspec/` or other skipped folders, `testpaths` read), and listed projects are checked too;
  - switching to full ruff is `update --only ci,agents`, and `[values] commands` moves on only with the agents' files;
  - a listed project never linted is said to get full ruff;
  - the privacy hint is withheld with a key among the findings;
  - a new repository set up in stages stays new;
  - the file listing is reused, with `--no-optional-locks`.

- **Review closed** after two rounds: Gemini accepted `P8-G01` to `P8-G06`, added to [docs/reviews/phase-8.md](../reviews/phase-8.md).

- **SeamSpec, locked by the owner on 2026-11-25** (30 rules in force; `docs/EARNED_SPEC.md` regenerated):
  - `inv_197d9002`: a codebase never linted isn't red on day one;
  - `inv_260277fe`: missing tests never fail `check --ci`.

  Both check structure, never wording, and Rule 1 covers the root project only, so v0.2 can change what `--projects` folders get (the owner's watchouts). After SeamSpec's reviewer read them, both were tightened: Rule 1 tests the plain new project and recorded choices in both directions, with `swerepo/detect.py` in scope; Rule 2 says what the code checks and exits 0 outside GitHub Actions too. Each rule's test was checked by breaking what it guards: ten breakages, all caught. `init`'s plan note is covered by ordinary tests instead.

- **Applied for real, step 1** (`docs` and `agents` on a local `swerepo-setup` branch of the established repository, the owner answering the terminal's questions, not committed there): `check` clean for both components and a second run with nothing to do. Two gaps found and fixed (ADR-20261125-5f22 point 4), each fix broken on purpose and caught (ten breakages; one first missed, `--editors none` on the command line, until a test covered it):
  - **`--editors`** on `init` and `update`: an agent can choose editors, a person can change them, the plan shows the change, and the order doesn't matter (adding Claude Code there first needed a hand edit to `.swerepo.toml`);
  - **the agents' commands:** without `ci` in the run, the plan says which tools `uv sync` won't install (`pytest` in an optional extra, `ruff` not a dependency there);
  - **wording:** "commit them on a branch".

- **Applied for real, the rest** (`ci`, `security` and the `github` files there; GitHub's settings not applied, as the owner chose). Four more gaps, designed first and reviewed by Gemini (`P8-A01` to `P8-A07`, two rounds, all accepted), then built (ADR-20261125-5f22 point 5):
  - **GitHub's settings change only when asked for by name:** `--yes` alone writes the files and leaves GitHub as it is; `--yes --apply-github`, or a yes in a terminal after each change is shown, applies them. A second run with `--yes` had applied them there, against the owner's no; it was undone by hand and logged as dead end `de_00bb3c21`;
  - **a table `uv add` appended inside SWERepo's `pyproject.toml` block** is named with the fix and left alone, and dependencies are read from the whole file;
  - **`check`'s "Next:"** names what fixes each gap, never `init` for what it can't write (there, it suggested `init --only ci,security` when only the person's steps were left);
  - **`--editors`** needs `agents`, refuses wrong lists, lets a dropped editor's file go, and runs `seamspec init` again for an added editor; the `AGENTS.md` tools note follows what its commands run, once.

  Each fix broken on purpose and caught: 22 breakages (two first missed, until sharper tests covered them).
- **Gemini's code review** (`P8-A08` to `P8-A10`), each fixed, broken on purpose and caught:
  - `--editors` needs `agents` itself, and the SeamSpec rerun compares with the detected editors when none are recorded;
  - "Next:" never suggests `init` where it writes nothing: pull-request rules, a project CI can't install, SeamSpec's own unpinned workflow, an edited ADR README;
  - the proposed rule tests `update` as it does `init`.
- **SeamSpec, approved by the owner on 2026-11-25** (30 rules in force; `docs/EARNED_SPEC.md` regenerated): `inv_81872dfe` (critical) replaces `inv_ef31cc79`, which said `--yes` applies GitHub's settings, and the dead end `de_00bb3c21` is recorded. Before the owner's review, SeamSpec's reviewer found `--yes` in a terminal untested; the test now covers it and a terminal's yes, and fails when the `and not yes` guard is dropped from `init` or `update`.

- **Copilot's review of PR #23**, three findings, each fixed and broken on purpose and caught (five breakages):
  - `testpaths` set inside SWERepo's `pyproject.toml` block count for `ci.tests`;
  - the editors `seamspec init` set up are recorded (`[seamspec] hosts`) only once it succeeds;
  - `[values] commands` and `test_inline` move on only when their file takes the new render.

## Next

- The pull request.
- On the established repository: turn on the dependency graph, commit the `swerepo-setup` branch, open its pull request, and apply the GitHub settings after it merges.
- The `0.1.0` release PR.
