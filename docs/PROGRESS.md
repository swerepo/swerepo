# Progress

What is being built now and next. The log of what each change did is in [progress/](progress/), one file per change (newest first by name). Phases are defined in ADR-20261119-9f87.

## Now

**Phase 7, designed:** the `seamspec` component (ADR-20261124-cd64): SeamSpec set up by its own command in the person's terminal, never installed or consented for them; its own workflow pinned when one is needed; the four hygiene rules proposed, or adopted where a locked rule already covers one. v0.2 is planned as Phases 9 to 12 (ADR-20261124-2452). Before that: Phase 6, `swerepo update` with the three-way merge, `diff` and `status` ([PR #18](https://github.com/swerepo/swerepo/pull/18)); 20 SeamSpec rules in force.

## Next

- **Owner, on GitHub:** secret scanning and push protection are on (2026-11-23); Dependabot security updates are still off (Settings → Advanced Security).
- **Phase 7:** build the `seamspec` component as ADR-20261124-cd64 decides, with `agents/address-review@3` (ask before resolving threads, ADR-20261124-023e); dogfood it here (adopt `inv_62d51113` and `inv_b2000e40`, propose the ADR-index and CI-tests rules); Gemini's review.
- **Owner:** pin the repository on your profile; delete the merged `phase-0/skeleton` branch on GitHub. Decided so far: license Apache-2.0 (ADR-20261119-7384), name SWERepo and hosting `swerepo/swerepo` (ADR-20261120-1a27), SeamSpec inside `swerepo-ci.yml` and private vulnerability reporting (2026-11-22); `solo` mode, own login as code owner, squash only, merges wait for Copilot (2026-11-23).
- **PyPI name:** claimed with the placeholder `swerepo 0.0.1` (ADR-20261119-d68b). Yank it and delete `tools/pypi-placeholder/` after the first real release (Phase 8).
- **Notes for later phases:** strict mode running the locked rules twice with `ci` (after Phase 7, ADR-20261124-cd64 point 3); Poetry projects in the CI template (Phase 11); the `[pr] skip_progress_label` input; `adr new` cutting slugs at a word boundary; a SeamSpec rule locking released templates (Phase 8).

## Phases

| Phase | Scope | Status |
|---|---|---|
| 0 | Skeleton, CI, ADRs, SeamSpec | done ([PR #1](https://github.com/swerepo/swerepo/pull/1), [review](reviews/phase-0.md)) |
| 1 | Detection, state file, rendering, fingerprints | done ([PR #2](https://github.com/swerepo/swerepo/pull/2), [review](reviews/phase-1.md)) |
| 2 | `check` | done ([PR #3](https://github.com/swerepo/swerepo/pull/3), [review](reviews/phase-2.md); Copilot fixes in [PR #4](https://github.com/swerepo/swerepo/pull/4)) |
| 3 | `init` for `docs` and `agents`; `progress`, `adr` | done ([PR #6](https://github.com/swerepo/swerepo/pull/6), [review](reviews/phase-3.md)); applied here (ADR-20261121-d0f5) |
| 4 | `ci` and `security` | done ([PR #8](https://github.com/swerepo/swerepo/pull/8), [review](reviews/phase-4.md)); applied here (ADR-20261123-d27b) |
| 5 | `github`; `threads` | done ([PR #10](https://github.com/swerepo/swerepo/pull/10), [review](reviews/phase-5.md)); applied here (ADR-20261123-e2f8) |
| 6 | `update`, merge, `diff`, `status` | done ([PR #18](https://github.com/swerepo/swerepo/pull/18), [review](reviews/phase-6.md)) |
| 7 | `seamspec` and the hygiene rule pack | designed (ADR-20261124-cd64) |
| 8 | `openspec`, `release`; dogfooding | |
| | **v0.2** (ADR-20261124-2452) | |
| 9 | Enterprise multi-branch governance: `develop` and `release` protected, `--protected-branches`, squash and merge commits | |
| 10 | Multi-service monorepos and federated ADRs: `adr new --scope`, two-tier ADRs | |
| 11 | Broader Python and ergonomics for agents: Poetry, `requirements.txt`, `--typecheck`, `progress new`, changelog fragments, `--pr`, editor wrappers | |
| 12 | TypeScript and polyglot monorepos; SeamSpec's OpenSpec importer | |
