---
id: ADR-20261126-c228
title: The Copilot wait passes while no ruleset requests Copilot's review
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-26
scopes: ["swerepo/templates/ci/job-copilot-review/", "swerepo/cli.py", "swerepo/init.py", "SWEREPO-SPEC.md"]
invariants: [inv_b5d32550]  # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261126-c228: The Copilot wait passes while no ruleset requests Copilot's review

## Context

ADR-20261123-a359 made merges wait for Copilot's review: a `copilot-review` job inside `ci-ok`, written when the committed `ruleset.json` requests Copilot's review. ADR-20261123-cc8d let Dependabot's own pull requests through. GitHub requests Copilot's review automatically only through an active `copilot_code_review` rule. Since ADR-20261125-5f22 point 5, the ruleset is applied only after a terminal yes or `--yes --apply-github`, and the runbook applies it after the setup pull request merges.

Dogfooding on an established repository showed the gap:
- **The setup pull request waited for a review nothing requested.** It waited 20 minutes and failed, so `ci-ok` turned red. So did every pull request opened before the ruleset was applied, and in a repository that never applies it, every pull request would be red for good.
- **Nothing was actually let through.** The same ruleset is what makes `ci-ok` required, so before it is applied a red `ci-ok` blocks nothing. It's a red check people learn to merge past.
- **Asking by hand works.** `gh pr edit <n> --add-reviewer @copilot` got Copilot to review there, and the job passed. GitHub's REST `requested_reviewers` never lists Copilot; GraphQL's `reviewRequests` does.

Designed in `CODE_REVIEW.md` (review P8-C) and reviewed by Gemini over two rounds: options A (tell the person), B (read GitHub's rules) and C (write the job only once the ruleset is applied). The owner chose B with A's command, 2026-11-26.

## Decision

1. **The job reads the default branch's active rules once,** after the draft check and Dependabot's checks and before the wait: `gh api repos/<repo>/rules/branches/<default branch> --paginate`, keeping the rules whose `type` is exactly `copilot_code_review`.
   - **The default branch, not the pull request's base** (review P8-C03). A pull request opened against a branch no ruleset covers can't pass and then be retargeted to `main`: a retarget starts no run, and a re-run reuses the original event's values. The question is "does a ruleset here request Copilot's review?", which is the gap.
   - **Passed through `env:`:** the name comes from `github.event.repository.default_branch`, never inside the script. It's encoded as one path segment with `jq`'s `@uri` (`release/1.0` → `release%2F1.0`), since `gh` cuts a name at `#` and reads `/` as more path. An empty name fails at once (review P8-C01).
   - **A standalone assignment,** never inside a test where bash suspends `set -e` (review P8-C04).
2. **No such rule: the job passes at once.** It says that the ruleset isn't applied, that the job waits once it is, and how to ask Copilot anyway: `gh pr edit <number> --add-reviewer @copilot`.
3. **A rule: the job waits as before,** 40 asks 30 seconds apart. The failure message now names the same command beside the Reviewers box.
4. **A failed read fails at once, except GitHub Free's answer on a private repository** (review P8-C02). There, rulesets aren't available, so nothing can request Copilot. The owner checked the answer on a throwaway private repository on GitHub Free on 2026-11-26:
   - `gh api` exits non-zero;
   - on stdout it writes the body `{"message": "Upgrade to GitHub Pro or make this repository public to enable this feature.", "documentation_url": "https://docs.github.com/rest/repos/rules#get-rules-for-a-branch", "status": "403"}`;
   - on stderr it writes `gh: Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)`.

   The owner's check used their own `gh` login, not the token GitHub Actions gives the job (`GITHUB_TOKEN`). If GitHub words the answer differently for that token, the exact match fails the job: `ci-ok` turns red with `gh`'s own message, and the wait is never skipped. On GitHub Free a private repository's required checks aren't enforced, so there it is a red check to fix (by matching the token's wording, through a new ADR), not a blocked merge.

   The job branches on the exit status first, then passes only when `github.event.repository.private` is `true` and the whole of `gh`'s stderr is exactly that one line. It's compared as a whole string: no pattern, no search for the line among others. Everything else fails at once:
   - another message starting "Upgrade to GitHub Pro";
   - that message with more text before its status or after it, in another case, or beside another line;
   - the same message on a public repository;
   - another 403, a 401, 404 or 5xx.

   So any change in GitHub's text fails the job (red), never skipping a wait. Tightened after SeamSpec's reviewer found the first version accepted any line matching `^gh: Upgrade to GitHub Pro.*\(HTTP 403\)$`.
5. **`init` and `update` say so** wherever they leave the ruleset unapplied while the workflow waits for Copilot (review P8-C05): held for `--apply-github`, a terminal "no" to the ruleset, or `gh` missing or logged out. The note says that until a ruleset requests Copilot's review on the default branch, CI's `copilot-review` passes without waiting, and gives the command. It never shows under `--no-copilot-review`, when GitHub's `swerepo` ruleset already requests Copilot, or before a GitHub repository exists.
   - **Asked as CI asks** (Copilot on PR #24): whether a ruleset requests Copilot is read from the default branch's active rules, so an active ruleset that leaves the branch out counts as requesting nothing; if GitHub won't say, the ruleset's own enforcement and rules decide.
   - **A pass is promised only where it happens:** when the `copilot-review` job on disk doesn't read the rules (an older render still waits), the note says so instead, with `swerepo update --only ci` and the same `gh pr edit` command.
6. **Templates changed in place:** `ci/job-copilot-review@2` hasn't been released (no `v*` tag), as in ADR-20261123-cc8d point 3. This repository's `swerepo-ci.yml`, unchanged since SWERepo wrote it, is rewritten by `swerepo update`.

**Alternatives considered:**
- **A: tell the person to request Copilot on each pull request.** It needs one command on every pull request until the ruleset is applied, and on every pull request for good where it never is. Anyone who misses it waits 20 minutes and goes red. Its command is kept, in the note and the job's messages.
- **C: write the job only once `[github] applied` is true.** It needs a second pull request after applying, and leaves pull requests merged in between without a wait while the live ruleset already requests Copilot: the PR #3 problem ADR-20261123-a359 was written for. It also goes stale when the ruleset changes on GitHub.
- **Keying on the pull request's base branch.** It's more precise for stacked pull requests, but retargeting without a push would pass a pull request into `main` unreviewed (review P8-C03).
- **Reading the pull request's requested reviewers** (GraphQL `reviewRequests`). The ruleset's request can land after the job's first read, and anyone who can remove a reviewer could take Copilot off and pass.
- **Matching any 403 on a private repository.** It fails open: a private repository on a paid plan whose read is refused for another reason would pass without waiting.
- **Having the job request Copilot itself.** It needs `pull-requests: write` on every pull request (ADR-20261123-cc8d).

## Enforced Invariants

- `inv_b5d32550` (critical), locked by the owner on 2026-11-26 after Gemini's code review and two reads by SeamSpec's reviewer: replaces `inv_78f19f51` (superseded), keeping every one of its checks. It adds the single rules read of the default branch, encoded; the pass with no `copilot_code_review` rule (look-alikes included); the wait with one, on a later page among other rules; the Free-plan 403 on a private repository, as exactly gh's stderr and nothing near it; and every other failed read failing at once.
- `inv_09cc1c20` is unchanged: `ci-ok`'s step and `needs:` don't change.

## Consequences

- The pull request that adds SWERepo, and every pull request before the ruleset is applied, passes `copilot-review` at once. So does every pull request in a repository that never applies it, or a private repository on GitHub Free.
- Once the ruleset is applied, every pull request waits as before, whatever its base. A stacked pull request into a branch the ruleset doesn't cover waits for a review nothing requests, as before; its failure message names `gh pr edit <n> --add-reviewer @copilot`.
- A pull request opened before the ruleset was applied and re-run after it waits and fails: GitHub doesn't request Copilot on pull requests already open. The same command fixes it.
- One more GitHub read per pull request, with the permissions the job already has (`pull-requests: read`; every `GITHUB_TOKEN` also has `metadata: read`).
- If the default branch is renamed between a run and its re-run, the re-run reads the old name, which has no rules, and passes. Only an administrator can rename it, and an administrator can bypass the ruleset anyway.
- **Revisit in Phase 9** (protected `develop` and `release` branches): waits keyed to the pull request's base, and retargeting without a push (`edited`). `governance` and `lint-gradual` share the retargeting limitation.
