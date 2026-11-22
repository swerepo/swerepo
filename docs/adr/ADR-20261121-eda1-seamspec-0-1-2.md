---
id: ADR-20261121-eda1
title: Upgrade SeamSpec to 0.1.2
status: ACCEPTED
date: 2026-11-21
scopes: ["pyproject.toml", "uv.lock", ".claude/settings.json", "AGENTS.md", "README.md"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261121-eda1: Upgrade SeamSpec to 0.1.2

## Context

ADR-20261119-6b94 pins SeamSpec exactly (`seamspec==0.1.1` in `[dependency-groups] dev`), with the same version installed as a tool for the commit hook and the Claude Code plugin, and says to upgrade on purpose. SeamSpec 0.1.2 (released 2026-11-21) fixes the Claude Code plugin install on older Claude Code versions and makes `seamspec doctor` warn about a failed plugin install. It changes no rule, test runner or file format.

The owner upgraded the tool and ran `seamspec init`, which moved the Claude Code plugin to 0.1.2 in `.claude/settings.json`. The run had no `--no-ci`, so it also wrote `.github/workflows/seamspec.yml` again (unpinned actions; CI already runs SeamSpec in `ci.yml`, ADR-20261119-6b94 point 1). That file was deleted before any commit, as in Phase 1.

## Decision

1. **SeamSpec 0.1.2 everywhere:** `seamspec==0.1.2` in `pyproject.toml` (and `uv.lock`), the plugin at `v0.1.2` in `.claude/settings.json`, and `uv tool install seamspec==0.1.2` in `README.md` and `AGENTS.md`. CI uses the lockfile's version through `uv run`.
2. **Re-runs of `seamspec init` here:** `uv run seamspec init --mode enforced --no-ci --hosts antigravity` (ADR-20261119-6b94, ADR-20261121-8259). Without `--no-ci`, delete `.github/workflows/seamspec.yml` before committing.

**Alternatives considered:**
- **Stay on 0.1.1.** The tool on PATH (0.1.2) and the project's pin would differ, so the commit hook and CI would run different versions.

## Enforced Invariants

None. The 8 locked rules pass under 0.1.2, and `seamspec doctor` reports no errors or warnings.

## Consequences

- Contributors run `uv tool install seamspec==0.1.2` (or `uv tool upgrade seamspec`).
- Earlier records (`docs/reviews/phase-0.md`, ADR-20261119-6b94 point 2) keep naming 0.1.1: they describe what was true then.
