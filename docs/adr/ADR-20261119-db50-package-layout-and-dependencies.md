---
id: ADR-20261119-db50
title: Package layout, build backend and runtime dependencies
status: ACCEPTED
date: 2026-11-19
scopes: ["pyproject.toml", "swerepo/", "uv.lock"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261119-db50: Package layout, build backend and runtime dependencies

## Context

The spec fixes the language and shape (§18: Python 3.11 or later, uv, one package `swerepo`, "a command-line library, a format-preserving TOML library, and the standard library") but leaves the specific choices open.

## Decision

1. **Python ≥ 3.11**, tested on 3.11 to 3.14.
2. **Flat layout:** the package lives in `./swerepo/`, with templates later under `swerepo/templates/<component>/` (spec §18). Built with **`uv_build`**, pinned to the uv minor version used in CI. Same as SeamSpec, so both projects share tooling and habits.
3. **Command-line library: Typer.** Same as SeamSpec; typed options, generated help, and a test runner (`typer.testing.CliRunner`). The `-u` shorthand for `update` (spec §7) is handled by rewriting the arguments before Typer parses them, when `update` arrives (Phase 6).
4. **TOML: tomlkit**, added when first used (Phase 1). It reads and writes TOML while keeping comments and formatting, which `.swerepo.toml` and table-level merges into an existing `pyproject.toml` (spec §6.3) need. The standard library's `tomllib` only reads.
5. **Nothing else at runtime** without a new ADR. YAML is not parsed with a library: the files SWERepo reads are ones it wrote, or are read as text (spec §6.8).
6. **Version** `0.1.0.dev0` until the owner approves a release. `__version__` comes from the installed package metadata, so `pyproject.toml` is the only place the version is written.
7. **Exit codes** follow spec §7. Running `swerepo` with no command shows the help and exits 2 (wrong usage), which is Typer's behaviour and matches the spec.

**Alternatives considered:**
- **argparse (no dependency).** Smaller install, but hand-written help and subcommand plumbing for about ten commands, and a different style from SeamSpec.
- **click directly.** Typer is click with type hints; the extra weight (rich, shellingham) is small next to the gain in consistency with SeamSpec.
- **src layout.** Protects against testing an uninstalled tree; uv always installs the project, so the benefit is small, and SeamSpec uses the flat layout.
- **hatchling.** Works, but a second build tool to learn; `uv_build` is what uv already uses.

## Enforced Invariants

None yet.

## Consequences

- Users get typer, click, rich and shellingham with SWERepo. Acceptable for a developer tool installed with `uv tool install`.
- Upgrading uv beyond 0.9 needs the `uv_build` pin and CI's uv pin moved together.
