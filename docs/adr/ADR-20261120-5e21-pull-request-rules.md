---
id: ADR-20261120-5e21
title: How check --base computes the pull-request rules, and who it skips
status: ACCEPTED
date: 2026-11-20
scopes: ["swerepo/prrules.py", "swerepo/cli.py", "swerepo/state.py", "SWEREPO-SPEC.md"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261120-5e21: How check --base computes the pull-request rules, and who it skips

## Context

Spec §6.5 and §15 define rules a pull request must follow, checked by `swerepo check --base REF` in CI: a progress entry per PR (unless opted out), an ADR when a runtime dependency is added, an ADR when a workflow changes (except SWERepo's own changes), and an ADR index that matches the ADR files. They are skipped for bot authors and lockfile-only diffs, and are warnings while `[pr] enforce = false`. The spec leaves the mechanics open: what "the diff" is, how the author reaches `check`, and how a new dependency is recognised.

## Decision

1. **The diff** is the working tree against the merge base of `REF` and `HEAD` (`git merge-base`), so it includes commits on the branch and uncommitted changes; files are compared with `git diff --name-status --no-renames`, run on a temporary copy of git's index so `check` never rewrites `.git/index` (ADR-20261120-fc5a item 10). A rename counts as a delete plus an add. A `REF` git can't resolve is wrong usage (exit 2). An untracked file the merge base has (`git rm --cached`) is a change only if its text differs, never an addition. When git or the index copy fails, the finding is `?` ("git couldn't list the changes"), never "no changes". `--base` runs at the repository's top level only (wrong usage otherwise), because the diff and the merge base's `pyproject.toml` are the whole repository's.
2. **Progress entry:** a file *added* under `docs/progress/` (or the folder in `[adopted] progress_dir`). Opt-outs: a commit since the merge base whose message has the trailer line `Progress: none` (case-insensitive), or `--skip progress` (the workflow passes it when the PR carries the label in `[pr] skip_progress_label`).
3. **New runtime dependency:** a package name in `[project].dependencies` of `pyproject.toml` that the merge base's version didn't have. Names are compared after PEP 503 normalisation (`packaging`), so `Foo_Bar` and `foo-bar` are the same; version changes and extras don't count. An unparsable entry is a `?` naming it. `[project].dependencies` that isn't a list, or an entry that isn't a valid requirement, is `?` ("can't read dependencies: …"), the entry named by position, never by its text.
4. **ADR added or changed:** an added or modified Markdown file directly in the ADR folder (`[adopted] adr_dir`, else `docs/adr`), other than `README.md`, `TEMPLATE.md` and `index.md`.
5. **Workflow changes** are added, modified or deleted files under `.github/workflows/`. An added or modified file doesn't count when it matches what SWERepo recorded writing (`.swerepo.toml` `written` fingerprint), so `swerepo init` and `swerepo update` PRs don't need an ADR (spec §6.5: "the file matches the render recorded").
6. **Who is skipped:** `--author LOGIN` (the workflow passes `github.event.pull_request.user.login` through `env:`, not `github.actor`, which becomes whoever re-runs the job) when the login is in `[pr] exempt_authors` (default `["dependabot[bot]"]`); and diffs whose files are all lockfiles (`uv.lock`, `poetry.lock`, `Pipfile.lock`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `Cargo.lock`, `go.sum`, `Gemfile.lock`). A skip is reported as one `–` line saying why. **`--author` is a new flag** (spec §7 updated).
7. **Enforcement:** `[pr] enforce` from `.swerepo.toml`; when the key or the file is absent, the rules are enforced. With `enforce = false` the findings are `✗` marked "warning only" and don't block, and on GitHub Actions they print as `::warning` annotations.
8. **`.swerepo.toml` gets typed accessors** for `[pr]` (`enforce`, `exempt_authors`, `skip_progress_label`) and `[adopted]` (`adr_dir`, `progress_dir`, `linters`), validated like other keys (ADR-20261120-ecf7).

**Alternatives considered:**
- **Diff `REF...HEAD` (commits only).** Misses uncommitted work when a developer runs `check --base main` before committing.
- **Read the author from the git log.** The last committer isn't the pull request's author (squash merges, bots pushing to a person's branch); the workflow knows the author.
- **Treat a version bump as a new dependency.** Dependabot and routine upgrades would need ADRs.
- **Detect renames.** Rename detection depends on similarity thresholds; delete-plus-add is predictable, and a renamed ADR is still an ADR change.

## Enforced Invariants

None yet; candidates once Phase 4's governance job runs these rules in CI.

## Consequences

- A developer can run `swerepo check --base origin/main` before pushing and see exactly what CI will say.
- The governance job (Phase 4) passes `--base`, `--author` and, when labelled, `--skip progress`.
