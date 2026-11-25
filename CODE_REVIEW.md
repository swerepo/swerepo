# Code Review · Phase 8

**Status:** open · **Developer:** Claude · **Reviewer:** Gemini · **Owner decides:** ties, merges, SeamSpec approvals
**Process:** ADR-20261119-9f87. Finding IDs `P8-D<nn>` (design) / `P8-F<nn>` (implementation); severities `blocker | should-fix | suggestion | question`; responses Fix / Push back / Defer, then Accept / Maintain.

---

## Design review (round 0)

**Reviewer:** Gemini · **Date:** 2026-11-24 · **Branch:** `phase-8/design`

### Strengths

- **Replacing `openspec` with a native `SPEC.md` (`ADR-20261124-4d76`):** Checking OpenSpec's public documentation cleanly and retiring the Node.js 22, home-folder skill writes, silent 1.x block removals, and default-on telemetry in favour of a plain Markdown `SPEC.md` completes a zero-dependency four-part loop (`SPEC.md` intended ↔ `docs/adr/` why ↔ `docs/progress/` each change ↔ `docs/EARNED_SPEC.md` enforced) that this repository already dogfoods. Making `SPEC.md` an unrecorded starter file (like `README.md`, `PROGRESS.md` and `CHANGELOG.md`), keeping it out of governance-only `CODEOWNERS`, and omitting a `--base` diff check so bug fixes and refactors cause zero alert fatigue are all the right calls.
- **Two-tier `v0.2` Phase 10 layout (`ADR-20261124-4d76` point 7):** Pairing root `docs/spec-system@1` with per-service `<service>/SPEC.md` (`docs/spec@1`) and `[projects.adopted."<service>"] spec` aligns cleanly with `[adopted] spec` at the root and `[projects.inputs."<service>"]` (`swerepo/state.py:320-335`), requiring no breaking change to v0.1's state schema.
- **Six complete, universal components and a hard no-publishing boundary (`ADR-20261124-152d`):** Removing `openspec` and `release` eliminates every `LATER` / `?` placeholder in Standard 1 and ensures SWERepo never wires up external registry publishing on user repositories.
- **Split build/publish/release pipeline and dual provenance (`ADR-20261124-4699`):** Building and signing SLSA build provenance (`actions/attest-build-provenance`) *before* human approval, pausing `publish` on the `pypi` environment (`prevent_self_review: false` for solo mode, `v*` tag policy, `id-token: write` only) to upload the frozen artifact via `pypa/gh-action-pypi-publish` (adding PyPI PEP 740 publish attestations without checking out or rebuilding code), and isolating `contents: write` to `github-release` are well-separated.
- **Immutability and wheel-purity rules (`ADR-20261124-41e9`):** Failing (rather than skipping) when the wheel check cannot run, checking *all* `v*` tags parsed by `packaging.version.Version` (passing before the first tag, failing on shallow clones, and explicitly handling `.git`-less staged-tree copies), and updating unreleased `ci/workflow@2` in place before `v0.1.0` are all well reasoned (`swerepo update` will rewrite this repository's `.github/workflows/swerepo-ci.yml` cleanly because `written == rendered`).

---

### Findings

#### P8-D01 · blocker · `docs/adr/ADR-20261124-4699-swerepo-releases-itself-through-a-release-workflow-in-this-r.md:29-44`
**`release.yml` needs `enable-cache: false` on every `setup-uv` step to pass `zizmor`, explicit `needs:` / `contents: read` gating, `main`-branch ancestry verification, and checkout-free `github-release`**

- **Failing scenario (verified against `zizmor==1.32.0 --offline`):**
  1. *`zizmor` high-severity failure (`ADR-20261124-4699:43`):* Line 43 specifies *"no caching in any job that builds or publishes"*. Tested against `uvx zizmor==1.32.0 --offline`, any workflow triggered by `on: push: tags: ["v*"]` fails with **`error[cache-poisoning]` (high severity, exit 14)** on **every** `astral-sh/setup-uv` step in the workflow—including `test` and `check`, not just `build`—unless `enable-cache: false` is set explicitly on each one. Without it, `swerepo-ci.yml`'s `workflow-audit` job will fail `ci-ok`.
  2. *Missing job dependencies & `main`-ancestry check (`ADR-20261124-4699:30-37, 41`):* Point 1 states `github-release` runs *"after `publish`"*, without stating `needs: [check, test]` on `build` or `needs: [build]` on `publish`, omits `contents: read` on `check`, `test`, and `build` under top-level `permissions: {}` (line 41), and in `check` (line 30) checks only `[project] version` and `CHANGELOG.md` without checking that the tagged commit is on `main`. If `build` runs in parallel with `check`/`test`—or if a `v*` tag is pushed from an unmerged branch commit—`actions/attest-build-provenance` signs permanent public Sigstore provenance for `swerepo/swerepo` and opens the `pypi` approval prompt (whose GitHub UI displays only the tag name, not whether the commit landed on `main`) before tests or branch lineage are verified.
  3. *Checkout inside `github-release` (`contents: write`, line 37) & provable artifact binding (lines 32–36):* Checking out the repository inside `github-release` exposes a `contents: write` token in a workspace with repository files, and uploading `dist/*` without recording SHA-256 digests leaves no in-log check tying `publish`'s downloaded files to `build`'s attested files (or excluding unexpected sidecar files in `dist/`).
- **Recommendation:**
  Update `ADR-20261124-4699` points 1–2 to specify:
  1. `enable-cache: false` on **every** `astral-sh/setup-uv` step across all jobs in `release.yml`.
  2. Explicit job graph and permissions: `check` (`contents: read`), `test` (`contents: read`), `build` (`needs: [check, test]`; `contents: read`, `id-token: write`, `attestations: write`), `publish` (`needs: [build]`; `id-token: write`), `github-release` (`needs: [publish]`; `contents: write`).
  3. In `check`, verify the tagged commit is on `main` (`git fetch origin main` or `fetch-depth: 0`, then `git merge-base --is-ancestor HEAD origin/main`), extract that version's changelog section into an artifact (or job output), and in `build` upload only `dist/*.whl` and `dist/*.tar.gz` plus their `SHA256SUMS` (verified via `sha256sum -c` in `publish` before `pypa/gh-action-pypi-publish`), so `github-release` downloads the artifacts and runs `gh release create "$TAG" dist/* --verify-tag --notes-file …` with **no `actions/checkout` at all**.
- **Developer response (Claude):** **Fix.** Verified: each point holds, and a cached `setup-uv` in any job of a tag-triggered workflow is a high `cache-poisoning` finding. ADR-20261124-4699 points 1 to 3 now say:
- **the job graph and permissions:** `check` and `test` (`contents: read`); `build` (`needs: [check, test]`; `contents: read`, `id-token: write`, `attestations: write`); `publish` (`needs: [build]`; `id-token: write`); `github-release` (`needs: [publish]`; `contents: write`). Nothing is built or attested before `check` and `test` pass;
- **`check`** verifies the tagged commit is an ancestor of `origin/main`, and extracts the version's changelog section into a `release-notes` artifact;
- **`build`** keeps only `dist/*.whl` and `dist/*.tar.gz`, with a `SHA256SUMS` file, and **`publish`** runs `sha256sum -c` before uploading;
- **`github-release`** has no checkout: it downloads the files and the notes and runs `gh release create … --verify-tag` against `$GITHUB_REPOSITORY`;
- **`enable-cache: false`** on every `setup-uv` step.
- **Reviewer (round 1):** Accept. Verified in `docs/adr/ADR-20261124-4699-swerepo-releases-itself-through-a-release-workflow-in-this-r.md:29-57` and `SWEREPO-SPEC.md:710`: the job graph, minimal per-job permissions, `origin/main` ancestry check, `SHA256SUMS` verification in `publish`, checkout-free `github-release` against `$GITHUB_REPOSITORY`, and `enable-cache: false` across every `setup-uv` step address all three scenarios.

---

#### P8-D02 · blocker · `docs/adr/ADR-20261124-4d76-specs-are-a-native-spec-md-kept-by-docs-and-agents-and-opens.md:30,52-53`
**Adding `agents/block@3` will fail locked critical SeamSpec rule `inv_9265607a` unless superseded in Phase 8**

- **Failing scenario:**
  `ADR-20261124-4d76:30` introduces a new version of `agents/block` (`agents/block@3`) for rule 10 and `update-spec.md`, while lines 52–53 list `"Enforced Invariants: None yet"`. Locked critical rule `inv_9265607a` (`.seamspec/tests/test_inv_9265607a.py:62,72,82`) hardcodes `"agents/block@2"` as the target version that `swerepo update` upgrades `agents/block@1` to (`new = TemplateStore().get("agents/block@2").render(...)`, `assert "agents/block@2" in dry.output`, `assert block.content == new`). Creating `swerepo/templates/agents/block/3.md` makes `update` upgrade `block@1` → `block@3`, immediately failing `inv_9265607a` and blocking commits and CI. *(Note also `.seamspec/tests/test_inv_60788941.py:167-169`, which computes the first changed line between `block@1` and `block@2`—keep rule 7's line differing from `block@1` in `block@3` so `inv_60788941` stays green.)*
- **Recommendation:**
  Note in `ADR-20261124-4d76` ("Enforced Invariants") that Phase 8's implementation PR will request a supersede of `inv_9265607a` whose replacement resolves the latest `agents/block` template dynamically via `TemplateStore().latest("agents", "block")`, so neither `block@3` nor v0.2 template bumps trip on a hardcoded version number.
- **Developer response (Claude):** **Fix** (the owner agreed, 2026-11-24). Verified: `.seamspec/tests/test_inv_9265607a.py:62,72` names `agents/block@2`. ADR-20261124-4d76's Enforced Invariants now plan the supersede in the implementation PR, with a replacement whose test finds the latest version itself (`TemplateStore().latest("agents", "block")`); the locked test is never edited. `inv_60788941` stays green: it edits the first line where `@1` and `@2` differ, and `@3` keeps `@2`'s change there. The implementation PR runs both before asking for the owner's review.
- **Reviewer (round 1):** Accept. Verified in `docs/adr/ADR-20261124-4d76-specs-are-a-native-spec-md-kept-by-docs-and-agents-and-opens.md:67-70` and the owner's answer #2.

---

#### P8-D03 · should-fix · `docs/adr/ADR-20261124-4699-swerepo-releases-itself-through-a-release-workflow-in-this-r.md:57-58`
**Bumping `pyproject.toml` from `0.1.0.dev0` to `0.1.0` in the release PR breaks 6 unit tests (and `release.yml`'s `test` job)**

- **Failing scenario (reproduced by running `pytest` with `swerepo.__version__ = "0.1.0"`):**
  Throughout Phases 0–7, `swerepo.__version__` has been `"0.1.0.dev0"`, so `ci.released()` (`swerepo/ci.py:53-59`) returned `False`. When step 5.1 of `ADR-20261124-4699` sets `version = "0.1.0"`, `ci.released()` flips to `True` and `ci.swerepo_command()` returns `"uvx swerepo==0.1.0"` instead of `""`. Six unit tests immediately fail:
  - `tests/test_init_ci.py:59`, `tests/test_init_ci.py:124`, `tests/test_init_ci.py:307`, `tests/test_security.py:74`, and `tests/test_init.py:94` assume `swerepo.__version__` is unreleased (`"governance" not in jobs`, `swerepo-privacy.yml` not created, or `privacy_command == ci.SWEREPO_FROM_GITHUB`) without monkeypatching `swerepo.__version__`.
  - `tests/test_update.py:456` sets `monkeypatch.setattr(ci, "released", lambda: True)` (zero-argument lambda), which raises `TypeError: <lambda>() takes 0 positional arguments but 1 was given` at `swerepo/ci.py:169` (`released(version)`) once `recorded` holds `"uvx swerepo==0.1.0"`.
  *(All 26 locked `.seamspec/tests/` invariants were also simulated under `0.1.0` and passed.)*
- **Recommendation:**
  Fix all 6 tests in Phase 8's implementation PR (monkeypatching `swerepo.__version__` to `"0.1.0.dev0"` in tests specifically exercising unreleased behavior, changing `lambda: True` to `lambda *_: True` in `tests/test_update.py:456`, and adding a test under a released version), and note `uv lock` alongside the version bump in `ADR-20261124-4699` step 5.1 so `uv sync --locked` succeeds in CI and `release.yml`.
- **Developer response (Claude):** **Fix.** Verified: `ci.released()` and `ci.swerepo_command()` follow `swerepo.__version__`, and `tests/test_update.py:456` patches `released` with a lambda that takes no argument. In the implementation PR, the tests that assume an unreleased SWERepo pin the version they mean (the unreleased cases patch `swerepo.__version__`; the lambda takes `*_`), and one test covers a released version. The version bump then changes no test. ADR-20261124-4699 point 5 adds `uv lock` beside the bump, so `uv sync --locked` passes.
- **Reviewer (round 1):** Accept. Verified in `docs/adr/ADR-20261124-4699-swerepo-releases-itself-through-a-release-workflow-in-this-r.md:76,101`.

---

#### P8-D04 · should-fix · `docs/adr/ADR-20261124-4d76-specs-are-a-native-spec-md-kept-by-docs-and-agents-and-opens.md:28,30`
**`SPEC.md` adoption rules conflate default root `SPEC.md` with `[adopted] spec`, leave cross-location ambiguity undefined, and omit `update` / `state` details**

- **Failing scenario:**
  1. *Second-run idempotence on default `SPEC.md` (`ADR-20261124-4d76:28` vs `SWEREPO-SPEC.md:390`):* Line 28 says *"`SPEC.md`, `docs/SPEC.md` or a root `<PROJECT>-SPEC.md` … is recorded as `[adopted] spec = \"<path>\"`"*. Because `SPEC.md` is an unrecorded starter file, `init` creates `SPEC.md` on run 1 without recording `[adopted] spec`; on run 2, `SPEC.md` exists on disk. If root `SPEC.md` caused `[adopted] spec = "SPEC.md"` to be written, run 2 would modify `.swerepo.toml` and **fail locked `inv_1002d669`**. Root `SPEC.md` is the default (`keep — yours`), whereas `[adopted] spec` is only for non-default paths (`SWEREPO-SPEC.md:390`).
  2. *Candidate matching & ambiguity (`ADR-20261124-4d76:28`):* Sentence 1 names `<PROJECT>-SPEC.md` (one name), while sentence 2 says *"When several root `*-SPEC.md` files match, none is guessed"*, leaving unclear: (a) whether any root `*-SPEC.md` (case-insensitively) or only `<PROJECT>-SPEC.md` is matched (for instance when folder name `goldenrepo` differs from `[project] name = "swerepo"`), (b) what happens when both `docs/SPEC.md` and `FOO-SPEC.md` (or `SPEC.md` and `docs/SPEC.md`) exist, and (c) what `init --yes` writes (`NOTE`, no `SPEC.md` created?), what `agents/block@3` renders for the spec path, and what `check` (`docs.spec`) reports when ambiguous.
  3. *Upgrading existing repositories via `swerepo update`:* When this repository runs `swerepo update` to move to `agents/block@3` and `prepare-pr@2`, `[adopted] spec` is not yet in `.swerepo.toml`. Spec detection must run before `compute_values` (`swerepo/init.py:1520`), record `"spec"` in `RECORDED_VALUES`, validate `[adopted] spec` with `check_path` (`swerepo/state.py:299-304, 612-614`) and `inside(root, ...)`, and save newly detected `[adopted] spec` in `_new_state` during `update` as well as `init`. *(Also add `SPEC.md` to the starter-file list in `SWEREPO-SPEC.md:424`.)*
- **Recommendation:**
  Clarify point 2 of `ADR-20261124-4d76` (and `SWEREPO-SPEC.md:424, 548`): an existing root `SPEC.md` is kept as the default without setting `[adopted] spec` (unless another candidate also exists—decide whether `SPEC.md` wins or reports ambiguity); when `SPEC.md` is absent and `[adopted] spec` is unset, match `docs/SPEC.md` and any root `*-SPEC.md` case-insensitively (`docs/EARNED_SPEC.md` excluded)—adopting `[adopted] spec` when unique, or emitting a `NOTE` (writing no `SPEC.md`, rendering `"SPEC.md"` in `agents/block@3`, and reporting the ambiguity in `check`) when multiple exist.
- **Developer response (Claude):** **Fix**, with the owner's answer to question 1. ADR-20261124-4d76 point 2 and spec §6.7 and §14 now define the lookup, the same for `init` and `update`:
1. `[adopted] spec`, when set, is the spec, checked like any recorded path; nothing is looked for.
2. Otherwise the candidates are the root `SPEC.md`, `docs/SPEC.md` and any root `*-SPEC.md`, case-insensitively, never `docs/EARNED_SPEC.md`.
3. None: the starter `SPEC.md` is written, and nothing is recorded, so the second run finds it as the only candidate and changes nothing (inv_1002d669).
4. One: a root `SPEC.md` is kept as the default with nothing recorded; any other is recorded as `[adopted] spec`, by `update` too, so this repository adopts `SWEREPO-SPEC.md` on its next `update`.
5. Several, the root `SPEC.md` among them or not: none is guessed. The plan lists them and how to record one, no `SPEC.md` is written, and `check` reports `✗ docs.spec`.

The path is an input of the templates that name the spec (`spec`, `SPEC.md` by default), so recording it later makes them outdated and `update` brings them in line. §9's list of starter files now includes `SPEC.md`. For v0.2, Phase 10, the owner's note is in ADR-20261124-4d76 point 7 and spec §11: inside a service, `<service>/SPEC.md` governs that service's behaviour, and the root `SPEC.md` covers what crosses services.
- **Reviewer (round 1):** Accept. Verified in `docs/adr/ADR-20261124-4d76-specs-are-a-native-spec-md-kept-by-docs-and-agents-and-opens.md:28-37,53` and `SWEREPO-SPEC.md:251,424,481,548-555`: the five-step lookup preserves `inv_1002d669`, handles `update` adoption cleanly, refuses to guess when multiple candidates exist, and records the Phase 10 service-spec priority.

---

#### P8-D05 · should-fix · `docs/adr/ADR-20261124-41e9-two-rules-guard-the-shipped-package-no-publishing-footprint.md:25-38,52`
**Tighten the two SeamSpec rules: offline/sandbox-safe wheel build + `openspec` check in Rule 1, code-built templates (`github/ruleset@1`, `repo-settings@1`) + worktree `.git` check in Rule 2, and `fetch-tags: true` in `seamspec/workflow@1`**

- **Failing scenario (verified empirically):**
  1. *Rule 1 sandbox panic & cold-cache network access (`ADR-20261124-41e9:26,52`):* Plain `uv build --wheel` resolves `[build-system]` in a fresh isolated venv on every commit/stop (reaching PyPI on a cold cache, `0.15s` with `--offline`) and **panics with exit 101** inside macOS Seatbelt sandboxes (`system-configuration/dynamic_store.rs:154: Attempted to create a NULL object`, affecting Antigravity review runs per `ADR-20261121-8259`). Adding `uv_build>=0.9.28,<0.10.0` to `[dependency-groups] dev` (already the `[build-system]` backend, not a runtime dependency) lets Rule 1 build the wheel completely offline in-process via `uv_build.build_wheel(str(tmp_path))` in `~0.02s` inside any sandbox (or fall back to `uv_build.build_wheel` when `uv build --wheel --offline` cannot run in a sandbox), still failing hard if building fails. In addition, lines 27–28 check `"release"` and three strings (`gh-action-pypi-publish`, `uv publish`, `twine upload`), omitting `openspec` (`ADR-20261124-152d`) and other common publishers (`poetry publish`, `hatch publish`, `flit publish`, `upload.pypi.org`).
  2. *Rule 2 blind spot on code-built templates (`ADR-20261124-41e9:33`, `swerepo/github.py:4-6,61-100`):* Rule 2 checks only files under `swerepo/templates/`. Yet `.github/swerepo/ruleset.json` and `repo-settings.json` are recorded in `.swerepo.toml` as `github/ruleset@1` and `github/repo-settings@1` and rebuilt in Python (`_ruleset_v1`, `_repo_settings_v1`) for `update`'s 3-way merge (`ADR-20261124-2452:77`). Mutating `_ruleset_v1` in Phase 9 instead of adding `_ruleset_v2` would break 3-way merges for every `0.1.0` repository while Rule 2 passes.
  3. *Rule 2 worktrees & `seamspec/workflow@1` (`ADR-20261124-41e9:35-37`, `swerepo/templates/seamspec/workflow/1.yml:21-24`):* In a git worktree `.git` is a file, so checking `.is_dir()` instead of `(ROOT / ".git").exists()` would misread a worktree as "without git history" and pass without checking tags; and unreleased `seamspec/workflow@1` (which `SWEREPO-SPEC.md:256` promises runs the same steps as `swerepo-ci.yml`'s `seamspec` job) is missing `fetch-tags: true`.
- **Recommendation:**
  1. Add `uv_build>=0.9.28,<0.10.0` to `[dependency-groups] dev` so Rule 1 builds the wheel offline without Seatbelt panics, assert `COMPONENTS == ("docs", "agents", "ci", "security", "github", "seamspec")` (covering `openspec` too), and include `poetry publish`, `hatch publish`, `flit publish`, and `upload.pypi.org` in the forbidden-string check.
  2. In Rule 2, check `(ROOT / ".git").exists()` and `git rev-parse --is-shallow-repository == "true"`, and also lock the rendered JSON fingerprints of released code builders (`github/ruleset@1`, `github/repo-settings@1`) across a fixed matrix of `Settings` inputs once `v0.1.0` is tagged (or document why if covered separately).
  3. Add `fetch-tags: true` in place to unreleased `swerepo/templates/seamspec/workflow/1.yml:21-24` alongside `ci/workflow@2`.
- **Developer response (Claude):** **Fix**, except for one sub-point (pushed back):
1. **Rule 1** builds the wheel in its own process through `uv_build.build_wheel`. `uv_build` joins `[dependency-groups] dev` with `[build-system]`'s version range, so there's no network, no `uv` subprocess and no sandbox panic, and it still fails when the build fails. The publishing strings now include `poetry publish`, `hatch publish`, `flit publish` and `upload.pypi.org`.
   - **Push back** on asserting the exact six components: that would turn any future component into a supersede of a rule about publishing. The rule checks that `release` is absent; `openspec`'s removal is ordinary tests' job (ADR-20261124-152d).
2. **Rule 2** now also covers renders put together in Python, and wider than the finding: besides the `github` builders, `ci.py` assembles `ci/workflow` and `ci/pyproject`. The release PR commits `tests/released/<version>.json` with the fingerprints `rebuild.rebuild` produces for every released template id over a fixed set of inputs that covers each branch. Rule 2 protects `tests/released/` like the templates and checks that today's code reproduces each fingerprint. A `.git` file (a worktree) counts as git.
3. **`seamspec/workflow@1`** (unreleased) gains `fetch-tags: true` in place, as `ci/workflow@2` does.
- **Reviewer (round 1):** Accept (including the pushback). Keeping Rule 1 scoped strictly to the publishing-footprint invariant (`"release"` absent, no `--release`/`--no-release` flags, wheel files confined to `swerepo/`, and the seven publishing strings absent) is the right call so future non-publishing components never force superseding a publishing rule, while unit tests in `ADR-20261124-152d` enforce `openspec`'s removal. Extending Rule 2 through `rebuild.rebuild` (`swerepo/rebuild.py:98-116`) and `tests/released/<version>.json` (`docs/adr/ADR-20261124-41e9-two-rules-guard-the-shipped-package-no-publishing-footprint.md:34-39,58`) is also stronger than the original suggestion because `ci.render_workflow` (`swerepo/ci.py:39,404`, e.g. `BASE_JOBS`) and `ci.settings_block` assemble renders in Python too, and keeping per-release fingerprints in `tests/released/` avoids superseding Rule 2 at future releases. *(See `P8-D10` below for one gap between `tests/released/<version>.json`, pre-tag execution, and the immutable `v*` tag ruleset.)*

---

#### P8-D06 · suggestion · `docs/adr/ADR-20261124-4d76-specs-are-a-native-spec-md-kept-by-docs-and-agents-and-opens.md:29-34,59`
**Include `.github/copilot-instructions.md` (and `CONTRIBUTING.md`) in the `SPEC.md` update nudges**

- **Failing scenario:**
  `ADR-20261124-4d76:59` states: *"there is no automatic check, by the owner's choice. Reviewers (Copilot included) are the guard, through the pull-request template's checklist."* Copilot code review reads `.github/copilot-instructions.md`, not `.github/pull_request_template.md`, when deciding what to flag on a diff, and `swerepo/templates/github/copilot-instructions/1.md:10-15` currently tells Copilot to flag missing progress entries and ADRs without mentioning the spec. Likewise `swerepo/templates/docs/contributing/1.md` lists ADRs and progress entries for human contributors without mentioning `SPEC.md`.
- **Recommendation:**
  Add a bullet in `github/copilot-instructions@2` telling Copilot to comment on *"a change to user-visible behaviour, CLI flags, APIs or configuration without updating `@@spec@@`"* (unlike a static `--base` rule, Copilot distinguishes refactors and bug fixes from behaviour changes), and mention updating `SPEC.md` on behaviour changes in `docs/contributing`.
- **Developer response (Claude):** **Fix.** ADR-20261124-4d76 point 3 and spec §6.1 and §6.5 add a new `github/copilot-instructions` version, asking Copilot to comment on a change to user-visible behaviour, CLI flags, APIs or configuration that leaves the spec as it was (it can tell a refactor from a behaviour change, which a fixed rule can't), and a new `docs/contributing` version that mentions keeping the spec current.
- **Reviewer (round 1):** Accept. Verified in `docs/adr/ADR-20261124-4d76-specs-are-a-native-spec-md-kept-by-docs-and-agents-and-opens.md:6,43-44` and `SWEREPO-SPEC.md:146,214,252`.

---

#### P8-D07 · should-fix · `docs/adr/ADR-20261124-152d-standard-1-has-six-components-and-swerepo-never-sets-up-pack.md:29-37`, `SWEREPO-SPEC.md:561-571,585`
**Complete the `openspec` / `release` removal touchpoints (`cli.py` help text, `test_check.py`/`test_init.py`, and `SWEREPO-SPEC.md` §15)**

- **Failing scenario:**
  1. In `swerepo/cli.py:275-276`, `init`'s help text still reads *"This version applies `docs`, `agents`, `ci`, `security`, `github` and `seamspec`; the others come in later phases"* (and `cli.py:3-4` still describes partial phase rollout); `swerepo/init.py:40-41,55,1598,1617` still carries `AVAILABLE`, `LATER`, and `LATER_VERB`; and `tests/test_check.py:77-80,320-321` and `tests/test_init.py:24,209-210` explicitly assert `openspec.chosen == NOT_CHOSEN`, `only=["openspec"]`, and `LATER_VERB`. *(Also `ADR-20261124-152d:34` says `"no --only, --no-openspec..."`—clarify `"no --only openspec, --only release..."` so it doesn't read as dropping `--only`.)*
  2. In `SWEREPO-SPEC.md:562-570`, the `swerepo check` example removed `openspec` without adding `docs.spec` (`SPEC.md`), and `SWEREPO-SPEC.md:585` still states *"checks a later phase adds show as `?` naming that phase"*, contradicting `ADR-20261124-152d` point 1 (*"no `LATER` entries, and no `?` items naming Phase 8"*).
- **Recommendation:**
  Update `SWEREPO-SPEC.md:562-570, 585`, clarify `ADR-20261124-152d:34`, and include `cli.py` docstrings, `init.py`'s `AVAILABLE`/`LATER`/`LATER_VERB`, and the `test_check.py` / `test_init.py` updates in the removal touchpoints.
- **Developer response (Claude):** **Fix.** ADR-20261124-152d point 2 now lists `cli.py`'s docstring and `init`'s help text, `init.py`'s `AVAILABLE`, `LATER` and `LATER_VERB`, and the tests in `tests/test_check.py` and `tests/test_init.py` that assert the placeholders. The flags line now reads `--only openspec`, `--only release`, `--no-openspec`, `--no-release`, `--openspec`, `--release`, with `--only` itself kept. In the spec, §15's example shows `✓ spec (adopted: LEGACY-API-SPEC.md)`, and the rule for later checks says standard 1 has none left.
- **Reviewer (round 1):** Accept. Verified in `docs/adr/ADR-20261124-152d-standard-1-has-six-components-and-swerepo-never-sets-up-pack.md:33-38` and `SWEREPO-SPEC.md:571,594` (the `6 missing` summary line in §15 also stays exact).

---

#### P8-D08 · should-fix · `README.md:7`, `pyproject.toml:11`, `docs/adr/ADR-20261124-4699-swerepo-releases-itself-through-a-release-workflow-in-this-r.md:56-61`
**`README.md` (rendered on PyPI for `0.1.0`) still says *"pre-alpha, under construction — only `docs` and `agents` work"* and uses relative links that 404 on `pypi.org`**

- **Failing scenario:**
  `pyproject.toml:5` sets `readme = "README.md"`, so PyPI displays `README.md` as the public project page when `0.1.0` is published. Today `README.md:7` still states *"Status: pre-alpha, under construction. `swerepo check` works today (read-only), and `swerepo init` sets up the `docs` and `agents` components; the other components and `update` are next"*, lacks user install/quickstart commands (`uv tool install swerepo`, `swerepo init`, `swerepo check`, `swerepo update`), and uses relative Markdown links (`SWEREPO-SPEC.md`, `docs/PROGRESS.md`, `CONTRIBUTING.md`) that 404 on `pypi.org`. `pyproject.toml:11` also still declares `"Development Status :: 2 - Pre-Alpha"`, and `SWEREPO-SPEC.md:3` still says `draft`. None of these are listed in `ADR-20261124-4699`'s release sequence or `docs/PROGRESS.md`.
- **Recommendation:**
  Add rewriting `README.md` for `0.1.0` users (installation, quickstart, the six components, and full `https://github.com/swerepo/swerepo/blob/main/...` links so PyPI links resolve) and updating `pyproject.toml`'s Trove classifier (`3 - Alpha` or `4 - Beta`) to the Phase 8 implementation or `0.1.0` release PR plan.
- **Developer response (Claude):** **Fix.** ADR-20261124-4699 point 5: the release PR rewrites `README.md` for people installing from PyPI (what it is, `uv tool install swerepo`, a quickstart with `check`, `init` and `update`, the six components, and absolute `https://github.com/swerepo/swerepo/blob/main/…` links). It also moves the classifier to `Development Status :: 3 - Alpha` and updates the spec's status line.
- **Reviewer (round 1):** Accept. Verified in `docs/adr/ADR-20261124-4699-swerepo-releases-itself-through-a-release-workflow-in-this-r.md:78-79`.

---

#### P8-D09 · suggestion · `docs/adr/ADR-20261124-4699-swerepo-releases-itself-through-a-release-workflow-in-this-r.md:79`
**Protect `refs/tags/v*` with a GitHub tag ruleset (`deletion` + `non_fast_forward`) alongside the `pypi` environment**

- **Failing scenario:**
  `ADR-20261124-4699:79` leaves a `v*` tag ruleset *"for later"* because the `pypi` environment's tag policy and human approval guard PyPI uploads. However, `ADR-20261124-41e9` Rule 2 uses git `v*` tags directly (rather than committed hashes) as the sole record of released templates: if `v0.1.0` were accidentally deleted or force-moved (`git push --force origin v0.1.0`), Rule 2's baseline would silently disappear or shift without failing.
- **Recommendation:**
  Add a lightweight tag ruleset on `swerepo/swerepo` targeting `refs/tags/v*` with `deletion` and `non_fast_forward` rules (applied with the owner's go-ahead alongside the `pypi` environment) so released `v*` tags cannot be deleted or force-moved.
- **Developer response (Claude):** **Fix** (the owner's answer to question 3). ADR-20261124-4699 point 3 adds a tag ruleset on `refs/tags/v*`, applied through `gh api` only after the owner's yes, alongside the `pypi` environment, and never shipped in `swerepo`. One addition to the recommendation: `deletion` and `non_fast_forward` alone would still let `v0.1.0` move to a later commit, because that move is a fast-forward. So the ruleset also has `update`. Creating new `v*` tags stays allowed. ADR-20261124-41e9 point 4 refers to it.
- **Reviewer (round 1):** Accept. Verified in `docs/adr/ADR-20261124-4699-swerepo-releases-itself-through-a-release-workflow-in-this-r.md:63-68` and `docs/adr/ADR-20261124-41e9-two-rules-guard-the-shipped-package-no-publishing-footprint.md:40`. Adding `update` alongside `deletion` and `non_fast_forward` closes a real gap: in GitHub tag rulesets, `creation` governs new `refs/tags/v*` refs (left open), whereas moving an existing lightweight tag forward to a descendant commit is a fast-forward ref update that only `update` blocks.

---

### Questions for the owner

1. **When both `SPEC.md` and another candidate (e.g., `docs/SPEC.md` or `FOO-SPEC.md`) exist in an established repository (`P8-D04`):** should root `SPEC.md` take priority automatically, or should SWERepo report both and ask the person to set `[adopted] spec`?
2. **Superseding `inv_9265607a` (`P8-D02`):** ok for Claude to request a supersede of `inv_9265607a` in the Phase 8 implementation PR so its test resolves the latest `agents/block` version dynamically instead of hardcoding `agents/block@2`?
3. **Protecting `v*` tags on `swerepo/swerepo` (`P8-D09`):** would you like a tag ruleset blocking deletion and force-pushes on `v*` tags applied alongside the `pypi` environment before `v0.1.0`?

### Owner's answers (2026-11-24)

1. **Several spec candidates:** list them and let the owner set `[adopted] spec`; never guess. For v0.2, Phase 10: inside a service, `<service>/SPEC.md` takes priority for that service's behaviour, and the root `SPEC.md` covers what crosses services. Done in ADR-20261124-4d76 points 2 and 7.
2. **Superseding `inv_9265607a`:** yes, in the Phase 8 implementation PR, with a replacement that finds the latest `agents/block` version itself. Planned in ADR-20261124-4d76.
3. **Protecting `v*` tags:** yes, with a tag ruleset on `swerepo/swerepo` only, applied after asking, alongside the `pypi` environment. Done in ADR-20261124-4699 point 3.

**Round 0 status:** every finding answered: eight fixed, and P8-D05 fixed except one sub-point pushed back (asserting the exact six components). Waiting for the reviewer's Accept or Maintain.

---

## Design review (round 1)

**Reviewer:** Gemini · **Date:** 2026-11-24 · **Branch:** `phase-8/design`

All nine Round 0 findings (`P8-D01` to `P8-D09`, including `P8-D05`'s pushback on not locking the six-component list inside a publishing rule and `P8-D09`'s `update` addition to the `refs/tags/v*` ruleset) are accepted. Checking the interaction between the two Round 1 extensions (`tests/released/<version>.json` in `ADR-20261124-41e9` and the immutable `v*` tag ruleset in `ADR-20261124-4699`) surfaced one gap:

### Findings

#### P8-D10 · should-fix · `docs/adr/ADR-20261124-41e9-two-rules-guard-the-shipped-package-no-publishing-footprint.md:34-36,58`, `docs/adr/ADR-20261124-4699-swerepo-releases-itself-through-a-release-workflow-in-this-r.md:30-34,75-80`
**Verify `tests/released/<version>.json` before the first tag, require it when `[project] version` is a release, and run `seamspec verify` in `release.yml`**

- **Failing scenario:**
  1. *Omitted snapshot frozen by the immutable tag ruleset (`ADR-20261124-4699:63-66,75-80`, `ADR-20261124-41e9:34-35`):* `ADR-20261124-41e9:35,58` introduces `tests/released/<version>.json` for the release PR, but `ADR-20261124-4699:75-80` (point 5.1, *"The release PR"*) omits it from the release-PR checklist, `pyproject.toml:55` sets `testpaths = ["tests"]` (so `release.yml`'s `test` job skips `.seamspec/tests/`), and neither Rule 2 nor `release.yml`'s `check` job checks that `tests/released/<version>.json` exists when `swerepo.__version__` is a released version (`ci.released() == True`). If `tests/released/0.1.0.json` (or `0.2.0.json`) is omitted from the release PR, both PR CI and `release.yml` pass; once `v0.1.0` is pushed, the new `refs/tags/v*` ruleset (`deletion`, `non_fast_forward`, `update`) prevents moving or recreating the tag, leaving that release's Python-built renders permanently unrecorded at `v0.1.0`.
  2. *Malformed or stale snapshot wedging Rule 2 after tagging (`ADR-20261124-41e9:34-36`):* Line 36 states *"before the first tag there is nothing released, so it passes."* If Rule 2 returns early when no `v*` tag exists rather than verifying any `tests/released/*.json` already in the working tree, a mistyped or stale `tests/released/0.1.0.json` committed in the `0.1.0` release PR passes `swerepo-ci.yml` untested (because `v0.1.0` is pushed only after merge). Once `v0.1.0` is pushed, the tag ruleset forbids moving `v0.1.0` and Rule 2's tag check forbids editing `tests/released/0.1.0.json`, wedging Rule 2 on the next commit until superseded.
- **Recommendation:**
  1. In `ADR-20261124-41e9` point 2: always verify every `tests/released/*.json` present in the working tree against `rebuild.rebuild` (even before the first `v*` tag and when `.git` is absent), and when `ci.released(swerepo.__version__)` is `True`, require `tests/released/{swerepo.__version__}.json` to exist and cover every released code-built/assembled template id (`ci/workflow@1`, `ci/workflow@2`, `ci/pyproject@1`, `github/ruleset@1`, `github/repo-settings@1`).
  2. In `ADR-20261124-4699`: add committing `tests/released/<version>.json` to point 5.1 (*"The release PR"*), and run `uv run --locked seamspec verify --all --ci` (with `fetch-tags: true` on `check`'s checkout) inside `release.yml`'s `check` job so Rule 1 and Rule 2 gate `build` at tag time as well.
- **Developer response (Claude):** **Fix.** Verified: `pyproject.toml` sets `testpaths = ["tests"]`, so `release.yml`'s `test` job never runs `.seamspec/tests/`, and nothing required the snapshot before the tag froze it.
  1. **ADR-20261124-41e9 point 2:**
     - Rule 2 checks every `tests/released/*.json` in the working tree against today's renders, before the first tag and without git too, so a wrong snapshot fails in the release PR's own CI.
     - When `ci.released()` is true, `tests/released/<version>.json` must exist and cover every template id assembled in code. The ids are derived from the code, not listed by hand: `github.BUILDERS`, and every `ci/workflow` and `ci/pyproject` version in the store. Today those are `ci/workflow@1`, `@2`, `ci/pyproject@1`, `github/ruleset@1` and `github/repo-settings@1`.
     - A script in `tools/` writes the file.
  2. **ADR-20261124-4699:**
     - point 1's `check` job runs `uv run --locked seamspec verify --all --ci` with tags fetched, so both rules gate `build` at the tag;
     - point 5's release PR includes `tests/released/0.1.0.json`.
- **Reviewer (round 2):** Accept. Verified in `docs/adr/ADR-20261124-41e9-two-rules-guard-the-shipped-package-no-publishing-footprint.md:36-38,60` and `docs/adr/ADR-20261124-4699-swerepo-releases-itself-through-a-release-workflow-in-this-r.md:34,79`. Checking every `tests/released/*.json` in the working tree before the first tag and without git, deriving the required code-built template ids dynamically from `github.BUILDERS` and the `ci/workflow` and `ci/pyproject` versions in `TemplateStore` whenever `ci.released()` is true, generating the snapshot from `tools/` (excluded from the wheel by Rule 1), and running `uv run --locked seamspec verify --all --ci` in `release.yml`'s `check` job close both gaps without needing future supersedes.

---

**Round 1 status:** `P8-D01` to `P8-D09` accepted; one new `should-fix` finding (`P8-D10`) open on verifying and requiring `tests/released/<version>.json` before `v*` tags lock it. Waiting for the developer's response.

**Developer (Claude):** `P8-D10` fixed (above). Waiting for the reviewer's Accept or Maintain.

**Design review status (round 2):** closed — all findings (`P8-D01` to `P8-D10`) fixed and accepted, and all owner questions answered. Ready for Phase 8 implementation.
