# Code Review · Phase 4: swerepo init for ci and security

**Status:** closed · **Rounds:** 3 · **Developer:** Claude · **Reviewer:** Gemini · **Owner decides:** ties, merges, SeamSpec approvals
**Process:** ADR-20261119-9f87. Finding IDs `P4-F<nn>`; severities `blocker | should-fix | suggestion | question`; responses Fix / Push back / Defer, then Accept / Maintain.

---

## Developer summary

### Scope

`swerepo init` now applies the two components of spec §10's step 3, and `check` checks what they write:

- **`ci`** (`swerepo/ci.py`, `swerepo/init.py`): `.github/workflows/swerepo-ci.yml` and ruff and pytest settings in `pyproject.toml`; `--projects` for monorepos; `--with-governance`; the choice between keeping other linters and moving to ruff gradually.
- **`security`** (`swerepo/privacy.py`, `swerepo/init.py`): `SECURITY.md` with the contact asked for, `.github/workflows/swerepo-privacy.yml`, a `.gitignore` block, and the privacy scan.
- **`check`** (`swerepo/check.py`): the Python matrix against `requires-python`, `ci-ok` waiting for every job, monorepo project coverage, kept linters and `.seamspec`, and the privacy scan. Two `?` items of Phase 4 are now real checks.
- **11 version-1 templates** under `swerepo/templates/ci/` and `swerepo/templates/security/`.

Two owner decisions came first (2026-11-22): SeamSpec's locked rules run **inside `swerepo-ci.yml`** (option (a), open since P0-F01), and SWERepo's own `SECURITY.md` points to **GitHub's private vulnerability reporting**.

Branch `phase-4/ci-security`. Spec updated to v0.10.

### What to review

| Area | Files |
|---|---|
| The workflow and its parts | `swerepo/templates/ci/*/1.*`, `swerepo/ci.py` (`render_workflow`, `settings_block`, `KEPT_LINT`) |
| What CI runs SWERepo with, branch, install, Python versions | `swerepo/ci.py` (`swerepo_command`, `released`, `default_branch`, `install_command`, `python_versions`, `seamspec_pin`) |
| init: ci and security | `swerepo/init.py` (`_workflows`, `_ci`, `_lint_mode`, `_settings`, `_toml_problem`, `_listed_projects`, `_project_inputs`, `_coverage_notes`, `_security`, `contact_text`, `_new_state`); `_managed_file` and `_managed_block` now take a ready render |
| The privacy scan | `swerepo/privacy.py` |
| check | `swerepo/check.py` (`workflow_jobs`, `_ci_ok`, `_python_matrix`, `_projects_covered`, `_settings_mention_seamspec`, `_security`), `swerepo/standard.py` (`LATER`) |
| Command line | `swerepo/cli.py` (`--projects`, `--with-governance`, `_ask_lint`, `_ask_contact`) |
| State | `swerepo/state.py` (`projects_listed`, `projects_not_covered`, `privacy_allow_paths`, `tools`, `set_adopted_linters`, `set_projects_listed`, `set_tool`; validation of `[projects]`, `[privacy]`, `[tools]`) |
| Tests | `tests/test_init_ci.py`, `tests/test_security.py` (new); `tests/test_check.py`, `tests/test_init.py` (updated) |
| ADRs | `docs/adr/ADR-20261122-4a06-ci-component.md`, `docs/adr/ADR-20261122-a48e-security-component.md` |
| Spec | `SWEREPO-SPEC.md` §6.2, §6.3, §6.4, §6.8, §9 (`[values]`, `[blocks."pyproject.toml"]`), §11, §13, Appendix A "0.9 → 0.10" |
| Proposed rules | `.seamspec/proposed/inv_ab57c6ff/`, `.seamspec/proposed/inv_09cc1c20/` |
| Docs | `docs/PROGRESS.md`, `docs/progress/20261122-phase-4-ci-security.md`, `CHANGELOG.md` |

### ADRs written

| ADR | Decision |
|---|---|
| ADR-20261122-4a06 | SeamSpec runs in an always-present `seamspec` job under `ci-ok`. The jobs. `ci-ok` checks each result against what was expected. The workflow is composed from templates at one version number, with its inputs recorded. Governance: pinned, own checkout, or `--with-governance`. Installs with uv only. Python versions from `requires-python`. ruff and pytest settings as a marked block in `pyproject.toml` (settles ADR-20261120-9495 point 5). Kept linters or a gradual move. `--projects`. |
| ADR-20261122-a48e | `SECURITY.md` is a starter file; the contact defaults to private vulnerability reporting. The scan's allowances match inv_62d51113, plus `[privacy] allow_paths`, plus a few secret formats; findings name places only. The privacy workflow needs an installable SWERepo. A `.gitignore` block. |

### How to run

```bash
uv sync
uv run pytest
GITHUB_ACTIONS=true TERM=dumb uv run pytest
uv run ruff check . .seamspec/proposed/
uv run ruff format --check . .seamspec/proposed/
uv run seamspec verify --all
uv run seamspec verify --proposed inv_ab57c6ff --proposed inv_09cc1c20
uv run swerepo init --only ci,security --dry-run       # on this repository: the plan only
mkdir /tmp/demo && cd /tmp/demo && git init -q -b main
printf '[project]\nname = "demo"\nrequires-python = ">=3.11"\n' > pyproject.toml
uv run --project <this checkout> swerepo init --yes --with-governance
uvx zizmor==1.32.0 --offline .github/workflows
uv run --project <this checkout> swerepo check --only ci,security
```

### Results (run by the developer on 2026-11-22, macOS, Python 3.14, uv 0.9.28, git 2.50)

- pytest: **447 passed** (58 new). ruff check and format: clean, including `.seamspec/proposed/`. Locked rules: 10 passed. Proposed rules: 2 passed.
- **Generated workflows:** four variants rendered (ruff, kept black and flake8, gradual, governance plus a project). Each parses as YAML (checked with PyYAML outside the project), zizmor 1.32.0 reports nothing, and `ci-ok`'s `jq` check was run on sample results: a pull request where every job passed, a private repository where dependency review ran when it should have been skipped, and a push with a cancelled job. Only the first passed.
- **Built wheel:** the 11 new templates are inside. Installed in a fresh virtual environment, `swerepo init --yes --with-governance` on a new project created 15 files and a block; the second run said "Nothing to do."; `check --only ci,security` found nothing missing; zizmor passed on both generated workflows.
- **This repository** (`init --only ci,security --dry-run`): `swerepo-ci.yml` with `uv run --locked swerepo` as governance (its own checkout), the existing ruff and pytest settings kept, a note that zizmor also audits the hand-written `ci.yml`, `SECURITY.md` with private reporting, the privacy workflow, a `.gitignore` block, and "privacy scan: nothing found". Not applied: that is its own pull request after this one, as PR #7 was for docs and agents.
- **Mutation checks:**
  - **Component tests:** caught dropping `governance` from `ci-ok`, ignoring a TOML clash, ignoring the `swerepo: allow-privacy` marker, and counting SWERepo's own `[tool.ruff]` as the person's.
  - **Proposed rules:** each caught a mutation of its own: a project's test job left out of `ci-ok`, and the matched text put into a finding.

### Design notes worth checking

1. **The `seamspec` job is always present** (ADR-4a06 point 1). Without `.seamspec/config.toml` it prints a line and passes, so the recommended order (ci before seamspec) needs no workflow change later. In exchange, every repository runs a near-empty job.
2. **Templates without logic, composed at one version number** (point 4). `ci/workflow@1` has placeholders for the lint steps, the optional jobs and `ci-ok`'s `needs:`; each optional part is `ci/<part>@1`. The recorded id `ci/workflow@1`, plus the recorded inputs, names the whole render, so Phase 6 can rebuild it. The test `test_the_rendered_workflow_is_what_was_recorded` does exactly that.
3. **Recorded inputs win on later runs** (`_workflows`, `_lint_mode`): the Python list, default branch, install command, lint mode and governance command. A changed `requires-python` shows in `check` as `↑` (`ci.python-matrix`), not as a silent rewrite. Same reasoning as Phase 3's design note 5.
4. **What counts as "configured"** excludes SWERepo's own block (`ci.without_block`). Otherwise the second run would see its own `[tool.ruff]` and change its mind (mutation 4 above).
5. **`pyproject.toml` gets a marked block, not a tomlkit merge** (point 8). This keeps inv_8314036c's guarantee (only a block at the end of a file SWERepo didn't write). `_toml_problem` refuses the block when the result wouldn't parse, or would change any of the person's values.
6. **`ci` isn't recorded as applied when no workflow can be written** (Poetry, no `[project]`, impossible `requires-python`). Otherwise `check --ci` would start failing for a component the person couldn't get.
7. **The privacy scan also reads untracked files git would add**, as detection lists them, so `init` catches a leak before the first commit. The ADR says "tracked files" in its context; the scan's docstring and spec §6.4 say both.
8. **`ci-ok` with `toJSON(needs)` and `jq`** instead of one environment variable per job: adding a job only touches `needs:`. jq is on GitHub's Ubuntu runners.

### Known gaps and deliberate omissions

- **Poetry and requirements-only projects** get no workflow yet (ADR-4a06 point 6).
- **`[pr] skip_progress_label`** isn't passed by the governance job; the `Progress: none` trailer works (point 5).
- **`[github] extra_required_checks`** is only read: asking for it and putting it in the ruleset belongs to `github` (Phase 5). Until then `check` reports `?` for projects it might cover.
- **Secret scanning** stays `?` until Phase 5 can read the setting.
- **Kept linters' local settings and `.seamspec`**: `check` reports `~` when their own settings don't mention `.seamspec`. It reads the sections detection found and doesn't parse each tool's exclude syntax.
- **`seamspec_pin`** runs `seamspec --version` when the version isn't recorded: one read-only subprocess.
- **Per-project lint** keeps the project's own linters or uses ruff. The gradual move is offered for the root project only.

### Questions for the reviewer

1. **The always-present `seamspec` job** (design note 1): right trade, or only add it when SeamSpec is set up and let `update` add it later?
2. **The `ci-ok` check in `jq`** (design note 8): is reading `needs` as JSON robust enough, or would you rather have explicit per-job variables, as SWERepo's own `ci.yml` does?
3. **A marked block in `pyproject.toml`** (design note 5): any TOML layout where appending tables at the end changes the meaning of the person's text without `_toml_problem` noticing?
4. **Privacy scan patterns** (`privacy.SECRETS`): too narrow, too broad, or missing an obvious format?
5. **The two proposed rules:** the right behaviours to lock, and should either be critical?

### SeamSpec proposals waiting for the owner

| ID | Rule | Critical | Verified |
|---|---|---|---|
| inv_ab57c6ff | The privacy scan reports where, never what: exactly the counts, the first ten places and how many more, in `check` text, JSON and the finding's own annotation, and in `init`'s plan; no value or fragment of one | yes | passed · **locked 2026-11-23** |
| inv_09cc1c20 | `ci-ok` waits for every job in every `swerepo-ci.yml` init writes (also jobs asked for later), and its step, run with bash and jq on sample results, fails on any failed, cancelled, unexpectedly skipped or unexpectedly run job | yes | passed · **locked 2026-11-23** |
| inv_2c3b6053 | `swerepo-ci.yml` tests exactly the Python versions each project declares (three root ranges, a listed project's own), and macOS runs the newest | no | passed · **locked 2026-11-23** |

The owner approved all three in `seamspec review` on 2026-11-23 (13 rules in force); `docs/EARNED_SPEC.md` was regenerated in this pull request.

**After SeamSpec's reviewer (2026-11-22):** the reviewer asked for changes before approval, and all three tests were strengthened. The privacy rule now checks the finding's own annotation, the ten-place limit and the exact message; the `ci-ok` rule runs the generated step itself against every wrong result for every job and event; the Python-versions promise became its own rule. For each rule I broke the behaviour it guards and its test failed (three breakages each for the privacy and `ci-ok` rules, two for the Python one). One breakage first went uncaught: a fragment of the matched text added to the finding. That is why the message is now pinned exactly.

---

## Review rounds

### Round 1

#### Reviewer: verification and strengths

**Verification run (macOS, Python 3.14, uv 0.9.28, git 2.50):** Ran every command under "How to run" (using a scratch `demo` repository outside this checkout), plus targeted reproduction probes:
- `uv sync` → clean (50 packages resolved, 47 audited).
- `uv run pytest` → **447 passed** in 53.74s (0 failures).
- `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **447 passed** in 54.41s (0 failures).
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (109 files formatted).
- `uv run seamspec verify --all` → **10 locked invariants passed**; `uv run seamspec verify --proposed inv_ab57c6ff --proposed inv_09cc1c20` → **2 proposed invariants passed**.
- `uv run swerepo init --only ci,security --dry-run` on this repository → matched the developer summary (`5 changes`, writes nothing; `git status` unchanged).
- Scratch `demo` repository (`requires-python = ">=3.11"`):
  - 1st `swerepo init --yes --with-governance` → exit 0 (`17 changes`; `Applied: 15 file(s) created, 1 block(s) added`, plus `.swerepo.toml`).
  - 2nd `swerepo init --yes --with-governance` → exit 0 (`Nothing to do.`).
  - `uvx zizmor==1.32.0 --offline .github/workflows` → exit 0 (`No findings to report. Good job! (9 suppressed)`).
  - `swerepo check --only ci,security` → exit 0 (`0 missing, 0 changed by you, 0 outdated, 1 can't tell`; spotted a duplicate `✓` line for `.github/workflows/swerepo-privacy.yml`, filed under `P4-F06`).

**What is well done and should be kept:**
- **`swerepo/templates/ci/workflow/1.yml:10-16, 78-120, 134-160` and `swerepo/templates/security/privacy-workflow/1.yml`:** Clean workflow hardening throughout — SHA-pinned actions with version comments, `permissions: contents: read`, `persist-credentials: false` on every checkout, untrusted GitHub context values passed via `env:` rather than `${{ ... }}` interpolation inside `run:` (passing `zizmor` cleanly), multi-commit push handling via `github.event.before` for `seamspec doctor --ci`, and `ci-ok` verifying both expected successes and expected skips.
- **`swerepo/ci.py:157-176, 302-355` and `tests/test_init_ci.py:217-249`:** Composing `ci/workflow@1` from version-matched fragments while stripping SWERepo's own `# swerepo:begin` block (`without_block`) before inspecting user TOML configuration avoids self-detection on second runs and keeps workflow reconstruction deterministic.
- **`swerepo/init.py:451-471` (`_toml_problem`):** Appending settings as a marked block at the end of `pyproject.toml` and verifying `after == before` after removing only SWERepo's added tables preserves `inv_8314036c` without risking `tomlkit` reformatting or silent value overwrites.
- **`swerepo/privacy.py:42-51, 147-155` and `.seamspec/proposed/inv_ab57c6ff/`:** Structural separation of `Hit(kind, path, line)` from matched content guarantees that `privacy.summary`, `check` text/JSON/annotations, and `init` plans never echo leaked addresses, usernames, or keys into CI logs.

---

#### Reviewer: findings

##### P4-F01 · blocker · `swerepo/ci.py:116-120`
**What is wrong:** `install_command(root, folder)` sets `locked = any((d / "uv.lock").is_file() for d in folders)` across `base` and every parent folder up to `root`, without checking whether that parent's `pyproject.toml` declares `[tool.uv.workspace]` covering `folder`. In `swerepo/templates/ci/job-project/1.yml:7, 16, 28, 37`, `lint-<job>` and `test-<job>` run `@@install@@` with `working-directory: @@folder@@`. In `uv`, `uv sync --locked` only uses an ancestor `uv.lock` when that ancestor defines a uv workspace containing the subproject; in a non-workspace monorepo with `root/uv.lock` and a standalone `services/api/pyproject.toml` (the exact setup in `tests/test_init_ci.py:46, 193-204`), `uv sync --locked` inside `services/api` fails immediately because `services/api/uv.lock` does not exist.
**How to reproduce:**
1. Create a repository with `pyproject.toml` (`[project]\nname = "root"\nversion = "0.1.0"\nrequires-python = ">=3.12"\n`), run `uv lock` at the repository root, and add `services/api/pyproject.toml` (`[project]\nname = "api"\nversion = "0.1.0"\nrequires-python = ">=3.12"\n`, with no `services/api/uv.lock` and no `[tool.uv.workspace]` in root `pyproject.toml`).
2. Call `ci.install_command(root, "services/api")` → returns `("uv sync --locked", "")`.
3. Run `uv sync --locked` with `cwd=root / "services/api"` → exits with code `2` (`error: Unable to find lockfile at uv.lock`).
**Suggested fix:** Treat `(base / "uv.lock").is_file()` as locked directly, and treat an ancestor `d != base` with `(d / "uv.lock").is_file()` as locking `folder` only when `d / "pyproject.toml"` defines a `[tool.uv.workspace]` whose `members` globs match `base.relative_to(d)` (and `exclude` globs do not). Add a test covering both standalone subprojects (under a root with `uv.lock`) and `[tool.uv.workspace]` members.

##### P4-F02 · blocker · `swerepo/init.py:242-244, 778-793`, `swerepo/check.py:437`
**What is wrong:** Re-running `swerepo init` with `--projects` or `--with-governance` on an already-initialised repository — as `init`'s own plan notes (`swerepo/init.py:540, 573`) and `check`'s failure message (`swerepo/check.py:437`) tell the user to do — leaves `.github/workflows/swerepo-ci.yml` un-updated, overwrites `.swerepo.toml`'s recorded workflow inputs anyway, and traps `check` and `init` in a loop:
1. `_managed_file` (`swerepo/init.py:242-244`) sees an existing record for `.github/workflows/swerepo-ci.yml` whose `rendered` hash differs from the new render and returns `outdated (... swerepo update (Phase 6))` without writing `.github/workflows/swerepo-ci.yml`.
2. Despite not updating `swerepo-ci.yml` or its `[files.".github/workflows/swerepo-ci.yml"]` record, `_new_state` (`swerepo/init.py:778-793`) writes the new `[projects] listed = [...]` (and `[values] swerepo_command` on `--with-governance`) into `.swerepo.toml`.
3. **Consequence A (corrupted Phase 6 merge base):** `.swerepo.toml`'s recorded inputs no longer rebuild `[files.".github/workflows/swerepo-ci.yml"].rendered`, breaking the reconstruction invariant in Design Note 2 and `ADR-20261122-4a06` point 4.
4. **Consequence B (`check` ↔ `init` loop):** `swerepo check --only ci` now fails (`exit 1`) with `✗ services/api/ is listed, but swerepo-ci.yml has no jobs for it: swerepo init --only ci` (`Next: swerepo init --only ci`), while running `swerepo init --only ci` reports `outdated` and writes nothing.
5. **Consequence C (`swerepo_command` dropped when `shared.python` is empty, `swerepo/init.py:778`):** `_new_state` checks `if shared is not None and {"ci", "security"} & set(applied) and shared.python:` before saving `shared.values`. When `shared.python` is `[]` (e.g. `requires-python = ">=3.99"`), `swerepo init --only security --with-governance --yes` writes `.github/workflows/swerepo-privacy.yml` (using `(shared.python or ci.DEFAULT_PYTHONS)[-1]` on line `630`), but never persists `swerepo_command` in `.swerepo.toml`, so the next `swerepo init --only security` says `.github/workflows/swerepo-privacy.yml not written: needs a released SWERepo`.
**How to reproduce:**
1. In a git repo with `pyproject.toml` and `services/api/pyproject.toml` (`requires-python = ">=3.12"`), run `swerepo init --only ci --yes`, then `swerepo init --only ci --projects services/api --yes`. Inspect `.swerepo.toml` (`projects.listed == ["services/api"]`) and `.github/workflows/swerepo-ci.yml` (no `services-api` jobs), then run `swerepo check --only ci` → exits `1` pointing back to `swerepo init --only ci`.
2. Run `swerepo init --only ci,security --yes`, then `swerepo init --only ci,security --with-governance --yes`: `values.swerepo_command` becomes `'uvx --from git+https://github.com/swerepo/swerepo@main swerepo'`, while `swerepo-ci.yml` has no `governance` job.
3. In a repo with `requires-python = ">=3.99"`, run `swerepo init --only security --with-governance --yes`, then `swerepo init --only security --dry-run`: the second run reports `.github/workflows/swerepo-privacy.yml not written`.
**Suggested fix:**
1. Keep `.swerepo.toml`'s recorded workflow inputs in lockstep with `[files.".github/workflows/swerepo-ci.yml"].rendered`: never overwrite the workflow's recorded inputs unless `swerepo-ci.yml` and its `Record` are written in the same plan.
2. When the user explicitly passes `--projects` or `--with-governance` (or when a `[projects] listed` project lacks jobs in `swerepo-ci.yml`) and `swerepo-ci.yml` on disk is **unmodified** (`file_fingerprint == record.written`), update `swerepo-ci.yml` and its `Record` in place so `--projects` and `--with-governance` work after initial setup as advertised by `init`'s notes and `check.py:437` (while leaving user-edited workflows untouched as `changed`).
3. On `swerepo/init.py:778`, persist `default_branch` and `swerepo_command` whenever `"security" in applied` even if `shared.python` is empty (only skip saving an empty `python` list).

##### P4-F03 · blocker · `swerepo/state.py:280-284, 418-422, 449-450`, `swerepo/ci.py:138-141`, `swerepo/init.py:422-424, 438-442, 556-558`
**What is wrong:** `.swerepo.toml` is a repository file that may come from an untrusted branch or pull request. While `default_branch` (`init.py:414`) and `python` (`init.py:417`) are validated before being substituted into workflow YAML, other recorded workflow values are interpolated unquoted into `run:` steps without validation:
1. **`[tools] seamspec` (`state.py:282, 449-450`, `ci.py:140-141`):** Unlike top-level `swerepo` (validated with `_version` on `state.py:406`), `tools` only checks `isinstance(v, str)`, and `ci.seamspec_pin` returns `recorded` verbatim into `uvx seamspec==@@seamspec@@ ...` (`workflow/1.yml:107-120`). A newline or shell metacharacter in `tools.seamspec` injects arbitrary YAML steps or shell commands into `.github/workflows/swerepo-ci.yml`.
2. **`[values] install` (`init.py:556-558`):** Accepts any non-empty string and substitutes `@@install@@` into `workflow/1.yml:40, 56, 96` and `lint/1.yml:8` (standard 1 only ever produces `"uv sync"` or `"uv sync --locked"`).
3. **`[values] swerepo_command` (`init.py:422-424`):** Accepts any string and substitutes `@@swerepo@@` into `job-governance/1.yml:20` and `privacy-workflow/1.yml:30` (standard 1 only allows `""`, `SWEREPO_OWN_CHECKOUT`, `SWEREPO_FROM_GITHUB`, or `uvx swerepo==<PEP 440 version>`).
4. **`[adopted] linters` (`init.py:438-442`, `ci.py:285-286`):** Not checked against `ci.KEPT_LINT`. If `.swerepo.toml` sets `values.lint = "kept"` with `adopted.linters = []` or an unknown linter name, `ci.lint_runs` returns `[]` and renders a `lint` job that runs **no** linter commands at all while `ci-ok` still passes.
**How to reproduce:**
1. Create a repo with `pyproject.toml` (`requires-python = ">=3.12"`) and `.swerepo.toml` containing:
   ```toml
   standard = 1
   swerepo = "0.0.1"
   [tools]
   seamspec = "0.1.2\n      - run: curl evil"
   ```
   Call `make_plan(root, only=["ci"], hosts=[])`: the rendered `.github/workflows/swerepo-ci.yml` contains `- run: curl evil` as a step in the `seamspec` job (likewise for `values.install` and `values.swerepo_command`).
2. With `values.lint = "kept"` and `[adopted]\nlinters = ["mypy"]`, `make_plan` renders `lint` with `- run: uv sync` as its last line and zero linter steps.
**Suggested fix:** Validate `tools.*` with `_version(v, key=f"tools.{name}")` in `state.py` (`set_tool` and `_validate`) and check `recorded` in `ci.seamspec_pin`; validate recorded `values.install` against `{"uv sync", "uv sync --locked"}` and `values.swerepo_command` against `{SWEREPO_OWN_CHECKOUT, SWEREPO_FROM_GITHUB}` or `uvx swerepo==<released Version>` (falling back to recomputing when invalid); and filter `adopted.linters` to `ci.KEPT_LINT` (requiring at least one known kept linter before accepting `lint == "kept"`).

##### P4-F04 · should-fix · `swerepo/init.py:508`, `swerepo/ci.py:183-191`
**What is wrong:** In `_project_inputs` (`swerepo/init.py:508`), a `--projects` subproject's lint mode is selected with:
`lint = "ruff" if "ruff" in names or not others or ci.ruff_configured(ctx.root, folder) else "kept"`
Because `ci.ruff_configured(ctx.root, folder)` (`swerepo/ci.py:186`) checks both `root / folder` **and `root`**, any monorepo whose root project configures Ruff (`[tool.ruff]` in root `pyproject.toml`, `ruff.toml`, or `.ruff.toml`) forces `lint = "ruff"` onto **every** subproject — even when `services/api/pyproject.toml` configures `[tool.black]` / `.flake8` / `[tool.isort]` and has no Ruff configuration of its own. That contradicts `SWEREPO-SPEC.md` §11 (`line 449`: *"with that project's own linter detection and choice"*) and `CODE_REVIEW.md` (`line 94`: *"Per-project lint keeps the project's own linters or uses ruff"*).
**How to reproduce:**
Create a git repo with root `pyproject.toml` (`[project]\nname = "root"\n[tool.ruff]\nextend-exclude = [".seamspec"]\n`) and `services/api/pyproject.toml` (`[project]\nname = "api"\n[tool.black]\nline-length = 100\n`), and call `make_plan(root, only=["ci"], hosts=[], projects=["services/api"])`: `lint-services-api` in `.github/workflows/swerepo-ci.yml` runs `uv run ruff check .` and `uv run ruff format --check .` instead of `uv run black --check --extend-exclude '\.seamspec' .`.
**Suggested fix:** In `_project_inputs` (`swerepo/init.py:508`), check only `folder` itself (`"ruff" in names or not others or ci.ruff_configured(ctx.root / folder)`) when choosing `"ruff"` vs `"kept"`, while keeping `ci.ruff_configured(ctx.root, folder)` in `_settings` (`swerepo/init.py:478`) so subprojects that do use Ruff still inherit a root `[tool.ruff]` without a duplicate table.

##### P4-F05 · should-fix · `swerepo/privacy.py:113, 120-122`
**What is wrong:** Two path-handling bugs in `swerepo/privacy.py`:
1. **`allowed_path` (`lines 120-122`) uses `fnmatch.fnmatchcase` directly:** `fnmatchcase` treats `/` as an ordinary character and treats `**` identically to `*`. As a result:
   - Single-`*` globs such as `allow_paths = ["*.md"]` or `["docs/*.md"]` cross `/` and silently exempt files in every nested subdirectory (`a/b/c/secret.md`, `docs/sub/secret.md`), disabling scanning much more broadly than standard path globs; and
   - Double-`**` globs such as `allow_paths = ["tests/**/data.md"]` and `["**/fixtures/**"]` return `False` on zero-segment paths (`tests/data.md`, `fixtures/data.md`) because `fnmatchcase` requires literal slashes on both sides of `**`.
2. **Only root `"SECURITY.md"` is exempted for contact emails (`line 113`):** `line_kinds` checks `if path != "SECURITY.md":`, whereas `detect` (`detect.py:390-395`), `init._security` (`init.py:618-620`), and `check._security` (`check.py:527`) all recognise and adopt `.github/SECURITY.md` and `docs/SECURITY.md` (case-insensitively). A repository whose security policy is `.github/SECURITY.md` or `docs/SECURITY.md` with a published vulnerability-reporting address gets `✓ .github/SECURITY.md` for `security.policy` and then fails `security.privacy-scan` on that same file.
**How to reproduce:**
1. Call `privacy.allowed_path("docs/sub/secret.md", ["docs/*.md"])` → `True`; call `privacy.allowed_path("tests/data.md", ["tests/**/data.md"])` and `privacy.allowed_path("fixtures/data.md", ["**/fixtures/**"])` → both `False`.
2. Commit `.github/SECURITY.md` containing a reporting email address (at a non-example domain) and run `run_check(root, only=["security"])` → `security.policy` is `ok` (`.github/SECURITY.md`), while `security.privacy-scan` fails with `missing` (`1 email address in tracked files (.github/SECURITY.md:1)`).
**Suggested fix:**
1. Match `allow_paths` with segment-aware POSIX glob semantics (`*` and `?` match within `[^/]*`, `**` matches zero or more path segments, and `dir` / `dir/` matches `dir/**`).
2. Exempt all adopted security policy paths (`path.lower() in {"security.md", ".github/security.md", "docs/security.md"}`, or pass the detected policy path into `privacy.scan`).

##### P4-F06 · should-fix · `swerepo/check.py:348-349, 429-435, 471, 510, 533`
**What is wrong:** Three reporting/coverage bugs in `swerepo/check.py`:
1. **False `✓` when a kept linter is configured only in `.pre-commit-config.yaml` (`lines 471, 510`):** `_settings_mention_seamspec` has `if ".seamspec" not in text and name != ".pre-commit-config.yaml": return False` and then returns `bool(places)`. When `black` (or `flake8`/`isort`) is configured solely in `.pre-commit-config.yaml` with no `.seamspec` exclusion anywhere, the loop never returns `False`, so `check` falsely reports `✓ black skip .seamspec (their own settings)` (also singular/plural grammar `"black skip"` on line `471`), even though local `pre-commit run` will reformat `.seamspec/tests/`.
2. **`_projects_covered` skips `[projects] listed` folders outside `d.projects` and ignores missing `lint-<job>` (`lines 348-349, 429, 434`):** `ADR-20261122-4a06` point 10 explicitly allows `--projects tools/gen` for folders in `NON_PROJECT_DIRS` that detection skips. Yet `_ci` (`line 348`) only calls `_projects_covered` `if d.is_monorepo:` (which is `False` when root + `tools/gen` are the only projects) and `_projects_covered` (`line 429`) iterates only `ctx.detection.projects`, ignoring `listed`. Removing `tools-gen`'s jobs from `swerepo-ci.yml` produces no `ci.projects:tools/gen` finding. In addition, line `434` checks only `f"test-{job}" in jobs` and not `f"lint-{job}" in jobs`.
3. **Duplicate `✓` output and `path=None` for `security.workflow` (`line 533`):** `_ok(c, "security.workflow", f"privacy workflow ({standard.PRIVACY_WORKFLOW})")` omits `standard.PRIVACY_WORKFLOW` as the 4th `path` argument (unlike `_missing` on line `537` and `_ci` on line `330`). Consequently, `--json` emits `"path": null` and `_without_repeats` (`line 817`) cannot deduplicate the managed-file record, printing both `✓ privacy workflow (.github/workflows/swerepo-privacy.yml)` and `✓ .github/workflows/swerepo-privacy.yml (current)`.
**How to reproduce:**
1. Create a repo with `pyproject.toml`, `.seamspec/config.toml` (`mode = "enforced"`), and `.pre-commit-config.yaml` containing a `black` hook with no `exclude`, and run `run_check(root, only=["ci"])`: `ci.seamspec-excluded` returns `('ok', 'black skip .seamspec (their own settings)')`.
2. Create a repo with `pyproject.toml` and `tools/gen/pyproject.toml`, run `swerepo init --only ci --projects tools/gen --yes`, delete `lint-tools-gen` and `test-tools-gen` from `.github/workflows/swerepo-ci.yml`, and run `swerepo check --only ci`: no `ci.projects:tools/gen` finding is reported (`exit 0`).
3. Run the `CODE_REVIEW.md` "How to run" demo commands (`swerepo init --yes --with-governance` then `swerepo check --only ci,security`): `security` prints two `✓` lines for `.github/workflows/swerepo-privacy.yml`.
**Suggested fix:**
1. Check `".seamspec" in text` for `.pre-commit-config.yaml` when it is the only configured location (or across every configured location, since `.pre-commit-config.yaml` supports `exclude: \.seamspec`), and use `"skips"` when `len(linters) == 1`.
2. Call `_projects_covered` whenever `d.is_monorepo or (ctx.state and ctx.state.projects_listed)`, iterate over all paths in `{p.path for p in d.projects if p.path != "."} | set(listed)`, and require both `f"lint-{job}" in jobs and f"test-{job}" in jobs`.
3. Pass `standard.PRIVACY_WORKFLOW` as the 4th argument on `swerepo/check.py:533`.

##### P4-F07 · should-fix · `swerepo/init.py:141-145, 701-703, 715-728`
**What is wrong:** When a repository has a non-Ruff linter (e.g. `[tool.black]`) and the user chooses `lint = "gradual"` during `swerepo init`, `compute_values` (`swerepo/init.py:702`) runs *before* `_ci` resolves `lint="gradual"`. On the first run, `detection.linters` has `"black"` and not `"ruff"`, so `ctx.values["commands"]` writes `- Lint: \`uv run black --check .\`` into `AGENTS.md`, `CONTRIBUTING.md`, and `README.md`, and saves that in `.swerepo.toml`. Meanwhile `_ci` appends SWERepo's `[tool.ruff]` block to `pyproject.toml`. On the immediate next run of `swerepo init`, `detect()` reads the full `pyproject.toml` (including SWERepo's `[tool.ruff]` block), sees `"ruff"`, and computes Ruff commands for `computed["commands"]` — triggering a spurious `note: the project's commands changed since they were recorded: swerepo update (Phase 6)` on a freshly initialised, untouched repository.
**How to reproduce:**
In a git repo with `pyproject.toml` containing `[project]\nname = "x"\nrequires-python = ">=3.12"\n[tool.black]\nline-length = 100\n`, run `apply(make_plan(root, lint="gradual", hosts=[]), root)` and then immediately call `make_plan(root, hosts=[])`: `AGENTS.md` lists `uv run black --check .` rather than Ruff, and the second `make_plan` emits `Action("agents", "note", None, "the project's commands changed since they were recorded: \`swerepo update\` (Phase 6)")`.
**Suggested fix:** Resolve `_lint_mode` before `compute_values` (and pass `lint_mode` — or exclude SWERepo's own block when detecting the project's own linters for `commands`) so `gradual` writes consistent lint instructions on the first run and computes the exact same `commands` value on the second run.

##### P4-F08 · suggestion · `swerepo/privacy.py:28-37`
**What is wrong:** In `privacy.SECRETS`, line `36` (`r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}T3BlbkFJ[A-Za-z0-9_-]{20,}"`) requires the legacy `T3BlbkFJ` marker that OpenAI dropped in 2024 when introducing `sk-proj-...` and `sk-svcacct-...` keys, so current OpenAI keys are not detected. Also, for Python repositories (especially ahead of Phase 8's PyPI release workflow), PyPI API tokens (`pypi-AgEIcHlwaS5vcmc...`) are a very common accidental commit and carry a fixed base64 `pypi.org` Macaroon header with near-zero false positives.
**How to reproduce:**
Call `privacy.line_kinds("x.py", "sk-" + "proj-" + "a" * 48, set())` → returns `[]`.
**Suggested fix:** Match `sk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{40,}` alongside legacy `sk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}`, and add `("PyPI token", re.compile(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{50,}\b"))` (and optionally Hugging Face `\bhf_[A-Za-z0-9]{34,}\b`).

##### P4-F09 · suggestion · `swerepo/templates/ci/lint-gradual/1.yml:21-33`
**What is wrong:** On lines `32-33`, `xargs -0 uv run ruff check --force-exclude < "$RUNNER_TEMP/changed"` (and `ruff format --check --force-exclude`) omits `--` before filename arguments, so a changed root-level `.py` file starting with `-` is parsed as CLI flags by Ruff. Also on lines `21-25`, unlike `workflow/1.yml:108-112`, a push where `$BEFORE` is `0000000000000000000000000000000000000000` does not fall back to `HEAD~1` when `HEAD~1` exists.
**How to reproduce:**
Create `-bad.py` in a repository and run `printf '%s\0' '-bad.py' | xargs -0 uv run ruff check --force-exclude` → Ruff exits with `error: unexpected argument '-b' found`; adding `--` after `--force-exclude` lints `-bad.py` cleanly.
**Suggested fix:** Add `-r` and `--` (`xargs -0r uv run ruff check --force-exclude -- < "$RUNNER_TEMP/changed"` and `xargs -0r uv run ruff format --check --force-exclude -- < "$RUNNER_TEMP/changed"`), and optionally mirror `workflow/1.yml:108-112`'s `HEAD~1` fallback.

---

#### Reviewer: answers to "Questions for the reviewer"

1. **The always-present `seamspec` job (design note 1):** **Right trade — keep it always present.** Spec §10's adoption sequence puts `ci` in step 3 and `seamspec` in step 5. Having `seamspec` already wired into `ci-ok` means enabling SeamSpec later (`seamspec init --no-ci`) immediately gates merges with zero workflow edits, zero ADR churn, and no risk of forgetting `swerepo update` and assuming locked rules are blocking merges when they aren't. Without `.seamspec/config.toml`, the job skips `setup-uv` and `uv sync` and finishes in a few seconds in parallel with `lint` and `test`.
2. **The `ci-ok` check in `jq` (design note 8):** **`toJSON(needs)` + `jq` is robust and preferable here to per-job variables.** Because `swerepo-ci.yml` has a dynamic job list (`governance` plus arbitrary `lint-<job>` / `test-<job>` pairs from `--projects`, plus any custom job a user adds to `ci-ok.needs`), deriving expectations from `needs` in one place means adding a job touches only `needs:` and defaults safely to requiring `"success"`. Passing `NEEDS` via `env:` avoids script injection, `jq` is standard on `ubuntu-latest`, and `set -eu` fails closed.
3. **A marked block in `pyproject.toml` (design note 5):** **`_toml_problem` (`swerepo/init.py:451-471`) is sound.** I tested inline `tool = {...}` tables, scalar `tool = "x"`, trailing `[[array.of.tables]]` sections, preexisting `[tool.pytest]` sibling subtables, and syntax errors at EOF: TOML 1.0 forbids reopening inline tables or scalars (`TOMLDecodeError`, caught on line `460`), a new `[tool.ruff]` header cleanly closes any preceding table scope, and `after == before` after popping only SWERepo's keys catches any structural or value drift. (Even a literal `nan` float in user TOML fails safe by evaluating `after == before` as `False` and returning `KEEP`.)
4. **Privacy scan patterns (`privacy.SECRETS`):** **Good high-precision baseline (prefix + length rather than noisy generic entropy rules), with two additions recommended in `P4-F08`:** update OpenAI's pattern so modern `sk-proj-...` and `sk-svcacct-...` keys (without legacy `T3BlbkFJ`) are caught, and add PyPI Macaroon tokens (`pypi-AgEIcHlwaS5vcmc...`), which are zero-false-positive and directly relevant to Python repositories. Leave broad provider catalogs to GitHub secret scanning (Phase 5).
5. **The two proposed rules (`inv_ab57c6ff`, `inv_09cc1c20`):** **Both capture the right Phase 4 invariants, and both should be marked `critical: true`:**
   - `inv_ab57c6ff` prevents `check` and `init` from leaking personal emails, home paths, or live secrets into CI logs and PR annotations — the same security/privacy boundary as `inv_5e3b5ef3` (locked `critical`).
   - `inv_09cc1c20` protects the single merge gate (`ci-ok`) that branch rulesets require; leaving any job out of `ci-ok.needs` silently lets failing checks merge, on par with `inv_b14b3413` (locked `critical`).
   - Two small strengthenings recommended while addressing Round 1: in `inv_09cc1c20`, add `"swerepo/detect.py"` to `scope.paths` (since `ci.python_versions` delegates version resolution to `detect.py`) and assert that `ci-ok` still checks `toJSON(needs)` rather than only `if: always()` + `needs:`.

#### Readiness summary

Not ready to merge yet: **3 blockers** (`P4-F01`–`P4-F03`), **4 should-fix** findings (`P4-F04`–`P4-F07`), and **2 suggestions** (`P4-F08`–`P4-F09`). Hold owner approval of `inv_ab57c6ff` and `inv_09cc1c20` until the Round 1 fixes and the `critical: true` / `inv_09cc1c20` scope updates are in place.

### Developer responses

All nine findings were reproduced on the reviewed code before any change: F01 with uv itself (`uv sync --locked` in a standalone `services/api` under a root `uv.lock` exits 2), F09 with ruff on a file named `-bad.py`, and the rest through `make_plan`, `run_check` and `privacy`. All nine are fixed, each with a regression test (`TestGeminiReviewRound1` in `tests/test_init_ci.py` and `tests/test_security.py`). For F01, F02, F04 and F06 I put the old code back and saw its test fail. pytest: **479 passed** (32 new), also with `GITHUB_ACTIONS=true TERM=dumb`; ruff clean; 10 locked rules and both proposed rules pass; the changed gradual workflow parses as YAML and passes zizmor. Spec v0.10 and both ADRs updated.

#### P4-F01 · **Fix**
`ci._workspace_root` walks up from the project to the repository root and returns the uv workspace whose `[tool.uv.workspace]` `members` globs (minus `exclude`) contain it. `install_command` uses `--locked` only for the project's own `uv.lock` or that workspace's. Test: `test_p4_f01_a_lock_file_above_counts_only_for_a_workspace_member` (standalone, member, excluded member, own lock).

#### P4-F02 · **Fix** (all three, with one change to your suggestion)
1. **Inputs in step with what was written.** A workflow's inputs are recorded only when it is created, rewritten or already current (`init.WRITTEN`). A changed or outdated workflow keeps its recorded inputs, and the plan says the request waits for it.
2. **Asking later works.** `--projects` or `--with-governance` on a set-up repository rewrites `swerepo-ci.yml` (and `swerepo-privacy.yml`) when SWERepo wrote it and its fingerprint still equals `written`: a new verb `rewrite`, checked in the preflight and again just before the write. A file changed after the plan stops the run with nothing written (`test_p4_f02_a_rewrite_stops_if_the_file_changed_after_the_plan`). `check`'s message now names the command that does it: `swerepo init --only ci --projects <listed>`.
3. **The change to your suggestion:** one recorded command fed both workflows, so asking for governance could still leave one of them out of step. Each workflow now records its own: `[values] governance_command` and `privacy_command` (and `install` became `ci_install`, which no longer shares a name with the README's install value). `default_branch` is recorded whenever either workflow is written; `python` only when it isn't empty (your consequence C).
Tests: `test_p4_f02_asking_later_rewrites_an_unchanged_workflow_and_keeps_inputs_in_step`, `test_p4_f02_a_changed_workflow_keeps_its_inputs_and_says_why`, `test_p4_f02_the_privacy_command_is_recorded_without_python_versions`. The proposed rule `inv_09cc1c20` now covers jobs asked for after the first run.

#### P4-F03 · **Fix** (all four)
- `[tools]` values must be one plain word (`state._check_tool`, on load and on `set_tool`): a newline or `&&` makes the state file unreadable, as any other invalid value does.
- `ci.seamspec_pin` uses a recorded or installed version only if `ci.valid_pin` accepts it (a PEP 440 version, nothing else).
- A recorded `ci_install` is used only if it is one of `ci.INSTALLS`, and a recorded SWERepo command only if `ci.valid_swerepo_command` accepts it (`""`, the own-checkout or GitHub command, or `uvx swerepo==<released version>`); otherwise init computes them again.
- `[adopted] linters` are filtered to the ones standard 1 can run (`ci.KEPT_LINT`). A recorded `lint = "kept"` with none left falls back to detection, so a lint job is never empty.
Tests: `test_p4_f03_recorded_values_never_reach_a_workflow_unchecked` (four values), `test_p4_f03_unknown_kept_linters_fall_back_to_detection`.

#### P4-F04 · **Fix**
As suggested: the project's lint choice looks at its own configuration only (`ruff_configured(..., inherit=False)`), while `_settings` still lets a root `[tool.ruff]` stand in for the project's ruff table. Test: `test_p4_f04_a_projects_own_linters_win_over_a_root_ruff`.

#### P4-F05 · **Fix** (both)
1. `privacy._glob` reads `allow_paths` as git does: `*` and `?` within a folder, `**` across any number of folders (none included), and a folder covers what is in it. Nine cases in `test_p4_f05_allow_paths_globs_respect_folders`.
2. The contact is allowed in every place detection takes a security policy from (`privacy.POLICY_PATHS`, case-insensitive). Home-folder paths there are still found. Test: `test_p4_f05_the_contact_in_any_policy_place_is_allowed`.

#### P4-F06 · **Fix** (all three)
1. A kept linter configured only in `.pre-commit-config.yaml` must name `.seamspec` there too (a hook's `exclude:`); "skips" for one linter. Test: `test_p4_f06_a_linter_only_in_pre_commit_must_skip_seamspec_there_too`.
2. Coverage covers every listed folder, also those detection skips, whenever something is listed, and needs both the lint and the test job. Test: `test_p4_f06_listed_projects_outside_detection_are_checked`.
3. `security.workflow` carries its path, so the record line no longer repeats it. Test: `test_p4_f06_the_privacy_workflow_is_reported_once_with_its_path`.

#### P4-F07 · **Fix**
The lint choice is now made before the commands are computed, and passed to them. With `gradual`, the agents block lists `uv run ruff check --force-exclude <changed .py files>` and the format check, matching what CI runs. A later run computes the same commands, so no note appears. Test: `test_p4_f07_gradual_lists_the_same_commands_on_every_run`.

#### P4-F08 · **Fix**
Added: OpenAI project, service-account and admin keys, with the legacy `T3BlbkFJ` form kept; PyPI tokens; Hugging Face tokens. Test: `test_p4_f08_current_token_formats`.

#### P4-F09 · **Fix** (both)
`--` after `--force-exclude` in both ruff commands (checked with ruff on `-bad.py`), and a push whose `before` is all zeros (a new branch) compares with `HEAD~1`, as the SeamSpec job does. `xargs -r` isn't needed: the step exits before `xargs` when nothing changed. `ci/lint-gradual@1` hasn't been released, so it was corrected in place. Test: `test_p4_f09_the_gradual_step_protects_file_names_and_new_branches`.

#### On your answers
- **Q1, Q2 and Q3:** agreed. They stay as they are.
- **Q4:** done in F08.
- **Q5:** both rules re-proposed as critical. `inv_09cc1c20` now includes `swerepo/detect.py` in its scope, checks that `ci-ok` reads `toJSON(needs)` and exits 1 on a mismatch, and adds a run where governance and a project are asked for after the first run.
  - One correction: there is no `inv_b14b3413` in this repository. The locked rules are listed in `docs/EARNED_SPEC.md`; the closest is the hygiene pack's rule 4 (spec §6.8), which Phase 7 will propose for a repository's own workflow.

Ready for round 2.

---

### Round 2

#### Reviewer: verification

Re-ran every command under "How to run" (plus targeted Round 2 probes on `REWRITE`, recorded workflow values, `_workspace_root`, and `privacy._glob`):
- `uv sync` → clean (50 packages resolved, 47 audited).
- `uv run pytest` → **479 passed** in 52.79s; `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **479 passed** in 52.99s.
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (109 files formatted).
- `uv run seamspec verify --all` → **10 locked invariants passed**; `uv run seamspec verify --proposed inv_ab57c6ff --proposed inv_09cc1c20` → **2 proposed invariants passed** (both now `critical: true`, with `swerepo/detect.py` in `inv_09cc1c20`'s scope and `toJSON(needs)` + post-init `--projects`/`--with-governance` assertions).
- `uv run swerepo init --only ci,security --dry-run` on this repository → `5 changes`, writes nothing.
- Scratch `demo` repository: 1st `init --yes --with-governance` → `17 changes`; 2nd `init --yes --with-governance` → `Nothing to do.`; `zizmor==1.32.0 --offline` → `0` findings; `check --only ci,security` → exit `0` (`0 missing, 0 changed by you, 0 outdated, 1 can't tell`, with `.github/workflows/swerepo-privacy.yml` reported once).

#### Reviewer: response to developer responses

- **P4-F01 · Accept** (with a new edge-case crash in `_workspace_root` filed separately as `P4-F10`): `ci._workspace_root` and `install_command` (`swerepo/ci.py:110-140`) now distinguish standalone subprojects from `[tool.uv.workspace]` members (and excluded members), verified by `test_p4_f01_a_lock_file_above_counts_only_for_a_workspace_member`.
- **P4-F02 · Accept:** Splitting `swerepo_command` into per-workflow `governance_command` and `privacy_command` (plus `ci_install`, `swerepo/init.py:435-458, 592-610, 671-682, 831-860`) is cleaner than a single shared key — enabling `--only security --with-governance` and `--only ci --with-governance` independently never knocks either workflow's recorded merge-base inputs out of step. I also audited the new `REWRITE` verb (`swerepo/init.py:888-890, 911-920, 958-960`): it requires an existing `.swerepo.toml` record, verifies `not target.is_symlink()` and `file_fingerprint == action.expect` in `_check_targets` and again immediately before `write_text`, preserves user-edited workflows as `changed`, and composes cleanly in both orders (`--projects` then `--with-governance`, and vice versa).
- **P4-F03 · Accept:** `state._check_tool` (`swerepo/state.py:455-460`), `ci.valid_pin`, `ci.INSTALLS`, `ci.valid_swerepo_command` (`swerepo/ci.py:107, 142-164`), and `_lint_mode`'s `ci.KEPT_LINT` filter (`swerepo/init.py:472-480`) close all four injection / empty-lint paths, covered by `test_p4_f03_recorded_values_never_reach_a_workflow_unchecked` and `test_p4_f03_unknown_kept_linters_fall_back_to_detection`.
- **P4-F04 · Accept:** `ci.ruff_configured(..., inherit=False)` in `_project_inputs` (`swerepo/init.py:543`) preserves subprojects' own kept linters when root configures Ruff, while `_settings` (`line 512`) still avoids duplicating `[tool.ruff]` for Ruff subprojects.
- **P4-F05 · Accept** (with ReDoS / path-normalization issues in the new `privacy._glob` filed separately as `P4-F11`): single-`*` stays within a folder, `**` matches zero or more folders, directory entries cover their contents, and `POLICY_PATHS` (`swerepo/privacy.py:41, 117`) exempts contact emails in `.github/SECURITY.md` and `docs/SECURITY.md` while still catching home-folder paths and secrets.
- **P4-F06 · Accept:** Pre-commit-only linters must exclude `.seamspec` (`swerepo/check.py:512`), singular `"skips"` is fixed (`line 472`), `_projects_covered` checks `listed` projects outside `d.projects` and requires both `lint-<job>` and `test-<job>` (`lines 348, 430-439`), and `security.workflow` carries `standard.PRIVACY_WORKFLOW` (`line 536`).
- **P4-F07 · Accept:** Resolving `_lint_mode` before `compute_values` (`swerepo/init.py:148-150, 750-751`) writes `uv run ruff check --force-exclude <changed .py files>` on run 1 and produces identical `commands` on subsequent runs.
- **P4-F08 · Accept:** Modern OpenAI (`sk-proj-`, `sk-svcacct-`, `sk-admin-` alongside legacy `T3BlbkFJ`), PyPI, and Hugging Face token patterns added (`swerepo/privacy.py:36-38`) and tested.
- **P4-F09 · Accept:** `--` after `--force-exclude` and the `0000...` / `HEAD~1` new-branch fallback are in `swerepo/templates/ci/lint-gradual/1.yml:21-25, 36-37` and tested. (Also acknowledging your Q5 correction: `inv_b14b3413` was my misreference — hygiene rule 4 in spec §6.8 is the right parallel.)

---

#### Reviewer: new findings

##### P4-F10 · should-fix · `swerepo/ci.py:120-121`
**What is wrong:** In `_workspace_root`, lines `120-121` pass raw strings from `[tool.uv.workspace]` `members` and `exclude` directly to `pathlib.Path.glob`:
```python
members = {m.resolve() for g in workspace.get("members", []) if isinstance(g, str) for m in folder.glob(g)}
excluded = {m.resolve() for g in workspace.get("exclude", []) if isinstance(g, str) for m in folder.glob(g)}
```
Under Python 3.12 (used by `.venv` and tested in the 3.11–3.14 matrix), `folder.glob(g)` raises unhandled exceptions on valid or mildly malformed `pyproject.toml` entries, crashing `swerepo init --projects ...` with a raw Python traceback (whose stack frames also expose absolute local paths):
1. `members = [".", "services/*"]` (a common Cargo/uv convention explicitly listing `.` alongside member globs): `folder.glob(".")` raises **`IndexError: tuple index out of range`**.
2. `members = [""]` (or `exclude = [""]`): `folder.glob("")` raises **`ValueError: Unacceptable pattern: ''`**.
3. `members = ["/services/*"]`: `folder.glob("/services/*")` raises **`NotImplementedError: Non-relative patterns are unsupported`**.
**How to reproduce:**
Create a repository with `pyproject.toml` containing `[project]\nname = "root"\n[tool.uv.workspace]\nmembers = [".", "services/*"]\n`, `uv.lock`, and `services/api/pyproject.toml` (`[project]\nname = "api"\n`), and call `ci.install_command(root, "services/api")` under Python 3.12 (`uv run python`): raises `IndexError: tuple index out of range` (likewise `ValueError` for `[""]` and `NotImplementedError` for `["/services/*"]`).
**Suggested fix:** Either match `base.relative_to(folder).as_posix()` against the workspace member/exclude globs in memory without `Path.glob` (skipping empty / leading-`/` patterns and treating `"."` as `folder` itself), or normalize `"."` / skip `""` and leading `"/"` before `folder.glob(g)` and catch `(OSError, ValueError, NotImplementedError, IndexError)`.

##### P4-F11 · should-fix · `swerepo/privacy.py:124-144`
**What is wrong:** Two issues in `privacy._glob`:
1. **Catastrophic regex backtracking (ReDoS) on `[privacy] allow_paths` globs (`lines 133-138`):** `_glob` translates every `*` to greedy `[^/]*` (without atomic grouping or collapsing adjacent `*`) and every non-final `**` to `(?:[^/]+/)*` (without collapsing adjacent `**`). Because `.swerepo.toml` is a repository file read by `swerepo check --ci` in CI (`swerepo-privacy.yml` and `governance`), multi-wildcard globs trigger exponential/combinatorial backtracking across tracked files (the glob counterpart to Phase 3's `P3-F10`):
   - `allow_paths = ["*********b"]` takes **1.23s** on a single 30-character filename `"a" * 30 + ".py"` (`>30s` per file at 10 stars, hanging `privacy.scan` across a repository until CI job timeout).
   - `allow_paths = ["*a*a*a*a*a*a*a*a*a*b"]` (non-adjacent `*`) takes **0.31s** on one 30-character filename and doubles with each added `*a`.
   - `allow_paths = ["**/**/**/**/**/**/**/nope"]` backtracks combinatorially across nested folders (`~0.08s` per file on 24 segments).
   In addition, `scan()` (`line 152`) calls `allowed_path(path, allow_paths or [])` inside the per-file loop rather than compiling the globs once.
2. **Unnormalized `/` and `.` segments inside globs (`line 129`):** `parts = glob.strip("/").split("/")` keeps `""` and `"."` segments, so `allow_paths = ["docs//fixtures"]` and `["docs/./fixtures"]` return `False` for `"docs/fixtures/x.md"`.
**How to reproduce:**
1. Time `privacy.allowed_path("a" * 30 + ".py", ["*********b"])` (`~1.23s` for a single file) and `privacy.allowed_path("a" * 30 + ".py", ["*a" * 9 + "*b"])` (`~0.31s` for a single file).
2. Call `privacy.allowed_path("docs/fixtures/x.md", ["docs//fixtures"])` and `privacy.allowed_path("docs/fixtures/x.md", ["docs/./fixtures"])` → both return `False`.
**Suggested fix:**
- Split normalized segments with `[p for p in glob.strip("/").split("/") if p and p != "."]` and collapse consecutive `"**"` segments.
- Match path segments with a small NFA state set (`states: set[int]`) over `path.split("/")` (returning `True` whenever the end state is reached so folder globs still match everything inside them, in guaranteed $O(\text{len(parts)} \times \text{len(segments)})$ time), and compile each single segment via `fnmatch.translate` (escaping `[` as `[[]` if literal brackets are desired) — in Python >=3.11 `fnmatch.translate` emits atomic groups, matching `"*a" * 9 + "*b"` on `"a" * 100 + ".py"` in ~13 µs. Pre-compile the globs once in `scan()`.

#### Readiness summary

All 9 Round 1 findings (`P4-F01`–`P4-F09`) are **Accepted**, and both proposed critical rules (`inv_ab57c6ff` and `inv_09cc1c20`) have the right assertions and scopes. Hold merge and owner rule approval for **2 should-fix** regressions found in the new helper code (`P4-F10` in `swerepo/ci.py` and `P4-F11` in `swerepo/privacy.py`, both in scope of the proposed rules).

### Developer responses (round 2)

Thank you for the audit of `rewrite`. Both new findings reproduced exactly as you described: P4-F10 crashed with `IndexError`, `ValueError` and `NotImplementedError` for the three `members` values, and P4-F11 took 1.24 s and 0.31 s per file for the two globs, and missed `docs//fixtures` and `docs/./fixtures`. Both are fixed by one shared matcher, `swerepo/globs.py`, with regression tests in `TestGeminiReviewRound2`. On the round-1 code, the P4-F10 tests fail three of five, and the P4-F11 timing test didn't finish in two minutes, so I stopped it. pytest: **496 passed** (17 new), also with `GITHUB_ACTIONS=true TERM=dumb`; ruff clean; 10 locked and 2 proposed rules pass.

#### P4-F10 · **Fix**
`_workspace_root` matches the member's relative path against `members` and `exclude` as text, through `globs.Glob`, and never calls `Path.glob`. `.` names the workspace root itself, `""` matches nothing, and a pattern starting with `/` is ignored. Test: `test_p4_f10_workspace_globs_never_crash` (`[".", "services/*"]`, `["services/**"]`, `[""]`, `["/services/*"]`, `["services/[ab]pi"]`).

#### P4-F11 · **Fix** (both, as you suggested)
`globs.Glob` drops empty and `.` parts and collapses repeated `**`. It compiles each folder-name part with `fnmatch.translate`, and walks the path one folder at a time through a set of positions in the glob, so the time is at most the path's length times the glob's. With `contents=True`, a glob that names a folder matches everything inside it, as `allow_paths` needs. `privacy.scan` compiles the globs once per scan. Tests: `test_p4_f11_globs_take_linear_time` (four globs, each on a 63-character name and a 40-folder path, under 0.5 s in all), `test_p4_f11_empty_and_dot_parts_are_dropped`, `test_p4_f11_an_empty_glob_allows_nothing`.

Ready for round 3.

---

### Round 3

#### Reviewer: verification

Re-ran every command under "How to run" and Round 3 probes against `swerepo/globs.py`, `swerepo/ci.py`, and `swerepo/privacy.py`:
- `uv sync` → clean (50 packages resolved, 47 audited).
- `uv run pytest` → **496 passed** in 59.88s; `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **496 passed** in 57.21s.
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (110 files formatted).
- `uv run seamspec verify --all` → **10 locked invariants passed**; `uv run seamspec verify --proposed inv_ab57c6ff --proposed inv_09cc1c20` → **2 proposed invariants passed**.
- `uv run swerepo init --only ci,security --dry-run` on this repository → `5 changes`, writes nothing.
- Scratch `demo` repository: 1st `init --yes --with-governance` → `17 changes`; 2nd `init --yes --with-governance` → `Nothing to do.`; `zizmor==1.32.0 --offline` → `0` findings; `check --only ci,security` → exit `0` (`0 missing, 0 changed by you, 0 outdated, 1 can't tell`).
- `globs.Glob` adversarial checks: `*********b` and `*a`×9 + `*b` now run in **0.03–0.16 ms** (down from 1.23 s and 0.31 s); `*a`×30 + `*b` on a 30-folder / 60-char path completes in **0.22 ms**; reversed/unclosed bracket expressions (`[z-a]`, `[unclosed`, `[]]`, `[!]`) compile and evaluate without raising.

#### Reviewer: response to developer responses

- **P4-F10 · Accept:** `ci._workspace_root` (`swerepo/ci.py:121-128`) now matches `base.relative_to(folder).as_posix()` purely in memory through `globs.Glob`, never calling `Path.glob`. `[".", "services/*"]`, `[""]`, `["/services/*"]`, trailing slashes, `./` prefixes, and character classes all behave cleanly without exceptions, covered by `test_p4_f10_workspace_globs_never_crash`.
- **P4-F11 · Accept:** `swerepo/globs.py` (`Glob` and `compile_all`, `lines 16-69`) normalizes `\`/`//`/`/./` segments, collapses adjacent `**`, translates each single-folder segment via `fnmatch.translate`'s atomic regexes, and walks path segments through an NFA state set in $O(\text{len(parts)} \times \text{len(path)})$ time with `contents=True` support for `allow_paths`; `privacy.scan` (`swerepo/privacy.py:135`) pre-compiles `allow_paths` once per scan, covered by `TestGeminiReviewRound2` in `tests/test_security.py:220-238`.

#### Reviewer: new findings

None.

#### Readiness summary

**Phase 4 is ready to close and merge.** All 11 findings across Rounds 1–2 (`P4-F01`–`P4-F11`) are **Accepted** with regression tests, and both proposed critical SeamSpec rules (`inv_ab57c6ff` and `inv_09cc1c20`) are ready for the owner's approval via `uv run seamspec review`.

### Closing

Round 3 found nothing new and accepted P4-F10 and P4-F11, so all 11 findings are accepted with regression tests. The review is closed.

- **Since Gemini's round 3 run:** the owner approved the three rules (Gemini's run saw 10 locked rules and 2 proposed). Now 13 rules are locked and all pass. `seamspec spec --check` is clean after regenerating `docs/EARNED_SPEC.md`, and `seamspec doctor` reports 0 errors and 0 warnings.
- **Final results:** pytest 496 passed; ruff clean; `swerepo check --base main` finds nothing missing.
- **Next:** the pull request for Phase 4, then a separate pull request that applies `ci` and `security` to this repository.

---

## Copilot's review of PR #8

Copilot left 8 inline comments. Each was reproduced on the PR's code before any change, and each is fixed, with a regression test in `TestCopilotReviewPR8` (`tests/test_init_ci.py`, `tests/test_security.py`). For four of the fixes I put the bug back and saw its test fail. pytest: 510 passed; ruff clean; 13 locked rules pass.

| Thread | Finding | Response |
|---|---|---|
| `swerepo/check.py` `workflow_jobs` | A comment at column 0 inside `jobs:` ended the jobs section, so later jobs were invisible to the `ci-ok` check | **Fix:** comment lines are skipped before the section is tracked (`test_a_comment_at_column_0_doesnt_end_jobs`) |
| `swerepo/init.py` `_listed_projects` | `--projects macos` made a second `test-macos` job | **Fix:** a folder whose jobs would take a fixed job's name is refused (`ci.FIXED_JOBS`) |
| `swerepo/check.py` `_python_matrix` | The first `python:` matrix anywhere counted as the root's, and listed projects' matrices were never compared | **Fix:** `check.job_blocks` reads the `test` job's matrix, and each listed project's `test-<name>` matrix is compared with that project's own `requires-python` (`ci.python-matrix:<folder>`) |
| `swerepo/ci.py` dependencies | Tools in an extra or a non-default group counted as installed | **Fix:** `ci.installed_dependencies` counts what `uv sync` installs: dependencies, default groups (`[tool.uv] default-groups`, else `dev`, with `dev-dependencies`), `include-group` followed |
| `swerepo/init.py` `_workflows` | A security-only run's recorded `python` decided the first CI workflow's versions | **Fix:** each workflow keeps its own snapshot; the privacy workflow records `privacy_python`, and the CI workflow's recorded inputs are read only while it is recorded |
| `swerepo/init.py` `_project_inputs` (tools) | A listed project missing pytest or ruff got no warning | **Fix:** each new project's jobs are checked against what `uv sync` installs in its folder, and the note names that folder |
| `swerepo/init.py` `_new_state` | Only folder names were recorded, so a project's jobs couldn't be rebuilt | **Fix:** each project's inputs are recorded under `[projects.inputs."<folder>"]` and used while the workflow is recorded; invalid recorded inputs are never used |
| `swerepo/privacy.py` Google key | `\b` at the end missed a key ending in `-` | **Fix:** a negative lookahead for another key character (Slack's pattern too) |

ADR-20261122-4a06 and spec §9 updated for the new recorded values.
