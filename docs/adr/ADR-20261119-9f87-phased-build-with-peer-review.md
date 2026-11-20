---
id: ADR-20261119-9f87
title: Build in phases, each closed by a peer code review
status: ACCEPTED
date: 2026-11-19
scopes: ["CODE_REVIEW.md", "docs/reviews/", "docs/PROGRESS.md", "docs/adr/"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261119-9f87: Build in phases, each closed by a peer code review

## Context

SWERepo is built by an AI developer (Claude) from SWEREPO-SPEC.md v0.5, with the owner deciding. The owner wants a second, independent reviewer (Gemini) on every step, and a written trail of what was reviewed, what was changed and what was argued, the way SeamSpec's own repository keeps ADRs and a progress log.

## Decision

1. **Phases.** The build follows the spec's order (§20), one phase at a time:

   | Phase | Scope |
   |---|---|
   | 0 | Repository skeleton, CI, first ADRs, SeamSpec |
   | 1 | Detection, `.swerepo.toml`, template rendering, normalised fingerprints |
   | 2 | `swerepo check` (read-only), including `--base` |
   | 3 | `init`, plan and apply for `docs` and `agents`; `progress`, `adr` |
   | 4 | `ci` and `security` components |
   | 5 | `github` component; `threads` |
   | 6 | `update`, three-way merge, `diff`, `status` |
   | 7 | `seamspec` component and the hygiene rule pack |
   | 8 | `openspec` and `release` components; dogfooding on this and one established repository |

2. **ADRs are not optional.** Every decision in the table in [docs/adr/README.md](README.md) gets an ADR in the same PR as the change. A reviewer finding "decision without an ADR" is a valid finding.

3. **Each phase ends with a peer review in `CODE_REVIEW.md`** at the repository root, with these parts:
   - **Developer summary:** scope, files, ADRs written, how to run it, test results, known gaps, questions for the reviewer.
   - **Review rounds:** the reviewer's strengths and findings (IDs `P<phase>-F<nn>`, severity `blocker | should-fix | suggestion | question`, repo-relative `path:line`, a failing scenario, a recommendation), then the developer's response to each: **Fix** (with what changed), **Push back** (with reasons) or **Defer** (to a named phase).
   - Pushbacks go back to the reviewer, who answers **Accept** or **Maintain**. After two rounds on the same finding, it is marked **Owner decides**.
   - **Status:** open, or closed when every finding is fixed, accepted, deferred or decided.

4. **Closing a phase.** When the review is closed, `CODE_REVIEW.md` moves to `docs/reviews/phase-<n>.md` unchanged, the phase's progress entry links it, and the next phase starts with a fresh `CODE_REVIEW.md`.

5. **Roles.** The developer writes code, tests, ADRs and the developer parts of the review. The reviewer edits only its own sections of `CODE_REVIEW.md`. The owner merges, approves SeamSpec rules, and settles "Owner decides" findings. Nothing is published without the owner's explicit go-ahead (spec §18).

6. **No paths from anyone's machine** in review files or any other tracked file: repo-relative paths only (the first Gemini-written design note had `file:///` links into a home folder).

**Alternatives considered:**
- **Review in GitHub PR comments only.** There is no GitHub repository yet (spec §19.2), Gemini isn't wired to GitHub, and PR threads don't keep a reviewable history in the repository itself. Copilot review on PRs is added once the repository is on GitHub (Phase 5 dogfooding); it complements this review, not replaces it.
- **One review file per round.** More files, harder to follow one finding through its rounds. One file per phase keeps a finding's whole conversation together.

## Enforced Invariants

None yet. Could later be proposed: "every file in docs/reviews/ has a closed status".

## Consequences

- Every phase takes a review round trip through the owner; phases are sized so a review is a reasonable read.
- `docs/reviews/` becomes the history of why the code looks the way it does, next to the ADRs.
