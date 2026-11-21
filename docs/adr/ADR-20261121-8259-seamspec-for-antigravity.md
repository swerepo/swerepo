---
id: ADR-20261121-8259
title: SeamSpec is also set up for Antigravity, where the Gemini reviewer works
status: ACCEPTED
date: 2026-11-21
scopes: [".agents/", "AGENTS.md", "CLAUDE.md"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261121-8259: SeamSpec is also set up for Antigravity, where the Gemini reviewer works

## Context

ADR-20261119-6b94 point 1 set SeamSpec up for Claude Code only (`seamspec init --hosts none`), because the reviewer, Gemini, doesn't edit code. In Phase 1 a re-run of `seamspec init` without `--hosts none` detected Antigravity, the editor Gemini works in, and added SeamSpec's setup for it. The developer didn't notice, and the files were committed in Phase 1 (PR #2):

- `.agents/`: SeamSpec's eight skills (`seamspec-checkpoint`, `-context`, `-dead-end`, `-drain`, `-explain`, `-lock`, `-status`, `-supersede`), its reviewer agent (`.agents/agents/seamspec-reviewer.md`) and `.agents/hooks.json`, which runs `seamspec hook antigravity session-start` when a session starts and `seamspec hook antigravity stop` when the agent finishes;
- a SeamSpec block in `AGENTS.md` (between `<!-- seamspec:begin -->` and `<!-- seamspec:end -->`), the protocol for any agent that reads `AGENTS.md`.

Found in Phase 2, when `swerepo check` reported `GEMINI.md` missing because `.agents/` shows Antigravity is in use.

## Decision

1. **Keep it** (the owner's decision, 2026-11-21). Gemini works in this repository every phase, in Antigravity. With SeamSpec set up there, it sees the locked rules and pending reviews when a session starts, and SeamSpec checks the locked rules when it finishes, as for Claude Code.
2. **Antigravity is a supported editor here.** This amends ADR-20261119-6b94 point 1: re-runs of `seamspec init` use `--hosts antigravity` (still with `--no-ci`), not `--hosts none`, so they keep this setup rather than drop it.
3. **The two SeamSpec blocks stay.** Claude Code reads the protocol twice (`CLAUDE.md`'s own block, and `AGENTS.md`'s through `@AGENTS.md`), with command names in each tool's form (`/seamspec:drain`, `/seamspec-drain`). Both are SeamSpec's managed blocks, which `seamspec init` keeps current; editing them by hand would be undone on the next run.
4. **`GEMINI.md`** (pointing to `AGENTS.md`, spec §6.6) is added by Phase 3's `swerepo init --only agents`, which `check` already asks for; the owner records `[agents] hosts = ["claude", "antigravity"]` when `init` creates `.swerepo.toml`.

**Alternatives considered:**
- **Remove `.agents/` and the `AGENTS.md` block**, back to ADR-20261119-6b94. Gemini would then work without SeamSpec's hooks, so nothing would check the locked rules at the end of its sessions.
- **Remove only the `AGENTS.md` block** to avoid the duplicate. It is SeamSpec's managed block, and `seamspec init --hosts antigravity` would add it back.

## Enforced Invariants

None. SeamSpec's own setup is checked by `seamspec doctor` (Phase 7 adds it to `swerepo check`).

## Consequences

- The Gemini reviewer works under the same locked rules as the developer.
- Every `seamspec init` in this repository: `uv run seamspec init --mode enforced --no-ci --hosts antigravity`.
- `swerepo check` on this repository reports `GEMINI.md` missing until Phase 3.
