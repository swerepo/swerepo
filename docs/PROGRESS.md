# Progress

What is being built now and next. The log of what each change did is in [progress/](progress/), one file per change (newest first by name). Phases are defined in ADR-20261119-9f87.

## Now

**Phase 8, reviewed:** the last phase of v0.1 (the owner's decisions, 2026-11-24; design in [PR #21](https://github.com/swerepo/swerepo/pull/21)):
- a native `SPEC.md` kept by `docs` and `agents` instead of OpenSpec (ADR-20261124-4d76);
- standard 1 with six components, `openspec` and `release` removed, since SWERepo never sets up package publishing (ADR-20261124-152d);
- SWERepo's own release workflow, in this repository only (ADR-20261124-4699);
- two rules guarding the shipped package (ADR-20261124-41e9).

Before that: Phase 7, the `seamspec` component and the hygiene rules ([PR #20](https://github.com/swerepo/swerepo/pull/20)). 30 SeamSpec rules are in force.

## Next

- **Owner, on GitHub:** secret scanning and push protection are on (2026-11-23); Dependabot security updates are still off (Settings → Advanced Security).
- **Dogfooding** on an established repository (ADR-20261125-5f22): a codebase never linted moves to ruff gradually, a project without tests is warned and agents are told to write a real one, `--editors`, GitHub's settings applied only when asked for by name (`--apply-github`), a table appended inside SWERepo's `pyproject.toml` block named and left alone, and `check`'s "Next:" naming what fixes each gap. Pull request next.
- **Two `check` gaps from dogfooding** (ADR-20261126-a7ce, review P8-K): the CI tools `uv sync` won't install (`ci.tools`, a warning) and code owners GitHub doesn't know (`github.code-owner`; `init` refuses them). Built on `phase-8/check-gaps`; Gemini's code review, then the pull request.
- **Phase 8, in order:**
  1. the implementation PR (the native `SPEC.md`, removing `openspec` and `release`, the refreshed `docs`, `agents` and `github` templates applied here, `release.yml`, and the two rules), with Gemini's review;
  2. dogfooding `check` and `init` on an established repository of the owner's;
  3. the `0.1.0` release PR;
  4. the owner's tag and approval, and the PyPI publish;
  5. a cleanup PR: `0.0.1` yanked and `tools/pypi-placeholder/` removed.
- **Owner:** pin the repository on your profile; delete the merged `phase-0/skeleton` branch on GitHub. Decided so far: license Apache-2.0 (ADR-20261119-7384), name SWERepo and hosting `swerepo/swerepo` (ADR-20261120-1a27), SeamSpec inside `swerepo-ci.yml` and private vulnerability reporting (2026-11-22); `solo` mode, own login as code owner, squash only, merges wait for Copilot (2026-11-23).
- **PyPI name:** claimed with the placeholder `swerepo 0.0.1` (ADR-20261119-d68b). Before the release, the owner adds the trusted publisher on pypi.org (ADR-20261124-4699); after it, yanks `0.0.1`.
- **Notes for later phases:** strict mode running the locked rules twice with `ci` (v0.2, ADR-20261124-cd64 point 3); Poetry projects in the CI template (Phase 11); the `[pr] skip_progress_label` input; `adr new` cutting slugs at a word boundary.

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
| 7 | `seamspec` and the hygiene rule pack | done ([PR #20](https://github.com/swerepo/swerepo/pull/20), [review](reviews/phase-7.md)) |
| 8 | native `SPEC.md`; six components (no `openspec`, no `release`); this repository's release workflow and rules; dogfooding; `0.1.0` | reviewed ([review](reviews/phase-8.md); design: [PR #21](https://github.com/swerepo/swerepo/pull/21)); pull request next |
| | **v0.2** (ADR-20261124-2452) | |
| 9 | Enterprise multi-branch governance: `develop` and `release` protected, `--protected-branches`, squash and merge commits | |
| 10 | Multi-service monorepos and federated ADRs: `adr new --scope`, two-tier ADRs | |
| 11 | Broader Python and ergonomics for agents: Poetry, `requirements.txt`, `--typecheck`, `progress new`, changelog fragments, `--pr`, editor wrappers | |
| 12 | TypeScript and polyglot monorepos; SeamSpec's OpenSpec importer | |
