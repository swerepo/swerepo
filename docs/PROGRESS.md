# Progress

What is being built now and next. The log of what each change did is in [progress/](progress/), one file per change (newest first by name). Phases are defined in ADR-20261119-9f87.

## Now

**Phase 1: foundation.** Fingerprints and marked blocks, the template store and renderer, the `.swerepo.toml` state module, and read-only project detection. No new commands yet: Phase 2's `check` is the first user of all four. Review closed after 3 rounds ([docs/reviews/phase-1.md](reviews/phase-1.md)). The owner approved the four earned SeamSpec rules (6 locked in all). Left: the pull request.

## Next

- **Phase 2:** `swerepo check` (read-only), including `--base`, `--json` and `--ci`, built on Phase 1's modules.
- **Owner:** pin the repository on your profile; decide the security contact for `SECURITY.md`; delete the merged `phase-0/skeleton` branch on GitHub. Decided so far: license Apache-2.0 (ADR-20261119-7384), name SWERepo and hosting `swerepo/swerepo` (ADR-20261120-1a27).
- **PyPI name:** claimed with the placeholder `swerepo 0.0.1` (ADR-20261119-d68b). Yank it and delete `tools/pypi-placeholder/` after the first real release (Phase 8).
- **Spec gap to settle before Phase 4 (owner decides; developer and reviewer both recommend option a):** SeamSpec's own CI workflow is outside `ci-ok`, so its locked rules wouldn't block a merge in repositories SWERepo sets up. Option (a): `seamspec init --no-ci` and a `seamspec` job inside `swerepo-ci.yml` (with P0-F01's base logic and `spec --check`). Edge cases to record with it: `--only seamspec` without the `ci` component (fall back to `seamspec init --ci`, or warn that nothing runs SeamSpec in CI); `strict` mode expects SeamSpec's own workflow.
- **From the Phase 1 review:** in `check`, treat nested repositories as "wrong folder" only when the folder isn't itself a git work tree (submodules and worktrees are normal) (Phase 2); `init --projects` lets a real project under `tools/` or `examples/` override the default non-project folders (Phase 3).
- **Notes for later phases:** `--json` output must bypass Rich's line wrapping and styling, and tests of command output must compare plain text: on GitHub Actions Typer forces Rich's terminal styling (PR #1) (Phase 2); fingerprinting merged TOML sections (ADR-20261120-9495) and dependency review in the generated workflow (Phase 4); a SeamSpec rule locking released templates (Phase 8).

## Phases

| Phase | Scope | Status |
|---|---|---|
| 0 | Skeleton, CI, ADRs, SeamSpec | done ([PR #1](https://github.com/swerepo/swerepo/pull/1), [review](reviews/phase-0.md)) |
| 1 | Detection, state file, rendering, fingerprints | review closed; landing |
| 2 | `check` | |
| 3 | `init` for `docs` and `agents`; `progress`, `adr` | |
| 4 | `ci` and `security` | |
| 5 | `github`; `threads` | |
| 6 | `update`, merge, `diff`, `status` | |
| 7 | `seamspec` and the hygiene rule pack | |
| 8 | `openspec`, `release`; dogfooding | |
