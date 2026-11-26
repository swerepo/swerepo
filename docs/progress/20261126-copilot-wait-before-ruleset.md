# 2026-11-26 · The Copilot wait passes while no ruleset requests Copilot's review

**Branch:** `phase-8/copilot-wait-setup-pr`

## Done

- **The gap, from dogfooding on an established repository:** the pull request that adds SWERepo waited 20 minutes for a Copilot review nothing requested, then turned `ci-ok` red. GitHub requests Copilot's review only through an active ruleset rule, and the ruleset is applied after that pull request merges (ADR-20261125-5f22 point 5). Every pull request before the ruleset was applied would have been red, and every pull request for good where it never is.
- **Designed first, reviewed by Gemini** (`P8-C01` to `P8-C05`, two rounds, all accepted, in `CODE_REVIEW.md`). The owner chose option B with A's command (ADR-20261126-c228); the owner checked GitHub Free's answer on a private repository.
- **The job** (`ci/job-copilot-review@2`, changed in place: no release yet) reads the default branch's active rules once, after the draft and Dependabot checks:
  - **no `copilot_code_review` rule:** it passes at once and says how to ask Copilot anyway (`gh pr edit <number> --add-reviewer @copilot`);
  - **a rule:** it waits as before;
  - **a failed read:** it fails at once, except GitHub Free's exact "Upgrade to GitHub Pro" 403 on a private repository (the whole of `gh`'s stderr, so any change in GitHub's text fails the job);
  - **the default branch, never the base,** so retargeting can't skip the wait. The name comes through `env:`, encoded as one path segment.
- **`init` and `update` say so** where they leave the ruleset unapplied while the workflow waits for Copilot: held for `--apply-github`, a terminal no, or `gh` missing or logged out. Never under `--no-copilot-review`, or when GitHub's ruleset already requests Copilot.
- **Spec v0.18** (§6.2, §12, Appendix A); ADR-20261123-a359 and ADR-20261123-cc8d amended.
- **This repository's `swerepo-ci.yml`** rewritten by `swerepo update`.
- **Tests:** `tests/test_copilot_wait.py` (the note on each path, and the job run as written with a fake `gh`). Each change was broken on purpose and caught: 19 breakages (one first missed, the note under `--no-copilot-review`, until a test with `gh` logged out covered it). The 14 breakages of the job are caught by `inv_b5d32550`'s test as well.
- **Reviews:** Gemini approved the design in two rounds (`P8-C01` to `C05`) and the code in a third, with two suggestions fixed (`P8-C06`, `C07`). The owner checked GitHub Free's answer on a private repository. SeamSpec's reviewer read the rule twice before approval: the Free-plan exception now matches gh's exact answer only, and the private 401 and 500 cases are tested.
- **SeamSpec, approved by the owner on 2026-11-26** (30 rules in force; `docs/EARNED_SPEC.md` regenerated): `inv_b5d32550` (critical) replaces `inv_78f19f51`, keeping every one of its checks.

## Next

- The pull request and Copilot's review.
- **Phase 9:** waits keyed to the pull request's base, and retargeting without a push.
