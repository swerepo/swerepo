---
id: ADR-20261123-f571
title: Dependabot owns action pins; update never moves a pin backwards
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-23
scopes: ["swerepo/merge.py", "swerepo/init.py", "swerepo/check.py", "swerepo/prrules.py", "swerepo/templates/ci/", "swerepo/templates/security/", ".github/workflows/"]
invariants: ["inv_d60ffffd", "inv_60788941"]  # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261123-f571: Dependabot owns action pins; update never moves a pin backwards

## Context

The workflows SWERepo writes pin every GitHub Action to a commit, with its version as a comment:

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
```

Two things move those pins. SWERepo's templates carry the pins current when each version was written, and `update` (Phase 6, spec §16) brings a repository to the latest template. Dependabot also proposes newer pins every week for the same lines (`github/dependabot@1`, ADR-20261123-cc8d), and the owner merges them (#12, #13).

A plain three-way merge (spec §16) would report a conflict whenever both moved the same pin. `check` would also call every workflow Dependabot touched "changed by you". Spec §16 said version pins are updated "only through `update`", which predates Dependabot.

## Decision

The owner chose option A on 2026-11-23: **Dependabot owns action pins, and `update` never moves a pin backwards.**

1. **What a pin-only change is.** All of these must hold, or the line is treated like any other:
   - both lines are `uses:` lines with the same action path before `@`;
   - the ref after `@` is a 40-character lowercase hex commit, never a tag or a branch;
   - the trailing comment is `# v<version>`: the version starts with a digit (no second `v`, no epoch) and parses with `packaging.version.Version`. It is kept as written, so `2026.03.01` stays `2026.03.01` (review M6-F02);
   - nothing else on the line differs: indentation, the `- ` and everything around the commit and the version are identical.
2. **`update`'s merge** (`swerepo/merge.py`). Before `git merge-file` runs, pins are settled line by line:
   - **Settled:** a pin line that each side either left alone or changed only as a pin, the repository's pin no older than the earlier render's. It is set, on all three sides (the earlier render, the repository's file and the new render), to the newest of the three. Pins then never differ between the sides, so they can't conflict. They can't move backwards either. Git would otherwise report a conflict when the template changes a neighbouring line, such as a `with:` line under a pin that Dependabot moved.
   - **A pin the person lowered** is their edit, not settled: git keeps it when the template left the line alone, and calls it a conflict when the template changed it or a neighbouring line (review M6-F03).
   - **Lines the new render adds:** a pin on them is raised to the repository's newest for that action.
   - **Line endings:** the three texts are compared as LF, since templates render LF. The result has the person's line endings: CRLF when their file uses only CRLF (review M6-F01).
   - **Never guessed:** one action pinned at one version to two different commits is a conflict: on one line against the other sides, on a line the new render adds, or across two lines of the person's file (SeamSpec's reviewer, 2026-11-24).
   - **Ordinary edits:** any other change to a pin line, such as a tag, more text on the line or a moved line, goes to git like any other line, so a clash with the other side is a conflict.

   A conflict leaves the file as it is: conflict markers are never written (point 4).
3. **`check`.** A managed workflow that differs from SWERepo's render only by pin-only changes to newer versions counts as current, not "changed by you". It is compared as fingerprints compare: BOM, line endings, trailing spaces and the final newline aside (review M6-F04). Equal versions with different commits, on a line or across two lines of one action, count as changed (`~`).
4. **No guessing.** When a version comment is missing, a ref isn't a full commit, the version doesn't parse, or anything else on the line changed, the line is an ordinary edit: a conflict in `update` (never conflict markers in the file), and "changed by you" in `check`.
5. **The pull-request rules don't change.** `check --base`'s `pr.workflows` still compares a workflow with `record.written`. A person's or an agent's pull request that edits pins by hand outside `update` still needs an ADR. Dependabot's pull requests are exempt (ADR-20261123-cc8d), and `update` records what it writes in `written`.
6. **Spec §16** now says SWERepo's `update` moves pins forward with its templates and never moves one backwards, and Dependabot may move them forward in between.

**Alternatives considered:**
- **B. SWERepo owns pins:** Dependabot would leave Actions alone. Pins would then be only as fresh as SWERepo's releases, with no weekly security fixes for actions.
- **C. Plain three-way merge:** both would move pins, and every collision would be a hand-fixed conflict after each update.

## Enforced Invariants

- `inv_d60ffffd` (locked, critical): `update` never moves a pin backwards, also when the new render moves the same pin or adds one; one version pinned to two commits is never guessed; Dependabot's newer pins alone need no `--merge`.
- `inv_60788941` (locked, critical): conflict markers are never written into a file.

SeamSpec's own record of this decision is ADR-20261124-b9d7 (accepted 2026-11-24), so `get_constraints` shows it for these files.

## Consequences

- Pins stay current within a week (Dependabot, after its 7-day cooldown), and `update` never undoes them.
- A repository without Dependabot still gets newer pins with each template release.
- Pins hand-edited outside Dependabot and `update` still need an ADR in their pull request.
