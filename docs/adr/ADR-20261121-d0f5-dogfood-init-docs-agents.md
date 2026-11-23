---
id: ADR-20261121-d0f5
title: This repository is set up by swerepo init for docs and agents
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-21
scopes: ["AGENTS.md", "GEMINI.md", "docs/agents/", ".swerepo.toml"]
invariants: []              # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261121-d0f5: This repository is set up by swerepo init for docs and agents

## Context

ADR-20261119-75e6 said this repository follows the SWERepo standard by hand until SWERepo can apply it, and spec principle 12 says SWERepo's own repository is set up by SWERepo. Phase 3 (PR #6) shipped `swerepo init` for the `docs` and `agents` components. Its dry run here kept every existing document and proposed only additions: SWERepo's block in AGENTS.md, GEMINI.md, the three `docs/agents/` runbooks, a progress entry and `.swerepo.toml`.

## Decision

1. **Applied with SWERepo itself:** `uv run swerepo init --only docs,agents --yes`, created by the owner's go-ahead ("Dogfood init first"), 2026-11-21. Editors as detected and decided in ADR-20261121-8259: Claude Code and Antigravity. The ADR README, TEMPLATE, PROGRESS, CHANGELOG, CONTRIBUTING and README stay this repository's own (`keep`): SWERepo didn't write them, so it doesn't manage them.
2. **AGENTS.md:** SWERepo's block holds the general working rules and commands. The hand-written part above SeamSpec's block keeps only what is particular to this repository: commit, push and merge only with the owner's go-ahead; the spec as source of truth; `file:///` links in the privacy check; owner-only actions; phase reviews and Copilot threads (resolved by the owner, or by the agent when the owner asks, as on PR #2 and PR #6); the SeamSpec and in-checkout `swerepo` commands. Rules that repeated the block word for word were removed.
3. **Pull-request rules enforced:** `init` starts an existing repository warn-only (`[pr] enforce = false`, spec §10). This repository has followed the rules from its first PR, so `.swerepo.toml` sets `enforce = true` by hand (its settings may be edited; its fingerprints may not), and `warn_since` is removed.
4. **The ADR file name** was shortened by hand from the 60-character slug `adr new` made, which cut a word. The id is what matters.

**Alternatives considered:**
- **Keep the hand-written rules as they were.** Agents would read most rules twice in two wordings, and the two copies would drift.
- **Delete the hand-written section.** The repository-specific rules (owner's go-ahead, spec updates, owner-only actions, phase reviews) are not in SWERepo's general block.
- **Leave the pull-request rules warn-only** until `swerepo update --enforce-pr-rules` (Phase 6). Nothing here needs a warning period.

## Enforced Invariants

None new. `swerepo check --only docs,agents` reports both components complete; the CI governance job that would run it on every PR comes with the `ci` component (Phase 4).

## Consequences

- ADR-20261119-75e6 now holds only for the components SWERepo can't apply yet (`ci`, `security`, `github`, `seamspec`).
- `swerepo update` (Phase 6) will keep the block, GEMINI.md and the runbooks current here as in any other repository.
- `swerepo adr new` could cut slugs at a word boundary; noted for a later phase.
