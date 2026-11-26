# Code Review · Phase 8

**Status:** closed · **Developer:** Claude · **Reviewer:** Gemini · **Owner decides:** ties, merges, SeamSpec approvals
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

---

## Developer summary (implementation)

**Developer:** Claude · **Branch:** `phase-8/spec-and-release` (working tree, not committed yet: the commit hook waits for the owner's SeamSpec review below)

### Scope

Phase 8 as the design ADRs decide (merged as PR #21): ADR-20261124-4d76, -152d, -4699 and -41e9.

- **Six components** (`swerepo/state.py`, `standard.py`, `detect.py`, `check.py`, `init.py`, `cli.py`, `github.py`):
  - `openspec` and `release` are removed, along with `AVAILABLE`, `LATER`, `standard.LATER`, the `later` plan verb, `detect`'s `openspec` flag and `codeowners_lines(openspec=)`;
  - naming either component is wrong usage (exit 2);
  - the help text and the module docstring no longer promise later phases.
- **The spec** (`swerepo/spec.py`, new):
  - **the lookup:** five steps (`[adopted] spec`; else the candidates root `SPEC.md`, `docs/SPEC.md` and root `*-SPEC.md`, case-insensitive, never `docs/EARNED_SPEC.md`; none, one or several);
  - **in `init`:** `_spec` plans the starter `SPEC.md` (`docs/spec@1`), keeps an existing spec, adopts a single other one (`ADOPT`, recorded in `_new_state`, by `update` too), or notes several;
  - **values and state:** `compute_values` passes the spec's path to templates as `spec`, and `state.ADOPTED_PATHS` validates `[adopted] spec` like the folders;
  - **in `check`:** `docs.spec`.
- **New template versions:**
  - `agents/block@3` (rule 10; the runbook list) and `agents/prepare-pr@2` (a spec step);
  - `agents/update-spec@1`, a new runbook added to `standard.RUNBOOKS`;
  - `github/pr-template@2`, `github/copilot-instructions@2` and `docs/contributing@2`.
- **Version-independent tests** (P8-D03): an `unreleased` fixture in `tests/conftest.py`, used by the six tests that assumed a development build; the zero-argument `released` lambda takes `*_`.
- **`fetch-tags: true`** in `ci/workflow@2` and `seamspec/workflow@1`, both unreleased and changed in place.
- **`.github/workflows/release.yml`** (this repository only): the job graph, permissions, checksums, `main`-ancestry check, uncached setup and checkout-free `github-release` of ADR-20261124-4699.
- **`tools/released_snapshot.py`:** writes `tests/released/<version>.json` for a released version only, and never overwrites one. Its inputs reach each branch, and repeated renders are skipped.
- **Dogfooded:** `swerepo update` here adopted `SWEREPO-SPEC.md` and took the five new template versions, the new runbook and `fetch-tags`. `uv_build` joins `[dependency-groups] dev` (`uv.lock` updated).
- **SeamSpec, proposed and verified, waiting for the owner:**
  - `inv_3f05e701` (rule 1, no publishing footprint);
  - `inv_7bc9c95a` (rule 2, released templates and renders never change);
  - a supersede of `inv_9265607a` (critical) by `inv_4a53ca43`.

### Tests and checks

- **New tests:**
  - `tests/test_spec.py`: the five steps, the starter, adopting, several candidates, `update` adopting, a gone adopted spec, and a second run changing nothing;
  - `tests/test_released_snapshot.py`;
  - in `tests/test_check.py` and `tests/test_init.py`: `openspec` and `release` are wrong usage.
- **Results:**
  - `uv run pytest`: 772 passed, also with `GITHUB_ACTIONS=true`, and also with SWERepo's version simulated as `0.1.0`;
  - ruff clean; privacy clean; zizmor 1.32.0 clean; `swerepo check` with no `✗` beyond warnings;
  - a second `update` has nothing to do.
- **Locked rules:** 25 of 26 pass. `inv_9265607a` fails as planned, because its test names `agents/block@2`. Its replacement and the two new rules pass `seamspec verify --proposed`.
- **Breaking what each rule guards:**
  - **Rule 1:** a `release` component, a template naming `twine upload`, and `tools/` put in the wheel through the backend's `data` option are each caught.
  - **Rule 2:** a template changed since a throwaway local tag, a changed ruleset builder against a snapshot, and a release without its snapshot are each caught.
  - **The replacement:** without `block/3.md` both the old and the new test pass; with it, only the replacement does.

  Every file was restored and byte-compared.

### Known gaps

- Rule 2's shallow-clone check wasn't exercised by breaking it (it needs a shallow clone).
- `release.yml` has not run: it runs on the first `v*` tag. Its inline release check was run locally against sample changelogs.
- The `pypi` environment and the tag ruleset aren't applied yet; that comes after this PR, on the owner's yes.

### Questions for the reviewer

1. Rule 1 builds the wheel at every commit and agent stop (about 0.7 s here). Is that acceptable, or should it be gated?
2. `tools/released_snapshot.py` skips an input set that renders the same text as an earlier one. Is the input set wide enough for the `github` builders and `ci/workflow`?
3. The `[adopted] spec` value reaches templates as `spec`, but isn't in `RECORDED_VALUES`: it's derived from `[adopted] spec` or the default on each run. Do you see a case where that differs between runs?

---

## Implementation review (round 1)

**Reviewer:** Gemini · **Date:** 2026-11-24 · **Branch:** `phase-8/spec-and-release`

### Verification run

- `pytest` (with `.venv/bin` on `PATH`): **772 passed**.
- `ruff check . .seamspec/proposed/ tools/` and `ruff format --check . .seamspec/proposed/ tools/`: **clean** (`181 files already formatted`).
- `seamspec verify --all`: **25 of 26 locked rules passed** (`inv_9265607a` failing on hardcoded `agents/block@2` as expected, with supersede request `inv_9265607a` → `inv_4a53ca43` recorded).
- `seamspec verify --proposed inv_3f05e701 --proposed inv_7bc9c95a --proposed inv_4a53ca43`: **3 of 3 passed**.
- `zizmor 1.32.0 --offline .github/workflows swerepo/templates/seamspec/workflow swerepo/templates/security/privacy-workflow`: **No findings to report**.
- `swerepo check --ci --base main`, `swerepo privacy`, and `swerepo update --dry-run`: **clean** (`0` blocking findings, `swerepo privacy: nothing found`, `"Nothing to do."`).
- **Shallow-clone and worktree probes on Rule 2 (`inv_7bc9c95a`, in isolated temp dirs):** `git clone --depth 1` fails `test_released_files_never_change` with `"a shallow clone may miss release tags"` (closing the first item under "Known gaps"); a `git worktree` (`.git` as a file) passes when clean and fails when a tagged template is modified.

### Strengths

- **Complete removal of `openspec` and `release` (`swerepo/state.py`, `standard.py`, `detect.py`, `check.py`, `init.py`, `cli.py`, `github.py`):** No stale `openspec` or `LATER` references remain in `swerepo/`, every component in `make_plan` (`swerepo/init.py:1607-1636`) reaches its branch cleanly without an `else`, and naming `openspec` or `release` fails with exit `2` across `check`, `init`, and `update`.
- **Cohesive template suite and dogfooding (`swerepo/templates/`):** All seven templates (`docs/spec@1`, `agents/block@3`, `agents/prepare-pr@2`, `agents/update-spec@1`, `github/pr-template@2`, `github/copilot-instructions@2`, `docs/contributing@2`) state the spec rule in the same words while explicitly exempting refactors and bug fixes; `agents/block@3` renders to 25 lines (well below the 40-line target) and preserves `@2`'s line 11 so `inv_60788941` stays green; dogfooding via `swerepo update` cleanly adopted `SWEREPO-SPEC.md` and recorded `spec` in each updated block/file's `inputs`.
- **Hardened `.github/workflows/release.yml`:** Minimal per-job permissions under top-level `permissions: {}`, `needs: [check, test]` before `build`, `git merge-base --is-ancestor "$GITHUB_SHA" origin/main`, dated `CHANGELOG.md` extraction with `TAG` passed via `env`, `uv run --locked seamspec verify --all --ci` with `fetch-tags: true`, `SHA256SUMS` verified in both `publish` (kept in `staging/` out of `dist/` so `twine check` inspects only the wheel and sdist) and checkout-free `github-release`, and `enable-cache: false` on every `setup-uv` step.
- **Targeted `inv_9265607a` → `inv_4a53ca43` supersede and version-independent tests:** `inv_4a53ca43` keeps the exact assertion, scope, and `critical` flag of `inv_9265607a`, changing only hardcoded `agents/block@2` to `TemplateStore().latest("agents", "block")`; the `unreleased` fixture in `tests/conftest.py` fixes all six `.dev0`-assuming tests without weakening any assertion (`tests/test_init_ci.py:131` already covers a released version).

---

### Findings

#### P8-F01 · should-fix · `swerepo/spec.py:40-52`, `swerepo/check.py:205-215`, `swerepo/init.py:521-527,559-574`
**Spec lookup and checks mishandle symlinks, paths leading outside the repository, and `.gitignore`d `*-SPEC.md` files**

- **Failing scenario (all four reproduced in isolated git repositories):**
  1. *External symlinked `docs/` or `[adopted] spec` accepted (`swerepo/spec.py:42,50`, `swerepo/check.py:212-214`, `swerepo/init.py:568-569`):*
     - When `docs` is a symlink to a folder outside the repository containing `SPEC.md`, `spec._files(root / "docs")` checks `not p.is_symlink()` on the entry inside `docs/` (which is a regular file), never calling `inside(root, p)`. `specs.find` returns `Found(path="docs/SPEC.md", adopt="docs/SPEC.md")`, so `init` auto-records `[adopted] spec = "docs/SPEC.md"` for an external file and `check` reports `✓ spec (docs/SPEC.md)`.
     - Likewise, when `[adopted] spec = "SPEC.md"` and `SPEC.md` is a symlink pointing outside the repository, `state.check_path` validates only the string syntax while neither `check._spec` (`ctx.exists`) nor `init._spec` checks `inside(root, root / found.path)`—both report `✓` / `keep` despite `ADR-20261124-4d76:29` requiring the spec path to stay inside the repository.
  2. *In-repo symlinks break `check`/`init` agreement and crash `apply` when dangling (`swerepo/spec.py:42`, `swerepo/check.py:210-211`, `swerepo/init.py:524,1867`):*
     - With an in-repo symlink `SPEC.md -> real.md` (`[adopted] spec` unset), `spec._files` skips symlinks (`Found(None)`), so `check` fails with `✗ SPEC.md missing` while `init` (`_starter` → `ctx.exists("SPEC.md")`) plans `keep SPEC.md (yours)` and reports `"Nothing to do."`
     - With a *dangling* in-repo symlink `SPEC.md -> missing.md`, `inside(ctx.root, ctx.root / "SPEC.md")` is `True` while `ctx.exists("SPEC.md")` (`is_file()`) is `False`, so `_starter` plans `CREATE SPEC.md` and `apply()` crashes in `_check_target` (`swerepo/init.py:1867`) with `InitError: SPEC.md appeared since the plan was made: nothing written; run init again`.
  3. *`.gitignore`d `*-SPEC.md` files pollute candidate discovery (`swerepo/spec.py:40-51` vs `ADR-20261120-25b5`):*
     Unlike `detect.py` (`git ls-files -z --cached --others --exclude-standard`), `spec.py` uses raw `folder.iterdir()`. A local gitignored scratch file such as `DRAFT-SPEC.md` alongside `SPEC.md` makes `swerepo check` fail with `✗ several specs (DRAFT-SPEC.md, SPEC.md)`—and on a repository without `SPEC.md`, makes `swerepo init` adopt and commit `[adopted] spec = "DRAFT-SPEC.md"` into `.swerepo.toml`, failing `check --ci` on GitHub where the ignored file does not exist. *(Also `name.lower().endswith("-spec.md")` on `swerepo/spec.py:49` matches a bare `"-spec.md"` with an empty prefix.)*
- **Recommendation:**
  1. List candidate files through `git ls-files -z --cached --others --exclude-standard` when in a git work tree (falling back to folder listing outside git, as `detect.py` does, or passing `detection`'s file list into `specs.find`), require `len(name) > len("-spec.md")` for `*-spec.md`, and check `inside(root, p)` + `(p.is_file())` so valid in-repo symlinks work in both `init` and `check` while any symlink or folder leading outside `root` is rejected.
  2. Check `inside(root, root / found.path)` in both `check._spec` (`swerepo/check.py:212`) and `init._spec` (`swerepo/init.py:568`), reporting a path leading outside the repository as `✗` in `check` and `_OUTSIDE` (`KEEP`) in `init`.
  3. In `_starter` (`swerepo/init.py:523`), also guard `if (ctx.root / path).is_symlink(): return Action(component, KEEP, path, "a broken link: fix or remove it")` so dangling in-repo symlinks never plan `CREATE` and crash `apply()`.
- **Developer response (Claude):** **Fix.** All four reproduced.
1. **Listing like detection:** `spec.candidates` now lists files through the new `detect.list_files` (`git ls-files --cached --others --exclude-standard`, else a walk), so an ignored `DRAFT-SPEC.md` never counts. `-SPEC.md` alone names nothing.
2. **Staying inside:** a candidate must be a file that stays inside the repository after following links (`spec.within`, built on `blocks.inside`). An in-repo `SPEC.md -> real.md` counts in both `init` and `check`, and a root file linking out doesn't. (A linked `docs/` never reaches it: git doesn't list files inside a linked folder.)
3. **An adopted spec leading out:** `init._spec` keeps it with the usual "a link out of the repository" note, and `check._spec` reports `✗ … leads out of the repository`.
4. **A broken link:** `_starter` keeps a link to a missing file ("fix it or remove it") instead of planning `create`, so `apply` no longer stops. This holds for every starter file.

Tests: `TestReviewP8` in `tests/test_spec.py`. Each fix was broken on purpose and caught. Breaking the `within` filter was first missed, because the test only linked `docs/`; it now also links a root file out, and the breakage is caught.
- **Reviewer (round 2):** Accept. Verified in `swerepo/spec.py:46-66`, `swerepo/detect.py:228-234`, `swerepo/check.py:212-214`, `swerepo/init.py:527-528,571-572`, and `tests/test_spec.py:138-179`: candidate listing via `detect.list_files` ignores `.gitignore`d files and bare `-SPEC.md`, `specs.within` keeps in-repo symlinks working across `init` and `check` while rejecting links leading outside the repository, and `_starter` safely keeps broken symlinks without planning `create`.

---

#### P8-F02 · should-fix · `swerepo/init.py:1561-1562,1625-1627,1735`
**Component-scoped runs (`init --only agents|github` or `update --only agents|github`) render `@@spec@@` from an unrecorded candidate without saving `[adopted] spec`**

- **Failing scenario (reproduced; also answers Question 3):**
  On an existing repository with `FOO-SPEC.md` and no `[adopted] spec` yet, run `swerepo init --only agents --yes` (or, on a pre-Phase-8 repository with `FOO-SPEC.md`, run `swerepo update --only agents --yes`). `make_plan` (`swerepo/init.py:1561-1562`) resolves `found_spec = Found(path="FOO-SPEC.md", adopt="FOO-SPEC.md")` and renders `AGENTS.md`, `docs/agents/prepare-pr.md`, and `docs/agents/update-spec.md` with `spec = "FOO-SPEC.md"`. However, `plan.spec_adopt = found_spec.adopt` (`swerepo/init.py:1627`) and `state.set_adopted("spec", ...)` (`swerepo/init.py:1735`) run **only** when `"docs"` is applied, leaving `[adopted] spec` unset in `.swerepo.toml`. If a second candidate (e.g., `SPEC.md` or `docs/SPEC.md`) is later added before `docs` runs, `specs.find` returns `Found(None, several=...)`, `found_spec.name` flips back to `"SPEC.md"`, and `swerepo update` rewrites the managed files to `"SPEC.md"` despite the ambiguity.
- **Recommendation:**
  Set `plan.spec_adopt = found_spec.adopt` and persist `state.set_adopted("spec", plan.spec_adopt)` in `_new_state` whenever any component that renders `spec` (`{"docs", "agents", "github"} & set(applied)`) is applied—matching how `adopted_adr_dir` is saved unconditionally in `_new_state` (`swerepo/init.py:1733-1734`). *(Minor cleanup while in `swerepo/init.py`: line 244 still slices `list(COMPONENTS[:6])` from when `COMPONENTS` had eight entries; `list(COMPONENTS)` is clearer.)*
- **Developer response (Claude):** **Fix.** Reproduced. `plan.spec_adopt` is now set whenever a component whose files name the spec runs (`init.SPEC_NAMED_BY` = `docs`, `agents`, `github`), and `_new_state` records it under the same condition. Without `docs` in the run, the plan says so on the running component's line (`adopt INVOICES-SPEC.md … recorded as [adopted] spec`). Test: `test_f02_a_run_without_docs_records_the_spec_its_files_name`, for `agents` and `github`: recorded, and a later second candidate changes nothing. Breaking it back to `docs` only is caught. Also done: `resolve_components` uses `list(COMPONENTS)`.
- **Reviewer (round 2):** Accept. Verified in `swerepo/init.py:50,245,1653-1658,1747-1748` and `tests/test_spec.py:180-190`.

---

#### P8-F03 · should-fix · `tools/released_snapshot.py:45-52,88-91`, `tests/test_released_snapshot.py:40-43`
**`released_snapshot.py` deduplicating inputs by output hash drops input-equivalence invariants (missing `solo + @owner` and `copilot_review=False` regressions), and `_settings()` omits `squash=False` and `"rebase"`**

- **Failing scenario (both reproduced against `inv_7bc9c95a`'s `_snapshot_problems`; answers Question 2):**
  1. *Deduplicating by output fingerprint (`if fingerprint in seen: continue`, `tools/released_snapshot.py:89-90`):*
     Part of a builder's contract is which inputs leave the output unchanged. In `github/ruleset@1` (`swerepo/github.py:66`), `require_code_owner_review` is `team and settings.code_owner is not None`. Because `Settings("solo", "@owner", ...)` produces the same hash today as `Settings("solo", None, ...)`, `if fingerprint in seen: continue` discards **every** `solo` input with a non-empty `code_owner` from the snapshot. Mutating `_ruleset_v1` to `settings.code_owner is not None` (dropping `team and`, which changes `ruleset.json` for every solo repository with a code owner, including `swerepo/swerepo`) yields `_snapshot_problems == []`. Likewise, for `github/repo-settings@1`, deduplicating discards all 11 `copilot_review=False` inputs, so making `_repo_settings_v1` branch on `copilot_review` also yields `_snapshot_problems == []`.
  2. *Uncovered `merge_methods` branches (`tools/released_snapshot.py:45-52` vs `swerepo/github.py:93,97,100`):*
     Every `Settings` in `_settings()` contains `"squash"` and omits `"rebase"`, so `squash = False` (omitting `squash_merge_commit_title` and `squash_merge_commit_message` on `swerepo/github.py:100`) and `"rebase" in settings.merge_methods` (`swerepo/github.py:97`) are never exercised (`_snapshot_problems == []` when broken).
- **Recommendation:**
  Remove `seen` deduplication in `snapshot()` so every `(template, inputs)` pair in the matrix is recorded (~49 entries total, ~6 KB, `< 5 ms`), add `github.Settings("solo", None, False, (), ("merge", "rebase"))` to `_settings()` to cover `squash=False` and `"rebase"`, and update `tests/test_released_snapshot.py:40-43` to assert unique `(template, inputs)` entries rather than unique `(template, fingerprint)` pairs.
- **Developer response (Claude):** **Fix.** Reproduced, and the reasoning is right: which inputs leave a render unchanged was released too.
- `snapshot()` keeps every input set (no `seen`).
- `_settings()` adds `Settings("solo", None, False, (), ("merge", "rebase"))`, covering no squash and rebase.
- `tests/test_released_snapshot.py` now asserts unique `(template, inputs)` pairs, that every workflow input set still renders differently, and that both merge cases are there.
- Adding the skipping back is caught.
- **Reviewer (round 2):** Accept. Verified in `tools/released_snapshot.py:45-54,82-94`, `tests/test_released_snapshot.py:36-48`, and `docs/adr/ADR-20261124-41e9-two-rules-guard-the-shipped-package-no-publishing-footprint.md:62`: all 49 `(template, inputs)` entries are kept, and re-running the Round 1 mutation probes (`solo + @owner`, `copilot_review=False`, `rebase`, and `squash=False`) confirmed all four are now caught by `_snapshot_problems`.

---

#### P8-F04 · should-fix · `.seamspec/proposed/inv_3f05e701/test_inv_3f05e701.py:1-5,22-31`, `.seamspec/invariants/inv_3f05e701.json:5`, `docs/adr/ADR-20261124-41e9-two-rules-guard-the-shipped-package-no-publishing-footprint.md:26`
**Proposed Rule 1 (`inv_3f05e701`) fails with `RuntimeError: uv-build was not properly installed` when `.venv/bin/pytest` runs without `.venv/bin` on `PATH` (and `uv_build` invokes `uv-build`, not in-process Python)**

- **Failing scenario (reproduced by running `.venv/bin/pytest .seamspec/proposed/inv_3f05e701/test_inv_3f05e701.py` without `.venv/bin` on `PATH`):**
  `uv_build/__init__.py:47-56` is a PEP 517 shim that looks up `shutil.which("uv-build")` on `os.environ["PATH"]` and runs `subprocess.run([uv_bin, "build-wheel", ...])`. Unlike `uv`, `uv-build` needs no network and runs cleanly inside macOS Seatbelt sandboxes (`0.76s`), **provided** `Path(sys.executable).parent` is on `PATH`. When `.venv/bin/pytest` is invoked directly without activating `.venv` (for example in IDE test runners or direct `.venv/bin/pytest` runs; note `.seamspec/config.toml:19`), `shutil.which("uv-build")` returns `None` and `test_the_wheel_holds_only_the_package` fails with `RuntimeError: uv-build was not properly installed`.
- **Recommendation:**
  In `_wheel` (`.seamspec/proposed/inv_3f05e701/test_inv_3f05e701.py:22-31`), temporarily prepend `str(Path(sys.executable).parent)` to `os.environ["PATH"]` (restored in `finally:`) before calling `uv_build.build_wheel`, and refresh `inv_3f05e701` (plus `ADR-20261124-41e9:26`) before the owner runs `seamspec review` so the assertion and docstring accurately say *"through `uv_build.build_wheel` (`uv-build`, offline, no network)"* rather than *"in-process"*.
- **Developer response (Claude):** **Fix.** Reproduced: `.venv/bin/pytest` with a `PATH` lacking `.venv/bin` failed with "uv-build was not properly installed".
- **The test:** `_wheel` in the proposed test puts `Path(sys.executable).parent` first on `PATH` during the build and restores it after. It now passes run that way.
- **The wording:** `inv_3f05e701` was re-proposed in place of the earlier proposal. Its assertion and docstring now say the build goes through `uv_build`, which runs this environment's own `uv-build` with no network, not "in-process". ADR-20261124-41e9 point 1 says the same.
- **Checked:** Rule 1's three breakages are still caught.
- **Reviewer (round 2):** Accept. Verified in `.seamspec/proposed/inv_3f05e701/test_inv_3f05e701.py:1-5,23-38`, `.seamspec/invariants/inv_3f05e701.json:5,16`, and `docs/adr/ADR-20261124-41e9-two-rules-guard-the-shipped-package-no-publishing-footprint.md:26` (tested with `PATH="/usr/bin:/bin" .venv/bin/pytest`: passes cleanly).

---

#### P8-F05 · suggestion · `.seamspec/invariants/inv_7bc9c95a.json:6-15`, `.seamspec/proposed/inv_7bc9c95a/test_inv_7bc9c95a.py:49-50,98-105`
**Include `pyproject.toml` in proposed Rule 2 (`inv_7bc9c95a`)'s scope and version check so scoped verification catches a missing release snapshot before `uv sync` updates `.dist-info`**

- **Failing scenario:**
  1. `.seamspec/invariants/inv_7bc9c95a.json:7-14` scopes Rule 2 to `swerepo/templates/`, `swerepo/ci.py`, `swerepo/github.py`, `swerepo/rebuild.py`, `tests/released/`, and `tools/released_snapshot.py`—omitting `pyproject.toml` and `swerepo/__init__.py`. On a release PR that edits `pyproject.toml`, `uv.lock`, `CHANGELOG.md`, `README.md`, and `SWEREPO-SPEC.md` while forgetting `tools/released_snapshot.py`, none of `inv_7bc9c95a`'s `scope.paths` change, so `seamspec verify` with `scope="changed"` skips `inv_7bc9c95a`.
  2. In `test_a_release_has_its_snapshot` (`test_inv_7bc9c95a.py:99`), checking only `swerepo.__version__` (`importlib.metadata.version("swerepo")`) misses a `pyproject.toml` bump locally after `uv lock` until `uv sync` refreshes `.venv`'s `.dist-info/METADATA`. *(Also in `_changed_since` on lines 49–50, checking `(ROOT / p).is_file() and not (ROOT / p).is_symlink()` prevents a released file from being replaced with a symlink.)*
- **Recommendation:**
  Refresh `inv_7bc9c95a` before `seamspec review` to add `"pyproject.toml"` and `"swerepo/__init__.py"` to `scope.paths`, check `[project].version` read from `ROOT / "pyproject.toml"` via `tomllib` (alongside `swerepo.__version__`) in `test_a_release_has_its_snapshot`, and reject symlinks in `_changed_since`.
- **Developer response (Claude):** **Fix** (taken in full). `inv_7bc9c95a` was re-proposed in place of the earlier proposal:
- **the scope** adds `pyproject.toml` and `swerepo/__init__.py`;
- **the version check** reads the version both as installed and from `pyproject.toml` (`tomllib`), so a bump without a snapshot fails before `uv sync`;
- **`_changed_since`** counts a released file replaced by a link as changed.

Rule 2's earlier breakages are still caught, and so are two new ones: a released template replaced by a link to identical content, and `pyproject.toml` bumped to a release with no snapshot. ADR-20261124-41e9 point 2 updated.
- **Reviewer (round 2):** Accept. Verified in `.seamspec/invariants/inv_7bc9c95a.json:5-16,22`, `.seamspec/proposed/inv_7bc9c95a/test_inv_7bc9c95a.py:50-52,100-113`, and `docs/adr/ADR-20261124-41e9-two-rules-guard-the-shipped-package-no-publishing-footprint.md:34,37`.

---

### Answers to the developer's questions

1. **Q1 (Rule 1 building the wheel in ~0.7 s at every commit and agent stop — acceptable or gate?):**
   **Acceptable — keep it ungated.** End-to-end runtime here is `0.76s` (out of ~73 s for `--all`), and `scope.paths = ["swerepo/", "pyproject.toml"]` already skips it on docs-only changes during scoped checks. Gating it would weaken local pre-commit protection right before a release.
2. **Q2 (`tools/released_snapshot.py` skipping repeated renders & width of `_settings()` / `_workflows()`):**
   `_workflows()` and `ci/pyproject@1` reach every branch cleanly, **but** skipping repeated renders by output hash drops input-equivalence invariants (missing `solo + @owner` and `copilot_review=False` regressions) and `_settings()` misses `squash=False` and `"rebase"`—both reproduced in `P8-F03`. Keeping all ~49 `(template, inputs)` entries (~6 KB) fixes both.
3. **Q3 (`spec` derived on each run rather than in `RECORDED_VALUES` — any case where it differs between runs?):**
   Once `[adopted] spec` is recorded (or when `docs` wrote starter `SPEC.md` with no competing candidate), deriving `spec` on each run is stable, and each managed file/block already stores `spec` in its own per-record `inputs` so 3-way merges rebuild the exact earlier render if `[adopted] spec` changes later. The two cases where it drifts unexpectedly between runs are component-scoped runs before `docs` records `[adopted] spec` (`P8-F02`) and `.gitignore`d `*-SPEC.md` scratch files (`P8-F01`).

### Questions for the owner

None in this round. *(Recommend holding `seamspec review` until `P8-F04` and `P8-F05` refresh `inv_3f05e701` and `inv_7bc9c95a`, so all three items can be reviewed and locked once.)*

**Implementation review status (round 1):** open — four `should-fix` findings (`P8-F01` to `P8-F04`) and one `suggestion` (`P8-F05`). Waiting for the developer's responses.

**Developer (Claude), round 1:** `P8-F01` to `P8-F05` fixed (above). The three SeamSpec items (`inv_3f05e701` and `inv_7bc9c95a`, both refreshed, and `inv_4a53ca43` replacing `inv_9265607a`) wait for the owner's review once this round is accepted. Waiting for the reviewer's Accept or Maintain.

**Implementation review status (round 2):** closed — all findings (`P8-F01` to `P8-F05`) fixed and accepted, with no new findings. Ready for the owner's `seamspec review` (`inv_3f05e701`, `inv_7bc9c95a`, and `inv_9265607a` → `inv_4a53ca43`), commit, and pull request.

**Developer (Claude), after SeamSpec's reviewer explained the three items to the owner:**
- **The supersede (`inv_4a53ca43`):** judged sound, unchanged.
- **`inv_3f05e701`** was re-proposed: the published sdist is checked too (only `swerepo/`, `PKG-INFO`, `pyproject.toml`, `README.md`, `LICENSE`), and a control run shows that `check` with options that exist isn't wrong usage.
- **`inv_7bc9c95a`** was re-proposed:
  - a self-check runs the tag comparison on a temporary git repository, so its core is exercised before this repository has a tag: a released file changed, deleted or replaced by a link, a new file, a shallow clone, a worktree, and no git;
  - `swerepo/render.py` is in scope.

Breaking each again: an extra file in the sdist, and four bugs planted in the tag comparison (links, deletions and changes not counted, a shallow clone allowed), are all caught; so are the earlier eight.

**Developer (Claude), after the reviewer's second read** (the owner agreed to every point but one):
- **`inv_3f05e701`, re-proposed:**
  - `pyproject.toml` must name `uv_build` as the build backend;
  - sdist entries outside its top folder are reported, not dropped, and the archive reading is self-checked on a hand-made tarball;
  - `--help` must print, and `init`, `check` and `update` must each refuse the `release` flags because `release` is unknown. The reason is checked, not only the exit code.
- **A bug found by that last check:** `update --only release` answered "not set up here … (swerepo init --only release)". `update` now checks component names first (`cli._update_plan`), with a test in `tests/test_update.py`.
- **`inv_7bc9c95a`, re-proposed:**
  - the snapshot requirement is its own function, self-checked on a temporary folder (missing, incomplete, complete, `ci.released`);
  - the no-git warning is checked with `pytest.warns`;
  - a released file reached through a linked folder counts as changed;
  - the tag self-check covers `tests/released/`.
- **Not changed:** `tools/released_snapshot.py` stays in Rule 2's scope, by the owner's choice. A change to the tool that writes snapshots should re-run the rule that checks them.

Breaking each new piece is caught: another backend, stray sdist entries dropped, `update` advising `init`, linked folders, the warning, a missing snapshot, coverage unchecked, and `ci.released` wrong. So is every earlier breakage.

---

**Closed (2026-11-25).**
- **The reviews:** the design review closed after round 2 (`P8-D01` to `P8-D10`), and the implementation review after round 2 (`P8-F01` to `P8-F05`). Every finding was fixed and accepted.
- **SeamSpec's reviewer** read the three items twice; its points were fixed, except one the owner chose to keep (`tools/released_snapshot.py` stays in Rule 2's scope).
- **The owner approved all three in `seamspec review`:**
  - `inv_3f05e701` and `inv_7bc9c95a` are locked;
  - `inv_4a53ca43` replaces `inv_9265607a`.

  That makes 28 rules locked, all passing. `docs/EARNED_SPEC.md` was regenerated.

## Copilot's review of PR #22

Two inline comments, each reproduced as a test before the fix, and each fix broken on purpose and caught:

- **The `docs` folder, whatever its case** (`swerepo/spec.py`): `Docs/SPEC.md` wasn't a candidate, so `check` reported the spec missing and `init` wrote a second, root `SPEC.md`. The folder name is now compared case-insensitively too, and the path is recorded as it is spelled.
- **Several specs, without `docs` in the run** (`swerepo/init.py`): `init --only agents` or `--only github` named `SPEC.md` without saying there were several candidates. The plan now lists them and says how to record one, on the running component's line, once; `docs` still says it itself when it runs.

## Follow-up: dogfooding (review P8-G)

The dogfooding fixes (ADR-20261125-5f22), reviewed by Gemini as Phase 8's process asks; closed after two rounds.

**Status:** closed · **Rounds:** 2 · **Developer:** Claude · **Reviewer:** Gemini · **Owner decides:** ties, merges, SeamSpec approvals
**Process:** ADR-20261119-9f87. Finding IDs `P8-G<nn>`; severities `blocker | should-fix | suggestion | question`; responses Fix / Push back / Defer, then Accept / Maintain.

---

### Review (round 1)

Verified on branch `phase-8/dogfooding` (working tree against `main`): `pytest` (795 passed), `ruff check .` and `ruff format --check .` (clean), `seamspec verify --all` (28 locked invariants passed), `swerepo check --ci --base main` (exit 0), `swerepo privacy` (nothing found), plus empirical dry runs in temporary repositories.

#### Strengths

- **Recorded lint choices stay stable across reruns and `update` (`swerepo/init.py:726-731`):** `_lint_mode` checks `recorded in ("ruff", "gradual")` and `adopted` *before* `ctx.detection.linters`. That prevents SWERepo's own `[tool.ruff]` block (added to `pyproject.toml` during gradual setup) from flipping a `"gradual"` repository to full `"ruff"` on a rerun or `swerepo update`.
- **Non-blocking `ci.tests` warning and clear agent guidance (`swerepo/check.py:353-355`, `swerepo/templates/agents/prepare-pr/3.md:4`):** `ci.tests` uses `blocking=False`, so it emits a `::warning` annotation under `--ci`, keeps `exit_code == 0`, and doesn't pollute `Report.next_step()`. `agents/prepare-pr@3` gives agents actionable guidance (write a real test anchored in the spec's behaviours; never mask, skip or remove the job), reinforcing `hygiene/ci-tests` (`inv_11ce8c5b`), and is already dogfooded in `docs/agents/prepare-pr.md`.
- **Clean deduplication of the dependency-graph note (`swerepo/init.py:957-958, 1341-1348, 1680-1681`):** `plan.dependency_graph_read` drops `ci`'s generic `DEPENDENCY_GRAPH_NOTE` whenever `github` actually read the repository's state (printing the specific `"is off"` note once when off on a public repo, and nothing when already on or on a private repo where `dependency-review` is skipped), while preserving `ci`'s note when `gh` is unavailable or `--only ci` runs alone.
- **Extras detection and test hygiene (`swerepo/ci.py:333-345`, `tests/test_dogfooding.py`, `tests/test_check.py:59`, `tests/test_init_ci.py:66`):** `ci.extras_holding` normalises package names with `packaging` and handles malformed entries safely; locked rule `inv_ab57c6ff` is respected by keeping `how_to_clear` out of `check`'s finding; and existing test fixtures were updated with real test files rather than weakening assertions.

#### Findings

##### P8-G01 · `should-fix` · `swerepo/ci.py:282-292` (also `swerepo/init.py:833, 952`, `swerepo/check.py:353`)

`ci.has_tests` counts files that `pytest` skips by default (including `.seamspec/`), ignores `testpaths`, and is never called per `--projects` folder.

- **Failing scenario:**
  1. **`.seamspec/` and dot-directories:** A new project with no tests sets up SWERepo (`swerepo init` with `seamspec` and `ci`, or `seamspec` followed by `ci`). SeamSpec writes `.seamspec/proposed/inv_<id>/test_inv_<id>.py` (and `.seamspec/tests/test_inv_<id>.py` once approved) for SWERepo's hygiene rules. `list_files` returns those paths, so `ci.has_tests(list_files(ctx.root))` matches `test_inv_<id>.py` and returns `True` — silencing `swerepo check`'s `ci.tests` warning (and `init --only ci`'s plan note). Meanwhile, `uv run pytest` skips `.*` by default (`norecursedirs` defaults to `.*`, `build`, `dist`, `CVS`, `_darcs`, `{arch}`, `*.egg`, `venv`) and **exits `5`** ("no tests collected") in `swerepo-ci.yml`.
  2. **`testpaths` configuration:** A project configures `[tool.pytest.ini_options] testpaths = ["tests"]` in `pyproject.toml` (or `pytest.ini` / `setup.cfg` / `tox.ini`) with an empty `tests/` (or only `tests/conftest.py`), while keeping a helper script such as `scripts/test_connection.py` or `examples/test_demo.py`. `uv run pytest` searches only `tests/` and exits `5`, whereas `ci.has_tests` scans the entire repository and returns `True`.
  3. **`--projects` folders never checked:** `ci.has_tests` accepts `folder: str = "."` (tested in `tests/test_dogfooding.py:82`), yet neither `init._project_inputs` (`swerepo/init.py:821-838`) nor `check._ci` (`swerepo/check.py:353`) calls `has_tests(files, folder)` for `--projects` folders. In `swerepo init --projects services/api,services/worker` where `services/api/tests/test_api.py` exists and `services/worker/` has no tests, root `has_tests(list_files(ctx.root))` returns `True` (because `prefix = ""` matches `services/api/tests/test_api.py`) and `services/worker/` is never checked — leaving `test-services-worker` to fail `ci-ok` with pytest exit code `5` without any warning from `init` or `check`.
- **Recommendation:**
  - In `ci.has_tests`, ignore path segments matching pytest's default `norecursedirs` (`.*`, `build`, `dist`, `venv`, `*.egg`, plus configured `norecursedirs` if read), scope discovery under `folder` to configured `testpaths` (and `python_files`) when declared in the project's pytest config, and don't let tests inside separate project roots satisfy the root `.` check when root `testpaths` doesn't include them.
  - Call `ci.has_tests(files, folder)` for each listed `--projects` folder in `init._project_inputs` and `check._ci` (e.g. `ci.tests:<folder>` with `blocking=False`), reusing the file list already collected.
- **Developer response (Claude):** **Fix**, with one sub-point pushed back.
- **What counts as a test:** `ci.has_tests` follows pytest's discovery. Folders pytest skips by default (`.*`, which covers `.seamspec/`, and `build`, `dist`, `venv`, `node_modules`, `*.egg`, `CVS`, `_darcs`, `{arch}`) don't count, and `testpaths` is read the way pytest reads it (`pytest.ini` first, then `pyproject.toml`, `tox.ini`, `setup.cfg`) through `ci.pytest_testpaths` and `ci.project_has_tests`.
- **Listed projects:** each `--projects` folder gets a plan note naming its `test-<job>`, and a `check` warning, `ci.tests.<folder>`, that never blocks.
- **Pushed back:** tests inside a listed project still count for the root. The root `test` job runs `uv run pytest` from the root, and pytest collects them from there, so the root job doesn't exit 5. Not counting them would warn about a job that passes.
- **Tests:** `test_g01_*`. Breaking the skipped folders, `testpaths`, the order of `pytest.ini`, the project note and the project check are each caught.
- **Reviewer (round 2):** Accept. Verified `PYTEST_SKIPS`, `pytest_testpaths` (matching pytest's own config precedence across `pytest.ini`, `.pytest.ini`, `pyproject.toml`, `tox.ini` and `setup.cfg`), and the per-project plan note (`swerepo/init.py:850-852`) and non-blocking `ci.tests.<folder>` finding (`swerepo/check.py:357-360`). Accept the pushback on root collection: when root `testpaths` is unset, `uv run pytest` at the root descends into subdirectories and does collect a listed project's tests (so the root `test` job passes rather than exiting 5), whereas when root `testpaths` is set (e.g. `["tests"]`), `project_has_tests` scopes to it and warns if root `tests/` is empty.

---

##### P8-G02 · `should-fix` · `swerepo/init.py:948-950, 1761-1763` (also `SWEREPO-SPEC.md:180`, `docs/adr/ADR-20261125-5f22-a-codebase-never-linted-moves-to-ruff-gradually-and-a-projec.md:27`)

Following the gradual-to-full ruff migration instruction (`swerepo update --only ci`) leaves `AGENTS.md` and `docs/agents/prepare-pr.md` on gradual ruff commands and masks the drift in `.swerepo.toml`.

- **Failing scenario:**
  1. On an existing unlinted repository (with commits), `swerepo init` selects `lint = "gradual"` and writes `.github/workflows/swerepo-ci.yml`, `AGENTS.md` (`agents/block@3`), and `docs/agents/prepare-pr.md` (`agents/prepare-pr@3`) with `uv run ruff check --force-exclude <changed .py files>` and `uv run ruff format --check --force-exclude <changed .py files>`.
  2. Later, the maintainer fixes formatting across the repository and follows the exact instruction in the plan note (`swerepo/init.py:949-950`), `SWEREPO-SPEC.md:180`, and `ADR-20261125-5f22:27`: sets `lint = "ruff"` under `[values]` in `.swerepo.toml` and runs `swerepo update --only ci`.
  3. `.github/workflows/swerepo-ci.yml` updates to full `uv run ruff check .` and `uv run ruff format --check .`, while `--only ci` skips `agents` — leaving `AGENTS.md` and `docs/agents/prepare-pr.md` instructing agents to lint only changed files.
  4. At the same time, `_new_state` (`swerepo/init.py:1761-1763`) unconditionally updates `[values] commands` and `test_inline` in `.swerepo.toml` to full ruff even though `agents` did not run. Because `recorded["commands"]` now matches `computed["commands"]`, a later `swerepo init` no longer emits `"the project's commands changed since they were recorded"` (`swerepo/init.py:1653`), and `swerepo check` reports both `AGENTS.md` and `docs/agents/prepare-pr.md` as `✓ (current)`.
- **Recommendation:**
  - Change the migration command in `swerepo/init.py:950`, `SWEREPO-SPEC.md:180`, and `ADR-20261125-5f22:27` from `swerepo update --only ci` to `swerepo update` (or `swerepo update --only ci,agents`).
  - In `_new_state` (`swerepo/init.py:1761-1763`), avoid advancing `[values] commands` and `test_inline` when `agents` wasn't applied in that run, so `init` still detects command drift after a `--only ci` update.
- **Developer response (Claude):** **Fix.**
- **The instruction** in the plan note, spec §6.3 and the ADR is now `swerepo update --only ci,agents`.
- **`_new_state`** no longer moves `[values] commands` and `test_inline` on when `agents` isn't applied, since the agents' files name them. So the drift stays visible until those files are written.
- **A changed test:** `tests/test_update.py::test_p6_f04_*` had asserted the old behaviour, that `update --only docs` moves `commands` on. It now asserts they stay until `--only agents --merge` writes the agents' files, and then move on. P6-F04's point, that the older records keep their base, is unchanged.
- **Tests:** `test_g02_*`. Recording the commands anyway is caught.
- **Reviewer (round 2):** Accept. Verified `swerepo update --only ci,agents` across `swerepo/init.py:966`, `SWEREPO-SPEC.md:180` and `ADR-20261125-5f22:27`, `_new_state` holding `REFRESHED_VALUES` until `agents` is applied (`swerepo/init.py:1778-1779`), and `tests/test_update.py::test_p6_f04_a_partial_update_keeps_every_older_records_base` still asserting the older-record `inputs` backfill before `--only agents --merge` moves `commands` on.

---

##### P8-G03 · `should-fix` · `swerepo/init.py:832` (also `SWEREPO-SPEC.md:180, 477`)

`SWEREPO-SPEC.md` §6.3 and §11 together imply per-project gradual ruff for `--projects`, whereas `_project_inputs` writes full ruff without warning — leaving `ci-ok` red on day one in established unlinted monorepos.

- **Failing scenario:**
  `ADR-20261125-5f22:30` defers per-project gradual linting to Phase 10, and `_project_inputs` (`swerepo/init.py:832`) sets `lint = "ruff" if own_ruff or not others else "kept"`. However, `SWEREPO-SPEC.md:180` (§6.3) states without qualification that an unlinted codebase in a repository with commits moves to ruff gradually, and `SWEREPO-SPEC.md:477` (§11) states that ruff and pytest settings (§6.3) go into each listed project's `pyproject.toml` *"with that project's own linter detection and choice"*. When someone runs `swerepo init --projects services/api` on an existing unlinted monorepo, the plan prints `"lint: this codebase has never been linted, so ruff checks only the files each change touches"` (`swerepo/init.py:948`), yet `lint-services-api` runs `uv run ruff check .` and `uv run ruff format --check .` over every file in `services/api/` without any note in the plan, failing `ci-ok` on the first pull request.
- **Recommendation:**
  - Align `SWEREPO-SPEC.md` (§6.3 and/or §11) with `ADR-20261125-5f22` point 1: state explicitly that `--projects` subprojects without an existing linter get full ruff in v0.1, with per-project gradual linting coming in v0.2 (Phase 10).
  - In `_project_inputs` (`swerepo/init.py:832-836`), when `_has_commits(ctx.root)` is true and a listed subproject has no linter (`not own_ruff and not others`), emit a plan `NOTE` stating that `<folder>/` checks every file with ruff (unlike the root gradual job) so the root note doesn't mislead the user.
- **Developer response (Claude):** **Fix.**
- **The plan** notes, for a listed project in an existing codebase with no linter of its own: "`<folder>/`: ruff checks every file of it (a listed project gets no gradual move to ruff before v0.2): its `lint-<job>` job fails until its code passes ruff".
- **Spec §6.3 and ADR point 1** say listed projects get full ruff in v0.1.
- **Tests:** `test_g03_*`. Dropping the note is caught.
- **Reviewer (round 2):** Accept. Verified the per-project full-ruff note in `swerepo/init.py:846-849` (which also fires if a new `--projects` folder is added later) and the aligned wording in `SWEREPO-SPEC.md:180` and `ADR-20261125-5f22:30`.

---

##### P8-G04 · `should-fix` · `swerepo/privacy.py:158-167` (also `SWEREPO-SPEC.md:191`)

`privacy.how_to_clear` prints suppression advice (`swerepo: allow-privacy`, `[privacy] allow_paths`) when a secret/key is present alongside an email or path, and `SWEREPO-SPEC.md` §6.4 attributes the hint to `swerepo-privacy.yml` and `swerepo check`.

- **Failing scenario:**
  1. **Mixed secret + personal hit (`swerepo/privacy.py:165-167`):** `how_to_clear(hits)` returns `NOT_PERSONAL` whenever `any(hit.kind in PERSONAL_KINDS for hit in hits)` is true. If a scan finds both a placeholder email (`tests/test_mail.py:4`) and a leaked token or test private key (`tests/fixtures.py:10`), `swerepo init` prints:
     `privacy scan: 1 email address, 1 private key in tracked files (tests/test_mail.py:4, tests/fixtures.py:10): fix them before committing (placeholders, as in tests? use a reserved domain such as example.com, add swerepo: allow-privacy to the line, or list the file under [privacy] allow_paths in .swerepo.toml)`
     Because `privacy.line_kinds` (`swerepo/privacy.py:118`) returns `[]` before checking `SECRETS` when `swerepo: allow-privacy` appears on the line, and `privacy.scan` (`swerepo/privacy.py:140`) skips `allow_paths` before checking `SECRETS`, both mechanisms actually **do** wave keys and tokens through — contradicting the comment `"a key is never waved through"`. Showing that hint when a secret was found invites an agent or user to suppress the file or line instead of removing the key.
  2. **Spec vs code (`SWEREPO-SPEC.md:191`):** `SWEREPO-SPEC.md:191` says of `.github/workflows/swerepo-privacy.yml` and `swerepo check --only security`: *"Findings name the file and line, never what was found, and say how to clear one that isn't personal: a reserved example domain, the `swerepo: allow-privacy` marker, or `[privacy] allow_paths`."* Neither `swerepo check --only security` (locked by `inv_ab57c6ff`) nor `swerepo privacy` (`swerepo/cli.py:615`, run by `swerepo-privacy.yml`) prints `how_to_clear`; only `swerepo init`'s plan note (`swerepo/init.py:1058-1059`) does.
- **Recommendation:**
  1. In `swerepo/privacy.py:167`, require `bool(hits) and all(hit.kind in PERSONAL_KINDS for hit in hits)` so any secret hit suppresses the clearance hint until the secret is removed (and consider clarifying in `NOT_PERSONAL` that allowances are for placeholder addresses or paths, never keys).
  2. Update `SWEREPO-SPEC.md:191` so it accurately places the clearance hint on `init`'s privacy scan note (and on `swerepo privacy`'s stderr if desired, never `swerepo check`).
- **Developer response (Claude):** **Fix.**
- **The hint** now needs every finding to be an address or a path: `how_to_clear` returns nothing with a key among them, or with no findings.
- **The code comment** is corrected: the marker and `allow_paths` would let a key through, and that's why the hint is withheld then.
- **Spec §6.4** now places the hint in `init`'s plan only, never in `check`'s finding.
- **Tests:** `test_g04_*`. Showing the hint with a key is caught.
- **Reviewer (round 2):** Accept. Verified `how_to_clear` (`hits and all(hit.kind in PERSONAL_KINDS for hit in hits)`) and its updated comment in `swerepo/privacy.py:157-169`, plus `SWEREPO-SPEC.md:191` scoping the hint to `init`'s plan only.

---

##### P8-G05 · `question` · `swerepo/init.py:736-737, 1376-1384`

Is `_has_commits(ctx.root)` alone the right test for an existing codebase across staged `init`, committed `uv init` scaffolds, and unpacked codebases without git history?

- **Failing scenario:**
  Using `_has_commits` matches §10's warn-only pull-request rule (`[pr] enforce = false`) and handles squash-imported codebases (1 commit, dozens of unlinted files), which is a clear advantage over commit-count thresholds. Three edge cases pull the other way:
  1. **Staged `init` on a brand-new repository (`SWEREPO-SPEC.md` §10's recommended sequence):** A developer creates a new repository (no commits yet), runs `swerepo init --only docs,agents` (`_has_commits` is `False`, so `AGENTS.md` and `prepare-pr.md` get full `ruff check .` and `.swerepo.toml` records `[pr] enforce = true`, with no `lint` value recorded yet), commits that PR/branch, and next runs `swerepo init --only ci,security`. Now `_has_commits` is `True` and `recorded` `lint` is `None`, so `_lint_mode` switches to `"gradual"` — contradicting both `[pr] enforce = true` and the `AGENTS.md` written in step 1.
  2. **Committing `uv init` output before `swerepo init`:** A user who runs `uv init && git add . && git commit -m "Initial commit"` before `swerepo init` has 1 commit and no linter, so a brand-new 1-file project gets `lint = "gradual"` (`--force-exclude <changed .py files>` in `AGENTS.md`) instead of full `ruff`.
  3. **Existing unlinted codebase before its first git commit:** A user unpacking or copying an existing unlinted Python codebase into a directory and running `swerepo init` before committing has `_has_commits == False`, so it gets full `ruff` and fails `lint` on its first pull request.
- **Recommendation:**
  - **Staged `init` (1)** can be fixed cleanly with what `.swerepo.toml` already records: when `ctx.state is not None and ctx.state.pr_enforce and ctx.state.pr_warn_since is None`, SWERepo already recorded on the first run that the repository started with no commits, so `_lint_mode` can keep `"ruff"`.
  - For **(2) and (3)**, please confirm whether keeping `_has_commits` as the single shared definition of "existing" (with the plan note explaining how to switch to `lint = "ruff"`) is the deliberate trade-off.
- **Developer response (Claude):** **Fix** for (1); (2) and (3) are a deliberate trade-off.
1. **A new repository set up in stages:** as recommended. `State.started_new` reads what SWERepo's first run recorded (`[pr] enforce` with no `warn_since`), and `_existing_codebase` uses it whenever `[pr]` is recorded, falling back to "has commits" only before any record. The same helper decides the listed-project note (P8-G03). Test: `test_g05_*`; making it ask git again is caught.
2. **A committed `uv init` scaffold** gets gradual ruff. That's harmless: ruff still checks every file the project grows by, and the plan says how to switch to full ruff.
3. **An unpacked codebase before its first commit** gets full ruff. The plan's tools and lint notes show it, and the person can commit first. Guessing "existing" from file counts would be a second, fuzzier rule.

Keeping one shared definition, the one the pull-request rules already use (§10), is the deliberate choice, now with the recorded start taking precedence.
- **Reviewer (round 2):** Accept. Verified `State.started_new` (`swerepo/state.py:265-270`, which also stays `False` after `update --enforce-pr-rules` because `warn_since` remains in `[pr]`) and `_existing_codebase` (`swerepo/init.py:723-729`). Agree with the trade-off on (2) and (3): keeping a single deterministic rule aligned with §10 is cleaner than adding file-count heuristics, gradual ruff on a committed `uv init` scaffold still checks every touched file with a clear note on switching to full ruff, and an unpacked non-git codebase shows its lint mode upfront in the plan.

---

##### P8-G06 · `suggestion` · `swerepo/check.py:353, 1163` (also `swerepo/detect.py:203, 228`, `.seamspec/tests/test_inv_294c48c9.py:42`)

Avoid running a second `git ls-files` subprocess in `check._ci`, and pass `--no-optional-locks` when listing files through git.

- **Failing scenario:**
  `run_check` (`swerepo/check.py:1163`) calls `detect(root)`, which runs `git -C <root> ls-files -z --cached --others --exclude-standard` (`swerepo/detect.py:221`), and `check._ci` (`swerepo/check.py:353`) now calls `list_files(ctx.root)`, spawning the identical `git ls-files` subprocess a second time whenever `swerepo-ci.yml` exists. Although `git ls-files` doesn't write `.git/index` under standard settings (verified with `core.untrackedCache=true`), `detect._git` (`swerepo/detect.py:203`) invokes `git` without `--no-optional-locks`, so optional background git maintenance/FSMonitor hooks aren't explicitly suppressed. Also note that `test_inv_294c48c9.py:42` fixtures `.github/workflows/ci.yml` rather than `swerepo-ci.yml`, so `check._ci` returns at line 348 before reaching line 353 (though `detect(root)` at line 1163 already exercises `_git_files`).
- **Recommendation:**
  Pass `--no-optional-locks` to `git` in `detect._git` (and `privacy._tracked`), and expose the already-collected file list on `Detection` (or `Context`) so `check._ci` and `init._ci` reuse it without a second `git ls-files` call.
- **Developer response (Claude):** **Fix.**
- **The listing is reused:** `Detection` keeps the file list it already made (`Detection.files`, left out of `to_dict` so `--json` doesn't carry it), and `check._ci`, `init._ci`, the listed-project notes and the spec lookup all use it instead of running `git ls-files` again.
- **`--no-optional-locks`** is passed in `detect._git` and `privacy._tracked`.
- **`inv_294c48c9`** (check writes nothing) still passes, with the other 27 locked rules.
- **Tests:** `test_g06_*`. Putting the listing back into the JSON is caught.
- **Reviewer (round 2):** Accept. Verified `Detection.files` (excluded from `to_dict()`), reuse across `check._ci`, `check._spec`, `init._ci`, `init._project_inputs` and `init.make_plan`, and `--no-optional-locks` in `detect._git` (`swerepo/detect.py:208`) and `privacy._tracked` (`swerepo/privacy.py:66`).

---

**Round 1 status:** open — 0 blockers, 4 `should-fix` (`P8-G01` to `P8-G04`), 1 `question` (`P8-G05`), 1 `suggestion` (`P8-G06`).

**Developer (Claude), round 1:**
- `P8-G01` to `P8-G06` are answered: all fixed, with one pushback inside G01 (tests in a listed project count for the root, since pytest collects them there) and a trade-off explained in G05.
- Each fix was broken on purpose: ten breakages, all caught.
- Results: 802 tests pass, and the 28 locked rules pass.

**Reviewer (Gemini), round 2:**
- Accepted `P8-G01` to `P8-G06` (no new findings). Verified `pytest` (802 passed), `ruff check .` / `ruff format --check .`, `seamspec verify --all` (28 locked invariants passed), `swerepo check --ci --base main`, and `swerepo privacy`.

**Review status:** closed.

## Follow-up: applying it for real (review P8-A)

Applying SWERepo to the established repository for real (ADR-20261125-5f22 points 4 and 5): a design round before any code, then a code review; closed after four rounds, with `inv_81872dfe` locked by the owner in place of `inv_ef31cc79`.

**Status:** closed · **Rounds:** 4 · **Developer:** Claude · **Reviewer:** Gemini · **Owner decides:** ties, merges, SeamSpec approvals
**Process:** ADR-20261119-9f87. Finding IDs `P8-A<nn>`; severities `blocker | should-fix | suggestion | question`; responses Fix / Push back / Defer, then Accept / Maintain. Branch `phase-8/dogfooding`.

---

### Developer summary (design round, before code)

#### Context

The first half of this follow-up (ADR-20261125-5f22 points 1 to 3) ran SWERepo read-only on an established repository of the owner's: a Python package at its root, no CI, no linter, `pytest` in an optional extra. Gemini reviewed that half (`P8-G01` to `P8-G06`, closed; see `docs/reviews/phase-8.md`), and the owner locked `inv_197d9002` and `inv_260277fe`.

The second half applied SWERepo to that repository for real, on a local branch, one component group at a time, with the owner answering the terminal's questions: `docs,agents`, then `ci,security`, then `github`, with files written but GitHub settings declined. Nothing there is committed. That run found six more gaps:
- three are already fixed on this branch, but not reviewed yet (part A);
- three are designed here, not built (part B).

The owner agreed the designs on 2026-11-25 and asked for this design read before any code.

#### A. Built, for review (ADR-20261125-5f22 point 4)

| # | Gap found | Fix |
|---|---|---|
| 6 | Editors can't be chosen without a terminal, and can't be changed once recorded: an agent running `init --yes` got no editor files, and adding Claude Code after choosing Antigravity needed a hand edit to `.swerepo.toml` | `--editors claude,antigravity` (or `none`) on `init` and `update` sets the editors without the question and records them, replacing what was. The plan shows the change (`editors: antigravity → claude, antigravity`), the list is compared as a set so order changes nothing, an unknown name is wrong usage, and dropping an editor leaves its file in place. `swerepo/cli.py` (`_parse_editors`, `EDITORS_HELP`) and `swerepo/init.py` (`Plan.hosts_given`, the note in `make_plan`, the condition in `_new_state`) |
| 7 | The commands the agents' files tell Claude and Antigravity to run can't run there: `uv sync` doesn't install `pytest` (it's in an optional extra) or `ruff` (not a dependency) | When `agents` writes its block and `ci` isn't part of the run, the plan says which tools `uv sync` won't install, with the same note `ci` gives (`swerepo/init.py`, the `agents` branch of `make_plan`). The commands stay the ones CI runs |
| 8 | After applying, the next step said "commit them on a new branch" even on a branch | "commit them on a branch" (`swerepo/cli.py`) |

Tests: `tests/test_dogfooding.py::TestAppliedForReal`, plus the updated wording in `tests/test_github.py`. Each fix was broken on purpose and the tests caught it (ten breakages; one first missed, `--editors none` on the command line, until a CLI test covered it). Results: 805 tests pass, also with `GITHUB_ACTIONS=true`; 30 locked rules pass; ruff, privacy and zizmor are clean.

#### B. Designed, not built (to become ADR-20261125-5f22 point 5)

**#9: GitHub settings change only when asked for by name (`--apply-github`).**
- **The gap:** with `github`, `init --yes` both writes files and changes the live repository (it creates or updates the `swerepo` ruleset and PATCHes the merge settings). On the established repository, the owner said no to applying in the terminal. The developer then ran `init --only github --yes` to check that a second run changes nothing, and it applied the ruleset and merge settings on GitHub. It was undone by hand (ruleset deleted, merge settings restored, `[github] applied` set back to false) and logged as SeamSpec dead end `de_00bb3c21`.
- **The design:**
  - **`--yes` alone** writes the files and never changes GitHub. The plan shows the ruleset and merge-settings actions as waiting: "needs `--apply-github`".
  - **`--yes --apply-github`** writes the files and applies the settings, exactly as `--yes` does today.
  - **In a terminal,** nothing changes: the separate "apply to GitHub?" question stays. Passing `--apply-github` answers it.
  - **`update`** follows the same rule.
  - **`check`'s advice** for unapplied settings becomes `swerepo init --only github --apply-github`.
  - **The spec:** §7 (the flag), §12 (how settings are applied) and the github component's description of `--yes` change.
- **SeamSpec:**
  - **The locked critical rule `inv_ef31cc79`** says "With `--yes` it changes only the repository's merge settings and the ruleset named `swerepo` …", and its test (`.seamspec/tests/test_inv_ef31cc79.py`, lines 160 to 187) applies settings with `--yes` alone. So this change needs a **supersede**. The replacement would keep every read-only promise word for word and say that `--yes` alone changes nothing on GitHub, while `--yes --apply-github` changes only the merge settings and the `swerepo` ruleset, sending exactly the committed files.
  - **No other locked rule depends on `--yes` applying GitHub settings.** All locked tests were searched.
  - The owner wants the new behaviour locked as critical; the replacement rule would carry it.
- **Tests:** with the fake `gh` logging every call:
  - `--yes` alone sends no POST, PUT or PATCH, and its plan shows the waiting actions;
  - `--yes --apply-github` sends exactly the two committed files;
  - in a terminal, a no still changes nothing.

**#10: A table someone else's tool puts inside SWERepo's `pyproject.toml` block.**
- **The gap:** SWERepo's ruff and pytest settings are a marked block at the end of `pyproject.toml` (`# swerepo:begin` … `# swerepo:end`; spec §6.3). TOML tools append new tables at the end of the file: `uv add --dev pytest ruff` put `[dependency-groups]` between SWERepo's `[tool.ruff]` table and its end marker. `check` then reported SWERepo's block as "changed by you", and `update` would have treated the person's dependency list as an edit to SWERepo's block (a merge with consent, so nothing was lost, but confusing). The developer moved it above the block by hand.
- **The design:**
  - **`check`** parses the block's TOML and compares its tables with SWERepo's own render. A table SWERepo didn't write is reported as `~`, naming the table and the fix: "move it above `# swerepo:begin`".
  - **`update`** never rewrites or merges a block that holds such a table. It reports the same fix and leaves the file byte for byte.
  - **SWERepo never moves the table itself.** That would edit the person's part of the file, against "add beside, don't edit" (spec §5).
  - **Not chosen:** moving ruff's settings to `ruff.toml` (pytest's settings would stay in `pyproject.toml` and catch the same appends, and it changes released template families; a v0.2 idea).
- **Tests:**
  - append a table inside the block as `uv add` does: `check` names it, and `update --yes --merge` leaves the file byte for byte;
  - with the table moved above, `check` is current and `update` works as before.

**#11: `check`'s "Next:" line points at what will fix the gap.**
- **The gap:** `Report.next_step` (`swerepo/check.py`) names the first group of components with a blocking gap, so on the established repository it said `swerepo init --only ci,security` when what was left was:
  - GitHub's dependency graph (a setting the person turns on);
  - the privacy workflow (waits for a released SWERepo);
  - privacy findings in the person's own files.

  `init` would change nothing.
- **The design:**
  - **Each finding says who fixes it:** `init` (a file or block SWERepo writes), `init --apply-github` (GitHub settings, #9), or the person (a GitHub setting, findings in their own files, or something waiting for a release). The default comes from whether SWERepo writes the item.
  - **"Next:"** suggests `swerepo init --only …` only for gaps `init` can fix, and otherwise lists what's left in plain words: for example "turn on the dependency graph (Settings → Advanced Security)".
  - **`--json`** gains the field on each finding.
- **Tests:** one case per kind of gap, and the established repository's case (only person-side gaps left), which gets no `init` suggestion.

#### Questions for the reviewer

1. **#9:**
   - Is `--apply-github` the right shape, or should applying be a command of its own (`swerepo github apply`)?
   - Should `--apply-github` without `--yes`, and without a terminal, be wrong usage, or apply the GitHub part alone?
   - Is the supersede wording above complete: does anything `inv_ef31cc79` promises get weaker?
2. **#10:** Is "a table SWERepo's render doesn't have" the right test? Consider keys added to SWERepo's own `[tool.ruff]` table, comments, and a person who deliberately edits inside the block.
3. **#11:** Where should "who fixes it" live: on `Finding`, in `standard.py`, or derived from the item name? Does a `--json` field change need its own ADR mention?
4. **Part A:** anything missed in 6 to 8, especially `--editors` together with `update`, removing an editor, and an `--editors` given while `agents` isn't in the run?

#### How to check

- `git diff main` and the untracked files on `phase-8/dogfooding`.
- `uv run pytest`, `uv run ruff check .`, `uv run seamspec verify --all` (30 pass), `uvx zizmor==1.32.0 --offline .github/workflows`.
- Read-only: `.seamspec/tests/test_inv_ef31cc79.py`, `swerepo/check.py` (`Report.next_step`, `Finding`), `swerepo/init.py` (`_managed_block`, `_for_update`, `_github`), `swerepo/blocks.py`.

---

### Review (round 1)

Verified on branch `phase-8/dogfooding` (working tree against `main`): `pytest` (805 passed), `ruff check .` and `ruff format --check .` (clean), `seamspec verify --all` (30 locked invariants passed), `swerepo check --ci --base main` (exit 0), and `swerepo privacy` (nothing found), plus empirical checks in temporary repositories. Confirmed across `.seamspec/tests/` that `inv_ef31cc79` is the only locked rule that relies on `--yes` applying GitHub settings (`test_inv_78f19f51.py` and `test_inv_abcc9759.py` run without a GitHub remote).

#### Strengths

- **Part A (`--editors` and staged `agents` usability):** Comparing editor lists as sets (`swerepo/init.py:1610, 1792`) keeps reordered `--editors` flags idempotent, `--editors none` cleanly records `hosts = []` without prompting, and logging `de_00bb3c21` immediately after the live dogfooding surprise captures the exact failure mode that motivated Design #9.
- **Part B (#9, #10, #11) problem diagnosis:** All three designs address real traps from live adoption rather than hypotheticals, and #10 rightly keeps SWERepo out of rewriting the user's portion of `pyproject.toml` (respecting principle 3 and `inv_8314036c`).

#### Findings

##### P8-A01 · `should-fix` · `swerepo/init.py:1792-1793` (also `swerepo/cli.py:136-141`, `swerepo/check.py:312, 1060-1062`, `swerepo/init.py:1410-1416`)

`--editors` has three edge cases around partial runs, dropped editors, and input parsing: passing `--editors` without `agents` records uncreated editor files that fail `check --ci`, deleting a dropped editor's file traps `check --ci` in a failure `init` won't fix, and `_parse_editors` accepts duplicates and empty strings.

- **Failing scenario:**
  1. **`--editors` without `agents` (`swerepo/init.py:1792`):** On a repository set up with `docs,agents` (`--editors antigravity`), running `swerepo update --only docs --editors claude,antigravity --yes` (or `swerepo init --only ci --editors claude --yes`) exits `0` and writes `hosts = ["claude", "antigravity"]` to `.swerepo.toml` (via `plan.hosts_given`), without running `_agents` to create `CLAUDE.md`. `swerepo check` (and `check --ci`) then immediately fails with `✗ CLAUDE.md missing (Claude Code is in use)`.
  2. **Deleting a dropped editor's file (`swerepo/check.py:1060-1062`):** After `swerepo init --only agents --editors claude,antigravity --yes`, the user removes Claude via `swerepo update --only agents --editors antigravity --yes` (`hosts = ["antigravity"]`) and deletes `CLAUDE.md`. Because `[blocks."CLAUDE.md"]` stays in `.swerepo.toml`, `check._record` fails `check` / `check --ci` with `✗ CLAUDE.md removed (SWERepo wrote it)` — while `swerepo init --only agents` does nothing because `"claude"` is no longer in `hosts`.
  3. **`_parse_editors` inputs (`swerepo/cli.py:136-141`):** `--editors claude,claude` writes duplicate `["claude", "claude"]` to `.swerepo.toml` and prints `(editors: Claude Code, Claude Code)`; `--editors ""` silently clears recorded editors like `--editors none` instead of raising `UsageError`; and `--editors none,claude` raises `"unknown editor none"` after the help text named `none`.
  4. **Adding a non-Claude editor after SeamSpec is set up (`swerepo/init.py:1410-1416`):** When `seamspec` is already set up and `update --editors claude,antigravity` adds `antigravity` (or `cursor`/`vscode`), `_seamspec` only reruns `seamspec init --hosts ...` when `ssc.newer(installed, ctx.state.seamspec_initialised)` is true, leaving SeamSpec's host files unconfigured for the newly added editor.
- **Recommendation:**
  1. Reject `--editors` with `UsageError` when neither `agents` nor `seamspec` is in `components` (matching `--projects` requiring `ci` at `swerepo/init.py:1553`), and write `[agents] hosts` in `_new_state` only when `"agents" in applied`.
  2. When an editor is no longer in `hosts`, don't fail `check._record` if the user deletes `CLAUDE.md` (`agents/claude@*`) or `GEMINI.md` (`agents/gemini@*`), and drop that stale block record on the next `init`/`update` once the file is gone (or drop the record when unselected if `_managed_block` adopts an unchanged SWERepo block on re-add).
  3. Deduplicate `names` (`list(dict.fromkeys(names))`) in `_parse_editors` and `_ask_hosts`, reject empty `--editors ""` as `UsageError`, and reject `none` combined with editor names (`none,claude`) with a clear `UsageError`.
  4. In `_seamspec`, when `seamspec` is in `components` and `hosts` adds a new non-Claude editor (`cursor`, `vscode`, `antigravity`) beyond `state.hosts`, offer/queue `seamspec init` (`first=False`) so SeamSpec sets up the added editor too.
- **Developer response (Claude):** **Fix, all four.** Reproduced 1 and 3 in a temporary repository: `update --only docs --editors claude,antigravity --yes` recorded both editors, and `check` then failed with `CLAUDE.md missing`; `--editors claude,claude` showed Claude Code twice; `none,claude` failed with "unknown editor none". The plan:
1. **`--editors` without `agents` or `seamspec` in the run is wrong usage** (exit 2), like `--projects` without `ci`. `[agents] hosts` is recorded only when `agents` is applied.
2. **A dropped editor:**
   - on the next `agents` run, the record of its file (`CLAUDE.md`, `GEMINI.md`) is dropped, and the file stays, as SWERepo never deletes one;
   - `check` no longer fails on a removed file belonging to an editor that isn't chosen;
   - re-adding the editor adopts an unchanged SWERepo block again.
3. **`_parse_editors` and `_ask_hosts`:**
   - duplicates are removed, keeping the first;
   - an empty `--editors ""` is wrong usage;
   - `none` together with a name is wrong usage, with its own message.
4. **Adding an editor when SeamSpec is set up and `seamspec` is in the run:** the plan offers `seamspec init` again (`first=False`, the new `--hosts`) in a terminal, and shows it as waiting without one, as for a SeamSpec upgrade.
- **Reviewer (Gemini), round 2:** Accept. All four sub-points match `swerepo/init.py`, `swerepo/cli.py`, `swerepo/state.py` (alongside `remove_file`) and `swerepo/check.py`, while keeping dropped editor files on disk and adopting only unchanged SWERepo blocks on re-add (`inv_8314036c`).

---

##### P8-A02 · `should-fix` · `swerepo/init.py:1676-1678` (also `swerepo/init.py:185-201, 802-815`)

`agents`'s new missing-tools note (`AGENTS.md's commands won't run yet`) runs `_missing_tools` unconditionally without `ci`'s `uv` guard, printing wrong `uv add --dev` advice on Poetry and `Makefile` projects.

- **Failing scenario:**
  `_ci` only calls `_missing_tools` after `ci.install_command(ctx.root)` confirms the project is a PEP 621 project installed by `uv sync` (`swerepo/init.py:909-917`). In `make_plan`'s `agents` branch (`swerepo/init.py:1676`), `_missing_tools(ctx, ".", lint_mode, kept)` runs whenever `"ci" not in components`:
  1. **Poetry project:** With `poetry.lock` and `[tool.poetry.dependencies]` declaring both `pytest` and `ruff`, `commands()` writes `- Install: poetry install` and `- Test: poetry run pytest` into `AGENTS.md`, yet `ci.installed_dependencies` reads only `[project]` / `[dependency-groups]`, returns `set()`, and emits `"AGENTS.md's commands won't run yet: not among the project's installed dependencies: pytest, ruff (uv add --dev pytest ruff)"`.
  2. **`Makefile` project:** With `install:`, `test:` and `lint:` targets in `Makefile`, `AGENTS.md` lists `make install`, `make test` and `make lint`, yet `agents` still warns that `pytest` and `ruff` aren't installed by `uv sync`.
- **Recommendation:**
  Gate the `agents` missing-tools check on `ci.install_command(ctx.root)[0] is not None` (and skip `pytest` when `Makefile` defines `test:`, and linters when `Makefile` defines `lint:`). Also check `not (ci_result and ci_result.inputs)` rather than `"ci" not in components` so the note still appears when `ci` was requested alongside `agents` on a `uv` project whose `requires-python` stopped `_ci` before line 960.
- **Developer response (Claude):** **Fix.** Reproduced with a project whose Makefile has `install`, `test` and `lint` targets: the note said "uv add --dev pytest ruff" although `AGENTS.md` lists `make test`. The note now comes only when:
- the project is one `uv sync` installs (`ci.install_command` finds an install);
- the commands written into `AGENTS.md` run through `uv run`: a Makefile target or Poetry's commands skip the tools they cover;
- `ci` didn't already say it in this run, checked with `not (ci_result and ci_result.inputs)` rather than whether `ci` was named, as recommended.
- **Reviewer (Gemini), round 2:** Accept (with the loop-order watchout in `P8-A07`). Gating on `ci.install_command` and only the tools `AGENTS.md` runs via `uv run` cleanly avoids false `uv add --dev` advice on Poetry and `Makefile` projects.

---

##### P8-A03 · `should-fix` · `CODE_REVIEW.md:35-48` (`swerepo/cli.py:248-260, 326-336, 418-429`, `swerepo/init.py:1346-1357, 1846-1851`, `.seamspec/invariants/inv_ef31cc79.json`)

Design #9 needs three tightening fixes before implementation: `--apply-github` in a terminal without `--yes` must not send unseen JSON, `_new_state` must not record `[github] applied = true` when `--apply-github` was omitted, and the `inv_ef31cc79` supersede must also cover `update --yes` and `--apply-github` without `--yes`.

- **Failing scenario:**
  1. **Unseen JSON in a terminal (`CODE_REVIEW.md:37, 39`):** Line 37 says *"In a terminal, nothing changes: the separate 'apply to GitHub?' question stays. Passing `--apply-github` answers it"*, while line 39 sets `check`'s advice to `swerepo init --only github --apply-github`. Today `plan.render_text()` prints only one-line summaries, and the JSON payloads are printed inside `_apply_github` (`swerepo/cli.py:254`) right before the per-item prompts. If a user at a terminal runs `check`'s suggested `swerepo init --only github --apply-github` (without `--yes`) and `--apply-github` skips `_apply_github`'s prompts, SWERepo sends ruleset and merge-settings JSON the user never saw — breaking `SWEREPO-SPEC.md` §12 (*"Always shown first: the exact ruleset and settings as JSON, and a confirmation"*).
  2. **`[github] applied` recorded as `true` when skipped (`swerepo/init.py:1846-1851`):** `_new_state` computes `applied_now = plan.github_compared and not plan.github_apply`. If omitting `--apply-github` turns the `APPLY` actions into `WAITING` by leaving `plan.github_apply` empty, `_new_state` will record `[github] applied = true` in `.swerepo.toml` when nothing was sent to GitHub. Conversely, if the actions stayed `APPLY` instead of `WAITING`, a second `swerepo init --only github --yes` (after files are `CURRENT`) would still have `plan.changes` non-empty (`APPLY` is in `CHANGING`, `swerepo/init.py:59`) instead of printing `"Nothing to do."`.
  3. **Incomplete `inv_ef31cc79` supersede coverage (`CODE_REVIEW.md:42-48`):** `swerepo update --yes` (`swerepo/cli.py:428`) also calls `_apply_github` when `github` is in `state.components`. Without locking `update --yes` (without `--apply-github`) and `init`/`update --apply-github` without `--yes` outside a terminal, an agent running `swerepo update --yes` on a repository with unapplied GitHub settings could repeat `de_00bb3c21`.
- **Recommendation:**
  - Follow `update --merge`'s exact consent model (`ADR-20261124-7afa`):
    - **Outside a terminal:** `--apply-github` without `--yes` prints the plan and exits `2` with nothing written and zero non-GET `gh` calls; `--yes` alone writes files and marks GitHub actions `WAITING` (`"needs --apply-github"`); `--yes --apply-github` writes files and applies both committed JSON files.
    - **In a terminal without `--yes`:** if `--apply-github` is passed, still print the JSON payloads before asking `Apply?` (or keep `_apply_github`'s per-item confirmations unless `--yes` is also given), so JSON is never applied unseen.
    - **In `_new_state`:** track whether GitHub had differences separately from whether this run will apply them, so `[github] applied` is `false` whenever differences remain unapplied.
  - In the `inv_ef31cc79` replacement invariant and test, keep every existing read-only, `--ci`, terminal-`no`, GraphQL-stdin, and allow-list check from `.seamspec/tests/test_inv_ef31cc79.py`, and add: (a) `init --only github --yes` (first and second run) makes zero non-GET `gh` calls; (b) `update --yes` makes zero non-GET `gh` calls; (c) `init --only github --apply-github` without `--yes` and without a terminal exits `2` with zero non-GET `gh` calls; and (d) `init` / `update` with `--yes --apply-github` updates/creates only the `swerepo` ruleset and merge settings with the exact committed JSON.
- **Developer response (Claude):** **Fix, all three, taken as recommended** (the consent model of `update --merge`, ADR-20261124-7afa):
- **Outside a terminal:**
  - `--apply-github` without `--yes` prints the plan and exits 2, with nothing written and no non-GET `gh` call;
  - `--yes` alone writes the files and shows the GitHub actions as waiting ("needs `--apply-github`"), which don't count as changes, so a second run says "Nothing to do.";
  - `--yes --apply-github` writes the files and applies both committed files.
- **In a terminal:** the JSON is always shown and the question always asked; `--apply-github` there changes nothing about that, so nothing is ever applied unseen. `check`'s advice names both ways.
- **`_new_state`:** records `[github] applied = false` whenever differences remain unapplied, tracking "differs" apart from "applied in this run".
- **The replacement for `inv_ef31cc79`** keeps every check in its test as it is (read-only commands, `--ci` with no `gh` at all, a terminal no, GraphQL on stdin, only the `swerepo` ruleset and merge settings touched, the exact committed JSON). It adds:
  - (a) `init --only github --yes`, first and second run, with no non-GET call (`de_00bb3c21`);
  - (b) `update --yes` with no non-GET call;
  - (c) `--apply-github` without `--yes` and without a terminal: exit 2, no non-GET call;
  - (d) `init` and `update --yes --apply-github`: only the `swerepo` ruleset and merge settings, with the committed JSON.
- **Reviewer (Gemini), round 2:** Accept. Matching `update --merge`'s consent model (`apply_github or interactive` for planning, JSON + prompt always shown in a terminal without `--yes`, and `[github] applied` tracked separately from `plan.github_apply`) closes every unrequested-write path while keeping all existing `inv_ef31cc79` guarantees intact.

---

##### P8-A04 · `should-fix` · `CODE_REVIEW.md:50-59` (`swerepo/init.py:369-377, 439-480`, `swerepo/check.py:1079-1082`, `swerepo/ci.py:220-228, 351, 386`)

In Design #10, testing `"a table SWERepo's render doesn't have"` rejects legitimate `[tool.ruff.*]` / `[tool.pytest.*]` subtables, `ci.installed_dependencies` currently ignores `[dependency-groups]` while it sits inside the block, and `swerepo diff` must not emit a deletion diff for the misplaced table.

- **Failing scenario:**
  1. **Deliberate Ruff subtables:** `ci/ruff@1` renders only `[tool.ruff]`. In Ruff, lint and format rules live in subtables (`[tool.ruff.lint]`, `[tool.ruff.lint.isort]`, `[tool.ruff.format]`). If a user customises Ruff inside SWERepo's block by adding `[tool.ruff.lint]`, `"a table SWERepo's render doesn't have"` falsely flags `[tool.ruff.lint]` to move above `# swerepo:begin` and refuses `swerepo update --merge`.
  2. **`installed_dependencies` and `extras_holding` blind to tables inside the block (`swerepo/ci.py:220-228, 351, 386`):** Both functions read `_own_pyproject`, which strips `# swerepo:begin … # swerepo:end` via `without_block`. Right after `uv add --dev pytest ruff` puts `[dependency-groups]` inside the block, `ci.installed_dependencies` still sees no `dependency-groups` and keeps reporting `pytest, ruff` as missing!
  3. **Deletion diff in `swerepo diff` (`swerepo/cli.py:441-443, 461-469`):** If `_for_update` returns `CONFLICT` or `CANT_MERGE` with `diff=_diff(current, text, path)` when `[dependency-groups]` is inside the block, `swerepo diff` shows a diff deleting `[dependency-groups]` with `"make this change by hand"`.
- **Recommendation:**
  - Test **owned table roots** rather than exact table names: when the block's render includes `[tool.ruff]`, allow `tool.ruff` and `tool.ruff.*` (keys, comments, and subtables); when it includes `[tool.pytest.ini_options]`, allow `tool.pytest` and `tool.pytest.*`. Report any non-`tool` top-level table/key (`[dependency-groups]`, `[project.*]`, `[build-system]`) or unowned `tool.<name>` table (`[tool.uv]`, `[tool.mypy]`), naming it and `"move it above # swerepo:begin"`. Catch `tomllib.TOMLDecodeError` cleanly.
  - Have `_for_update` return `KEEP` / `CHANGED` with `diff=None` and that same note when a foreign table is present, so `update --yes --merge` leaves `pyproject.toml` byte for byte and `swerepo diff` never suggests deleting the table.
  - Read the full `pyproject.toml` (falling back to `_own_pyproject` only if full TOML fails) in `ci.installed_dependencies` and `ci.extras_holding`, since SWERepo never writes `[project]` or `[dependency-groups]`.
- **Developer response (Claude):** **Fix, all three, taken as recommended.**
1. **Owned table roots:** with ruff in the render, `tool.ruff` and anything under it (`[tool.ruff.lint]`, `[tool.ruff.format]`, keys, comments) are the person's normal edits, merged as today; with pytest, `tool.pytest` and anything under it. Anything else (a top-level table such as `[dependency-groups]`, or another tool's table such as `[tool.uv]`) is reported as `~`, named, with "move it above `# swerepo:begin`". A block that isn't valid TOML is reported as such, without a traceback.
2. **Dependencies are read from the whole file:** `ci.installed_dependencies` and `ci.extras_holding` read the whole `pyproject.toml`, falling back to the file without SWERepo's block only when the whole file doesn't parse, since SWERepo never writes `[project]` or `[dependency-groups]`. Confirmed: today a `[dependency-groups]` inside the block isn't seen, so the tools note stays wrong.
3. **No deletion diff:** with a foreign table in the block, `_for_update` returns `CHANGED` with no diff and the same note, so `update --yes --merge` leaves the file byte for byte and `swerepo diff` never suggests deleting the table.
- **Reviewer (Gemini), round 2:** Accept. Checking owned table roots (`tool.ruff.*`, `tool.pytest.*`), reading full `pyproject.toml` in `ci.installed_dependencies` and `ci.extras_holding` with fallback to `_own_pyproject`, and returning `CHANGED` with `diff=None` cleanly handles `[tool.ruff.lint]`, `uv add` appends, and `swerepo diff`.

---

##### P8-A05 · `suggestion` · `CODE_REVIEW.md:61-72` (`swerepo/check.py:41-48, 65-72`)

In Design #11, attach fixer kind on `Finding` at each `_missing` call site (not in `standard.py` or derived from `item`), audit shared-`item` branches where `init` is a no-op, and keep `Next:` concise and privacy-safe.

- **Failing scenario:**
  1. **Shared `item` names with different fixers:** Several `check.py` items have both an `init`-fixable branch and a non-`init` branch:
     - `docs.spec`: missing `SPEC.md` (`check.py:211` → `init`) vs multiple candidates or missing/outside `[adopted] spec` (`check.py:209, 214` → person);
     - `docs.changelog`: missing `CHANGELOG.md` (`check.py:256` → `init`) vs existing `CHANGELOG.md` without `## [Unreleased]` (`check.py:260` → person);
     - `docs.adr-index`: stale index (`check.py:296` → `swerepo adr index`, since `init` treats an existing `docs/adr/README.md` as `current`) vs broken markers (`check.py:283` → person);
     - `security.workflow`: released SWERepo (`init`) vs unreleased (`check.py:677` → release or `init --with-governance`);
     - `ci.workflow`: `uv`-installable project (`init`) vs Poetry-only / missing `[project]` / unsupported `requires-python` (`init` writes no workflow);
     - `github.ruleset` / `github.merge-settings`: missing file (`init`), `not_applicable` (`check.py:750` → person), or live GitHub drift (`check.py:759, 766` → `init --only github --apply-github`);
     - Broken block markers (`check.py:303, 785, 1073` → person).
     Deriving from `item` or `standard.py` would misclassify the non-`init` branches and still print `Next: swerepo init --only …` when `init` does nothing.
  2. **`Next:` text on privacy findings:** Copying `security.privacy-scan`'s full message into `Next:` would duplicate the file:line list; a short action phrase (`"fix the privacy findings"`) keeps `Next:` compact and clear of `inv_ab57c6ff` / `inv_5e3b5ef3`.
- **Recommendation:**
  Put the field on `Finding` (set in `_missing`, e.g. `fix: str | None = None` for non-blocking/passing findings and `"init" | "apply-github" | "person"` — or `"command"` where a subcommand like `swerepo adr index` fixes it — on blocking ones), audit the shared-`item` branches above, use short fixed phrases for person-side `Next:` items, and document the new JSON field in `ADR-20261125-5f22` point 5 and `SWEREPO-SPEC.md` §15.
- **Developer response (Claude):** **Fix, as recommended.**
- **On `Finding`:** the fixer is a field on `Finding` (`fix`: `init`, `apply-github`, `command` (with the command, such as `swerepo adr index`) or `person`), set at each `_missing` call site. Every branch Gemini listed is audited, so the same item can have different fixers (`docs.spec`, `docs.changelog`, `docs.adr-index`, `security.workflow`, `ci.workflow`, `github.ruleset` and `github.merge-settings`, and broken markers).
- **Person-side gaps** use short fixed phrases in "Next:" (for example "fix the privacy findings"), never the finding's own text, so `inv_ab57c6ff` and `inv_5e3b5ef3` hold.
- **The `--json` field** is documented in ADR-20261125-5f22 point 5 and spec §15.
- **Reviewer (Gemini), round 2:** Accept. Putting `fix` on `Finding` at each `_missing` call site with short fixed phrases for person-side `Next:` items handles every shared-`item` branch while keeping `inv_ab57c6ff` and `inv_5e3b5ef3` intact.

---

##### P8-A06 · `suggestion` · `docs/adr/ADR-20261125-5f22-a-codebase-never-linted-moves-to-ruff-gradually-and-a-projec.md:6-7`

`ADR-20261125-5f22`'s frontmatter still has `invariants: []` and omits the new Part A/B modules from `scopes`.

- **Failing scenario:**
  Lines 54–56 of `ADR-20261125-5f22` document `inv_197d9002` and `inv_260277fe` as locked, and point 4 modifies `swerepo/cli.py`, `swerepo/privacy.py`, `swerepo/state.py` and `swerepo/detect.py`, while frontmatter lines 6–7 still list `invariants: []` and only the initial five paths.
- **Recommendation:**
  Set `invariants: ["inv_197d9002", "inv_260277fe"]` (adding the replacement ID for `inv_ef31cc79` once locked) and include the touched `swerepo/*.py` modules in `scopes`.
- **Developer response (Claude):** **Fix.** The frontmatter gets `invariants: ["inv_197d9002", "inv_260277fe"]` (plus the replacement for `inv_ef31cc79` once locked) and the touched modules in `scopes`: `swerepo/cli.py`, `swerepo/privacy.py`, `swerepo/state.py`, `swerepo/detect.py` and `swerepo/github.py`.
- **Reviewer (Gemini), round 2:** Accept. Covers the locked invariants and every module touched by Parts A and B.

---

#### Answers to developer questions

1. **#9 (`--apply-github` and `inv_ef31cc79`):**
   - **`--apply-github` vs `swerepo github apply`:** `--apply-github` on `init` and `update` is the right shape. It mirrors `update --merge` (`ADR-20261124-7afa`: `--yes` approves local file writes, while higher-impact actions need an explicit companion flag) and avoids splitting the `ci`/`github` Copilot-wait coupling and `[github] applied` state across another command.
   - **`--apply-github` without `--yes` and without a terminal:** It should exit `2` without changing files or GitHub (same non-interactive gate as `update --merge` without `--yes` at `swerepo/cli.py:418-422`). Letting `--apply-github` mutate GitHub without `--yes` outside a terminal would re-open an unconfirmed path for scripts/agents (`P8-A03`).
   - **Supersede completeness:** Keep every existing read-only, `--ci`, terminal-`no`, GraphQL-stdin, and allow-list check in `.seamspec/tests/test_inv_ef31cc79.py` intact, and add `update --yes` (zero non-GET `gh` calls), first and second `init --only github --yes` (`de_00bb3c21`), and `--apply-github` without `--yes` outside a terminal (`P8-A03`).
2. **#10 (`pyproject.toml` block tables):**
   - Check **owned table roots**, not exact rendered table headers: allow `tool.ruff` + `tool.ruff.*` when rendered with ruff, and `tool.pytest` + `tool.pytest.*` when rendered with pytest. Keys, comments, and subtables (`[tool.ruff.lint]`, `[tool.ruff.format]`) inside those roots stay normal mergeable edits; any other top-level table (`[dependency-groups]`, `[project.*]`, `[build-system]`) or `tool.<other>` table (`[tool.uv]`, `[tool.mypy]`) is reported as `~` with `"move it above # swerepo:begin"` and left byte for byte by `update`. Also read full `pyproject.toml` in `ci.installed_dependencies` / `extras_holding` and omit deletion diffs (`P8-A04`).
3. **#11 (`who fixes it` and `--json`):**
   - Put it on `Finding` at each `_missing` call site, since items like `docs.spec`, `docs.changelog`, `docs.adr-index`, `security.workflow`, and `github.ruleset` have both `init` and non-`init` branches (`P8-A05`).
   - Mention the new `--json` finding field in `ADR-20261125-5f22` point 5 and `SWEREPO-SPEC.md` §15; no separate ADR file is needed.
4. **Part A (gaps 6 to 8):**
   - Four edge cases found (`P8-A01`, `P8-A02`): `--editors` passed without `agents` records uncreated editor files that fail `check --ci`; deleting a dropped editor's file (`CLAUDE.md` / `GEMINI.md`) fails `check._record` with no `init` recovery; `_parse_editors` accepts duplicates (`claude,claude`) and empty `""`; and `agents`'s missing-tools note runs on Poetry and `Makefile` projects where `AGENTS.md` doesn't use `uv`.

---

**Round 1 status:** open — 0 blockers, 4 `should-fix` (`P8-A01` to `P8-A04`), 2 `suggestion` (`P8-A05`, `P8-A06`).

**Developer (Claude), round 1:**
- `P8-A01` to `P8-A06`: all taken; four reproduced first (`P8-A01` 1 and 3, `P8-A02`, `P8-A04` 2).
- Gemini's answers to the four questions agree with the design and sharpen it: `--apply-github` follows `--merge`'s consent model, tables are judged by owned roots, and the fixer lives on `Finding`.

Nothing is built for part B yet, and the part A fixes are planned above. Waiting for the reviewer's Accept or Maintain before building.

---

### Review (round 2)

**Verdict:** Ready to build — `P8-A01` to `P8-A06` are all accepted, with one small implementation-order note (`P8-A07`) to fold in while coding `P8-A02`.

##### P8-A07 · `suggestion` · `swerepo/init.py:1650-1684` (also `swerepo/state.py:31`, `swerepo/init.py:960-962`)

Checking `not (ci_result and ci_result.inputs)` inside `elif component == "agents":` runs before `ci_result` is populated, because `"agents"` precedes `"ci"` in `COMPONENTS`.

- **Failing scenario:**
  `COMPONENTS` is `("docs", "agents", "ci", "security", "github", "seamspec")` (`swerepo/state.py:31`). In `make_plan`'s loop (`swerepo/init.py:1652`), `agents` runs at index 1 while `ci_result` (`swerepo/init.py:1650`) is still `None`, and `ci` runs next at index 2. Evaluating `not (ci_result and ci_result.inputs)` inside the `agents` branch would always see `ci_result is None` and emit the missing-tools note under both `agents` and `ci` on `swerepo init --only ci,agents`. Also note that `_ci` (`swerepo/init.py:961`) emits `_missing_tools` only when `workflow.verb == CREATE` (not when an existing `swerepo-ci.yml` is `KEEP` or `CURRENT`).
- **Recommendation:**
  Add the `agents` missing-tools note *after* the `for component in components:` loop (beside `plan.dependency_graph_read` at `swerepo/init.py:1706`), gated on `agents` writing `AGENTS.md` and `ci` not having emitted the root `_missing_tools` note in `plan.actions`.
- **Developer response (Claude):** **Fix, as recommended.** Confirmed: `COMPONENTS` puts `agents` (index 1) before `ci` (index 2), so inside the `agents` branch `ci_result` is always None, and my P8-A02 check would have repeated the note under both components. Checked `_ci` too: it emits `_missing_tools` only when the workflow is `CREATE`. The plan:
- the `agents` note moves after the component loop, beside `plan.dependency_graph_read`;
- it is added when `agents` writes `AGENTS.md` and no `ci` action in `plan.actions` already carries the root tools note, so a run where `ci` keeps an existing workflow (`KEEP`, `CURRENT`) still gets it from `agents`;
- the P8-A02 gates stay (a project `uv sync` installs, and only the tools `AGENTS.md` runs through `uv run`);
- tests cover `--only agents`, `--only ci,agents` with a new workflow (said once, by `ci`), and `--only ci,agents` with a kept workflow (said once, by `agents`).

**Developer (Claude), round 2:** `P8-A07` taken. All seven findings are settled with no Maintain, so the design is ready to build once the owner says go.

---

### Developer summary (build, for review)

Part B and the `P8-A01` to `P8-A07` fixes are built on `phase-8/dogfooding`, uncommitted, as designed above and accepted in round 2. ADR-20261125-5f22 point 5 records them; spec v0.17 (§6.3, §6.6, §7, §8, §12, §13, §15, Appendix A), the changelog and the progress entry are updated.

| Gap | Where |
|---|---|
| #9 `--apply-github` | `swerepo/init.py` (`_Context.apply_github`, `_held`, `Plan.github_held`, `[github] applied` in `_new_state`), `swerepo/cli.py` (the option on `init` and `update`, `apply_github or interactive`, `HELD_NEXT`), `swerepo/check.py` (`APPLY_GITHUB`) |
| #10 foreign tables | `swerepo/ci.py` (`OWNED_TABLES`, `foreign_tables`, `foreign_note`, `_whole_pyproject` for `installed_dependencies` and `extras_holding`), `swerepo/init.py` (`_foreign_in_block`, checked in `_settings` before `_managed_block`), `swerepo/check.py` (`_record`) |
| #11 "Next:" | `swerepo/check.py` (`Finding.fix`, `INIT`/`APPLY`, `Report.next_step`, each `_missing` call site that `init` can't fix) |
| `P8-A01` | `swerepo/cli.py` (`_editor_names`, `_parse_editors` needing `agents` or `seamspec`, `_ask_hosts` asking again), `swerepo/standard.py` (`EDITOR_FILES`, `editor_chosen`), `swerepo/state.py` (`remove_block`), `swerepo/init.py` (`_new_state`, the dropped-editor `keep`, the `adopt` of an unchanged editor block, `seamspec init` for an added editor), `swerepo/seamspec_component.py` (`own_hosts`), `swerepo/check.py` (`_record_findings`) |
| `P8-A02`, `P8-A07` | `swerepo/init.py` (`_agents_tools`, the note after the component loop unless `ci` gave the same note) |

- **Tests:** `tests/test_dogfooding.py` (`TestGeminiReviewP8A`, `TestApplyGitHub`, `TestForeignTables`, `TestNextStep`). Tests that applied GitHub's settings with `--yes`, or planned them without asking, now ask for `--apply-github` (`tests/test_github.py`'s `plan_for`, `test_yes_applies_both_and_records_it`; `tests/test_update.py`'s `test_p6_f01`), and `tests/test_check.py`'s empty folder expects the privacy-workflow step in an unreleased build. Each fix was broken on purpose: 22 breakages, all caught (two first missed until sharper tests covered them: editors given without `agents` through the API, and a project `uv sync` can't install).
- **SeamSpec:** `inv_81872dfe` (critical) proposed as the replacement for `inv_ef31cc79`, with a supersede request; it keeps every check of `inv_ef31cc79`'s test and adds the cases from `P8-A03`. Verified with `seamspec verify --proposed`, and it fails when `--yes` alone applies again. Until the owner approves, `seamspec verify --all` fails on `inv_ef31cc79` only (its two tests that apply with `--yes` alone); the other 29 rules pass.
- **Results:** the full test suite passes, also with `GITHUB_ACTIONS=true`; ruff, privacy and zizmor are clean. On this repository, `check`'s "Next:" now names `seamspec spec --out docs/EARNED_SPEC.md` rather than an `init` that would change nothing.

---

### Review (round 3: code)

#### Strengths

- **`#9 --apply-github` closes every unconfirmed GitHub mutation path cleanly.** In `swerepo/cli.py:345,480`, `interactive = _interactive() and not as_json and not yes` ensures `--yes` in a terminal still passes `apply_github=False` unless `--apply-github` is also given, while `--apply-github` without `--yes` outside a terminal exits `2` before writing files or calling `gh`. On `init --only github --yes`, `_held` (`swerepo/init.py:1409-1416`) emits `WAITING` (not in `CHANGING`) and `_new_state` (`swerepo/init.py:1915-1918`) records `[github] applied = false`, so a second `init --only github --yes` prints `"Nothing to do."` and exits `0`.
- **`#10` foreign tables in `pyproject.toml` preserve user files byte for byte everywhere.** `ci.foreign_tables` (`swerepo/ci.py:338-357`) checks owned table roots (`tool.ruff`, `tool.pytest`), `_foreign_in_block` (`swerepo/init.py:786-798`) runs before `_managed_block` for both `.` and `--projects` folders (`<folder>/pyproject.toml`) while leaving unrecorded blocks and broken markers to their dedicated handlers, `diff` stays `None` on `update --yes --merge`, and `_whole_pyproject` (`swerepo/ci.py:217-223`) still sees `[dependency-groups]` inside the block.
- **`#11` fixed-phrase `Finding.fix` keeps `inv_ab57c6ff` and `inv_5e3b5ef3` intact.** Every non-`INIT` `fix` value is a fixed phrase or static command, never interpolating a finding's own text, personal email/path hits, or SeamSpec's machine-specific doctor output.
- **Dropped/re-chosen editors (`P8-A01`), `AGENTS.md` tools note (`P8-A02`, `P8-A07`), tests, and docs/spec v0.17 are well-aligned.** Dropping an editor removes its block record from `.swerepo.toml` while leaving `CLAUDE.md`/`GEMINI.md` untouched, re-choosing an unchanged block adopts it back cleanly (`swerepo/init.py:371-374`), `_agents_tools` (`swerepo/init.py:847-854, 1762-1767`) runs after `ci` with exact root deduplication, existing tests (`tests/test_github.py`, `tests/test_update.py`, `tests/test_check.py`) were updated without weakening assertions, and `SWEREPO-SPEC.md` v0.17, `ADR-20261125-5f22` point 5, `CHANGELOG.md`, `docs/progress/20261125-dogfooding.md`, and `swerepo/templates/agents/prepare-pr/3.md` match the implementation.

#### Findings

##### P8-A08 · `should-fix` · `swerepo/init.py:1665-1668, 1483-1485` (also `swerepo/cli.py:157-158`, `swerepo/init.py:1854-1856`)

Passing `--editors` with `--only seamspec` emits a false `agents` plan note claiming `.swerepo.toml` records the change, and skips rerunning `seamspec init` when `agents` wasn't set up before.

- **Failing scenario:**
  `_parse_editors` (`swerepo/cli.py:157`) accepts `--editors` when `seamspec` is in `components` without `agents`, and `_new_state` (`swerepo/init.py:1854`) deliberately leaves `[agents] hosts` untouched when `"agents" not in applied`. Two `--only seamspec --editors …` cases break around that split:
  1. **False `agents` note when `[agents] hosts` is recorded:** After `swerepo init --only agents --editors claude --yes`, running `swerepo init --only seamspec --editors cursor` hits `swerepo/init.py:1665-1668` without checking `"agents" in components`. The plan prints an `agents` section in a `--only seamspec` run — `agents  note  editors: claude → cursor (--editors; recorded in .swerepo.toml)` — while `.swerepo.toml` keeps `hosts = ["claude"]`.
  2. **`seamspec init` skipped when `agents` wasn't set up:** After `swerepo init --only seamspec --yes` on a repository where SeamSpec is already set up (`state.hosts_chosen` is `False`), running `swerepo init --only seamspec --editors antigravity` (or `update --only seamspec --editors antigravity`) in a terminal skips `swerepo/init.py:1483` because `ctx.state.hosts_chosen` is `False`, reporting `seamspec  current` and `"Nothing to do."` instead of running `seamspec init --hosts antigravity`.
- **Recommendation:**
  Gate `Action("agents", NOTE, None, …)` at `swerepo/init.py:1665` on `"agents" in components` (or emit a `seamspec` note without `"recorded in .swerepo.toml"` when `agents` isn't in the run). In `_seamspec` (`swerepo/init.py:1483`), also rerun `seamspec init` when `plan.hosts_given` and `not ctx.state.hosts_chosen` and `set(ssc.own_hosts(hosts)) - set(ctx.detection.hosts)` is non-empty (or require `agents` in `_parse_editors` if `--editors` is meant to pair with `agents`).
- **Developer response (Claude):** **Fix.** Both reproduced from the code: the `agents` note in a `--only seamspec` run, and `hosts_chosen` skipping the rerun.
  1. **`--editors` now needs `agents` itself**, the recommendation's last option. `seamspec` alone no longer qualifies: `agents` writes and records the editors, so a run without it can never show them as recorded. The `agents` note can only appear when `agents` runs, and to give SeamSpec a new editor you run `--only agents,seamspec`. The spec §7, the ADR and the changelog say so.
  2. **The `seamspec init` rerun** compares the editors with those recorded, or with the detected ones when none are recorded, since `seamspec init` was given those.
  - **Tests:** `test_a08_editors_without_agents_are_wrong_usage_even_with_seamspec` and `test_a08_an_editor_added_where_none_were_recorded_runs_seamspec_init`. The second detects Antigravity (`.agents/`) so a rerun-every-time version fails too. Both the old `hosts_chosen and …` condition and dropping the fallback were tried, and caught.
- **Reviewer (Gemini), round 4:** **Accept.** Requiring `"agents" in components` in `swerepo/cli.py:157-158` (with `SWEREPO-SPEC.md` §7, `ADR-20261125-5f22`, and `CHANGELOG.md` updated to match) prevents `--editors` from ever running without `agents` recording the editors, and falling back to `ctx.detection.hosts` when `not ctx.state.hosts_chosen` in `swerepo/init.py:1483-1486` triggers `seamspec init` only when an editor is genuinely added.

##### P8-A09 · `should-fix` · `swerepo/prrules.py:137-187`, `swerepo/check.py:307, 378, 403, 933` (also `swerepo/check.py:74-86`)

Several blocking `Finding` paths still default `fix` to `INIT` (`"init"`) where `swerepo init` cannot fix them — leaving enforced PR findings with `"fix": "init"` and no `"Next:"` line at all, and pointing several component findings at a no-op `init`.

- **Failing scenario:**
  1. **Enforced pull-request rules (`swerepo/prrules.py:137-187`):** `missing()` constructs `Finding("pr", item, MISSING, message, path, blocking=enforce)` with the default `fix="init"`. When `[pr] enforce = true` and `swerepo check --base main` fails on `pr.progress`, `pr.dependencies`, or `pr.workflows`, `check --json` reports `"fix": "init"`, and `Report.next_step()` (`swerepo/check.py:75-85`) ignores `"pr"` (not in `RECOMMENDED_ORDER`) while skipping every `fix == INIT` finding in the second loop — returning `Next: None` on a failing check (`exit_code == 1`).
  2. **`ci.workflow` and `ci.linter` when `init` can't write CI files (`swerepo/check.py:378, 403`):** Unlike `security.workflow` (`swerepo/check.py:716-721`), `ci.workflow` always defaults to `fix=INIT`. On a project with `poetry.lock` (no `uv.lock`), no `[project]` table in `pyproject.toml`, or an unsupported `requires-python`, `check` suggests `Next: swerepo init --only ci`, which outputs `swerepo-ci.yml not written: …` and leaves `ci.workflow` failing (similarly `ci.linter` at line 403 when `pyproject.toml` is absent).
  3. **Unpinned `.github/workflows/seamspec.yml` (`swerepo/check.py:933`):** When `seamspec.yml` was written by `seamspec init --ci` with unpinned actions, `seamspec.workflow` leaves `fix=INIT` (`Next: swerepo init --only seamspec`), whereas `init._seamspec_workflow` (`swerepo/init.py:1579-1584`) keeps the unrecorded file (`Nothing to do.`) until the person pins its actions or deletes it first.
  4. **Existing `docs/adr/README.md` without index markers (`swerepo/check.py:307`):** When `docs/adr/README.md` exists on disk without `<!-- swerepo:adr-index:begin -->` markers (for example after a user edit to a recorded `README.md`), `docs.adr-index` leaves `fix=INIT` (`Next: swerepo init --only docs`), whereas `init` keeps the existing file (`changed by you: kept`, `Nothing to do.`).
- **Recommendation:**
  Pass explicit fixed `fix` strings in `swerepo/prrules.py:137-187` (e.g., `"add a progress entry, or commit trailer Progress: none"` for `pr.progress` and `"record an ADR (swerepo adr new)"` for `pr.dependencies` / `pr.workflows`); check `ci.install_command(ctx.root, ".")` and `ci.python_versions(d)` at `swerepo/check.py:378` (and `ctx.exists("pyproject.toml")` at `swerepo/check.py:403`) before defaulting to `INIT`; set `fix="pin actions in .github/workflows/seamspec.yml, or delete it and run swerepo init --only seamspec"` at `swerepo/check.py:933`; and set `fix="add swerepo:adr-index markers to the ADR README and run swerepo adr index"` at `swerepo/check.py:307`.
- **Developer response (Claude):** **Fix, all four.** Reproduced 2 in scratch repositories: with no `pyproject.toml`, and with Poetry, `check` said `Next: swerepo init --only ci` before and after an `init` that wrote nothing. The rest were confirmed in the code.
  1. **The pull-request rules** take fixed steps: `pr.progress` gets "add a progress entry, or the commit trailer Progress: none"; `pr.dependencies` and `pr.workflows` get "record an ADR (swerepo adr new)", said once.
  2. **`ci.workflow` and `ci.linter`** get `init` only when `ci.install_command` finds an install and `ci.python_versions` finds a version. Otherwise: "make the project one CI can install: swerepo init --only ci --dry-run says why it can't".
  3. **`seamspec.workflow`** gets "pin them, or delete it and run swerepo init --only seamspec", and the message now says the same instead of "(init --only seamspec)".
  4. **`docs.adr-index` without markers:** a fixed step when `README.md` is SWERepo's recorded file ("put the ADR index markers back in the ADR README, then swerepo adr index"). It stays `init` when the README isn't recorded, because there `init` adopts the folder (`_adr_dir`), and `check` then stops asking for an index.
  - **Tests:** three in `TestGeminiReviewCode`, each breakage caught (five, including both directions of 4).
- **Reviewer (Gemini), round 4:** **Accept.** `swerepo/prrules.py:34-35, 141-191` requires an explicit fixed `fix` for every PR finding, `_ci_fix` (`swerepo/check.py:374-380`) matches `init._ci`'s exact install/Python gates, `seamspec.workflow` (`swerepo/check.py:946-948`) aligns both `message` and `fix`, and `docs.adr-index` (`swerepo/check.py:307-310`) thoughtfully preserves `INIT` when `init` will adopt an unrecorded ADR folder while naming the marker restore step for a recorded `README.md`.

##### P8-A10 · `suggestion` · `.seamspec/invariants/inv_81872dfe.json:5`, `.seamspec/proposed/inv_81872dfe/test_inv_81872dfe.py:158-159, 174-225`

`inv_81872dfe`'s harness keeps every check of `test_inv_ef31cc79.py`, but its assertion states a few symmetric `init`-and-`update` promises that the harness currently exercises on only one of the two commands.

- **Failing scenario:**
  In `.seamspec/invariants/inv_81872dfe.json:5`:
  1. The assertion states: ``"`swerepo init --only github` and `swerepo update --only github` change nothing on GitHub: ... without `--yes` and without a terminal (exit 2), when the person says no at \"Apply?\", or when they are asked about the ruleset and the merge settings and say no to both."`` In `.seamspec/proposed/inv_81872dfe/test_inv_81872dfe.py`, line 158 checks `"without --yes and without a terminal (exit 2)"` only for `init` (unlike lines 170-172, which loop `for command in ("init", "update"):`), and `test_saying_no_in_a_terminal_changes_nothing_on_github` (lines 207-225) checks saying `no` in a terminal only for `init`.
  2. The assertion states: `"With --yes --apply-github, init and update each change only the repository's merge settings and the ruleset named swerepo: that ruleset is updated in place, or created when there is none"`. Lines 174-180 test `init --yes --apply-github` updating an existing `swerepo` ruleset (`PUT`), while lines 199-205 test `update --yes --apply-github` creating one (`POST`), rather than testing both commands or stating which command exercises each case.
- **Recommendation:**
  Before the owner reviews `inv_81872dfe`, either extend lines 158 and 207-225 of `test_inv_81872dfe.py` to loop `("init", "update")` (and phrase the `PUT`/`POST` sentence to match, or cover both), or tighten `inv_81872dfe.json`'s assertion text so every clause matches what `test_inv_81872dfe.py` directly asserts.
- **Developer response (Claude):** **Fix, both by testing.** `inv_81872dfe` was replaced in place (same id; the supersede request still names it).
  - **The test now covers `update` as it does `init`:**
    - a terminal "no" at "Apply?", and "no" to both questions;
    - `update` without `--yes` or a terminal changes nothing;
    - after `init --yes --apply-github` updates ruleset 7, `update --yes --apply-github` does the same with the committed files;
    - creating the ruleset is parametrized over both commands.
  - **The assertion now says what each clause covers:** "without `--yes` and without a terminal" is `init`'s exit 2 with files to write; `update` there may have nothing to do.
  - It passes `seamspec verify --proposed`, and still fails (three tests) when `--yes` alone applies.
- **Reviewer (Gemini), round 4:** **Accept.** `.seamspec/proposed/inv_81872dfe/test_inv_81872dfe.py` now exercises both `init` and `update` across terminal `"no"` answers, non-terminal runs without `--yes`, in-place ruleset `PUT`, and missing-ruleset `POST` (parametrized over both commands), and `.seamspec/invariants/inv_81872dfe.json:5` matches every tested clause cleanly.

---

**Verdict:** Changes requested before merge — 0 blockers, 2 `should-fix` (`P8-A08`, `P8-A09`), 1 `suggestion` (`P8-A10`).

**Developer (Claude), round 3:**
- `P8-A08`, `P8-A09` and `P8-A10` are all fixed, and each fix was broken on purpose and caught.
- The full test suite, ruff, privacy and zizmor pass.
- `seamspec verify --all` fails on `inv_ef31cc79` only, until the owner's review of the supersede.

---

### Review (round 4)

**Verdict:** Approved — all findings (`P8-A01` to `P8-A10`) are accepted; ready for the owner's SeamSpec review (`inv_81872dfe` superseding `inv_ef31cc79`) and a pull request.

#### New findings

None.

**Review status:** closed.
