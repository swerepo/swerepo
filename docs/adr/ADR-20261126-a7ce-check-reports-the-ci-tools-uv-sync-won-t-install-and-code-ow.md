---
id: ADR-20261126-a7ce
title: check reports the CI tools uv sync won't install, and code owners GitHub doesn't know
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-26
scopes: ["SWEREPO-SPEC.md", "swerepo/check.py", "swerepo/init.py", "swerepo/ci.py", "swerepo/github.py", "swerepo/cli.py", "swerepo/commands.py", "tests/fake_gh.py"]
invariants: []              # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261126-a7ce: check reports the CI tools uv sync won't install, and code owners GitHub doesn't know

## Context

Dogfooding SWERepo on an established repository (ADR-20261125-5f22) found two gaps in `swerepo check` (spec §15):

1. **The tools CI runs.**
   - `swerepo-ci.yml`'s jobs run `uv run pytest` and ruff or the kept linters, after `uv sync`.
   - When `uv sync` doesn't install them, `init`'s plan says so once, when the workflow is created (ADR-20261125-5f22 point 3). `check` never repeated it.
   - The person who missed the note found out only when the setup pull request's CI failed.
2. **A code owner GitHub doesn't know.**
   - The code-owner question's own example, `@login`, was recorded and written into CODEOWNERS.
   - `init` and `check` checked the syntax only. GitHub ignores an owner who doesn't exist or lacks write access, so in team mode the governance paths had no effective code owner.

Read-only GETs on GitHub settled what the lookups can rely on (2026-11-26, review P8-K):
- **Unknown logins:** `users/login` and `orgs/org/teams/team` answer 404, and `collaborators/{login}/permission` answers 404 "`<login>` is not a user", not "Not Found". Without push access, it answers 403 for real and unknown logins alike, while `users/{login}` still tells them apart.
- **Teams:** `orgs/{org}/teams/{team}` answers 404 for a team that exists when the caller isn't a member, and listing the organisation's teams answers 403 to a non-member.

The design was reviewed by Gemini in two rounds (`P8-K01` to `P8-K07`, all accepted) and agreed by the owner on 2026-11-26; the code review (`P8-K08` to `P8-K11`) hardened it.

## Decision

1. **`check` reports the tools CI runs that `uv sync` won't install.**
   - **Items:** `ci.tools` for the root project and `ci.tools.<folder>` for each listed project. Their paths match `ci.tests`, never `pyproject.toml`'s.
   - **What's needed:** from the inputs recorded with `swerepo-ci.yml`, or for an older record `[values] lint`, `[adopted] linters` and `[projects.inputs]`. A recorded project's folder must be one SWERepo writes (`valid_folder`), and a folder linked out of the repository is never read (review P8-K08).
   - **When:** only while the workflow is as SWERepo wrote it, or differs only by newer action pins (Dependabot's). An edited workflow may install differently.
   - **Left out:** a project uv can't install (Poetry's lock without uv's), where `uv add` is the wrong advice.
   - **A Makefile changes nothing here:** the CI jobs run `uv run` whatever its targets.
   - **One wording:** `init`'s plan note and the finding come from the same functions in `swerepo/ci.py`. `Finding.fix` is the runnable command: `uv add --dev pytest ruff`, or `uv add --directory api --dev …` for a listed project. `init`'s note says the same, in place of "(… in api)".
2. **It's a warning, never blocking.** It never fails `check --ci`, and the `::warning` annotation sits next to the red job.
   - CI fails without the tools anyway, so a blocking finding inside that CI would add a second red job saying the same thing.
   - The names read are the declared ones, so a tool installed through another (pytest through pytest-cov) would be reported though CI runs it. A warning can't turn a green CI red over that.
   - It has the same shape as `ci.tests` (ADR-20261125-5f22 point 2).
   - Reading `uv.lock`'s resolved graph waits for Phase 11: a flat read would count an optional extra's packages as installed.
3. **The agents' commands, said once.** `agents.tools`, a warning, reports what `AGENTS.md`'s test and lint commands run through `uv run` that `uv sync` won't install, in `init`'s words.
   - **Read from:** the block's own commands, and only while it is as SWERepo wrote it, never from `[values] commands` edited apart from it. Only a tool from the fixed set counts (`pytest`, `ruff`, the kept linters), never a flag, a path or an address (review P8-K09).
   - **Left out:** when `ci.tools` was evaluated in the same run, and for a Makefile target or Poetry, which run their own tools.
   - **Where the code moved:** `commands()` went from `init.py` to `swerepo/commands.py`, because `check` can't import `init`.
   - **After Copilot's review of PR #25:**
     - "As SWERepo wrote it" means as rendered, never as merged. After `update --merge`, a record's `written` holds the person's edits, which may install differently, so neither warning runs from it.
     - `agents.tools` leaves out only the tools the root's CI jobs run, which `ci.tools` reports; a tool only `AGENTS.md` runs is still said.
     - The fix names a group `uv sync` installs: `--dev` when `dev` is among `[tool.uv] default-groups` (or by default), else `--group <the first listed>`. With no such group, the note says to add `dev` there.
     - A group's or an optional extra's name is repeated only when it is a valid name; any other key, an address in a quoted TOML key included, is never shown.
4. **A warning never hides a blocking gap.** `check` shows one line per missing file. It now drops a blocking record finding only for another blocking finding or a `✓` at the same path, never for a warning.
5. **`check` reads SWERepo's CODEOWNERS block, offline too.**
   - **How the block is read:** as rule lines, with `#` comments skipped.
   - **Each of these is missing and blocking, under `--ci` too:**
     - no rules;
     - a rule with no owner;
     - the question's examples (`@login`, `@org/team`, one source: `github.OWNER_EXAMPLES`);
     - an owner GitHub can't read.
   - **Never printed:** an unreadable owner. The message names its rule's place instead, since it may be an address with a typo.
   - **Order:** the block is checked before the lines after it, so a problem in it isn't masked.
6. **`check` looks the block's owners up on GitHub** (`github.code-owner`).
   - **When:** only with `gh` logged in, never with `--ci`, GET requests only (ADR-20261123-4e40).
   - **A user:**
     - the repository's owner (any case) needs no call;
     - otherwise `collaborators/{login}/permission` answers whether it exists, is a person and can write;
     - on a 403, `users/{login}` still says whether it exists.
   - **A team:**
     - it must belong to the organisation that owns the repository, checked with no call;
     - a 404 is settled by listing the organisation's teams: if they can be listed, the team doesn't exist; otherwise `check` can't tell;
     - a secret team, and a team without write access here, are reported.
   - **Statuses:** a problem is missing and blocking. What can't be read is `?`. Email owners aren't looked up or printed.
   - **Offline:** the "can't tell" line names the code owner too.
   - **`GitHubError`** carries the HTTP status (GitHub's JSON `status`, else gh's `(HTTP nnn)`), and a 404 is `not_found` whatever its message (review P8-K07).
7. **`init`, given a code owner** (`--code-owner`, or the terminal's answer):
   - **Refused (exit 2, or asked again in a terminal):** the question's examples, offline too, and what GitHub says can't be one (no such user, an organisation, a team of another organisation or on a user's repository, no such team the caller can see). Nothing is written.
   - **Written, with a plan note:** an owner without write access yet (access can be granted after setup).
   - **Accepted with a "not checked on GitHub" note:** what can't be checked (offline, a 403, a timeout). `check` looks it up once it can. Notes aren't changes, so a second run still says "Nothing to do.".
8. **A recorded example owner** (the established repository's state):
   - **In a terminal:** asked again, offering the repository's owner when it's a person and `none` otherwise.
   - **Without a terminal:** nothing is written from it, and a note names the fix. `check` points "Next:" at `--code-owner …` when CODEOWNERS is missing too (review P8-K10).
   - **The ruleset keeps its render:** `settings.code_owner` stays the recorded value, because `require_code_owner_review` is built from it. Setting it to `None` would move a team-mode ruleset on every run (review P8-K05).

**Alternatives considered:**
- **`ci.tools` blocking.** It would add a second red job to a CI already failing for the same reason, and turn a passing CI red when a tool comes in through another package.
- **Only a louder plan note.** Someone who misses the plan still learns only from a red CI, and an agent running `check` never hears of it.
- **GitHub's `codeowners/errors`.** It is GitHub's own verdict, but on the file pushed at a ref, not the working tree, so it can't serve `init` or a `check` before pushing. It stays a possible second signal later.
- **Looking up users only (`users/{login}`).** It says nothing about write access or teams.
- **Refusing every owner `init` can't check.** That would make `gh` a requirement for `--code-owner`, against §12, where `init` works without `gh`.

## Enforced Invariants

None yet. Every locked rule touching these files was read against the design, and none changes. In particular, `inv_81872dfe` holds: the new lookups are GET requests, `check --ci` makes none, and its fixture's owner is the repository's owner, which needs no call. And `inv_5e3b5ef3` holds: an address in CODEOWNERS is never printed. Two rules could be proposed: `ci.tools` never fails `check --ci`, and a code owner GitHub doesn't know is reported by `check` (reading only) and refused by `init` when GitHub says so. The owner decides.

## Consequences

- A person who misses `init`'s note hears it again from `check`, and from an annotation in CI, before or beside the red job.
- The established repository's `@login` is now reported by `check`, also under `--ci`, until `swerepo init --only github --code-owner @<real>` replaces it.
- A team named as code owner can only be checked by someone who can see the organisation's teams. Others get "can't tell", never a wrong refusal.
- `commands()` lives in `swerepo/commands.py`; `init` imports it from there.
