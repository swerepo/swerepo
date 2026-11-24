# 2026-11-23 · Phase 5: swerepo init for github, and swerepo threads

**Branch:** `phase-5/github-threads` · **Review:** [docs/reviews/phase-5.md](../reviews/phase-5.md) (closed, 4 rounds)

## Done

- **Owner decisions** (2026-11-23):
  - `solo` mode for this organisation-owned repository;
  - the owner's own login as code owner;
  - squash-only merging;
  - merges wait for Copilot's review.
- **`swerepo init` for `github`** (`swerepo/github.py`, ADR-20261123-4e40):
  - `.github/swerepo/ruleset.json` and `repo-settings.json`, built in Python as `github/ruleset@1` and `github/repo-settings@1`;
  - Copilot review instructions, PR and issue templates, Dependabot, and CODEOWNERS (a block at the end);
  - the mode and code owner, asked, or given with `--mode`, `--code-owner` and `--no-copilot-review`;
  - the ruleset and merge settings applied through `gh` after they are shown as JSON. A ruleset named `swerepo` is adopted, other rulesets are never touched, and without a GitHub repository they wait, with the next steps printed.
- **Merges wait for Copilot's review** (ADR-20261123-a359): a `copilot-review` job inside `ci-ok`, in `ci/workflow@2`, which `init` writes over an unchanged version 1 workflow when `github` is applied.
- **`swerepo check` reads GitHub** through `gh`, with GET requests only and never with `--ci`: the live ruleset and merge settings against the committed files, secret scanning and push protection, and the dependency graph (the gap PR #9 found).
- **`swerepo threads <pr>`** (`swerepo/threads.py`): open review threads, read-only.
- **The agents templates:** `agents/block@2` and `agents/address-review@2` name `swerepo threads`.
- **Tests:** a fake `gh` (`tests/fake_gh.py`) answers from canned data and logs every call, so the tests prove what reaches GitHub. Spec v0.11.
- **Review:** Gemini's 14 findings (`P5-F01`–`P5-F14`) are all accepted with regression tests; Gemini signed off in round 4.
- **SeamSpec:** the owner approved two critical rules, so 15 are locked (`docs/EARNED_SPEC.md` regenerated):
  - `inv_ef31cc79`: `check`, `init`'s plan and `threads` only read GitHub; `init` changes only the `swerepo` ruleset and the merge settings, and only after a yes;
  - `inv_faa5bef5`: pull requests wait for Copilot's review inside `ci-ok`.

## Next

- Pull request for Phase 5, then apply `github` here with the owner's choices.
