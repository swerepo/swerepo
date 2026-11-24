# Progress

What is being built now and next. The log of what each change did is in [progress/](progress/), one file per change (newest first by name). Phases are defined in ADR-20261119-9f87.

## Now

**Secrets caught before a push:** `swerepo hook install` adds a pre-push privacy hook (ADR-20261123-24e0), so a key, a personal email address or a home-folder path is refused before it reaches GitHub. SWERepo sets up this repository's GitHub settings itself since [PR #11](https://github.com/swerepo/swerepo/pull/11); 16 SeamSpec rules in force.

## Next

- **Owner, on GitHub:** secret scanning and push protection are on (2026-11-23); Dependabot security updates are still off (Settings → Advanced Security).
- **Phase 6:** `update`, three-way merge, `diff`, `status`. Also: explain `delete_branch_on_merge` in `init`'s plan, or ask about it, for teams that keep merged branches (release branches merged by pull request would be deleted); today it is changed by editing `repo-settings.json` (owner, 2026-11-23: keep it on here).
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
| 5 | `github`; `threads` | done ([PR #10](https://github.com/swerepo/swerepo/pull/10), [review](reviews/phase-5.md)); applied here (ADR-20261123-e2f8) |
| 6 | `update`, merge, `diff`, `status` | |
| 7 | `seamspec` and the hygiene rule pack | |
| 8 | `openspec`, `release`; dogfooding | |
