# Progress

What is being built now and next. The log of what each change did is in [progress/](progress/), one file per change (newest first by name). Phases are defined in ADR-20261119-9f87.

## Now

**Phase 5 reviewed, pull request next:** `init` for `github`, `swerepo threads`, and `check` reading GitHub (ADR-20261123-4e40); merges wait for Copilot's review (ADR-20261123-a359). Review: [closed, 4 rounds](reviews/phase-5.md); 15 SeamSpec rules locked. This repository runs its own generated CI since [PR #9](https://github.com/swerepo/swerepo/pull/9).

## Next

- **After Phase 5 merges:** apply `github` to this repository in its own pull request, with the owner's choices (2026-11-23): `solo` mode, the owner's login as code owner, squash-only merging. Its existing ruleset `swerepo` is adopted.
- **Owner, on GitHub:** secret scanning and push protection are off for this repository (`check` reports it; free on public repositories).
- **Phase 6:** `update`, three-way merge, `diff`, `status`.
- **Owner:** pin the repository on your profile; delete the merged `phase-0/skeleton` branch on GitHub. Decided so far: license Apache-2.0 (ADR-20261119-7384), name SWERepo and hosting `swerepo/swerepo` (ADR-20261120-1a27), SeamSpec inside `swerepo-ci.yml` and private vulnerability reporting (2026-11-22); `solo` mode, own login as code owner, squash only, merges wait for Copilot (2026-11-23).
- **PyPI name:** claimed with the placeholder `swerepo 0.0.1` (ADR-20261119-d68b). Yank it and delete `tools/pypi-placeholder/` after the first real release (Phase 8).
- **Notes for later phases:** `GitHub.find_ruleset` reads only the first 100 rulesets (read every page); `--only seamspec` without `ci` and SeamSpec's `strict` mode (Phase 7, ADR-20261122-4a06 point 1); Poetry projects in the CI template; the `[pr] skip_progress_label` input; `adr new` cutting slugs at a word boundary; a SeamSpec rule locking released templates (Phase 8).

## Phases

| Phase | Scope | Status |
|---|---|---|
| 0 | Skeleton, CI, ADRs, SeamSpec | done ([PR #1](https://github.com/swerepo/swerepo/pull/1), [review](reviews/phase-0.md)) |
| 1 | Detection, state file, rendering, fingerprints | done ([PR #2](https://github.com/swerepo/swerepo/pull/2), [review](reviews/phase-1.md)) |
| 2 | `check` | done ([PR #3](https://github.com/swerepo/swerepo/pull/3), [review](reviews/phase-2.md); Copilot fixes in [PR #4](https://github.com/swerepo/swerepo/pull/4)) |
| 3 | `init` for `docs` and `agents`; `progress`, `adr` | done ([PR #6](https://github.com/swerepo/swerepo/pull/6), [review](reviews/phase-3.md)); applied here (ADR-20261121-d0f5) |
| 4 | `ci` and `security` | done ([PR #8](https://github.com/swerepo/swerepo/pull/8), [review](reviews/phase-4.md)); applied here (ADR-20261123-d27b) |
| 5 | `github`; `threads` | reviewed ([review](reviews/phase-5.md)); pull request next |
| 6 | `update`, merge, `diff`, `status` | |
| 7 | `seamspec` and the hygiene rule pack | |
| 8 | `openspec`, `release`; dogfooding | |
