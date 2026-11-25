---
id: ADR-20261124-4699
title: SWERepo releases itself through a release workflow in this repository only
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-24
scopes: [".github/workflows/release.yml", "pyproject.toml", "CHANGELOG.md", "tools/pypi-placeholder/"]
invariants: []              # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261124-4699: SWERepo releases itself through a release workflow in this repository only

## Context

v0.1 is released after Phase 8 (ADR-20261124-2452). The PyPI name `swerepo` is held by a `0.0.1` placeholder the owner published by hand (ADR-20261119-d68b). That ADR plans trusted publishing from this repository's release workflow, then yanking the placeholder and deleting `tools/pypi-placeholder/`. The spec says SWERepo is published "only with the owner's explicit go-ahead for each release", through "a release workflow with a human approval" (§18).

The `release` component is gone (ADR-20261124-152d), so this workflow is this repository's own: it is never inside `swerepo/` and never shipped to anyone.

Facts this rests on, from GitHub's and PyPI's documentation (read on 2026-11-24):
- **Trusted publishing** needs, on PyPI, the repository owner, the repository name and the workflow's file name. An environment name is optional but "strongly recommended". The publishing job needs `id-token: write`.
- **`pypa/gh-action-pypi-publish`** uploads PEP 740 attestations by default with trusted publishing, and advises separating building from publishing. `uv publish` uploads attestations but doesn't create them.
- **Environment protection:** environments with required reviewers work on public repositories on every plan. "Prevent self-review" is an opt-in setting. GitHub's environments API takes reviewers as numeric user or team IDs.
- **`actions/attest-build-provenance`** works on public repositories on every plan. From version 4 it wraps `actions/attest`.
- **Yanking:** a yanked release is ignored unless it is the only match for an exact pin, so `pip install swerepo` skips it and `pip install swerepo==0.0.1` still works.

## Decision

1. **`.github/workflows/release.yml`**, in this repository only, runs on a pushed `v*` tag. Its jobs, each with only the permissions named (review P8-D01):
   1. **`check`** (`contents: read`):
      - the tagged commit is on `main` (`git merge-base --is-ancestor "$GITHUB_SHA" origin/main`, with the history fetched), so a tag on an unmerged branch stops here;
      - the tag without its `v` equals `[project] version` in `pyproject.toml`;
      - `CHANGELOG.md` has a dated entry for that version (`## [0.1.0] - YYYY-MM-DD`), which is extracted into a `release-notes` artifact;
      - the locked rules pass at the tag (`uv run --locked seamspec verify --all --ci`, with tags fetched), so ADR-20261124-41e9's two rules gate `build` as well as pull requests (review P8-D10). The `test` job's pytest reads only `tests/`, so this is where the locked rules run.
   2. **`test`** (`contents: read`): the test suite, on the Python versions CI tests.
   3. **`build`** (`needs: [check, test]`; `contents: read`, `id-token: write`, `attestations: write`):
      - `uv build` once;
      - only `dist/*.whl` and `dist/*.tar.gz` are kept, with a `SHA256SUMS` file listing them;
      - provenance is signed with `actions/attest-build-provenance`;
      - the files and `SHA256SUMS` are uploaded as an artifact.

      Nothing is built or signed before the tag has passed `check` and `test`.
   4. **`publish`** (`needs: [build]`; `id-token: write` only; `environment: pypi`):
      - waits until the owner approves;
      - downloads that exact artifact into a staging folder and checks it with `sha256sum -c SHA256SUMS`, so the files published are the files built and attested;
      - then moves only the wheel and the sdist into `dist/`, the action's `packages-dir`. The action runs `twine check` on every file there, so `SHA256SUMS` stays behind in the staging folder (Copilot on PR #21);
      - publishes with `pypa/gh-action-pypi-publish` through trusted publishing;
      - never checks out or rebuilds the code.
   5. **`github-release`** (`needs: [publish]`; `contents: write` only):
      - downloads the built files and `release-notes`, with no checkout, so no repository files share a workspace with its write token;
      - runs `gh release create "$TAG" … --verify-tag --notes-file …` against `$GITHUB_REPOSITORY`.
2. **Hardening, as for every workflow here:**
   - actions pinned to commits;
   - `persist-credentials: false` on every checkout;
   - `permissions: {}` at the top;
   - values like the tag name passed to scripts through `env`, never written into them with `${{ }}`;
   - `enable-cache: false` on **every** `astral-sh/setup-uv` step. zizmor 1.32.0 reports `cache-poisoning` (high) for any cached setup in a workflow triggered by tags, whichever job it is in (P8-D01).

   `zizmor` stays clean, since the `workflow-audit` job audits this workflow with the others.
3. **On `swerepo/swerepo`, applied by SWERepo's agent through `gh api` only after the owner's yes, and never shipped in the `swerepo` package:**
   - **The `pypi` environment:**
     - the owner is the required reviewer, resolved from the login to the numeric ID the API takes;
     - `prevent_self_review: false`, because in `solo` mode the owner is the only person who can approve;
     - deployments only from `v*` tags.
   - **A tag ruleset** (the owner's choice on P8-D09), on `refs/tags/v*`, with three rules:
     - `deletion`, so a released tag can't be deleted;
     - `non_fast_forward`, so it can't be force-pushed;
     - `update`, so it can't be moved at all, not even to a later commit, which would be a fast-forward.

     Creating a new `v*` tag stays allowed. ADR-20261124-41e9's template rule reads the tags as the record of what was released, so they must not change.
4. **The trusted publisher** is added by the owner on pypi.org, on the existing `swerepo` project (Manage → Publishing). The values:
   - **Owner:** `swerepo`
   - **Repository name:** `swerepo`
   - **Workflow name:** `release.yml`
   - **Environment name:** `pypi`
5. **The release sequence:**
   1. **The release PR:**
      - `0.1.0.dev0` → `0.1.0`, then `uv lock`, so `uv sync --locked` still passes (P8-D03);
      - `CHANGELOG.md`'s `[Unreleased]` dated as `[0.1.0]`, with a new empty `[Unreleased]`;
      - `tests/released/0.1.0.json`, the fingerprints of the renders put together in code (ADR-20261124-41e9), which the locked rule requires once the version is a release (P8-D10);
      - `README.md` rewritten for people installing from PyPI (P8-D08): what SWERepo is, `uv tool install swerepo`, a quickstart (`check`, `init`, `update`), the six components, and absolute `https://github.com/swerepo/swerepo/blob/main/…` links, since PyPI shows the README as the project page and relative links break there;
      - `Development Status :: 3 - Alpha` instead of `2 - Pre-Alpha` in `pyproject.toml`, and the spec's status line updated.
   2. **The owner pushes the tag:** `v0.1.0`, on the merged commit.
   3. **The owner approves** the `publish` job.
   4. **The cleanup PR:** the owner yanks `0.0.1` on PyPI, and the PR deletes `tools/pypi-placeholder/` and moves the version on to the next `.dev0`.

   SWERepo's agent tags, approves and publishes nothing.

**Alternatives considered:**
- **`uv publish` instead of the PyPA action.** It doesn't create PEP 740 attestations yet; the action does, by default.
- **`actions/attest` directly.** `attest-build-provenance` is a thin wrapper over it and names its purpose. Dependabot keeps either current, and swapping later is a one-line change.
- **Building inside the publish job.** Then what the owner approved would be a build that hasn't happened yet. Building first and publishing the frozen artifact means the files were attested before anyone approved them.
- **"Prevent self-review" on.** Right for `team` mode, but here it would leave nobody able to approve.

## Enforced Invariants

ADR-20261124-41e9 proposes that nothing outside `swerepo/` ships in the wheel, so this workflow, `.seamspec/`, `tests/`, `docs/` and `tools/` never reach users' machines.

## Consequences

- A release needs three deliberate acts by the owner: merging the release PR, pushing the tag and approving the environment.
- Once `0.1.0` is on PyPI, SWERepo writes a pinned `uvx swerepo==0.1.0` for other repositories' `governance` and privacy jobs (§15). This repository keeps `uv run swerepo` from its own checkout.
- Adding `release.yml` changes `.github/workflows/`, so the implementation pull request records the workflow's final shape in this ADR (the `--base` rule counts a changed ADR).
- Tests that assumed an unreleased SWERepo (no `governance` job, no privacy workflow, `uvx --from git+…`) are made independent of the package's own version in the implementation PR, so the version bump changes no test (P8-D03).
- Once `v0.1.0` exists it can't be moved or deleted, and a mistake in a release is fixed by a new version, as on PyPI.
