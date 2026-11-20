---
id: ADR-20261120-2e50
title: Every pull request gets a Copilot code review, and its threads must be resolved before merging
status: ACCEPTED
date: 2026-11-20
scopes: [".github/swerepo/ruleset.json", ".github/copilot-instructions.md", "AGENTS.md", "SWEREPO-SPEC.md"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261120-2e50: Every pull request gets a Copilot code review, and its threads must be resolved before merging

## Context

The ruleset applied in Phase 0 left out the Copilot review rule, because the owner's Copilot access was unknown (spec §12, §19.7). On PR #2 the owner asked for a Copilot review as a test: it reviewed in about five minutes and found three real bugs that three rounds of Gemini's review and two passes of SeamSpec's reviewer had missed (docs/reviews/phase-1.md). Copilot reads the code fresh, on GitHub, at every pull request; Gemini reviews each phase as a whole before the pull request. They catch different things.

GitHub's REST documentation for rulesets (read on 2026-11-20) names the rule `copilot_code_review`, with two optional boolean parameters, `review_on_push` and `review_draft_pull_requests`, and says it requests a review "if the author has access to Copilot code review and AI credits". The owner has that access.

## Decision

1. **The ruleset requests a Copilot review on every new pull request** to `main`: rule `copilot_code_review` in `.github/swerepo/ruleset.json`, applied with `gh api` (PUT on the existing `swerepo` ruleset) after the owner's go-ahead.
   - `review_on_push: false`: one review per pull request, not one per push, to keep AI credits and comment noise down. A re-review after fixes is requested by hand when a fix is substantial.
   - `review_draft_pull_requests: false`.
2. **Review threads must be resolved before merging** (`required_review_thread_resolution: true`), as spec §12's solo mode says once Copilot review is on. Approvals stay at 0 (solo mode).
3. **`.github/copilot-instructions.md`** tells Copilot what to look at and what to skip (spec §6.1): correctness, data safety, the spec and ADRs, tests that really test; not style that ruff enforces. Needed because every comment now blocks the merge until resolved.
4. **Threads are answered by the developer, resolved by the owner.** Each thread gets a reply with the fix commit, or the reason it isn't changed (AGENTS.md rule 9). The owner resolves the threads when satisfied; the developer never resolves them.
5. **Both reviews stay.** Gemini's phase review in `CODE_REVIEW.md` before the pull request; Copilot's review on the pull request. Copilot findings and their fixes are recorded in that phase's review file.
6. Spec §19.7 is marked as decided.

**Alternatives considered:**
- **Request Copilot by hand when wanted.** Easy to forget; PR #2 shows the automatic second look is worth having on every change.
- **`review_on_push: true`.** Re-reviews every push, including documentation-only commits; more credits and threads for little gain.
- **Copilot instead of Gemini.** Copilot reviews a diff; Gemini's phase review runs the commands, checks the spec and ADRs as a whole and answers design questions before code lands.
- **Leave threads unresolved-allowed.** Then an unanswered Copilot finding could be merged past without anyone noticing.

## Enforced Invariants

None; the ruleset is enforced by GitHub. `swerepo check` (Phase 2 and 5) will compare the live ruleset with `.github/swerepo/ruleset.json`.

## Consequences

- Every pull request waits for Copilot's review and for its threads to be resolved before merging.
- Copilot's review uses the owner's AI credits, once per pull request.
- If the owner's Copilot access lapses, the rule simply doesn't request a review; the rest of the ruleset is unaffected.
