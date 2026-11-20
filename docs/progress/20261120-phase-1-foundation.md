# 2026-11-20 · Phase 1: foundation

**Branch:** `phase-1/foundation` · **Review:** [docs/reviews/phase-1.md](../reviews/phase-1.md) (closed after 3 rounds)

## Done

- `swerepo/fingerprint.py`: normalised SHA-256 fingerprints and marked-block parsing (ADR-20261120-9495).
- `swerepo/render.py`: the template store (`templates/<component>/<name>/<version>[.<ext>]`) and `@@name@@` rendering (ADR-20261120-b25a); `swerepo/templates/README.md`.
- `swerepo/state.py`: `.swerepo.toml` with tomlkit, validated on load, atomic saves, never overwritten by an older SWERepo (ADR-20261120-ecf7).
- `swerepo/detect.py`: read-only detection of git, languages, Python versions, projects and monorepos, CI, documents, ADR folders, agent files and editors, linters, pytest, SeamSpec and OpenSpec (ADR-20261120-25b5). On this repository: not a monorepo, `tools/pypi-placeholder` skipped (the Phase 0 review note).
- New runtime dependencies `tomlkit` and `packaging`; spec v0.7.
- 123 tests at first (116 new), 155 after the review; fixture repositories built per test; four SeamSpec rules proposed: inv_7c5f3156 (fingerprints), inv_bee7349a (detection is read-only), inv_d8603926 (state file keeps comments and unknown keys), inv_070db19c (a newer state file loads but is never overwritten). Strengthened twice after SeamSpec's reviewer explained the drafts; the state rule was split in two. All four approved and locked by the owner on 2026-11-20; `docs/EARNED_SPEC.md` lists 6 rules.
- Phase 0 marked done in `docs/PROGRESS.md`.
- PR #2's first CI run failed the workflow audit: a re-run of `seamspec init` without `--no-ci` had added `.github/workflows/seamspec.yml` (unpinned actions), and it went into the Phase 1 commit unnoticed. Removed; it duplicated the SeamSpec job in `ci.yml`. ADR-20261119-6b94 now says every `seamspec init` needs `--no-ci`.
- Review (Gemini), 3 rounds, closed 2026-11-20: 10 findings, all reproduced and fixed, one refined; 155 tests. Round 1: project roots for other languages and manifest-less Python projects, Markdown fences / BOM / one-comment marker lines, newer state files load, stricter paths, patch-level Python pins, `copilot-instructions.md` no longer means VS Code, more linter sections, `TERM`-proof CLI test, `fullmatch`. Round 2: package and `src/` layouts, inline-code backticks aren't fences, the version is always validated.

## Next

- Pull request for `phase-1/foundation`.
- Phase 2: `swerepo check`.
