---
id: ADR-20261123-5e14
title: "Dependabot owns action pins; update never moves a pin backwards"
status: REJECTED
date: 2026-11-23
scopes: ["swerepo/merge.py", "swerepo/check.py", "swerepo/prrules.py", "swerepo/templates/ci/"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261123-5e14: Dependabot owns action pins; update never moves a pin backwards

## Context
Dependabot now bumps the same action pins SWERepo's workflow templates carry (ADR-20261123-cc8d), so `update`'s three-way merge (spec §16) would conflict whenever both moved a pin, and `check` would call every Dependabot-touched workflow "changed by you".

From the conversation: The owner chose option A with three guards on 2026-11-23 (ADR-20261123-f571): strict pin-only lines, equal versions with different commits never guessed, and pr.workflows unchanged.

## Decision
Action pins are moved forward by Dependabot and by `update` with each template release, and `update` never moves one backwards. A line is a pin-only change only when the `uses:` action path before `@` is identical, the ref after `@` is a 40-character lowercase hex commit, the trailing `# v…` comment parses with `packaging.version.Version`, and nothing else on the line differs. In a merge conflict made only of such lines, the newer version wins line by line; a pin older than the repository's own after merging is set back to it. Equal versions with different commits are never guessed: a conflict in `update` and "changed by you" in `check`. `check` counts pin-only changes to newer versions as current. `check --base`'s `pr.workflows` keeps comparing with `record.written`, so pins hand-edited in a person's or agent's pull request still need an ADR.

## Enforced Invariants
None.

## Consequences
* Pins stay current within a week, and update never undoes a reviewed Dependabot bump.
* A repository without Dependabot still gets newer pins with each template release.
* Anything but a clean, parseable pin line is an ordinary edit: a conflict in update (never markers in the file), changed in check.
* Pins hand-edited outside Dependabot and update still need an ADR in their pull request.
* To lock once update exists: update never moves a pin backwards.
