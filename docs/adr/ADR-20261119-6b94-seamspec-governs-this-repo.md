---
id: ADR-20261119-6b94
title: SeamSpec governs this repository from Phase 0; rules are locked once earned
status: ACCEPTED
date: 2026-11-19
scopes: [".seamspec/", "pyproject.toml", ".github/workflows/ci.yml", "CLAUDE.md"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261119-6b94: SeamSpec governs this repository from Phase 0; rules are locked once earned

## Context

The spec says SWERepo's own repository uses SeamSpec on its own rules (§5 principle 12, §18). SeamSpec locks behaviour that already works: a locked rule's test is hashed at approval and checked when an agent stops, at commit, and in CI. Locking rules on code that is still changing would only produce supersedes. SeamSpec 0.1.1 is released on PyPI.

The spec's own design has a gap here: for other repositories, `seamspec init --ci` writes a separate workflow, but the ruleset requires only `ci-ok`, so a failing locked rule in that workflow wouldn't block a merge. This repository avoids the gap by running SeamSpec inside its own CI workflow; the spec gap is raised for the owner in the Phase 0 review.

## Decision

1. **Set up in Phase 0**, by the owner in their own terminal: `uv run seamspec init --mode enforced --no-ci --hosts none` (the owner answers SeamSpec's consent and the plugin questions; the developer never does). `--no-ci` because CI runs SeamSpec inside `ci.yml` (point 3). `--hosts none`: Claude Code only, since the reviewer (Gemini) doesn't edit code.
2. **SeamSpec is a dev dependency pinned exactly** (`seamspec==0.1.1` in `[dependency-groups] dev`), so the lockfile decides the version for `uv run seamspec` and CI, and upgrades are deliberate. The git pre-commit hook and the Claude Code plugin run the `seamspec` on PATH, not the project's environment, so contributors also install the same version as a tool (`uv tool install seamspec==0.1.1`, in README and AGENTS.md). Upgrading means moving both together (review finding P0-F05).
3. **No separate SeamSpec workflow.** CI runs `seamspec doctor --ci` and `seamspec verify --all --ci` as a job inside `.github/workflows/ci.yml`, feeding `ci-ok` (ADR-20261119-dd1a), the way SeamSpec's own repository does.
4. **Day-one rules**, proposed in Phase 0 because they are true from the start:
   - no personal email addresses or home-folder paths in tracked files (placeholders and noreply addresses allowed, spec §6.4);
   - `CHANGELOG.md` keeps an `[Unreleased]` section.
5. **Later rules are earned.** At the end of each phase, the developer proposes rules for behaviour that now works (for example "`check` never writes a file", "a file a person edited is never overwritten", "`init` twice changes nothing"). The owner approves each with `seamspec review`; the developer never approves.
6. **`docs/EARNED_SPEC.md` from Phase 0**, written with `seamspec spec --out` and checked in CI with `seamspec spec --check` (spec §6.8, §13). Regenerated in the same change whenever rules are approved or superseded, so six phases dogfood the earned-spec workflow before SWERepo automates it in Phase 7 (review finding P0-F06).
7. **Locked tests are never linted or reformatted:** `.seamspec` is in ruff's `extend-exclude` (SeamSpec ADR-20261013-c3f7). Rule tests are linted before they are proposed.

**Alternatives considered:**
- **Wait until Phase 7**, when SWERepo can set SeamSpec up itself. Loses six phases of protection for the developer's own work, and the day-one rules are already true.
- **`seamspec init --ci`** (its own workflow). Not required by a ruleset that requires only `ci-ok`; see Context.
- **SeamSpec as a global tool only.** Machines and CI could run different versions; the ledger checks can differ between versions (SeamSpec ADR-20261011-a9f3).

## Enforced Invariants

The two day-one rules, once approved.

## Consequences

- The developer's agent stops run the locked tests; a weakened test is caught.
- Phase 7 is the real dogfooding test: SWERepo then applies its own hygiene rule pack here.
- The spec gap (SeamSpec's CI outside `ci-ok`) needs a decision before Phase 7.
