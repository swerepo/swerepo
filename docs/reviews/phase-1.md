# Code Review · Phase 1: Foundation

**Status:** closed · **Rounds:** 3 · **Developer:** Claude · **Reviewer:** Gemini · **Owner decides:** ties, merges, SeamSpec approvals
**Process:** ADR-20261119-9f87. Finding IDs `P1-F<nn>`; severities `blocker | should-fix | suggestion | question`; responses Fix / Push back / Defer, then Accept / Maintain.

---

## Developer summary

### Scope

The four modules every later command builds on, with no new command yet (Phase 2's `check` is their first user):

- **Fingerprints and marked blocks** (`swerepo/fingerprint.py`): whether a person edited what SWERepo wrote.
- **Templates** (`swerepo/render.py`): where bundled templates live, how they are versioned and rendered.
- **State** (`swerepo/state.py`): reading, validating and writing `.swerepo.toml`.
- **Detection** (`swerepo/detect.py`): what a repository already has (spec §10, §11), read-only.

Branch `phase-1/foundation`, uncommitted. Spec updated to v0.7.

### What to review

| Area | Files |
|---|---|
| Fingerprints, blocks | `swerepo/fingerprint.py`, `tests/test_fingerprint.py` |
| Templates | `swerepo/render.py`, `swerepo/templates/README.md`, `tests/test_render.py` |
| State file | `swerepo/state.py`, `tests/test_state.py` |
| Detection | `swerepo/detect.py`, `tests/test_detect.py` |
| Dependencies | `pyproject.toml` (`tomlkit`, `packaging`), `uv.lock` |
| ADRs | `docs/adr/ADR-20261120-9495-*`, `-b25a-*`, `-ecf7-*`, `-25b5-*`; `docs/adr/README.md` |
| Spec | `SWEREPO-SPEC.md` §8, §9, §11, Appendix A "0.6 → 0.7" |
| Proposed rules | `.seamspec/proposed/inv_7c5f3156/`, `inv_bee7349a/`, `inv_d8603926/` |
| Docs | `docs/PROGRESS.md`, `docs/progress/20261120-phase-1-foundation.md`, `CHANGELOG.md` |

### ADRs written

| ADR | Decision |
|---|---|
| ADR-20261120-9495 | Fingerprint = SHA-256 of normalised UTF-8 (surrogateescape, no BOM, LF, no trailing whitespace, one final newline); blocks found by HTML or `#` comment markers, named by a marker parameter; malformed blocks are errors naming the line; TOML sections deferred to Phase 4 |
| ADR-20261120-b25a | Templates at `templates/<component>/<name>/<version>[.<ext>]` (no `@` in file names); `@@name@@` placeholders, substitution only, string values, missing value = error; released versions never change; read with `importlib.resources` |
| ADR-20261120-ecf7 | `.swerepo.toml` via tomlkit; validated on load; unknown keys kept; save refused if a newer SWERepo or standard wrote it; atomic writes |
| ADR-20261120-25b5 | Detection read-only; files listed with `git ls-files -co --exclude-standard` (walk fallback); conventional non-project folders and `[projects] ignore`; Python versions via `packaging`; new runtime dependency `packaging` |

### How to run

```bash
uv sync
uv run pytest
GITHUB_ACTIONS=true uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run seamspec verify --all
uv run seamspec verify --proposed inv_7c5f3156
uv run seamspec verify --proposed inv_bee7349a
uv run seamspec verify --proposed inv_d8603926
uv run python -c "import json; from pathlib import Path; from swerepo.detect import detect; print(json.dumps(detect(Path('.')).to_dict(), indent=1))"
```

### Results (run by the developer on 2026-11-20, macOS, Python 3.14, uv 0.9.28)

- pytest: **123 passed** (116 new), also with `GITHUB_ACTIONS=true`.
- ruff check and format: clean. zizmor: no findings. `uv lock --check`: clean.
- Locked rules: 2 passed. Proposed rules: 3 verified.
- Built wheel: contains `swerepo/templates/README.md`; installed into a fresh environment, `TemplateStore()` finds its folder. `Requires-Dist`: packaging, tomlkit, typer.
- **Detection on this repository** (the last command above): not a monorepo; `tools/pypi-placeholder` skipped "under tools/" (the Phase 0 review's forward note); Python 3.11–3.14 from `requires-python`; `docs/adr` with 13 ADRs; agent files `AGENTS.md`, `CLAUDE.md`; host `claude`; linter ruff; SeamSpec present; `ci.yml` runs pytest and ruff; no errors.

### Design notes worth checking

1. **Fixture repositories are built inside each test** (`make()` and `git_init()` in `tests/test_detect.py`), not committed under `tests/fixtures/`. Committed fixtures would put `pyproject.toml` files in this repository (detection would then rely on its own `tests/` exclusion to stay correct here), and the privacy rule scans every tracked file.
2. **`git ls-files --cached --others --exclude-standard`, filtered to files that exist.** `--cached` alone misses new untracked files; `--others` alone misses tracked ones; deleted-but-tracked files are dropped by the existence check. Submodules (directories) drop out the same way.
3. **Editors are detected from folders on disk as well as listed files**, because `.vscode/` and `.agents/` are often git-ignored but still mean the editor is in use.
4. **A bug caught while dogfooding the state module:** `tomlkit.array(list)` parses its argument as TOML *text*; passing a Python list "worked" by turning it into `['a', 'b']`. Fixed (`array()` then `extend`), and a test checks the double-quoted output.
5. **`to_dict()` round-trips through JSON** so `--json` gets lists, not tuples; a test checks no absolute path appears.
6. **A collision with the locked privacy rule, caught before review.** The first template layout named files by template name, `@`, version and extension; the final privacy scan read each as an email address with the version and extension as its domain (`.md` is Moldova's real top-level domain), so the commit hook would have blocked Phase 1. Fixed by changing SWERepo, not the rule: one folder per template, one file per version (`docs/adr-template/1.md`), template ids unchanged (`docs/adr-template@1`). Recorded in ADR-20261120-b25a point 3 and its alternatives.
7. **The proposed rule tests are short** (SeamSpec warned about the 133-line privacy test in Phase 0): 16 to 25 lines each, standard library plus pytest plus `swerepo`.

### Known gaps and deliberate omissions

- **No command uses these modules yet**; `check` (Phase 2) is the first.
- **TOML sections** (`[sections."pyproject.toml"."tool.ruff"]`) aren't fingerprinted: deferred to Phase 4, which first writes them (ADR-20261120-9495 point 5). The state module doesn't model `[sections]` yet.
- **No real templates yet**: `swerepo/templates/` has only its README. Components add them from Phase 3.
- **Windows**: paths are handled as POSIX and CI has no Windows job (spec targets macOS and Linux); backslash and drive-letter paths are rejected in `.swerepo.toml`.
- **Nested repositories** are looked for two levels down only.
- **`[projects] ignore`** takes folder prefixes, not globs (ADR-20261120-25b5 point 4).

### Questions for the reviewer

1. **Default non-project folders** include `tools`, `docs` and `scripts`. Right trade-off, given a monorepo could have a real project under `tools/`? (The ADR's alternative was heuristics, which fail on this repository.)
2. **Python version rule:** a minor version counts as supported if the specifier allows `3.X.0` or `3.X.99`. Do you see a common specifier this gets wrong?
3. **State version guard:** a development build (`0.1.0.dev0`) refuses to save a file written by the release `0.1.0` (`Version` ordering). Acceptable, or should pre-releases of the same version be allowed?
4. **Template syntax** `@@name@@` with no conditionals: any template type you expect (workflow YAML, TOML, Markdown, JSON) where this will hurt?
5. **The three proposed rules**: the right behaviours to lock now, and anything that should be locked that isn't (for example "rendering fails on a missing value")?

### SeamSpec proposals waiting for the owner

| ID | Rule | Critical | Verified |
|---|---|---|---|
| inv_7c5f3156 | A fingerprint ignores whitespace-only differences and changes for any other edit | yes | passed |
| inv_bee7349a | Detection never writes to the repository it looks at | yes | passed |
| inv_d8603926 | Saving `.swerepo.toml` keeps comments and unknown keys; an older SWERepo never overwrites a newer one's file | no | passed |

The owner approves with `uv run seamspec review` after this review round.

---

## Round 1

### Reviewer: strengths

**Verification run (macOS, uv 0.9.28):** Ran all 10 commands in "How to run":
- `uv sync` → clean (50 packages resolved).
- `uv run pytest` and `GITHUB_ACTIONS=true uv run pytest` → **1 failed, 122 passed** (`tests/test_cli.py::test_help_reads_the_same_when_ci_forces_terminal_styling` failed because the runner environment sets `TERM=dumb`, suppressing Rich's ANSI codes; see `P1-F04`). All 116 new Phase 1 tests passed.
- `uv run ruff check .` and `uv run ruff format --check .` → clean (43 files), plus explicit `ruff check` and `ruff format --check` on `.seamspec/proposed/` → clean (3 files).
- `uv run seamspec verify --all` → 2 locked invariants passed; `uv run seamspec verify --proposed` on `inv_7c5f3156`, `inv_bee7349a`, and `inv_d8603926` → all 3 passed.
- `detect(Path('.')).to_dict()` → clean JSON output (`is_monorepo: false`, `tools/pypi-placeholder` skipped `"under tools/"`, 13 ADRs, Python `3.11`–`3.14`, `errors: []`). Also scanned all 66 tracked and untracked non-ignored files with `inv_62d51113`'s privacy logic → 0 findings.

- **`swerepo/render.py:51-65` and `ADR-20261120-b25a`:** Single-pass `PLACEHOLDER.sub` prevents double-expansion when values themselves contain `@@...@@` (`tests/test_render.py:49`), `@@name@@` avoids every YAML `${{ }}`, TOML `[[ ]]`, and shell `$VAR` collision without escaping, and switching to `templates/<component>/<name>/<version>[.<ext>]` eliminated the `.md`-TLD privacy false positive without weakening `inv_62d51113`.
- **`swerepo/state.py:111-130` and `tests/test_state.py:50-115`:** Clean `tomlkit` round-tripping (`array()` + `.extend()` avoiding single-quoted TOML arrays), `fsync` + mode-preserving atomic `os.replace` in `root`, and separating read-only loading from `save()`'s version guard.
- **`swerepo/fingerprint.py:18-35`:** Symmetric UTF-8 `surrogateescape` decode/encode gives deterministic SHA-256 fingerprints even on non-UTF-8 files without crashing, while preserving indentation and interior blank lines that carry meaning in YAML and Python.
- **`swerepo/detect.py:100-104` and `tests/test_detect.py:18-33`, `:231-242`:** Building fixture repos in `tmp_path` keeps dogfooding (`test_this_repository`) honest, and returning `SkippedProject(path, reason)` makes conventional and configured project exclusions visible rather than silent.
- **`.seamspec/proposed/` (`inv_7c5f3156`, `inv_bee7349a`, `inv_d8603926`):** Tight 17–24 line harnesses testing public contracts rather than private helpers, all Ruff-clean.

### Reviewer: findings

#### P1-F01 · blocker · `swerepo/detect.py:50`
**Problem:** `PROJECT_FILES` (`line 50`) recognizes only `pyproject.toml`, `setup.py`, and `package.json`, and `_languages()` (`line 330`) inspects only `{p.path for p in projects} | {"."}`. This breaks two spec requirements:
1. **Polyglot monorepos (spec §11 `line 441`):** Subprojects in other languages that `LANGUAGE_MARKERS` (`lines 54-55`) already knows (`go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle`, `build.gradle.kts`, `Gemfile`, `tsconfig.json`) are never added to `projects`, do not set `is_monorepo = True`, and are omitted from `languages` when below `.`, so `check` and `init` cannot flag uncovered project roots (`✗ gateway/ not covered by any required check`). Also, a TypeScript root (`package.json` + `tsconfig.json`) is typed `"javascript"` instead of `"typescript"`.
2. **Python projects without `pyproject.toml` or `setup.py` (spec §10 `line 402`):** Projects using `setup.cfg`, `requirements*.txt`, `Pipfile`, `poetry.lock`, or `uv.lock` alone get `projects = ()` (indistinguishable from an empty folder, and invisible as a monorepo subfolder) even though spec §10 lists them as Python project-type markers.
**Scenario:** (1) A repository has `pyproject.toml` at `.` and a Go service at `gateway/go.mod` → `detect()` returns `is_monorepo=False`, `projects=(ProjectRoot('.', 'python'),)`, `languages=('python',)` — silently hiding `gateway/` from required-check coverage. (2) An existing Python service with `requirements.txt` + `app.py` (or `setup.cfg` alone) → `detect().projects` is `()`.
**Recommendation:** Expand project-root detection to cover the other root manifests (`setup.cfg`, `Pipfile`, `poetry.lock`, `uv.lock`, and `requirements*.txt` for Python; `go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle`, `build.gradle.kts`, `Gemfile` for other languages; and `"typescript"` when `tsconfig.json` accompanies `package.json` or stands alone), and add tests for a Python+Go/TS monorepo and a `requirements.txt`/`setup.cfg`-only Python repo.

#### P1-F02 · blocker · `swerepo/fingerprint.py:67`
**Problem:** Three marker-parsing bugs in `find_block()`:
1. **UTF-8 BOM on line 1 (`line 78`):** Unlike `normalise()` (`line 23`), `find_block()` does not strip a leading UTF-8 BOM (`\ufeff`). Because `\ufeff` is Unicode category `Cf` (not `\s`), a marker on line 1 of a BOM-prefixed file misses `begin_re`, causing the closing marker to raise `BlockError`.
2. **Greedy HTML comment match (`line 68`):** `rf"^\s*<!--\s*{name}(?:\s.*)?-->\s*$"` lets `.*` span across `-->`, so a line like `<!-- swerepo:begin --> real user text <!-- note -->` matches as a pure marker line, silently hiding/dropping `real user text` when the block is fingerprinted or replaced.
3. **Markdown fenced code blocks (`lines 81-94`, `style=HTML`):** `find_block()` matches markers inside fenced code blocks (` ``` ` / ` ~~~ `), so any documentation example of `<!-- swerepo:begin -->` in `AGENTS.md`, `CONTRIBUTING.md`, or `docs/adr/README.md` raises `BlockError`.
**Scenario:** (1) `find_block("\ufeff<!-- swerepo:begin -->\nrule\n<!-- swerepo:end -->\n", style=HTML)` → raises `BlockError("line 3: `swerepo:end` without a `swerepo:begin` before it")` while `fingerprint()` treats the BOM as unedited. (2) An `AGENTS.md` or `docs/adr/README.md` includes a fenced ` ```markdown ` example showing `<!-- swerepo:begin -->` above the real block → `find_block()` raises `BlockError("a second `swerepo` block")`.
**Recommendation:** Strip `_BOM` at the start of `find_block()`, forbid `-->` inside the optional HTML marker note (`(?:\s(?:(?!-->).)*)?`), ignore lines inside Markdown fenced code blocks (` ``` ` / ` ~~~ `) when `style == HTML` and `begin is None`, and add tests for all three cases.

#### P1-F03 · should-fix · `swerepo/state.py:256`
**Problem:** `ADR-20261120-ecf7` (points 3–4 and Consequence 2) requires `State.load()` to succeed on files written by a newer SWERepo or newer standard so Phase 2's `check` can inspect `written_by_newer()` and report `"can't tell: upgrade SWERepo"`, refusing only on `save()`. However, `_validate()` unconditionally rejects unknown component names (`_check_components`, `line 256`) and unknown `mode` strings (`line 257`) during `load()`/`parse()`, before considering `standard > SUPPORTED_STANDARD` or `Version(version) > Version(__version__)`. In addition:
- `State.load()` (`line 98`) does not catch `UnicodeDecodeError` or `OSError` (unlike `detect.py:253`), leaking raw exceptions instead of `StateError`;
- `check_path()` (`line 52`) accepts unnormalised double slashes (`"docs//adr/TEMPLATE.md"`, because `PurePosixPath.parts` collapses `//`) and NUL bytes (`"\x00"`).
**Scenario:** SWERepo `0.3.0` (or `standard = 2`) introduces an optional `"hooks"` component (spec §20) and writes `standard = 2`, `swerepo = "0.3.0"`, `components = ["docs", "hooks"]` → a teammate or CI run on SWERepo `0.1.0` calls `State.load(root)` → raises `StateError: .swerepo.toml: components: unknown component 'hooks'` instead of loading so `check` can report "upgrade SWERepo".
**Recommendation:** When `standard > SUPPORTED_STANDARD` or `Version(version) > Version(__version__)` in `_validate()`, check types (`list` of `str`, `str`) without rejecting unknown future `components` or `mode` values (keep strict membership checks for current/older versions and in `set_components`/`set_mode`); catch `(OSError, UnicodeDecodeError)` in `State.load()` as `StateError`; reject `"//" in path or "\x00" in path` in `check_path()`; and test loading + refusing `save()` on a newer state file that lists an unknown future component (in `test_state.py` and `inv_d8603926`).

#### P1-F04 · should-fix · `tests/test_cli.py:40`
**Problem:** `test_help_reads_the_same_when_ci_forces_terminal_styling` failed during review (`1 failed, 122 passed`). `env = {**os.environ, "GITHUB_ACTIONS": "true"}` inherits `TERM=dumb` (or `NO_COLOR`) from the parent process; Rich suppresses ANSI escape sequences when `TERM=dumb` or `NO_COLOR` is present even if `GITHUB_ACTIONS=true`, failing `assert "\x1b[" in completed.stdout` on line 45.
**Scenario:** Running `uv run pytest` inside any non-interactive runner, agent sandbox, cron job, or shell where `TERM=dumb` or `NO_COLOR=1` → `AssertionError` at `tests/test_cli.py:45`.
**Recommendation:** Keep `assert "\x1b[" in completed.stdout` intact, and construct `env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"} | {"GITHUB_ACTIONS": "true", "TERM": "xterm-256color"}` in `tests/test_cli.py:40`.

#### P1-F05 · should-fix · `swerepo/detect.py:389`
**Problem:** Two brownfield detection issues:
1. **False `"vscode"` host from `.github/copilot-instructions.md` (`line 389`):** `_hosts()` maps `.github/copilot-instructions.md` to `"vscode"`. However, SWERepo's `github` component creates `.github/copilot-instructions.md` in *every* repository for GitHub.com PR code review (spec §6.1 `line 145`), regardless of editor. Treating it as VS Code will make `detect()` (and `seamspec init --hosts` in spec §13) report `"vscode"` on Claude-only repositories as soon as `github` is applied. (SeamSpec's own `hosts.py` checks `.vscode/` only for VS Code, and checks both `.agents/` and `.agent/` for Antigravity.)
2. **Missing `setup.cfg` / `tox.ini` linter sections (`lines 421-424`, spec §6.3 `line 170`):** `_linters()` checks INI files only for `[flake8]` and `[isort]`, missing `[tool:isort]` (isort's standard `setup.cfg` section name) and `[pylint]` / `[pylint.*]` (`[pylint.messages_control]`, `[pylint.main]`, etc.).
**Scenario:** (1) A Claude-only repository runs `swerepo init --only github` (adding `.github/copilot-instructions.md`), then `detect()` → `hosts` becomes `("claude", "vscode")`. (2) A legacy repo with `[tool:isort]` and `[pylint.messages_control]` in `setup.cfg` → `detect().linters` is `()`.
**Recommendation:** Detect `"vscode"` from `(root / ".vscode").is_dir()` only (leaving `.github/copilot-instructions.md` in `agent_files`, and optionally adding `(root / ".agent").is_dir()` for Antigravity); in `_linters()`, recognize `[tool:isort]` and `[pylint]` / `[pylint.*]` sections in `setup.cfg` and `tox.ini` (plus `.pytest.ini` in `_pytest_configured`), with tests for both.

#### P1-F06 · should-fix · `swerepo/detect.py:268`
**Problem:** `_supported()` probes only `3.X.0` and `3.X.99` (`line 270`). Specifiers that pin a patch version (`==3.11.4`, common in deployed Python services) or bound patches within a minor series (`>=3.12.1,<3.12.8`, `!=3.11.0,>=3.11,<3.11.5`) exclude both `.0` and `.99` and return `versions = ()`. Also, `_git_files()` (`line 212`) does not check `result.returncode == 0`, silently returning `[]` instead of falling back to `_walk_files()` if `git ls-files --others --exclude-standard` exits non-zero, and `_under()` (`line 299`) returns `True` for every path if `ignore` ever contains `""` or `"."`.
**Scenario:** `pyproject.toml` has `requires-python = "==3.11.4"` (or `">=3.12.1,<3.12.8"`) → `detect().python.versions` returns `()`.
**Recommendation:** Probe patches `(*range(30), 99)` per minor in `KNOWN_PYTHONS` (217 micro-checks, < 0.5 ms), fall back to `_walk_files()` when `_git_files()` sees a non-zero exit code, guard empty/`"."` entries in `_under()`, and add `==3.11.4` and `>=3.12.1,<3.12.8` to `test_python_versions_from_requires_python`.

#### P1-F07 · suggestion · `swerepo/render.py:18`
**Problem:** `TEMPLATE_ID`, `_VERSION_FILE` (`render.py:18-19`), and `_CLASSIFIER` (`detect.py:76`) use `.match(...)` with `$`, which in Python matches before a trailing `\n` (`parse_id("docs/adr-template@1\n")` succeeds). Also, `docs/progress/20261120-phase-1-foundation.md:8` still writes the pre-fix `templates/<component>/<name>@<version>[.<ext>]` path instead of `<name>/<version>[.<ext>]`.
**Scenario:** `State.parse` accepts `template = "docs/adr-template@1\n"` with a trailing newline; readers of the Phase 1 progress note see the superseded `@` file naming.
**Recommendation:** Use `.fullmatch(...)` (or `\Z`) on `TEMPLATE_ID`, `_VERSION_FILE`, and `_CLASSIFIER`, and change `@` to `/` in `docs/progress/20261120-phase-1-foundation.md:8`.

### Reviewer: answers to questions

1. **Default non-project folders (`tools`, `docs`, `scripts`, …):** **Right trade-off.** Heuristics fail on `tools/pypi-placeholder/` right here, whereas conventional directory names plus `SkippedProject(path, reason)` are predictable and transparent. One clean escape hatch for Phase 3 (`swerepo init --projects`): if a monorepo genuinely ships a project under `tools/cli`, let an explicit `--projects tools/cli` (`[projects] listed`) override `NON_PROJECT_DIRS` without needing a new config key. *(Also note for Phase 2/3: `_nested_repos` runs even when `git.is_toplevel` is `True`, so git submodules or `.worktrees/*` appear in `nested_repos`; only treat `nested_repos` as "wrong parent folder, refuse to run" when `not git.is_work_tree`.)*
2. **Python version rule (`3.X.0` or `3.X.99`):** Exact patch pins (`==3.11.4`) and mid-minor ranges (`>=3.12.1,<3.12.8`, `!=3.11.0,>=3.11,<3.11.5`) fail both `.0` and `.99` and return `()`. Probing `(*range(30), 99)` fixes all of them cheaply; see `P1-F06`.
3. **State version guard (`0.1.0.dev0` vs `0.1.0`):** **Keep strict PEP 440 `Version` ordering.** Once `0.1.0` ships, development immediately moves to `0.1.1.dev0` or `0.2.0.dev0` (both `> 0.1.0`), so `0.1.0.dev0` meeting a `0.1.0` file genuinely is an older pre-release build and should not overwrite `0.1.0`. Just fix `_validate()` (`P1-F03`) so newer files with new component names still *load* cleanly for `check`.
4. **Template syntax (`@@name@@`, no conditionals):** Safe across workflow YAML, TOML, Markdown, JSON, unified diffs (`@@ -1,3 +1,4 @@` doesn't match `[a-z]`), and `inv_62d51113` (`@@` never matches a single-`@` email). Two small guidelines for Phase 3–5 template authors: (i) keep multi-line YAML block placeholders at column 0 (`@@lint_job@@`) so lines 2..N don't lose indentation; (ii) build structured JSON (`ruleset.json`, `repo-settings.json`) with separate `solo`/`team` templates or `json.dumps` in Python rather than interpolating non-string arrays/booleans via `@@...@@`.
5. **The three proposed SeamSpec rules:** **Right three behaviours to lock**—they cover the real user-safety boundaries (no silent overwrite of edited files, read-only detection, non-destructive state saves) without bloating every Stop/commit hook with unit-level checks like missing template values (`tests/test_render.py` covers those in CI). Hold off on `seamspec review` until Round 1 fixes land (in particular updating `state.py` / `inv_d8603926` for `P1-F03`).

### Developer responses

An excellent review. Before answering, every finding was reproduced in one script against the code as reviewed: all seven reproduce exactly as described (BOM and fenced markers raise, the greedy marker matches, a newer state file with a new component fails to load, `==3.11.4` gives no versions, `parse_id` accepts a trailing newline, a Go service is invisible, a requirements-only project has no root, `copilot-instructions.md` gives `vscode`, `[tool:isort]` and `[pylint.*]` are missed, and the CLI test fails under `TERM=dumb`). The same script found one more: `check_path(".")` was accepted (fixed under P1-F03).

#### P1-F01 · **Fix**, with one refinement
Project roots now come from every manifest SWERepo knows (`swerepo/detect.py` `PYTHON_MANIFESTS`, `OTHER_MANIFESTS`, `_manifest_kind`): Python (`pyproject.toml`, `setup.py`, `Pipfile`), TypeScript (`tsconfig.json`, which wins over `package.json` in the same folder), JavaScript, Go, Rust, Java (Maven and Gradle) and Ruby; a folder with several kinds is named by `KIND_ORDER`.

**Refinement:** `setup.cfg` and `requirements*.txt` make a *sub-folder* a project only when the folder also holds `.py` files; at the repository root they always count. On their own they are often configuration (`ci/requirements.txt` for tox, `deploy/setup.cfg` for flake8), and counting them would invent monorepos. `uv.lock` and `poetry.lock` are not markers: they never appear without `pyproject.toml`. Tests: `test_a_polyglot_monorepo` (Python root + Go, TypeScript, Rust, Java, Ruby), `test_python_projects_without_pyproject` (requirements + source, `setup.cfg` + source, `Pipfile`; `ci/requirements.txt` and `deploy/setup.cfg` are not projects), `test_a_requirements_only_repository_is_a_python_project`. ADR-20261120-25b5 point 3 and spec §11 updated.

#### P1-F02 · **Fix** (all three)
`swerepo/fingerprint.py` `find_block`: a leading BOM is removed first; an HTML marker's note can't contain `-->` and the whole stripped line must be the marker (`fullmatch`), so `<!-- swerepo:begin --> text <!-- x -->` is not a marker; in HTML style, lines inside fenced code blocks (CommonMark: 3+ backticks or tildes, indented at most 3 spaces, closed by the same character, at least as long, with no info string) are skipped. Seven new tests, including a fence *inside* the block (kept as content), a fence that doesn't close (` ```python ` inside a ` ``` ` fence, `~~~` inside backticks), and fences meaning nothing in hash-style files. ADR-20261120-9495 point 3 updated.

#### P1-F03 · **Fix** (all four parts)
- `swerepo/state.py` `_validate(doc, running)`: for a file whose `standard` is newer than supported or whose `swerepo` version is newer than the running one, components and mode are type-checked only, so `check` can load it and report "upgrade SWERepo"; files from this or older versions stay strict, and the setters always are. `State.parse` and `State.load` take `running` (default: the installed version) so this is testable.
- `State.load` turns `OSError` and `UnicodeDecodeError` into `StateError`.
- `check_path` rejects empty parts (`a//b`), `.` and `..` parts, `.` alone (the extra bug), and control characters including NUL.
- Proposed rule **inv_d8603926 updated** to lock the new behaviour too: a newer file naming an unknown component loads, and the older SWERepo still refuses to save over it. (The first re-proposal was rejected for a title over 120 characters and the developer's `grep` hid the error; caught by checking the proposed file's content, then re-proposed and re-verified.)

Tests: newer file with unknown component and mode loads and isn't overwritten; older file with unknown component is still an error; newer file with the wrong types is still an error; unreadable file; and five new path and template-id cases.

#### P1-F04 · **Fix**
`tests/test_cli.py`: the styled-help test drops `NO_COLOR` and `TERM` from the inherited environment and sets `TERM=xterm-256color`; the "styling is really on" assertion stays. Reproduced first (fails with `TERM=dumb`); now passes under `TERM=dumb`, `NO_COLOR=1`, `GITHUB_ACTIONS=true` and a plain environment.

#### P1-F05 · **Fix** (both)
`_hosts`: `vscode` only from `.vscode/` (on disk or listed); `.github/copilot-instructions.md` stays in `agent_files` but no longer suggests an editor, since SWERepo's own `github` component writes it. Antigravity also from `.agent/`, as SeamSpec's `hosts.py` does. `_linters` reads every section of `setup.cfg` and `tox.ini`: `[flake8]`, `[isort]`, `[tool:isort]`, `[pylint]` and `[pylint.*]`; `.pytest.ini` counts as pytest configuration. Tests added for each.

#### P1-F06 · **Fix** (all three)
`_supported` probes patches 0–29 and 99 per minor version (`_PATCHES`); `==3.11.4`, `>=3.12.1,<3.12.8` and `!=3.11.0,>=3.11,<3.11.5` added to the parametrised test. `_git_files` returns `None` on a failed `git ls-files`, and `detect` falls back to the walk with `listed_by = "walk"` (test with a monkeypatched failure). `_under` returns `False` for `""` and `"."` (test: `ignore=["", "."]` skips nothing).

#### P1-F07 · **Fix**
`fullmatch` for `TEMPLATE_ID` (in `render.py` and in `state.py`'s record check), `_VERSION_FILE` and `_CLASSIFIER`; a trailing-newline template id is now a test case. The progress entry's stale `@` layout corrected.

#### Answers to questions: taken
- **Q1:** the `--projects` override for a real project under `tools/` is noted for Phase 3 (it's `init`'s flag). The submodule and worktree note on `nested_repos` is right: Phase 2's `check` will treat nested repositories as "wrong folder" only when the folder isn't itself a work tree. Both recorded in `docs/PROGRESS.md`.
- **Q2:** fixed as P1-F06.
- **Q3:** keeping strict ordering, as you recommend.
- **Q4:** both guidelines (column-0 placeholders for multi-line YAML; build structured JSON in Python or use per-variant templates) added to `swerepo/templates/README.md`.
- **Q5:** agreed; the three rules stay as the safety boundaries, with inv_d8603926 extended for P1-F03.

### Checks after the fixes (developer, 2026-11-20)

pytest **152 passed** (29 new), also with `GITHUB_ACTIONS=true TERM=dumb` · ruff check and format clean · zizmor no findings · `uv lock --check` clean · locked rules 2 passed · proposed rules 3 verified (inv_d8603926's new test confirmed in place) · detection on this repository unchanged (not a monorepo, host `claude` only, ruff, no errors) · privacy rule over all 66 files: no findings.

---

## Round 2

### Reviewer: response to developer responses

**Verification run (macOS, uv 0.9.28):**
- `uv run pytest` → **152 passed** in 2.07s (up from 123 in Round 1; 0 failures).
- `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **152 passed** in 1.90s (`P1-F04` confirmed fixed under a dumb terminal).
- `uv run ruff check .` and `uv run ruff format --check .` → clean (43 files); `.venv/bin/ruff check . .seamspec/proposed/` and `.venv/bin/ruff format --check . .seamspec/proposed/` → clean (46 files).
- `uv run seamspec verify --all` → 2 locked invariants passed.
- `uv run seamspec verify --proposed inv_7c5f3156`, `inv_bee7349a`, and `inv_d8603926` → all 3 passed (verified `inv_d8603926`'s updated assertion and `from-the-future` component test are in place).
- Re-ran all Round 1 reproduction scenarios in an independent script against the updated modules (polyglot Python+Go monorepo, `requirements.txt`-only root project, BOM on line 1, greedy HTML marker comment, fenced Markdown marker example, newer `.swerepo.toml` naming an unknown `"hooks"` component and `"pair"` mode, `.github/copilot-instructions.md` host check, `setup.cfg` `[tool:isort]`/`[pylint.*]` + `.pytest.ini`, `requires-python = "==3.11.4"`, and trailing-newline template IDs) → all passed.

- **P1-F01 · Accept (including the refinement in principle; see `P1-F08` for one package-layout gap in its subfolder check).** The developer's refinement is well-reasoned and better than counting bare configuration files unconditionally: `uv.lock` and `poetry.lock` never exist without `pyproject.toml`, and requiring Python source alongside `setup.cfg` or `requirements*.txt` in subfolders prevents `ci/requirements.txt` or `deploy/setup.cfg` from turning single-project repositories into false monorepos while still counting them at `.`. Polyglot manifests, `KIND_ORDER` (`typescript` winning over `javascript` when `tsconfig.json` accompanies `package.json`), `ADR-20261120-25b5`, and `SWEREPO-SPEC.md` §11 are all cleanly aligned. (One bug in how `python_source` checks for `.py` files in subfolders is filed below as `P1-F08`.)
- **P1-F02 · Accept (with one CommonMark inline-backtick edge case in the new fence check filed as `P1-F09`).** Stripping `_BOM`, anchoring single-comment HTML markers with `(?:(?!-->).)*` + `fullmatch`, and tracking code fences in HTML mode fix all three Round 1 scenarios cleanly, and keeping fences inside an open `swerepo` block as block content (`tests/test_fingerprint.py:176`) is the right behaviour.
- **P1-F03 · Accept.** Relaxing component and mode membership checks to type checks when `newer` is true while keeping current/older files and setters strict satisfies `ADR-20261120-ecf7` cleanly; `State.load` now wraps `OSError` and `UnicodeDecodeError` in `StateError`, `check_path` catches empty/`. `/`..` parts (including `"."` alone, good catch) and control characters, and `inv_d8603926` now locks the newer-version load + no-overwrite contract. (One minor short-circuit detail on `swerepo/state.py:261` is noted as `P1-F10`.)
- **P1-F04 · Accept.** Filtering `NO_COLOR` and `TERM` and setting `TERM=xterm-256color` keeps `assert "\x1b[" in completed.stdout` meaningful and passes under both `uv run pytest` and `GITHUB_ACTIONS=true TERM=dumb uv run pytest`.
- **P1-F05 · Accept.** Restricting `"vscode"` to `.vscode/`, adding `.agent/` for Antigravity, normalizing `[tool:isort]` and `[pylint.*]` in `setup.cfg` / `tox.ini`, and checking `.pytest.ini` all work as expected and match `tests/test_detect.py:285-309`.
- **P1-F06 · Accept.** Probing `_PATCHES = (*range(30), 99)`, returning `None` from `_git_files` on non-zero `git ls-files` exit so `detect()` falls back to `_walk_files` with `listed_by="walk"`, and guarding empty/`"."` entries in `_under` resolve all three cases with tests.
- **P1-F07 · Accept.** `fullmatch` is used across `TEMPLATE_ID`, `_VERSION_FILE`, and `_CLASSIFIER`, tested via `State.parse` in `tests/test_state.py:144`, and `docs/progress/20261120-phase-1-foundation.md:8` is updated.
- **Answers to Round 1 questions:** Confirmed recorded in `docs/PROGRESS.md` (`nested_repos` work-tree rule for Phase 2, `--projects` override for Phase 3) and `swerepo/templates/README.md` (column-0 multi-line placeholders and structured JSON guidance).

### Reviewer: new findings

#### P1-F08 · should-fix · `swerepo/detect.py:326`
**Problem:** `python_source = {PurePosixPath(name).parent.as_posix() for name in files if name.endswith(".py")}` records only the *immediate* parent directory of each `.py` file. In Python monorepos, subprojects configured with `setup.cfg` (`[options]\npackages = find:`) or `requirements.txt` routinely place their `.py` files inside a package or `src/` directory (`services/legacy/legacy/__init__.py`, `services/legacy/src/legacy/core.py`, `services/worker/app/main.py`) with no flat `.py` file directly beside the manifest. Because `"services/legacy"` and `"services/worker"` are not immediate parents of `.py` files, `key in python_source` (`line 333`) evaluates to `False` and those subprojects are missed. *(Minor adjacent note: `ProjectRoot.kind`'s comment at `swerepo/detect.py:106` still says `# "python" or "javascript"`.)*
**Scenario:** A repository has `pyproject.toml` at `.`, a Celery service at `services/worker/requirements.txt` + `services/worker/worker/tasks.py`, and a legacy package at `services/legacy/setup.cfg` + `services/legacy/src/legacy/core.py` → `detect()` returns `projects=(ProjectRoot(path='.', kind='python'),)` and `is_monorepo=False`, missing both subprojects.
**Recommendation:** Include ancestor folders of `.py` files (excluding `.py` files inside `NON_PROJECT_DIRS` so e.g. `ci/requirements.txt` + `ci/scripts/lint.py` stays excluded):
`python_source = {parent.as_posix() for name in files if name.endswith(".py") and not (set(PurePosixPath(name).parts) & NON_PROJECT_DIRS) for parent in PurePosixPath(name).parents}`. That still excludes bare `ci/requirements.txt`, `deploy/setup.cfg`, and `requirements/prod.txt` while detecting package- and `src/`-layout subprojects. Add a package/`src/`-layout subfolder case to `test_python_projects_without_pyproject`, and update the `swerepo/detect.py:106` comment.

#### P1-F09 · should-fix · `swerepo/fingerprint.py:90`
**Problem:** In CommonMark (§4.5), the info string of a backtick code fence (`mark[0] == "`"`) may not contain any backtick characters—otherwise inline code spans delimited by three or more backticks (the standard Markdown way to write inline code containing `` ` `` or literal delimiters, e.g. `` ``` `swerepo check` ``` `` or `` ```@@name@@``` ``) would be misread as opening fences. Currently `_FENCE.match(line)` (`line 90`) opens `fence = mark` (`line 93`) even when the rest of the line contains closing backticks, leaving `fence` open to EOF so `find_block()` silently skips the real `swerepo` block below and returns `None`.
**Scenario:** `AGENTS.md` contains `` ```@@name@@``` placeholders are replaced once. `` on line 1 followed by `<!-- swerepo:begin -->\nrule\n<!-- swerepo:end -->\n` → `find_block(..., style=HTML)` returns `None` instead of `Block(begin_line=3, end_line=5, content="rule\n")` (which would cause `check` to report the block missing and `init` to append a duplicate block).
**Recommendation:** When `fence is None`, open a fence only when `mark[0] != "`" or "`" not in line[opening.end():]` (and `continue` only when a fence actually opens or closes), and add a test with a triple-backtick inline code span at the start of a line above a marked block.

#### P1-F10 · suggestion · `swerepo/state.py:261`
**Problem:** In `newer = standard > SUPPORTED_STANDARD or _version(version, key="swerepo") > Version(running)`, Python's `or` short-circuits when `standard > SUPPORTED_STANDARD`, skipping `_version(version, key="swerepo")` so an invalid `swerepo` version string is accepted without raising `StateError` (`ADR-20261120-ecf7` point 2).
**Scenario:** `State.parse('standard = 2\nswerepo = "not-a-version"\ncomponents = ["docs"]\n', running="0.1.0")` succeeds with `state.swerepo_version == "not-a-version"` instead of raising `StateError`.
**Recommendation:** Compute `parsed_version = _version(version, key="swerepo")` before the `or` expression so `swerepo` is always validated as a PEP 440 version regardless of `standard`, and add a test case.

### Readiness summary

- **Proposed SeamSpec rules (`inv_7c5f3156`, `inv_bee7349a`, `inv_d8603926`):** **Ready for the owner to approve** (`uv run seamspec review`). Their assertions, scopes, and harnesses are complete, Ruff-clean, and verified, and none of `P1-F08`–`P1-F10` require changing any of the three proposed rule tests (wait until `P1-F08`–`P1-F10` are addressed before running `seamspec review` if you want one clean final pass before committing).
- **Can Phase 1 close?** **Not yet** — two small `should-fix` edge cases (`P1-F08` and `P1-F09`, ~5 lines of code total, plus `P1-F10` if taken) remain in the Round 2 additions. Once addressed and verified in Round 3, Phase 1 can close.

### Developer responses

All seven round 1 resolutions accepted, the refinement included. The three new findings are right, and all three are holes in the developer's round 1 fixes; each was reproduced before fixing (worker and legacy services missing, the inline-code line hiding the block, `not-a-version` accepted).

#### P1-F08 · **Fix**
`swerepo/detect.py` `_projects`: `python_source` now holds every ancestor folder of a `.py` file, except files under a conventional non-project folder, exactly as recommended. Package layout (`services/worker/worker/tasks.py`) and `src/` layout (`services/legacy/src/legacy/core.py`) now make their folders projects; `ci/requirements.txt` with `ci/scripts/lint.py` still doesn't. All three added to `test_python_projects_without_pyproject`. The `ProjectRoot.kind` comment lists every kind. ADR-20261120-25b5 point 3 and spec §11 reworded ("Python source in the folder or below it").

#### P1-F09 · **Fix**
`swerepo/fingerprint.py` `find_block`: a backtick run opens a fence only if no backtick follows it on the line (CommonMark §4.5); a tilde fence may still have backticks in its info string. The `continue` now happens only when a fence opens or closes. Tests: the inline-code line above a block (block found on line 2), and a tilde fence with `` `example` `` in its info string still hiding an example marker.

#### P1-F10 · **Fix**
`swerepo/state.py` `_validate`: the version is parsed before the "newer" check, so it is always validated. Test: `standard = 2` with `swerepo = "not-a-version"` raises.

### Checks after round 2 (developer, 2026-11-20)

pytest **155 passed** (also with `GITHUB_ACTIONS=true TERM=dumb`) · ruff check and format clean · zizmor no findings · locked rules 2 passed · proposed rules 3 verified (unchanged, as you noted none needed changes) · detection on this repository unchanged · the three round 2 scenarios re-run: both services found, block found on line 2, invalid version rejected · privacy rule over all 66 files: no findings.

---

## Round 3

Scope: P1-F08, P1-F09 and P1-F10 only. Everything else was accepted in round 2.

### Reviewer

**Verification run (macOS, uv 0.9.28):**
- `uv run pytest` → **155 passed** in 1.99s (0 failures).
- `.venv/bin/ruff check . .seamspec/proposed/` and `.venv/bin/ruff format --check . .seamspec/proposed/` → clean (46 files).
- Re-ran all three Round 2 scenarios in an independent script (`services/worker/requirements.txt` + `services/worker/worker/tasks.py`, `services/legacy/setup.cfg` + `services/legacy/src/legacy/core.py`, and `ci/requirements.txt` + `ci/scripts/lint.py`; `` ```@@name@@``` `` inline code span above `<!-- swerepo:begin -->`; and `standard = 2` with `swerepo = "not-a-version"`) → all passed.

**Responses to Round 2 fixes:**
- **P1-F08 · Accept.** `python_source` (`swerepo/detect.py:328-333`) now collects ancestor folders of `.py` files outside `NON_PROJECT_DIRS`, detecting both package and `src/` subfolder layouts while keeping `ci/requirements.txt` + `ci/scripts/lint.py` excluded (`tests/test_detect.py:161-177`). `ProjectRoot.kind`'s comment (`swerepo/detect.py:106`) and `ADR-20261120-25b5` point 3 are updated.
- **P1-F09 · Accept.** `find_block` (`swerepo/fingerprint.py:92-99`) checks CommonMark §4.5's no-backtick info-string rule for backtick fences (`mark[0] != "`" or "`" not in line[opening.end():]`), preserves backticks in tilde fence info strings, and `continue`s only when a fence opens or closes (`tests/test_fingerprint.py:180-188`).
- **P1-F10 · Accept.** `_validate` (`swerepo/state.py:261-262`) parses `written_by = _version(version, key="swerepo")` before the `standard > SUPPORTED_STANDARD` check, tested in `tests/test_state.py:174-176`.

**New findings:** None.

**Readiness:** All 10 findings (`P1-F01`–`P1-F10`) are resolved and verified. The three proposed SeamSpec rules (`inv_7c5f3156`, `inv_bee7349a`, `inv_d8603926`) are ready for owner approval (`uv run seamspec review`), and **Phase 1 can close**.

### Developer responses

Accepted with thanks: no open findings.

## Outcome

**Closed on 2026-11-20 after three rounds.** 10 findings (2 blockers, 6 should-fix, 2 suggestions): all fixed, every one reproduced against the code before fixing. One refinement (P1-F01: `setup.cfg` and `requirements*.txt` count in sub-folders only with Python source) accepted by the reviewer. No "Owner decides" items. One extra bug found by the developer while reproducing (`check_path(".")`), fixed under P1-F03. Tests went from 123 to 155.

### After the review: rule tests strengthened (owner decision)

Before approving, the owner asked SeamSpec's own reviewer (a separate agent that didn't write the rules) to explain the three proposals. It recommended changes to all three, and the owner chose to strengthen them. Code was not changed; only the proposed rule tests:

- **inv_7c5f3156 (fingerprints):** the rule's wording now names every ignored difference, including the byte-order mark the code (and ADR-20261120-9495) already ignored but the first wording left out. Added cases: lone CR line endings, trailing tabs and spaces on several lines, bytes, a BOM with CRLF as bytes; tabs for spaces, a blank line inside, a deleted line.
- **inv_bee7349a (detection is read-only):** runs both with git and on a folder that isn't a repository (the walk path), with a workflow, `.pre-commit-config.yaml`, `setup.cfg`, `tox.ini`, an ADR and a nested repository, so every file read is exercised.
- **inv_d8603926 split in two:** inv_d8603926 now covers only "comments and unknown keys survive" (own-line and end-of-line comments, an unknown top-level key, an unknown table, with values checked); the new **inv_070db19c** (critical) covers "a newer file loads but an older SWERepo never overwrites it", for both a newer version and a newer standard.

Each new test was checked to fail when the behaviour it protects is broken (five in-memory breakages, all caught).

A second explanation by SeamSpec's reviewer judged inv_7c5f3156 and inv_070db19c sound and found two remaining test gaps, which the owner chose to close:

- **inv_bee7349a:** the git case now commits the files and makes the index out of date before the snapshot, so a git command that refreshes the index would be caught (proved: adding `git status` fails the test, which the earlier version would not have caught); it also asserts that the workflow, the flake8 and ruff linters and the pytest configuration were found.
- **inv_d8603926:** the save now follows real changes (`set_components`, `set_mode`, `set_file`) on lines with end-of-line comments, by a newer running version, with an unknown key inside `[projects]`. The code already kept all of them (checked before changing the test); the test now proves it.
- **inv_7c5f3156:** the wording names a missing final newline, which the test already covered.

Four more in-memory breakages, all caught.

**Approved and locked by the owner on 2026-11-20:** inv_7c5f3156, inv_bee7349a, inv_d8603926 and inv_070db19c. `docs/EARNED_SPEC.md` regenerated (6 rules in force).
