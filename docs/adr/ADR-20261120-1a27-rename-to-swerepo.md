---
id: ADR-20261120-1a27
title: The project is renamed SWERepo (package and command swerepo), hosted at swerepo/swerepo
status: ACCEPTED
date: 2026-11-20
scopes: ["swerepo/", "pyproject.toml", "SWEREPO-SPEC.md", "tools/pypi-placeholder/", ".github/", "docs/", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "README.md", "CHANGELOG.md"]
invariants: []
supersedes: ADR-20261119-13fc
superseded_by: null
---

# ADR-20261120-1a27: The project is renamed SWERepo (package and command swerepo), hosted at swerepo/swerepo

## Context

"Golden Repo" was a working name (spec §19.1). Before anything was pushed or published, the owner found several GitHub repositories named `goldenrepo` with similar ideas, and "golden repo" / "golden path" are generic platform-engineering terms that a project can't own in search. The GitHub organisation name `goldenrepo` already belongs to someone else, which is why ADR-20261119-13fc used `goldenrepo-dev`. Nothing had been committed, pushed or published, so renaming was close to free.

Checked on 2026-11-20: `swerepo` is free on PyPI, as a GitHub account or organisation name, and on npm; the only GitHub repositories with that name are three empty personal ones. Several other candidates were checked first (most dictionary words are taken everywhere).

## Decision

1. **Name: SWERepo.** "SWE" is how the coding-agent world names software engineering (SWE-agent, SWE-bench, Open SWE), so the name speaks to the target audience: teams building with coding agents. The owner wanted "repo" in the name.
2. **Spelling.** `SWERepo` wherever the name is shown (prose, README, PyPI title, organisation display name), because `swerepo` in lower case is hard to read. `swerepo` for the package, the command and file names.
3. **Hosting:** the organisation `swerepo` and the repository `swerepo`: `github.com/swerepo/swerepo`, public. The owner renames the empty `goldenrepo-dev` organisation (or creates `swerepo`); the empty `goldenrepo` repository is renamed to `swerepo`. Everything else in ADR-20261119-13fc (an organisation, public from the first push, pinned on the owner's profile, `CODEOWNERS`) stands; this ADR supersedes it only for the names.
4. **Independence.** SWERepo isn't part of, or endorsed by, SWE-agent, SWE-bench or Open SWE. The README says so, and no tagline borrows those names (for example "SWE-agent ready").
5. **Every name the spec defines is renamed** (spec v0.6):

   | Was | Now |
   |---|---|
   | Golden Repo, `goldenrepo` (package, command, module) | SWERepo, `swerepo` |
   | `.golden.toml` | `.swerepo.toml` |
   | `<!-- goldenrepo:begin -->` / `goldenrepo:end`, `goldenrepo:adr-index:…` | `<!-- swerepo:begin -->` / `swerepo:end`, `swerepo:adr-index:…` |
   | `goldenrepo: allow-privacy` | `swerepo: allow-privacy` |
   | `golden-ci.yml`, `golden-privacy.yml` | `swerepo-ci.yml`, `swerepo-privacy.yml` |
   | `.github/goldenrepo/` | `.github/swerepo/` |
   | ruleset `golden` | ruleset `swerepo` |
   | "the golden standard" | "the SWERepo standard" |
   | `GOLDENREPO-SPEC.md` | `SWEREPO-SPEC.md` |

6. **Records.** The spec, code, docs and the not-yet-merged ADRs use the new names. ADR-20261119-13fc keeps its original text and is marked superseded. `GOLDENREPO-BLUEPRINT.md` keeps its file name and text as the historical design input, with a note at the top. The Phase 0 review keeps the reviewer's words as written; a note maps old paths to new ones.
7. **PyPI.** The placeholder (ADR-20261119-d68b) becomes `swerepo 0.0.1`; the owner publishes it before the first push.

**Alternatives considered:** KeelRepo and SteadyRepo (free everywhere and more distinctive, but "keel" needs explaining and neither speaks to the agent audience as directly); AgentRepo (ambiguous: a repository *of* agents; GitHub name taken); VibeRepo (suggests the unreviewed AI coding the tool exists to prevent; taken on npm); keeping Golden Repo (generic, crowded, organisation name taken).

## Enforced Invariants

None. The proposed privacy rule's allow marker changes to `swerepo: allow-privacy` before the owner approves it.

## Consequences

- Searches for "swe repo" will mostly show SWE-agent and SWE-bench at first; consistent links from PyPI and the README matter.
- The owner renames (or creates) the GitHub organisation; the local `origin` remote moves to `github.com/swerepo/swerepo`.
- If a trademark search turns up a conflict before wide promotion, renaming again is still cheap until the first real release.
