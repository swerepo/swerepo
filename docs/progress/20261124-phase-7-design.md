# 2026-11-24 · Phase 7 design, and v0.2 planned as Phases 9 to 12

**Branch:** `phase-7/design`

## Done

- **ADR-20261124-cd64, the `seamspec` component** (the owner's choices, 2026-11-24):
  - `seamspec init` runs only in the person's terminal, never with `--accept-auto-run`; without a terminal the plan shows the command and the component waits;
  - SWERepo never installs or upgrades SeamSpec, and makes no PyPI lookup;
  - `--mode enforced` on a first setup only; strict is never lowered; `--no-ci` with `ci`, `--ci` without;
  - the four hygiene rules, each with its component, adopted instead when a locked rule already covers one (`[seamspec.adopted]`, `--adopt`);
  - `-u --seamspec` moves the SeamSpec pin forward, with `ci` brought along for the pin only.
- **The owner's four watchouts, checked against SeamSpec 0.1.2 and the code:**
  1. **Strict mode's workflow fails the workflow audit:** zizmor reports two high `unpinned-uses` and a medium `artipacked`. SWERepo writes a pinned `seamspec.yml` first, which SeamSpec keeps. Strict mode's CODEOWNERS block, appended after SWERepo's, would take `/.seamspec/` to a placeholder team: reported, a failure in `team` mode.
  2. **`hygiene/privacy`** reads `[privacy] allow_paths` with `tomllib` and git's glob rules; **`hygiene/adr-index`** follows `[adopted] adr_dir`, and is proposed only when the README has the index markers.
  3. **`hygiene/ci-tests`** expects `test-<project>` jobs for listed projects; standard 1's CI runs only `uv run pytest`, so other commands come with a version 2.
  4. **The pin, `swerepo-ci.yml` and its record move together, or not at all.**
- **Also checked:** `seamspec doctor`, `status` and `spec --check` write nothing, so `check` can call them.
- **ADR-20261124-2452, v0.2 as Phases 9 to 12:** multi-branch governance; multi-service monorepos and federated ADRs; broader Python and ergonomics for agents; TypeScript and the OpenSpec importer.
- **Spec v0.15:** §6.8, §7 (`--adopt`), §9 (`[seamspec.adopted]`), §11, §12, §13, §19.4, §19.8, §19.10, §20, Appendix A.
- **`docs/PROGRESS.md`:** Phase 6 done ([PR #18](https://github.com/swerepo/swerepo/pull/18)), Phase 7 designed, Phases 9 to 12 listed.

## Next

- Build Phase 7 as ADR-20261124-cd64 decides, then Gemini's review.
