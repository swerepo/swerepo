---
id: ADR-20261123-4e40
title: The github component and swerepo threads
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-23
scopes: ["swerepo/github.py", "swerepo/threads.py", "swerepo/init.py", "swerepo/check.py", "swerepo/cli.py", "swerepo/templates/github/", "SWEREPO-SPEC.md"]
invariants: []              # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261123-4e40: The github component and swerepo threads

## Context

Phase 5 makes `swerepo init` apply the `github` component (spec §6.1, §12) and adds `swerepo threads` (§7, §12). The spec leaves open:
- how the ruleset and merge settings, which are JSON, are rendered when templates hold no logic (ADR-20261120-b25a);
- how `init` talks to GitHub and what happens without a GitHub repository;
- what `check` compares on GitHub, and how without breaking its read-only and `--ci` promises.

Building SWERepo's own CI on PR #9 also showed that dependency review fails `ci-ok` when GitHub's dependency graph is off, and nothing warned about it.

## Decision

1. **Files** (spec §6.1):
   - **Settings files, managed:** `.github/swerepo/ruleset.json` and `.github/swerepo/repo-settings.json`.
   - **Managed templates:** `.github/copilot-instructions.md` (a marked block when the file exists, spec §10), `.github/dependabot.yml` and `.github/pull_request_template.md`.
   - **Starter files:** the issue templates (`.github/ISSUE_TEMPLATE/bug.md`, `feature.md`).
   - **CODEOWNERS:** SWERepo's marked block at the end, in an existing CODEOWNERS or a new `.github/CODEOWNERS`.

   Existing files are kept, as for every component.
2. **The JSON settings are built in Python** (`swerepo/github.py`), as the templates README allows for structured files. Each builder is named like a template (`github/ruleset@1`, `github/repo-settings@1`) and kept for good once released, so `update` can rebuild an earlier render. `check` treats a builder id as a template version.
3. **The ruleset** is named `swerepo` and targets the default branch (`~DEFAULT_BRANCH`), with no bypass actors. Rules:
   - deletion and non-fast-forward blocked;
   - a pull-request rule: 0 approvals (`solo`) or 1 with stale approvals dismissed (`team`); code-owner review in `team` only once CODEOWNERS names a real owner; thread resolution required when Copilot review is on, or in `team`; merges limited to the methods `repo-settings.json` allows;
   - the required check `ci-ok`, plus `[github] extra_required_checks`;
   - `copilot_code_review` (not on push, not on drafts) unless the person turns Copilot review off.
4. **Merge settings:** squash only (`allow_squash_merge` true, merge commits and rebase off), head branches deleted after merge, auto-merge off. The pull request's title becomes the squash commit's title.
5. **What init asks** (spec §12, "always shown first"):
   - the mode: `solo` by default for a user-owned repository, `team` for an organisation's, shown with what each means;
   - the code owner: an `@login` or `@org/team`, default the repository owner when that is a user, never guessed from git config;
   - Copilot review: on by default.

   `--mode` and `--code-owner` answer the first two in scripts. In a terminal, `init` asks only what no flag and no earlier run decided, with the detected default. `none` is an answer too: it is recorded, so the repository owner isn't proposed again. Without an owner, CODEOWNERS isn't written, code-owner review stays off, and `check` warns without failing (review P5-F03, P5-F04).
6. **Applying through `gh`** with the person's own login:
   - **Shown first:** the plan shows the ruleset and the merge settings as JSON, each asked separately (`Apply ruleset "swerepo" on main?`, `Apply merge settings?`). `--yes` answers both; without a terminal and without `--yes`, both are skipped and the plan prints the command to run.
   - **Ruleset:** found by name among the repository's rulesets. Updated in place (`PUT`) when it exists, so a hand-made `swerepo` ruleset is adopted, and created (`POST`) when it doesn't. Other rulesets are never touched. Merge settings are one `PATCH` of the repository.
   - **What is applied:** the committed `ruleset.json` and `repo-settings.json` when they exist, a person's edits included, and a fresh build only for a file `init` creates in the same run (review P5-F02). A file that isn't a JSON object is reported, and nothing is applied from it.
   - **What is never applied** (Copilot's review of PR #10): a `ruleset.json` whose `name` isn't `swerepo`, since later runs couldn't find it by name and would make another; and a `repo-settings.json` holding fields beyond the merge settings (`allow_*_merge`, `allow_auto_merge`, `allow_update_branch`, `delete_branch_on_merge`, the merge and squash commit title and message, `use_squash_pr_title_as_default`), so applying it can't, say, make a private repository public. The plan says why and applies the other file; `check` reports it as missing; `apply_ruleset` and `apply_settings` refuse such a payload before anything is sent.
   - **Recorded:** `[github] applied = true` once GitHub was read, both files were compared, and nothing is left to apply, whether `init` applied it or it already matched. When GitHub can't be read (a refused request, say), the recorded value is kept; when a file can't be compared (missing, not JSON, or never applied as above), it is `false` (Copilot's review of PR #10).
   - **Choices given later:** `--mode`, `--code-owner` or `--copilot-review` on a set-up repository rewrite an unchanged `ruleset.json` SWERepo wrote. `--code-owner` likewise rewrites an unchanged SWERepo block in CODEOWNERS, leaving the person's own lines byte for byte. Each choice is recorded in `.swerepo.toml` only where the files carry it: the mode once the ruleset holds it, the code owner once CODEOWNERS does. A changed ruleset or block is left as it is, and the plan says to edit it (review P5-F10). With a kept ruleset and no `--mode`, the mode shown, asked and recorded is the one the committed ruleset is in: `team` when it requires an approval (review P5-F14).
   - **No GitHub repository** (no `origin` on github.com): the files are written, the plan says "waiting: no GitHub repository yet", `[github] applied = false`, and the next steps are printed (spec §12).
   - **On GitHub, but `gh` missing or logged out:** the plan says "waiting: gh isn't installed or logged in", and the next steps keep the usual branch and pull request, then ask to log in (`gh auth login`) and run `swerepo init --only github` (Copilot's review of PR #10).
7. **`check` reads GitHub only through `gh`, never with `--ci`**, and only when `gh` is logged in. Each item is reported, or `?` with the reason:
   - the live ruleset `swerepo` and the merge settings match the committed files (compared field by field, ignoring fields GitHub adds);
   - secret scanning and push protection are on;
   - the dependency graph is on (dependency review needs it).

   `check` stays read-only: `gh api` GET requests only.
8. **The dependency graph** (the gap PR #9 found): `init`'s `ci` plan says that dependency review needs GitHub's dependency graph; `check` reports it (point 7). On a private repository it isn't needed, since dependency review is skipped there. Only GitHub's 404 means "off"; any other failure reads as "can't tell" (review P5-F06).

   **GitHub itself:** a remote counts only when its host is `github.com`, not a name that merely contains it (review P5-F06). **`github` applied on its own** after `ci` also brings an unchanged `swerepo-ci.yml` to version 2 with the Copilot wait, and records the workflow's own `ci_copilot_review`; `check` reports a workflow whose wait disagrees with the ruleset (review P5-F01).
9. **`swerepo threads <pr>`** lists the open (unresolved) review threads of a pull request through `gh api graphql`:
   - each thread with its file and line, whether it is outdated, its first comment's author, and the first line of its last comment;
   - `--json` for scripts.

   It only reads; it never replies or resolves (spec §17).
10. **Agents:** `agents/block@2` names `swerepo threads` in rule 7 and `agents/address-review@2` uses it. The `@1` versions stay; repositories set up with them get the new ones through `update` (Phase 6), and `check` reports `↑`.

**Alternatives considered:**
- **Ruleset templates per variant.** Mode × Copilot × code owner × extra checks multiply; a builder per version is one readable function.
- **JSON values through `@@name@@` placeholders.** Against the templates README: a misplaced value breaks the JSON silently.
- **`check --ci` reading GitHub.** CI must never need more than the checkout (spec §15); a token with admin read isn't there.
- **Writing a new ruleset beside a hand-made one.** Two rulesets with overlapping rules; adopting by name keeps one.

## Enforced Invariants

To propose once the code works: `check` never writes to GitHub (only GET requests reach `gh`); and `init` never changes a ruleset not named `swerepo`.

## Consequences

- A repository's rules live in its history as reviewable JSON. A person may edit them, and the next `init` or `update` applies the committed file.
- A repository on a plan where rulesets aren't enforced still gets the files. `check` can't tell the plan from the repository alone, so it says so (`?`) rather than guess.
- `swerepo threads` makes the runbooks' "answer every thread" step one command.
