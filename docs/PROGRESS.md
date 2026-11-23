# Progress

What is being built now and next. The log of what each change did is in [progress/](progress/), one file per change (newest first by name). Phases are defined in ADR-20261119-9f87.

## Now

**Phase 4 built and reviewed:** `init` for `ci` and `security`, and `check` for both (ADR-20261122-4a06, ADR-20261122-a48e). Review closed after 3 rounds ([phase-4](reviews/phase-4.md)); 13 SeamSpec rules in force. Pull request next.

## Next

- **After Phase 4 merges:** apply `ci` and `security` to this repository (its hand-written `ci.yml` replaced by `swerepo-ci.yml`, `SECURITY.md` pointing to private vulnerability reporting), as PR #7 did for `docs` and `agents`. Private vulnerability reporting is already on (2026-11-23).
- **Phase 5:** `github` (ruleset, merge settings, CODEOWNERS, Copilot instructions) and `swerepo threads`; secret scanning reported by `check`. Open question for its spec: make merges wait until Copilot's review has arrived.
- **Owner:** pin the repository on your profile; delete the merged `phase-0/skeleton` branch on GitHub. Decided so far: license Apache-2.0 (ADR-20261119-7384), name SWERepo and hosting `swerepo/swerepo` (ADR-20261120-1a27), SeamSpec inside `swerepo-ci.yml` and private vulnerability reporting (2026-11-22).
- **PyPI name:** claimed with the placeholder `swerepo 0.0.1` (ADR-20261119-d68b). Yank it and delete `tools/pypi-placeholder/` after the first real release (Phase 8).
- **Notes for later phases:** `--only seamspec` without `ci` and SeamSpec's `strict` mode (Phase 7, ADR-20261122-4a06 point 1); Poetry projects in the CI template; the `[pr] skip_progress_label` input; `adr new` cutting slugs at a word boundary; a SeamSpec rule locking released templates (Phase 8).

## Phases

| Phase | Scope | Status |
|---|---|---|
| 0 | Skeleton, CI, ADRs, SeamSpec | done ([PR #1](https://github.com/swerepo/swerepo/pull/1), [review](reviews/phase-0.md)) |
| 1 | Detection, state file, rendering, fingerprints | done ([PR #2](https://github.com/swerepo/swerepo/pull/2), [review](reviews/phase-1.md)) |
| 2 | `check` | done ([PR #3](https://github.com/swerepo/swerepo/pull/3), [review](reviews/phase-2.md); Copilot fixes in [PR #4](https://github.com/swerepo/swerepo/pull/4)) |
| 3 | `init` for `docs` and `agents`; `progress`, `adr` | done ([PR #6](https://github.com/swerepo/swerepo/pull/6), [review](reviews/phase-3.md)); applied here (ADR-20261121-d0f5) |
| 4 | `ci` and `security` | review closed ([review](reviews/phase-4.md)); pull request next |
| 5 | `github`; `threads` | |
| 6 | `update`, merge, `diff`, `status` | |
| 7 | `seamspec` and the hygiene rule pack | |
| 8 | `openspec`, `release`; dogfooding | |
