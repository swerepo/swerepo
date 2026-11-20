# Working on SWERepo

SWERepo is built in phases from [SWEREPO-SPEC.md](SWEREPO-SPEC.md), the source of truth for behaviour. Each phase ends with a peer review (ADR-20261119-9f87).

## Rules

1. Start by reading `docs/PROGRESS.md` and the latest entries in `docs/progress/`.
2. Never commit to `main` directly (the one exception was the bootstrap commit, ADR-20261119-75e6); one branch per phase or piece of work. Commit, push or merge only with the owner's go-ahead.
3. Add one progress entry in `docs/progress/` in the same change as the work.
4. Every decision in the table in `docs/adr/README.md` gets an ADR in the same change: design, process, CI, new dependencies, anything that changes or adds to the spec. A spec change updates `SWEREPO-SPEC.md` in the same change.
5. Run the full test suite and both ruff checks before saying tests pass, even for docs-only changes.
6. Before committing: no personal emails, home-folder paths, `file:///` links, keys or passwords in the change.
7. When a test fails, fix the code; never weaken the test. Never edit a file in `.seamspec/`; request a supersede instead.
8. Never publish a package, approve a SeamSpec rule, or create a GitHub repository or organisation unless the owner explicitly asks. Those are the owner's.
9. A phase ends with `CODE_REVIEW.md` (format in ADR-20261119-9f87). Answer every reviewer finding: fix it, push back with reasons, or defer it to a named phase.

## Commands

- Install: `uv sync` (and `uv tool install seamspec==0.1.1` for the commit hook)
- Test: `uv run pytest`
- Lint: `uv run ruff check .` and `uv run ruff format --check .`
- Locked rules: `uv run seamspec verify --all`
