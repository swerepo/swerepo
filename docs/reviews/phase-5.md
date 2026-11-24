# Code Review · Phase 5: swerepo init for github, and swerepo threads

**Status:** closed · **Rounds:** 4 · **Developer:** Claude · **Reviewer:** Gemini · **Owner decides:** ties, merges, SeamSpec approvals
**Process:** ADR-20261119-9f87. Finding IDs `P5-F<nn>`; severities `blocker | should-fix | suggestion | question`; responses Fix / Push back / Defer, then Accept / Maintain.

---

## Developer summary

### Scope

Spec §10's last step, and the commands around it:

- **`swerepo init` for `github`** (`swerepo/github.py`, `swerepo/init.py`, `swerepo/cli.py`):
  - **Settings as code:** `.github/swerepo/ruleset.json` and `repo-settings.json`.
  - **The other files:** Copilot review instructions, PR and issue templates, Dependabot, and CODEOWNERS as a block at the end.
  - **Choices:** the mode and code owner are asked, or given with `--mode`, `--code-owner` and `--no-copilot-review`.
  - **GitHub:** the ruleset and merge settings are applied through `gh` after being shown as JSON, or wait when there is no GitHub repository.
- **Merges wait for Copilot's review** (the owner's decision): a `copilot-review` job inside `ci-ok`, in `ci/workflow@2`.
- **`swerepo check` reads GitHub** through `gh`: the live ruleset and merge settings, secret scanning and push protection, and the dependency graph. It never does so with `--ci`, and sends GET requests only.
- **`swerepo threads <pr>`** (`swerepo/threads.py`): open review threads, read-only.
- **New template versions:** `agents/block@2` and `agents/address-review@2` name `swerepo threads`; `ci/workflow@2` and its parts are listed above.

The owner decided four things for this repository first (2026-11-23):
- `solo` mode, although the repository belongs to an organisation;
- the owner's own login as code owner;
- squash-only merging;
- merges wait for Copilot's review.

They're applied in the pull request after this one, as Phases 3 and 4 were.

Branch `phase-5/github-threads`, uncommitted. Spec updated to v0.11.

### What to review

| Area | Files |
|---|---|
| Builders, `gh` calls, comparisons | `swerepo/github.py` (`_ruleset_v1`, `_repo_settings_v1`, `BUILDERS`, `GitHub`, `ruleset_differences`, `settings_differences`) |
| init: github | `swerepo/init.py` (`_github_choice`, `_github`, `_github_apply`, `apply_github`, `MODE_MEANING`, the `APPLY` and `WAITING` verbs, `_new_state`); `_ci` gets `copilot` and `asked` |
| Command line | `swerepo/cli.py` (`--mode`, `--code-owner`, `--copilot-review/--no-copilot-review`, `_ask_github`, `_apply_github`, `threads`) |
| The Copilot wait | `swerepo/templates/ci/job-copilot-review/2.yml`, `swerepo/templates/ci/workflow/2.yml` (the `ci-ok` filter), `swerepo/ci.py` (`Inputs.copilot_review`, `FIXED_JOBS`) |
| check | `swerepo/check.py` (`Context.hub`, `_github_live`, `_secret_scanning`, `_dependency_graph`, builder ids in `_record`, `read_github`); `swerepo/standard.py` (`LATER`) |
| threads | `swerepo/threads.py` |
| Templates | `swerepo/templates/github/*/1.*`; `ci/*/2.yml`; `agents/block/2.md`, `agents/address-review/2.md` |
| State | `swerepo/state.py` (`github`, `set_github`; validation of `[github]`) |
| Tests | `tests/test_github.py`, `tests/fake_gh.py` (new); updates in `tests/test_init.py`, `tests/test_init_ci.py`, `tests/test_check.py` |
| ADRs | `docs/adr/ADR-20261123-4e40-github-component.md`, `docs/adr/ADR-20261123-a359-copilot-review-wait.md` |
| Spec | `SWEREPO-SPEC.md` §6.2 (copilot-review), §7 (flags), §9 (`[github] copilot_review`), §12 (applying, check), Appendix A "0.10 → 0.11" |
| Proposed rules | `.seamspec/proposed/inv_ef31cc79/`, `.seamspec/proposed/inv_faa5bef5/` |
| Docs | `docs/PROGRESS.md`, `docs/progress/20261123-phase-5-github-threads.md`, `CHANGELOG.md` |

### ADRs written

| ADR | Decision |
|---|---|
| ADR-20261123-4e40 | The files; JSON built in Python and versioned like templates; the ruleset's rules per mode; squash-only merge settings; what init asks; applying through `gh` after a yes, adopting a ruleset named `swerepo` and never touching others; waiting without a GitHub repository; `check` reading GitHub with GET only and never with `--ci`; the dependency graph; `swerepo threads`; the agents templates at version 2. |
| ADR-20261123-a359 | A `copilot-review` job in the same CI run (not a re-run on `pull_request_review`, which would let `ci-ok` pass without governance); any commit's review counts, since Copilot reviews the first push only; `ci/workflow@2`, written over an unchanged version 1 when `github` is applied. |

### How to run

```bash
uv sync
uv run pytest
GITHUB_ACTIONS=true TERM=dumb uv run pytest
uv run ruff check . .seamspec/proposed/
uv run ruff format --check . .seamspec/proposed/
uv run seamspec verify --all
uv run seamspec verify --proposed inv_ef31cc79 --proposed inv_faa5bef5
uv run swerepo init --only github --dry-run          # on this repository: reads GitHub (GET only), writes nothing
uv run swerepo check --only github,security,ci        # reads GitHub through gh
uv run swerepo threads 8                              # PR #8: no open threads (all resolved)
```

### Results (run by the developer on 2026-11-23, macOS, Python 3.14, uv 0.9.28, git 2.50, gh logged in)

- **Tests:** pytest **546 passed** (36 new in `tests/test_github.py`). ruff check and format are clean, including `.seamspec/proposed/`. Locked rules: 13 passed. Proposed rules: 2 passed.
- **A version 2 workflow with the Copilot wait** passes zizmor 1.32.0 and parses as YAML (9 jobs).
- **Against this repository's real GitHub settings** (read-only):
  - **The ruleset:** for `solo` with Copilot review and squash only, the built ruleset differs from the live `swerepo` ruleset in one field only, `pull_request.allowed_merge_methods`.
  - **Merge settings:** they differ in `allow_merge_commit`, `allow_rebase_merge`, `delete_branch_on_merge` and the squash title and message. That's exactly the owner's choice.
  - **`check`** reports the dependency graph on, and secret scanning and push protection **off** (a warning; the owner's setting).
- **`swerepo threads 8`:** "no open review threads". On a missing PR, a one-line error with exit 1.
- **Mutation checks:**
  - **Component tests:** caught `check` sending a non-GET request, a hand-made `swerepo` ruleset not being adopted, `ci-ok` not waiting for Copilot's review, and `solo` requiring an approval.
  - **Proposed rules:** caught the wait passing with no review, `ci-ok` not waiting, a new ruleset made instead of the adopted one, and reads sent as POST.
  - **A miss that changed a rule's test:** the wait matching look-alike logins went uncaught at first, because the fake `gh` didn't run the job's `--jq` filter. It does now, and both look-alike breakages are caught.

### Design notes worth checking

1. **The JSON is built in Python** (ADR-4e40 point 2). The templates README already allows this for structured files. The builders are keyed like template ids so `check` and `update` treat them the same way.
2. **The Copilot wait runs inside the pull request's own run** (ADR-a359 point 2). A second run triggered by the review would produce a `ci-ok` where governance is skipped by design, which could pass after the first run's governance failed. The trade is a runner that polls for up to 20 minutes.
3. **Any commit's review counts** (ADR-a359 point 1), since `review_on_push: false` means Copilot reviews the first push only.
4. **Adopting by name:** `apply_ruleset` updates the ruleset named `swerepo` with `PUT`, so this repository's hand-made ruleset (id 27712627) becomes SWERepo's without a second one.
5. **`[github] applied`** turns true only when nothing is left to apply. If the person applies the ruleset but not the merge settings, it stays false, and the next `init` offers the rest.
6. **The plan reads GitHub, including in a dry run.** It shows what would change ("update: pull_request.allowed_merge_methods") from GET requests. The proposed rule `inv_ef31cc79` locks that `check` and the plan never change GitHub.
7. **Recorded choices are reused:** the mode, the code owner and `copilot_review` come from `.swerepo.toml` on later runs, like Phase 4's inputs.
8. **Version 1 templates kept** (`ci/workflow@1`, `agents/block@1`, `agents/address-review@1`): repositories that recorded them report `↑` until `update` (Phase 6). This repository's `swerepo-ci.yml` shows `↑ @2 available` until the next dogfooding PR rewrites it.

### Known gaps and deliberate omissions

- **Plan limits** (rulesets not enforced on a private repository on the Free plan) aren't detected: the repository alone doesn't say which plan it's on. `check` can't tell and doesn't guess.
- **`[github] extra_required_checks`** is read and put into the ruleset, but `init` doesn't yet ask which other workflows' checks to require (spec §11). It's recorded by hand for now.
- **Copilot availability** isn't detected. The owner turns review off with `--no-copilot-review` when the account has no Copilot review; otherwise the wait fails after 20 minutes with a message saying how to request the review.
- **`swerepo threads`** shows the first line of the last comment only; the URL leads to the rest.
- **Secret scanning** is reported, not turned on: it's a repository setting, and only the owner changes it.

### Questions for the reviewer

1. **Waiting in the same run, for up to 20 minutes** (design note 2): right trade, or is there a way to re-run on `pull_request_review` without the governance gap?
2. **Any commit's review counts** (design note 3): acceptable, or should a pull request whose later pushes change a lot need a fresh review?
3. **Adopting a hand-made ruleset by name** (design note 4): should `init` show the live ruleset's differences in more detail before `PUT`, since it replaces every rule?
4. **`check` reading GitHub by default** (not `--ci`): right default, or should it need a flag?
5. **The two proposed rules:** the right behaviours to lock, and critical?

### SeamSpec proposals waiting for the owner

| ID | Rule | Critical | Verified |
|---|---|---|---|
| inv_ef31cc79 | `check` and `init`'s plan only read GitHub, and `check --ci` doesn't call it; without a yes, nothing changes on GitHub; with `--yes`, only the ruleset named `swerepo` and the merge settings | yes | passed |
| inv_faa5bef5 | Pull requests wait for Copilot's review inside `ci-ok`: the generated wait passes only on a review by Copilot (look-alikes rejected), and `ci-ok` fails on any wrong result for it; no wait with `--no-copilot-review` | yes | passed |

The owner approves with `uv run seamspec review` after this review round.

---

## Review rounds

### Round 1

#### Reviewer: verification and strengths

**Verification run (macOS, Python 3.12 / 3.14, uv 0.9.28, git 2.50, gh logged in — GET-only on GitHub):** Ran every command under "How to run", plus local reproduction probes against `FakeGh` and checked PR #8's live `/reviews` author login (`copilot-pull-request-reviewer[bot]`):
- `uv sync` → clean (50 packages resolved, 47 audited).
- `uv run pytest` → **546 passed** in 76.59s; `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **546 passed** in 76.24s.
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (127 files formatted).
- `uv run seamspec verify --all` → **13 locked invariants passed**; `uv run seamspec verify --proposed inv_ef31cc79 --proposed inv_faa5bef5` → **2 proposed invariants passed**.
- `uv run swerepo init --only github --dry-run` on this repository → exit `0` (`9 changes`, writes nothing; exposed `P5-F02` live on `.github/swerepo/ruleset.json`).
- `uv run swerepo check --only github,security,ci` on this repository → reported dependency graph `on`, secret scanning `off (warning)`, `ci/workflow@1 → @2 available`, and `5 missing` (exposed `P5-F02` part 3 live on missing `repo-settings.json`).
- `uv run swerepo threads 8` → `#8: no open review threads.` (`exit 0`).

**What is well done and should be kept:**
- **`swerepo/github.py:53-119, 197-224` and `swerepo/check.py:922-934`:** Building `ruleset.json` and `repo-settings.json` in Python under versioned builder IDs (`github/ruleset@1`, `github/repo-settings@1`) avoids fragile string interpolation into JSON while plugging cleanly into `_managed_file` and `_record`. Adopting an existing `swerepo` ruleset via `PUT` without touching any other ruleset is clean and safe.
- **`swerepo/templates/ci/job-copilot-review/2.yml` and `.seamspec/proposed/inv_faa5bef5/`:** Minimal `permissions: pull-requests: read` scoped to that job alone, untrusted values passed through `env:`, exact equality on `copilot-pull-request-reviewer[bot]` (verified against live PR #8's `/reviews` API payload), and executing the real `--jq` filter inside the SeamSpec test to catch look-alike logins.
- **`tests/fake_gh.py` and `.seamspec/proposed/inv_ef31cc79/`:** Testing against a real executable `gh` shim on `PATH` that logs every invocation proves both zero network traffic in `--ci` and GET-only discipline in `check` and `init --dry-run`.

---

#### Reviewer: findings

##### P5-F01 · blocker · `swerepo/init.py:960-979, 1067-1068`, `swerepo/check.py:323-355`
**What is wrong:** `SWEREPO-SPEC.md` §10 recommends applying one component per pull request (`init --only ci,security`, then `init --only github`), which is also what the next dogfooding PR on this repository will run (`CODE_REVIEW.md:30, 69`). When `swerepo init --only github` runs on a repository that already applied `ci`:
1. `"ci"` is not in `components`, so `_ci` (`swerepo/init.py:969-970`) never runs, leaving `.github/workflows/swerepo-ci.yml` without the `copilot-review` job (and at `ci/workflow@1` on Phase 4 repos).
2. Yet `_new_state` (`swerepo/init.py:1067-1068`) writes `[github] copilot_review = true` into `.swerepo.toml`.
3. **Three consequences:**
   - **Silent non-enforcement:** Pull requests do **not** wait for Copilot's review, and `swerepo check` (`swerepo/check.py:323-355`) never checks whether `swerepo-ci.yml` contains `copilot-review` when `state.github.get("copilot_review")` is `True` — reporting `✓` while the wait is missing.
   - **Corrupted Phase 6 merge base:** `.swerepo.toml`'s recorded inputs (`copilot_review = true`) no longer rebuild `[files.".github/workflows/swerepo-ci.yml"].rendered` on disk (breaking Phase 4's `P4-F02` invariant).
   - **Subsequent `init --only ci` cannot add it either:** Because `choice` is `None` when `"github"` is not in `components` (`swerepo/init.py:961, 970`), `asked` is `False`, so `swerepo init --only ci` marks `swerepo-ci.yml` as `outdated (... swerepo update (Phase 6))` and writes nothing (`tests/test_github.py:322` tested `only=["ci", "github"]`, masking `only=["github"]`).
**How to reproduce:**
1. In a fresh repo (`pyproject.toml` with `requires-python = ">=3.12"`), run `apply(make_plan(root, only=["ci"], hosts=[]), root)`, then `apply(make_plan(root, only=["github"], hosts=[], code_owner="@dev"), root)`.
2. `State.load(root).github["copilot_review"]` is `True`, while `"copilot-review" in workflow_jobs((root / ".github/workflows/swerepo-ci.yml").read_text())` is `False`, and `ci.render_workflow` from `.swerepo.toml`'s recorded inputs no longer matches `swerepo-ci.yml` on disk.
3. Run `make_plan(root, only=["ci"], hosts=[])` → `.github/workflows/swerepo-ci.yml` is `outdated` (`0` changes).
**Suggested fix:**
1. When `"github"` is in `components` and `.github/workflows/swerepo-ci.yml` is already recorded in `ctx.state.files()` (or `"ci"` is in `ctx.state.components`), rewrite `swerepo-ci.yml` if unchanged (and record `ci_copilot_review` per-workflow in `[values]`, alongside `ci_install` and `governance_command`, so a user-edited `swerepo-ci.yml` that stays `changed` keeps an exact merge-base snapshot in `.swerepo.toml` while `[github] copilot_review` records the `github` component's setting).
2. In `check._ci`, report when `[github] copilot_review = true` (or `False`) disagrees with whether `copilot-review` is in `swerepo-ci.yml`.

##### P5-F02 · blocker · `swerepo/init.py:792-795, 847-859, 1069-1070`, `swerepo/check.py:666-670, 683-686`
**What is wrong:** Three bugs in how `.github/swerepo/ruleset.json` and `repo-settings.json` interact with GitHub and `check`:
1. **`init` overwrites GitHub with builder defaults instead of kept/edited JSON files (`swerepo/init.py:792-795, 847-857`):** `SWEREPO-SPEC.md` §12 (`line 472`) and `ADR-20261123-4e40` (`line 76`) state that `ruleset.json` and `repo-settings.json` are the source of truth: a person may write or edit them, `init` keeps the file, and `init` applies the committed file to GitHub. Instead, `_github` always populates `rendered[name] = json.loads(render[1])` from SWERepo's builder, even when `_managed_file` returns `KEEP` or `CHANGED`. Seen **live** in `uv run swerepo init --only github --dry-run` on this repository: `init` prints `keep .github/swerepo/ruleset.json (yours: SWERepo didn't write it)` and then plans `apply ruleset "swerepo" ... (update: ... required_approving_review_count: 1)` from its default `team` builder — clobbering the `solo` ruleset on GitHub and immediately causing `swerepo check` (which compares GitHub against the file on disk) to fail!
2. **`[github] applied` stays `false` forever if GitHub already matches (`swerepo/init.py:1069-1070`):** Line `1069` (`if "applied" not in state.github or (plan.github_apply and state.github.get("applied")):`) never updates `applied` from `False` to `True` when `plan.github_apply` is empty (e.g. `init` first ran before `gh repo create` or after declining one prompt, and on a later run live GitHub already matches the files so `apply_github` is not called).
3. **Missing JSON files trigger a duplicate, misleading `"isn't readable JSON"` `UNKNOWN` finding (`swerepo/check.py:666-670`, also seen live in "How to run"):** When `.github/swerepo/repo-settings.json` does not exist yet, `_github` (`line 628`) reports `✗ merge settings as code missing`, and `_github_live` (`lines 667-669`) calls `_read_json` on the missing file and adds `? can't compare with GitHub: .github/swerepo/repo-settings.json isn't readable JSON`. (Also minor grammar on `lines 683, 686`: `ruleset "swerepo" on GitHub match` / `differ`.)
**How to reproduce:**
1. Run `uv run swerepo init --only github --dry-run` on this repository (or edit `.github/swerepo/repo-settings.json` to `"allow_merge_commit": true` matching `FakeGh` and run `swerepo init --only github --yes`): `init` keeps `repo-settings.json` on disk, yet sends `PATCH {"allow_merge_commit": false, ...}`, after which `swerepo check --only github` fails with `merge settings on GitHub differ from .github/swerepo/repo-settings.json`.
2. Run `uv run swerepo check --only github` on this repository: reports both `✗ merge settings as code missing` and `? can't compare with GitHub: .github/swerepo/repo-settings.json isn't readable JSON`.
**Suggested fix:**
1. When `ruleset.json` or `repo-settings.json` already exists on disk and its action is `KEEP`, `CHANGED`, `CURRENT`, or `OUTDATED`, read and validate the on-disk JSON file as `rendered[name]` for `_github_apply` (emitting a `NOTE` and skipping `APPLY` if the on-disk file isn't valid JSON).
2. On `swerepo/init.py:1069-1070` (when reading live GitHub succeeded), set `applied = not plan.github_apply and choice.hub is not None` whenever `state.github.get("applied") != applied`.
3. In `check._github_live` (`swerepo/check.py:667`), `if not ctx.exists(path): continue`, and use `"matches"` / `"differs"` for `kind == "ruleset"`.

##### P5-F03 · blocker · `swerepo/init.py:819-827`, `swerepo/check.py:640, 690-693`
**What is wrong:** `SWEREPO-SPEC.md` §7 (`line 279`) and `ADR-20261123-4e40` point 5 (`line 44`) specify that without a code owner (the default on every new local project without a GitHub remote, on every Organization-owned repository with `--yes`, and whenever the user answers `none`), `CODEOWNERS` is not written. `init._github` (`swerepo/init.py:825-827`) follows that rule, yet records `"github"` in `components`, while `check._codeowners` (`swerepo/check.py:690-693`) unconditionally returns a **blocking** `MISSING` finding (`✗ CODEOWNERS missing (.github/CODEOWNERS)`). As a result, `swerepo init --yes` on a new project or an Organization repo is immediately followed by `swerepo check` and `swerepo check --ci` (the `governance` CI job) failing with `exit 1` (`Next: swerepo init --only github`), while `swerepo init --only github --yes` prints `Nothing to do.`.
**How to reproduce:**
In a fresh repo (`pyproject.toml` + `uv.lock`, no GitHub remote — or with an Organization remote on `FakeGh`), run `swerepo init --yes` (`exit 0`), then `swerepo check --only github --ci`: exits `1` on `github.codeowners: CODEOWNERS missing (.github/CODEOWNERS)`, and re-running `swerepo init --only github --yes` does nothing.
**Suggested fix:** When `.swerepo.toml` records the `github` component without `values.code_owner` and no `CODEOWNERS` file exists, report `github.codeowners` as non-blocking (`blocking=False` warning, or `OK`/`NOTE` in `solo` mode where code-owner review is off anyway) naming `swerepo init --only github --code-owner @login` so `check --ci` does not fail for a choice `init` explicitly permits.

##### P5-F04 · blocker · `swerepo/cli.py:147-156, 213-216`, `swerepo/init.py:773-782, 963`
**What is wrong:** Three bugs in interactive `github` prompting (`_ask_github`):
1. **Hardcoded `default="solo"` overrides Organization `team` default (`swerepo/cli.py:153`):** `_github_choice` (`init.py:773`) defaults Organization repos to `"team"` (`SWEREPO-SPEC.md` §7 line `276`), yet `_ask_github()` prompts `default="solo"`. Pressing Enter on an Organization repo silently switches `mode` to `solo`.
2. **User `@login` default hidden AND explicit `"none"` ignored (`swerepo/cli.py:154-155`, `swerepo/init.py:779-781`):** On a User-owned repo (`alice/app`), `_ask_github()` shows `default="none"` instead of `@alice` (`SWEREPO-SPEC.md` §6.1 line `147`). Worse, when the user answers `"none"`, `_ask_github()` omits `"code_owner"` from the returned dict, so the second `make_plan` call hits `init.py:780` (`if owner is None and owner_type == "User": owner = f"@{owner_login}"`) and **creates `.github/CODEOWNERS` with `@alice` anyway**! (Passing `--code-owner none` on the CLI also raises `UsageError`.)
3. **`--mode` suppresses asking for `code_owner` (`swerepo/init.py:963`):** `plan.github_question = not choice.recorded and mode is None`. Running `swerepo init --only github --mode solo` interactively on an Organization repo never asks for `code_owner`.
**How to reproduce:**
1. With `FakeGh` returning `{"owner": {"login": "alice", "type": "User"}}` on `alice/app` and `_interactive = lambda: True`, invoke `swerepo init --only github` with input `"solo\nnone\nn\n"` → the plan still creates `.github/CODEOWNERS` with `@alice`.
2. With `FakeGh` returning `{"owner": {"login": "acme", "type": "Organization"}}` on `acme/app`, invoke `swerepo init --only github` with input `"\n\nn\n"` → selects `mode: solo` instead of `mode: team`.
3. On `acme/app`, invoke `swerepo init --only github --mode solo` interactively with input `"n\n"` → never prompts for `Code owner`.
**Suggested fix:** Carry the detected default `mode` and default `code_owner` on `Plan`, prompt separately for whichever of `mode` / `code_owner` wasn't recorded or given via flag (using those detected defaults), and allow `"none"` (both interactively and via `--code-owner none`) as an explicit "no code owner" value that suppresses the `@owner_login` fallback.

##### P5-F05 · should-fix · `swerepo/templates/ci/workflow/2.yml:5-6`, `swerepo/templates/ci/job-copilot-review/2.yml:3-29`, `swerepo/github.py:71-73`
**What is wrong:** Draft pull requests hit a double failure mode:
1. `_ruleset_v1` (`swerepo/github.py:72`) sets `"review_draft_pull_requests": False`, so GitHub never triggers Copilot review on Draft PRs — yet `copilot-review` (`job-copilot-review/2.yml:4`) runs on every `pull_request` regardless of `github.event.pull_request.draft`, sleeping 20 full minutes on every push to a Draft PR before failing.
2. `workflow/2.yml:6` specifies `on:\n  pull_request:` without `types:`, which defaults in GitHub Actions to `[opened, synchronize, reopened]` — **excluding `ready_for_review`**. When the author marks the Draft PR **"Ready for review"**, GitHub requests Copilot's review, while `swerepo-ci.yml` never re-runs on that commit SHA, leaving `ci-ok` stuck red.
**How to reproduce:**
Inspect `swerepo/github.py:72` (`"review_draft_pull_requests": False`), `swerepo/templates/ci/workflow/2.yml:5-6` (no `ready_for_review` activity type), and `swerepo/templates/ci/job-copilot-review/2.yml:4, 17-28` (no `draft` check before the 40×30s loop).
**Suggested fix:** Add `types: [opened, synchronize, reopened, ready_for_review]` under `on.pull_request` in `swerepo/templates/ci/workflow/2.yml`, and in `job-copilot-review/2.yml` pass `DRAFT: ${{ github.event.pull_request.draft }}` and exit immediately before the polling loop when `[ "$DRAFT" = "true" ]` (`echo "Draft pull request: Copilot reviews once marked ready for review."; exit 1`) — burning zero runner minutes on drafts and automatically running to green when marked ready for review.

##### P5-F06 · should-fix · `swerepo/github.py:32, 143, 204-210`, `swerepo/init.py:685-687, 860-862`, `swerepo/check.py:352-353, 393-402`
**What is wrong:** Three issues in `GitHub` host detection and `dependency_graph` checks:
1. **Unanchored `github.com` match (`swerepo/github.py:32, 143`, `swerepo/init.py:685-687`):** `_REMOTE` uses `.search(r"github\.com[:/]...")` with no host-start boundary (and `has_github_remote` uses `"github.com" in url`). A look-alike remote such as `https://evilgithub.com/victim/repo.git` matches `victim/repo`, causing `GitHub.connect` (and `init --yes`) to read or `PUT`/`PATCH` `github.com/victim/repo`!
2. **False blocking failure on private repositories (`swerepo/check.py:352-353, 393-402`, `swerepo/init.py:860-862`):** `dependency-review` in `swerepo-ci.yml` is skipped by design on private repositories (`!github.event.repository.private`), yet `_ci` checks `"dependency-review:" in text` (true in every generated workflow) and fails `swerepo check` with `blocking=True` (`exit 1`) on private repositories where Dependency Graph is off, claiming `"dependency-review fails ci-ok"`.
3. **All `GitHubError`s treated as `"dependency graph is off"` (`swerepo/github.py:204-210`):** `dependency_graph()` catches every `GitHubError` (timeouts, `502`, rate limits, `403`) and returns `False`, turning transient/permission errors into a blocking `MISSING` instead of `UNKNOWN` (`? can't read GitHub`, as `_secret_scanning` does on `check.py:586-587`).
**How to reproduce:**
1. Set `origin` to `https://evilgithub.com/victim/repo.git` and call `github.repository(root)` → returns `"victim/repo"`.
2. With `FakeGh` returning `{"owner": {"login": "dev", "type": "User"}, "private": True}` on `GET repos/acme/priv` and `404` on `dependency-graph/sbom`, run `run_check(root, only=["ci"], read_github=True)` → `ci.dependency-graph` is `missing` with `blocking=True` (`exit 1`).
**Suggested fix:** Anchor `_REMOTE` to host boundaries (`^(?:https?://(?:[^@/]+@)?|ssh://git@|git@)github\.com(?::\d+)?[:/]...`) and reuse `github.repository(root) is not None` in `has_github_remote`; skip `_dependency_graph` (or report non-applicable) when `repo().get("private") is True` (caching `hub.repo()` on `GitHub` so `check` doesn't fetch `GET repos/{slug}` multiple times); and distinguish `404` (disabled) from other `GitHubError`s (`UNKNOWN`).

##### P5-F07 · should-fix · `swerepo/threads.py:48-65`, `swerepo/cli.py:330-347`
**What is wrong:** In `threads._graphql`:
1. When `gh api graphql` exits non-zero (e.g. missing PR, bad repository, or insufficient scope), `gh` frequently writes the GraphQL error JSON (`{"errors": [{"message": "..."}]}`) to `stdout` with empty `stderr`; line `59` inspects only `done.stderr` and prints `swerepo threads: review threads of #99: failed`.
2. Line `60` (`json.loads(done.stdout)`) is not guarded against `JSONDecodeError`, and lines `61-63` ignore `data.get("errors")` when `pull is None`, reporting `"no pull request #N"` even on repository/auth GraphQL errors.
3. Non-positive PR numbers (`0`, or `-- -1`) are not rejected as `UsageError` (`exit 2`) before calling `gh`.
**How to reproduce:**
With `FakeGh` returning exit `1`, `stdout = '{"errors": [{"message": "Could not resolve to a PullRequest with the number of 99."}]}'`, and `stderr = ""` on `api graphql`, run `swerepo threads 99` → prints `swerepo threads: review threads of #99: failed`.
**Suggested fix:** Validate `number >= 1` (`UsageError`), wrap `json.loads` in `try ... except json.JSONDecodeError`, prefer `errors[0]["message"]` from `stdout` JSON before falling back to `stderr` (and surface non-`NOT_FOUND` GraphQL `errors` before assuming `"no pull request #N"`).

##### P5-F08 · suggestion · `swerepo/check.py:701`
**What is wrong:** `_codeowners` slices `text.splitlines()[block.end_line :]`, whereas `find_block` counts lines only on `\r\n|\r|\n` (same mismatch as Phase 3's `P3-F02`). A `\u2028` or `\x0c` in a comment above `# swerepo:begin` shifts `splitlines()` so `# swerepo:end` or comment lines misalign and trigger a false `~ rules after the SWERepo block can override governance owners`.
**How to reproduce:**
Write `"# note\u2028here\n\n# swerepo:begin\n/.github/ @dev\n# swerepo:end\n"` to `.github/CODEOWNERS` and run `run_check(root, only=["github"])` → `github.codeowners` returns `status='changed'`.
**Suggested fix:** Use `re.split(r"\r\n|\r|\n", text)[block.end_line :]`.

##### P5-F09 · suggestion · `swerepo/github.py:197-202`
**What is wrong:** `find_ruleset` calls `GET repos/{slug}/rulesets?includes_parents=false` without `per_page=100` or pagination (GitHub defaults to 30 items), so on a repository with >30 rulesets `find_ruleset` could miss `swerepo` on page 2 and attempt `POST` instead of `PUT`.
**How to reproduce:**
Inspect `swerepo/github.py:199`.
**Suggested fix:** Add `&per_page=100` (or paginate).

---

#### Reviewer: answers to "Questions for the reviewer"

1. **Waiting in the same run, for up to 20 minutes (design note 2):** **Right trade — keep it in the `pull_request` run (with the Draft PR fix in `P5-F05`).** Avoiding the governance/dependency-review skip gap on `pull_request_review` would require either re-running the entire test/lint/governance suite a second time on every PR when Copilot's review lands, or fragile cross-workflow `workflow_run` API lookups. Polling `pulls/$NUMBER/reviews` every 30s typically finishes in 1–3 minutes on the first push and <2s on every subsequent push. Adding `ready_for_review` + fast-exit on `draft == true` (`P5-F05`) eliminates the one case where it would genuinely sit for 20 minutes.
2. **Any commit's review counts (design note 3):** **Acceptable — keep it.** With `review_on_push: false`, GitHub only auto-requests Copilot on the PR's initial review; requiring a fresh Copilot review after later commits would block every PR as soon as the author pushes fixes for Copilot's comments. Meanwhile `lint`, `test`, `seamspec`, `governance`, `zizmor`, and `swerepo-privacy` re-run on every push, and `team` mode's `dismiss_stale_reviews_on_push` already requires a fresh human approval.
3. **Adopting a hand-made ruleset by name (design note 4):** **Showing the rule-level delta + the full JSON prompt is sufficient once two small tweaks are made:** (a) fix `P5-F02` so an existing `.github/swerepo/ruleset.json` on disk isn't overwritten on GitHub by builder defaults; and (b) clarify `ruleset_differences`'s `"<kind> added"` wording (`swerepo/github.py:257`) when used in `init`'s `update: ...` note (`swerepo/init.py:850`), because in `init` `"merge_queue added"` sounds like `PUT` will *add* `merge_queue` when `PUT` will actually **remove** that extra live rule! Calling it `"removes <kind>"` in `init` (or `"extra <kind> on GitHub"` in `check`) makes destructive rule replacement obvious before confirming `PUT`.
4. **`check` reading GitHub by default (not `--ci`):** **Right default.** Catching server-side drift (merge commits re-enabled in UI, ruleset edited, Dependency Graph off) is the primary local value of `check` in Phase 5; hiding it behind a flag means developers and coding agents won't run it. `--ci` stays offline and fast, and unauthenticated/offline local runs degrade cleanly to `? can't tell` (`exit 0`).
5. **The two proposed rules (`inv_ef31cc79`, `inv_faa5bef5`):** **Both lock the right Phase 5 behaviours and both should stay `critical: true`**, with two additions while addressing Round 1:
   - In **`inv_ef31cc79`**: add `"swerepo/threads.py"` to `scope.paths` and invoke `swerepo threads` inside `test_inv_ef31cc79.py` so `threads` is also locked against ever sending a mutating call.
   - In **`inv_faa5bef5`**: test the two-step `only=["ci"]` followed by `only=["github"]` sequence (`P5-F01`, instead of `only=["ci", "github"]` on line `89`) and pass `DRAFT="false"` (plus asserting fast failure on `DRAFT="true"`, `P5-F05`).

#### Readiness summary

Not ready to merge yet: **4 blockers** (`P5-F01`–`P5-F04`), **3 should-fix** findings (`P5-F05`–`P5-F07`), and **2 suggestions** (`P5-F08`–`P5-F09`). Hold owner approval of `inv_ef31cc79` and `inv_faa5bef5` until the Round 1 fixes and test updates are in place.

### Developer responses

All nine findings were reproduced before any change. Four of them on this repository itself:
- **P5-F01:** `[github] copilot_review = true` was recorded with no wait in the workflow.
- **P5-F02:** a dry run here planned to replace the committed `solo` ruleset with a `team` build.
- **P5-F03:** a blocking CODEOWNERS finding after `init` had left CODEOWNERS out on purpose.
- **P5-F06:** an `evilgithub.com` remote was read as `victim/repo`.

All nine are fixed, each with a regression test (`TestGeminiReviewRound1` in `tests/test_github.py`). For F01, F02, F04 and F05 I put the old behaviour back and saw its test fail.

**Results:** pytest **566 passed** (20 new), also with `GITHUB_ACTIONS=true TERM=dumb`; ruff clean; 13 locked and 2 proposed rules pass; the version 2 workflow passes zizmor. ADR-4e40, ADR-a359 and spec §6.2, §7 and §12 are updated.

#### P5-F01 · **Fix** (both parts)
- **Applying `github` alone brings `ci` along:** when `.swerepo.toml` records `ci`, `init --only github` also plans `ci`, and an unchanged `swerepo-ci.yml` is rewritten to version 2 with the wait.
- **The workflow records its own flag:** `ci_copilot_review` is recorded with its other inputs. A later `init --only ci` renders from that recorded flag, so the recorded inputs always rebuild what was written.
- **`check` reports disagreement:** `ci.copilot-review` is ✗ when the ruleset asks for Copilot review but the workflow doesn't wait, or the workflow waits for a review the ruleset doesn't request.

Tests: `test_p5_f01_applying_github_alone_brings_ci_along`, `test_p5_f01_check_reports_a_workflow_that_doesnt_wait`.

#### P5-F02 · **Fix** (all three)
1. When `ruleset.json` or `repo-settings.json` exists, the committed file is what gets compared and applied, a person's edits included. A fresh build is used only for a file `init` creates in the same run. A file that isn't a JSON object gets a note, and nothing is applied from it. Test: `test_p5_f02_the_committed_files_are_what_gets_applied` (an edited `allow_merge_commit: true` survives `--mode team`).
2. `[github] applied` follows GitHub whenever GitHub could be read: true when there's nothing left to apply, including when it already matched. Test: `test_p5_f02_applied_turns_true_when_github_already_matches`.
3. A missing settings file is reported once; "matches" and "differs" are fixed for the ruleset. Test: `test_p5_f02_a_missing_settings_file_is_reported_once`.

#### P5-F03 · **Fix**
When `.swerepo.toml` records `github` without a code owner, a missing CODEOWNERS is a warning (it doesn't fail `--ci`) and names `--code-owner`. Without the component recorded, it stays blocking. Test: `test_p5_f03_no_code_owner_is_a_warning_not_a_failure`.

#### P5-F04 · **Fix** (all three)
- **Detected defaults, asked separately:** `Plan.github_ask` carries what to ask and the detected default (`team` for an organisation, `@login` for a user), each only when no flag and no earlier run decided it. `--mode solo` no longer skips the code-owner question.
- **`none` is an answer:** in a terminal and as `--code-owner none`, it is recorded, so the repository owner isn't proposed again.

Test: `test_p5_f04_questions_use_the_detected_defaults_and_none_means_none`.

#### P5-F05 · **Fix** (as you suggested)
`on.pull_request.types` includes `ready_for_review`. The wait fails at once on a draft, before any request or sleep, with a message saying it runs again once the draft is ready. `${DRAFT:-false}` keeps `set -u` happy where the variable is absent. `ci/workflow@2` hasn't been released, so it was corrected in place. Test: `test_p5_f05_drafts_dont_wait_and_ready_for_review_runs_again`. `inv_faa5bef5` now checks the draft case too.

#### P5-F06 · **Fix** (all three)
- **Only github.com itself:** `_REMOTE` matches `github.com` only as the host: after a scheme and an optional user, or at the start of an SCP-style address. `has_github_remote` now uses it too, since it had its own unanchored test.
- **Private repositories:** the dependency graph is reported as not needed there, since dependency review is skipped. `GitHub.repo()` is read once per run.
- **Only a 404 means "off":** `GitHubError.not_found` marks GitHub's 404, and `dependency_graph()` raises any other failure, so it reads as "can't tell".

Tests: `test_p5_f06_only_github_itself_counts` (6 URLs), `test_p5_f06_private_repositories_dont_need_the_dependency_graph`, `test_p5_f06_only_a_404_means_off`.

#### P5-F07 · **Fix** (all three)
GraphQL errors are read from stdout first, then stderr; the JSON is parsed safely; and errors are reported before "no pull request". A number below 1 is wrong usage (exit 2). Test: `test_p5_f07_threads_reports_graphqls_own_message`.

#### P5-F08 · **Fix**
`_codeowners` splits lines the way `find_block` counts them. Test: `test_p5_f08_unicode_line_breaks_above_the_block_dont_shift_it`.

#### P5-F09 · **Fix**
`per_page=100`. Test: `test_p5_f09_rulesets_are_listed_100_at_a_time`.

#### On your answers
- **Q1, Q2 and Q4:** agreed; they stay as they are.
- **Q3:** done. In `init`'s plan, a rule only GitHub has reads `removes <rule>` (`github.ruleset_changes`). The full JSON is still shown before the yes.
- **Q5:** both rules were strengthened as you suggested, and both are still critical:
  - `inv_ef31cc79` now covers `swerepo threads`, which may send no mutation, and has `swerepo/threads.py` in its scope.
  - `inv_faa5bef5` applies `github` on its own after `ci`, and checks drafts and `ready_for_review`.

  Each new part caught a breakage of its own: drafts waiting anyway, `github` alone leaving `ci` behind, and `threads` sending a mutation.

Ready for round 2.

---

### Round 2

#### Reviewer: verification

**Verification run (macOS, uv 0.9.28, git 2.50, gh logged in — GET-only on GitHub):** Re-ran every command under "How to run", `uvx zizmor==1.32.0 --offline` on a rendered `ci/workflow@2` with `copilot-review` + `governance`, and local Round 2 reproduction probes against `FakeGh`:
- `uv sync` → clean (50 packages resolved, 47 audited).
- `uv run pytest` → **566 passed**; `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **566 passed**.
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (127 files formatted).
- `uv run seamspec verify --all` → **13 locked invariants passed**; `uv run seamspec verify --proposed inv_ef31cc79 --proposed inv_faa5bef5` → **2 proposed invariants passed**.
- `uvx zizmor==1.32.0 --offline` on rendered `swerepo-ci.yml` (`@2` with `copilot-review` + `governance`) + `swerepo-privacy.yml` → **0 findings**.
- `uv run swerepo init --only github --dry-run` on this repository → exit `0`, GET-only (`9 changes`: `rewrite .github/workflows/swerepo-ci.yml`, `keep .github/swerepo/ruleset.json`, `current ruleset "swerepo" on GitHub`, `apply merge settings`).
- `uv run swerepo check --only github,security,ci` → reports `ruleset "swerepo" on GitHub matches .github/swerepo/ruleset.json`, single missing finding for `repo-settings.json`, dependency graph `on`, secret scanning `off (warning)`.
- `uv run swerepo threads 8` → `#8: no open review threads.` (`exit 0`).

---

#### Reviewer: Round 1 dispositions

- **P5-F01 · Accept:** `init --only github` now brings a recorded `ci` along and rewrites an unchanged `swerepo-ci.yml` to `ci/workflow@2` with `copilot-review`; `ci_copilot_review` is recorded with the workflow's inputs; `check._copilot_wait` catches disagreement; and `TestGeminiReviewRound1` + `inv_faa5bef5` cover sequential `only=["ci"]` → `only=["github"]`. *(Two follow-up edge cases in the new logic are filed below as `P5-F10` and `P5-F12`.)*
- **P5-F02 · Accept:** All three parts verified in tests and live on this repository: committed `ruleset.json` and `repo-settings.json` are read as the source of truth (so `--dry-run` here now reports `current ruleset "swerepo" on GitHub` instead of clobbering `solo` with `team`); `[github] applied` flips to `true` when GitHub already matches; missing `repo-settings.json` is reported once and ruleset singular verbs (`matches` / `differs`) are fixed.
- **P5-F03 · Accept:** Missing `CODEOWNERS` when `github` is recorded without a valid `code_owner` is now a non-blocking warning (`blocking=False`) naming `--code-owner`, so `check --ci` no longer fails on a choice `init` permits.
- **P5-F04 · Accept:** `Plan.github_ask` carries the detected defaults (`team` for Organization, `@login` for User), prompts `mode` and `code_owner` independently (`--mode solo` still prompts for `code_owner`), and records `"none"` so `@<owner>` is not re-proposed on later runs.
- **P5-F05 · Accept:** `on.pull_request.types` includes `ready_for_review`, `job-copilot-review/2.yml` exits immediately before polling when `${DRAFT:-false}` is `"true"`, `zizmor 1.32.0` passes with 0 findings, and `inv_faa5bef5` covers drafts.
- **P5-F06 · Accept:** `_REMOTE` is anchored to host boundaries and shared by `repository()` and `has_github_remote()`; private repositories report `ci.dependency-graph` as `OK` (`not needed`); `GitHub.repo()` is cached per instance; and `GitHubError.not_found` separates `404` (`off`) from `502`/timeout (`UNKNOWN`).
- **P5-F07 · Accept:** `threads._graphql` reads GraphQL `errors` from `stdout` before `stderr`, guards `json.loads`, reports GraphQL `errors` before `"no pull request"`, and rejects `number < 1` as `UsageError` (`exit 2`). *(One tiny `null`/`[]` JSON guard is noted as `P5-F13`.)*
- **P5-F08 · Accept:** `_codeowners` now splits lines with `re.split(r"\r\n|\r|\n", text)[block.end_line :]`, matching `find_block`.
- **P5-F09 · Accept:** `find_ruleset` requests `per_page=100`, covered by `test_p5_f09_rulesets_are_listed_100_at_a_time`.
- **Q3 & Q5 updates · Accept:** `github.ruleset_changes` turns `"<kind> added"` into `"removes <kind>"` in `init`'s plan, `inv_ef31cc79` now covers `swerepo threads` and scopes `swerepo/threads.py`, and `inv_faa5bef5` covers sequential `ci` → `github` and drafts.

---

#### Reviewer: new findings

##### P5-F10 · blocker · `swerepo/init.py:791-817, 841-847, 1001, 1017-1018, 1102-1110`, `swerepo/check.py:354-355, 395-406`
**What is wrong:** `ruleset.json`, `swerepo-ci.yml`, `CODEOWNERS`, and `.swerepo.toml` go out of sync in two directions:
1. **Explicit `github` flags (`--mode`, `--code-owner`, `--no-copilot-review`) update `.swerepo.toml` and `swerepo-ci.yml` while leaving unchanged `ruleset.json` (and `CODEOWNERS`) `outdated`:**
   - `_github` (`swerepo/init.py:806`) never calls `_rewrite_if_asked` on `.github/swerepo/ruleset.json`. After `swerepo init --only ci,github --yes`:
     - Running `swerepo init --only github --no-copilot-review --yes` **rewrites `swerepo-ci.yml`** to remove `copilot-review` and writes `[github] copilot_review = false` into `.swerepo.toml`, while leaving `.github/swerepo/ruleset.json` `outdated` **with `copilot_code_review` still inside** (applied to GitHub!), and `swerepo check` reports `✓ no Copilot review to wait for`.
     - Running `swerepo init --only github --mode team --code-owner @acme/devs --yes` leaves `.github/swerepo/ruleset.json` `outdated` on `solo` (`required_approving_review_count: 0`, `require_code_owner_review: false`) and `.github/CODEOWNERS` `outdated` on `@dev`, yet `_new_state` (`swerepo/init.py:1104-1108`) overwrites `mode = "team"` and `code_owner = "@acme/devs"` in `.swerepo.toml` — leaving GitHub on `solo` and corrupting `.swerepo.toml`'s recorded merge-base inputs for both files.
2. **A kept or user-edited `ruleset.json` without `copilot_code_review` still gets a 20-minute failing `copilot-review` job in `swerepo-ci.yml` (and `check` misses it):**
   - Because `_ci` (`swerepo/init.py:1010`) runs before `_github` (`line 1018`) using `choice.settings.copilot_review` (`True` by default), when `.github/swerepo/ruleset.json` already exists on disk (`KEEP` or `CHANGED`) **without** `copilot_code_review`, `init` keeps and applies that `ruleset.json` (so GitHub never requests Copilot's review), yet writes `copilot-review` into `swerepo-ci.yml` — causing every pull request to poll 20 minutes and fail!
   - `check._ci` (`swerepo/check.py:354-355`) checks only `ctx.state.github["copilot_review"]` instead of inspecting `.github/swerepo/ruleset.json`, so `check` reports `✓ waits for Copilot's review` even when `ruleset.json` has no `copilot_code_review` rule (and on repositories where `ruleset.json` exists before `[github]` is in `.swerepo.toml`, such as this checkout right now, `check` skips `ci.copilot-review` completely).
**How to reproduce:**
1. Run `swerepo init --only ci,github --yes` on a `FakeGh` repo, then `swerepo init --only github --no-copilot-review --yes`: `swerepo-ci.yml` drops `copilot-review` and `State.load(root).github["copilot_review"]` is `False`, while `.github/swerepo/ruleset.json` still contains `"copilot_code_review"` and `run_check(root, only=["ci"])` reports `ci.copilot-review` as `OK`.
2. Run `swerepo init --only ci,github --yes`, then `swerepo init --only github --mode team --code-owner @acme/devs --yes`: `State.load(root).mode == "team"` and `State.load(root).values["code_owner"] == "@acme/devs"`, while `ruleset.json` still has `required_approving_review_count == 0` and `CODEOWNERS` still has `@dev`.
3. Write a `solo` `.github/swerepo/ruleset.json` with `copilot_review=False` (no `copilot_code_review` rule) before running `swerepo init --only ci,github --yes`: `ruleset.json` is kept without `copilot_code_review`, while `swerepo-ci.yml` gets `copilot-review` and `run_check` reports `ci.copilot-review` as `OK`.
**Suggested fix:**
1. Add `github.has_copilot_review(ruleset: dict[str, Any]) -> bool` (`any(isinstance(r, dict) and r.get("type") == "copilot_code_review" for r in ruleset.get("rules") or [])`).
2. Plan `_github`'s `ruleset.json` before `_ci` (or resolve `ruleset.json` up front): when `mode`, `code_owner`, or `copilot_review` was explicitly given in this run, call `_rewrite_if_asked` on `.github/swerepo/ruleset.json` (and treat `action.verb in (CREATE, REWRITE)` as using `json.loads(render[1])`), and rewrite an unchanged SWERepo block in `CODEOWNERS` when `code_owner` was given (via `replace_block_content`, or keep the recorded `code_owner`/`mode` in `.swerepo.toml` whenever `CODEOWNERS`/`ruleset.json` stays `CHANGED`/`OUTDATED`/`KEEP`). Derive `copilot` for `_ci` and `[github] copilot_review` from `has_copilot_review(rendered["ruleset"])` whenever `rendered["ruleset"]` is a `dict` (falling back to `choice.settings.copilot_review` only when `ruleset.json` isn't valid JSON).
3. In `check._ci` (`swerepo/check.py:354-355`), read `.github/swerepo/ruleset.json` with `_read_json` when it exists and pass `github.has_copilot_review(committed)` to `_copilot_wait` (falling back to `ctx.state.github["copilot_review"]` only when `ruleset.json` is absent).

##### P5-F11 · should-fix · `swerepo/init.py:827-835`
**What is wrong:** On the first run, `.github/pull_request_template.md` is created via `_managed_file` and recorded in `.swerepo.toml` under `[files.".github/pull_request_template.md"]` (`ADR-20261123-4e40` point 1). On every subsequent `init` run, `ctx.detection.documents.get("pr_template")` finds `.github/pull_request_template.md`, and lines `828-829` (`if existing_template: actions.append(Action(c, KEEP, existing_template, "yours"))`) short-circuit before `_managed_file` — reporting SWERepo's own managed file as `keep .github/pull_request_template.md (yours)` instead of `current` / `changed` / `outdated`.
**How to reproduce:**
Run `apply(make_plan(project, only=["github"], hosts=[]), project)`, then inspect `make_plan(project, only=["github"], hosts=[]).actions`: `.github/pull_request_template.md` has `verb == "keep"` and `note == "yours"` instead of `verb == "current"`.
**Suggested fix:** Change line `828` to `if existing_template and not (ctx.state and existing_template in ctx.state.files()):` (matching line `819`'s check for `.github/copilot-instructions.md`).

##### P5-F12 · should-fix · `swerepo/init.py:646-659, 1002-1010`
**What is wrong:** Two edge cases in `P5-F01`'s `ci_along` and `asked` plumbing:
1. **`asked=choice is not None` (`swerepo/init.py:1010`) rewrites `swerepo-ci.yml` even when Copilot review didn't change:**
   - On a repository with `ci/workflow@1` (no Copilot wait), running `swerepo init --only github --no-copilot-review` passes `asked=True` (`choice is not None`) and rewrites `swerepo-ci.yml` to `@2` even though `copilot` stayed `False`.
   - Likewise, once both `ci` and `github` are applied, running plain `swerepo init` (all components, so `"github"` is in `components` and `choice is not None` is `True`) passes `asked=True` and would silently rewrite `swerepo-ci.yml` on any future `ci/workflow` template bump instead of reporting `outdated` for `swerepo update` (`tests/test_init_ci.py` only tested `only=["ci"]`, where `choice` is `None`).
2. **`ci_along` (`swerepo/init.py:1002`) ignores `--no-ci` (`skip`):**
   - Running `make_plan(root, skip=["ci"])` (`swerepo init --no-ci`) on a repository where `"ci"` is in `state.components` removes `"ci"` in `resolve_components`, and line `1002` puts `"ci"` right back into `components`.
**How to reproduce:**
1. Record an unchanged `ci/workflow@1` workflow (`ci_copilot_review` unset) and call `make_plan(root, only=["github"], copilot_review=False, hosts=[])` → `.github/workflows/swerepo-ci.yml` has `verb == "rewrite"` instead of `"outdated"`.
2. After `apply(make_plan(root, only=["ci"], hosts=[]), root)`, call `make_plan(root, skip=["ci"], hosts=[])` → `ci` actions still appear in `plan.actions`.
**Suggested fix:** Require `"ci" not in skip` in `ci_along` (`swerepo/init.py:1002`), and in `_ci` (`swerepo/init.py:646-659`) treat `asked` as `True` only when `asked and copilot != (recorded_copilot == "true")`.

##### P5-F13 · suggestion · `swerepo/threads.py:59-62`
**What is wrong:** If `gh api graphql` writes valid non-object JSON to `stdout` (e.g. `"null"` or `"[]"`), `data = json.loads(done.stdout)` sets `data` to `None` or `list`, and `data.get("errors")` on line `62` raises `AttributeError` instead of `GitHubError` (unlike `github._reason` on `swerepo/github.py:256`, which catches `AttributeError`).
**How to reproduce:**
With `FakeGh` setting `gh.set("graphql", None)`, run `CliRunner().invoke(app, ["threads", "1", "--path", str(project)])` → crashes with `AttributeError: 'NoneType' object has no attribute 'get'`.
**Suggested fix:** Add `if not isinstance(data, dict): data = {}` after `json.loads`.

#### Readiness summary

All nine Round 1 findings (`P5-F01`–`P5-F09`) and both SeamSpec rule expansions (`inv_ef31cc79`, `inv_faa5bef5`) are **Accepted**. Round 2 turned up **1 blocker** (`P5-F10`), **2 should-fix** findings (`P5-F11`–`P5-F12`), and **1 suggestion** (`P5-F13`) — all tight and local to `init.py`, `check.py`, `github.py`, and `threads.py`. Hold owner approval of `inv_ef31cc79` and `inv_faa5bef5` until Round 2's fixes pass so the locked hashes capture the final code.

### Developer responses (round 2)

All four new findings were reproduced first. P5-F10 reproduced both ways: turning Copilot review off left it in `ruleset.json` while CI stopped waiting, and a committed ruleset without Copilot review still got the 20-minute wait. All four are fixed, each with a regression test (`TestGeminiReviewRound2` in `tests/test_github.py`), and for each fix I put the old behaviour back and saw its test fail. pytest passes, also with `GITHUB_ACTIONS=true TERM=dumb`; ruff clean; both proposed rules pass.

#### P5-F10 · **Fix** (all three, as you suggested)
- **The ruleset is decided before the CI workflow** (`init._settings_files`). When `--mode`, `--code-owner` or `--copilot-review` is given in this run, an unchanged `ruleset.json` SWERepo wrote is rewritten. A changed or hand-written one is kept, and the plan says what was given isn't in it.
- **The ruleset decides the wait:** whether CI waits comes from the committed ruleset (`github.has_copilot_review`), falling back to the choice only when `ruleset.json` isn't readable.
- **Recorded only where written:** the mode and `copilot_review` are recorded when the ruleset holds them, and the code owner when CODEOWNERS does. So `.swerepo.toml` never says `team` while the ruleset says `solo`.
- **`check` reads the committed ruleset** for `ci.copilot-review` when the file exists.

Tests: `test_p5_f10_turning_copilot_review_off_rewrites_the_ruleset_and_the_workflow`, `test_p5_f10_a_new_mode_goes_into_the_ruleset_or_isnt_recorded`, `test_p5_f10_a_committed_ruleset_without_copilot_review_gets_no_wait`, `test_p5_f10_check_reads_the_committed_ruleset`. `inv_faa5bef5` now also checks that a committed ruleset without Copilot review gets no wait.

#### P5-F11 · **Fix**
SWERepo's own PR template is compared with its record (`current`, `changed` or `outdated`), as for `copilot-instructions.md`. Test: `test_p5_f11_swereposs_own_pr_template_is_compared_not_called_yours`.

#### P5-F12 · **Fix** (both)
- **No rewrite unless the wait changes:** applying `github` rewrites the CI workflow only when the wait itself changes, compared with the workflow's recorded `ci_copilot_review` (a version 1 workflow counts as not waiting). A plain `init`, or `--no-copilot-review` on a workflow that never waited, leaves template bumps to `update`.
- **`--no-ci` is respected:** `ci` is brought along only when it isn't skipped.

Tests: `test_p5_f12_no_rewrite_when_the_wait_doesnt_change`, `test_p5_f12_a_version_1_workflow_isnt_rewritten_unless_the_wait_changes`, `test_p5_f12_no_ci_is_respected`. The version 1 test was added after my first version missed the breakage: its workflow was already at version 2, so nothing would have been rewritten anyway.

#### P5-F13 · **Fix**
An answer that isn't a JSON object reads as no answer: "no pull request #N", exit 1, no traceback. Test: `test_p5_f13_a_non_object_answer_is_an_error_not_a_crash` (`null`, a list, a string).

ADR-4e40 and ADR-a359 are updated for the committed ruleset deciding the wait, and for recording choices only where they're written.

**Found while checking the fix on this repository:** `ci.copilot-review` at first compared any committed `ruleset.json` with the workflow. This repository has a hand-written ruleset with Copilot review, but hasn't chosen the `github` component yet, so `swerepo check --base main --ci`, which the governance job runs, would have failed this PR. The check now applies only when `github` is chosen; without it, a ruleset is the person's own. Test: `test_p5_f10_a_ruleset_without_the_github_component_isnt_checked_against_ci`.

Ready for round 3.

---

### Round 3

#### Reviewer: verification

**Verification run (macOS, uv 0.9.28, git 2.50, gh logged in — GET-only on GitHub):** Re-ran every command under "How to run", `swerepo check --base main --ci` (exact governance job check for this PR), `zizmor==1.32.0 --offline`, and the Round 2 reproduction probes:
- `uv sync` → clean (50 packages resolved, 47 audited).
- `uv run pytest` → **578 passed**; `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **578 passed**.
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (127 files formatted).
- `uv run seamspec verify --all` → **13 locked invariants passed**; `uv run seamspec verify --proposed inv_ef31cc79 --proposed inv_faa5bef5` → **2 proposed invariants passed**.
- `uv run swerepo check --base main --ci` on this branch → **exit `0`** (`0 missing, 0 changed by you, 3 outdated, 2 can't tell`; `pr: ✓ progress entry added`).
- `uv run swerepo init --only github --dry-run`, `uv run swerepo check --only github,security,ci`, and `uv run swerepo threads 8` → all GET-only and clean.

---

#### Reviewer: Round 2 dispositions

- **P5-F10 · Maintain (narrowed to `CODEOWNERS` only — `swerepo/init.py:290-310, 873-878, 1153-1157`):**
  - **What is fixed and verified:** `_settings_files` deciding `ruleset.json` before `_ci`, rewriting an unchanged `ruleset.json` on `--mode` / `--code-owner` / `--no-copilot-review`, deriving CI's `copilot-review` wait from `github.has_copilot_review(committed)`, gating `check`'s `ci.copilot-review` on `"github" in ctx.state.components` (nice catch on `check --base main --ci`!), and expanding `inv_faa5bef5` all work and pass.
  - **What still fails (`CODEOWNERS` half):** On `swerepo/init.py:1153-1156`:
    ```python
    codeowners = [
        a
        for a in plan.actions
        if a.component == "github" and a.kind == "block" and a.path and a.path.endswith("CODEOWNERS")
    ]
    owner_written = not codeowners or codeowners[0].verb in (CREATE, ADD_BLOCK, CURRENT)
    ```
    `_managed_block` (`swerepo/init.py:290-310`) sets `kind="block"` **only** on `CREATE` and `ADD_BLOCK` — on `CURRENT`, `CHANGED`, `OUTDATED`, and `KEEP`, `a.kind` is `None`! So whenever `CODEOWNERS` already exists (`OUTDATED` or `CHANGED`), `codeowners` is `[]`, `not codeowners` is `True`, and `owner_written` is **always `True`**:
    1. Re-running `swerepo init --only github --mode team --code-owner @acme/devs --yes` after initial setup (`@dev`) rewrites `ruleset.json` to `team` (`require_code_owner_review: true`), leaves the unchanged SWERepo block in `.github/CODEOWNERS` `outdated` with `@dev` (never rewritten to `@acme/devs`), **and** overwrites `state.values["code_owner"] = "@acme/devs"` in `.swerepo.toml` — both enforcing `@dev` instead of `@acme/devs` on GitHub and corrupting `.swerepo.toml`'s merge-base input for `[blocks.".github/CODEOWNERS"]`.
    2. Even on a user-edited `CODEOWNERS` block (`CHANGED`), `state.values["code_owner"]` is overwritten because `codeowners` is `[]`.
  - **Suggested fix:** Match the `CODEOWNERS` action by path (`a.path == (ctx.detection.documents.get("codeowners") or github.CODEOWNERS)` rather than `a.kind == "block"`), and when `code_owner is not None` in this run, rewrite an unchanged recorded SWERepo block in `CODEOWNERS` via `replace_block_content` (already in `swerepo/blocks.py`, checking the block's fingerprint in `_check_unchanged` when `action.kind == "block"`), leaving `CHANGED` / `KEEP` untouched with a note (`"; what you gave (--code-owner) isn't in it: edit it yourself"`) and keeping the old recorded `code_owner` in `.swerepo.toml` when not written.
- **P5-F11 · Accept:** Managed `.github/pull_request_template.md` now reports `current` / `changed` / `outdated` on subsequent runs (`test_p5_f11_swereposs_own_pr_template_is_compared_not_called_yours`).
- **P5-F12 · Accept:** Both parts verified (`test_p5_f12_no_rewrite_when_the_wait_doesnt_change`, `test_p5_f12_a_version_1_workflow_isnt_rewritten_unless_the_wait_changes`, and `test_p5_f12_no_ci_is_respected`).
- **P5-F13 · Accept:** Non-object JSON (`null`, `[]`, `"text"`) from `gh api graphql` now exits `1` cleanly without crashing (`test_p5_f13_a_non_object_answer_is_an_error_not_a_crash`).

---

#### Reviewer: new findings

##### P5-F14 · suggestion · `swerepo/init.py:848, 1149-1151`
**What is wrong:** When `.github/swerepo/ruleset.json` is `KEEP` (e.g. a hand-written `solo` ruleset on an Organization-owned repository, like this repository) and `--mode` was not passed, `settings.mode` defaults to `"team"` (`owner_type == "Organization"`), so `init` prints `note mode: team (...)` (`line 848`) and, because `state.mode is None` (`line 1150`), writes `mode = "team"` into `.swerepo.toml` even though the kept `ruleset.json` has `required_approving_review_count: 0` (`solo`).
**How to reproduce:**
Inspect `uv run swerepo init --only github --dry-run` on this repository: prints `mode: team (...)` alongside `keep .github/swerepo/ruleset.json` (which is `solo`), and `plan.state_text` records `mode = "team"` unless `--mode solo` is passed.
**Suggested fix:** Add a 4-line `github.ruleset_mode(ruleset)` helper (`"team"` when `pull_request.required_approving_review_count >= 1` else `"solo"`), and when `files.ruleset_verb not in (CREATE, REWRITE)` and `mode is None`, take the displayed and recorded `mode` from the committed `ruleset.json` (just as `copilot_review` already does).

#### Readiness summary

`P5-F11`, `P5-F12`, and `P5-F13` are **Accepted**. Only the `CODEOWNERS` half of **P5-F10** (`a.kind == "block"` on `swerepo/init.py:1153` + rewriting an unchanged `CODEOWNERS` block on `--code-owner`) and optional suggestion **P5-F14** remain before sign-off and owner approval of `inv_ef31cc79` and `inv_faa5bef5`.

### Developer responses (round 3)

Both points reproduced first, as you described:
- **P5-F10, the CODEOWNERS half:** after `--code-owner @acme/devs`, the existing block's action had `kind = None`, so `.swerepo.toml` recorded `@acme/devs` while the file still named `@dev`.
- **P5-F14:** on this repository, the dry run printed `mode: team` beside the kept `solo` ruleset.

Both are fixed, with tests in `TestGeminiReviewRound3`. For each fix I put the old behaviour back (four breakages in all) and saw its test fail.

#### P5-F10 (CODEOWNERS half) · **Fix**, as you suggested
- **Matched by path:** the CODEOWNERS action is found by its path, not by `kind`, which is set on writes only.
- **Rewritten when unchanged:** when `--code-owner` is given in this run, an unchanged SWERepo block is rewritten in place (`_rewrite_block_if_asked`, a `rewrite` of kind `block`). Only the block's lines change, through `replace_block_content`; the person's lines stay byte for byte.
- **Checked twice:** the block's fingerprint is checked in the preflight and again just before the write, so a block edited after the plan stops the run with nothing written.
- **A changed block is kept:** with a note that the code owner given isn't in it, and the previously recorded owner stays in `.swerepo.toml`.

Tests: `test_p5_f10_a_new_code_owner_rewrites_an_unchanged_codeowners_block`, `test_p5_f10_a_changed_codeowners_block_keeps_the_recorded_owner`, `test_p5_f10_a_block_edited_after_the_plan_stops_the_rewrite`.

#### P5-F14 · **Fix**, as you suggested
`github.ruleset_mode` reads the mode from a ruleset: `team` when it requires an approval, `solo` otherwise. With a kept ruleset and no `--mode`, that mode is the one shown ("from the committed ruleset.json"), the question's default, and what is recorded. On this repository the dry run now says `mode: solo`. Test: `test_p5_f14_a_kept_rulesets_mode_is_shown_and_recorded`.

ADR-4e40 point 6 is updated for both.

#### The two proposed rules, tightened

SeamSpec's reviewer and a second review asked for changes before the owner approves. Both rules now cover them:

- **`inv_ef31cc79`:**
  - **An allow-list:** any `gh` call counts as a change unless it is `auth status`, a REST GET, or a GraphQL query, never a mutation. So a write spelled `--method`, or sent with a body and no method (which `gh` sends as a POST), still counts.
  - **Wording:** it now says GraphQL reads are queries, not "only GET".
  - **Title:** it names the merge settings.
  - **`check` runs again after `--yes`,** so its live-ruleset comparison is covered.
  - **Request bodies are checked:** the PUT carries SWERepo's ruleset.
  - **The create path** (no `swerepo` ruleset yet) has its own test.
- **`inv_faa5bef5`:**
  - **The fake `gh` answers only `repos/acme/app/pulls/1/reviews`**, with `--paginate`, and fails anything else.
  - **Copilot's review arrives on the second ask,** which proves the loop waits and asks again.
  - **Values come from the job's own `env:` block:** `DRAFT`, `NUMBER` and `REPOSITORY`.
  - **Pull requests only:** the job's `if:` must limit it to pull requests.
  - **Drafts fail without asking GitHub.**
  - **The opt-out runs through the real `--no-copilot-review` flag.**

Each gap was reproduced against the new tests, and all eight were caught:
- a read sent with a body and no `-X`;
- a change spelled `--method`;
- a broken create path;
- the wrong reviews address;
- no `--paginate`;
- the job running on pushes;
- `DRAFT` mapped to the wrong value;
- no retry after the first ask.

Ready for round 4, or to close.

---

### Round 4

#### Reviewer: verification

**Verification run (macOS, uv 0.9.28, git 2.50, gh logged in — GET-only on GitHub):** Re-ran every command under "How to run", `swerepo check --base main --ci`, `uvx zizmor==1.32.0 --offline`, and all Round 2/3 reproduction probes:
- `uv sync` → clean (50 packages resolved, 47 audited).
- `uv run pytest` → **582 passed**; `GITHUB_ACTIONS=true TERM=dumb uv run pytest` → **582 passed**.
- `uv run ruff check . .seamspec/proposed/` and `uv run ruff format --check . .seamspec/proposed/` → clean (127 files formatted).
- `uv run seamspec verify --all` → **13 locked invariants passed**; `uv run seamspec verify --proposed inv_ef31cc79 --proposed inv_faa5bef5` → **2 proposed invariants passed**.
- `uvx zizmor==1.32.0 --offline` on rendered `swerepo-ci.yml` (`@2`) + `swerepo-privacy.yml` → **0 findings**.
- `uv run swerepo init --only github --dry-run` on this repository → exit `0`, GET-only, and now prints `mode: solo (...) (from the committed ruleset.json)`.
- `uv run swerepo check --base main --ci` → exit `0` (`0 missing, 0 changed by you, 3 outdated, 2 can't tell`).
- `uv run swerepo check --only github,security,ci` and `uv run swerepo threads 8` → GET-only and clean.

---

#### Reviewer: Round 3 dispositions

- **P5-F10 (CODEOWNERS half) · Accept:** `_rewrite_block_if_asked` (`swerepo/init.py:472-483`), path-based matching in `_new_state` (`swerepo/init.py:1184-1188`), the preflight + pre-write block fingerprint checks in `_check_unchanged` (`swerepo/init.py:1264-1273`), and byte-preserving `replace_block_content` in `apply` (`swerepo/init.py:1314-1318`) all work cleanly and are covered by `test_p5_f10_a_new_code_owner_rewrites_an_unchanged_codeowners_block`, `test_p5_f10_a_changed_codeowners_block_keeps_the_recorded_owner`, and `test_p5_f10_a_block_edited_after_the_plan_stops_the_rewrite` (plus verified in `Probe 1A`).
- **P5-F14 · Accept:** `github.ruleset_mode` (`swerepo/github.py:148-156`) and its plumbing in `_github`, `make_plan`, and `_new_state` (`swerepo/init.py:868-870, 1057-1059, 1177-1182`) display, prompt, and record a kept ruleset's actual mode when `--mode` wasn't passed — verified both in `test_p5_f14_a_kept_rulesets_mode_is_shown_and_recorded` and live on this repository's `--dry-run`.

---

#### Reviewer: new findings

None.

#### Sign-off

All 14 findings across Rounds 1–3 (`P5-F01`–`P5-F14`) are **Accepted**. Phase 5 is **ready to close**:
1. Owner approves the two proposed critical SeamSpec rules (`inv_ef31cc79` and `inv_faa5bef5`) via `uv run seamspec review`.
2. Archive `CODE_REVIEW.md` to `docs/reviews/phase-5.md` (ADR-20261119-9f87) and open the Phase 5 pull request.

### Closing

Round 4 found nothing new and accepted P5-F10 and P5-F14, so all 14 findings are accepted with regression tests. The review is closed.

- **Since Gemini's round 4 run:** at the owner's request, both proposed rules were tightened before approval:
  - **`inv_ef31cc79`:**
    - the request bodies must equal the committed `ruleset.json` and `repo-settings.json`;
    - `check --json` and `check --ci` run again once the files exist;
    - saying no in a terminal is tested, and the test confirms both GitHub questions were asked;
    - attached and `=` spellings of methods and bodies count as changes, and so does a GraphQL mutation sent through the fake `gh` with `--input -` or `--input=-`.
  - **`inv_faa5bef5`:**
    - `GH_TOKEN` must reach `gh`;
    - the job's `permissions:` hold only `pull-requests: read`;
    - `ready_for_review` sits under the `pull_request` trigger;
    - turning Copilot review off on a later run removes the wait.

  SeamSpec's reviewer read both as sound to approve, and the owner approved them. Now 15 rules are locked, and all pass. `seamspec spec --check` is clean after regenerating `docs/EARNED_SPEC.md`.
- **Noted for later:** `GitHub.find_ruleset` reads only the first 100 rulesets (`per_page=100`). A repository with more could get a second `swerepo` ruleset instead of an update. This is outside both rules.
- **Next:** the pull request for Phase 5, then a separate pull request that applies `github` to this repository.

---

## Copilot's review of PR #10

Copilot left 4 inline comments and a summary. Each was reproduced on the PR's code before any change, and each is fixed with a regression test in `TestCopilotReviewPR10` (`tests/test_github.py`). For each fix I put the bug back and saw a test fail (six breakages in all). No locked rule changed; all 15 pass.

| Thread | Finding | Response |
|---|---|---|
| `swerepo/github.py` `apply_ruleset` | A `ruleset.json` edited to another `name` was created or renamed on GitHub, and later runs couldn't find it | **Fix:** `github.not_applicable` refuses it: the plan says why and applies only the settings, `check` reports it as missing, and `apply_ruleset` refuses such a payload before sending |
| `swerepo/github.py` `apply_settings` | Every key of `repo-settings.json` was sent, so `"private": false` could make a private repository public | **Fix:** an allow-list of merge settings (`github.MERGE_SETTINGS`); other fields refuse the file the same way, and `apply_settings` refuses such a payload before sending |
| `swerepo/cli.py` next steps | On GitHub without `gh` (or logged out), the next steps said to commit on the default branch and create the repository | **Fix:** the plan tells the two apart (`Plan.github_remote`): on GitHub, the next steps keep the branch and pull request, then `gh auth login` and `swerepo init --only github` |
| `swerepo/init.py` `[github] applied` | A refused ruleset listing, or a settings file that isn't JSON, left an empty plan and recorded `applied = true` | **Fix:** `Plan.github_compared` records whether GitHub was read and both files compared; `applied` is true only then with nothing left to apply, kept when GitHub can't be read, and `apply_github` records it on the same condition |

ADR-20261123-4e40 point 6 and spec §12 are updated.
