# Progress

What is being built now and next. The log of what each change did is in [progress/](progress/), one file per change (newest first by name). Phases are defined in ADR-20261119-9f87.

## Now

**Phase 0: repository skeleton.** Review closed after 3 rounds ([docs/reviews/phase-0.md](reviews/phase-0.md)). Both SeamSpec rules approved and locked. Bootstrap commit pushed and the ruleset applied; Phase 0 lands through its pull request.

## Next

- **Phase 1:** detection (`detect`), `.swerepo.toml` (`state`), template rendering and normalised fingerprints (`render`).
- **PyPI name:** claimed. The owner published the placeholder `swerepo 0.0.1` on 2026-11-20 (`pypi.org/project/swerepo`, ADR-20261119-d68b). Yank it and delete `tools/pypi-placeholder/` after the first real release (Phase 8).
- **GitHub:** done on 2026-11-20: the organisation is `swerepo` and the empty public repository is `github.com/swerepo/swerepo` (ADR-20261120-1a27); `origin` points to it. Bootstrap commit pushed to `main`; ruleset `swerepo` active on `main` (pull requests only, `ci-ok` required, no force pushes or deletion), applied from `.github/swerepo/ruleset.json`. Still to do: pin the repository on the owner's profile.
- **Owner decision waiting:** the security contact, for `SECURITY.md`. Decided: license Apache-2.0 (ADR-20261119-7384), name SWERepo and hosting `swerepo/swerepo` (ADR-20261120-1a27).
- **Spec gap to settle before Phase 4 (owner decides; developer and reviewer both recommend option a):** SeamSpec's own CI workflow is outside `ci-ok`, so its locked rules wouldn't block a merge in repositories SWERepo sets up. Option (a): `seamspec init --no-ci` and a `seamspec` job inside `swerepo-ci.yml` (with P0-F01's base logic and `spec --check`). Edge cases to record with it: `--only seamspec` without the `ci` component (fall back to `seamspec init --ci`, or warn that nothing runs SeamSpec in CI); `strict` mode expects SeamSpec's own workflow.
- **Notes for later phases from the Phase 0 review:** `detect` must tell tooling folders with their own `pyproject.toml` (like `tools/pypi-placeholder/`) apart from project roots, or this repository looks like a monorepo (Phase 1); `--json` output must bypass Rich's line wrapping and styling, and tests of command output must compare plain text: on GitHub Actions Typer forces Rich's terminal styling (found on PR #1's first CI run) (Phase 2); dependency review job in the generated workflow (Phase 4).

## Phases

| Phase | Scope | Status |
|---|---|---|
| 0 | Skeleton, CI, ADRs, SeamSpec | review closed; landing |
| 1 | Detection, state file, rendering, fingerprints | |
| 2 | `check` | |
| 3 | `init` for `docs` and `agents`; `progress`, `adr` | |
| 4 | `ci` and `security` | |
| 5 | `github`; `threads` | |
| 6 | `update`, merge, `diff`, `status` | |
| 7 | `seamspec` and the hygiene rule pack | |
| 8 | `openspec`, `release`; dogfooding | |
