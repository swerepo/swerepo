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
