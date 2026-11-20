# 2026-11-19 · Phase 0: repository skeleton

**Branch:** bootstrap commit on `main`, then `phase-0/skeleton` (ADR-20261119-75e6) · **Review:** [docs/reviews/phase-0.md](../reviews/phase-0.md) (closed after 3 rounds)

## Done

- Git repository; Python package `swerepo` (flat layout, `uv_build`, Typer) with `swerepo --version` and `python -m swerepo`; 6 tests.
- CI workflow `.github/workflows/ci.yml`: lint, tests on 3.11 to 3.14, macOS on `main`, zizmor, SeamSpec, `ci-ok`. SHA-pinned actions.
- ADRs: ADR-20261119-9f87 (phases and peer review), ADR-20261119-6b94 (SeamSpec), ADR-20261119-db50 (packaging and dependencies), ADR-20261119-dd1a (CI), ADR-20261119-75e6 (following the standard by hand).
- `AGENTS.md`, `CLAUDE.md` (imports it), `CONTRIBUTING.md`, `CHANGELOG.md`, `docs/PROGRESS.md`, ADR index and template.
- During the review: Apache-2.0 `LICENSE` (ADR-20261119-7384); hosting decided (ADR-20261119-13fc), project URLs and `.github/CODEOWNERS` added; then the project was renamed from Golden Repo to SWERepo, hosted at `swerepo/swerepo` (ADR-20261120-1a27).
- GitHub repository created (public, empty) at the owner's request, as `goldenrepo-dev/goldenrepo` before the rename; `origin` set to `swerepo/swerepo`. PyPI placeholder `swerepo 0.0.1` published by the owner on 2026-11-20, claiming the name (ADR-20261119-d68b).
- SeamSpec set up by the owner (`--mode enforced --no-ci --hosts none`, plugin for the project). Two day-one rules, approved and locked by the owner on 2026-11-20: inv_62d51113 (privacy, critical), inv_b2000e40 (changelog). `docs/EARNED_SPEC.md` lists both.
- Bootstrap commit (5 files) pushed to `main`; ruleset `swerepo` applied to `main` from `.github/swerepo/ruleset.json` (solo mode, spec §12: pull requests only with 0 approvals, `ci-ok` required, no force pushes or deletion; no Copilot rule yet).
- Both commits simulated in a scratch copy first: the bootstrap commit needs `CHANGELOG.md` (the locked changelog rule runs at every commit), so it has five files; the Phase 0 commit (39 files) passes the hook, and `seamspec doctor --ci` against `main` reports no errors.

- Review (Gemini), 3 rounds, closed 2026-11-20: 8 findings, all fixed; one partial pushback accepted. Fixes: the privacy rule gained the spec's allowances and self-checks; CI's `doctor` uses an explicit base (root commits and multi-commit pushes); `docs/EARNED_SPEC.md` is generated and checked in CI; the bootstrap commit is defined.

## Next

- Owner merges the Phase 0 pull request once `ci-ok` is green.
- Owner pins the repository on their profile; decides the security contact for `SECURITY.md`.
- Phase 1.
