---
id: ADR-20261124-2452
title: v0.2 is planned as Phases 9 to 12
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-24
scopes: ["SWEREPO-SPEC.md", "docs/PROGRESS.md"]
invariants: []              # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261124-2452: v0.2 is planned as Phases 9 to 12

## Context

The build of v0.1 is in eight phases (ADR-20261119-9f87). Phase 7 is the `seamspec` component; Phase 8 is `openspec`, `release` and dogfooding.

Spec §20 lists v0.2 as one paragraph:
- TypeScript;
- monorepo projects;
- `--pr`;
- the OpenSpec importer;
- changelog fragments.

Spec §20's "Later" holds editor wrappers around the `docs/agents/` runbooks. §19 leaves open a type checker (19.4), `--pr` (19.8) and changelog fragments (19.10).

The owner planned v0.2 on 2026-11-24 as four phases after v0.1. That adds one area the spec doesn't cover yet: teams whose long-lived environment branches (`develop` for staging, `release` for production) need the same protection as `main`.

Moving spec items between v0.1, v0.2 and Later needs an ADR (`docs/adr/README.md`).

## Decision

v0.2 is built in four more phases after v0.1, each closed by a peer review like the first eight (ADR-20261119-9f87). The scope of each is below. Each phase starts with its own design ADR, which decides the details against the tools as they are then.

1. **Phase 9: enterprise multi-branch governance.** For repositories with long-lived environment branches, such as `develop` (staging) and `release` (production):
   - **Choosing them:** `--protected-branches`, recorded in `.swerepo.toml`.
   - **The ruleset protects them** like the default branch, including the `deletion` rule, so `delete_branch_on_merge` never deletes `develop` after a `develop → release` pull request.
   - **Merge methods:** `ruleset.json` and `repo-settings.json` allow `["squash", "merge"]`, so `develop → release` can merge without squashing its history.
   - **Kept in step:** `swerepo-ci.yml`'s `push.branches` and the agent instructions name the same branches.
2. **Phase 10: multi-service monorepos and federated ADRs.**
   - **`swerepo adr new --scope <path>`.**
   - **Two tiers of ADRs, opt-in,** when `--projects` lists several roots:
     - the root `docs/adr/` for decisions across services, such as contracts between them;
     - `services/<name>/docs/adr/` for each service's own decisions.
     So teams don't collide on one index, and CODEOWNERS can give each service's ADRs to its owners.
   - **It includes** spec §11's "full monorepo support", following SeamSpec's per-runner folders.
3. **Phase 11: broader Python, and ergonomics for agents.**
   - **More project setups:** Poetry and `requirements.txt` projects in CI.
   - **A type checker, opt-in:** `--typecheck ty|pyright|mypy`. This answers §19.4: none by default, offered as an option.
   - **New commands:**
     - `swerepo progress new`;
     - changelog fragments (§19.10);
     - `--pr`, to open one pull request per component (§19.8).
   - **Editor command wrappers** around the `docs/agents/` runbooks. These move from Later to v0.2.
4. **Phase 12: TypeScript and polyglot monorepos.**
   - **TypeScript projects:** npm and pnpm, vitest and jest, biome, eslint and prettier, matching SeamSpec's presets.
   - **SeamSpec's OpenSpec importer,** once SeamSpec ships it.

v0.1 is unchanged: Phases 7 and 8 come first, and v0.1 is released after Phase 8.

**Alternatives considered:**
- **Keeping v0.2 as one list:** the phases are large and unrelated. Phases give each its own design review and pull request, as v0.1's did.
- **Multi-branch governance in v0.1:** it touches the ruleset, the merge settings and CI together. v0.1's single protected branch is enough for its first users, and Phase 5's settings-as-code makes the change contained later.
- **TypeScript first:** the Python setups (Poetry, `requirements.txt`) and the monorepo work come first, because they serve the repositories SWERepo already supports. TypeScript also follows SeamSpec's own presets, so it goes last.

## Enforced Invariants

None. This is a plan. Each phase's ADR names the rules it locks.

## Consequences

- **Where it's recorded:**
  - spec §20 lists v0.2 as Phases 9 to 12;
  - §11 points to Phase 10, §12 to Phase 9, and §19.4, §19.8 and §19.10 to Phase 11;
  - `docs/PROGRESS.md` lists the four phases.
- **Not fixed yet:** a phase's scope can still change at its design ADR, which records any change against this one.
- **Released templates stay locked** (Phase 8). Phase 9's ruleset and merge settings, and Phase 11's CI for Poetry and `requirements.txt`, come as new template versions, so `update` brings them to existing repositories.
