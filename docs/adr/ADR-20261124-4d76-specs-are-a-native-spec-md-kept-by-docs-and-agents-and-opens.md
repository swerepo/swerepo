---
id: ADR-20261124-4d76
title: Specs are a native SPEC.md kept by docs and agents, and OpenSpec leaves v0.1
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-24
scopes: ["SWEREPO-SPEC.md", "swerepo/templates/docs/", "swerepo/templates/agents/", "swerepo/templates/github/pr-template/", "swerepo/templates/github/copilot-instructions/", "swerepo/check.py", "swerepo/init.py", "swerepo/state.py", "swerepo/standard.py"]
invariants: []              # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261124-4d76: Specs are a native SPEC.md kept by docs and agents, and OpenSpec leaves v0.1

## Context

Spec §6.7 and §14 planned an optional `openspec` component for Phase 8: SWERepo would run OpenSpec's own `init`, "if its docs confirm a clean non-interactive init" (§20). OpenSpec's public documentation (README and openspec.dev, read on 2026-11-24; never its code) confirms that it can run without questions (`openspec init --tools …`), and also shows what it would cost:

- **Node.js 22.20 or newer** and an npm install, against principle 10 (Python, uv, git and `gh` only).
- **Skills installed in the person's home folder by default** (`~/.agents/skills`), a change to the whole machine, which SWERepo never makes; `--scope project` avoids it.
- **Old 1.x marker blocks in `CLAUDE.md` and `AGENTS.md` removed without asking** whenever `--tools` is used, including edits inside them.
- **Anonymous usage statistics on by default**, against principle 11 (no data leaves the machine except the GitHub calls the person approves).

SWERepo's own repository already works without it: `SWEREPO-SPEC.md` is the source of truth for behaviour, and its rules say a change to behaviour updates the spec in the same change. Progress entries, ADRs and the checks keep it honest, and `docs/EARNED_SPEC.md` shows what SeamSpec enforces. The owner decided on 2026-11-24 to make that pattern part of the standard.

## Decision

1. **`SPEC.md`, written by `docs`.** On a repository without a spec, `docs` writes a starter `SPEC.md` at the root from a new template, `docs/spec@1`, with short sections: purpose, who it's for, behaviours, out of scope, open questions. Like README, PROGRESS and CHANGELOG it is a starter file: written once, the person's from then on, never recorded or updated by SWERepo.
2. **Finding the spec** (review P8-D04; the owner's answer, 2026-11-24). `init` and `update` both look, in this order:
   1. **`[adopted] spec` is set:** that file is the spec, and nothing is looked for. The path is checked like every recorded path (repository-relative, inside the repository).
   2. **Otherwise, the candidates** are the root `SPEC.md`, `docs/SPEC.md` and any root `*-SPEC.md`, matched without regard to case. `docs/EARNED_SPEC.md` is never one.
   3. **No candidate:** `docs` writes the starter `SPEC.md`. Nothing is recorded, so a second run finds `SPEC.md` as the only candidate and changes nothing (inv_1002d669).
   4. **One candidate:**
      - the root `SPEC.md` is the default and is kept as it is, with nothing recorded;
      - any other candidate is recorded as `[adopted] spec = "<path>"`, by `update` as well as `init`, so a repository set up before Phase 8 adopts its spec on its next `update`.
   5. **Several candidates, the root `SPEC.md` among them or not:** none is guessed. The plan names them and how to record one under `[adopted] spec`. No `SPEC.md` is written, and `check` reports `✗ docs.spec` with the same list until the person chooses.

   This repository adopts `SWEREPO-SPEC.md`. The spec's path reaches the templates that name it as an input of their render (`spec`, `SPEC.md` by default), so recording `[adopted] spec` later makes those blocks and files outdated and `update` brings them in line.
3. **The rule, in `agents` and `github`:** a change to behaviour, CLI flags, APIs or configuration updates the spec in the same pull request. It goes into:
   - the `AGENTS.md` block, as one more working rule, naming the adopted file (a new version of `agents/block`);
   - `docs/agents/prepare-pr.md`, as a step (a new version of `agents/prepare-pr`);
   - a new runbook, `docs/agents/update-spec.md` (`agents/update-spec@1`): what belongs in the spec and what doesn't, and on an existing codebase, starting from the part a change touches rather than describing all of it at once;
   - `.github/pull_request_template.md`, as a checklist line (a new version of `github/pr-template`);
   - `.github/copilot-instructions.md`, so Copilot comments on a change to user-visible behaviour, CLI flags, APIs or configuration that leaves the spec as it was (a new version of `github/copilot-instructions`). Unlike a fixed rule, Copilot can tell a refactor or a bug fix from a change in behaviour (P8-D06);
   - the starter `CONTRIBUTING.md`, for people (a new version of `docs/contributing`).
4. **`check` looks only for the file:** `docs.spec`, `✓` when the adopted or default spec exists, `✗` when it doesn't.
5. **No pull-request rule for the spec.** `check --base` doesn't compare code changes with spec changes, and there is no `Spec: none` trailer: bug fixes and refactors change code without changing intended behaviour, and a warning on every such pull request would teach people to ignore warnings.
6. **Not a governance path.** `SPEC.md` stays out of SWERepo's `CODEOWNERS` block, so feature pull requests update it without a code owner's review. (This repository's own `/SWEREPO-SPEC.md` line, above the block, is the owner's and stays.) A change to the spec alone needs no ADR: the spec says what; an ADR says why, when a change is a design decision.
7. **Planned for v0.2, Phase 10 (two tiers, with `--projects`):**
   - a single-service repository keeps one root `SPEC.md`;
   - a multi-service monorepo keeps a root `SPEC.md` for what spans services (system-wide behaviour, contracts between services) and `<service>/SPEC.md` in each listed service folder, beside that service's `<service>/docs/adr/`, so each team edits its own spec without merge conflicts;
   - the root file of a multi-service repository comes from a second template, `docs/spec-system@1`, with sections for the services and the contracts between them; each service's file comes from `docs/spec@1` rendered with the service's name;
   - a service that keeps its spec elsewhere is adopted per service, under `[projects.adopted."<service>"] spec`, as `[adopted] spec` works for the root;
   - **which one wins** (the owner's answer on P8-D04): inside a service, `<service>/SPEC.md` is the spec for that service's behaviour, and the root `SPEC.md` covers what crosses services. The agents block says so once there are service specs;
   - v0.1 writes only the root file and reads only `[adopted] spec`, so this layout adds keys and files without changing any.
8. **OpenSpec leaves v0.1.** The `openspec` component, its detection, check and `[tools] openspec` are removed (ADR-20261124-152d). v0.2, Phase 12 keeps SeamSpec's OpenSpec importer, for teams that use OpenSpec on their own.

**Alternatives considered:**
- **Build the `openspec` component with `--scope project`, telemetry off and only on a fresh setup.** Possible, but every repository that chooses it needs Node 22 on every machine, and SWERepo would be running a tool whose defaults it has to work against. A Markdown file and a rule do the job with nothing to install.
- **A `check --base` warning when code changes without the spec (with a `Spec: none` trailer).** Rejected by the owner: refactors and bug fixes would trigger it constantly.
- **A `docs/spec/` folder from day one.** A folder of one file is ceremony for most repositories; the two-tier layout covers the case where one file collides.
- **The spec as a governance path in `CODEOWNERS`.** In `team` mode every feature pull request would need a code owner's review.

## Enforced Invariants

None of its own yet. The spec's content can't be checked by a test; that it exists is a `check` item. Once built, a rule could protect that `init` never writes `SPEC.md` over an existing spec and adopts it instead.

**A locked rule this changes** (review P8-D02; the owner agreed, 2026-11-24):
- **`inv_9265607a` (critical):** `update` writes only what SWERepo wrote. Its test names `agents/block@2` as the version `update` moves an `agents/block@1` block to. With `agents/block@3`, `update` moves it to version 3 and the test fails.
- **What happened to it:** the owner approved the supersede on 2026-11-25; `inv_4a53ca43` is locked in its place. It was requested in the implementation pull request, with a replacement whose test finds the latest version itself (`TemplateStore().latest("agents", "block")`), so later versions don't trip it either. Its test is never edited.
- **`inv_60788941` stays green.** It edits the first line where `agents/block@1` and `@2` differ, and version 3 keeps version 2's change on that line, so the edit still conflicts.

## Consequences

- One fewer tool to install, and nothing written outside the repository.
- Agents get the spec rule in every editor through the same block, with nothing per editor.
- Whether agents keep the spec current depends on the rule being followed: there is no automatic check, by the owner's choice. Reviewers (Copilot included) are the guard, through the pull-request template's checklist.
- The block grows by one rule; it stays within its target of under 40 lines (§19.9).
- New template versions for `agents/block`, `agents/prepare-pr` and `github/pr-template` reach existing repositories through `update`.
