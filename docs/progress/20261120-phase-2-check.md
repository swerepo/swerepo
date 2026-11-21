# 2026-11-20 · Phase 2: swerepo check

**Branch:** `phase-2/check` · **Review:** [docs/reviews/phase-2.md](../reviews/phase-2.md) (closed, 3 rounds)

## Done

- `swerepo check`: read-only findings per component (`✓ ✗ ~ ↑ ? –`), as plain text or `--json`; `--only`, `--path`, `--ci` (GitHub Actions annotations); exit 0, 1 (something chosen missing) or 2 (wrong usage). `swerepo/check.py`, ADR-20261120-fc5a.
- `swerepo/standard.py`: standard 1's components, files and recommended order, and the checks later phases add (reported as `?` naming the phase).
- Pull-request rules with `--base REF`, `--author`, `--skip progress`: progress entry or `Progress: none`, ADR for new dependencies (PEP 503 names) and workflow changes (SWERepo's own changes excepted), bot and lockfile-only skips, warn-only mode. `swerepo/prrules.py`, ADR-20261120-5e21.
- `.swerepo.toml` accessors and validation for `[agents]`, `[adopted]` and `[pr]`.
- No absolute paths or email addresses in the output.
- Read-only includes git's index: drafting the earned rule's test showed `git diff` rewrote an out-of-date `.git/index`, even with `--no-optional-locks` (logged as dead end `de_a22b43fe`); the pull-request diff now runs on a temporary copy of the index (ADR-20261120-fc5a, item 10). Proposed rule `inv_294c48c9` (critical): check never writes to the folder it checks.
- Spec v0.8: `--author` flag, `[adopted] progress_dir`, what this version checks.
- Gemini's review round 1 (8 findings): all fixed, two in part (a kept linter without configuration is `?`, not `✗`; for split-index repositories, a documented git limit instead of a flag that didn't help). Second proposed rule `inv_5e3b5ef3` (critical): no absolute paths or personal emails in `check` output.
- Round 2 (3 findings, all fixed): binary files untracked with `git rm --cached` compared as bytes, CODEOWNERS never names an `@` token, `--only ""` is wrong usage.
- SeamSpec's Antigravity setup (`.agents/`, the second SeamSpec block in `AGENTS.md`), committed unnoticed in Phase 1, is kept: the owner's decision, ADR-20261121-8259 (amends ADR-20261119-6b94; `seamspec init` re-runs use `--hosts antigravity`).
- Earned rules locked by the owner (2026-11-21): `inv_294c48c9` (check writes nothing, not even git's index) and `inv_5e3b5ef3` (no paths or personal emails in output). 8 rules in force; `docs/EARNED_SPEC.md` regenerated.
- 262 tests (101 new); fixture repositories with real git histories; `tests/repo_helpers.py`.
- Dogfooding: on this repository `check` finds `docs` complete and reports what `init` will add (agent block and runbooks, `swerepo-ci.yml`, security and GitHub files); `--base main` flags a missing progress entry before this one was written.

## Next

- Pull request for Phase 2 and Copilot's review.
- Phase 3: `swerepo init` for `docs` and `agents`.
