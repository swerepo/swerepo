# 2026-11-23 · SWERepo sets up its own CI and security

**Branch:** `chore/dogfood-ci-security` · **ADR:** ADR-20261123-d27b

## Done

- `uv run swerepo init --only ci,security --yes` on this repository:
  - `.github/workflows/swerepo-ci.yml`, whose governance job runs this checkout's `swerepo check --ci --base`, so the pull-request rules now fail CI here;
  - `.github/workflows/swerepo-privacy.yml`;
  - `SECURITY.md`, pointing to private vulnerability reporting, which is on;
  - SWERepo's block in `.gitignore`;
  - `.swerepo.toml`, recording `docs`, `agents`, `ci` and `security`.

  The project's own ruff and pytest settings were kept.
- The hand-written `.github/workflows/ci.yml` is removed, as ADR-20261119-dd1a (now superseded) planned. The generated workflow keeps all its jobs and adds `dependency-review` and `governance`.

## Next

- Watch the new jobs on this pull request (governance, dependency review, the privacy workflow); the ruleset still requires only `ci-ok`.
- Phase 5: `github` (ruleset and merge settings as code, CODEOWNERS, Copilot instructions, PR template) and `swerepo threads`.
- Noted while dogfooding: in `.swerepo.toml`, a record added to an existing `[blocks]` table has no blank line before the next table (valid TOML; cosmetic, `state.py`); and `adr new` turned "repository's" into `repository-s` in the file name, which joins the earlier note about cutting slugs at a word boundary.
