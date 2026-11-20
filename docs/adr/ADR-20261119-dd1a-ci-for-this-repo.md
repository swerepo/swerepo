---
id: ADR-20261119-dd1a
title: CI for this repository, with a single required check
status: ACCEPTED
date: 2026-11-19
scopes: [".github/workflows/ci.yml"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261119-dd1a: CI for this repository, with a single required check

## Context

SWERepo will generate `swerepo-ci.yml` for other repositories (spec §6.2, Phase 4). This repository needs CI now, before that exists, and it should already follow the same pattern so the generated workflow is dogfooded in spirit from day one. There is no GitHub repository yet (spec §19.2), so the workflow can't run until the owner creates one.

## Decision

`.github/workflows/ci.yml`, written by hand:

1. **Jobs:** `lint` (ruff check and format check); `test` (pytest on Python 3.11 to 3.14, Linux); `test-macos` (pushes to `main` only); `workflow-audit` (zizmor, pinned, through `uvx`); `seamspec` (`doctor --ci` and `verify --all --ci`, ADR-20261119-6b94); and **`ci-ok`**, which a ruleset will require.
2. **`ci-ok`** runs with `if: always()` and passes only if every job succeeded, or was skipped by design (only `test-macos` on pull requests). A failed or cancelled job fails it.
3. **Hardening:** actions pinned to full commit SHAs with the version in a comment; `permissions: contents: read`; `persist-credentials: false` on checkout; `concurrency` cancelling superseded PR runs; `timeout-minutes` on every job; uv pinned to 0.9.28 to match the `uv_build` pin; `uv sync --locked`.
4. **SeamSpec job:** `doctor --ci` compares the ledger with an explicit base: the PR's base branch on pull requests; on pushes, `github.event.before` (every commit the push brought) when it exists, else `HEAD~1`, else `HEAD` for a root commit. SeamSpec's own default (`HEAD~1`) misses earlier commits of a multi-commit push and fails on a root commit (review finding P0-F01). Then `verify --all --ci` and `spec --check docs/EARNED_SPEC.md`. The same base logic goes into the generated `swerepo-ci.yml` (Phase 4/7).
5. **Named `ci.yml`, not `swerepo-ci.yml`.** When SWERepo can generate its CI (Phase 4), it is run on this repository and the hand-written file is replaced in that PR. Keeping a different name now avoids this file being mistaken for one SWERepo wrote.
6. **Not yet included:** the `governance` job (needs `swerepo check`, Phase 2/4), the privacy workflow (Phase 4; the SeamSpec privacy rule covers it until then), dependency review (with the generated workflow in Phase 4; the repository is public from the first push, ADR-20261119-13fc).

**Alternatives considered:**
- **Wait for Phase 4 to add CI.** Phases 1 to 3 would have no CI once the repository is on GitHub.
- **Tags instead of SHAs.** Tags can be moved; the spec requires SHA pins for generated workflows, and this repository should meet its own standard.

## Enforced Invariants

None yet. Spec §6.8 rule 4 ("CI still runs the tests and `ci-ok` depends on them") is proposed here in Phase 7.

## Consequences

- Actions need deliberate updates; Dependabot (Phase 5) will open PRs for them.
- macOS problems surface only after merging to `main`; acceptable for the cost saving (spec §6.2).
