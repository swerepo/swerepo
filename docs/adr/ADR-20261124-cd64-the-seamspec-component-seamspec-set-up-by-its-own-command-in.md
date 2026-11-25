---
id: ADR-20261124-cd64
title: "The seamspec component: SeamSpec set up by its own command in the person's terminal, and the hygiene rules proposed or adopted"
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-24
scopes: ["swerepo/init.py", "swerepo/check.py", "swerepo/cli.py", "swerepo/state.py", "swerepo/ci.py", "swerepo/templates/seamspec/", "swerepo/templates/agents/address-review/", "SWEREPO-SPEC.md"]
invariants: ["inv_c45b7540", "inv_022998a0", "inv_4eaaa886", "inv_2f78270e"]  # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261124-cd64: The seamspec component: SeamSpec set up by its own command in the person's terminal, and the hygiene rules proposed or adopted

## Context

Phase 7 builds the `seamspec` component (spec §6.8, §13). SWERepo uses SeamSpec only through its public command line. These facts were checked against SeamSpec 0.1.2 and this repository on 2026-11-24.

- **`seamspec init`** takes `--mode advisory|enforced|strict`, `--ci/--no-ci`, `--hosts`, `--plugin/--no-plugin`, `--plugin-scope` and `--accept-auto-run`.
  - The last one answers SeamSpec's consent screen ("Allow automatic test runs?") for scripted setups. Otherwise SeamSpec asks its own questions in a terminal.
  - Without `--mode`, an existing `enforced` or `strict` mode is kept. Lowering it needs a person at a terminal.
- **Strict mode** has two side effects SWERepo has to handle:
  - **It always writes `.github/workflows/seamspec.yml`,** ignoring `--no-ci`, but never overwrites an existing file. Its `doctor` only warns when the file is missing.
    - **The file fails the workflow audit.** As SeamSpec renders it, it pins actions by tag (`actions/checkout@v4`, `astral-sh/setup-uv@v6`) and keeps credentials. zizmor 1.32.0 reports two high-severity `unpinned-uses` errors and a medium `artipacked`.
    - **So a strict repository fails `ci-ok`:** `swerepo-ci.yml`'s `workflow-audit` job runs zizmor on every workflow, so it would fail, and `ci-ok` with it (the owner's watchout 1).
  - **It also appends a CODEOWNERS block** (`# seamspec:begin` … `# seamspec:end`) giving `/.seamspec/` to the placeholder `@your-team/leads`.
    - **It lands after SWERepo's block.** SWERepo's governance block already gives `/.seamspec/` to the code owner and is kept last, because the last matching line wins. SeamSpec's block, appended after it, would win.
    - **In `team` mode, merges block.** Code-owner review is required there, so a pull request touching `.seamspec/` would wait for a team that doesn't exist.
- **`seamspec doctor`, `doctor --ci`, `status` and `spec --check`** left every file in this repository untouched (modification times and sizes, `.git` included).
- **CI tests:** standard 1's CI runs `uv run pytest` in a `test` job, and in a `test-<job>` job for each project listed with `--projects`. The job name is the folder, lower-cased, with other characters turned into `-`. Other test commands appear only in the agent instructions, never in CI.
- **This repository** already uses SeamSpec in enforced mode, with 20 locked rules. Two of the four hygiene rules exist under its own ids: `inv_62d51113` (personal data; it doesn't read `[privacy] allow_paths`, and none are set here) and `inv_b2000e40` (`[Unreleased]`).
- **The CI pin:** the SeamSpec version CI pins comes from `[tools] seamspec` (`ci.seamspec_pin`). Once recorded, it wins in `init` and `update` alike.

The owner accepted the recommendations below on 2026-11-24 and added four watchouts, all handled here.

## Decision

1. **Running `seamspec init`.**
   - **Only in a terminal,** attached to it, so the person answers SeamSpec's own questions: the consent screen, the plugin and its scope.
   - **Never `--accept-auto-run`.** Consent is the person's; `--yes` never answers it.
   - **The flags SWERepo passes:**
     - `--mode enforced` on a first setup only; an existing mode is never lowered;
     - `--no-ci` when the `ci` component is set up, `--ci` when it isn't (point 3);
     - `--hosts` with the non-Claude editors chosen in `agents`.
   - **Without a terminal, or with `--yes`,** `seamspec init` isn't run. The plan shows the exact command and the component waits, as GitHub's settings do without `gh`. The next `init` or `update` carries on once `.seamspec/config.toml` exists.
   - **A repository where SeamSpec is already set up** is adopted, and `init` doesn't rerun `seamspec init`. `swerepo -u --seamspec` does (point 8).
2. **Installing and upgrading.** SWERepo never installs or upgrades SeamSpec, since that changes the person's whole machine.
   - **Not installed:** the plan prints `uv tool install seamspec==<pin>`, with the recorded pin, or else standard 1's.
   - **Upgrades:** `uv tool upgrade seamspec`, run by the person.
   - **No PyPI lookup.** SWERepo makes no network call except through `gh`. This changes spec §13, which said SWERepo asks before installing, and that `-u --seamspec` reads the latest version on PyPI if allowed.
3. **SeamSpec's own workflow, when one is needed** (the `seamspec` component without `ci`, or strict mode):
   - **SWERepo writes `.github/workflows/seamspec.yml` itself,** as a managed file from its own template `seamspec/workflow@1`, before running `seamspec init`. Since SeamSpec never overwrites an existing workflow, it keeps SWERepo's.
     - The file runs the same steps as `swerepo-ci.yml`'s `seamspec` job: `seamspec doctor --ci` (against the pull request's base, or the commits a push brought), `seamspec verify --all --ci`, and `seamspec spec --check docs/EARNED_SPEC.md` when the file exists. Without the last one, a rule approved or superseded without regenerating the earned spec would pass CI, against point 7 (Copilot's review of PR #19).
     - Actions are pinned to commits, credentials aren't kept, and uv and SeamSpec are pinned.
     - So it passes the workflow audit, Dependabot keeps its pins current, and `update` maintains it like any other managed file. Once recorded, `update` keeps it current even after `ci` is added and the repository would no longer need it, so its pin moves with the others (Copilot on PR #20).
     - **Not written** when `requires-python` allows none of the Python versions standard 1 knows: the plan says why, as for `swerepo-ci.yml`, and no interpreter is guessed (Copilot on PR #20).
     - It is written only once SeamSpec is set up, or is set up in the same run, and it is recorded in `.swerepo.toml` even before SeamSpec counts as applied (review P7-F02). A run that only waits writes nothing.
     - This refines the owner's point 3 (`--ci` without `ci`): the flag is still passed, and the file SeamSpec then keeps is SWERepo's pinned one.
   - **An existing `seamspec.yml` that SeamSpec wrote** is never replaced (inv_8314036c: never edit a file SWERepo didn't write). When it fails the audit, the plan and `check` report it with the fix: delete it and run `swerepo init --only seamspec`, which writes the pinned one, or pin its actions by hand.
   - **Strict mode with `ci`:** the locked rules run twice, in `swerepo-ci.yml`'s `seamspec` job (inside `ci-ok`) and in `seamspec.yml`. That costs a minute of runner time; `check` notes it, and removing the duplicate is left for later.
4. **Strict mode's CODEOWNERS block.** SWERepo never edits SeamSpec's block. When SeamSpec's block comes after SWERepo's governance block, or still holds `@your-team/leads`, the plan and `check` report it with the fix: put the code owner in it, and keep SWERepo's block last. In `team` mode it is a failure (`✗`), since it blocks merges; in `solo` mode a warning.
5. **The hygiene rule pack.**
   - **The four rules** are bundled in SWERepo as versioned templates under `swerepo/templates/seamspec/`: `hygiene/privacy@1`, `hygiene/adr-index@1`, `hygiene/changelog@1` and `hygiene/ci-tests@1`.
   - **Each rule is a self-contained pytest file:**
     - it uses only the standard library and pytest (`tomllib` included), and is ruff-clean;
     - it finds the repository root from SeamSpec's `config.toml`, as this repository's locked tests do.
   - **How each is proposed:**
     - each is proposed only when its component is set up: privacy with `security`, the ADR index and changelog with `docs`, and CI tests with `ci`;
     - the proposal goes through `seamspec propose --json -`, with the origin reference `swerepo:hygiene/<name>@<version>`, and is verified with `seamspec verify --proposed` before SWERepo reports it;
     - SWERepo never approves. The person runs `seamspec review`, ideally after `/seamspec:explain`.
   - **`hygiene/privacy@1`:** no personal email addresses or home-folder paths in tracked files, with the same allowances as §6.4:
     - noreply and example domains, `git@` in SSH remotes;
     - emails declared in `pyproject.toml`'s authors and maintainers, emails in `SECURITY.md`;
     - placeholder home folders, and lines marked `swerepo: allow-privacy`;
     - `[privacy] allow_paths`, read from `.swerepo.toml` with `tomllib` and matched with git's glob rules, implemented in the test (the owner's watchout 2);
     - like `swerepo privacy` (review P7-F05): the security policy wherever GitHub reads it (`SECURITY.md`, `.github/SECURITY.md`, `docs/SECURITY.md`), links and files over 2 MB skipped, file names read as bytes.
   - **`hygiene/adr-index@1`:**
     - every ADR file in the ADR folder (`[adopted] adr_dir`, else `docs/adr`) is listed in its README's index, between the `swerepo:adr-index` markers, by its own row's link to the file: an ID named in a title or a "SUPERSEDED by" cell doesn't count, and every link must name an existing file once (SeamSpec's reviewer);
     - it is proposed only when that README has the markers (watchout 2).
   - **`hygiene/changelog@1`:** `CHANGELOG.md` keeps an `[Unreleased]` section.
   - **Proposed only when its subject is there** (review P7-F06): an ADR README with one intact index, in the ADR folder `init` uses (also on a first run that adopts one), a `CHANGELOG.md` that already has `[Unreleased]`, a `swerepo-ci.yml`; `check` reports a rule only under the same condition. And only when the `seamspec` command can run here: a repository whose SeamSpec is set up, on a machine without it, waits.
   - **`hygiene/ci-tests@1`:** `swerepo-ci.yml` still runs the tests, checked on its text without parsing YAML.
     - **The expected jobs:** a `test` job, and a `test-<job>` job for every folder in `.swerepo.toml`'s `[projects] listed`, named as SWERepo names them. Each runs `uv run pytest`, and `ci-ok`'s `needs:` names each of them (watchout 3).
     - **Robust to change:** it ignores action pins, comments and job order, so Dependabot's bumps and `update`'s new template versions don't break it.
     - **Each job is read step by step** (review P7-F04): a pytest step switched off or allowed to fail (also quoted, or as `${{ … }}`), a run masked (`|| …`, `; …`, `… &`, `--version`, `--help`, `--collect-only`, with folded `run: >` blocks and line continuations joined first), or a `needs:` list read past its end don't count; `uv run` options such as `--locked` do. `ci-ok` itself must not be switched off or allowed to fail, and must still fail when a test job fails: it runs `if: always()` (a skipped required check counts as passed) and keeps a step that reads the jobs' results and can exit non-zero, so replacing that script with `echo ok` breaks the rule (SeamSpec's reviewer).
     - **The whole script is read** (Copilot on PR #20): `uv run pytest` counts only as a command of its own at the top of its step's script, not piped (no `pipefail` by default), with `&& …` after it only as the script's last command, and with no `set +e`, no earlier `exit` and no `shell:` other than GitHub's own `bash` or `sh` (for the step, the job or the workflow). `ci-ok`'s judging step must read the results into a variable (`var=$(… "$NEEDS" …)`) and then run `if [ -n "$var" ]; then` with a non-zero `exit` before any other `exit` and before its `fi`, so `if false; then` or a leading `exit 0` breaks the rule.
     - **Other test commands:** standard 1's CI runs only `uv run pytest`. When CI learns other test commands (Phase 11), the rule gets a version 2.
6. **Rules the repository already has.**
   - **A hygiene rule counts as present when either:**
     - a rule with its origin reference is locked or proposed, or
     - `.swerepo.toml`'s `[seamspec.adopted]` names a locked rule for it, for example `privacy = "inv_62d51113"`.
   - **Filling `[seamspec.adopted]`:** in a terminal, `init` asks once for each missing hygiene rule whether a locked rule covers it, listing the locked rules; the default is to propose a new one. `--adopt <name>=<id>` does the same without a terminal.
   - **`check`** reports an adopted id that isn't locked as `✗`.
   - **Here:** adopt `privacy = "inv_62d51113"` and `changelog = "inv_b2000e40"`, and propose `adr-index` and `ci-tests`.
7. **`docs/EARNED_SPEC.md`** stays as spec §13 says. It is written with `seamspec spec --out` after the person's first review (with the rules approved so far if they postpone it), and checked in CI with `seamspec spec --check`: by `swerepo-ci.yml`'s `seamspec` job, or by SWERepo's `seamspec.yml` when there is no `ci` component (point 3).
8. **`swerepo -u --seamspec`:** (refined on Gemini's Phase 7 review, P7-F01 and P7-F07)
   - **The versions:** reports the installed SeamSpec against the CI pin, and tells the person to run `uv tool upgrade seamspec` themselves.
   - **`seamspec init`:** reruns it in the person's terminal, with point 1's flags, and printed only without a terminal. It reruns when the installed SeamSpec is newer than the one `seamspec init` last ran with, recorded as `[seamspec] initialised` apart from the CI pin, so an `update --yes` that moved the pin still leaves the terminal rerun to do. Adopting an existing SeamSpec records the installed version.
   - **The pin moves to the installed version, never backwards.** A development build is never pinned. These move together, in one write:
     - `[tools] seamspec`;
     - `swerepo-ci.yml`'s `seamspec==` pin, and its record's `inputs`, `rendered` and `written`;
     - SWERepo's `seamspec.yml`, if it has one.
   - **`ci` is brought along for the pin only** (the owner's watchout 4), as `--only github` brings it for the Copilot wait (P6-F08).
     - **The new render** is the recorded workflow with only the SeamSpec version changed: rebuilt from its recorded template version and inputs, so a newer workflow template and `ci`'s other files (the pyproject settings, per-project files) wait for `update --only ci` (Copilot on PR #20). A record without inputs can't be rebuilt: the plan says so and the pin holds.
     - **Untouched:** the workflow is rewritten.
     - **Edited:** it is merged, with the person's consent.
     - **Conflict or can't merge:** the pin doesn't move either, so `.swerepo.toml` and the files keep agreeing and `check` stays green. This holds in both directions: when any recorded workflow pinning SeamSpec (`swerepo-ci.yml`, or SWERepo's `seamspec.yml`) can't take the new pin, or isn't planned in this run (`--no-ci`), none moves, and the plan says why (P7-F01; Copilot on PR #20).
   - **Finally:** reports `seamspec doctor`'s checks (by name), after applying.
9. **`check` for the `seamspec` component:**
   - **What it reports:**
     - whether SeamSpec is set up, and its mode;
     - the CI pin against the installed version (`↑` when a newer one is installed);
     - `seamspec doctor` (errors `✗`, warnings `~`);
     - each hygiene rule: locked, adopted, proposed or missing;
     - the proposals waiting for review;
     - whether the earned spec is current;
     - points 3 and 4 in strict mode.
   - **Read-only.** It runs only `seamspec --version`, `seamspec doctor --json` and `seamspec spec --check`, which were checked to write nothing; the proposals and hygiene rules come from SeamSpec's own files. A test locks that it stays read-only (`inv_294c48c9`'s promise, extended to this component).
   - **`doctor --json`, not the text output:** SeamSpec 0.1.2's text output counts warnings without saying what they are. `check` names only the checks that warned or failed, never SeamSpec's messages, which can hold machine paths (`inv_5e3b5ef3`).
   - **With `--ci`,** it calls no SeamSpec command and reads files only. In CI, the `seamspec` job already runs `doctor` and `verify`.
10. **Also in Phase 7:**
    - `agents/address-review@3`, whose step 4 is to ask before resolving review threads and resolve only on a yes (ADR-20261124-023e), so other repositories get the rule through `update`. Only step 4's own line changes: renumbering the steps would change the last line, next to where people add their own notes, and turn those merges into conflicts (locked rule `inv_60788941` caught that);
    - `docs/PROGRESS.md` marks Phase 6 done.
11. **Dogfooding.** This repository adds `seamspec` to its components, adopts its SeamSpec setup and two locked rules, and proposes the other two hygiene rules. SeamSpec's own files are left as they are.

**Alternatives considered:**
- **Passing `--accept-auto-run` with `--yes`:** an agent's or a script's `init --yes` would give consent the person never gave.
- **Installing SeamSpec when it is missing, after a yes:** SWERepo would change the person's machine-wide tools. Printing the command is enough.
- **Leaving SeamSpec's own workflow as SeamSpec writes it:** every strict repository, and every repository using `seamspec` without `ci`, would carry actions pinned by tag, and the workflow audit would fail `ci-ok` on strict ones.
- **Excluding `seamspec.yml` from the workflow audit:** that weakens the audit for the one workflow that runs pull-request code.
- **Proposing all four hygiene rules even when a locked rule covers one:** the repository would end with two rules for one behaviour, and the person would have to reject duplicates in every review.
- **Matching existing rules to hygiene rules by title:** a guess. The person names them instead.

## Enforced Invariants

Locked by the owner on 2026-11-24, after two reads by SeamSpec's reviewer:
- `inv_c45b7540` (critical): SWERepo never answers SeamSpec's consent (no argument starting with `--accept-auto-run`), and runs `seamspec init`, and the review it offers, only on a person's yes in a terminal.
- `inv_022998a0`: `check` writes nothing with SeamSpec set up (folders' modification times included), runs only `--version`, `doctor --json` and `spec --check`, and with `--ci` runs no SeamSpec command.
- `inv_4eaaa886`: every bundled hygiene test uses only the standard library and pytest, passes ruff, passes on a repository `init` sets up, and fails on the breakage it guards, `ci-ok` no longer failing when a test job fails included.
- `inv_2f78270e`: `-u --seamspec` never moves the SeamSpec pin backwards or to a development or local build, and every workflow pinning it and `[tools] seamspec` name one version afterwards.

On this repository, the hygiene rules are `inv_62d51113` (privacy, adopted), `inv_b2000e40` (changelog, adopted), `inv_5c45ea08` (ADR index) and `inv_c78fcca0` (CI tests), all locked. After Copilot's review of PR #20 the `ci-tests` template reads the whole script, and the owner approved its replacement (2026-11-24): `inv_11ce8c5b` is locked and `inv_c78fcca0` superseded.

## Consequences

- SeamSpec's consent always comes from a person at a terminal. An agent's `init --yes` sets up everything else and leaves SeamSpec waiting.
- Every workflow in a SWERepo repository passes the audit, SeamSpec's included.
- A repository can bring its own rules for the hygiene behaviours. SWERepo checks that they are locked, not what their tests say.
- The bundled tests are code SWERepo ships into other repositories. Once a person locks one, it can't be changed there except by a supersede, so they are versioned like templates and never changed once released.
- The locked rules run twice on strict repositories with `ci`, until a later phase removes the duplicate.
