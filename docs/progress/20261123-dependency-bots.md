# 2026-11-23 · Dependabot's pull requests can merge

**Branch:** `fix/dependabot-copilot-wait` · **ADR:** ADR-20261123-cc8d

## Done

- **Found:** Dependabot's first pull requests (#12–#14) passed every test, but `copilot-review` timed out on each: GitHub requests Copilot's review only for authors who have Copilot. So `ci-ok` failed and none could merge.
- **Owner decisions** (2026-11-23):
  - pull requests opened by `dependabot[bot]` pass the wait at once. People, look-alike names and other bots, coding agents included, still wait;
  - Dependabot proposes a new version once it is 7 days old (`cooldown: default-days: 7`, checked against GitHub's documentation). Security updates don't wait.
- **Templates:** `ci/workflow@2` (`job-copilot-review/2`) and `github/dependabot@1`, corrected in place (unreleased). This repository's two files were rewritten from them by `init`.
- **SeamSpec**, approved by the owner, so 17 rules are locked; `docs/EARNED_SPEC.md` regenerated:
  - `inv_78f19f51` (critical) supersedes `inv_faa5bef5`. It keeps everything the old rule locked and adds Dependabot's cases.
  - `inv_abcc9759` (critical): the 7-day cooldown on every Dependabot update, and auto-merge off in SWERepo's settings.
- **Gemini's review (DB-F01–F03), all fixed:**
  - a bot's pull request passes the wait only with its own commits, Dependabot's signed, on a branch in the repository, and fails at once with anything else: people's changes go in a pull request of their own;
  - the pull-request rules exempt a bot's branch only while every commit is the bot's (`test_prrules.py`);
  - the replacement rule's test maps its cases through the job's `env:` and adds an unquoted-glob look-alike.
  - Found along the way: the old rule's test printed the whole environment on a failing assertion. The new one never prints it.
- **SeamSpec's reviewer**, all fixed:
  - Dependabot's commits must be committed by GitHub itself (`web-flow`), not only verified;
  - a bot's draft fails like any draft;
  - the cooldown block must be exactly `default-days: 7`, with nothing after the last entry;
  - both rules say only what the workflow and the files do.
- **Copilot's review of PR #16**, both fixed:
  - a person's merge on Dependabot's branch now counts for the pull-request rules; only GitHub's own checkout merge is left out;
  - a list of 250 commits, GitHub's limit, fails closed.
- **Tests:** `TestDependencyBots`; the replacement rule's test catches a too-broad name match, every-bot matching, and a missing bot check.

## Next

- After this pull request merges: re-run CI on #12–#14 (Dependabot rebases them), then merge them.
- Phase 6: `update`, three-way merge, `diff`, `status`.
