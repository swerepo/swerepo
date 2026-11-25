---
id: ADR-20261124-41e9
title: "Two rules guard the shipped package: no publishing footprint, and released templates never change"
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-24
scopes: ["swerepo/", "swerepo/templates/", "tests/released/", "pyproject.toml", ".github/workflows/swerepo-ci.yml", "swerepo/templates/ci/workflow/", "swerepo/templates/seamspec/workflow/"]
invariants: []              # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261124-41e9: Two rules guard the shipped package: no publishing footprint, and released templates never change

## Context

Two promises about the package become real once `0.1.0` is on PyPI:

- **The package stays clean.** SWERepo sets up no package publishing (ADR-20261124-152d), yet this repository now holds a workflow that does (ADR-20261124-4699). Nothing of it, nor `.seamspec/`, `tests/`, `docs/` or `tools/`, may reach the machines of people who install SWERepo.
- **Released templates never change** (ADR-20261120-b25a): `update` rebuilds an earlier render from the template version recorded in `.swerepo.toml`, so a released template that changed would make every repository that used it look edited, or merge against the wrong base. ADR-20261120-b25a planned "a SeamSpec rule [that] will lock the released files by hash" once the first release exists.

Each rule belongs in SeamSpec, where an agent can't weaken it quietly.

## Decision

1. **Rule 1, no publishing footprint in the shipped package.** Its test:
   - **builds the wheel** through the build backend's standard hook (`uv_build.build_wheel`, PEP 517) into a temporary folder. `uv_build` joins `[dependency-groups] dev` with the same version range as `[build-system]`. It runs its own `uv-build` binary from this environment, found on `PATH`, so the test puts the environment's scripts folder first, also when the environment isn't activated (review P8-F04). The build needs no network and no `uv`, and runs inside sandboxes where `uv build` can't (review P8-D05);
   - checks that every file in the wheel outside the `.dist-info` folder lives under `swerepo/`, and builds the sdist the same way, since the release publishes both: it holds nothing but `swerepo/`, `PKG-INFO`, `pyproject.toml`, `README.md` and `LICENSE` (SeamSpec's reviewer);
   - checks that no file under `swerepo/` (code and templates) names a publishing tool or endpoint: `gh-action-pypi-publish`, `uv publish`, `twine upload`, `poetry publish`, `hatch publish`, `flit publish` or `upload.pypi.org`;
   - checks that `swerepo` offers no `release` component and no `--release` or `--no-release` flag: `init`, `check` and `update` each refuse them as wrong usage because `release` is unknown (the reason is checked, not only the exit code), and `check` and `init` with options that exist aren't refused;
   - checks that `pyproject.toml` names `uv_build` as the build backend, so the packages it checks are the ones a release builds (SeamSpec's reviewer, second read).

   It fails, and doesn't skip, when the wheel can't be built, so a broken build is never read as a clean one.
2. **Rule 2, released templates and renders never change.** Its test:
   - reads every git tag named `v*` that `packaging.version.Version` can parse, oldest first, all of them and not just the latest;
   - checks that every file under `swerepo/templates/` and `tests/released/` at each tag still exists today with the same content, as a file of the repository: not a link, and not reached through a linked folder. New files are fine; a modified, deleted or linked one fails, and the failure names the file and the tag (P8-F05);
   - **checks the renders put together in Python** (P8-D05). Some recorded template ids are built by code rather than read from one file: the `github/ruleset` and `github/repo-settings` builders, and `ci/workflow` and `ci/pyproject`, which `ci.py` assembles. A change to that code would change a released render while every template file stayed the same. So the release PR commits `tests/released/<version>.json`, holding the fingerprint of what `rebuild.rebuild` produces for every released template id over a fixed set of inputs that covers each branch (solo and team, a code owner or none, Copilot review on or off, each lint mode, projects, the governance job). The test checks today's code still produces each recorded fingerprint;
   - **checks every snapshot present, tags or not** (review P8-D10): each `tests/released/*.json` in the working tree is checked against today's renders even before the first tag and without git, so a wrong snapshot fails in the release PR's own CI, before a tag freezes it;
   - **requires the snapshot of a release:** when the package's own version is a release (`ci.released()`), as installed or as `pyproject.toml` declares it (a bump changes the file before `uv sync`; P8-F05), `tests/released/<version>.json` must exist and hold a fingerprint for every template id whose render is put together in code. Those ids are taken from the code, not from a list kept by hand: `github.BUILDERS`, and every `ci/workflow` and `ci/pyproject` version in the store. So a release PR without its snapshot fails;
   - **before the first tag** there is nothing released to compare files with, so that part passes. That is why unreleased templates, such as `ci-tests@1` in Phase 7, could still change in place;
   - **a shallow clone fails,** because tags or their history may be missing, and a rule that can't see the tags must not pass;
   - **without git at all** (no `.git` file or folder, as in a copy of the staged tree that SeamSpec may use at a commit), it passes and says it couldn't look; CI, which has the full history, is where it holds. A git worktree, where `.git` is a file, counts as git;
   - **the snapshot requirement is self-checked** on a temporary folder: a missing snapshot and an incomplete one fail, a complete one passes, and `ci.released` is true for a release (SeamSpec's reviewer, second read);
   - **a self-check runs the tag comparison on a temporary git repository**, so the rule's core is exercised before this repository has any tag (SeamSpec's reviewer). A released file changed, deleted or replaced by a link is reported, a new file isn't, a shallow clone fails, a worktree counts as git, and no git is reported as such.
3. **CI sees the tags.** Both workflows that run the locked rules gain `fetch-tags: true` beside their `fetch-depth: 0`, so the intent survives a later change of depth: the `seamspec` job of `ci/workflow@2` and SWERepo's `seamspec/workflow@1` (P8-D05). Neither template is released yet, so both change in place. This repository takes the change through `update`, and every repository's locked rules can rely on tags too.
4. **The tags themselves are protected** on this repository by a tag ruleset (no deletion, no force-push, no move), applied with the owner's yes (ADR-20261124-4699, review P8-D09), since this rule reads them as the record of what was released.
5. **Both are proposed in Phase 8's implementation pull request,** once the code they check exists, and verified with `seamspec verify --proposed`. The owner locks them in `seamspec review`. Rule 2's test runs in this repository's own environment, so it may use `packaging`, a runtime dependency already.

**Alternatives considered:**
- **A list of hashes for released templates, kept in a file.** The list would itself need protecting, and someone has to update it at each release. The tags are already the record of what was released.
- **Checking only the latest tag.** A template removed in one release and changed before another would slip past; checking all tags costs little.
- **Checking the package for the word "release".** Too broad: the agents block says only the person publishes, and the spec talks about releases. The test looks for the publishing tools themselves.
- **Rule 1 asserting the exact list of six components** (suggested in P8-D05, which would cover `openspec` too). That would make every future component a supersede of a rule about publishing. The rule checks that `release` is absent; that `openspec` is gone is ordinary tests' job (ADR-20261124-152d).
- **`uv build --wheel --offline`.** It still needs `uv_build` in uv's cache, and `uv` itself panics in some sandboxes.

## Enforced Invariants

Locked by the owner on 2026-11-25, after Gemini's implementation review and two reads by SeamSpec's reviewer:
- `inv_3f05e701`: the shipped package has no publishing footprint (rule 1);
- `inv_7bc9c95a`: what a release shipped never changes, its templates and the renders built in code (rule 2), with `tools/released_snapshot.py` writing each release's snapshot.

## Consequences

- From `v0.1.0` on, a template change means a new version file, as ADR-20261120-b25a already says; the rule makes it impossible to forget.
- Rule 1 builds a wheel each time it runs, in under a second, with the `uv_build` the dev group installs; Gemini judged that acceptable without a gate (its answer to question 1 of the implementation review).
- Each release PR adds a `tests/released/<version>.json`, written by a small script in `tools/`, and can't pass CI without it. The script keeps every input set, also those that render what another does, since which inputs leave a render unchanged is part of what was released (P8-F03). Changing the code that builds a released render means adding a new template version, as for a template file.
- The `seamspec` job in every repository on `ci/workflow@2` fetches full history and tags; that was already true of `fetch-depth: 0`.
