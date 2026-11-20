---
id: ADR-20261119-d68b
title: Reserve the PyPI name with a 0.0.1 placeholder, published by the owner
status: ACCEPTED
date: 2026-11-19
scopes: ["tools/pypi-placeholder/", "SWEREPO-SPEC.md"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261119-d68b: Reserve the PyPI name with a 0.0.1 placeholder, published by the owner

## Context

The repository `github.com/swerepo/swerepo` is public (ADR-20261119-13fc; names from ADR-20261120-1a27), so the name is visible, but `swerepo` on PyPI is unclaimed: PyPI gives a name to whoever uploads first, and configuring a trusted publisher in advance doesn't reserve it. The first real release is Phase 8. SeamSpec solved the same gap with a placeholder upload.

## Decision

1. **A separate placeholder package**, `swerepo` version **0.0.1**, in `tools/pypi-placeholder/`: a README for the PyPI page, the Apache-2.0 license, project links, and a `swerepo` command that says the tool isn't released yet and exits 1. No dependencies.
2. **Not the real package.** The real package (`0.1.0.dev0`) isn't committed yet, and a release should be built from a commit, not a working tree. The placeholder has no code worth reviewing, so it doesn't depend on Phase 0's state. `0.0.1` sorts below every real version, so `pip install swerepo` picks the real release once it exists.
3. **Published by the owner** from their own machine with their own PyPI account and token: `uv build` in `tools/pypi-placeholder/`, then `uvx twine upload dist/*`, which asks for the token. The developer prepares and checks the build (`twine check`, a test install) but never handles tokens or uploads (spec §18).
4. **After the first real release** (Phase 8), the owner yanks 0.0.1 on PyPI, so nothing resolves to it by accident, and `tools/pypi-placeholder/` is deleted in that release's PR.
5. **Trusted publishing** for real releases is configured on the then-existing PyPI project in Phase 8, pointing at `swerepo/swerepo`'s release workflow.

**Alternatives considered:**
- **Publish the current `0.1.0.dev0`.** Built from an uncommitted tree, with only `--version`; a pre-release whose behaviour with `pip install` (no `--pre`) is less obvious to users than a placeholder that explains itself.
- **A PyPI "pending publisher".** Doesn't reserve the name; someone else can still upload first.
- **Wait for Phase 8.** Leaves the name open for weeks while the repository advertises it.

## Enforced Invariants

None.

## Consequences

- `pip install swerepo` installs a command that only points to the project, until Phase 8.
- The PyPI page shows "Development Status :: 1 - Planning" and links to the repository.
- One more cleanup step in Phase 8 (yank and delete).
