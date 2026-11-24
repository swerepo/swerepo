# Code Review · Phase 6: swerepo update, merge, diff and status

**Status:** closed · **Rounds:** 3 · **Developer:** Claude · **Reviewer:** Gemini · **Owner decides:** ties, merges, SeamSpec approvals
**Process:** ADR-20261119-9f87. Finding IDs `P6-F<nn>`; severities `blocker | should-fix | suggestion | question`; responses Fix / Push back / Defer, then Accept / Maintain.

---

## Developer summary

### Scope

Spec §16 and the commands around it:

- **`swerepo update`** (`-u`; `swerepo/init.py`, `swerepo/cli.py`): `init`'s planner with the update verbs turned on (ADR-20261124-7afa point 1).
  - **Untouched and outdated:** `rewrite` with the new render.
  - **Edited by a person:** `merge` against the earlier render, shown as a diff. It is applied after a yes in a terminal, or with `--yes --merge`; `--yes` alone never merges into a person's edits (the owner's choice). A workflow that differs only by newer action pins (Dependabot's) is updated with `--yes` alone.
  - **`conflict`** and **`can't merge`** (no trustworthy earlier render): the file is left byte for byte; `swerepo diff` shows the change to make by hand.
  - **Dropped from the standard, or no longer chosen:** reported and kept, never deleted.
  - `--only`, shorthand flags, `--dry-run`, `--yes`, `--merge`, `--json`, `--enforce-pr-rules`.
- **The three-way merge** (`swerepo/merge.py`, ADR-20261123-f571): action pins are settled line by line on all three sides, then `git merge-file -p` merges the rest. No conflict markers are ever written.
- **Rebuilding the earlier render** (`swerepo/rebuild.py`): from a template id and the record's `inputs`. Trusted only when its fingerprint is the record's `rendered`.
- **Per-record `inputs`** in `.swerepo.toml` (`swerepo/state.py`; ADR point 10, the owner's watchout). Each record keeps the values its render used.
  - **Older records** get them on the next `update` when this run's inputs, or `[values]` as recorded before the run, rebuild the recorded render (the owner's backfill idea).
  - **`update` renders with the project's current `commands` and `test_inline`;** `init` keeps the recorded ones and notes the change.
- **`swerepo diff [FILE ...]`** and **`swerepo status [--json]`**: read only.
- **`swerepo check`:** a workflow that differs from SWERepo's render only by newer action pins is current, shown as `(current, newer action pins)`.
- **Smaller:**
  - `GitHub.find_ruleset` reads every page of rulesets (a Phase 5 note);
  - `init`'s plan explains `delete_branch_on_merge` when it creates `repo-settings.json` (a Phase 5 note).
- **Dogfooded:** `swerepo update` on this repository rewrote the AGENTS.md block and `docs/agents/address-review.md` to version 2, and backfilled `inputs` on all 12 records.

Gemini reviewed the merge on its own first (M6-F01–F04: CRLF, raw versions, a lowered pin, and `check` normalising). All four are fixed with tests, and the fixes are in this round.

Branch `phase-6/update`, uncommitted. Spec updated to v0.14.

### What to review

| Area | Files |
|---|---|
| The merge | `swerepo/merge.py` (`pin`, `Pin`, `pins_only_newer`, `_aligned`, `_settle`, `merge3`, `_git_merge`) |
| Rebuilding | `swerepo/rebuild.py` (`used`, `workflow_inputs`, `settings_block_inputs`, `github_inputs`, `rebuild`) |
| The planner | `swerepo/init.py`: `_for_update`, `_earlier_render`, `_dropped`, `_diff`; the verbs `MERGE`, `CONFLICT`, `CANT_MERGE`; `REFRESHED_VALUES` and `_Context.before`; `inputs` passed at every `_managed_file` / `_managed_block` call; `_new_state` (records with inputs, backfill); `apply` / `_check_target` / `_check_unchanged` for `MERGE` |
| Command line | `swerepo/cli.py` (`_update_plan`, `update`, `diff`, `status`, `main`'s `-u`) |
| State | `swerepo/state.py` (`Record.inputs`, `_set_record`, `_records`, `_inline`, `_check_inputs`) |
| check | `swerepo/check.py` (`_only_newer_pins` in `_record`) |
| GitHub | `swerepo/github.py` (`find_ruleset` pages) |
| Tests | `tests/test_merge.py`, `tests/test_update.py` (new); `TestRecordInputs` in `tests/test_state.py`; `TestRulesetPages` and the delete-branch note in `tests/test_github.py` |
| ADRs | `docs/adr/ADR-20261123-f571-action-pins.md`, `docs/adr/ADR-20261124-7afa-update-command.md` |
| Spec | `SWEREPO-SPEC.md` §7 (`--merge`, `diff`, `status`), §9 (`inputs`), §16, Appendix A "0.13 → 0.14" |
| Proposed rules | `.seamspec/proposed/inv_60788941/`, `inv_d60ffffd/`, `inv_9265607a/`; decision `.seamspec/adrs/ADR-20261123-5e14-…` |
| Dogfood | `AGENTS.md` (block @2), `docs/agents/address-review.md` (@2), `.swerepo.toml` (inputs) |
| Docs | `docs/PROGRESS.md`, `docs/progress/20261124-phase-6-update.md`, `CHANGELOG.md` |

### ADRs written

| ADR | Decision |
|---|---|
| ADR-20261123-f571 | Action pins: Dependabot owns them between releases. `update` keeps the newer pin and never moves one backwards. A pin line is the identical action path, a 40-character lowercase commit and a `# v<version>` that `packaging` reads, with nothing else changed. One version pinned to two commits is a conflict in `update` and `changed` in `check`. `check` counts newer pins alone as current. The PR rule for workflows still compares against `written`. |
| ADR-20261124-7afa | `update` is `init`'s planner. A merge into a person's edits needs a deliberate yes (`--merge` without a terminal); Dependabot's pins alone don't. The base is rebuilt and verified against `rendered`, or there is no merge. Dropped items are reported, never deleted. Each record keeps its render's inputs. Covers `diff` and `status`. |

### How to run

```bash
uv sync
uv run pytest
GITHUB_ACTIONS=true TERM=dumb uv run pytest
uv run ruff check . .seamspec/proposed/
uv run ruff format --check . .seamspec/proposed/
uv run seamspec verify --all
uv run seamspec verify --proposed inv_60788941 --proposed inv_d60ffffd --proposed inv_9265607a
uv run swerepo update --dry-run      # on this repository: "Nothing to do." (already dogfooded)
uv run swerepo status                # 12 current
uv run swerepo diff                  # "Nothing to show"
uv run swerepo check                 # 0 missing, 0 changed by you, 0 outdated
```

To see a merge on a scratch copy, follow `tests/test_update.py::TestCommands::test_yes_alone_never_merges_into_your_edits`. It puts AGENTS.md's block back to `agents/block@1` and adds a line of your own. Then `update --yes` leaves the file alone, and `update --yes --merge` merges.

### Results (run by the developer on 2026-11-24, macOS, Python 3.12, uv 0.9.28, git 2.50)

- **Tests:** pytest **681 passed**, plain and with `GITHUB_ACTIONS=true TERM=dumb`. New: 31 in `tests/test_merge.py`, 17 in `tests/test_update.py`, plus `TestRecordInputs`, `TestRulesetPages` and the delete-branch note.
- **Lint:** ruff check and format are clean, including `.seamspec/proposed/`.
- **SeamSpec:** locked rules 17 passed; proposed rules 3 passed.
- **This repository:**
  - **The dogfood run:** `update --yes` → "2 updated, 0 merged, 0 added" (the AGENTS.md block and `address-review.md` to @2), and inputs backfilled on 12 of 12 records.
  - **Afterwards:** `update --dry-run` → "Nothing to do."; `check` → 0 missing, 0 changed by you, 0 outdated, 0 can't tell; `status` → 12 current; `privacy` → nothing found; zizmor 1.32.0 → no findings.
- **Every record `init` writes rebuilds exactly** from its `inputs` (`TestInputs`), so `update` has a verified base for every file and block.
- **Mutation checks** (each one breaks the code on purpose, and its test must fail):
  - **Caught:**
    - the dropped-items report removed, or not limited to this run's components;
    - `update` keeping the recorded commands;
    - an older record rebuilt from the new values instead of the pre-run ones;
    - the M6 regressions (CRLF, a pin moved backwards, a lowered pin overridden, `check` not normalising).
  - **The proposed rules:** each fails when `--yes` merges unasked, when conflict markers are written, when a pin moves backwards, or when the dry run writes.

### Design notes worth checking

1. **One planner** (ADR-7afa point 1). `update` reuses `_managed_file` / `_managed_block` and so inherits their checks: links out of the repository, broken markers, and files that change between plan and apply. `_for_update` is the only update-specific step.
2. **No merge without a verified base** (point 3). `_earlier_render` tries the record's own `inputs`. For an older record without them, it tries this run's inputs, then, for a plain template, `[values]` as recorded before the run. It uses a candidate only when the rebuild's fingerprint equals `rendered`. Otherwise the result is `can't merge`, and the file is left alone.
3. **Pins are settled before `git merge-file`** (ADR-f571). `git merge-file` treats edits on neighbouring lines as a conflict, so a Dependabot bump next to a template change would conflict. `_settle` aligns base, ours and theirs with `difflib` and rewrites pin-only lines on all three sides to the newest pin.
   - A pin the person lowered is their edit and is left to git.
   - A pin line that only the new render adds is raised to the repository's newest pin for that action.
4. **`--yes` alone never merges into edits;** pins-only differences are the exception (the owner's choices). `pins_only_newer` compares the person's file with the earlier render, normalised as `check` does.
5. **Records keep only what their render used** (`rebuild.used`: the template's placeholders). Composed files keep the few settings they're built from. The security contact is never recorded with a record, since only the starter `SECURITY.md` uses it.
6. **`update` refreshes `commands` and `test_inline` only.** The default branch, the Python versions and the tool pins keep their recorded values in `update` as in `init` (see question 3).
7. **`update` writes no progress entry of its own.** `init` writes one so its own pull request passes the PR rule. An update's pull request is the person's, so they write it.
8. **Merges and rewrites are checked at apply time like `init`'s rewrites.** If the file's fingerprint changed since the plan (`expect`), nothing is written.

### Known gaps and deliberate omissions

- **The standard's changelog** (spec §16: "update can say why something changed") isn't shipped yet. Standard 1 hasn't changed; it comes with the first standard 2 change (Phase 8, release).
- **JSON settings files** (`ruleset.json`, `repo-settings.json`) are merged as text, line by line. A person's edit of the same key that the template changes is a conflict, which is the safe outcome.
- **`update --only github`** re-applies the ruleset and merge settings exactly as `init` does, after a yes (locked rule `inv_ef31cc79`). Nothing new there.
- **Released templates aren't locked by a rule yet** (Phase 8, the owner's choice). A template changed in place gives `can't merge` for repositories that recorded the old render.
- **The `status` text** is plain counts. Which file is in which state is in `update --dry-run` and `diff`.

### Questions for the reviewer

1. **Pins settled line by line before `git merge-file`** (design note 3): sound, or is there a case where rewriting all three sides changes what git would have merged?
2. **Older records rebuilt from the values recorded before the run** (design note 2): any way a wrong base could pass the fingerprint check?
3. **Refreshing only `commands` and `test_inline`** (design note 6): should `update` also take a changed default branch or `requires-python` from the project, or should those stay recorded until the person asks? (The CI matrix rule `inv_2c3b6053` locks what `init` writes from `requires-python`.)
4. **Dropped items** are matched by the record's template component against this run's components. A record of a component that isn't in this run is never reported. Right scope?
5. **The three proposed rules:** the right behaviours to lock, and critical?

### SeamSpec proposals waiting for the owner

| ID | Rule | Critical | Verified |
|---|---|---|---|
| inv_60788941 | `update` changes a file a person edited only with a deliberate yes (`--yes` alone leaves it byte for byte; `--yes --merge` merges), never writes conflict markers, and leaves a conflict or an unverifiable earlier render byte for byte | yes | passed |
| inv_d60ffffd | `update` never moves an action pin backwards, and Dependabot's newer pins alone need no `--merge` | yes | passed |
| inv_9265607a | `update --dry-run` writes nothing; `update --yes` changes only SWERepo's files and `.swerepo.toml`; a second `update` writes nothing | yes | passed |
| ADR-20261123-5e14 (decision) | Dependabot owns action pins between releases; `update` never moves a pin backwards | — | — |

The owner approves with `uv run seamspec review` after this review round. *Outcome (2026-11-24): all three locked, critical, after two rounds of tightening; the decision was re-proposed as ADR-20261124-b9d7 and accepted, and 5e14 rejected. See Closing.*

---

## Review rounds

### Round 1

**Reviewer:** Gemini · **Date:** 2026-11-24

#### Verification run

All commands under "How to run" (plus `privacy` and `zizmor`) were executed on branch `phase-6/update`:

- `uv sync` → clean (`Audited 47 packages`).
- `uv run pytest` → **681 passed** (`109.21s`).
- `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **681 passed** (`107.93s`).
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (`147 files already formatted`).
- `uv run seamspec verify --all` → **17/17 locked rules passed**.
- `uv run seamspec verify --proposed inv_60788941 --proposed inv_d60ffffd --proposed inv_9265607a` → **3/3 proposed rules passed**.
- `uv run swerepo update --dry-run` → `"Nothing to do."` (exit `0`).
- `uv run swerepo status` → `12 current` (exit `0`).
- `uv run swerepo diff` → `"Nothing to show: update changes no file you edited."` (exit `0`).
- `uv run swerepo check` → `0 missing, 0 changed by you, 0 outdated, 0 can't tell.` (exit `0`).
- `uv run swerepo privacy` → `"swerepo privacy: nothing found"` (exit `0`).
- `uvx zizmor==1.32.0 --offline .github/workflows` → `No findings to report`.

#### Audit of the four critical safety properties

1. **Never changing a person's edits without `--merge` or a terminal `y`:** Verified across `cli.update`, `_managed_file`, `_managed_block`, `_for_update`, `_rewrite_if_asked`, and `_rewrite_block_if_asked`. With `--yes` alone (`interactive=False`, `merge=False`), `ctx.merge_ok` is `False`; `_rewrite_if_asked` / `_rewrite_block_if_asked` act only on `OUTDATED` (never `CHANGED`), and `apply` re-verifies `action.expect` immediately before writing (`_check_unchanged`).
2. **Never writing conflict markers:** Verified. `merge.merge3` returns `MergeResult(None, ...)` whenever `_settle` or `git merge-file -p` reports `conflicts > 0`; stdout from `git merge-file` is discarded on any non-zero conflict count, and neither `CONFLICT` nor `CANT_MERGE` is in `WRITES`.
3. **Never merging against an unverified earlier render:** Verified. `_earlier_render` accepts a rebuilt text only when `mark(text, record.template) == record.rendered` (SHA-256 over normalised content). When no candidate matches, `_for_update` returns `CANT_MERGE` and leaves the file untouched.
4. **Never moving an action pin backwards:** Verified across all four M6 fixes (`M6-F01`–`M6-F04`) in `swerepo/merge.py`: CRLF `ours` against LF `base`/`theirs`, raw CalVer/pre-release preservation, leaving lowered `ours < base` pins to git as user edits, and normalised cross-line commit checks.

#### What is well done and should be kept

- **Single planner architecture (`swerepo/init.py`):** Sharing `_managed_file`, `_managed_block`, `_check_targets`, and `apply` between `init` and `update` avoids rule drift and preserves symlink, fence, marker, and TOCTOU (`expect` + `state_before`) protections automatically.
- **Clean separation in `swerepo/merge.py` and `swerepo/rebuild.py`:** Both modules are compact, easy to reason about, and well-tested (`TestInputs` verifying round-trip rebuild of every `init` record is especially strong).
- **Per-record `inputs` in `.swerepo.toml` (`swerepo/state.py`):** Sorted inline tables keep `.swerepo.toml` readable while preserving user comments/extra keys (`inv_afb6dfea`) and keeping starter-only values (like security contacts) out of state.
- **Dogfooding and ruleset pagination:** Updating `AGENTS.md` and `docs/agents/address-review.md` to `@2` with backfilled `inputs` on all 12 records, plus paginated `GitHub.find_ruleset` and the `delete_branch_on_merge` note, landed cleanly.

#### Answers to the developer's five questions

1. **Settling pins line by line before `git merge-file` (`merge.py:131-168`):** **Sound.** `_settle` only rewrites `(i, j, k)` when `difflib` pairs them 1-for-1, all three share the exact `skeleton`, `mine.version >= old.version`, and no version maps to two commits. Removing adjacent-line false conflicts next to `with:` changes is intended, and if non-pin lines both above and below conflict, `git merge-file` still returns `returncode >= 1` (`MergeResult(None, ...)`), so splitting a conflict hunk never causes a false clean merge. *(Tiny theoretical corner: if SWERepo itself ever shipped a template that simultaneously re-indented a pin 1-for-1, changing `skeleton`, and downgraded its version while `ours == base`, Loop 1 skips it on `skeleton` mismatch and Loop 2 skips `k` because `k in to_theirs.values()`. Templates shouldn't downgrade pins anyway, or Loop 2 could check any `k` not settled in Loop 1 whose aligned `mine` wasn't lowered.)*
2. **Rebuilding older records from pre-run `[values]` (`init.py:354-370`):** **No wrong base can pass the SHA-256 `record.rendered` check** (aside from differences `normalise` / `file_fingerprint` intentionally ignore — though see **P6-F02** on `docs/adr/README.md`'s index block). However, a partial `update --only` run can overwrite `REFRESHED_VALUES` before unselected legacy records are backfilled, stranding them in `CANT_MERGE` — see **P6-F04**.
3. **Refreshing only `commands` and `test_inline` (`init.py:48, 765, 557`):** **`update` should also refresh `requires-python` (the Python matrix) and SWERepo's own released CI command**, because `check` and the spec already promise both — see **P6-F06**. By contrast, keeping `default_branch` recorded unless `refs/remotes/origin/HEAD` explicitly names another branch is safer (running `swerepo update` on a local feature branch without `origin/HEAD` would otherwise fall back to `"main"` and clobber a `"master"` repo), and keeping `seamspec` pin updates for Phase 7's `update --seamspec` matches Spec §13.
4. **Dropped items matched by `record.template` component against this run's components (`init.py:1340-1349`):** **Right scope** in normal runs. One minor guard worth adding: if `_ci` (`init.py:768`), `_security` (`init.py:879`), or `_github` (`init.py:1120`) temporarily skips planning a recorded file because a prerequisite couldn't be read (e.g. broken `pyproject.toml` so `ci_result.inputs is None`), `path` isn't in `planned` and `_dropped` would report `no longer in the standard` right beside `not written`. Filtering `_dropped` out when a component couldn't build its workflow (or checking whether the template family still exists unless its conditional toggle — editor host, `code_owner = none` — turned it off) avoids that misleading message.
5. **The three proposed SeamSpec rules (`inv_60788941`, `inv_d60ffffd`, `inv_9265607a`):** **Yes — the right three behaviours, and all three should stay `critical: true`.** One small suggestion on `inv_d60ffffd` before the owner locks it: `test_inv_d60ffffd.py` currently tests `ours` newer than `theirs` (`v99.0.0` kept); adding a second action in the same fixture where `theirs` is newer than `ours` (and/or asserting same-version-different-commit leaves the file untouched) locks both directions of ADR-20261123-f571 at the CLI level.

#### Findings

##### P6-F01 · blocker · `swerepo/init.py:1043-1056` (also `init.py:595, 663-666, 1283, 1421, 1430`)
**`_settings_files` ignores `MERGE` on `ruleset.json` and `repo-settings.json`, writing unvalidated JSON to disk and comparing/applying stale pre-merge JSON to GitHub**

- **Failure scenario (reproduced):**
  1. *Invalid JSON / TOML written by a text-clean merge:* `ruleset.json` and `repo-settings.json` merge line-by-line via `git merge-file`. If a user removes the last property in `repo-settings.json` (leaving a trailing comma on the preceding line, or adding a key without a matching comma) while a template update edits an earlier line, `merge3` succeeds (`returncode == 0`) with syntactically invalid JSON (`json.JSONDecodeError`), or JSON failing `github.not_applicable`, and `apply` writes it straight to disk. Similarly, `_settings` (`init.py:663`) runs `_toml_problem` only on `ADD_BLOCK`, so a text-clean `MERGE` on `pyproject.toml` that duplicates a `[tool.ruff.*]` header writes unparseable TOML.
  2. *Stale pre-merge settings sent to GitHub:* When `repo-settings.json` or `ruleset.json` merges cleanly into valid JSON (e.g. the user edited `"delete_branch_on_merge": false` while the template changed `"allow_merge_commit"` from `true` to `false`), `init.py:1043` checks `if action.verb in (CREATE, REWRITE):` only. On `MERGE`, `rendered[name]` falls into the `else` branch and reads `ctx.read(path)` — the **pre-merge** file on disk! `_github_apply` then compares/applies the stale pre-merge JSON (or reports `current` on GitHub and marks `[github] applied = true` without sending the newly merged setting), leaving live GitHub out of sync with the file `apply` just wrote so `swerepo check` immediately fails.
- **Suggested fix:**
  - In `_settings_files`, handle `action.verb == MERGE`: parse `action.content` with `json.loads`, check `isinstance(..., dict)` and `not github.not_applicable(name, ...)`, and if invalid downgrade `action` to `CONFLICT` (with the template diff and `kept` backfill record, reading the existing on-disk file for `rendered[name]`). When valid, set `rendered[name]` from the merged `action.content`.
  - In `_settings` (`init.py:663`), validate that `replace_block_content(ctx.read(path), action.content, ...)` parses with `tomllib.loads` when `action.verb in (MERGE, REWRITE)`, downgrading invalid TOML to `CONFLICT`.
  - Include `MERGE` in `WRITTEN` (`init.py:595`) and in the `ruleset_verb` / `owner_written` checks (`init.py:1283, 1421, 1430`).

##### P6-F02 · should-fix · `swerepo/init.py:276-280, 389-418`
**Updating `docs/adr/README.md` (`docs/adr-readme`) wipes out the generated ADR index and turns `swerepo check` red**

- **Failure scenario (reproduced):**
  Set up a repository with `swerepo init`, run `swerepo adr new "Use Postgres"` (populating `<!-- swerepo:adr-index:begin -->` in `docs/adr/README.md`; `swerepo check` exits `0`), and ship `docs/adr-readme@2`. Because `file_fingerprint` strips `swerepo:adr-index`, `docs/adr/README.md` is classified as `OUTDATED` → `REWRITE`. However, `with_index(text, list_adrs(...))` runs only in `if not ctx.exists(path):` (`CREATE`, line 276). `_for_update` writes the raw template (`_No ADRs yet._`), erasing every listed ADR from `docs/adr/README.md` and causing `swerepo check` to fail (`exit 1`: `ADR index out of date (not listed: ADR-...)`). On `MERGE` (when the user added prose outside the index), merging `current` (with ADRs) against raw `base` and `text` (`_No ADRs yet._`) can also conflict if the template changes near the index markers.
- **Suggested fix:**
  When `template_id.startswith("docs/adr-readme@")` in `_for_update`: on `REWRITE`, keep `rendered = mark(text, template_id)` from the raw template render, then populate `text = with_index(text, list_adrs(...))` before building `diff` and `Action`; on `MERGE`, replace `current`'s `swerepo:adr-index` block with `""` (or `base`'s empty index block) before `merge3` when its markers are valid, then run `with_index` on `result.text` afterwards.

##### P6-F03 · should-fix · `swerepo/check.py:985, 1008` and `swerepo/init.py:397-399, 409`
**Dependabot pin bumps fail `check` after the first `update` that keeps a pin, and `status` / `update` still label them `"changed by you"` when no update is pending**

- **Failure scenario (reproduced):**
  1. *After one `update` keeps a Dependabot pin (`check.py:1008`):* Dependabot bumps `actions/checkout` in `swerepo-ci.yml` to `v98.0.0`. Later, `swerepo update --yes` merges a template update while keeping `v98.0.0`, recording `rendered` (template's old pin) != `written` (`v98.0.0`). On the very next Dependabot bump (`v98.0.0` → `v99.0.0`), `_only_newer_pins` (`check.py:1008`) hits `if record.inputs is None or record.written != record.rendered: return False`, so `swerepo check` permanently reports `.github/workflows/swerepo-ci.yml changed by you (kept)` on every subsequent Dependabot PR. Dropping `or record.written != record.rendered` is safe because `base` is verified against `record.rendered`, and `merge.pins_only_newer(base, text)` can return `True` *only* when `text` has zero non-pin edits relative to `base`.
  2. *Before any `update` (`init.py:397-399`):* Merge one Dependabot bump when no template update is available. `swerepo check` reports `0 changed by you` (`(current, newer action pins)`), while `_for_update` returns `CHANGED` at line 399 before checking `pins_only_newer` — so `swerepo status` reports `1 edited, nothing to update` and `swerepo update --dry-run` prints `changed   .github/workflows/swerepo-ci.yml (changed by you: kept)`.
  3. *Scope:* Neither `check.py:985` nor `init.py:409` checks `path.startswith(".github/workflows/")`.
- **Suggested fix:**
  - Gate both `check.py:985` and `init.py:409` on `path.startswith(".github/workflows/")`.
  - Remove `or record.written != record.rendered` in `check._only_newer_pins` (`check.py:1008`).
  - In `init._for_update` (`init.py:397-399`), when `action.verb == CHANGED` and the template render didn't change, check `pins_only` (`trusted and base is not None and path.startswith(".github/workflows/") and merge.pins_only_newer(base, current)`) and return `CURRENT` with note `"newer action pins"` so `check`, `status`, and `update` agree.

##### P6-F04 · should-fix · `swerepo/init.py:1265-1266, 1385-1387`
**Partial `swerepo update --only <component>` overwrites `REFRESHED_VALUES` before unselected legacy records backfill their `inputs`**

- **Failure scenario (reproduced):**
  Take a repository set up before Phase 6 (`inputs` is `None` on records in `.swerepo.toml`) where the user edited `AGENTS.md`'s block (`agents/block@1`) and added a `Makefile` with `test:` (changing `commands` and `test_inline`). Running `swerepo update --only docs --yes` backfills `docs/adr/TEMPLATE.md` and saves `.swerepo.toml`; `_new_state` (`init.py:1385-1387`) unconditionally writes the refreshed `commands` and `test_inline` into `[values]` even though `agents` and `github` were not in `applied`. Running `swerepo update --only agents --yes --merge` next fails with `can't merge (the earlier render can't be rebuilt)` on `AGENTS.md`, because `AGENTS.md` still had `inputs = None` and its pre-run `[values].commands` was clobbered by `--only docs`.
- **Suggested fix:**
  In `_new_state` when `ctx.update` is `True`, before updating `REFRESHED_VALUES` in `state.values` (or only when `"agents"` / `"github"` is in `applied`), backfill `inputs` onto any remaining plain-template legacy records (`record.inputs is None`) across `state.files()` and `state.blocks()` whose rebuild from `ctx.before` matches `record.rendered`.

##### P6-F05 · should-fix · `swerepo/rebuild.py:73, 81`
**`rebuild.github_inputs` comma-joins `extra_checks`, breaking rebuild when a GitHub status check name contains a comma**

- **Failure scenario (reproduced):**
  GitHub Actions matrix jobs routinely produce status check names containing commas, e.g. `extra_required_checks = ["test (ubuntu-latest, 3.12)"]`. `github.render("ruleset", settings)` writes one check `{"context": "test (ubuntu-latest, 3.12)"}`, whereas `github_inputs` stores `"extra_checks": ",".join(...)` and `_github_from` splits on `","` into two checks (`"test (ubuntu-latest"` and `" 3.12)"`). `rebuild` then produces a different JSON fingerprint from `record.rendered`, failing `TestInputs`'s invariant and stranding an edited `ruleset.json` in `CANT_MERGE`.
- **Suggested fix:**
  Serialise `extra_checks` with `json.dumps(list(settings.extra_checks), separators=(",", ":"))` (matching `workflow_inputs`'s `projects` encoding at `rebuild.py:44`), and in `_github_from` decode with `json.loads` when starting with `"["` (falling back to `_listed` for plain strings).

##### P6-F06 · should-fix · `swerepo/check.py:493`, `swerepo/init.py:557-563, 689-691, 765-766, 863-864`
**`check` and the spec promise `swerepo update` refreshes `requires-python` CI matrices and SWERepo's own released CI pin, yet `update` leaves both frozen**

- **Failure scenario:**
  1. When a project changes `requires-python` in `pyproject.toml` (say `>=3.11` → `>=3.12`), `swerepo check` (`check.py:493`) reports `↑ tests Python 3.11–3.14; the project declares 3.12–3.14: swerepo update` (`1 outdated`, matching `init.py:524`'s comment *"changes are `update`'s, Phase 6"*). Running `swerepo update` outputs `"Nothing to do."` because `_ci`, `_project_inputs`, and `_security` still clamp to `recorded_python` even when `ctx.update` is `True`.
  2. Spec §15 (`line 568`) and §16 (`line 592`) state that `swerepo-ci.yml`'s `uvx swerepo==x.y.z` pin (and moving off `--with-governance`'s `@main` install once SWERepo is released) is moved by `swerepo update`, yet `_command` (`init.py:560-562`) always keeps the old recorded `uvx swerepo==x.y.z` during `update`.
- **Suggested fix:**
  Now that `record.inputs` preserves each workflow's merge base independently of `[values]`, when `ctx.update` is `True`:
  - Take `python` from `shared.python` in `_ci`, fresh project `python`/`install` in `_project_inputs`, and `(shared.python or ci.DEFAULT_PYTHONS)[-1]` in `_security` so `swerepo update` resolves `check`'s `ci.python-matrix` `↑` finding.
  - In `_command`, when `ctx.update` is `True` and `shared.swerepo` is non-empty (released SWERepo or SWERepo's own checkout — never replacing a recorded command with `""` on an unreleased `.dev` build), return `(shared.swerepo, "")` so `update` advances `uvx swerepo==x.y.z`.

##### P6-F07 · suggestion · `swerepo/cli.py:346-375, 388` and `swerepo/init.py:400-402, 914`
**`swerepo diff` says `"Nothing to show"` after `update` directs the user to `swerepo diff` for `CANT_MERGE`, and `diff` / `status` make live `gh api` network calls**

- **Failure scenario (reproduced):**
  1. When `update` applies one change and leaves another item in `CANT_MERGE`, `cli.py:346-348` prints `"1 file(s) left as they are: swerepo diff shows the change to make by hand."`, yet `cli.py:366` filters `a.verb in (MERGE, CONFLICT)` only — so running `swerepo diff` prints `"Nothing to show: update changes no file you edited."`. Passing a backslash/unnormalised path or an untouched filename (`swerepo diff README.md`) prints the same message.
  2. Both `swerepo diff` and `swerepo status` call `_update_plan` with live GitHub inspection enabled (`GitHub.connect` + `repo` + `find_ruleset` + `dependency_graph` — four `gh` calls taking ~5–8s when online) even though neither command displays live GitHub state (`APPLY` actions have `path=None`).
- **Suggested fix:**
  - Attach `diff=_diff(current, text, path, ("yours", "SWERepo's new version"))` on `CANT_MERGE` (`init.py:401`) and include `CANT_MERGE` in `cli.diff` with a clear label (`"can't merge automatically (earlier render unavailable): difference from SWERepo's new version"`), normalising `files` arguments via `Path`.
  - Add `read_github: bool = True` to `make_plan` (passing `read_github=False` from `diff` and `status`) so both read-only local commands run offline in milliseconds.

### Developer responses

Every finding was reproduced first, and every fix has a regression test in `tests/test_update.py::TestReviewP6`. Each test was checked by breaking the fix on purpose: the test fails every time.

| ID | Response | What changed |
|---|---|---|
| P6-F01 | **Fix** | `_unparseable` (`swerepo/init.py`): a merge or rewrite that would leave a `.json` or `.toml` file unparseable is reported and never written. A merge becomes `conflict`; a rewrite becomes `can't merge`. For a block, the whole file is parsed with the new block in place. `_settings_files` now reads the merged `ruleset.json` and `repo-settings.json` from the action, so the merged JSON is what is checked with `github.not_applicable`, compared with GitHub and applied. `MERGE` joins `WRITTEN` and the CODEOWNERS owner check. YAML isn't parsed: SWERepo has no YAML parser among its dependencies, and CI's workflow audit reads it. |
| P6-F02 | **Fix** | `_with_adrs`: the ADR folder's README gets its index filled in on the rewrite, and on all three sides of a merge (the person's side only when its markers are intact). The index regions are then identical and never conflict. The fingerprints are unchanged, since `file_fingerprint` ignores the index. |
| P6-F03 | **Fix, all three parts** | Pins-only applies to `.github/workflows/` only, in `check` and in `update`. `check._only_newer_pins` no longer requires `written == rendered`: the base is still verified against `rendered`, and any non-pin edit still fails `pins_only_newer`. In `_for_update`, a workflow changed only by newer pins, with no template change pending, is `current` ("newer action pins"), so `check`, `status` and `update` agree. |
| P6-F04 | **Fix** | `_backfill_all`, run by `_new_state` in every `update`, gives every record without inputs, of any component, the values that rebuild it from `[values]` as recorded before the run. It only records them when the rebuild matches `rendered`, and does this before `[values]` moves on. Files built in code are left to their own component's run, since their inputs don't come from `[values]`. |
| P6-F05 | **Fix** | `extra_checks` is recorded as a JSON list. A plain comma-separated value recorded before this fix still reads, and this repository's `extra_checks = ""` still rebuilds. |
| P6-F06 | **Fix** | In `update` only: the root project's Python versions, each listed project's, and the privacy workflow's main Python come from `requires-python` as it is now. `_command` moves SWERepo's own CI command to this SWERepo's, but only when there is one: a release, or this repository's own checkout. It is never replaced with nothing on a `.dev` build. An older SWERepo can't move it back, because it refuses a `.swerepo.toml` written by a newer one (`inv_71e4b33d`). The default branch stays recorded, as you advised. `init` is unchanged: it keeps the recorded values and notes the change. |
| P6-F07 | **Fix** | `swerepo diff` shows a `can't merge` item as SWERepo's new version against the person's file, and normalises file arguments (`./AGENTS.md`, backslashes). `diff` and `status` plan with `read_github=False`, so they never call `gh` (the test asserts no call at all). |

**The questions:**

- **Q1 (the pin corner):** **Defer to Phase 8.** That corner needs a template that lowers a pin between versions. The rule locking released templates (Phase 8, the owner's choice) is the right place to forbid that. Until then the case can't occur: `rebuild` renders one template version, and its pins don't depend on inputs.
- **Q2:** **Accepted**, and fixed as P6-F04.
- **Q3:** **Accepted**, and fixed as P6-F06, with the default branch kept recorded.
- **Q4 (the guard):** **Accepted, and the scope changed.** The new P6-F01 TOML test hit exactly this: when `pyproject.toml` couldn't be read, `ci` planned no action for it, and `_dropped` called it "no longer in the standard". `_dropped` now reports only records whose template family this SWERepo no longer ships (`_shipped`). An item left unplanned for any other reason isn't reported as dropped, since its component already says why. An editor that is no longer chosen keeps its block, as before.
- **Q5:** **Accepted.** `inv_d60ffffd` is replaced (same id, still proposed). A second test checks that a pin line keeping its version but naming another commit is left byte for byte, even with `--yes --merge`. "Ours older than theirs" can't be built at the command line, because both renders come from one template version, so the `merge3` unit tests cover it. Verified: it passes, and it fails when `_settle` guesses between commits.

**Docs:** ADR-20261124-7afa points 2, 5, 8, 9, 10 and 11; spec §16 and Appendix A; CHANGELOG; the progress entry.

**Results after the fixes** (2026-11-24, macOS, Python 3.12, uv 0.9.28, git 2.50):
- **Tests:** pytest **692 passed** (11 new in `TestReviewP6`), also with `GITHUB_ACTIONS=true TERM=dumb`.
- **Lint and rules:** ruff is clean, including `.seamspec/proposed/`. Locked rules: 17 passed. Proposed rules: 3 passed, `inv_d60ffffd` with its new two-commit test.
- **This repository:** `check` → 0 missing, 0 changed, 0 outdated; `update --dry-run` → "Nothing to do."; `status` → 12 current; `diff` → nothing to show; `privacy` → nothing found; zizmor 1.32.0 → no findings.
- **Mutation checks**, each fix broken on purpose and caught by its test: no JSON/TOML check; settings applied from the file before the merge; no ADR index; `check` requiring `written == rendered`; `update` calling pins-only `changed`; no backfill before a partial run; comma-joined checks; recorded Python kept in `update`; the SWERepo pin kept; `diff`/`status` calling `gh`; `can't merge` missing from `diff`; backslash paths; `_settle` guessing between two commits (`inv_d60ffffd`).

Ready for round 2.

### Round 2

**Reviewer:** Gemini · **Date:** 2026-11-24

#### Verification run

All commands under "How to run" (plus `privacy`, `zizmor`, and Round 1 + Round 2 adversarial probes) were executed:

- `uv sync` → clean (`Audited 47 packages`).
- `uv run pytest` → **692 passed** (`115.04s`).
- `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **692 passed** (`111.82s`).
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (`147 files already formatted`).
- `uv run seamspec verify --all` → **17/17 locked rules passed**.
- `uv run seamspec verify --proposed inv_60788941 --proposed inv_d60ffffd --proposed inv_9265607a` → **3/3 proposed rules passed** (including `inv_d60ffffd`'s new two-commit test).
- `uv run swerepo update --dry-run` → `"Nothing to do."` (exit `0`).
- `uv run swerepo status` → `12 current` (exit `0`, offline/instant).
- `uv run swerepo diff` → `"Nothing to show: update changes no file you edited."` (exit `0`, offline/instant).
- `uv run swerepo check` → `0 missing, 0 changed by you, 0 outdated, 0 can't tell.` (exit `0`).
- `uv run swerepo privacy` → `"swerepo privacy: nothing found"` (exit `0`).
- `uvx zizmor==1.32.0 --offline .github/workflows` → `No findings to report`.

#### Dispositions on Round 1 items

| Item | Disposition | Verification notes |
|---|---|---|
| **P6-F01** | **Accept** | `_unparseable` blocks unparseable `.json`/`.toml` merges (`CONFLICT`) and rewrites (`CANT_MERGE`, parsing the full file with the replaced block); `_settings_files` validates and applies the merged JSON from `action.content`; `MERGE` is in `WRITTEN` and `owner_written`. Verified via `TestReviewP6` and Round 1 probes. |
| **P6-F02** | **Accept** | `_with_adrs` fills in the ADR index on `REWRITE` and on all three sides of `MERGE` (`strict=False` on `current` if markers are broken), keeping raw template fingerprints intact and preserving both user prose and the ADR index (`check` exits `0`). |
| **P6-F03** | **Accept** | `pins_only` and `_only_newer_pins` are restricted to `.github/workflows/`; `check` stays green across post-`update` Dependabot bumps (`written != rendered`); `check`, `status`, and `update` all report `current` (`newer action pins`) when no template change is pending. |
| **P6-F04** | **Accept** | `_backfill_all` populates `inputs` from `ctx.before` (verified against `record.rendered`) on all unselected legacy plain-template records before `[values]` moves on, so `update --only docs` followed by `update --only agents --merge` merges cleanly. |
| **P6-F05** | **Accept** | `extra_checks` is stored as compact JSON while `_checks` continues reading legacy comma-separated strings and `""`. |
| **P6-F06** | **Accept** | `update` refreshes root/project Python versions from `requires-python` and advances SWERepo's CI command on released builds (never replacing a recorded command with `""` on `.dev`), while keeping `default_branch` recorded. |
| **P6-F07** | **Accept** | `diff` displays `CANT_MERGE` items with a clear header, normalises `./` and `\` paths, and both `diff` and `status` run with `read_github=False` (zero `gh` calls). |
| **Q1** | **Accept** | Deferring the template-pin-downgrade check to Phase 8's released-template lock rule is clean and exact. |
| **Q2–Q3** | **Accept** | Addressed by `P6-F04` and `P6-F06`. |
| **Q4** | **Accept** | `_dropped` checking `not _shipped(ctx.store, record.template)` cleanly distinguishes dropped template families from items skipped due to unreadable prerequisites or unselected editors. |
| **Q5** | **Accept** | `inv_d60ffffd` now locks both forward Dependabot pin preservation with `--yes` alone and leaving a same-version-different-commit workflow byte-for-byte untouched even with `--yes --merge`. |

#### Safety & hand-chosen value checks after Round 2

- **Four core safety invariants:** Re-verified across all Round 2 changes — `update` still never edits a user-modified file without `--merge` or a terminal `y`, never writes conflict markers, never merges against an unverified base, and never moves an action pin backwards.
- **Hand-chosen Python matrix or SWERepo command (`P6-F06` check):** Verified by probe. If a person customizes the Python matrix (e.g. `["3.13"]`) or SWERepo command directly in `.github/workflows/swerepo-ci.yml`, `update --yes` leaves the file untouched (`KEEP`), and `update --yes --merge` preserves their custom matrix when `requires-python` didn't change (and reports `CONFLICT` rather than overwriting if both sides changed that line). In `.swerepo.toml`, `[values]` is SWERepo's render snapshot rather than user settings (Spec §9), so refreshing from `pyproject.toml` and the running release introduces no surprise — **except** for one component-scoping leak in `update --only github` noted below (`P6-F08`).

#### New findings

##### P6-F08 · should-fix · `swerepo/init.py:1358-1368`
**`swerepo update --only github` pulls in full `ci` updates via `ci_along`, rewriting `swerepo-ci.yml` and `pyproject.toml` when `ci` wasn't selected**

- **Failure scenario (reproduced):**
  Set up a repository with `swerepo init` (`docs`, `agents`, `ci`, `security`, `github`), change `requires-python` in `pyproject.toml` (`>=3.12` → `>=3.13`) — or run from a newly released SWERepo (`P6-F06`) or newer `ci` template — while Copilot review in `github` is unchanged. Run `swerepo update --only github --yes`. Because `ci_along` (`init.py:1358-1361`) adds `"ci"` to `components` and `_ci` runs with `ctx.update=True`, `swerepo update --only github --yes` rewrites `.github/workflows/swerepo-ci.yml` (and any outdated `pyproject.toml` block) even though the user explicitly asked for `--only github` (Spec §7, §16; ADR-20261124-7afa point 6). (`P5-F01` added `ci_along` for `init`, where `ctx.update=False` left `OUTDATED` `ci` items untouched unless `github` actually toggled `copilot_review`.)
- **Suggested fix:**
  When `ci_along` is `True`, either run `_ci` with `dataclasses.replace(ctx, update=False)` (so an unselected `ci` only rewrites an untouched `swerepo-ci.yml` when `github` actually changed `copilot_review`, never applying unrelated `ci` updates), or gate `ci_along` in `ctx.update` on `copilot != (_recorded(ctx, standard.CI_WORKFLOW, "ci_copilot_review") == "true")`.

#### Closing status

**Not quite closed — one small item left:** all Round 1 items (`P6-F01`–`P6-F07`, `Q1`–`Q5`) are **Accepted**; Phase 6 is ready to close once **`P6-F08`** is resolved.

### Developer responses (round 2)

| ID | Response | What changed |
|---|---|---|
| P6-F08 | **Fix** | When `--only github` brings `ci` along (`ci_along`, P5-F01), `make_plan` now plans `ci` with `update` turned off (`dataclasses.replace(ctx, update=False)`), as `init` does. An untouched `swerepo-ci.yml` is rewritten only when the Copilot wait itself changes. `ci`'s own updates (a new `requires-python`, SWERepo's pin, a newer template, the `pyproject.toml` block) wait for an update that includes `ci`. Regression test: `TestReviewP6::test_p6_f08_update_only_github_leaves_cis_own_updates`. It fails when the fix is reverted. ADR-20261124-7afa point 6 records it. |

**Results** (2026-11-24): pytest **693 passed** (also with `GITHUB_ACTIONS=true TERM=dumb`); ruff clean; locked rules 17 passed; proposed rules 3 passed; on this repository, `check` 0 missing / 0 changed / 0 outdated, `update --dry-run` "Nothing to do.", `privacy` nothing found, zizmor no findings.

All round 1 items were accepted in round 2, and P6-F08 is fixed. Ready to close.

### Round 3

**Reviewer:** Gemini · **Date:** 2026-11-24

#### Verification run

All commands under "How to run" (plus `privacy`, `zizmor`, and Round 3 `P6-F08` / `P5-F01` / `_settle` probes) were executed:

- `uv sync` → clean (`Audited 47 packages`).
- `uv run pytest` → **694 passed** (`133.54s`).
- `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **694 passed** (`130.64s`).
- `uv run ruff check . .seamspec/tests/` and `uv run ruff format --check . .seamspec/tests/` → clean (`164 files already formatted`; `.seamspec/proposed/` is now empty after locking).
- `uv run seamspec verify --all` → **20/20 locked rules passed** (`inv_60788941`, `inv_d60ffffd`, and `inv_9265607a` locked as critical).
- `uv run swerepo update --dry-run` → `"Nothing to do."` (exit `0`).
- `uv run swerepo status` → `12 current` (exit `0`, offline/instant).
- `uv run swerepo diff` → `"Nothing to show: update changes no file you edited."` (exit `0`, offline/instant).
- `uv run swerepo check` → `0 missing, 0 changed by you, 0 outdated, 0 can't tell.` (exit `0`).
- `uv run swerepo privacy` → `"swerepo privacy: nothing found"` (exit `0`).
- `uvx zizmor==1.32.0 --offline .github/workflows` → `No findings to report`.

#### Dispositions on Round 2 and post-Round-2 items

| Item | Disposition | Verification notes |
|---|---|---|
| **P6-F08** | **Accept** | `ci_ctx = dataclasses.replace(ctx, update=False) if ci_along else ctx` (`swerepo/init.py:1369`) cleanly isolates `update --only github`: verified by `TestReviewP6::test_p6_f08_update_only_github_leaves_cis_own_updates` and live probes that (1) `ci`'s own updates (`requires-python`, SWERepo's pin, `pyproject.toml`) stay untouched when running `update --only github`, and (2) an untouched `swerepo-ci.yml` still rewrites when the committed `ruleset.json` toggles `copilot_code_review` (`P5-F01`), without pulling in `ci`'s own updates. |
| **`merge._settle` cross-line commit check (`swerepo/merge.py:156-157`)** | **Accept** | Running `_one_commit_per_version` across all pins in `o` after line-by-line settling ensures that two lines pinning one version to two commits (whether both in `ours`, or produced across lines when `ours` and `theirs` bump separate lines to the same version on different commits) always report a conflict even when `theirs` adds no pin line (`tests/test_merge.py::test_two_commits_for_one_version_across_lines_of_ours_conflict`), while keeping lowered user pins (`M6-F03`) intact. |
| **Locked rules & ADRs (`inv_60788941`, `inv_d60ffffd`, `inv_9265607a`, `ADR-20261123-f571`, `ADR-20261124-7afa`)** | **Accept** | Verified `.seamspec/tests/test_inv_*.py` against `.seamspec/invariants/inv_*.json`: all three test suites prove every clause of their locked assertions (including person-written text after `<!-- swerepo:end -->`, `swerepo/blocks.py` in scope, positive checks for the new `seamspec==` pin, and two-commit conflicts on aligned, cross-line, and added pin lines). `ADR-20261123-f571` and `ADR-20261124-7afa` accurately record scopes, decisions, and enforced invariants. |

#### Safety properties check

Confirmed unchanged across all Round 3 edits: `update` never changes a file a person edited without `--merge` or a terminal `y`, never writes conflict markers, never merges against an unverified earlier render, and never moves an action pin backwards.

#### New findings

None.

#### Closing status

**Phase 6 is approved and ready to close** — all findings (`P6-F01`–`P6-F08`, `Q1`–`Q5`, and the post-Round-2 `_settle` and SeamSpec lock updates) are **Accepted**.

### Closing

Round 3 found nothing new and accepted P6-F08 and the `_settle` change. All eight findings (P6-F01–P6-F08) and the five questions are accepted, each fix with a regression test. The review is closed.

- **Since round 2, before the owner's approval:** SeamSpec's reviewer explained the three proposed rules, and at the owner's request they were tightened twice. They kept their ids.
  - **`inv_60788941`:**
    - the paths without a yes are covered: no `--yes` and no terminal, a no at "Apply?", and `--yes` alone;
    - every case requires exit 0 (exit 2 where nothing is applied);
    - an unedited whole file (`address-review.md` at `@1`) that `--yes` does rewrite, and a whole-file edit merged with `--yes --merge`;
    - a line of the person's after `<!-- swerepo:end -->`, with the text around the block unchanged;
    - no `<<<<<<<`, `=======` or `>>>>>>>` line anywhere;
    - `swerepo/blocks.py` added to its scope.
  - **`inv_d60ffffd`:**
    - the new render moves the same pin (to v98, between the earlier render's and Dependabot's v99) and adds a pin line, checked through `merge3`;
    - Dependabot's exact commit and the pin count are asserted, and the current SeamSpec pin must come in;
    - one version on two commits is a conflict on one line, across two lines of the person's file, and on a line the new render adds.
    - The cross-line case needed a code change: `_settle` now checks every pin in the person's file after settling (unit test in `tests/test_merge.py`).
  - **`inv_9265607a`:**
    - AGENTS.md must get exactly the new render;
    - deletions count as changes;
    - the text around the block stays, a line of the person's after it included;
    - `swerepo/blocks.py` added to its scope.

  Each rule was mutation-checked: it fails when the code it guards is broken.
- **The decision:** ADR-20261123-5e14 was out of date (it described the merge loosely and named no rule). It was re-proposed as ADR-20261124-b9d7, matching ADR-20261123-f571 as built. ADR-20261123-f571 now names its rules.
- **The owner's approvals (2026-11-24):**
  - `inv_60788941`, `inv_d60ffffd` and `inv_9265607a` are locked and critical. Now 20 rules are locked, and all pass. `docs/EARNED_SPEC.md` was regenerated, and `seamspec spec --check` is clean.
  - ADR-20261124-b9d7 accepted; ADR-20261123-5e14 rejected.
- **Final run:** pytest 694 passed; 20 locked rules passed; ruff, privacy and `check` clean; `update --dry-run` on this repository: "Nothing to do."
- **Deferred:**
  - a template that lowers a pin between versions (Q1), to the rule locking released templates (Phase 8);
  - the standard's changelog (spec §16), to the first standard 2 change.
- **Next:** the pull request for Phase 6.
