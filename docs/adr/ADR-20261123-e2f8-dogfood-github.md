---
id: ADR-20261123-e2f8
title: This repository's GitHub settings are set up by swerepo init
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-23
scopes: [".github/", ".swerepo.toml"]
invariants: [inv_ef31cc79, inv_faa5bef5]  # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261123-e2f8: This repository's GitHub settings are set up by swerepo init

## Context

Phase 5 (PR #10) shipped `init` for the `github` component (ADR-20261123-4e40) and the wait for Copilot's review (ADR-20261123-a359). Until now this repository's ruleset, `ruleset.json`, CODEOWNERS and Copilot instructions were written by hand (ADR-20261119-75e6, ADR-20261120-1a27). Spec principle 12 says SWERepo's repository is set up by SWERepo. ADR-20261121-d0f5 did this for `docs` and `agents`, and ADR-20261123-d27b for `ci` and `security`.

The owner's choices (2026-11-23):
- `solo` mode;
- the owner's own login as code owner;
- squash-only merging;
- merges wait for Copilot's review.

## Decision

1. **Applied with SWERepo itself:** `uv run swerepo init --only github --mode solo --code-owner @<owner> --yes`, after the owner's go-ahead, 2026-11-23. It wrote:
   - `.github/swerepo/repo-settings.json`;
   - `.github/dependabot.yml`, with weekly updates for Actions and uv;
   - `.github/pull_request_template.md` and two issue templates;
   - SWERepo's review block at the end of `.github/copilot-instructions.md`, after the repository's own instructions;
   - `swerepo-ci.yml` rewritten to `ci/workflow@2`, which adds the `copilot-review` job inside `ci-ok`. It was unchanged since SWERepo wrote it;
   - `.swerepo.toml`, recording `github`, `mode = "solo"`, the code owner and `[github] applied = true`.
2. **Kept as they were:**
   - The hand-made `ruleset.json`. It is already `solo` with Copilot review and matches the ruleset on GitHub, so nothing was sent for it. It lacks the builder's `allowed_merge_methods`; the merge settings restrict merging to squash instead.
   - The hand-made CODEOWNERS block, which already names the owner on every governance path.

   Both stay the person's files: `check` compares them, and `update` (Phase 6) won't overwrite them.
3. **Merge settings applied on GitHub:**
   - merge commits and rebase merging off;
   - head branches deleted after merge;
   - the squash commit takes the pull request's title and body.

   The ruleset was already current.
4. **Fixed while applying it:** the plan asked the person to edit `ruleset.json` and CODEOWNERS even though both already held the choices given. The note now names only the flags a kept file lacks (`--mode`, `--code-owner`, `--copilot-review`), and it is left off CODEOWNERS when its SWERepo block already names the owner on every line (ADR-20261123-4e40 point 6). After Copilot's review of PR #11:
   - the flag is named as given (`--no-copilot-review`);
   - code-owner review is compared in the kept ruleset's own mode when no `--mode` is given, and `--code-owner none` counts as a choice too;
   - a file that links out of the repository is kept and never read, as elsewhere in `init`.

**Alternatives considered:**
- **Replace the hand-made ruleset with SWERepo's build.** It would add `allowed_merge_methods: ["squash"]`, which the merge settings already enforce. It would also replace a file the owner wrote for nothing. Running `init --only github --mode solo` again after deleting the file would do it.
- **Wait for `update` (Phase 6).** The settings would stay hand-made for another phase, and the Copilot wait, the point of ADR-20261123-a359, wouldn't protect this repository yet.

## Enforced Invariants

`inv_ef31cc79` locks that `init` changes GitHub only after a yes, and only the `swerepo` ruleset and the merge settings. `inv_faa5bef5` locks the Copilot wait in the workflow this repository now runs.

## Consequences

- From this pull request on, `ci-ok` here waits for Copilot's review. A review that arrives after the 20-minute wait needs the `copilot-review` job re-run.
- ADR-20261119-75e6 now holds only for `seamspec`, which SWERepo can't apply yet (Phase 7).
- Secret scanning and push protection are still off. They are the owner's settings, and `check` reports them as a warning.
