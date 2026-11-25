# 2026-11-24 · Phase 7: the seamspec component and the hygiene rules

**Branch:** `phase-7/seamspec` · **Design:** ADR-20261124-cd64

## Done

- **`swerepo init` for `seamspec`** (`swerepo/seamspec_component.py`, `swerepo/init.py`, `swerepo/cli.py`):
  - **`seamspec init`** runs in the person's terminal only, attached so SeamSpec asks its own questions, never with `--accept-auto-run`. Without a terminal, or with `--yes`, the plan shows the command and the component waits. SWERepo never installs SeamSpec; the plan prints `uv tool install seamspec==<pin>`.
  - **SWERepo's own `seamspec.yml`** (`seamspec/workflow@1`), with actions pinned to commits and the same three steps as `swerepo-ci.yml`'s `seamspec` job, when SeamSpec needs a workflow of its own (no `ci`, or strict mode). SeamSpec's own unpinned one is reported, never replaced.
  - **The hygiene rules**, as versioned templates (`seamspec/hygiene-{privacy,adr-index,changelog,ci-tests}@1`): standard library and pytest only, ruff-clean, proposed with `seamspec propose` and the origin `swerepo:hygiene/<name>@1`, each only with its component, then verified where the clone is trusted. A locked rule of the repository's own is adopted instead (`--adopt NAME=ID`, or a question per rule in a terminal; `[seamspec.adopted]`). A rule the person rejected is never proposed again.
  - **The earned spec** is written after the proposals, and after `seamspec review` when the person takes it in the terminal.
- **`swerepo check` for `seamspec`:** the hygiene rules (locked, adopted, proposed, declined or missing; not yet approved only warns), proposals waiting, strict mode's workflow and CODEOWNERS block. On a person's machine only: the CI pin against the installed SeamSpec, `seamspec doctor --json` (the names of the checks that warn, never the messages, which can hold machine paths) and `spec --check`. With `--ci`, no SeamSpec command at all.
- **`swerepo update --only seamspec`:** a newer SeamSpec installed moves the pin, never back and never to a development build; `ci` is brought along for the pin only; when `swerepo-ci.yml` can't take it, neither `seamspec.yml` nor `[tools] seamspec` moves.
- **`agents/address-review@3`:** ask before resolving review threads (ADR-20261124-023e). Only step 4's line changes: renumbering the steps made a person's notes at the end conflict, which locked rule `inv_60788941` caught.
- **Found on the way:**
  - SeamSpec 0.1.2's `doctor` text counts warnings without saying what they are; `check` reads `--json`.
  - The ADR-index rule's scope follows the repository's ADR folder, so SeamSpec's `doctor` finds its files.
- **Gemini's round 1** (`P7-F01`–`P7-F07`), all fixed with tests (`TestReviewP7`), each checked by breaking it:
  - the pin holds in both directions: when SWERepo's `seamspec.yml` can't take it in strict mode, `swerepo-ci.yml` and `[tools]` don't move either;
  - `seamspec.yml` is written only once SeamSpec is set up or being set up, and always recorded, also on a fresh repository;
  - the earned spec is never written through a link; a repository set up with SeamSpec, on a machine without it, waits instead of failing every run;
  - `hygiene/ci-tests` reads each step (switched-off or masked test steps don't count; `uv run --locked pytest` does) and `.swerepo.toml` is in its scope; `hygiene/privacy` matches `swerepo privacy` (the policy in `.github/` or `docs/`, links and large files skipped);
  - rules without a subject are neither proposed nor reported, the first run follows an adopted ADR folder, and an unpinned `seamspec.yml` is reported in any mode;
  - `[seamspec] initialised` keeps the terminal rerun of `seamspec init` after `update --yes` moved the pin; `update` reports the installed version and `seamspec doctor`.
- **Gemini's round 2** (`P7-F08`–`P7-F10`), fixed with tests: `init` and `update` with `--json` print one JSON object (SeamSpec's lines go into it), and the earned spec is written only when planned; a first `.swerepo.toml` made after `seamspec init` keeps an existing repository's pull-request rules warn-only; an adoption counts before an earlier SWERepo rule the person declined.
- **After SeamSpec's reviewer read the six proposals:**
  - SWERepo finds SeamSpec in one place everywhere: `ci.seamspec_pin` used `shutil.which`, so a locked test could have started failing when SeamSpec was upgraded on the machine.
  - `hygiene/adr-index` counts only each row's own link (an ID in a "SUPERSEDED by" cell no longer hides a missing row).
  - `hygiene/ci-tests` joins folded blocks and continuations, and catches quoted and `${{ }}` forms, `&`, and `ci-ok` itself switched off.
  - A second read found `ci-ok`'s own script unguarded: `hygiene/ci-tests` now requires `ci-ok` to run `if: always()` and to keep a step that reads the jobs' results and can exit non-zero. The other gaps were test coverage: any `--accept-auto-run` form, what `--yes` applies, the review only on a yes, folders' modification times, all four hygiene statuses, whole files byte for byte when the pin doesn't move, a local build, and the adopted ADR folder.
  - The four rules about the component were tightened: through the command line with a terminal, the fake `seamspec` on PATH, `spec --check` really exercised, exit codes checked and each test file run alone, and the strict-mode upgrade moving all three pins together. Each fails on the gap the reviewer named.
- **Tests:** a fake `seamspec` (`tests/fake_seamspec.py`) that logs every call; by default no test reaches a real `seamspec` (`tests/conftest.py`). 32 new tests in `tests/test_seamspec.py`, each protection checked by breaking it on purpose.
- **Dogfooded here:** `seamspec` is a component; `privacy = inv_62d51113` and `changelog = inv_b2000e40` adopted; SWERepo proposed `inv_5c45ea08` (ADR index) and `inv_c78fcca0` (CI tests), verified passing; `docs/agents/address-review.md` at version 3. A second `init` and `update` have nothing to do.
- **SeamSpec:** the owner approved six rules (2026-11-24), so 26 are locked (`docs/EARNED_SPEC.md` regenerated):
  - `inv_c45b7540` (critical): SWERepo never answers SeamSpec's consent, and runs `seamspec init` only in a terminal;
  - `inv_022998a0`: `check` stays read-only with SeamSpec, and with `--ci` runs no SeamSpec command;
  - `inv_4eaaa886`: the bundled hygiene tests use only the standard library and pytest, pass ruff, and pass or fail as they should where `init` set things up;
  - `inv_2f78270e`: `update` moves the SeamSpec pin forward only, and every workflow and `.swerepo.toml` name the same version;
  - `inv_5c45ea08` and `inv_c78fcca0`: the ADR-index and CI-tests hygiene rules on this repository, proposed by SWERepo itself.

- **Copilot's review of PR #20** (six comments, [review](../reviews/phase-7.md)): a recorded `seamspec.yml` keeps taking the pin after `ci` is added; `--no-ci` holds the pin while `swerepo-ci.yml` pins SeamSpec; the pin alone rebuilds the recorded workflow with nothing else of `ci`; `seamspec.yml` isn't written for a Python version standard 1 doesn't know; `hygiene/ci-tests` reads the whole script and needs a reachable failure in `ci-ok`. The stronger `ci-tests` rule is proposed as `inv_11ce8c5b`, with a supersede request for the locked `inv_c78fcca0` waiting for the owner.

## Next

- The owner's decision on the `ci-tests` supersede request (`seamspec review`), then the merge of PR #20.
- Later: strict mode running the locked rules twice with `ci`; shortening the adoption question when a repository has many locked rules (review Q3).
