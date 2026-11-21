# Progress

What is being built now and next. The log of what each change did is in [progress/](progress/), one file per change (newest first by name). Phases are defined in ADR-20261119-9f87.

## Now

**Phase 2: `swerepo check`.** The first real command: a read-only report per component of what the repository meets, misses, has changed or can't tell yet, with `--json`, `--ci`, `--only` and the pull-request rules (`--base`). Review closed after 3 rounds (docs/reviews/phase-2.md); 8 locked rules; merged in PR #3. Copilot's review of PR #3 arrived after the merge; its 8 findings are fixed in a follow-up PR.

## Next

- **Phase 3:** `swerepo init` for the `docs` and `agents` components, with `progress` and `adr`; the per-component shorthand flags (`--docs` for `--only docs`, spec §7).
- **Owner:** pin the repository on your profile; decide the security contact for `SECURITY.md`; delete the merged `phase-0/skeleton` branch on GitHub. Decided so far: license Apache-2.0 (ADR-20261119-7384), name SWERepo and hosting `swerepo/swerepo` (ADR-20261120-1a27).
- **PyPI name:** claimed with the placeholder `swerepo 0.0.1` (ADR-20261119-d68b). Yank it and delete `tools/pypi-placeholder/` after the first real release (Phase 8).
- **Spec gap to settle before Phase 4 (owner decides; developer and reviewer both recommend option a):** SeamSpec's own CI workflow is outside `ci-ok`, so its locked rules wouldn't block a merge in repositories SWERepo sets up. Option (a): `seamspec init --no-ci` and a `seamspec` job inside `swerepo-ci.yml` (with P0-F01's base logic and `spec --check`). Edge cases to record with it: `--only seamspec` without the `ci` component (fall back to `seamspec init --ci`, or warn that nothing runs SeamSpec in CI); `strict` mode expects SeamSpec's own workflow.
- **From the Phase 1 review:** `init --projects` lets a real project under `tools/` or `examples/` override the default non-project folders (Phase 3).
- **Notes for later phases:** fingerprinting merged TOML sections (ADR-20261120-9495) and dependency review in the generated workflow (Phase 4); a SeamSpec rule locking released templates (Phase 8).

## Phases

| Phase | Scope | Status |
|---|---|---|
| 0 | Skeleton, CI, ADRs, SeamSpec | done ([PR #1](https://github.com/swerepo/swerepo/pull/1), [review](reviews/phase-0.md)) |
| 1 | Detection, state file, rendering, fingerprints | done ([PR #2](https://github.com/swerepo/swerepo/pull/2), [review](reviews/phase-1.md)) |
| 2 | `check` | in review |
| 3 | `init` for `docs` and `agents`; `progress`, `adr` | |
| 4 | `ci` and `security` | |
| 5 | `github`; `threads` | |
| 6 | `update`, merge, `diff`, `status` | |
| 7 | `seamspec` and the hygiene rule pack | |
| 8 | `openspec`, `release`; dogfooding | |
