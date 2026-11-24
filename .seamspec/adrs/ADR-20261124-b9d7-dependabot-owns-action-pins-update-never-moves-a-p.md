---
id: ADR-20261124-b9d7
title: "Dependabot owns action pins; update never moves a pin backwards (matches ADR-20261123-f571)"
status: ACCEPTED
date: 2026-11-24
scopes: ["swerepo/merge.py", "swerepo/init.py", "swerepo/check.py", "swerepo/prrules.py", "swerepo/templates/ci/", "swerepo/templates/security/", ".github/workflows/"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261124-b9d7: Dependabot owns action pins; update never moves a pin backwards (matches ADR-20261123-f571)

## Context
SWERepo's workflow templates pin every GitHub Action to a commit with its version as a comment (`uses: owner/action@<commit>  # v<version>`), in `swerepo-ci.yml` and `swerepo-privacy.yml`. Two things move those pins: `update` brings a repository to the latest template, and Dependabot proposes newer pins every week for the same lines (ADR-20261123-cc8d). A plain three-way merge would report a conflict whenever both moved a pin, or when the template changed a line next to a pin Dependabot moved, and `check` would call every Dependabot-touched workflow "changed by you". The repository's own record of this decision is ADR-20261123-f571 (ACCEPTED); this SeamSpec decision mirrors it so `get_constraints` shows it for the files it governs. It replaces the earlier proposal ADR-20261123-5e14, which described the merge loosely.

From braindump item `ADR-20261123-f571`: ADR-20261123-f571 (ACCEPTED; the owner chose option A with three guards on 2026-11-23). Re-proposed on the owner's request (2026-11-24) to match f571 as built, after SeamSpec's reviewer found ADR-20261123-5e14 out of date; 5e14 is to be rejected in review.

## Decision
Dependabot owns action pins between SWERepo releases, and `update` never moves a pin backwards (the owner's option A, 2026-11-23).
1. A pin-only change: both lines are `uses:` lines with the identical action path before `@`; the ref is a 40-character lowercase hex commit; the comment is `# v<version>` whose version starts with a digit (no second `v`, no epoch), parses with `packaging.version.Version`, and is kept as written (`2026.03.01` stays so); nothing else on the line differs.
2. `update`'s merge (`swerepo/merge.py`) settles pins before `git merge-file` runs, line by line across all three sides (the earlier render, the person's file, the new render), aligned with difflib: a pin line each side left alone or changed only as a pin, with the person's pin no older than the earlier render's, is set on all three sides to the newest of the three, so pins never conflict and never move backwards. A pin the person lowered is their edit, left to git. A pin on a line the new render adds is raised to the repository's newest for that action. Texts are compared as LF and the result keeps the person's CRLF when their file uses only CRLF.
3. Never guessed: one action pinned at one version to two commits is a conflict, on one line against the other sides, on an added line, or across two lines of the person's file. A conflict leaves the file as it is; conflict markers are never written.
4. `check` counts a managed workflow that differs from SWERepo's rebuilt render only by newer pins as current (also after an `update` kept a newer pin); equal versions on different commits count as changed. Only files under `.github/workflows/`.
5. A workflow that differs from the earlier render only by newer pins (Dependabot's) is updated by `update --yes` without `--merge`.
6. `check --base`'s `pr.workflows` still compares with `record.written`: pins hand-edited in a person's or agent's pull request still need an ADR.
Enforced by the proposed rule inv_d60ffffd (and inv_60788941 for conflict markers).

## Enforced Invariants
None.

## Consequences
* Pins stay current within a week (Dependabot, after its 7-day cooldown), and `update` never undoes them.
* A repository without Dependabot still gets newer pins with each template release.
* Anything but a clean, parseable pin line is an ordinary edit: a conflict in `update` (never markers in the file), changed in `check`.
* A template release that lowers a pin can't take effect over a newer repository pin; released templates are to be locked in Phase 8.
* Pins hand-edited outside Dependabot and `update` still need an ADR in their pull request.
