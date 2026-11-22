# 2026-11-21 · Set up this repository with swerepo init (docs, agents)

**Branch:** `chore/dogfood-init`

## Done

- `uv run swerepo init --only docs,agents --yes` on SWERepo's own repository (dogfooding, spec principle 12): created `GEMINI.md`, `docs/agents/prepare-pr.md`, `docs/agents/address-review.md`, `docs/agents/record-adr.md` and this entry; added SWERepo's block to `AGENTS.md`; wrote `.swerepo.toml` (components `docs`, `agents`; editors Claude Code and Antigravity). Every existing document was kept. A second run: "Nothing to do."
- AGENTS.md's hand-written part trimmed to the rules particular to this repository; the rest is in SWERepo's block. `[pr] enforce = true`. ADR-20261121-d0f5 (this entry and the ADR were written by `swerepo init` and `swerepo adr new`, then filled in).
- `swerepo check --only docs,agents`: both complete.

## Next

- Phase 4: `ci` and `security`, after the owner's decisions on SeamSpec in CI and the security contact.
