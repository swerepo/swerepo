# 2026-11-24 · Phase 8 design: a native SPEC.md, six components, and SWERepo's own release

**Branch:** `phase-8/design`

## Done

- **ADR-20261124-4d76, a native `SPEC.md` instead of OpenSpec** (the owner's choice, 2026-11-24):
  - `docs` writes a starter `SPEC.md` or adopts an existing spec (`SPEC.md`, `docs/SPEC.md`, `<PROJECT>-SPEC.md`) as `[adopted] spec`; this repository adopts `SWEREPO-SPEC.md`;
  - the rule that a change to behaviour, CLI flags, APIs or configuration updates the spec goes into the agents block, `prepare-pr.md`, a new `update-spec.md` runbook and the PR template;
  - `check` looks only for the file (`docs.spec`): no `--base` rule and no `Spec: none` trailer, so refactors and bug fixes raise no warnings;
  - the spec stays out of the CODEOWNERS block;
  - two-tier specs for multi-service monorepos are planned for v0.2, Phase 10.
- **OpenSpec's public docs, checked first** (README and openspec.dev, never its code): Node.js 22.20, skills in the home folder by default, old marker blocks removed from `CLAUDE.md` and `AGENTS.md` without asking, and usage statistics on by default.
- **ADR-20261124-152d, six components:** `openspec` and `release` leave the code and the spec; SWERepo never sets up package publishing.
- **ADR-20261124-4699, SWERepo's own release:** `release.yml` in this repository only. A `v*` tag runs `check`, `test`, `build` (with provenance), `publish` (the approved artifact, through trusted publishing, after the owner's approval in the `pypi` environment) and `github-release`. The trusted-publisher values for pypi.org are in the ADR.
- **ADR-20261124-41e9, two rules to propose in the implementation PR:** nothing outside `swerepo/` in the wheel and no publishing in the code; released templates never change, checked against every `v*` tag, with CI fetching tags.
- **Spec v0.16:** §1, §3, §5, §6, §6.1, §6.5, §6.6, §6.7 (now `SPEC.md`), §6.8, §6.9 (removed), §7, §8, §9, §10, §11, §14 (now `SPEC.md`), §15, §18, §19.6, §19.10, §20, §21, Appendices A and B.
- **Gemini's design review, round 0** (`CODE_REVIEW.md`, `P8-D01` to `P8-D09`), all fixed in the ADRs and the spec:
  - the release workflow: an explicit job graph with per-job permissions, a check that the tag is on `main`, checksums between `build` and `publish`, a `github-release` job without a checkout, and `setup-uv` uncached everywhere for zizmor;
  - how the spec is found when there are none, one or several candidates (several: listed, the owner records one);
  - a supersede of `inv_9265607a`, planned for the implementation PR, so its test finds the latest `agents/block` version;
  - tests made independent of the package's own version, and `uv lock` with the version bump;
  - Rule 1 building the wheel in its own process with `uv_build`; Rule 2 also covering the renders built in Python, git worktrees, and `seamspec.yml` fetching tags;
  - Copilot's instructions and CONTRIBUTING mentioning the spec;
  - the remaining `openspec` and `release` touchpoints;
  - the README rewritten for PyPI in the release PR;
  - a `v*` tag ruleset on this repository (no deletion, force-push or move).
- **Round 1:** Gemini accepted all nine, the pushback included, and raised `P8-D10`, fixed: each release's snapshot of the renders built in code is required, and checked before its tag freezes it; `release.yml` runs the locked rules at the tag.
- **Round 2:** Gemini accepted `P8-D10`; the design review is closed (`P8-D01` to `P8-D10` fixed and accepted). `CODE_REVIEW.md` stays open for the implementation review (`P8-F<nn>`).
- **`docs/PROGRESS.md`:** Phase 7 done ([PR #20](https://github.com/swerepo/swerepo/pull/20)), Phase 8 designed.

## Next

- Build Phase 8 as the four ADRs decide, then Gemini's review.
