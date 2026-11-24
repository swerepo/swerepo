---
id: ADR-20261124-7afa
title: swerepo update builds on init's plan and merges from the rebuilt earlier render
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-24
scopes: ["swerepo/init.py", "swerepo/rebuild.py", "swerepo/merge.py", "swerepo/check.py", "swerepo/cli.py"]
invariants: ["inv_60788941", "inv_d60ffffd", "inv_9265607a"]  # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261124-7afa: swerepo update builds on init's plan and merges from the rebuilt earlier render

## Context

Spec §16 describes `swerepo update`. It re-renders what SWERepo manages with the current templates:
- a file or block nobody changed is replaced;
- a changed one is three-way merged from the earlier render, which is "rebuilt from the recorded template version and `[values]`, checked against `rendered`";
- a conflict is reported, never written;
- new items are added, and removed ones are reported.

`init` already plans every managed file and block (`_managed_file`, `_managed_block`). It marks each one `current`, `changed` (by the person) or `outdated` (the template renders differently, and nobody changed it). It also records the inputs a composed file was built from. The CI workflow, for example, is rendered by `ci.render_workflow(store, inputs, version)` from recorded `[values]`. Phase 6 builds the rest of `update` on that.

## Decision

1. **One planner.** `update` is `init`'s plan with the update verbs turned on, not a second walk over the components. It plans the same files and blocks with the same checks: links out of the repository, broken markers, files that appear between the plan and applying it. `init` keeps leaving outdated files for `update`.
2. **What happens to each managed item:**
   - **`current`:** nothing.
   - **`outdated`** (nobody changed it): rewritten with the new render, as `init`'s `rewrite` already does when asked (P4-F02). Its record gets the new template, `rendered` and `written`.
   - **`changed`** (the person edited it): `merge` when the merge is clean, shown as a diff. `conflict` otherwise: the file is left as it is and `swerepo diff` shows the change to make by hand.
     - **Applying a merge needs a deliberate choice** (the owner, 2026-11-24). In a terminal, the person's yes after seeing the diff. Without one, `--yes --merge`: `--yes` alone doesn't merge into files a person edited, so an agent's or a script's `update --yes` never does it unseen.
     - **A workflow that differs from the earlier render only by newer action pins** (`merge.pins_only_newer`) was moved by Dependabot, not edited by a person. It is updated with `--yes` alone.
   - **`yours`** (SWERepo never wrote it), and starter files: never touched.
   - **A JSON or TOML file that a merge or rewrite would leave unparseable** (a text merge can be clean and still break the syntax; review P6-F01): reported, never written. What `update` merges into `ruleset.json` and `repo-settings.json` is what is compared with GitHub and applied.
   - **The ADR folder's README:** its index is filled in on all three sides before the merge, as `swerepo adr index` keeps it (P6-F02).
3. **The earlier render (the merge's base)** is rebuilt from the record's template version, with the values and inputs recorded in `.swerepo.toml`. It is used only when its fingerprint equals the record's `rendered`. When it doesn't, a template changed in place since or an input wasn't recorded, so there is no trustworthy base: the item is reported as `can't merge (the earlier render can't be rebuilt)` and left as it is. SWERepo never merges against a guessed base.
4. **The merge** is `merge.merge3` (ADR-20261123-f571): git's three-way merge, with action pins settled first, never moving a pin backwards and never writing conflict markers. Blocks are merged as their content only. The text around a block is the person's and is never part of the merge.
5. **New and removed items:**
   - **New in the standard:** planned as `init` plans them (`create`, `add block`).
   - **Removed from the standard** (its template is no longer in this SWERepo): reported as `no longer in the standard: kept`, never deleted. An item a component didn't plan for another reason (a file it couldn't read, an editor no longer chosen) isn't reported as removed (review P6, question 4).
6. **Per component:** `--only` and the shorthand flags (`swerepo -u --ci`) work as for `init`. `ci`, brought along by `--only github` for the Copilot wait (P5-F01), changes only for that wait, as in `init`, never for its own updates (review P6-F08). `--dry-run`, `--yes` and `--json` as for `init`. Without a terminal and without `--yes`, nothing is written.
7. **GitHub settings:** `update --only github` changes the ruleset and merge settings only after a yes, exactly as `init` does. Locked rule `inv_ef31cc79` already covers it.
8. **`check`:** an `outdated` item names `swerepo update` (as today). A workflow that differs from SWERepo's render only by newer pins is current (ADR-20261123-f571 point 3), also after an `update` kept a newer pin; `update` and `status` say the same (P6-F03). `check` rebuilds the render with the same code `update` uses, read-only.
9. **`swerepo diff [FILE ...]`:** for each changed item, the merge's result against the person's file. For a conflict, the template's change to make by hand, as a unified diff of the earlier render against the new one. For an item that can't be merged, SWERepo's new version against the person's (P6-F07). It reads only, and never calls GitHub.
10. **Each record keeps the inputs its render used** (the owner's watchout, 2026-11-24). `[values]` keys are shared: `commands` and `test_inline` by `agents` and the PR template, and `default_branch` by `ci` and `security`. A partial run (`--only agents`), a conflict or a "can't merge" leaves some records unwritten. If such a run changed a shared value, those records' earlier renders could no longer be rebuilt.
    - **The snapshot:** every record SWERepo writes gets an `inputs` table, holding the values its render used and nothing more. `update` rebuilds a record's earlier render from its own `inputs`, while `[values]` holds the current values for new renders.
    - **Older records:** records written before this have no `inputs`. Their earlier render is rebuilt from this run's inputs or, for a plain template, from `[values]` as recorded before the run (the owner's backfill), and they get those inputs when the rebuild matches `rendered`. The fingerprint check (point 3) still refuses a wrong base.
    - **Values `update` refreshes:** `init` keeps rendering with recorded values, so its renders stay stable, and notes what changed. `update` renders with the project as it is now: its commands (`commands`, `test_inline`), the Python versions `requires-python` allows (the root project, listed projects, the privacy workflow), and SWERepo's own CI command when this SWERepo has one (a release, or this repository's own checkout; never replaced with none) (review P6-F06). The default branch stays recorded: without `origin/HEAD`, detecting it would guess. The per-record snapshots keep every earlier render rebuildable.
    - **Every older record is backfilled first:** before an `update` moves `[values]` on, every record without inputs, of any component, gets the values that rebuild it from `[values]` as recorded before the run, so a partial run never strands another component's record (P6-F04).
    - **Never personal data:** `inputs` never holds values from files SWERepo doesn't manage. The security contact, for example, is used only by the starter `SECURITY.md` and is never recorded with a record.
11. **`swerepo status`:** the components chosen, the mode, the standard and SWERepo versions, the tool pins, and counts of items current, outdated, changed and in conflict. It reads only, and never calls GitHub (P6-F07).

**Alternatives considered:**
- **`--yes` applying merges too.** An agent or a script could merge into a person's edits without anyone looking (the owner chose `--merge`).
- **Keeping a shared `[values]` key unchanged until every record using it is rewritten.** Every key would then need a list of the templates using it, and one stuck conflict would pin a value forever.
- **A separate `update` planner.** Two copies of every component's rules would drift apart.
- **Merging against the record's `written` text.** Only fingerprints are recorded, not texts: storing every render's text in `.swerepo.toml` would bloat it and could copy personal data into it.
- **Merging when the base can't be verified.** A guessed base can silently undo a person's edit; reporting is safer.

## Enforced Invariants

Locked by the owner on 2026-11-24, all critical:
- `inv_60788941`: `update` changes a file a person edited only with a deliberate yes (a terminal's yes, or `--yes --merge`), never writes conflict markers, leaves a conflict or an earlier render that can't be rebuilt byte for byte, and keeps the text around SWERepo's block.
- `inv_d60ffffd`: `update` never moves an action pin backwards, also when the new render moves the same pin or adds one; one version pinned to two commits is never guessed; Dependabot's newer pins alone need no `--merge` (ADR-20261123-f571).
- `inv_9265607a`: `update --dry-run` writes nothing; `update` changes only SWERepo's files and `.swerepo.toml`, never a file SWERepo didn't write; a second `update` writes nothing.

## Consequences

- Templates changed in place (as `ci/workflow@2` was before release) can't be merged against for repositories that recorded the old render; those report "can't merge" until the person updates by hand. That is another reason to version templates once released.
- `init` and `update` stay in step, because they share one planner.
