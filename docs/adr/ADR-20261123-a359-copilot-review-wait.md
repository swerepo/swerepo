---
id: ADR-20261123-a359
title: Merges wait for Copilot review
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-23
scopes: ["swerepo/ci.py", "swerepo/templates/ci/", "swerepo/init.py", "SWEREPO-SPEC.md"]
invariants: []              # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261123-a359: Merges wait for Copilot review

## Context

The ruleset requests Copilot's review and requires review threads to be resolved before a merge (spec §6.1, ADR-20261120-2e50). It doesn't wait for the review to arrive: PR #3 was merged before Copilot's review came in, and its eight findings needed a follow-up pull request (#4).

The owner decided on 2026-11-23 that merges must wait for Copilot's review.

GitHub's `copilot_code_review` rule (`review_on_push: false`) reviews a pull request's first commit only. A rule like "Copilot has reviewed the latest commit" would therefore block every pull request that gets a fix pushed.

## Decision

1. **A `copilot-review` job in `swerepo-ci.yml`**, inside `ci-ok`, on pull requests only. It passes once GitHub lists a review of the pull request by Copilot (`copilot-pull-request-reviewer[bot]`), of any commit. It asks every 30 seconds for up to 20 minutes, then fails, saying so; re-running the job asks again. On a draft it fails at once, since the ruleset doesn't request reviews on drafts; the workflow runs again on `ready_for_review`, when the review is requested (review P5-F05).
2. **Waiting in the same run**, not re-running CI when the review is submitted. A run started by `pull_request_review` would produce a new `ci-ok` that skips the jobs that run on `pull_request` only, governance among them, so it could pass while the pull request's own governance had failed.
3. **Only where Copilot review is on:** the job is rendered when the committed `ruleset.json` requests Copilot's review (a `copilot_code_review` rule), which is also what `[github] copilot_review` records. A repository whose own ruleset has no such rule gets no wait, whatever the defaults say, and `check` compares the workflow with the committed ruleset (review P5-F10). Without it, nothing waits. The job reads reviews with the workflow's own token (`pull-requests: read` for that job only).
4. **Templates at version 2:** `ci/workflow@2` and its parts at `@2` add the optional job and teach `ci-ok` that `copilot-review` is skipped by design off pull requests. Version 1 stays for the repositories that recorded it. A repository whose `swerepo-ci.yml` is unchanged gets version 2 when `github` is applied: `init` rewrites it, as for `--projects` (ADR-20261122-4a06 point 10). A changed one is left for `update`.

**Alternatives considered:**
- **Review on every push** (`review_on_push: true`) and requiring a review of the latest commit. It costs a Copilot review per push and still needs a wait.
- **Re-running CI on `pull_request_review`.** It runs into the governance gap in point 2.
- **A separate workflow as a second required check.** The ruleset would need another required check, the same trade the owner rejected for SeamSpec.

## Enforced Invariants

`inv_09cc1c20` (`ci-ok` waits for every job and fails on any wrong result) covers the new job once it is in the workflow. Its fixed list of jobs skipped by design doesn't include `copilot-review`; the rule's variants render no `github` component, so it still holds. To propose with the code: a workflow rendered with Copilot review waits in a `copilot-review` job that `ci-ok` requires on pull requests.

## Consequences

- A pull request can't merge before Copilot has reviewed it, where Copilot review is on.
- A pull request's CI takes as long as Copilot's review, usually a few minutes. The 20-minute limit makes a missing review a visible failure, not a hang.
- Later pushes to the same pull request pass the job at once.
- *Amended by ADR-20261123-cc8d:* pull requests opened by Dependabot (`dependabot[bot]`) with only its own commits pass at once. GitHub never requests Copilot's review for them, so they would otherwise always fail.
