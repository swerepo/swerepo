---
id: ADR-20261119-13fc
title: The repository lives at goldenrepo-dev/goldenrepo, public; the package and command stay goldenrepo
status: SUPERSEDED
date: 2026-11-19
scopes: ["pyproject.toml", ".github/CODEOWNERS", "GOLDENREPO-SPEC.md"]
invariants: []
supersedes: null
superseded_by: ADR-20261120-1a27
---

# ADR-20261119-13fc: The repository lives at goldenrepo-dev/goldenrepo, public; the package and command stay goldenrepo

## Context

Spec §19.1 (name) and §19.2 (where it lives) were open. The project will be published on PyPI, which makes moving later costly: PyPI trusted publishing is tied to the exact owner and repository, and the URLs go into package metadata and docs. Checked on 2026-11-19: `goldenrepo` is free on PyPI; the GitHub organisation name `goldenrepo` belongs to someone else (created 2025-08-01, no public repositories); `goldenrepo-dev` was free.

## Decision

1. **A GitHub organisation, `goldenrepo-dev`, owned by the owner's personal account**, with the repository `goldenrepo` in it: `github.com/goldenrepo-dev/goldenrepo`. Decided by the owner.
2. **The package and command stay `goldenrepo`.** The organisation name doesn't need to match; `pip install goldenrepo` is what users type. Reserving the PyPI name is the owner's call (spec §18).
3. **Public from the first push.** On GitHub's Free plan, rulesets aren't enforced on private repositories, and dependency review and build provenance need a public repository (spec §6.2, §6.9, §12). Golden Repo should run under its own standard from Phase 1.
4. **The organisation is created by the owner** on github.com (organisations can only be created there), with the owner's membership set to public. **The repository** was created empty and public (no README, license or `.gitignore`, which would clash with the first commit) by the developer through `gh`, at the owner's explicit request on 2026-11-19. The developer never creates accounts, organisations or repositories on its own initiative.
5. **After the first push**, a ruleset requiring `ci-ok` is applied by hand, so every later phase lands through pull requests. Golden Repo applies its own ruleset from Phase 5.
6. **Visibility for the owner:** the repository is pinned on the owner's profile, with SeamSpec's.
7. **`CODEOWNERS`** names the owner's GitHub account for the governance paths (spec §6.1), in a marked block at the end of the file.
8. Spec §19.1 and §19.2 are marked as decided.

**Alternatives considered:**
- **The owner's personal account.** Shows directly on the profile with no setup, but moving to an organisation later means re-pointing PyPI publishing and every URL. Pinning gives the same visibility from an organisation.
- **The `seamspec` organisation.** Golden Repo is broader than SeamSpec (SeamSpec is one optional component); sharing the organisation would suggest it is a SeamSpec add-on.
- **Private until the first release** (as SeamSpec was). Phases 1 to 5 would run without an enforced ruleset.
- **Waiting for the `goldenrepo` organisation name.** GitHub's process for inactive names is slow and uncertain.

## Enforced Invariants

None.

## Consequences

- Package metadata links to `github.com/goldenrepo-dev/goldenrepo` (home, source, issues, changelog).
- CI runs on the first push; the ruleset follows right after.
- If the `goldenrepo` organisation name ever becomes available, moving is possible but needs PyPI's trusted publisher and the metadata URLs updated in the same change, with a new ADR.
