---
id: ADR-20261120-ecf7
title: .swerepo.toml is read and written with tomlkit, validated on load, and never overwritten by an older SWERepo
status: ACCEPTED
date: 2026-11-20
scopes: ["swerepo/state.py", "pyproject.toml", "SWEREPO-SPEC.md"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261120-ecf7: .swerepo.toml is read and written with tomlkit, validated on load, and never overwritten by an older SWERepo

## Context

`.swerepo.toml` records what SWERepo applied (spec §9): the standard, the version that wrote it, components, mode, the values templates were rendered with, a fingerprint per generated file, block and section, and settings such as `[privacy]` and `[pr]`. It is committed, so people read it in diffs and may add comments. Several SWERepo versions will meet the same file over time (a teammate on an older version, CI pinned to another).

## Decision

1. **tomlkit** reads and writes the file (runtime dependency announced in ADR-20261119-db50), so comments, key order and formatting a person added survive a rewrite.
2. **Validated on load.** Known keys must have the right types: `standard` a positive integer; `swerepo` a version string; `components` a list of known component names; `mode` `solo` or `team`; each `[files."<path>"]` and `[blocks."<path>"]` table a `template` id (ADR-20261120-b25a) and `rendered` and `written` 64-character hex fingerprints (ADR-20261120-9495). Paths are repository-relative, with `/`, written one way only: not empty or `.`, not absolute, no empty, `.` or `..` parts (`a//b`, `a/./b`), no trailing `/`, no backslashes or control characters. A file that can't be read (not UTF-8, unreadable) is a `StateError` too. A problem raises an error that names the key; SWERepo never guesses.
3. **Unknown keys are kept**, not rejected: a newer SWERepo may have added them. They survive a load and save unchanged.
4. **An older SWERepo never overwrites a newer one's file.** Loading is allowed (a read-only `check` can still report): for a file whose `standard` or `swerepo` version is newer than the running SWERepo, validation checks types but accepts component names and modes it doesn't know yet (review finding P1-F03); but saving refuses when the file's `swerepo` version is newer than the running one, or its `standard` is newer than the running SWERepo supports, with a message to upgrade.
5. **Writes are atomic:** a temporary file in the same folder, then a rename, so an interrupted run never leaves half a file.
6. **A new file starts with a one-line comment** saying it is written by SWERepo and should be committed (spec §9).
7. **`[projects] ignore`** (ADR-20261120-25b5) is a list of repository-relative folders, validated like other paths.

**Alternatives considered:**
- **`tomllib` + a hand-written TOML writer.** Loses people's comments and formatting.
- **JSON.** No comments, noisier diffs, and the spec chose TOML.
- **Reject unknown keys.** Breaks the moment two SWERepo versions share a repository.
- **Let any version overwrite.** An older SWERepo would silently drop fields it doesn't know (for example new fingerprints), and the next newer run would treat those files as a person's.

## Enforced Invariants

inv_d8603926 (comments and unknown keys survive a save) and inv_070db19c (a newer file loads but an older SWERepo never overwrites it), proposed in Phase 1.

## Consequences

- `tomlkit` (pure Python, no dependencies) ships with SWERepo.
- Phase 2's `check` reports a newer state file as "can't tell: upgrade SWERepo" instead of failing.
