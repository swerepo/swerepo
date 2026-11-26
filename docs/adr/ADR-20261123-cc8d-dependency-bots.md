---
id: ADR-20261123-cc8d
title: Dependency bots don't wait for Copilot, and Dependabot waits a week
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-23
scopes: ["swerepo/templates/ci/job-copilot-review/", "swerepo/templates/github/dependabot/"]
invariants: [inv_78f19f51, inv_abcc9759]  # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261123-cc8d: Dependency bots don't wait for Copilot, and Dependabot waits a week

## Context

ADR-20261123-a359 made merges wait for Copilot's review inside `ci-ok`. ADR-20261123-4e40 added a `dependabot.yml` with weekly updates. The first three Dependabot pull requests on this repository (#12–#14) passed every test, but `copilot-review` waited 20 minutes and failed on each, so `ci-ok` failed and none could merge. GitHub requests Copilot's review automatically only for authors who have Copilot, and Dependabot doesn't.

A Copilot review of a version bump would add little anyway: the diff is one version string, and the risk sits in the released code, which no review of the diff sees. What does guard dependency updates:
- actions pinned to a commit;
- `dependency-review` (known vulnerabilities);
- the tests, `zizmor` and the privacy scan;
- a person who merges, since nothing merges itself (`allow_auto_merge` is off; in `team` mode an approval is still required);
- time: a broken or malicious release is usually reported and pulled within days.

## Decision

The owner's decisions, 2026-11-23:

1. **Dependabot's pull requests pass the Copilot wait at once, while the update is Dependabot's alone.** These are pull requests opened by `dependabot[bot]`. Renovate isn't exempt: its commits carry no signature that GitHub vouches for, so only its name would speak for it, and a name can be faked (SeamSpec's reviewer). Its pull requests wait like anyone's. The job reads the author and its branch's repository through its `env:` block, never inside the script, and compares exact names. It passes only when both hold:
   - the branch is in this repository;
   - every commit on the pull request is the bot's own. Dependabot's must also be verified *and* committed by GitHub itself (`web-flow`), as its real commits are (checked on #12–#14). A verified signature alone isn't enough: someone with push access could commit in Dependabot's name and sign with their own key (SeamSpec's reviewer).

   A draft fails first, whoever opened it, a dependency bot included. GitHub lists at most 250 commits of a pull request, so a list that long fails closed: it may hide others (Copilot on PR #16).

   Otherwise, it **fails at once**, even with Copilot's review in (review DB-F01, the owner's choice). That covers a person or an agent pushing onto Dependabot's branch, a commit linked to no account, an unsigned commit in Dependabot's name, a fork, and no commits listed. A dependency update's pull request holds only the bot's commits, and changes by people or agents go in a pull request of their own, which waits for Copilot. Failing at once rather than waiting 20 minutes makes the reason plain. A look-alike name, a person, or another bot, a coding agent's included, always waits. Every other job still runs, and `ci-ok` still requires `copilot-review` to succeed on pull requests.
   - **The pull-request rules alike:** the `[pr] exempt_authors` exemption (`dependabot[bot]`) holds only while every commit on the pull request is the bot's own (review DB-F02). That includes merges: a person merging `main` into the bot's branch can carry changes of their own. Only GitHub's merge of the pull request into its base, which CI checks out, is left out (Copilot on PR #16).
2. **Dependabot's version updates wait until a new version is 7 days old:** `cooldown:` holding only `default-days: 7`, under each `updates` entry of `github/dependabot@1`. GitHub's documentation (checked 2026-11-23) says `default-days` works for `github-actions`, `uv` and `pip`, takes 1 to 90 days, defaults to 3 when unset, and applies to version updates only, never to security updates.
3. **Templates corrected in place:** `ci/workflow@2` (its fragment `job-copilot-review/2`) and `github/dependabot@1` haven't been released, so they change in place, as P5-F05 did. This repository's two files were unchanged since SWERepo wrote them, so `init` wrote them again from the new templates, as `update` would.
4. **The locked rule moves with it:** `inv_faa5bef5` is superseded by `inv_78f19f51` (approved by the owner). The new rule keeps everything the old one locked and adds the bot cases.

**Alternatives considered:**
- **Trust the pull request's author alone.** It stays `dependabot[bot]` even after a person pushes onto the branch, so a person's code could merge without Copilot's review (review DB-F01).
- **Let a mixed pull request wait for Copilot like anyone's.** GitHub never requests the review on a bot's pull request, so it would time out after 20 minutes. Keeping bots' and people's changes in separate pull requests is clearer.
- **Request Copilot on each Dependabot pull request by hand.** It works, but every weekly update would need a click and a re-run.
- **Have the job request Copilot's review itself.** That needs `pull-requests: write` for a job that runs on every pull request, against the least-privilege permissions `inv_faa5bef5` locked. It would also review a diff that shows nothing useful.
- **Skip the wait for every bot.** Coding agents open pull requests as bots too, and their code is exactly what Copilot's review is for.

## Enforced Invariants

- `inv_78f19f51` (critical, approved by the owner 2026-11-23): supersedes `inv_faa5bef5`, and locks that a bot's pull request holding anything but the bot's own commits fails at once.
- `inv_abcc9759` (critical, approved by the owner 2026-11-23): every `updates` entry has `cooldown: default-days: 7`, and `repo-settings.json` has `allow_auto_merge: false`.

## Consequences

- Dependabot's pull requests can merge once their checks pass and the owner merges them. #12–#14 need their CI re-run once this is on `main`.
- Updates arrive a week after release. Security updates, if turned on, still come as soon as a fix exists.
- Dependabot's changes to the workflows SWERepo manages make those files "changed by you". `update` (Phase 6) merges them with template changes three ways.
- *Amended by ADR-20261126-c228:* `inv_78f19f51` is to be replaced by a rule that keeps all of it and adds the read of the default branch's rules, which comes after Dependabot's checks: Dependabot's pull requests are decided exactly as here, and never read the rules.
