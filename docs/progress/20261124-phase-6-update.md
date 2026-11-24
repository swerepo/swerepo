# 2026-11-24 · Phase 6: swerepo update, merge, diff and status

**Branch:** `phase-6/update` · **Review:** [docs/reviews/phase-6.md](../reviews/phase-6.md) (closed, 3 rounds)

## Done

- **Owner decisions** (2026-11-24):
  - action pins: option A with three guards (ADR-20261123-f571);
  - merging into a person's edits needs a terminal yes or `--yes --merge`; Dependabot's pins alone need `--yes` only;
  - removed items are reported, never deleted; released templates are locked in Phase 8; `init` keeps saying "run swerepo update";
  - each record keeps the inputs its render used, and older records get them before `[values]` moves on.
- **`swerepo update`** (`-u`; ADR-20261124-7afa): `init`'s planner with the update verbs.
  - **Untouched and outdated:** rewritten with the new render.
  - **Edited by a person:** merged with `merge.merge3` against the earlier render, rebuilt from the record's `inputs` and trusted only when it matches `rendered`. The merge is shown as a diff. A conflict, or an earlier render that can't be rebuilt, leaves the file as it is.
  - **No longer in the standard, or no longer chosen:** reported and kept, never deleted.
  - `--only`, shorthand flags, `--dry-run`, `--yes`, `--merge`, `--json`, `--enforce-pr-rules`.
- **The three-way merge** (`swerepo/merge.py`): action pins settled line by line on all three sides first (never backwards; one version on two commits is a conflict; a pin the person lowered is their edit), then `git merge-file`. No conflict markers are ever written. CRLF files keep CRLF.
- **Rebuilding a render** (`swerepo/rebuild.py`): plain templates from the values they used; the CI workflow, the pyproject block and the GitHub settings from the few inputs they were built from.
- **`.swerepo.toml`:** each record gets an `inputs` table; older records are backfilled when their inputs, or `[values]` as recorded before the run, rebuild the recorded render. `update` renders with the project's current commands, which `init` only notes.
- **`swerepo diff [FILE ...]`** and **`swerepo status [--json]`**: read only.
- **`swerepo check`:** a workflow that differs only by newer action pins is current (`(current, newer action pins)`).
- **Smaller:** `GitHub.find_ruleset` reads every page of rulesets; `init`'s plan explains `delete_branch_on_merge` when it creates `repo-settings.json`.
- **Dogfooded here:** `swerepo update` rewrote the AGENTS.md block and `docs/agents/address-review.md` to version 2 and backfilled `inputs` on all 12 records; a second run has nothing to do; `check` and `status` report everything current.
- **Review:** Gemini's early review of the merge (`M6-F01`–`M6-F04`) is fixed with tests. Round 1 (`P6-F01`–`P6-F07`): all seven fixed with tests: merged JSON and TOML checked before writing, and the merged settings are what GitHub gets; the ADR index kept; Dependabot's pins current in `check`, `status` and `update` alike; older records backfilled before a partial run moves `[values]`; check names with commas; `update` follows `requires-python` and SWERepo's released pin; `diff` shows what can't be merged, and `diff` and `status` never call GitHub. Round 2 (`P6-F08`): `update --only github` no longer applies `ci`'s own updates. Gemini signed off in round 3. Spec v0.14.
- **The two-commit check:** `merge._settle` also conflicts when two lines of the person's file pin one version to two commits (found while tightening `inv_d60ffffd`).
- **SeamSpec:** the owner approved three critical rules (2026-11-24), so 20 are locked (`docs/EARNED_SPEC.md` regenerated). They were tightened twice after SeamSpec's reviewer before approval. The owner also accepted decision ADR-20261124-b9d7 (the pins decision as built) and rejected the older ADR-20261123-5e14:
  - `inv_60788941`: `update` changes an edited file only with a deliberate yes, never writes conflict markers, and never merges against an earlier render it can't rebuild;
  - `inv_d60ffffd`: `update` never moves an action pin backwards or guesses between two commits for one version, and Dependabot's pins alone need no `--merge`;
  - `inv_9265607a`: `update --dry-run` writes nothing, `update` writes only SWERepo's files and `.swerepo.toml`, and a second `update` writes nothing.

## Next

- The pull request for Phase 6.
- Deferred: a template that lowers a pin between versions (Phase 8, with the rule locking released templates); the standard's changelog (with the first standard 2 change).
