---
id: ADR-20261122-a48e
title: "The security component: policy, privacy scan and ignored files"
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-22
scopes: ["swerepo/privacy.py", "swerepo/init.py", "swerepo/check.py", "swerepo/templates/security/", "SWEREPO-SPEC.md"]
invariants: []              # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261122-a48e: The security component: policy, privacy scan and ignored files

## Context

Phase 4 makes `swerepo init` apply the `security` component and makes `check` run the privacy scan (spec §6.4, §8). The spec asks for the security contact but doesn't say what SWERepo proposes when there is no address to give. This repository's own `SECURITY.md` was waiting on the same choice (`docs/PROGRESS.md`). The privacy rule this repository locked (inv_62d51113) already defines the allowances; `check` must apply the same ones without ever printing what it finds (inv_5e3b5ef3).

## Decision

1. **`SECURITY.md` is a starter file** (written once, the person's from then on, not recorded), from `security/policy@N`. The contact is asked in a terminal: **GitHub's private vulnerability reporting** (the default, and what `--yes` picks when the repository has a GitHub remote), an email address the person types, or a placeholder to fill in (the default without a GitHub remote). Private reporting publishes no address; the repository owner turns it on in the repository's settings. The owner chose it for SWERepo's own `SECURITY.md` (2026-11-22). An existing `SECURITY.md` is kept.
2. **The privacy scan** (`swerepo/privacy.py`) reads tracked files (or every file outside `.git` and tool caches without git), skipping binary files and files over 2 MB. It reports:
   - **personal email addresses**, with inv_62d51113's allowances: GitHub noreply addresses, reserved example domains, `git@` in SSH remotes, `[project]` authors and maintainers in `pyproject.toml`, any address in the security policy (`SECURITY.md`, `.github/SECURITY.md` or `docs/SECURITY.md`; P4-F05);
   - **home-folder paths** (`/Users/<name>`, `/home/<name>`, `C:\Users\<name>`), except placeholders (`me`, `user`, `you`, `username`, `name`, `runner`, `runneradmin`, `Shared`);
   - **obvious secrets**: private key blocks and well-known token formats (AWS access keys, GitHub tokens, Slack tokens, Stripe live keys, Google API keys, Anthropic keys, OpenAI keys in today's and the legacy format, PyPI and Hugging Face tokens; P4-F08).
   A line with `swerepo: allow-privacy` and files matching `[privacy] allow_paths` are skipped. The globs read as git's do: `*` and `?` stay within a folder, `**` spans any number of folders, and a folder covers what is in it (P4-F05); `swerepo/globs.py` matches them folder by folder in linear time (P4-F11), and the `ci` component uses it for uv workspace members too (P4-F10). Findings name the kind, the file and the line, never the matched text (inv_5e3b5ef3), and are capped in the message with a count of the rest.
3. **`check`** reports the scan as `security.privacy-scan` (✗ with `--ci` failing; it was `?` until Phase 4). `init` runs the same scan once and lists the findings in the plan, so they are fixed before the first commit.
4. **The privacy workflow** (`.github/workflows/swerepo-privacy.yml`, `security/privacy-workflow@N`, managed) runs `swerepo check --only security --ci` on pull requests and pushes. It records its own command (`[values] privacy_command`), so asking for it later never changes the CI workflow's inputs (P4-F02). It needs a SWERepo it can install, as the `governance` job does (ADR-20261122-4a06 point 5): a released SWERepo pins itself, SWERepo's own repository runs its checkout, and an unreleased build writes it only with `--with-governance`. On pull requests the `governance` job inside `ci-ok` runs the same findings, so a privacy finding blocks a merge where `ci` is set up; the separate workflow covers repositories that apply `security` alone, and gives the result its own name.
5. **`.gitignore`** gets a marked block (`security/gitignore@N`, recorded): `.env` files (keeping `.env.example`), `*.pem`, macOS and Windows folder files, JetBrains folders, and Claude Code's personal settings file. A missing `.gitignore` is created with the block.

**Alternatives considered:**
- **Ask for an email address always.** Puts a personal address in the repository unless the person makes a project one; private reporting needs none.
- **Print the matched text in findings.** `check` output goes to CI logs and PR annotations: printing a leaked address publishes it again.
- **A local secret scanner (gitleaks) as well.** A separate binary (spec §19.5); GitHub's secret scanning plus these patterns cover the obvious cases. Later, with the optional pre-commit component.

## Enforced Invariants

inv_62d51113 locks the same allowances for this repository's tracked files; inv_5e3b5ef3 keeps addresses and absolute paths out of `check` output. To propose once the scan works: the scan reports a planted email, home path and key by file and line, and its output never contains the planted text.

## Consequences

- SWERepo's own `SECURITY.md` can now be written: it points to private vulnerability reporting, turned on for `swerepo/swerepo` on 2026-11-23 (with `gh`, at the owner's request).
- A repository's `check --only security` and its CI report the same findings, by file and line only.
- The secret patterns are a floor, not a guarantee; GitHub's secret scanning (reported from Phase 5) is the broader net.
