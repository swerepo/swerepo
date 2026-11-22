# Code Review · Phase 2: swerepo check

**Status:** closed · **Rounds:** 3 · **Developer:** Claude · **Reviewer:** Gemini · **Owner decides:** ties, merges, SeamSpec approvals
**Process:** ADR-20261119-9f87. Finding IDs `P2-F<nn>`; severities `blocker | should-fix | suggestion | question`; responses Fix / Push back / Defer, then Accept / Maintain.

---

## Developer summary

### Scope

The first real command, built on Phase 1's modules:

- **`swerepo check`** (`swerepo/check.py`, `swerepo/cli.py`): a read-only report per component (`✓ ✗ ~ ↑ ? –`), as plain text or `--json`, with `--only`, `--path` and `--ci` (GitHub Actions annotations). Exit 0, 1 (something chosen is missing) or 2 (wrong usage).
- **Standard 1 as data** (`swerepo/standard.py`): components, file names, the recommended order, and the checks later phases add (shown as `?` naming the phase).
- **Pull-request rules** (`swerepo/prrules.py`): `--base REF`, `--author LOGIN`, `--skip progress`. A progress entry or `Progress: none`; an ADR for a new runtime dependency or a workflow change; bot and lockfile-only skips; warn-only mode.
- **`.swerepo.toml` accessors** for `[agents]`, `[adopted]` and `[pr]`, validated on load (`swerepo/state.py`).

Branch `phase-2/check`, uncommitted. Spec updated to v0.8.

### What to review

| Area | Files |
|---|---|
| Report and component checks | `swerepo/check.py`, `tests/test_check.py` |
| Standard 1's items | `swerepo/standard.py` |
| Pull-request rules | `swerepo/prrules.py`, `tests/test_prrules.py` |
| Command line | `swerepo/cli.py` (`check` command) |
| State accessors | `swerepo/state.py` (`hosts`, `adopted`, `pr_enforce`, `exempt_authors`, `_validate_settings`), `tests/test_state.py` (`TestSettings`) |
| Test helpers | `tests/repo_helpers.py` (fixture repositories with real git histories) |
| ADRs | `docs/adr/ADR-20261120-fc5a-*`, `-5e21-*`; `docs/adr/README.md` |
| Spec | `SWEREPO-SPEC.md` §7 (`--author`), §9 (`[adopted] progress_dir`), §15 (what this version checks), Appendix A "0.7 → 0.8" |
| Proposed rule | `.seamspec/proposed/inv_294c48c9/` |
| Docs | `docs/PROGRESS.md`, `docs/progress/20261120-phase-2-check.md`, `CHANGELOG.md`, `README.md` |

### ADRs written

| ADR | Decision |
|---|---|
| ADR-20261120-fc5a | Findings per component (item key, status, message, path, blocking); chosen components from `.swerepo.toml` or the default set; checks a later phase adds are `?` with the phase, never left out; exit 0/1/2, only `✗` fails; plain text and JSON; no absolute paths or email addresses in output; read-only includes git's index (item 10) |
| ADR-20261120-5e21 | The PR diff is the working tree (plus untracked files) against the merge base; new dependencies by PEP 503 name; ADR = added/modified Markdown directly in the ADR folder; workflow changes except SWERepo's own recorded writes; `--author` for bot exemption; lockfile-only skip; `[pr] enforce = false` warns only |

### How to run

```bash
uv sync
uv run pytest
GITHUB_ACTIONS=true TERM=dumb uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run seamspec verify --all
uv run seamspec verify --proposed inv_294c48c9
uv run swerepo check
uv run swerepo check --json
uv run swerepo check --base main --author me --only docs
uv run swerepo check --only nope
```

### Results (run by the developer on 2026-11-20, macOS, Python 3.14, uv 0.9.28, git 2.50)

- pytest: **238 passed** (77 new), also with `GITHUB_ACTIONS=true TERM=dumb`.
- ruff check and format: clean. Locked rules: 6 passed. Proposed rule `inv_294c48c9`: verified.
- **`swerepo check` on this repository** (exit 1): `docs` complete (16 ADRs, index matches); `seamspec` complete; the `✗` lines are what Phase 3–5's `init` will add (SWERepo block in `AGENTS.md`, `GEMINI.md`, `docs/agents/` runbooks, `swerepo-ci.yml`, `SECURITY.md`, privacy workflow, `.gitignore` block, merge settings, Dependabot, PR and issue templates); 5 `?` lines naming Phases 4, 5 and 7. Summary: `19 ok, 11 missing, 0 changed, 0 outdated, 5 unknown, 2 not-chosen`; next step `swerepo init --only agents`.
- **`--base main` on this branch:** `pr ✓ progress entry added (docs/progress/20261120-phase-2-check.md)`; before that entry was written it reported the missing entry.
- **`--only nope`:** `unknown component nope (known: …)`, exit 2.

### Design notes worth checking

1. **A real bug found by the earned rule's test, before proposing it.** `git diff --name-status <merge-base>` (working tree against a commit) refreshes the index it reads and writes `.git/index` back when file times are out of date, so `check --base` wrote to the repository. `git --no-optional-locks` did not stop it (probed: it doesn't cover `git diff`; logged as SeamSpec dead end `de_a22b43fe`). Fix: that one diff runs with `GIT_INDEX_FILE` pointing at a temporary copy of the index (`prrules._worktree_diff`). Every other git call `check` makes was probed and writes nothing. Plain `git diff-index` (never writes) was rejected because, with an out-of-date index, it reports touched-but-unchanged files as modified; `test_a_touched_but_unchanged_workflow_is_no_change` guards that.
2. **`?` instead of silence.** A component never shows only `✓` while its hardest check didn't run: the privacy scan, Python matrix, live GitHub settings and SeamSpec health appear as `? … checked from Phase N` (`standard.LATER`).
3. **Editor-specific checks follow evidence.** The editors in use come from `[agents] hosts` when it is set, otherwise from detection (Phase 1: `.claude/`, `.agents/` and other editor folders). `CLAUDE.md` is checked when Claude Code is in use; `GEMINI.md` when Antigravity is. That is why this repository shows `GEMINI.md ✗`: SeamSpec's Antigravity files (`.agents/`) were committed in Phase 1 (owner decision pending, below).
4. **Untracked files count as added** in the PR diff, so `check --base main` before committing sees a new progress entry or ADR.
5. **No personal data in output.** The header names the folder only; the commit-email check reports how many commits use a non-noreply address, never the address. Tests check both.
6. **`CODEOWNERS` keeps the SWERepo block last** (a later rule would override governance): when it isn't last the finding is `~ changed`, not `✗`.
7. **Text output is plain `typer.echo`**, options use `Annotated` (ruff B008), and tests compare unstyled text (PR #1's lesson about Rich on Actions).
8. **Fixture repositories are real git repositories** built per test (`tests/repo_helpers.py`: hooks off, signing off, `-b main`), not mocks of git output.

### Known gaps and deliberate omissions

- **Checks later phases add** are `?`: Python matrix and privacy scan (Phase 4), secret scanning and live GitHub settings (Phase 5), SeamSpec health (Phase 7), release environment (Phase 8).
- **`--ci` never calls GitHub** — nothing in this version does; the switch matters from Phase 5.
- **`[pr] skip_progress_label`** is validated but used by the workflow (Phase 4 generates it), not by `check`.
- **Renames** are a delete plus an add (ADR-20261120-5e21 alternatives).
- **Monorepos:** `check` runs on the folder given; detection's monorepo warning (Phase 1) is not yet shown in the report.

### Questions for the reviewer

1. **Temporary index copy** (design note 1): sound, or do you see a case where the copy gives a different answer from the real index (split index, `index.lock` present, sparse checkout, worktrees where `--git-path index` is elsewhere)?
2. **Bot exemption by `--author`** rather than the git log: does anything in GitHub's `pull_request` event make `user.login` unreliable for Dependabot or forks?
3. **`~` for a misplaced CODEOWNERS block** (not `✗`): too lenient, given the block exists to protect governance files?
4. **Exit code 1 on any chosen `✗`**, including `agents` and `github` items on a repository that hasn't run `init` yet: right default for `check --ci`, or should a missing component (never initialised) be distinguished from a broken one?
5. **The proposed rule:** the right behaviour to lock, and anything else worth locking now (for example "only `✗` changes the exit code")?

### SeamSpec proposals waiting for the owner

| ID | Rule | Critical | Verified |
|---|---|---|---|
| inv_294c48c9 | Check never writes to the folder it checks, not even git's index (with `--base`, every default component, a recorded file, the CLI, and outside git; strengthened after P2-F08) | yes | passed · **locked 2026-11-21** |
| inv_5e3b5ef3 | Check output never shows absolute paths or personal email addresses (added after Q5 / P2-F03) | yes | passed · **locked 2026-11-21** |

The owner approves with `uv run seamspec review` after this review round.

### Owner decision outside this review

SeamSpec's Antigravity setup (`.agents/` and a second SeamSpec block in `AGENTS.md`) was added by a plain `seamspec init` run and committed in Phase 1. Keep it (Gemini in Antigravity uses it) or remove it and record `[agents] hosts`. **Decided 2026-11-21: kept** (ADR-20261121-8259).

---

## Round 1

### Reviewer: strengths

**Verification run (macOS, Python 3.14, uv 0.9.28):** Ran all 11 commands in "How to run", plus explicit Ruff checks on `.seamspec/proposed/`:
- `uv sync` → clean (50 packages resolved, 47 audited).
- `uv run pytest` → **238 passed** in 21.96s (0 failures).
- `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **238 passed** in 21.48s (0 failures).
- `uv run ruff check .` and `uv run ruff format --check .` → clean (64 files); `.venv/bin/ruff check . .seamspec/proposed/` and `.venv/bin/ruff format --check . .seamspec/proposed/` → clean (65 files, confirming `inv_294c48c9`'s test is Ruff-clean).
- `uv run seamspec verify --all` → **6 locked invariants passed**; `uv run seamspec verify --proposed inv_294c48c9` → **passed**.
- `uv run swerepo check` (exit 1) and `uv run swerepo check --json` (exit 1) → matched the developer's counts (`19 ok, 11 missing, 0 changed, 0 outdated, 5 unknown, 2 not-chosen`; `Next: swerepo init --only agents`). Only cosmetic difference: `folder` prints `goldenrepo` here because this local checkout folder hasn't been renamed on disk, confirming `root.name` works without leaking parent paths. (Noted `"path": null` on two missing `github` items in JSON; see `P2-F08`.)
- `uv run swerepo check --base main --author me --only docs` → exit 0 (`docs` 8 `✓`, `pr ✓ progress entry added (docs/progress/20261120-phase-2-check.md)`).
- `uv run swerepo check --only nope` → exit 2 (`swerepo check: unknown component nope (known: …)` on stderr).

**What is well done and should be kept:**
- **`swerepo/prrules.py:33-46`, `.seamspec/proposed/inv_294c48c9/`, and `.seamspec/dead_ends/de_a22b43fe.json`:** Catching `git diff`'s silent `.git/index` write via the earned rule test *before* review, recording `git --no-optional-locks` as dead end `de_a22b43fe`, isolating the refresh with `GIT_INDEX_FILE`, and guarding touched-but-unchanged workflows (`tests/test_prrules.py:111-116`) is exemplary engineering.
- **`swerepo/standard.py:36-45` and `swerepo/check.py:568-569` (`ADR-20261120-fc5a` point 4):** Surfacing unimplemented checks from `standard.LATER` as `? … checked from Phase N` prevents partial components from overclaiming full compliance while giving Phase 3+ a single source of truth.
- **`swerepo/check.py:35-103` and `swerepo/cli.py:57-60`:** Computing `Finding` objects once and rendering both plain `typer.echo` lines (avoiding Rich wrapping/ANSI drift) and `--json` from the same `Report` keeps human and machine output in lockstep.
- **`swerepo/check.py:398-415` and `tests/test_check.py:161-172`:** Checking both `git config user.email` and recent commit emails as non-blocking warnings while reporting counts rather than addresses protects privacy without demanding history rewrites.
- **`tests/repo_helpers.py:7-37` and `tests/test_prrules.py`:** Real per-test git histories with `core.hooksPath=/dev/null` and `commit.gpgsign=false` keep the suite hermetic against local git configs and exercise real `git merge-base` / `git diff` semantics rather than mocks.

### Reviewer: findings

#### P2-F01 · blocker · `swerepo/prrules.py:137`
**Problem:** `pr_findings` exempts SWERepo-generated workflow changes only when `status == "M"` (`if status == "M" and record is not None and fingerprint(ctx.read(path) or "") == record.written:`). When `swerepo init --only ci,security` (spec §10's step 3 recommended PR), `swerepo init --only release`, or `swerepo update` *creates* `.github/workflows/swerepo-ci.yml`, `swerepo-privacy.yml`, or `release.yml`, the diff status against the base branch is `"A"`, not `"M"`.
**Why it matters (scenario):** Spec §6.5 (`line 208`) and §15 (`line 541`) exempt workflow files that match SWERepo's recorded render in `.swerepo.toml`. Currently, a branch running `swerepo init --only ci,security` adds `.github/workflows/swerepo-ci.yml` (`status == "A"`) and records its fingerprint in `.swerepo.toml` → `swerepo check --ci --base main` fails SWERepo's own initialisation PR with `✗ workflow change (.github/workflows/swerepo-ci.yml) needs an ADR` (reproduced).
**Suggested fix:** Allow `status in ("A", "M")` when `record is not None and fingerprint(ctx.read(path) or "") == record.written`, update `ADR-20261120-5e21` point 5 ("added or modified"), and add a newly added recorded workflow case to `TestWorkflows.test_swerepos_own_change_needs_no_adr`.

#### P2-F02 · blocker · `swerepo/cli.py:61`
**Problem:** When `--json` and `--ci` are passed together on GitHub Actions (`GITHUB_ACTIONS=true`) and any missing item exists, `cli.check` writes the JSON object to `stdout` (`line 58`) and then writes `::error` / `::warning` annotation lines to **`stdout`** (`lines 61-63`), producing invalid JSON. In addition, `Report.annotations()` (`swerepo/check.py:113`) does not escape `%`, `\r`, or `\n` in `f.message`, so multi-line error messages (such as `TOMLKitError` in `state.read`) truncate or inject lines into Actions workflow commands.
**Why it matters (scenario):** Spec §7 (`line 275`) requires `--json` to print one machine-readable JSON result for scripts. Running `GITHUB_ACTIONS=true swerepo check --ci --json` on a repository with missing items prints `{...}\n::error file=...\n` to `stdout`, causing `json.loads(stdout)` / `jq` to fail with `JSONDecodeError: Extra data` (reproduced).
**Suggested fix:** Emit `annotations()` to `stdout` only when `not as_json` (or send annotations to `err=True` when `as_json`, or skip annotations in `--json` mode), URL-escape `%` (`%25`), `\r` (`%0D`), and `\n` (`%0A`) in `Report.annotations()`, and add a CLI test for `--json --ci` under `GITHUB_ACTIONS=true`.

#### P2-F03 · blocker · `swerepo/check.py:547`
**Problem:** `ADR-20261120-fc5a` (title and point 7) and `SWEREPO-SPEC.md` §15 (`line 545`) guarantee no absolute paths or home-folder paths appear in `check` output. However, `run_check` resolves `root = root.resolve()` (`line 538`) before calling `State.load(root)`. When `.swerepo.toml` triggers an `OSError` (e.g. `PermissionError`), `State.load` (`swerepo/state.py:101`) formats `str(error)`—which includes `error.filename`, the full resolved path `/Users/me/.../.swerepo.toml`—and `check.py:547` places `str(error)` straight into `Finding.message` (text, JSON, and `::error` annotations). (`_on_disk_reason` at `swerepo/state.py:275` similarly includes `str(error)` on `OSError`.)
**Why it matters (scenario):** `.swerepo.toml` has unreadable permissions (`chmod 000`) inside a developer's home directory → `swerepo check` and `swerepo check --json` print `.swerepo.toml: can't read it: [Errno 13] Permission denied: '/Users/me/project/.swerepo.toml'`, leaking the absolute home path into CI logs and pasted reports (reproduced).
**Suggested fix:** Format `OSError` in `State.load` (and `_on_disk_reason`) using `error.strerror or type(error).__name__` rather than `str(error)` so `error.filename` is never embedded, and add a test verifying `str(repo)` never appears in text or JSON when `.swerepo.toml` is unreadable.

#### P2-F04 · should-fix · `swerepo/check.py:308`
**Problem:** Three places where `check` claims `✓` without verifying what the message promises (plus one unguarded config type crash):
1. **Unverified `[adopted] linters` (`swerepo/check.py:308-309`):** `elif kept or detected:` reports `✓ linting: black (kept)` whenever `.swerepo.toml` sets `[adopted] linters = ["black"]`, even when `black` is not configured anywhere in the repository (`detected == set()`, as in `tests/test_check.py:175-183`).
2. **Prefix-only `.seamspec` match and unguarded non-list `exclude` in `_seamspec_excluded` (`swerepo/check.py:334-335`, plus `swerepo/prrules.py:62`):**
   - `str(entry).strip("/").startswith(".seamspec")` reports `✓ ruff skips .seamspec` when `extend-exclude = [".seamspec/proposed"]` or `[".seamspec-old"]`—even though `ruff format .` will still reformat `.seamspec/tests/` and break every locked test!
   - If `pyproject.toml` has a malformed non-list `[tool.ruff] exclude = true`, `[*config.get("exclude", [])]` (`line 334`) crashes `check` with `TypeError: Value after * must be an iterable, not bool`; similarly in `swerepo/prrules.py:62`, `tomllib.loads(text).get("project", {}).get("dependencies", [])` crashes with `AttributeError` if `project = "oops"` is not a table (both crashes reproduced).
3. **Commented-out `seamspec verify` and comments on `ci-ok:` (`swerepo/check.py:434`, `:299`):** `"seamspec verify" in (ctx.read(w.path) or "")` reports `✓ CI runs the locked rules` even if `# seamspec verify` is only in a YAML comment; conversely `r"^  ci-ok:\s*$"` (`line 299`) misses `  ci-ok:  # aggregator` when an inline YAML comment is present.
**Why it matters (scenario):** (1) A project sets `extend-exclude = [".seamspec/proposed"]` → `swerepo check` prints `✓ ruff skips .seamspec (pyproject.toml)`, then `ruff format .` reformats `.seamspec/tests/` and breaks SeamSpec verification. (2) Removing `[tool.black]` while `.swerepo.toml` still lists `linters = ["black"]` still prints `✓ linting: black (kept)`.
**Suggested fix:** (1) Check `missing_kept = [name for name in kept if name not in detected]` and report `✗` (or `~`) when a kept linter has no configuration on disk. (2) Require normalised exclude entries (after stripping leading `./` and trailing `/`) to be in `{".seamspec", ".seamspec/*", ".seamspec/**"}`, and guard non-list `exclude`/`extend-exclude` and non-dict `project` in `prrules.py:62`. (3) Strip `# ...` comments per line before matching `seamspec verify` and `ci-ok:`.

#### P2-F05 · should-fix · `swerepo/prrules.py:45`
**Problem:** Three git / `--base` edge cases in `prrules.py` and subfolder `--path` handling:
1. **`git rm --cached` on an existing progress file counts as a newly added entry (`swerepo/prrules.py:52-55`):** `_changes` appends `("A", path)` for every untracked file from `git ls-files --others` without checking whether `path` already appeared as `"D"` in `_worktree_diff` (meaning `path` existed in `merge_base` and was removed from the index while staying on disk).
2. **Failed `git diff` or failed index copy misreports changes (`swerepo/prrules.py:43-45`, `:87-88`):** `ctx.git("diff", ...) or ""` turns a `None` git error into `""`, causing `pr_findings` (`line 88`) to report `✓ no changes against main` (`OK`, exit 0) when `git diff` failed. And if `shutil.copyfile` fails with `OSError` when a real index file exists (`line 43`), running `git diff` with a non-existent `GIT_INDEX_FILE` treats the index as empty and marks every tracked file in `merge_base` as `"D"`.
3. **Subfolder `--path` (`not detection.git.is_toplevel`, `swerepo/check.py:553` and `swerepo/prrules.py:53, 120-121`):** When `swerepo check` runs on a subfolder of a git repository (e.g. `swerepo check --path services/api --base main`), `repository.git` emits no warning that `services/api` isn't the repository root, and `prrules` mixes repo-toplevel paths (`git diff`, `git show {merge_base}:pyproject.toml`) with subfolder-relative paths (`git ls-files --others`, `ctx.read("pyproject.toml")`)—comparing `<root>/pyproject.toml` at `merge_base` against `services/api/pyproject.toml` on disk.
**Why it matters (scenario):** (1) On a feature branch, `git rm --cached docs/progress/20260101-old.md` + editing `app.py` with no new progress file → `swerepo check --base main` reports `✓ progress entry added (docs/progress/20260101-old.md)` (reproduced). (2) Running `swerepo check --path services/api --base main` in a monorepo where `services/api/pyproject.toml` already declared `fastapi` on `main` → falsely fails with `✗ new dependency fastapi needs an ADR` and misses untracked root `docs/progress/` entries (reproduced).
**Suggested fix:** (1) Reconcile paths that are both `"D"` in `diff` and in `untracked`: compare working-tree content with `ctx.git("show", f"{merge_base}:{path}")` and emit `"M"` if changed or omit if identical, never `"A"`. (2) Return `None` from `_worktree_diff` when copying an existing index fails or `ctx.git("diff", ...)` returns `None`, and emit an `UNKNOWN` (`?`) finding (or `UsageError`) instead of `✓ no changes`. (3) When `detection.git.is_work_tree and not detection.git.is_toplevel`, emit a `repository.git` `UNKNOWN` note naming the subfolder mismatch, and in `pr_findings` raise `UsageError` asking to run `--base` at the repository root.

#### P2-F06 · should-fix · `swerepo/check.py:181`
**Problem:** `[adopted] adr_dir` in `.swerepo.toml` (`SWEREPO-SPEC.md` §9 `line 362`, `swerepo/state.py:373`) accepts any repository-relative folder path, such as `"decisions"` or `"docs/rfcs"`. However, `_docs` (`swerepo/check.py:181-187`) checks `if adr_dir in detected:`, where `detected` comes from `d.adr_dirs`—which in `swerepo/detect.py:66` scans only six hardcoded folder names (`docs/adr`, `doc/adr`, `docs/decisions`, `doc/decisions`, `docs/architecture/decisions`, `adr`).
**Why it matters (scenario):** An established repository records `[adopted] adr_dir = "decisions"` in `.swerepo.toml` with `decisions/0001-use-pg.md` on disk → `swerepo check` reports `✗ ADR folder missing (decisions)` and exits 1 (reproduced).
**Suggested fix:** When `adopted_dir` is set and not in `detected`, check `(ctx.root / adopted_dir).is_dir()` and count `.md` files directly inside it (excluding `NOT_ADRS`), and add a test with `[adopted] adr_dir = "decisions"`.

#### P2-F07 · should-fix · `swerepo/check.py:571`
**Problem:** Two reporting / CLI selection bugs:
1. **Duplicate findings and double error counts once `.swerepo.toml` records files (`swerepo/check.py:567-572`):** `run_check` appends both `CHECKERS[component](ctx)` and `_record_findings(...)`. For any standard file or block recorded in `.swerepo.toml` (e.g. `docs/PROGRESS.md`, `AGENTS.md`, `.gitignore`, `.github/CODEOWNERS`), deleting the file emits **two** blocking `✗` findings (`docs.progress` `"docs/PROGRESS.md missing"` and `docs.file:docs/PROGRESS.md` `"docs/PROGRESS.md removed (SWERepo wrote it)"`), doubling `report.count(MISSING)` and emitting two `::error file=docs/PROGRESS.md` annotations; when present and current, both `✓ docs/PROGRESS.md` and `✓ docs/PROGRESS.md (current)` print in the same `docs` section (reproduced; `tests/test_check.py:226` used `docs/PROGRESS-copy.md`, which hid the collision).
2. **Empty `--only` list silently checks everything (`swerepo/cli.py:51`, `swerepo/check.py:562`):** `swerepo check --only ","` (or `--only " "`, or `run_check(root, only=[])`) produces `components = []`, which is falsy at `if only:` (`check.py:562, 564, 570`) and silently checks all default components instead of exiting 2 (reproduced).
**Why it matters (scenario):** As soon as Phase 3's `init` writes `.swerepo.toml` records for `docs` and `agents`, every `swerepo check` run will print duplicate lines for every generated file and double-count missing files; and `swerepo check --only ","` exits 0/1 instead of 2.
**Suggested fix:** (1) Skip or merge `_record_findings` entries whose `path` already has a `MISSING` finding from `CHECKERS` (and when a recorded file is `OK` `"current"`, either fold the record check into `_present`/`_block_finding` or omit redundant `OK` record lines for paths already reported `OK` by the component checker, keeping `CHANGED`, `OUTDATED`, `UNKNOWN`, and any unrecorded/extra paths visible). (2) Reject empty `--only` (`only is not None and not components`) with `UsageError` (exit 2) and test `only is not None` in `run_check`.

#### P2-F08 · suggestion · `.seamspec/proposed/inv_294c48c9/test_inv_294c48c9.py:25`
**Problem:** Before locking `inv_294c48c9`, its harness sets `components = ["docs", "ci"]` (`line 25`) with no `[files]`/`[blocks]` records, so `_agents`, `_security`, `_github` (including `_commit_email`'s `git config` and `git log` calls), `_seamspec`, and `_record_findings` never run during the read-only invariant test; `_snapshot` (`line 19`) checks `(st_mtime_ns, st_size)` without file bytes; and `inv_294c48c9.json`'s `scope.paths` omits `swerepo/cli.py`. Also three small report polish items:
- `MISSING` findings for `docs.readme` (`check.py:178`), `github.pr-template` (`check.py:363`), `github.issue-templates` (`check.py:367`), and `github.codeowners` (`check.py:376`) omit `path` (`"path": null` in `--json`, no `file=` in `annotations()`), unlike `docs.changelog`, `docs.contributing`, and their `OK` counterparts.
- When `detection.is_monorepo` is `True`, `_ci` emits no `?` note for monorepo project coverage (`SWEREPO-SPEC.md` §11 `line 441`).
- Adding `"Cargo.lock"`, `"go.sum"`, and `"Gemfile.lock"` to `prrules.LOCKFILES` (`prrules.py:28`) aligns lockfile-only skips with Phase 1's polyglot manifests.
**Why it matters (scenario):** In Phase 1, SeamSpec's reviewer sent `inv_bee7349a` back twice because code paths covered by the rule's wording weren't exercised by the harness; tightening `inv_294c48c9` now avoids a supersede later.
**Suggested fix:** Expand `test_inv_294c48c9.py` to enable all 6 default components (`docs, agents, ci, security, github, seamspec`) plus one `[files]` record and `.seamspec/config.toml`, include `p.read_bytes()` in `_snapshot`, and add `"swerepo/cli.py"` to `inv_294c48c9`'s `scope.paths` (plus pass `-c splitIndex.maxPercentChange=100` on `git diff` in `_worktree_diff`; see Q1). Add the missing `path` arguments, monorepo `?` line, and polyglot lockfiles if you agree.

### Reviewer: answers to questions

1. **Temporary index copy (`prrules._worktree_diff`, design note 1):** Tested all four git configurations empirically against git 2.50:
   - **Diff answers match the real index in all four** (`index.lock` present, linked `git worktree`, `sparse-checkout`, and `split-index`). Copying the index is actually *better* when `.git/index.lock` exists (pre-commit or IDE background status), because Git locks the temp copy instead of failing on `.git/index.lock`; in linked worktrees, `git rev-parse --git-path index` returns an absolute path into `<main>/.git/worktrees/<wt>/index`, which `ctx.root / found` handles cleanly; in sparse checkouts, `SKIP_WORKTREE` bits survive the copy.
   - **One read-only caveat found on split-index repositories (`git update-index --split-index` / `feature.manyFiles=true`):** refreshing the temp copy causes Git to write a new `.git/sharedindex.<sha>` file into `.git/` when enough entries change! Passing `-c splitIndex.maxPercentChange=100` on that `git diff` call stops Git from creating new `sharedindex.*` files in `.git/` (Git's C `do_read_index` still freshens the existing `.git/sharedindex.<sha>` mtime). Also fix the silent `OSError` / `or ""` fallback in `P2-F05` so a failed copy or failed `git diff` never fakes an empty index or `✓ no changes`.
2. **Bot exemption by `--author` rather than the git log:** **Sound, provided Phase 4's workflow passes `github.event.pull_request.user.login` (not `github.actor`).** On Dependabot PRs, `pull_request.user.login` stays `"dependabot[bot]"` even when a human clicks "Re-run jobs" or comments `@dependabot recreate` (whereas `github.actor` switches to the human). GitHub logins are globally unique across forks and the `[bot]` suffix is reserved by GitHub, so a fork author cannot spoof `dependabot[bot]`. In Phase 4's generated workflow, pass it through `env:` (`AUTHOR: ${{ github.event.pull_request.user.login }}` → `--author "$AUTHOR"`), never inline in `run:`, so `zizmor` passes cleanly.
3. **`~` for a misplaced CODEOWNERS block (not `✗`):** **Keep `~` (`CHANGED`).** It matches `SWEREPO-SPEC.md` §6.1 (`line 149`) verbatim and respects principle 2 (a deliberate owner override at the bottom of `CODEOWNERS` should be visible, not fail `check --ci`). One small enhancement from §6.1 `line 149` (*"naming any that do"*): you can safely include the **path patterns** (`line.split()[0]`, never the `@owner` handles/emails) of trailing rules—or even better in Phase 5, note specifically trailing patterns that overlap SWERepo's governance paths rather than unrelated rules like `/frontend/`.
4. **Exit code 1 on any chosen `✗`:** **Right default — no separate "uninitialised" exit state needed.** Once a repository adopts SWERepo incrementally (spec §10's step-by-step PRs), `.swerepo.toml` lists only the components adopted so far (`components = ["docs", "agents"]`), so `chosen_components()` marks uninitialised components `– not chosen` and `check --ci` exits 0 when the adopted components are healthy. Before `.swerepo.toml` exists, exiting 1 accurately reports that the repository does not yet meet standard 1.
5. **The proposed rule (`inv_294c48c9`) and anything else worth locking now:**
   - **`inv_294c48c9` is the right primary rule to lock** — strengthen its harness and scope per `P2-F08` before running `seamspec review` so every component checker is exercised.
   - **One second rule worth proposing in Phase 2 (critical):** *"`swerepo check` output (text, `--json`, and `--ci` annotations) never contains absolute repository paths or personal email addresses, including when `.swerepo.toml` is unreadable or git config/commits use a personal email."* That directly locks `ADR-20261120-fc5a` point 7 (and catches regressions like `P2-F03`).

### Developer responses

Every finding was reproduced or confirmed in the code before answering. All eight are fixed; two parts are fixed differently from the suggestion, with reasons. Each fix has a test; for F01, F03 and F07 I also reverted the fix and saw the new test fail.

#### P2-F01 · **Fix**
Confirmed: only `M` was exempt. Spec §6.5 already says "the file matches the render recorded", with no restriction to modified files, so this was the code falling short of the spec. Now `A` or `M` with a matching `written` fingerprint is exempt (`prrules.py`). ADR-20261120-5e21 point 5 says "added or modified". Test: `TestWorkflows.test_a_workflow_swerepo_added_needs_no_adr` (an added recorded workflow passes, and a person's edit to it is still flagged).

#### P2-F02 · **Fix** (both parts)
`--json` now prints one JSON value and nothing else: annotations are skipped in JSON mode (`cli.py`). I didn't send them to stderr, because a script that asked for JSON wants findings from the JSON. Annotation values are escaped as GitHub's runner expects: `%`, CR and LF in the message, plus `:` and `,` in the `file` property (`check._escape`). Tests: `test_json_with_ci_on_github_actions_is_only_json`, `test_annotation_values_are_escaped`. Spec §15 and ADR-fc5a point 5 updated.

#### P2-F03 · **Fix**
Confirmed: an `OSError`'s text includes `filename`. `state._reason` gives `strerror` (or the error type) for an `OSError`, in both `State.load` and `_on_disk_reason`. The message is now `.swerepo.toml: can't read it: Permission denied`. The test simulates the error with the absolute path in `filename` (monkeypatched `PermissionError`), because `chmod 000` doesn't stop root in CI containers. Following Q5, this is also locked as **proposed rule `inv_5e3b5ef3`** (critical). It covers text, `--json` and `--ci` output, a personal git email in config and commits, and the unreadable state file. Its test fails if the path or the email leaks.

#### P2-F04 · **Fix**, part 1 differently
1. **Kept linter without configuration → `?`, not `✗`.** Detection finds linters in `pyproject.toml`, their own files and pre-commit, but not in workflow `run:` lines. A project that runs `black --check .` only in CI, with Black's defaults, would get a false `✗`. Now: `? linting: black kept, but no configuration found (pyproject, own files, pre-commit)`. `test_kept_linters_and_editors_from_the_state_file` now gives Black a real `[tool.black]`, so it still checks the `✓` path. The `?` case is `test_a_kept_linter_without_configuration_is_unknown`.
2. **Fixed as suggested.** Exclude entries are normalised (`./` and trailing `/` stripped) and must be `.seamspec`, `.seamspec/*`, `.seamspec/**`, `**/.seamspec` or `**/.seamspec/**`. A non-list `exclude` is ignored instead of crashing, and a non-table `[project]` is `? [project] isn't a table`. Tests: `test_ruff_must_skip_all_of_seamspec` (6 cases, including `.seamspec/proposed`, `.seamspec-old` and `true`), `test_a_project_that_isnt_a_table_is_unknown`.
3. **Fixed.** YAML comments are removed before looking for `seamspec verify`. Cutting at `#` may also cut a `#` inside a string, which can only turn a `✓` into a `✗`, never the reverse. `ci-ok:` may carry a trailing comment. Test: `test_yaml_comments_dont_count`.

#### P2-F05 · **Fix** (all three)
1. A path that is both `D` in the diff and untracked (`git rm --cached`) is compared with the merge base's text: dropped if the same, `M` if different, never `A`. Test: `test_untracking_an_old_progress_entry_is_not_a_new_one`.
2. `_worktree_diff` returns `None` when the existing index can't be copied or `git diff` fails, and so does an `ls-files` failure. The finding is then `? git couldn't list the changes against main`, and no other PR rule runs on a made-up diff. Test: `test_when_git_cant_list_the_changes_it_says_so` (copy fails).
3. `--base` below the repository's top level is wrong usage (exit 2: "run it at the repository's top level"). A plain `check` of a subfolder adds `? a folder inside a git repository: files are looked for here, not at the repository's top`. Tests: `test_base_runs_at_the_repository_top`, `test_a_subfolder_of_a_repository_is_noted`. Per-project checks in monorepos stay with the monorepo work (spec §11).

#### P2-F06 · **Fix**
When `[adopted] adr_dir` names a folder detection doesn't look in, `check` counts the `.md` files directly inside it, other than `README.md`, `TEMPLATE.md` and `index.md`. That list moved to `standard.NOT_ADRS`, shared with the PR rules. Test: `test_an_adopted_adr_folder_anywhere` (`decisions/` with 2 decisions and a README → `✓ ADRs (adopted: decisions, 2 files)`).

#### P2-F07 · **Fix** (both)
1. A record finding is dropped when the component already reported the same path as `✓` or `✗`. `~`, `↑` and `?` for records always show, since only the record knows them. A deleted `docs/PROGRESS.md` is now one `✗` and one count. Tests: `test_a_deleted_recorded_file_is_one_finding`, plus `test_records`, which now asserts that the current record doesn't repeat the `docs` line (it expected the repeat before; that expectation was the bug).
2. `--only` with no components (`","`, `" "`, `only=[]`) is wrong usage (exit 2). `run_check` tests `only is not None` throughout.

#### P2-F08 · **Fix**, except the split-index flag (push back, with a test)
- **The rule's test is strengthened** (proposal `inv_294c48c9` replaced). It now runs all six default components, a file recorded in `.swerepo.toml`, `.seamspec/config.toml`, CODEOWNERS and AGENTS blocks, and the CLI with `--base --ci` and `--base --ci --json` on simulated Actions. The snapshot compares contents (`read_bytes`) too, and the test asserts that the record, commit-email, SeamSpec and PR parts actually ran. `swerepo/cli.py` is added to the scope. Mutation check: putting back the plain `git diff` makes it fail.
- **Missing paths** added: `README.md`, `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE`, `.github/CODEOWNERS`.
- **Monorepo:** `? every project covered by a required check: checked from Phase 4` (`test_monorepo_coverage_is_a_later_check`).
- **Lockfiles:** `Cargo.lock`, `go.sum`, `Gemfile.lock` added (`test_other_ecosystems_lockfiles`).
- **Push back on `-c splitIndex.maxPercentChange=100`:** I tested it in a split-index repository with 30 of 40 entries stat-dirty (git 2.50). With or without the flag, and with `core.splitIndex=false`, git changes only the existing `sharedindex.<sha>` file's modification time, and plain `git ls-files --others` does the same. I couldn't reproduce a new `sharedindex` file. So the flag doesn't help, and this timestamp refresh is git's own behaviour on reading a split index, which detection's locked rule (`inv_bee7349a`) is subject to as well. Recorded as a known limit in ADR-20261120-fc5a item 10 rather than adding a flag with no effect.

#### Answers to questions: taken
- **Q1:** thank you for the four-configuration test. `index.lock` and linked worktrees confirm the copy is the right design. Split index: see F08.
- **Q2:** ADR-5e21 now says to pass `github.event.pull_request.user.login` through `env:`, not `github.actor`. Phase 4's workflow template will do that (zizmor-clean).
- **Q3:** kept `~`, and the message now names the trailing rules' **path patterns** (never the owners): `rules after the SWERepo block can override governance owners (/docs/)`. Test: `test_codeowners_names_the_overriding_patterns_not_the_owners`. Narrowing it to overlapping patterns is deferred to Phase 5, with live GitHub checks.
- **Q4:** agreed, no separate exit state.
- **Q5:** done: `inv_5e3b5ef3` (see F03).

### Checks after the fixes (developer, 2026-11-20)

- pytest: **260 passed** (22 new this round), also with `GITHUB_ACTIONS=true TERM=dumb`.
- ruff check and format: clean, including `.seamspec/proposed/`. Locked rules: 6 passed. Proposed `inv_294c48c9` and `inv_5e3b5ef3`: verified.
- Dogfood: `swerepo check` gives the same counts as before (`11 missing … Next: swerepo init --only agents`). `GITHUB_ACTIONS=true swerepo check --json --ci` parses as JSON. `--base main --only docs` passes.
- Changed: `swerepo/check.py`, `prrules.py`, `cli.py`, `state.py`, `standard.py`; tests in `test_check.py` and `test_prrules.py`; ADR-20261120-fc5a and -5e21; spec §15 and Appendix A "0.7 → 0.8" item 3; progress entry. Dead end `de_a22b43fe` (Round 0) stands.

---

## Round 2

### Reviewer: response to developer responses

**Verification run (macOS, Python 3.14, uv 0.9.28):** Re-ran all 11 commands in "How to run" plus the 3 Round 2 commands:
- `uv sync` → clean (50 packages resolved, 47 audited).
- `uv run pytest` and `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **260 passed** (22 new tests, 0 failures).
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (66 files).
- `uv run seamspec verify --all` → **6 locked invariants passed**; `uv run seamspec verify --proposed inv_294c48c9` and `uv run seamspec verify --proposed inv_5e3b5ef3` → **both passed**.
- `uv run swerepo check` (exit 1) and `uv run swerepo check --json` (exit 1) → matched (`19 ok, 11 missing, 0 changed, 0 outdated, 5 unknown, 2 not-chosen`, and `github.pr-template` / `github.issue-templates` now carry their `path` fields in JSON).
- `GITHUB_ACTIONS=true uv run swerepo check --json --ci` → exit 1, valid single JSON object on `stdout` with no trailing `::error` lines.
- `uv run swerepo check --base main --author me --only docs` → exit 0; `uv run swerepo check --only nope` → exit 2.

**Responses to Round 1 resolutions:**
- **P2-F01 · Accept.** Allowing `status in ("A", "M")` when `fingerprint(...) == record.written` (`swerepo/prrules.py:159`) matches spec §6.5 and is covered by `test_a_workflow_swerepo_added_needs_no_adr` (`tests/test_prrules.py:126-136`).
- **P2-F02 · Accept.** Skipping annotations when `as_json` is `True` (`swerepo/cli.py:61`) is cleaner than writing them to `stderr` for scripts expecting JSON only, and `_escape` (`swerepo/check.py:118-121`) escapes `%` first, then CR/LF, plus `:` and `,` on properties, matching `@actions/core`.
- **P2-F03 · Accept.** `state._reason` (`swerepo/state.py:279-284`) strips `error.filename` from `OSError` in both `State.load` and `_on_disk_reason`, tested via monkeypatched `PermissionError` (`tests/test_check.py:316-328`) and locked by the new critical rule `inv_5e3b5ef3`.
- **P2-F04 · Accept (including `?` instead of `✗` for part 1).** The developer's reasoning on part 1 holds: `detect._linters` inspects config files and pre-commit rather than workflow `run:` steps, so a repository running default-config `black --check .` in CI has no config file on disk; reporting `?` (`UNKNOWN`) stops `✓` from claiming more than was checked without falsely failing valid CI-only setups, consistent with `ADR-20261120-fc5a` point 4. Parts 2 and 3 (`_SEAMSPEC_EXCLUDES`—verified with Ruff that `"/.seamspec"` indeed does *not* exclude `.seamspec`, so rejecting leading `/` in `_normal_exclude` is right—non-list/non-table guards, and `_without_comments`) are all sound.
- **P2-F05 · Accept (with one binary-file edge case in the new `git show` check filed as `P2-F09`).** Reconciling `D` + untracked paths against `merge_base` (`swerepo/prrules.py:63-68`), returning `None` → `?` when git or the index copy fails (`lines 46-50, 107-108`), refusing `--base` below the repository top level (`lines 96-97`), and noting subfolders in `repository.git` (`swerepo/check.py:614-616`) resolve all three Round 1 scenarios cleanly.
- **P2-F06 · Accept.** Counting `.md` files directly inside any custom `[adopted] adr_dir` (`swerepo/check.py:193-195`) using shared `standard.NOT_ADRS` works cleanly (`tests/test_check.py:234-240`).
- **P2-F07 · Accept (with `--only ""` empty-string CLI case noted as `P2-F11`).** `_without_repeats` (`swerepo/check.py:554-558`) eliminates duplicate `✓`/`✗` lines and double counts while keeping `~`, `↑`, and `?` record findings visible (`tests/test_check.py:296-315`).
- **P2-F08 · Accept (including the pushback on `-c splitIndex.maxPercentChange=100`).** Re-checking our own Round 1 split-index probe confirms the developer's git 2.50 result: `set(after) - set(before)` was empty—no new `sharedindex.*` file is created, only the existing `sharedindex.<sha>`'s mtime is refreshed on read (which `git ls-files` does too), and neither flag prevents it. Recording that git behaviour as a known limit in `ADR-20261120-fc5a` item 10 rather than passing a no-op flag is the right call. `inv_294c48c9`'s expanded harness, byte-level snapshot, CLI coverage, and scope (`swerepo/cli.py` added), plus the `path` fields, monorepo `?` line, and polyglot lockfiles, are all well done.
- **Q3 follow-up (`_codeowners` pattern formatting):** Naming trailing patterns is clean; see `P2-F10` for one malformed-line privacy guard needed on `line.split()[0]`.

### Reviewer: new findings

#### P2-F09 · should-fix · `swerepo/prrules.py:65`
**Problem:** Round 2's `git rm --cached` check (`elif ctx.git("show", f"{merge_base}:{path}") == ctx.read(path):`) calls `Context.git` (`swerepo/check.py:155-158`), which runs `subprocess.run(..., capture_output=True, text=True)` without `encoding="utf-8", errors="replace"` and decodes arbitrary file contents as UTF-8 text. Untracking an accidentally committed binary file (`logo.png`, `.pdf`, `.whl`) via `git rm --cached`—one of the main real-world uses of `git rm --cached`—causes `ctx.git("show", ...)` to raise an unhandled `UnicodeDecodeError` and crash `swerepo check --base`. In addition, `text=True` without `encoding="utf-8", errors="replace"` in `Context.git` uses the locale encoding (`cp1252` on Windows) when reading UTF-8 commit messages or paths from git.
**Why it matters (scenario):** A branch runs `git rm --cached logo.png` (where `logo.png` starts with `\x89PNG...` on `main`) and runs `swerepo check --base main` → crashes with `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x89 in position 0` (reproduced).
**Suggested fix:** Compare raw bytes for `git rm --cached` paths (e.g. a `Context.git_bytes` helper returning `bytes | None` compared against `(ctx.root / path).read_bytes()`, so two distinct binary files also never collide on `\ufffd` replacement characters), pass `encoding="utf-8", errors="replace"` on `Context.git` (`swerepo/check.py:157`), and add a binary `git rm --cached` test in `tests/test_prrules.py`.

#### P2-F10 · should-fix · `swerepo/check.py:422`
**Problem:** Round 2 updated `_codeowners` (`line 422`) to extract `patterns = ", ".join(line.split()[0] for line in after)` ("path patterns only, never the owners"). However, if a trailing line below `# swerepo:end` in `.github/CODEOWNERS` is malformed and starts directly with an owner email address or `@handle` (omitting the leading path pattern), `line.split()[0]` *is* that email address or handle, printing personal data into `check` text, `--json`, and CI annotations (`ADR-20261120-fc5a` point 7).
**Why it matters (scenario):** `.github/CODEOWNERS` has a malformed line `<person>@<company-domain>` after `# swerepo:end` → `swerepo check` prints `.github/CODEOWNERS: rules after the SWERepo block can override governance owners (<person>@<company-domain>)`, leaking the email address into output (reproduced).
**Suggested fix:** Keep only non-owner first tokens (`patterns = [tok for line in after if "@" not in (tok := line.split()[0])]`), omitting ` ({...})` when `patterns` is empty, and add a malformed trailing `PERSONAL` line in `.github/CODEOWNERS` (plus `str(repo.resolve()) not in out` for symlinked `TMPDIR`s like `/tmp` → `/private/tmp`) to `tests/test_check.py` and `.seamspec/proposed/inv_5e3b5ef3/test_inv_5e3b5ef3.py`.

#### P2-F11 · suggestion · `swerepo/cli.py:51`
**Problem:** `run_check` now rejects `only=[]` (`swerepo/check.py:586`), so `--only ","` and `--only " "` exit 2, **except** `--only ""` (an empty string, e.g. `swerepo check --only "$COMPONENTS"` when `$COMPONENTS` is empty): `swerepo/cli.py:51` still writes `if only else None`, which treats `""` as falsy and passes `only=None`, silently checking all default components instead of exiting 2 (reproduced).
**Why it matters (scenario):** Running `swerepo check --only ""` exits 0/1 after checking all default components instead of exiting 2 with `--only needs at least one component`.
**Suggested fix:** Change `if only else None` to `if only is not None else None` on `swerepo/cli.py:51` and add `--only ""` to `test_wrong_usage_exits_2`.

### Readiness summary

- **Proposed SeamSpec rules:**
  - **`inv_294c48c9` (read-only check, including git's index):** **Ready for owner approval** (`uv run seamspec review`).
  - **`inv_5e3b5ef3` (no absolute paths or personal emails in output):** Sound design and scope; extend `test_inv_5e3b5ef3.py` with the malformed-`CODEOWNERS` `PERSONAL` case and `str(repo.resolve())` check alongside fixing `P2-F10` before approving.
- **Ready to merge?** **Not quite yet** — three small edge cases in Round 2's new code (`P2-F09`, `P2-F10`, `P2-F11`, ~12 lines total) need a quick pass. Once addressed and verified in Round 3, Phase 2 is ready to close and merge.

### Developer responses

All three reproduced and fixed, each with a test that fails without the fix.

#### P2-F09 · **Fix**
`Context.git` no longer decodes with the locale's encoding. It reads bytes and decodes UTF-8 with replacement (and normalises CRLF as `text=True` did). The new `Context.git_bytes` and `Context.read_bytes` serve the `git rm --cached` comparison, which now compares raw bytes, so two different binary files can't compare equal through replacement characters. Test: `test_untracking_a_binary_file_compares_bytes[same|changed]`. A non-UTF-8 binary file is untracked from a commit on `main`. Unchanged, it is no change; changed, it counts as `M`. The file sits under `.github/workflows/` so the outcome shows as a `pr.workflows` finding. Comparing as text makes the "changed" case fail, which I checked.

#### P2-F10 · **Fix**
The CODEOWNERS finding names only first tokens without `@`, and drops the parentheses when none are left: `…can override governance owners`. Tests: `test_codeowners_names_the_overriding_patterns_not_the_owners` (a pattern, an email-only line and an `@team`-only line → only `(/docs/)`; an email-only line alone → no parentheses, no address). **`inv_5e3b5ef3` is extended as you asked** (proposal replaced and verified). It adds the email-only CODEOWNERS line, asserts that the CODEOWNERS finding came up in every output, and checks the folder's path and its parent's, both as given and resolved (`/tmp` → `/private/tmp`). Mutation check: putting back the old pattern extraction makes the rule fail. ADR-20261120-fc5a point 7 records both.

#### P2-F11 · **Fix**
`cli.py` tests `only is not None`, so `--only ""` reaches `run_check` and exits 2 (`--only needs at least one component`). Added to `test_wrong_usage_exits_2`.

### Checks after the fixes (developer, 2026-11-20)

- pytest: **262 passed**, also with `GITHUB_ACTIONS=true TERM=dumb`. ruff check and format: clean, including `.seamspec/proposed/`.
- Locked rules: 6 passed. Proposed `inv_294c48c9` and `inv_5e3b5ef3`: both verified.
- Dogfood unchanged: `11 missing, 0 changed by you, 0 outdated, 5 can't tell. Next: swerepo init --only agents`. `swerepo check --only ""` → exit 2.

---

## Round 3

### Reviewer: response to developer responses

**Verification run (macOS, Python 3.14, uv 0.9.28):**
- `uv run pytest` and `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **262 passed** (0 failures).
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (66 files).
- `uv run seamspec verify --all` → **6 locked invariants passed**; `uv run seamspec verify --proposed inv_294c48c9` and `uv run seamspec verify --proposed inv_5e3b5ef3` → **both passed**.
- `uv run swerepo check --only ""` → exit 2 (`swerepo check: --only needs at least one component …` on stderr).
- Re-ran all three Round 2 reproduction probes (binary PNG `git rm --cached`, `--only ""`, and bare email after `# swerepo:end` in `.github/CODEOWNERS`) → all three passed cleanly.

**Responses to Round 2 fixes:**
- **P2-F09 · Accept.** Splitting `Context.git_bytes` (`swerepo/check.py:157-166`) from `Context.git` (`lines 150-155`, decoding UTF-8 with `errors="replace"` and normalising CRLF instead of using locale-dependent `text=True`), adding `Context.read_bytes` (`lines 168-172`), and comparing raw bytes in `swerepo/prrules.py:65` resolve both the binary `UnicodeDecodeError` and the Windows locale hazard cleanly. `test_untracking_a_binary_file_compares_bytes` (`tests/test_prrules.py:218-229`) specifically mutates `\xfe` to `\xfd`, proving two distinct invalid-UTF-8 payloads never collide on `\ufffd`.
- **P2-F10 · Accept.** `_codeowners` (`swerepo/check.py:433-437`) filters out first tokens containing `@` and drops empty parentheses when only malformed owner/email lines trail `# swerepo:end`, tested in `tests/test_check.py:243-251`. The replaced `.seamspec/proposed/inv_5e3b5ef3/test_inv_5e3b5ef3.py` (`lines 25, 45-48`) now includes the trailing email-only `CODEOWNERS` line, asserts `"override governance" in out` across all four CLI modes so the path is guaranteed to execute, and checks both raw and `.resolve()`d paths for `repo` and `tmp_path`.
- **P2-F11 · Accept.** `swerepo/cli.py:51` checks `if only is not None else None`, so `--only ""` reaches `run_check` and exits 2 (`tests/test_check.py:381`).

No new findings in Round 3.

### Readiness summary

- **Proposed SeamSpec rules (`inv_294c48c9` and `inv_5e3b5ef3`):** **Both are ready for the owner's approval** (`uv run seamspec review`), followed by regenerating `docs/EARNED_SPEC.md` (`uv run seamspec spec --out docs/EARNED_SPEC.md`).
- **Phase 2 (`swerepo check`):** All 11 findings (`P2-F01`–`P2-F11`) are resolved and verified. **Phase 2 can close and is ready to merge.**

### Developer: SeamSpec reviewer's explanation, before the owner's approval

SeamSpec's reviewer (a separate agent that didn't write the tests) asked for changes to both proposed rules before approval. Both are made, and both proposals are replaced and verified:

- **`inv_294c48c9`:** the two command-line runs weren't checked, so a command that crashed at the start would have passed. Both now assert exit code 1, the `--ci` output and annotations, and parsable JSON with the expected findings. The test now confirms a finding from each of the six components, not three. `state.py` and `detect.py` are added to the scope, since the run goes through them.
- **`inv_5e3b5ef3`:** "isn't a noreply" matched both email warnings, so the test couldn't show both came up. It now checks the configured-email and commit-email messages separately, runs every output with `--base` (plus a missing-progress finding), and the rule is worded for the cases it tests instead of "never".
- **Mutation checks:** both tests fail on all seven mutations tried: the index write, the command crashing at the start, the security checker skipped, a path in the state error, the commit-email check dropped, the configured email printed, and the pull-request rules skipped.
- **Dead end `de_a22b43fe`:** unchanged. The reviewer read it as sound. Its scope includes `detect.py` on purpose, so that anyone changing detection's git calls is warned off the same approach.

**Approved and locked by the owner on 2026-11-21** in `seamspec review`: inv_294c48c9 and inv_5e3b5ef3. For each, SeamSpec confirmed the test fails on the last commit and passes with the change. Dead end `de_a22b43fe` is active. `docs/EARNED_SPEC.md` regenerated (8 rules in force, 2 retired, 1 tried and failed).

**Review closed 2026-11-21:** all 11 findings resolved (P2-F01 to P2-F11), Gemini's readiness summary in round 3: ready to merge. Next: commit and pull request with the owner's go-ahead, then Copilot's review on the PR.

### After merge: GitHub Copilot's review on PR #3

PR #3 was merged at 08:10 UTC; Copilot's review, requested by the ruleset at 08:06, arrived at 08:12 with eight threads (1 high, 7 medium). All eight were reproduced on `main` and fixed on `phase-2/copilot-fixes`, each with a regression test that fails with its fix undone:

1. **High: workflow-command injection through the text report.** A newer state file's `mode` holding a newline printed a line starting `::error::` on Actions. Every text line now shows CR and LF as `\r` and `\n` (`check.one_line`), wrong-usage messages too.
2. **`[agents] hosts = []` fell back to detection.** Now an explicit empty list chooses no editor (`State.hosts_chosen`).
3. **`tool = "oops"` crashed `check --only ci`.** Guarded.
4. **A step named `seamspec verify` counted as running the locked rules.** Only `run:` commands count now, one-line or block, without comments; `uvx seamspec==X verify` counts. Partly different from the suggestion: when no step runs it, the finding stays `✗`, not `?`. A script a step calls isn't read, and `✗` names what to add (ADR-20261120-fc5a item 3).
5. **`components = []` checked all six components.** Now it chooses nothing (`State.components_chosen`); only a missing key falls back to the default set.
6. **A rejected absolute `[adopted] adr_dir` was repeated in the output.** `check_path` errors no longer repeat the value, and record-table errors name the table, not the rejected key.
7. **`dependencies = "requests>=2"` read as no dependencies.** Now `? can't read dependencies: [project].dependencies isn't a list`.
8. **An invalid dependency was printed verbatim** (a local wheel path, a URL with an address). Now named by position.

Two `test_state.py` expectations that the rejected value is echoed (`projects.ignore: '.'`) now expect the key and the reason without it: that echo is finding 6.

**Process gap:** the ruleset's `copilot_code_review` rule requests the review but doesn't make merging wait for it, so a PR can be merged before Copilot comments (ADR-20261120-2e50).

### GitHub Copilot's review on PR #4

Copilot's review of the follow-up PR found three more false `✓`s in the run-step reader written for finding 4 above, all reproduced:

1. **`run: echo seamspec verify` counted.** Each shell command is now split (`;`, `&&`, `||`, `|`, `&`, newlines) and read with `shlex` (shell comments removed); `seamspec verify` counts only as the command itself, after `VAR=value` assignments and the `uv run`, `uvx`, `uv tool run` and `python -m` wrappers (their options skipped).
2. **An `env` variable named `run` counted.** Only the `run` key of an item of a job's `steps:` list counts, at that step's own key column; a `steps:` inside a step's `with:` doesn't start a list.
3. **`- run: |` measured indentation before the dash**, so a sibling `env:` after the block was read as part of the script. The block now ends at the step's key column.

Ten parametrised cases added (the three above, a nested `steps:` argument, five wrapper forms, a folded `>` block, a second job with an unindented list). Breaking each part of the fix makes a case fail. This repository's `ci.yml` still reads as `✓ CI runs the locked rules`.

