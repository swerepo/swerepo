---
id: ADR-20261122-4a06
title: "The ci component: swerepo-ci.yml, project settings and SeamSpec in CI"
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-22
scopes: ["swerepo/ci.py", "swerepo/init.py", "swerepo/check.py", "swerepo/templates/ci/", "SWEREPO-SPEC.md"]
invariants: []              # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261122-4a06: The ci component: swerepo-ci.yml, project settings and SeamSpec in CI

## Context

Phase 4 makes `swerepo init` apply the `ci` component (spec §6.2, §6.3, §11): `.github/workflows/swerepo-ci.yml`, ruff and pytest settings, and per-project jobs for `--projects`. Four questions had no answer in the spec:

1. **SeamSpec's own CI workflow sits outside `ci-ok`.** The ruleset requires only `ci-ok`, so a failing locked rule in SeamSpec's workflow wouldn't block a merge (open since Phase 0's review, P0-F01; listed in `docs/PROGRESS.md` as a decision for the owner).
2. **Templates hold no logic** (ADR-20261120-b25a), but the workflow varies: Python versions, linters, which jobs exist, which projects get jobs.
3. **ADR-20261120-9495 point 5** left open how settings merged into `pyproject.toml` are fingerprinted.
4. **How CI installs the project** when it may not use uv's lockfile.

## Decision

1. **SeamSpec runs inside `swerepo-ci.yml`** (the owner's choice, 2026-11-22: option (a), recommended by developer and reviewer). The workflow always has a `seamspec` job: when `.seamspec/config.toml` is absent its first step says so and the rest are skipped, so a repository that sets up SeamSpec later is covered without touching the workflow. When it is present the job runs `seamspec doctor --ci` with P0-F01's base logic, `seamspec verify --all --ci` and, when `docs/EARNED_SPEC.md` exists, `seamspec spec --check`, through `uvx seamspec==<pin>` (the pin is recorded under `[tools] seamspec`). The `seamspec` component (Phase 7) will run `seamspec init --no-ci`. Edge cases recorded for Phase 7: `--only seamspec` without the `ci` component falls back to `seamspec init --ci` (or warns that nothing runs SeamSpec in CI); `strict` mode expects SeamSpec's own workflow, so `check` will say so.
2. **The jobs** (spec §6.2): `lint`, `test` (a matrix of the supported Python versions), `test-macos` (pushes only), `workflow-audit` (zizmor at a pinned version on `.github/workflows/`), `seamspec`, `governance` (pull requests only), `dependency-review` (pull requests to public repositories; GitHub's action at a pinned commit), one `lint-<name>` and `test-<name>` job per project listed with `--projects`, and `ci-ok`.
3. **`ci-ok` reads `toJSON(needs)`** with `jq`: every job must succeed, except a job skipped by design, which must be skipped: `test-macos` off pushes, `governance` off pull requests, `dependency-review` off pull requests to public repositories. Adding a job means adding it to `needs:` and nothing else. A failed, cancelled or unexpectedly skipped job fails it.
4. **Composition without logic.** The workflow template `ci/workflow@N` has placeholders for the parts that vary. Optional parts are their own templates at the **same version number** as the workflow (`ci/job-governance@N`, `ci/job-project@N`, `ci/lint-ruff@N`, `ci/lint-gradual@N`), so one version names the whole render. Values SWERepo computes (the Python list, kept linters' commands, `needs:`) are text. The inputs are recorded (`[values] python`, `default_branch`, `ci_install`, `lint`, `governance_command`; `[adopted] linters`; `[projects] listed` and each project's `[projects.inputs."<folder>"]`; `[tools] seamspec`) so `update` (Phase 6) can rebuild the earlier render. Each workflow keeps its own snapshot: the privacy workflow records `privacy_command` and `privacy_python`, so a security-only run never decides the CI workflow's first Python versions (review: Copilot on PR #8). They are recorded only when the workflow is created, rewritten or already current, so they always rebuild what is on disk (review P4-F02); a recorded value is used only if it is one standard 1 writes (an install command, a SWERepo command, a plain version), so a `.swerepo.toml` from a branch can't put a command into a workflow (P4-F03).
5. **The governance job** runs `swerepo check --ci --base origin/<base> --author <login>`. Its command follows spec §15: a released SWERepo pins itself (`uvx swerepo==x.y.z`); SWERepo's own repository (project `swerepo` with a `swerepo/` package) runs `uv run --locked swerepo`; an unreleased build adds the job only with `--with-governance`, installing from `git+https://github.com/swerepo/swerepo@main`, and the plan says so. The `[pr] skip_progress_label` input is not wired in standard 1's first template: the `Progress: none` trailer works everywhere.
6. **Installing the project:** `uv sync --locked` when the project has a `uv.lock`, or is a member of a uv workspace above it that has one (P4-F01); `uv sync` otherwise. A project uv can't install (a `poetry.lock` without `uv.lock`, or no `pyproject.toml`) gets no workflow in this version; the plan says why. uv itself is pinned to the version SWERepo's own CI uses. Lint and tests run the project's own tools with `uv run`; when pytest or ruff isn't among what `uv sync` installs there (dependencies and default groups, not extras), the plan says to add them, for the root and for each listed project in its own folder (Copilot on PR #8). SWERepo never edits dependencies.
7. **Python versions** come from `requires-python` (or classifiers), up to 3.14, the newest standard 1 knows; with none declared, 3.11 to 3.14 and a note to declare it. `lint`, `test-macos`, `seamspec` and `governance` run on the newest.
8. **Settings in `pyproject.toml` are a marked block** (`# swerepo:begin` … `# swerepo:end`, template `ci/pyproject@N`) at the end of the file, recorded under `[blocks]` like any other block. This settles ADR-20261120-9495 point 5: the block's text is fingerprinted, and `init`'s rule for files it didn't write (only a marked block at the end, inv_8314036c) holds for `pyproject.toml` too. The block holds `[tool.ruff]` (with `extend-exclude = [".seamspec"]`) only when ruff is chosen and not configured, and `[tool.pytest.ini_options]` only when the project has no pytest configuration. The result must parse as TOML with every one of the person's values unchanged; otherwise the file is kept and the plan says why. Spec §9's `[sections]` table is replaced by this block.
9. **Linters** (spec §6.3): ruff configured → kept. Other tools found → the person chooses in a terminal: **keep them** (the default, and what `--yes` picks; recorded in `[adopted] linters`; the lint job runs each with `.seamspec` excluded on its command line) or **move to ruff gradually** (`[values] lint = "gradual"`; ruff settings added with the line length read from black or flake8; the lint job runs ruff on the Python files the pull request, or push, changed). Nothing found → ruff.
10. **Asked for later:** `--projects` or `--with-governance` on a repository already set up rewrites `swerepo-ci.yml` (and `swerepo-privacy.yml`) when SWERepo wrote it and nobody changed it since, checked again just before writing; a changed workflow stays as it is, and the plan says the request waits for `update` (review P4-F02).
11. **Monorepos** (spec §11): `--projects a,b` lists Python projects (a folder with a `pyproject.toml`), including ones under folders that detection skips (`tools/`, `examples/`; Phase 1's review). Each gets lint and test jobs with `working-directory` and its own settings block, unless the root `pyproject.toml` already configures ruff. Its lint follows its own configuration: a root `[tool.ruff]` doesn't make a black project a ruff one (P4-F04). A folder whose jobs would take a fixed job's name (`macos` → `test-macos`) is refused, and `check` compares each project's test matrix with its own `requires-python` (Copilot on PR #8). `check` reports every project root that no listed job covers, unless it is recorded under `[projects] not_covered`.

**Alternatives considered:**
- **SeamSpec's own workflow, required as a second check.** Two workflows to keep in step, and the ruleset needs an extra required check in every repository.
- **The SeamSpec job only when SeamSpec is set up.** Setting it up later (the recommended order puts `ci` first) would then need a workflow update.
- **A template per workflow variant.** Linters × jobs × projects multiply; fragments at one version number keep a single id per render.
- **Writing YAML from code.** Breaks ADR-20261120-b25a: templates are data a reviewer can read.
- **Merging TOML tables with tomlkit and hashing their parsed values** (spec §9's `[sections]`). Edits a person's file away from its end, and the hash would miss comment changes a three-way merge has to see.

## Enforced Invariants

None new yet. Once the component works: a generated `swerepo-ci.yml` passes zizmor and its `ci-ok` depends on every other job (spec §6.8's hygiene rule 4 covers the repository's own workflow in Phase 7).

## Consequences

- Repositories set up by SWERepo get locked rules that block merges, with no extra required check.
- The workflow is a managed file: a person's edit shows as `~` and is merged by `update` (Phase 6).
- `zizmor` audits every workflow in `.github/workflows/`, existing ones included; the plan says so, since an existing workflow it flags would fail `ci-ok` until fixed.
- Poetry and requirements-only projects wait for a later version of the template.
