# 2026-11-21 · Copilot's review of PR #3 (Phase 2)

**Branch:** `phase-2/copilot-fixes` · **Review:** [docs/reviews/phase-2.md](../reviews/phase-2.md), "After merge"

## Done

- PR #3 (Phase 2) was merged before Copilot's review arrived; its 8 findings (1 high, 7 medium) are answered here. All 8 were reproduced on `main` first.
- The text report and wrong-usage messages show CR and LF from file values as `\r` and `\n`: a value such as a newer state file's `mode` could otherwise start a GitHub Actions workflow command.
- `components = []` and `[agents] hosts = []` in `.swerepo.toml` choose nothing; only a missing key falls back to the defaults (`State.components_chosen`, `State.hosts_chosen`).
- A `tool` value in `pyproject.toml` that isn't a table no longer crashes `check`.
- "CI runs the locked rules" reads only workflow `run:` commands (one-line and block); step names, `env` values and comments don't count.
- `.swerepo.toml` errors don't repeat rejected paths; dependency findings name an invalid entry by position, and dependencies that aren't a list are `?`.
- ADR-20261120-fc5a items 2, 3, 6, 7 and ADR-20261120-5e21 item 3 amended; CHANGELOG "Fixed".
- 15 regression tests, each shown to fail with its fix undone.
- Copilot's review of PR #4 (3 findings, all reproduced): the run-step reader follows `steps:` lists and the step's own key column, and recognises `seamspec verify` only as a command (shlex, with `uv run`/`uvx`/`python -m`), not as an argument or an `env` value. 10 more cases.

## Next

- Owner: resolve the 8 Copilot threads on PR #3 after the replies.
- Phase 3: `swerepo init` for `docs` and `agents`.
