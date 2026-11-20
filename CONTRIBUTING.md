# Contributing

SWERepo follows the process it installs in other repositories (SWEREPO-SPEC.md §6).

## How a change lands

1. **Branch.** Never commit to `main`. Name branches `feat/…`, `fix/…`, `docs/…`, `chore/…`, or `phase-<n>/…` for a build phase.
2. **Decide, then record.** Any decision listed in [docs/adr/README.md](docs/adr/README.md) gets an ADR in the same change. If it changes behaviour, update [SWEREPO-SPEC.md](SWEREPO-SPEC.md) too.
3. **Log progress.** Add one file in `docs/progress/` (`YYYYMMDD-<slug>.md`): what was done, ADRs touched, what's next. Edit `docs/PROGRESS.md` only when Now or Next changes. One file per change means parallel branches never conflict.
4. **Test.** `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run seamspec verify --all`.
5. **Review.** Each build phase ends with a peer review in `CODE_REVIEW.md` (ADR-20261119-9f87). Every finding gets an answer: fixed, pushed back with reasons, or deferred to a named phase. Closed reviews move to `docs/reviews/`.
6. **Merge.** The owner merges. Once the repository is on GitHub, through pull requests with `ci-ok` required.

## Locked rules

SeamSpec governs this repository (ADR-20261119-6b94). Locked rules run when an agent stops, at commit and in CI. Never edit a file in `.seamspec/`; if a rule is wrong, propose a supersede. Only the owner approves rules (`seamspec review`).

## Privacy

No personal email addresses, home-folder paths, `file:///` links, tokens or secrets in any tracked file. Commit under a noreply address.
