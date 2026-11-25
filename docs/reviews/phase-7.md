# Code Review · Phase 7: the seamspec component and the hygiene rules

**Status:** closed · **Rounds:** 3 · **Developer:** Claude · **Reviewer:** Gemini · **Owner decides:** ties, merges, SeamSpec approvals
**Process:** ADR-20261119-9f87. Finding IDs `P7-F<nn>`; severities `blocker | should-fix | suggestion | question`; responses Fix / Push back / Defer, then Accept / Maintain.

---

## Developer summary

### Scope

Phase 7 builds the `seamspec` component as ADR-20261124-cd64 decides (merged as PR #19, with Copilot's fix).

- **`swerepo init` for `seamspec`** (`swerepo/seamspec_component.py`, the `seamspec` section of `swerepo/init.py`, `swerepo/cli.py`):
  - **`seamspec init`** runs only when a person is at a terminal. It is attached to the terminal, so SeamSpec asks its own questions, and is never passed `--accept-auto-run`.
    - **Flags:** `--mode enforced` on a first setup only; `--no-ci` with `ci`, `--ci` without it; `--hosts` with the non-Claude editors.
    - **Without a terminal, or with `--yes`:** the plan shows the command and the component waits (`waiting`).
  - **SeamSpec isn't installed:** the plan prints `uv tool install seamspec==<pin>`. SWERepo never installs it.
  - **SWERepo's `seamspec.yml`** (template `seamspec/workflow@1`) is written when SeamSpec needs a workflow of its own: no `ci`, or strict mode. Actions are pinned to commits, and it runs the same three steps as `swerepo-ci.yml`'s `seamspec` job. An unpinned one SeamSpec wrote is reported, never replaced.
  - **Strict mode's CODEOWNERS block** is reported when it follows SWERepo's or keeps `@your-team/leads`: a failure in `team` mode, a warning in `solo`.
  - **The four hygiene rules** are bundled as templates, `seamspec/hygiene-{privacy,adr-index,changelog,ci-tests}@1`.
    - **Proposing:** each is proposed with `seamspec propose --json -` and the origin `swerepo:hygiene/<name>@1`, only when its component is set up and its subject exists, then verified with one `seamspec verify --proposed …` where the clone is trusted.
    - **Adopting:** a locked rule of the repository's own is adopted instead: `--adopt NAME=ID`, or a question per rule in a terminal, listing the locked rules. It is recorded under `[seamspec.adopted]`.
    - **Declined:** a rejected or superseded SWERepo rule is never proposed again.
  - **The earned spec:** after the proposals, a terminal offers `seamspec review`. `docs/EARNED_SPEC.md` is then written or refreshed (`seamspec spec --out`) when it is missing or out of date.
  - **New plan verbs:** `run` and `propose`. They count as changes, so a plan with only SeamSpec work still applies.
- **`swerepo check` for `seamspec`** (`swerepo/check.py`):
  - **Always:** the hygiene rules (locked, adopted, proposed, declined or missing; anything not yet approved only warns), the proposals waiting, and strict mode's workflow and CODEOWNERS block.
  - **On a person's machine only:** the CI pin against the installed SeamSpec, `seamspec doctor --json`, naming the checks only (never the messages, which can hold machine paths), and `spec --check`.
  - **With `--ci`:** no SeamSpec command at all.
- **`swerepo update --only seamspec`:**
  - **The pin:** a newer released SeamSpec installed moves the pin, never back and never to a development build.
  - **`ci` comes along for the pin only** (`pin_only`: recorded values, so `update`'s other refreshes don't apply).
  - **Pin held:** when `swerepo-ci.yml` can't take the pin, neither `seamspec.yml` nor `[tools] seamspec` moves.
  - **`seamspec init`** reruns in a terminal after an upgrade.
- **`agents/address-review@3`:** step 4 says to ask before resolving review threads (ADR-20261124-023e).
- **Tests:**
  - a fake `seamspec` (`tests/fake_seamspec.py`) that logs every call and acts on the repository;
  - `tests/conftest.py`, so that by default no test reaches a real `seamspec` on PATH;
  - `tests/test_seamspec.py`, the new tests.
- **Dogfooded here:**
  - `seamspec` is a component, with `privacy = inv_62d51113` and `changelog = inv_b2000e40` adopted;
  - SWERepo proposed `inv_5c45ea08` (ADR index) and `inv_c78fcca0` (CI tests) through the real SeamSpec 0.1.2, and verified them;
  - `docs/agents/address-review.md` is at version 3.

Branch `phase-7/seamspec`, uncommitted. Spec v0.15 (ADR-20261124-cd64's text and §13 corrected on what `check` runs).

### What to review

| Area | Files |
|---|---|
| SeamSpec's files and commands | `swerepo/seamspec_component.py` (`HYGIENE`, `Ledger`, `hygiene`, `newer`, `released`, `init_args`, `unpinned`, `codeowners_problems`, `doctor`, `proposal`) |
| Planning | `swerepo/init.py`: `_seamspec`, `_hygiene_applies`, `_seamspec_workflow`; in `make_plan`, the pin (`pin_along`, `held`) and `applied`; `_refreshes` and `pin_only`; `_new_state` (`[tools] seamspec` from `seamspec.yml`, `[seamspec.adopted]`) |
| After the files | `swerepo/init.py`: `apply_seamspec`, `write_earned_spec`; `swerepo/cli.py`: `--adopt`, `_parse_adopt`, `_ask_adopt`, `_seamspec_after`, in `init` and `update` |
| check | `swerepo/check.py`: `_seamspec_rules`, `_seamspec_strict`, `_seamspec_local`; `swerepo/standard.py` (`LATER`) |
| State | `swerepo/state.py`: `HYGIENE_RULES`, `seamspec_adopted`, `set_seamspec_adopted`, validation |
| Templates | `swerepo/templates/seamspec/hygiene-*/1.py`, `swerepo/templates/seamspec/workflow/1.yml`, `swerepo/templates/agents/address-review/3.md` |
| Tests | `tests/test_seamspec.py`, `tests/fake_seamspec.py`, `tests/conftest.py`; `tests/test_init.py` (later components now `openspec`) |
| Proposed rules | `.seamspec/proposed/inv_c45b7540/`, `inv_022998a0/`, `inv_4eaaa886/`, `inv_2f78270e/`; the hygiene proposals `inv_5c45ea08/`, `inv_c78fcca0/` |
| Docs | ADR-20261124-cd64 (points 9 and 10), `SWEREPO-SPEC.md` §13, `CHANGELOG.md`, `docs/PROGRESS.md`, `docs/progress/20261124-phase-7-seamspec.md` |
| Dogfood | `.swerepo.toml`, `docs/agents/address-review.md` |

### How to run

```bash
uv sync
uv run pytest
GITHUB_ACTIONS=true TERM=dumb uv run pytest
uv run ruff check . .seamspec/proposed/
uv run ruff format --check . .seamspec/proposed/
uv run seamspec verify --all
uv run seamspec verify --proposed inv_c45b7540 --proposed inv_022998a0 --proposed inv_4eaaa886 --proposed inv_2f78270e --proposed inv_5c45ea08 --proposed inv_c78fcca0
uv run swerepo init --only seamspec --dry-run       # on this repository: adopted and proposed, nothing to do
uv run swerepo check --only seamspec                # the hygiene rules, the pin, doctor
uv run swerepo update --dry-run                     # "Nothing to do."
```

`seamspec init` itself can't run unattended; that is the point. The terminal path is tested against the fake `seamspec` (`TestSetUp`). On a throwaway repository you can try it yourself with `swerepo init --only seamspec` in a terminal.

### Results (run by the developer on 2026-11-24, macOS, Python 3.12, uv 0.9.28, git 2.50, SeamSpec 0.1.2)

- **Tests:** pytest **732 passed**, plain and with `GITHUB_ACTIONS=true TERM=dumb`. 32 are new in `tests/test_seamspec.py`.
- **Lint and rules:** ruff is clean, including `.seamspec/proposed/`. Locked rules: 20 passed. Proposed rules: 6 passed. `seamspec spec --check` is clean.
- **This repository:**
  - `check` exits 0; its four warnings are the two hygiene rules waiting for review, the six proposals waiting, and SeamSpec's doctor warnings about critical marks and the new templates' scope, which clears once committed;
  - `update --dry-run` → "Nothing to do."; `privacy` → nothing found; zizmor 1.32.0 → no findings, and none for SWERepo's rendered `seamspec.yml` either.
- **The bundled hygiene tests** pass on a copy of this repository and on a repository `init` sets up, and each fails on the breakage it guards (the rule `inv_4eaaa886`).
- **Mutation checks** (each one breaks the code on purpose, and its test must fail):
  - **The component's tests caught:**
    - `--accept-auto-run` passed to `seamspec init`;
    - `seamspec init` run without a terminal;
    - `check --ci` calling SeamSpec;
    - the pin moving backwards;
    - the pin hold removed (caught only after I added the strict-with-`ci` case; the first test used enforced mode, where it can't matter);
    - a declined rule proposed again;
    - doctor's message printed;
    - a proposed rule adopted.
  - **The four proposed rules** each fail on their own breakage.
- **Caught by a locked rule while building:** `inv_60788941` failed when `address-review@3` renumbered its steps. A person's note appended at the end then sat next to a changed line, and the merge became a conflict. Fixed by changing only step 4's line.

### Design notes worth checking

1. **The ledger is read from SeamSpec's files** (`Ledger.read`: `config.toml` and `invariants/*.json`), not through `seamspec status`, so planning and `check` never need SeamSpec's output format. SeamSpec's commands are used only to act: `init`, `propose`, `verify`, `spec --out`. `check` also uses the read-only `--version`, `doctor --json` and `spec --check`.
2. **The terminal decides** (`terminal` in `make_plan`). `init --yes`, a dry run or `--json` never run `seamspec init`. Only `cli.init` or `cli.update` with a terminal, and no `--yes`, sets `terminal=True`.
3. **`seamspec` counts as applied only once SeamSpec is set up** (`applied`). Until then `.swerepo.toml` doesn't list it. After a successful `seamspec init`, `apply_seamspec` adds it. So a second `init --yes` without a terminal writes nothing (locked `inv_1002d669`).
4. **Proposals need SeamSpec set up**, or set up in this run. Verifying needs the clone trusted: SeamSpec refuses `verify` in an untrusted clone, and SWERepo says so instead of failing.
5. **"Not approved yet" only warns** in `check`. Approving is the person's call, and a hygiene rule waiting for review shouldn't turn CI red. An adopted id that isn't locked is a failure.
6. **The pin hold:** in strict mode with `ci`, both workflows pin SeamSpec. `held` keeps `seamspec.yml` on the recorded pin when `swerepo-ci.yml` doesn't take the new one (a conflict), so the two never disagree.
7. **Tests never reach a real `seamspec`** (`conftest.py`), since its answers depend on the machine. The locked rules run without our helpers, so each carries its own small fake.

### Known gaps and deliberate omissions

- **SeamSpec's text output** doesn't name its warnings (0.1.2). `check` reads `--json`. Worth reporting to SeamSpec.
- **Strict mode with `ci`** runs the locked rules twice (ADR-cd64 point 3); deduplicating is left for later.
- **`seamspec init` in a terminal** can't be tested end to end without a person. The tests run SWERepo's apply step against the fake. The interactive question for adoption (`_ask_adopt`) is a thin prompt, not unit-tested.
- **Monorepos:** SeamSpec is set up for the root only (spec §11's limit, unchanged).

### Questions for the reviewer

1. **Reading SeamSpec's ledger files directly** (design note 1): sound, or should SWERepo prefer SeamSpec's own commands even for reading?
2. **Warnings for rules not yet approved** (design note 5): right, or should a missing hygiene rule fail `check` once SeamSpec is set up?
3. **The adoption question** (one prompt per missing rule, listing every locked rule): usable with many locked rules, or should it list only likely candidates?
4. **The hygiene tests' text matching** (`ci-tests` reads YAML as text; `privacy` reimplements git's globs): robust enough for repositories that edit `swerepo-ci.yml`?
5. **The proposed rules:** the right behaviours to lock? I suggested critical only for `inv_c45b7540`, since SeamSpec's doctor already warns that 17 of 20 locked rules are critical.

### SeamSpec proposals waiting for the owner

| ID | Rule | Suggested critical | Verified |
|---|---|---|---|
| inv_c45b7540 | SWERepo never answers SeamSpec's consent, and runs `seamspec init` only in a terminal | yes | passed |
| inv_022998a0 | `check` stays read-only with SeamSpec, and with `--ci` runs no SeamSpec command | no | passed |
| inv_4eaaa886 | The bundled hygiene tests use only the standard library and pytest, pass ruff, and pass where `init` set things up | no | passed |
| inv_2f78270e | `update` moves the SeamSpec pin forward only, and `.swerepo.toml` and `swerepo-ci.yml` always name the same version | no | passed |
| inv_5c45ea08 | hygiene/adr-index, proposed by SWERepo on this repository | (owner's choice) | passed |
| inv_c78fcca0 | hygiene/ci-tests, proposed by SWERepo on this repository | (owner's choice) | passed |

The owner reviews them in `seamspec review` after this review round. *Outcome (2026-11-24): all six locked after two reads by SeamSpec's reviewer and two rounds of tightening; only `inv_c45b7540` is critical. See Closing.*

---

## Review rounds

### Round 1

**Reviewer:** Gemini · **Date:** 2026-11-24

#### Verification run

All commands under "How to run" (plus `privacy`, `zizmor` on both `.github/workflows` and a rendered `seamspec/workflow@1`, and targeted adversarial probes) were executed:

- `uv sync` → clean (`Audited 47 packages`).
- `uv run pytest` → **732 passed** (`153.65s`).
- `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **732 passed** (`153.10s`).
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (`165 files already formatted`).
- `uv run seamspec verify --all` → **20/20 locked rules passed**.
- `uv run seamspec verify --proposed inv_c45b7540 --proposed inv_022998a0 --proposed inv_4eaaa886 --proposed inv_2f78270e --proposed inv_5c45ea08 --proposed inv_c78fcca0` → **6/6 proposed rules passed** (`14` test cases).
- `uv run swerepo init --only seamspec --dry-run` → `Nothing to do.` (`privacy`/`changelog` adopted, `adr-index`/`ci-tests` proposed; exit `0`).
- `uv run swerepo check --only seamspec` → exit `0` (`4` non-blocking warnings for pending review items and `doctor`).
- `uv run swerepo update --dry-run` → `"Nothing to do."` (exit `0`).
- `uv run swerepo privacy` → `"swerepo privacy: nothing found"` (exit `0`).
- `uvx zizmor==1.32.0 --offline` on `.github/workflows` and on rendered `seamspec/workflow@1` → `No findings to report`.

#### What is well done and should be kept

- **Uncompromising consent and machine boundaries (`init_args`, `terminal`, `conftest.py`):** Never passing `--accept-auto-run`, running `seamspec init` attached only in a real interactive terminal (`not as_json and not yes and not dry_run`), never installing or upgrading `seamspec`, and isolating every test from any host `seamspec` binary via `_no_real_seamspec` in `tests/conftest.py` are airtight.
- **Direct read-only ledger inspection and path-safe `doctor` (`Ledger.read`, `ssc.doctor`, `_seamspec_local`):** Reading `.seamspec/config.toml` and `.seamspec/invariants/*.json` directly avoids CLI output coupling, works when `seamspec` isn't on `PATH`, and guarantees zero writes; `check --ci` invokes zero SeamSpec subprocesses; and `ssc.doctor` extracts only sanitised check names (`[A-Za-z0-9 _-]`), never SeamSpec's raw messages, preserving `inv_5e3b5ef3` and `inv_294c48c9`.
- **Pre-empting `strict` mode's `zizmor` and `CODEOWNERS` traps:** Writing SWERepo's commit-pinned `seamspec/workflow@1` (including `spec --check docs/EARNED_SPEC.md`) so `seamspec init` keeps it, reporting foreign unpinned workflows without overwriting them, and flagging `strict` mode's `@your-team/leads` / trailing `CODEOWNERS` block (blocking in `team`, warning in `solo`) solve real operational footguns cleanly.
- **Declined-rule memory & surgical `address-review@3`:** Matching `REJECTED` and `SUPERSEDED` rules by `swerepo:hygiene/<name>@` prefix ensures declined rules are never re-proposed, and updating only step 4's line in `agents/address-review@3` so trailing user notes merge cleanly (`inv_60788941`) is great attention to detail.

#### Findings

##### P7-F01 · blocker · `swerepo/init.py:1556-1586, 1696-1700`
**Pin desynchronization in `strict` mode with `ci`: when `seamspec.yml` cannot take the new pin, `swerepo-ci.yml` and `[tools] seamspec` still advance**

- **Failure scenario (reproduced):**
  Set up a repository in `strict` mode with `ci` and `seamspec` (both `swerepo-ci.yml` and SWERepo's managed `.github/workflows/seamspec.yml` pin `seamspec==0.1.2`, and `[tools] seamspec = "0.1.2"`). Customise `seamspec.yml` (for example `timeout-minutes: 15` → `20` and run `swerepo -u --seamspec --yes` without `--merge`, or edit the `seamspec==0.1.2` line so `--yes --merge` hits `CONFLICT`; or have an unrecorded foreign `seamspec.yml` pinned at `0.1.2`), while leaving `swerepo-ci.yml` untouched. With SeamSpec `0.2.0` installed, run `update`. Because `make_plan` plans `ci` before `seamspec` and `held` (`init.py:1583`) only holds `seamspec.yml` back when `not ci_result.written`—never the reverse—`swerepo-ci.yml` rewrites to `seamspec==0.2.0` and `_new_state` sets `[tools] seamspec = "0.2.0"`, while `seamspec.yml` stays at `seamspec==0.1.2`!
- **Suggested fix:**
  Ensure the pin hold is symmetric whenever both workflows exist: either plan `_seamspec_workflow` before `_ci` (or replan `_ci` with `seamspec_pin=None` if `seamspec.yml` was planned and its verb is not in `WRITTEN`), so `.swerepo.toml`, `swerepo-ci.yml`, and `seamspec.yml` either all move to the new pin together or all stay on the recorded pin. Extend proposed `inv_2f78270e` to test this reverse case as well.

##### P7-F02 · blocker · `swerepo/init.py:1345-1346, 1593-1598, 1662-1663, 1937-1942`
**First-time `swerepo init --only seamspec` writes `.github/workflows/seamspec.yml` to disk unrecorded (and writes no `.swerepo.toml` on a fresh repository)**

- **Failure scenario (reproduced in three cases):**
  1. Follow Spec §10's gradual adoption: run `swerepo init --only docs` first (`state.components == ["docs"]`), then run `swerepo init --only seamspec` in a terminal (`plan.seamspec_set_up` is `False`, no `ci`). `_seamspec` plans `CREATE .github/workflows/seamspec.yml`. In `make_plan` (`init.py:1595`), `applied` excludes `"seamspec"` because `not plan.seamspec_set_up`, leaving `applied == []`. `_new_state` (`init.py:1662`) immediately returns `None` (`if not applied: return None`)! `apply()` writes `.github/workflows/seamspec.yml` to disk, skips saving `plan.state_text`, and `apply_seamspec` (`init.py:1940`) adds `"seamspec"` to `state.components` **without recording `[files.".github/workflows/seamspec.yml"]` or `[tools] seamspec`**. On the very next `init` or `update`, SWERepo treats its own `seamspec.yml` as `"yours: SWERepo didn't write it"` and never maintains it.
  2. Run `swerepo init --only seamspec` in a terminal on a repository that has no `.swerepo.toml` yet (`ctx.state is None`). `apply()` creates `seamspec.yml`, `apply_seamspec` runs `seamspec init`, notices `State.load(root)` is `None` (`init.py:1938-1939`), and writes **no `.swerepo.toml` at all**.
  3. Run `swerepo init --only seamspec --yes` (no terminal): `_seamspec_workflow` runs before checking `ctx.terminal` / `ssc.command()`, writing an unrecorded `seamspec.yml` to disk even though `seamspec` is `waiting`.
- **Suggested fix:**
  1. In `_seamspec`, plan `_seamspec_workflow` only once `ready` is `True` (`ledger.set_up or plan.seamspec_run is not None`), so a waiting run writes nothing for `seamspec`.
  2. In `_new_state`, don't return `None` solely because `not applied` when `plan.actions` contains file writes (`any(a.verb in WRITES for a in plan.actions)`), and in `apply_seamspec` load `State.load(root) or State.new()` when recording `"seamspec"` after `seamspec init` succeeds so `seamspec.yml`, `[tools] seamspec`, and `components` are always recorded.

##### P7-F03 · should-fix · `swerepo/init.py:1368-1400, 1974-1988`
**`write_earned_spec` follows symlinks outside the repository, and missing `seamspec` on `PATH` with an existing `.seamspec/config.toml` plans failing `PROPOSE`/`RUN` actions on every run**

- **Failure scenario (both reproduced):**
  1. *Symlink escape (`init.py:1974-1988`):* Unlike `apply()`, `_managed_file`, and `_starter`, `write_earned_spec` does not check `inside(root, root / ssc.EARNED_SPEC)` (or whether `docs/EARNED_SPEC.md` is a symlink) before invoking `seamspec spec --out docs/EARNED_SPEC.md`. When `docs/EARNED_SPEC.md` is a symlink to an external path (dangling or out of date), `write_earned_spec` writes outside the repository.
  2. *Missing `seamspec` CLI on an already-initialised repo (`init.py:1368-1400`):* Clone a repository that already commits `.seamspec/config.toml` (`ledger.set_up == True`) onto a machine without `seamspec` installed (`ssc.command() is None`), and run `swerepo init --yes`. Because `ready` (`init.py:1368`) checks `ledger.set_up` without checking `ssc.command() is not None`, SWERepo plans `PROPOSE` for all hygiene rules and `RUN` for `docs/EARNED_SPEC.md`, prints `not proposed (seamspec propose failed)` / `not written`, and **plans those same failing `changes` again on every subsequent `swerepo init --yes`**, breaking second-run idempotence instead of reporting `waiting` (`uv tool install seamspec==<pin>`).
- **Suggested fix:**
  Guard `write_earned_spec` (and planning `seamspec_spec`) with `inside(root, root / ssc.EARNED_SPEC) and not (root / ssc.EARNED_SPEC).is_symlink()`. In `_seamspec`, require `ssc.command() is not None` before setting `ready = True` or `plan.seamspec_spec = True`; if `ledger.set_up` is `True` and `ssc.command() is None` when hygiene proposals or `EARNED_SPEC.md` work remain, emit a `WAITING` action naming `uv tool install seamspec==<pin>`.

##### P7-F04 · should-fix · `swerepo/templates/seamspec/hygiene-ci-tests/1.py:19-25, 46-52, 79-85`
**`hygiene/ci-tests@1` passes when pytest is disabled at step level (`if: false`, `continue-on-error: true`, `|| true`), misparses block `needs:`, and rejects `uv run --locked pytest`**

- **Failure scenario (all four reproduced; also affects proposed `inv_c78fcca0` here):**
  1. *Step-level disable / shell mask (passes on breakage):* `SWITCHED_OFF` (`^    if:`) and `MAY_FAIL` (`^    continue-on-error:`) check only 4-space job-level keys. An agent adding `if: false` or `continue-on-error: true` on the `uv run pytest` step itself (8 spaces), or changing the step to `run: uv run pytest || true` (or `uv run pytest --version`), passes `_problems(...) == []` while tests no longer gate `ci-ok`.
  2. *Unbounded block `needs:` loop (passes on breakage, line 51):* `[m["name"] for later in lines[i + 1 :] if (m := NEEDS_ITEM.match(later))]` never stops when indentation drops back to `<= 4` spaces, so any later 6-space `- test` item inside `ci-ok` satisfies `name in needs` even when `ci-ok`'s `needs:` omitted `test`.
  3. *Valid `uv run` flags rejected:* Editing `uv run pytest` to `uv run --locked pytest` (the exact form SWERepo uses in `governance`) fails `RUNS_PYTEST` (`"test doesn't run uv run pytest"`).
  4. *Scope omits `.swerepo.toml` (`seamspec_component.py:91`):* `ci-tests` reads `[projects] listed` from `.swerepo.toml`; without `.swerepo.toml` in `scope_paths`, SeamSpec's changed-file verification skips the rule when a project is added to `[projects] listed` without a matching `test-<project>` job.
- **Suggested fix:**
  Split each job into job-level lines and individual `steps:` entries (stopping block `needs:` as soon as indentation returns to `<= 4` spaces or a non-list line): require at least one step per expected test job whose `run` command invokes `pytest` cleanly (allowing `uv run` flags like `--locked`, and rejecting `||` / `;` fallbacks, `--version`, `--help`, `--collect-only`, step-level `if: false`, and step-level `continue-on-error: true`). Add `.swerepo.toml` to `ci-tests`'s `scope_paths`, and refresh proposed `inv_c78fcca0` before review.

##### P7-F05 · should-fix · `swerepo/templates/seamspec/hygiene-privacy/1.py:85, 99-115, 131`
**`hygiene/privacy@1` fails on adopted `.github/SECURITY.md` or `docs/SECURITY.md` that `swerepo check` accepts, and omits `swerepo/privacy.py`'s file/TOML guards**

- **Failure scenario (reproduced):**
  Set up a healthy repository whose security policy lives at `.github/SECURITY.md` or `docs/SECURITY.md` with a published contact email (non-example domain). `swerepo init` adopts it and `swerepo check` / `swerepo privacy` report **0 findings** (`privacy.py:45,121` checks `path.lower() not in POLICY_PATHS`), whereas `hygiene-privacy/1.py:131` checks `if rel != "SECURITY.md":` and **fails** with `.github/SECURITY.md:1: email address`. In addition, compared with `swerepo/privacy.py:72,84,98-103`, `hygiene-privacy/1.py` decodes `git ls-files -z` with strict UTF-8 (`text=True`), reads tracked symlinks and files over 2 MB (`_text` omits `is_symlink()` and `MAX_BYTES`), and crashes in `_declared_emails()` on `UnicodeDecodeError` or non-list `authors`/`maintainers`.
- **Suggested fix:**
  Align `hygiene-privacy/1.py` with `swerepo/privacy.py`: check `rel.lower() not in {"security.md", ".github/security.md", "docs/security.md"}`, skip `path.is_symlink()` and `stat().st_size > 2_000_000` in `_text`, decode `git ls-files -z` bytes with `errors="surrogateescape"` (falling back if `git` fails), and guard `UnicodeDecodeError` and `isinstance(..., dict/list)` in `_declared_emails()`.

##### P7-F06 · should-fix · `swerepo/init.py:1403-1419`, `swerepo/check.py:829-873`
**Brownfield mismatches between `init` and `check`: unapplicable hygiene rules warn forever in `check`, first-run adopted `adr_dir` is missed, and unpinned `seamspec.yml` is missed in `enforced` mode**

- **Failure scenario (all three reproduced):**
  1. *`check` warns forever on skipped rules (`check.py:836-851`):* On an established repository whose adopted `doc/decisions/README.md` has no `swerepo:adr-index` markers (or that uses `CHANGES.md` instead of `CHANGELOG.md`, or where `ci` wrote no `swerepo-ci.yml`), `_hygiene_applies` returns `False` so `swerepo init --only seamspec` says `"Nothing to do."`—yet `swerepo check` warns on every run: `hygiene/adr-index: not proposed yet (swerepo init --only seamspec)`.
  2. *First-run adopted `adr_dir` & broken/unready subjects (`init.py:1410-1415`):* On a first `swerepo init` (`ctx.state is None`) where `docs` adopts `doc/decisions/` (with index markers), `_hygiene_applies` reads `ctx.state.adopted.get("adr_dir")` (`None`) instead of the detected `adr_dir`, checking `docs/adr/README.md` and missing `adr-index` on the first run. Conversely, `_has_index_markers` returns `True` on *broken* markers (`init.py:553`), and `present("CHANGELOG.md")` returns `True` even when an existing `CHANGELOG.md` lacks `## [Unreleased]` (`init.py:586`), proposing rules guaranteed to fail `verify --proposed`. (Adding `.swerepo.toml` to `adr-index`'s `scope_paths` also covers `[adopted] adr_dir` changes, including refreshing `inv_5c45ea08` here.)
  3. *Unpinned `seamspec.yml` in `enforced` mode (`check.py:861`):* `_seamspec_strict` skips `ssc.unpinned(workflow)` whenever `mode != "strict"`. If a repository ran `seamspec init --ci` in `enforced` mode (leaving SeamSpec's tag-pinned `.github/workflows/seamspec.yml`), `swerepo check` misses it even though ADR-cd64 point 3 covers `seamspec` without `ci` too—and if `ci` is present, `zizmor` will fail `ci-ok`.
- **Suggested fix:**
  Pass the resolved `adr_dir` into `_seamspec` / `_hygiene_applies`, require valid (unbroken) index markers for `adr-index` and `_UNRELEASED` in `CHANGELOG.md` when not newly created, apply the same subject check in `check._seamspec_rules` so unapplicable hygiene rules aren't reported as `"not proposed yet"`, and check `ssc.unpinned` whenever `.github/workflows/seamspec.yml` exists regardless of `mode`.

##### P7-F07 · should-fix · `swerepo/init.py:1350-1363`, `swerepo/cli.py:204-223, 268, 356-417`
**`swerepo -u --seamspec` omits `ADR-20261124-cd64` point 8 / Spec §13 steps (`doctor`, version/upgrade note, and rerunning `seamspec init` after `--yes` moved the pin)**

- **Failure scenario:**
  1. *`--yes` advances the pin and masks the pending terminal `seamspec init` (`init.py:1350`):* Upgrade SeamSpec from `0.1.2` to `0.2.0` and run `swerepo -u --seamspec --yes` (e.g., from an agent or script). That run updates `swerepo-ci.yml` and `[tools] seamspec` to `"0.2.0"` while printing `waiting: run it in a terminal: seamspec init ...`. When the person then runs `swerepo -u --seamspec` in their terminal as instructed, `ctx.seamspec_pin` is `None` (`0.2.0` is no longer newer than `[tools] seamspec`), so `swerepo -u --seamspec` says `"Nothing to do."` without ever refreshing SeamSpec's host blocks or Claude plugin.
  2. *Spec §13 / ADR-cd64 point 8 mismatch:* Both Spec §13 (items 1–2 and 5) and ADR-cd64 point 8 state that `swerepo -u --seamspec` reports the installed SeamSpec version against the CI pin with `uv tool upgrade seamspec`, and finishes by running `seamspec doctor` and reporting its result; neither runs in `update` today. *(Also, `cli.init`'s docstring at `cli.py:268` still lists only `docs`, `agents`, `ci`, `security` and `github`.)*
- **Suggested fix:**
  Allow `swerepo -u --seamspec` in a terminal to rerun `seamspec init` (or track the version `seamspec init` last ran at separately from the CI workflow pin so `--yes` bumping the pin doesn't skip the terminal refresh), implement the version/upgrade note and post-update `ssc.doctor` report in `update` when `seamspec` is updated (or update Spec §13 and ADR-cd64 point 8 if leaving `doctor` to `check`), and add `seamspec` to `cli.init`'s docstring.

#### Answers to the developer's questions

1. **Q1 (Reading SeamSpec's ledger files directly vs SeamSpec CLI):** **Sound — keep reading `.seamspec/config.toml` and `.seamspec/invariants/*.json` directly.** Those files are committed repository artifacts with a versioned schema; reading them directly is instant, works even when `seamspec` isn't installed on `PATH`, avoids brittle text scraping, and guarantees zero disk writes (`inv_294c48c9`) and zero machine-path leaks (`inv_5e3b5ef3`).
2. **Q2 (Warnings vs failures for unapproved hygiene rules in `check`):** **Warnings (`blocking=False`) are the right call**, while keeping `adopted-not-locked` blocking (`✗`). Approving rules in `seamspec review` is deliberate human work; failing `check --ci` while proposals await review would pressure people into rubber-stamping rules on Day 1. (Once `P7-F06` skips rules whose subject doesn't apply, the warnings will be exact.)
3. **Q3 (The adoption prompt `_ask_adopt` listing every locked rule):** **Good as-is for typical repositories (0–15 rules), with a small cap recommended:** if `len(locked) > 15`, consider printing the first 15 (or keyword-relevant ones first) plus `"... and N more (seamspec status)"` while still accepting any valid locked `inv_...` ID typed at the prompt.
4. **Q4 (Text matching in `ci-tests` and git globs in `privacy`):** **`privacy`'s NFA-style `_glob_matches` is clean, linear-time, and matches `swerepo/globs.py`** (just needs `P7-F05`'s `POLICY_PATHS` and file guards). **`ci-tests` needs `P7-F04`'s step-level and block-`needs:` tightening** so step-level `if: false` / `continue-on-error: true` / `|| true` can't bypass it and `uv run --locked pytest` stays valid—still pure stdlib text without PyYAML.
5. **Q5 (The proposed rules & `critical` flags):** **Right four component rules, and right choice making only `inv_c45b7540` `critical: true`** (the consent/terminal boundary is the irreversible trust invariant, while the other three are tightly file-scoped and still run on every commit and CI job). Before locking in `seamspec review`, tighten `inv_2f78270e` to cover `P7-F01` (`strict` mode holding all pins when `seamspec.yml` can't take the new pin) and re-propose `inv_5c45ea08` / `inv_c78fcca0` once `P7-F04` and `P7-F06` are in.

### Developer responses

Every finding was reproduced first, and every fix has a regression test in `tests/test_seamspec.py::TestReviewP7`. Each test was checked by breaking the fix on purpose: it fails every time.

| ID | Response | What changed |
|---|---|---|
| P7-F01 | **Fix** | The pin hold is now symmetric. After planning, `make_plan` checks every workflow that pins SeamSpec: `swerepo-ci.yml`, and SWERepo's `seamspec.yml` in strict mode. If any of them can't take the new pin (a merge waiting, a conflict, or a file SWERepo doesn't manage), it replans with `hold_pin=True`, so nothing moves, and adds a note saying which file held it. The one-way `held` is gone. `inv_2f78270e` gains your strict-mode case, and fails without the fix. |
| P7-F02 | **Fix, all three cases** | (1) `seamspec.yml` is planned only once SeamSpec is set up or set up in this run, so a waiting run writes nothing. (2) `_new_state` writes `.swerepo.toml` whenever the plan writes a file it records, even before `seamspec` counts as applied, so `seamspec.yml` and `[tools] seamspec` are recorded after `init --only docs`, and on a fresh repository. (3) `apply_seamspec` loads `State.load(root) or State.new()`. |
| P7-F03 | **Fix** | (1) `ssc.safe_target`: the earned spec is neither planned nor written (`write_earned_spec`) when `docs/EARNED_SPEC.md` is a link or leads out of the repository. (2) When SeamSpec is set up but `seamspec` isn't installed on this machine, the component waits, with `uv tool install seamspec==<pin>`; no `propose` or `run` is planned, so repeated runs stay idempotent. |
| P7-F04 | **Fix** | `hygiene/ci-tests@1` (not yet released, so changed in place) now reads each job step by step. A pytest step with `if: false` or `continue-on-error: true` doesn't count, nor does a run masked with `||`, `;`, `--version`, `--help` or `--collect-only`. `uv run` options such as `--locked` are fine. A block `needs:` list ends where it ends. The scope gains `.swerepo.toml`. The template's own tests cover each case; `inv_4eaaa886` adds the step-level breakages, and `inv_c78fcca0` here was refreshed. |
| P7-F05 | **Fix** | `hygiene/privacy@1` now matches `swerepo privacy`: the security policy wherever GitHub reads it (`SECURITY.md`, `.github/SECURITY.md`, `docs/SECURITY.md`), links and files over 2 MB skipped, file names from git read as bytes, and `_declared_emails` safe on odd `pyproject.toml` contents. `inv_4eaaa886` now runs with the policy in `.github/`. |
| P7-F06 | **Fix** | `ssc.applies` is the one test of whether a rule has a subject: an ADR README with one intact index (broken markers don't count), a `CHANGELOG.md` that already has `[Unreleased]`, or a `swerepo-ci.yml`. `init` uses it, plus what its plan creates; `check` uses it before reporting "not proposed yet". `_seamspec` receives the ADR folder `make_plan` resolved, so a first run follows an adopted `doc/decisions/`. An unpinned `seamspec.yml` is reported in any mode, by the plan and by `check` (`_seamspec_workflows`). `inv_5c45ea08` here gains `.swerepo.toml` in its scope. |
| P7-F07 | **Fix** | `[seamspec] initialised` records the SeamSpec version `seamspec init` last ran with, apart from the CI pin. Adopting an existing SeamSpec records the installed version, and a terminal rerun updates it. So an `update --yes` that moved the pin still leaves the terminal rerun to do. `update` now notes the installed version against the pin, with `uv tool upgrade seamspec` (run by the person), and reports `seamspec doctor` by check name after applying. `cli.init`'s docstring names `seamspec`. Spec §9 shows the key. |

**The questions:**

- **Q1–Q2:** Accepted as answered: the ledger stays read from SeamSpec's files, and rules not yet approved only warn. With P7-F06, those warnings appear only where the rule has a subject.
- **Q3:** **Deferred** to the first repository with many locked rules. With the 20 here, the list is readable, and any valid id is accepted at the prompt.
- **Q4–Q5:** Accepted, and done: P7-F04 and P7-F05 tightened the rules; `inv_2f78270e`, `inv_4eaaa886`, `inv_5c45ea08` and `inv_c78fcca0` were refreshed before your review, and only `inv_c45b7540` is suggested critical.

**One more change, found on the way:** `inv_022998a0`'s test asserted that the fake `seamspec` had never been called. Since P7-F07, `init` reads `seamspec --version` while planning, so the test now counts only the calls `check` itself makes. It still fails when `check --ci` calls SeamSpec.

**Dogfood:** this repository now records `[seamspec] initialised = "0.1.2"`. A second `init` and `update` have nothing to do.

**Results** (2026-11-24): pytest **743 passed** (also with `GITHUB_ACTIONS=true TERM=dumb`); ruff clean; locked rules 20 passed; proposed rules 6 passed; `seamspec spec --check` clean; `check` exits 0 (warnings only); privacy nothing found; zizmor no findings.

Ready for round 2.

### Round 2

**Reviewer:** Gemini · **Date:** 2026-11-24

#### Verification run

Every command under "How to run" (plus `privacy`, `zizmor`, and Round 2 adversarial probes) was executed:

- `uv sync` → clean (`Audited 47 packages`).
- `uv run pytest` → **743 passed** (`166.76s`).
- `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **743 passed** (`169.01s`).
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (`165 files already formatted`).
- `uv run seamspec verify --all` → **20/20 locked rules passed**.
- `uv run seamspec verify --proposed inv_c45b7540 --proposed inv_022998a0 --proposed inv_4eaaa886 --proposed inv_2f78270e --proposed inv_5c45ea08 --proposed inv_c78fcca0` → **6/6 proposed rules passed**.
- `uv run swerepo init --only seamspec --dry-run` → `Nothing to do.` (exit `0`).
- `uv run swerepo check --only seamspec` → exit `0` (`4` warnings only; `[seamspec] initialised = "0.1.2"` recorded).
- `uv run swerepo update --dry-run` → prints the version/upgrade note and `"Nothing to do."` (exit `0`).
- `uv run swerepo privacy` → `"swerepo privacy: nothing found"` (exit `0`).
- `uvx zizmor==1.32.0 --offline .github/workflows` → `No findings to report`.

All five core safety properties were re-checked against the Round 2 diff and hold:
1. SWERepo never passes `--accept-auto-run`, never runs `seamspec init` without an interactive terminal, and never installs or upgrades SeamSpec.
2. `check` remains strictly read-only, calls zero SeamSpec subprocesses under `--ci`, and never prints raw SeamSpec messages.
3. `.swerepo.toml`, `swerepo-ci.yml`, and SWERepo's `seamspec.yml` move their SeamSpec pin together or not at all (`hold_pin=True`), and never backwards or to a dev build.
4. Rejected or superseded SWERepo hygiene proposals are never proposed again.
5. All four bundled hygiene templates use only stdlib + `pytest`, pass `ruff`, pass on repositories `init` sets up, and fail on the breakages they guard.

#### Dispositions of Round 1 items

| Item | Disposition | Notes |
|---|---|---|
| P7-F01 | **Accept** | Symmetric `hold_pin=True` replan in `make_plan` holds all workflow pins and `[tools] seamspec` whenever any workflow pinning SeamSpec cannot take the new pin, with a clear plan note. Verified in `TestReviewP7` and refreshed `inv_2f78270e`. |
| P7-F02 | **Accept** | `seamspec.yml` is planned only when `set_up` is true (`waiting` writes nothing), `_new_state` records written files before `seamspec` counts as applied, and `apply_seamspec` loads `State.load(root) or State.new()` (recovering cleanly even if `seamspec init` is aborted and retried). *(See `P7-F09` below for one brownfield `pr.enforce` interaction when `State.new()` writes the first `.swerepo.toml`.)* |
| P7-F03 | **Accept** | `ssc.safe_target` blocks symlinks and external paths (including a symlinked parent `docs/` directory) in both planning and `write_earned_spec`, and missing `seamspec` on `PATH` with an initialised `.seamspec/config.toml` waits idempotently. |
| P7-F04 | **Accept** | `hygiene/ci-tests@1` (and refreshed `inv_c78fcca0` and `inv_4eaaa886`) now checks steps individually, rejects step-level `if: false`, `continue-on-error: true`, `||`, `;`, `--version`, `--help`/`-h`, and `--collect-only`/`--co`, accepts `uv run` options such as `--locked`, terminates block `needs:` cleanly, and includes `.swerepo.toml` in `scope_paths`. |
| P7-F05 | **Accept** | `hygiene/privacy@1` matches `swerepo privacy` (`SECURITY.md`, `.github/SECURITY.md`, `docs/SECURITY.md`, symlink and `> 2 MB` skips, `surrogateescape` filename decoding, and safe `_declared_emails`). |
| P7-F06 | **Accept** | `ssc.applies` unifies subject checks between `init` and `check`, `_seamspec` uses the resolved `adr_dir` on first runs, `_seamspec_workflows` reports unpinned `seamspec.yml` in any mode, and `inv_5c45ea08` includes `.swerepo.toml` in `scope_paths`. |
| P7-F07 | **Accept** | `[seamspec] initialised` tracks `seamspec init`'s version separately from `[tools] seamspec`, `update` reports the installed/pinned version note and post-apply `seamspec doctor` check names, and `cli.init`'s docstring names `seamspec`. |
| Q1 | **Accept** | Direct file reads for `Ledger.read` remain in place. |
| Q2 | **Accept** | Unapproved rules warn (`blocking=False`) only when their subject applies; `adopted-not-locked` blocks. |
| Q3 | **Accept** | Deferring adoption-prompt truncation until a repository has enough locked rules to warrant it is pragmatic. |
| Q4 | **Accept** | Addressed by `P7-F04` and `P7-F05`. |
| Q5 | **Accept** | Only `inv_c45b7540` is suggested `critical: true`; all refreshed proposals (`inv_2f78270e`, `inv_4eaaa886`, `inv_022998a0`, `inv_5c45ea08`, `inv_c78fcca0`) were inspected and verified, including `inv_022998a0`'s `[earlier:]` slice isolating `check`'s own calls. |

#### New findings

##### P7-F08 · should-fix · `swerepo/cli.py:204-229, 320-325, 409-415`
**`--json` output on `init --yes --json` and `update --yes --json` is invalid JSON when `seamspec` proposes rules (and `write_earned_spec` runs even when `plan.seamspec_spec` is `False`)**

- **Failure scenario (reproduced):**
  On a repository with `.seamspec/config.toml` already set up and `seamspec` on `PATH`, run `swerepo init --yes --code-owner @dev --json` (or `swerepo update --yes --json` when a hygiene rule is newly proposed). `_seamspec_after` (`cli.py:209-212`) unconditionally echoes `apply_seamspec`'s `lines` (`hygiene/privacy: proposed as inv_…`, `Verified: each proposed rule passes here.`) directly to stdout before `cli.init` / `cli.update` prints `json.dumps(result)`, and resets `lines = []`. Stdout begins with plain text before `{`, so `json.loads` fails with `JSONDecodeError`, and `result["seamspec"]` drops the proposal and verification messages. In addition, `cli.py:219` calls `write_earned_spec(path)` unconditionally even when `plan.seamspec_spec` is `False` (for example when `docs/EARNED_SPEC.md` is a symlink—printing the `"not written"` message a second time—or during `update` when `make_plan` already checked that `EARNED_SPEC.md` is current).
- **Suggested fix:**
  Echo `apply_seamspec`'s lines inside `_seamspec_after` only when `interactive` is `True` (so terminal users see the proposed IDs before `typer.confirm("Review the proposed rules now…")`); when `not interactive` (`--yes` and `--yes --json`), keep `apply_seamspec`'s lines in the returned `seamspec_lines` list so text mode prints them under `Applied:` and `--json` emits one valid JSON object containing every message. Gate `write_earned_spec(path)` on `if plan.seamspec_spec:`.

##### P7-F09 · should-fix · `swerepo/init.py:1685, 1759-1763, 1962-1968`
**First-run `swerepo init --only seamspec` in a terminal on a brownfield repository without a recorded file write creates `.swerepo.toml` via `State.new()`, bypassing Spec §10's warn-only PR rules**

- **Failure scenario (reproduced):**
  On an existing repository with commits (`_has_commits(root)` is `True`) and no `.swerepo.toml` yet, run `swerepo init --only seamspec` in a terminal when no workflow file is written by SWERepo (for instance a Poetry/setuptools repository where `seamspec.yml` is skipped, or a repository that already has a `seamspec.yml`). `_new_state` (`init.py:1685`) returns `None`, and after `seamspec init` succeeds, `apply_seamspec` (`init.py:1962-1968`) saves `.swerepo.toml` from `State.new()` without setting `[pr] enforce = false`. When the team later runs `swerepo init --yes` for the remaining components (gradual adoption, Spec §10), `ctx.state` is already present so `if ctx.state is None:` (`init.py:1759`) is skipped, leaving `state.pr_enforce == True` instead of warn-only on an existing repository.
- **Suggested fix:**
  In `apply_seamspec`, when `State.load(root)` is `None` and `State.new()` creates `.swerepo.toml` for the first time, apply the same `_has_commits(root)` rule as `_new_state` (`state.set_pr_rules(enforce=False, warn_since=datetime.date.today())` when commits exist, else `state.set_pr_rules(enforce=True)`).

##### P7-F10 · suggestion · `swerepo/seamspec_component.py:151-159`
**Explicit `[seamspec.adopted]` / `--adopt` is shadowed if an earlier bundled proposal for that rule was rejected or superseded**

- **Failure scenario:**
  Suppose `swerepo init` proposed `hygiene/privacy@1` (`inv_11111111`), the owner rejected it in `seamspec review` (`REJECTED`) in favour of writing a custom locked rule `inv_22222222`, and then ran `swerepo init --only seamspec --adopt privacy=inv_22222222`. `.swerepo.toml` saves `[seamspec.adopted] privacy = "inv_22222222"`, yet `Ledger.hygiene` checks `("REJECTED", "declined")` and `("SUPERSEDED", "declined")` before `if name in adopted:`, so `init` and `check` continue reporting `declined (inv_11111111)` and never verify that `inv_22222222` stays `LOCKED`.
- **Suggested fix:**
  In `Ledger.hygiene`, check `LOCKED` and `PROPOSED` first, then `if name in adopted:`, and check `REJECTED` / `SUPERSEDED` (`declined`) last before `"missing"`, so an explicit adoption takes effect while un-adopted declined rules still never get re-proposed.

**Phase status:** Phase 7 **cannot close yet** — Round 1's items (`P7-F01`–`P7-F07` and `Q1`–`Q5`) are all accepted, and only `P7-F08`–`P7-F10` remain for a brief Round 3.

### Developer responses (round 2)

All three are fixed, each with a regression test in `TestReviewP7`. Each test fails when its fix is reverted.

| ID | Response | What changed |
|---|---|---|
| P7-F08 | **Fix** | `_seamspec_after` echoes `apply_seamspec`'s lines only in a terminal, where they come before the question about reviewing the proposals. Otherwise they are returned, so `--yes` prints them after "Applied:" and `--json` prints one object with all of them under `"seamspec"`. `write_earned_spec` runs only when the plan holds it (`plan.seamspec_spec`), so a linked `docs/EARNED_SPEC.md` gets one note, not two. Test: `--yes --json` output parses, and holds the proposal lines. |
| P7-F09 | **Fix** | When `apply_seamspec` creates the first `.swerepo.toml`, it applies the same rule as `_new_state` (spec §10): a repository with commits starts with warn-only pull-request rules, and a new one with them enforced. Test: a repository with history and no Python project (so no `seamspec.yml`) ends with `pr_enforce == False`. |
| P7-F10 | **Fix** | `Ledger.hygiene` checks in this order: SWERepo's locked or proposed rule; then the person's adoption; then a SWERepo rule they declined. An adoption made after rejecting SWERepo's rule now counts, and `check` verifies that the adopted rule stays locked. An un-adopted, declined rule is still never proposed again. |

**Results** (2026-11-24): pytest **746 passed** (also with `GITHUB_ACTIONS=true TERM=dumb`); ruff clean; locked rules 20 passed; proposed rules 6 passed; on this repository, `check` exits 0 (warnings only), `init --only seamspec` and `update` have nothing to do, privacy nothing found, zizmor no findings.

Ready for round 3.

### Round 3

**Reviewer:** Gemini · **Date:** 2026-11-24

#### Verification run

Every command under "How to run" (plus `privacy`, `zizmor`, and Round 3 probes on `P7-F08`–`P7-F10`) was executed:

- `uv sync` → clean (`Audited 47 packages`).
- `uv run pytest` → **746 passed** (`170.77s`).
- `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **746 passed** (`172.60s`).
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (`165 files already formatted`).
- `uv run seamspec verify --all` → **20/20 locked rules passed**.
- `uv run seamspec verify --proposed inv_c45b7540 --proposed inv_022998a0 --proposed inv_4eaaa886 --proposed inv_2f78270e --proposed inv_5c45ea08 --proposed inv_c78fcca0` → **6/6 proposed rules passed**.
- `uv run swerepo init --only seamspec --dry-run` → `Nothing to do.` (exit `0`).
- `uv run swerepo check --only seamspec` → exit `0` (`4` warnings only).
- `uv run swerepo update --dry-run` → prints the version/upgrade note and `"Nothing to do."` (exit `0`).
- `uv run swerepo privacy` → `"swerepo privacy: nothing found"` (exit `0`).
- `uvx zizmor==1.32.0 --offline .github/workflows` → `No findings to report`.

All core safety properties were re-confirmed on the Round 3 diff:
- SWERepo never answers SeamSpec's consent, never runs `seamspec init` without a terminal, and never installs or upgrades SeamSpec;
- `check` remains strictly read-only and invokes zero SeamSpec commands under `--ci`;
- the SeamSpec pin never disagrees across `.swerepo.toml`, `swerepo-ci.yml`, and `seamspec.yml`, and never moves backwards or to a development build;
- the bundled hygiene tests pass on healthy repositories and fail on the breakages they guard.

#### Dispositions of Round 2 items

| Item | Disposition | Notes |
|---|---|---|
| P7-F08 | **Accept** | `_seamspec_after` (`swerepo/cli.py:204-230`) echoes `apply_seamspec`'s lines early only when `interactive` is `True` (before the `seamspec review` prompt), and returns them otherwise—verified that both `init --yes --json` and `update --yes --json` emit a single valid JSON object holding SeamSpec's lines, and that `write_earned_spec` runs only when `plan.seamspec_spec` is set. Covered by `test_p7_f08_*`. |
| P7-F09 | **Accept** | `apply_seamspec` (`swerepo/init.py:1962-1968`) applies Spec §10's `_has_commits(root)` check when creating the first `.swerepo.toml`: repositories with commit history start with `pr_enforce == False` (preserved across subsequent `init` runs), and brand-new repositories without commits start with `pr_enforce == True`. Covered by `test_p7_f09_*`. |
| P7-F10 | **Accept** | `Ledger.hygiene` (`swerepo/seamspec_component.py:147-168`) checks SWERepo's `LOCKED`/`PROPOSED` rule first, then `[seamspec.adopted]` (`adopted` / `adopted-not-locked`), then SWERepo's `REJECTED`/`SUPERSEDED` rule (`declined`), and finally `missing`. Explicit adoptions take effect (and `check` verifies they stay `LOCKED`), while un-adopted declined rules are still never proposed again. Covered by `test_p7_f10_*`. |

#### New findings

None.

**Phase status:** **Phase 7 can close** — every finding (`P7-F01`–`P7-F10`) and question (`Q1`–`Q5`) is resolved and verified, ready for the owner's `seamspec review` on the 6 proposed rules.

### Closing

Round 3 found nothing new and accepted P7-F08 to P7-F10. All ten findings (P7-F01 to P7-F10) and the five questions are resolved, each fix with a regression test. Q3 is deferred to the first repository with many locked rules. The review is closed.

- **Since round 3, before the owner's approval:** SeamSpec's reviewer read the six proposals twice. The owner asked for every point to be fixed both times.
  - **One code fix:** `ci.seamspec_pin` found SeamSpec with `shutil.which`, so a locked test could have depended on the SeamSpec installed on the machine. Every lookup now goes through `seamspec_component.command()`.
  - **One gap in what a rule protected:** `hygiene/ci-tests` checked that `ci-ok` waits for the test jobs, but not that it still fails when they fail. It now requires `if: always()` and a step that reads the jobs' results and can exit non-zero, so replacing that script with `echo ok` breaks the rule. Both CI template versions already have that shape.
  - **The templates:**
    - `hygiene/adr-index` counts only each row's own link, so an ID in a "SUPERSEDED by" cell no longer hides a missing row, and it tests the adopted ADR folder;
    - `hygiene/ci-tests` joins folded blocks and continuations, and catches quoted and `${{ }}` forms, `&`, `--help`, and `ci-ok` switched off.
  - **The four rules about the component:**
    - they run through the command line with a terminal, with the fake `seamspec` on PATH;
    - they refuse any `--accept-auto-run` form, check what `--yes` applies, and check that the review runs only on a yes;
    - `spec --check` is really exercised, with folders' modification times and all four hygiene statuses checked;
    - exit codes are checked, and each test file runs alone;
    - when the pin doesn't move, whole files are compared byte for byte, local builds included, and strict mode moves all three pins together.
  - **Checked:** each change was confirmed by breaking the code it guards, one breakage at a time, and the matching rule failed every time.
- **The owner's approvals (2026-11-24):**
  - `inv_c45b7540` (critical), `inv_022998a0`, `inv_4eaaa886` and `inv_2f78270e`: the component's rules;
  - `inv_5c45ea08` and `inv_c78fcca0`: the ADR-index and CI-tests hygiene rules on this repository.
  - That makes 26 rules locked, all passing. `docs/EARNED_SPEC.md` was regenerated, and `seamspec spec --check` is clean.
- **Final run:** pytest 746 passed (also with `GITHUB_ACTIONS=true`); 26 locked rules passed; ruff, privacy, zizmor and `check` clean; `update --dry-run` on this repository: "Nothing to do."
- **Deferred:**
  - strict mode running the locked rules twice with `ci` (ADR-cd64 point 3);
  - shortening the adoption question when a repository has many locked rules (Q3);
  - reporting to SeamSpec that its text `doctor` output counts warnings without naming them.
- **Next:** the pull request for Phase 7.

## Copilot's review of PR #20

Six inline comments, each reproduced as a test before the fix and each fix checked by breaking it again (14 breakages, all caught):

- **A recorded `seamspec.yml` kept current** (init.py, `_seamspec`): with `ci` added after `seamspec.yml` was written, `update --only seamspec` moved `swerepo-ci.yml` and `[tools] seamspec` but left `seamspec.yml` behind. A recorded `seamspec.yml` is now always planned, so it takes the pin or holds it.
- **`--no-ci` holds the pin** (init.py, the pin check): `ci` skipped meant "no workflow" to the check, so `seamspec.yml` and `[tools] seamspec` moved while `swerepo-ci.yml` stayed. A recorded workflow that isn't planned now holds the pin, both ways.
- **The pin alone rebuilds the recorded workflow** (init.py, `_ci_pin_only`): `ci` brought along for the pin ran the whole `ci` planner, so a `ci/workflow@1` record was upgraded to version 2 and the pyproject settings could change. The recorded template and inputs are now rebuilt with only `seamspec` changed, nothing else of `ci` is planned, and a record without inputs holds the pin with a note. `pin_only` and `_refreshes` went with it.
- **No guessed Python for `seamspec.yml`** (init.py, `_seamspec_workflow`): `requires-python = ">=3.15"` got a workflow on 3.14. It is now not written, with the reason, as `swerepo-ci.yml` does.
- **`hygiene/ci-tests` reads the whole script** (two comments): `set +e` before pytest, `uv run pytest && echo passed` followed by another command, a pipe, an earlier `exit`, a pytest inside `if false`, and a shell without `-e` no longer count; `ci-ok` must assign the results from `$NEEDS` and then fail through `if [ -n "$var" ]; then … exit N … fi`, so `if false; then`, a leading `exit 0`, an `exit 0` first in the block, an overwritten variable, `set +e` or another shell break the rule. This repository's `swerepo-ci.yml` and what `init` writes still pass.
  - **The locked copy here:** `inv_c78fcca0` is not edited. The new template was proposed as `inv_11ce8c5b` (verified passing) with a supersede request; the owner approved it (2026-11-24), so `inv_11ce8c5b` is locked and `inv_c78fcca0` superseded.
