---
id: ADR-20261123-d27b
title: This repository's CI and security are set up by swerepo init
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-23
scopes: [".github/workflows/", "SECURITY.md", ".gitignore", ".swerepo.toml"]
invariants: []              # SeamSpec rule ids that enforce it, if any
supersedes: ADR-20261119-dd1a
superseded_by: null
---

# ADR-20261123-d27b: This repository's CI and security are set up by swerepo init

## Context

ADR-20261119-dd1a gave this repository a hand-written `ci.yml` until SWERepo could generate its own, and said the generated workflow would replace it in the pull request that applies it (point 5). Phase 4 (PR #8) shipped `init` for `ci` and `security`. Spec principle 12 says SWERepo's repository is set up by SWERepo and its CI runs `swerepo check` on itself. ADR-20261121-d0f5 did the same for `docs` and `agents`.

## Decision

1. **Applied with SWERepo itself:** `uv run swerepo init --only ci,security --yes`, by the owner's go-ahead ("Dogfood ci and security first"), 2026-11-23. It wrote:
   - `.github/workflows/swerepo-ci.yml` (Python 3.11–3.14, ruff);
   - `.github/workflows/swerepo-privacy.yml`;
   - `SECURITY.md`, pointing to GitHub's private vulnerability reporting, which is on for `swerepo/swerepo` (2026-11-23);
   - SWERepo's block in `.gitignore`;
   - `.swerepo.toml`, recording all four components.

   It kept this repository's own ruff and pytest settings.
2. **The hand-written `.github/workflows/ci.yml` is removed** in the same pull request, as ADR-20261119-dd1a point 5 planned. The generated workflow has every job it had (lint, test, test-macos, workflow-audit, seamspec, ci-ok), plus `dependency-review` and `governance`. Keeping both would give two checks named `ci-ok` for one required check, and every test would run twice.
3. **Governance runs this repository's own checkout:** `uv run --locked swerepo check --ci --base origin/<base> --author <login>`. Each pull request is checked by the SWERepo it contains, so the pull-request rules (`[pr] enforce = true`) now fail CI here, not only locally (spec §15).
4. **SeamSpec's job** runs through `uvx seamspec==0.1.2` (the `[tools]` pin) instead of the project's own dev dependency. It is the same version, and `uv.lock` still pins SeamSpec for local use.
5. **The ruleset is unchanged:** it requires `ci-ok`, which the generated workflow provides.

**Alternatives considered:**
- **Keep `ci.yml` beside `swerepo-ci.yml`.** Two `ci-ok` checks for one required name, and twice the CI minutes.
- **Edit `ci.yml` into the generated form by hand.** SWERepo would not record it, so `check` and `update` would treat it as the person's file.

## Enforced Invariants

`inv_09cc1c20` and `inv_2c3b6053` lock how `init` writes `swerepo-ci.yml`. `inv_62d51113` still guards this repository's tracked files; the privacy workflow now checks them too.

## Consequences

- ADR-20261119-dd1a is superseded. Its hardening (SHA pins, `persist-credentials: false`, `concurrency`, timeouts) and P0-F01's SeamSpec base logic live on in the template.
- A change to the CI template reaches this repository through `swerepo update` (Phase 6), like any other.
- ADR-20261119-75e6 now holds only for `github` and `seamspec`, which SWERepo can't apply yet.
