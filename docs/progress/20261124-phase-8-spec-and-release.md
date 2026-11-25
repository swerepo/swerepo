# 2026-11-24 · Phase 8: a native SPEC.md, six components, and SWERepo's own release workflow

**Branch:** `phase-8/spec-and-release`

## Done

- **Six components** (ADR-20261124-152d): `openspec` and `release` are gone from `state`, `standard`, `detect`, `check`, `init`, `cli` and `github.codeowners_lines`, with `AVAILABLE`, `LATER` and the `later` plan verb. Naming either is wrong usage (exit 2).
- **The spec** (ADR-20261124-4d76):
  - `swerepo/spec.py` finds it in five steps: `[adopted] spec`; else the root `SPEC.md`, `docs/SPEC.md` and root `*-SPEC.md` candidates; none gets the starter `SPEC.md` (`docs/spec@1`), one is followed (recorded unless it is `SPEC.md`), several are listed;
  - `init` and `update` record `[adopted] spec`; `check` reports `docs.spec`.
- **New template versions** carrying the spec rule:
  - `agents/block@3` (rule 10) and `agents/prepare-pr@2`;
  - a new `agents/update-spec@1` runbook;
  - `github/pr-template@2`, `github/copilot-instructions@2` and `docs/contributing@2`.
- **Tests independent of SWERepo's own version** (P8-D03): an `unreleased` fixture for the six tests that assumed a development build. The whole suite passes with the version simulated as `0.1.0`.
- **`fetch-tags: true`** in `ci/workflow@2` and `seamspec/workflow@1` (both unreleased, changed in place).
- **`.github/workflows/release.yml`** for this repository only (ADR-20261124-4699): `check` (tag on `main`, version, dated changelog, locked rules), `test`, `build` (`SHA256SUMS`, provenance), `publish` (the `pypi` environment, checked files, trusted publishing) and `github-release` (no checkout). zizmor reports nothing.
- **`tools/released_snapshot.py`** writes each release's `tests/released/<version>.json`.
- **Dogfooded here** with `swerepo update`: `[adopted] spec = "SWEREPO-SPEC.md"`, the five new template versions, `update-spec.md` and `fetch-tags`. A second `update` has nothing to do.
- **SeamSpec**, all waiting for the owner's review:
  - `inv_3f05e701`: the shipped package has no publishing footprint (`uv_build` joins the dev group, so the wheel is built in-process);
  - `inv_7bc9c95a`: released templates and the renders built in code never change;
  - a supersede of `inv_9265607a` by `inv_4a53ca43`, whose test takes the latest `agents/block` version.

  Each rule's test was checked by breaking what it guards: 3 breakages for rule 1, 3 for rule 2, and the old and new `agents/block` tests with and without `@3`.

- **Gemini's implementation review, round 1** (`P8-F01` to `P8-F05`), each fixed and each fix broken on purpose and caught:
  - **the spec lookup lists files the way detection does** (through git, so ignored files never count); a candidate or an adopted spec must stay inside the repository, links included; a broken link is never written through; `-SPEC.md` alone names nothing;
  - **`[adopted] spec` is recorded** whenever `docs`, `agents` or `github` runs, not only `docs`;
  - **the snapshot tool keeps every input set,** and covers a repository without squash merges and with rebase;
  - **both proposed rules were refreshed:** Rule 1 finds `uv-build` without an activated environment; Rule 2 reads the version from `pyproject.toml` too, has it and `swerepo/__init__.py` in scope, and counts a released file replaced by a link as changed.

- **After SeamSpec's reviewer read the three items:**
  - the supersede was judged sound;
  - Rule 1 now checks the published sdist too, with a control run of `check`;
  - Rule 2 gained a self-check on a temporary git repository, so its tag comparison is exercised before the first tag, and `swerepo/render.py` joined its scope.

  Both were re-proposed and verified, and every breakage is caught: the sdist, and four bugs planted in the tag comparison.

- **After the reviewer's second read:** both rules were tightened again and re-proposed (the build backend asserted; stray sdist entries reported; the refusal reason checked for `init`, `check` and `update`; the snapshot requirement self-checked; the no-git warning exercised; linked folders caught). Checking the refusal reason found a bug: `update --only release` advised `swerepo init --only release`. `update` now checks component names first, with a test. Every new breakage is caught, and so is every earlier one.

- **SeamSpec:** the owner approved all three on 2026-11-25. `inv_3f05e701` and `inv_7bc9c95a` are locked, and `inv_4a53ca43` replaces `inv_9265607a`, so 28 rules are locked, all passing. `docs/EARNED_SPEC.md` was regenerated.
- **Review:** closed after two rounds each for the design and the implementation ([review](../reviews/phase-8.md)).

## Next

- After merging: the `pypi` environment and the `v*` tag ruleset on GitHub (on the owner's yes), dogfooding on an established repository, and the `0.1.0` release PR.
