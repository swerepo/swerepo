# 2026-11-22 · Phase 4: swerepo init for ci and security

**Branch:** `phase-4/ci-security` · **Review:** [docs/reviews/phase-4.md](../reviews/phase-4.md) (closed, 3 rounds)

## Done

- Owner decisions: SeamSpec's locked rules run inside `swerepo-ci.yml` (option a), and SWERepo's `SECURITY.md` points to GitHub's private vulnerability reporting. On 2026-11-23 the owner confirmed the `seamspec` job stays in every workflow, passing when SeamSpec isn't set up.
- `swerepo init` for `ci` (`swerepo/ci.py`, ADR-20261122-4a06): `swerepo-ci.yml` from version-1 templates composed at one version number, with lint, tests on the declared Python versions, macOS on pushes, zizmor, an always-present `seamspec` job, dependency review on public repositories, `governance` (pinned, own checkout, or `--with-governance`), per-project jobs for `--projects`, and a `ci-ok` that checks each job's result. ruff and pytest settings as a marked block at the end of `pyproject.toml`. Kept linters (with `.seamspec` excluded) or a gradual move to ruff, asked in a terminal.
- `swerepo init` for `security` (`swerepo/privacy.py`, ADR-20261122-a48e): `SECURITY.md` with the contact asked for, `swerepo-privacy.yml`, a `.gitignore` block, and the privacy scan run once in the plan.
- `swerepo check`: the Python matrix, `ci-ok` waiting for every job, monorepo coverage, kept linters and `.seamspec`, the privacy scan (by file and line only).
- Spec v0.10. Three rules locked by the owner on 2026-11-23, after SeamSpec's reviewer asked for stronger tests (13 in force): `inv_ab57c6ff` (the privacy scan reports where, never what; critical), `inv_09cc1c20` (ci-ok waits for every job and fails on any wrong result; critical) and `inv_2c3b6053` (CI tests exactly the declared Python versions). `docs/EARNED_SPEC.md` regenerated.
- Gemini's round 1 (3 blockers, 4 should-fix, 2 suggestions), all reproduced and fixed: installs in uv workspaces, workflows rewritten when asked for later with their inputs kept in step (each workflow records its own SWERepo command), recorded values checked before they reach a workflow, per-project linters, git-style globs and every policy place in the privacy scan, three `check` fixes, matching lint commands for `gradual`, current token formats, and `--` in the gradual lint step. Both proposed rules marked critical.
- Gemini's round 2: all nine accepted; two new findings fixed with one shared glob matcher (`swerepo/globs.py`): uv workspace globs that crashed `Path.glob`, and `allow_paths` globs that backtracked exponentially.
- Gemini's round 3: nothing new; all 11 findings accepted; the review closed.
- Copilot's review of PR #8 (8 threads), all reproduced and fixed: comment lines in `jobs:`, reserved job names, each project's test matrix checked, tools counted only when `uv sync` installs them, a Python snapshot per workflow, missing tools named per project, each project's inputs recorded, and a Google key ending in `-`.
- 510 tests (121 new); the generated workflows pass zizmor.

## Next

- Pull request for Phase 4; wait for Copilot's review before merging.
- Then apply `ci` and `security` to this repository in its own pull request. Private vulnerability reporting is already on for `swerepo/swerepo` (turned on with `gh` at the owner's request, 2026-11-23).
