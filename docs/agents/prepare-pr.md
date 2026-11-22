# Prepare a pull request

1. **Branch.** Work on a branch named for the change (`feat/…`, `fix/…`, `docs/…`, `chore/…`), never on the default branch.
2. **Test.** Run `uv run pytest`, `uv run ruff check .` and `uv run ruff format --check .`, even for docs-only changes. Say tests pass only after all of them pass.
3. **Progress entry.** Add `docs/progress/YYYYMMDD-<slug>.md`: what changed, the branch or pull request, the ADRs and locked rules it touches, and what comes next. Never edit earlier entries. Edit `docs/PROGRESS.md` only when Now or Next changes.
4. **ADR, if needed.** A change to the design, the process or the runtime dependencies needs one: see `record-adr.md`.
5. **Locked rules.** If the change approves or supersedes SeamSpec rules, regenerate `docs/EARNED_SPEC.md` in the same pull request: `seamspec spec --out docs/EARNED_SPEC.md`.
6. **Check.** `swerepo check --base <default branch>` reports a missing progress entry or ADR before CI does.
7. **Privacy.** No personal emails, home-folder paths, keys or passwords in the diff.
8. **Open the pull request** with the template: what changed, the decisions it touches, the checklist. Never merge it without the person's go-ahead.
