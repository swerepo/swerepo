---
id: ADR-20261119-75e6
title: This repository follows the SWERepo standard by hand until SWERepo can apply it
status: ACCEPTED
date: 2026-11-19
scopes: ["AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "CHANGELOG.md", "docs/PROGRESS.md", "docs/progress/", "SWEREPO-SPEC.md", "GOLDENREPO-BLUEPRINT.md"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261119-75e6: This repository follows the SWERepo standard by hand until SWERepo can apply it

## Context

The spec says SWERepo's repository is set up by SWERepo (§5 principle 12, §18). That is only possible once the components exist (Phases 3 to 7). Until then the repository should already work the way the standard says, so the developer lives with the conventions before automating them, and problems show up early.

## Decision

*Since ADR-20261121-d0f5, SWERepo applies the `docs` and `agents` components to this repository itself; the rest is still by hand.*

1. **Hand-written now, regenerated later.** `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `docs/PROGRESS.md`, `docs/progress/` and `docs/adr/` follow spec §6.5 and §6.6 by hand. When a component can generate them, it is run on this repository in that phase's PR, and the hand-written versions are adopted or replaced through SWERepo's own rules (an existing file is the person's file).
2. **Agent rules in `AGENTS.md`; `CLAUDE.md` imports it** (spec §6.6). No `GEMINI.md`: Gemini reviews and reads files directly, and SeamSpec would read a `GEMINI.md` as Antigravity being in use.
3. **Progress:** `docs/PROGRESS.md` holds Now and Next; each PR adds one file in `docs/progress/` (spec §6.5).
4. **Branches and pull requests**, with one bootstrap exception (spec §12; review finding P0-F04):
   1. **Bootstrap commit on `main`**, the only commit that goes straight to it: `LICENSE`, `README.md`, `CHANGELOG.md`, `SWEREPO-SPEC.md` and `GOLDENREPO-BLUEPRINT.md`. It roots `main` so a branch can be compared with it, and it carries no workflow, so the first push runs no CI. `CHANGELOG.md` must be in it: SeamSpec's commit hook runs the locked rules on the staged files of every commit, and without it the changelog rule (inv_b2000e40) blocks the commit (found by simulating both commits in a scratch copy before committing).
   2. **Push to the empty GitHub repository**, then apply a ruleset requiring `ci-ok` on `main`.
   3. **Phase 0 itself** goes on `phase-0/skeleton` and lands through a pull request, so its CI runs as a pull request against `main` before merging.
   4. Every later phase: a branch and a pull request. All commits only with the owner's go-ahead.
5. **The spec stays at the root** as `SWEREPO-SPEC.md`, the source of truth for behaviour; a decision that changes it updates it in the same PR. `GOLDENREPO-BLUEPRINT.md` stays as the historical design input that spec Appendix B answers; it is not maintained.
6. **Not yet:** `SECURITY.md` (needs a contact). It waits for the owner's decision and is listed under Next. (`LICENSE` and `CODEOWNERS` were added later in Phase 0: ADR-20261119-7384, ADR-20261119-13fc.)

**Alternatives considered:**
- **No conventions until SWERepo can apply them.** The first phases would be built without the process the tool exists to install.
- **Move the spec to `docs/SPEC.md`.** Cleaner, but the reviewer prompts name the spec at the root; it can move later with its own ADR.

## Enforced Invariants

The SeamSpec day-one rules (ADR-20261119-6b94) cover privacy and the changelog.

## Consequences

- Phases 3 to 7 each include a dogfooding step on this repository, which doubles as a test of adopting an existing repository.
- `SECURITY.md` waits on the owner's choice of security contact.
