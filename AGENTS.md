# Working on SWERepo

SWERepo is built in phases from [SWEREPO-SPEC.md](SWEREPO-SPEC.md), the source of truth for behaviour. Each phase ends with a peer review (ADR-20261119-9f87). The working rules for every change are in SWERepo's block at the end of this file, written by `swerepo init` (ADR-20261121-d0f5); these add what is particular to this repository.

## Rules for this repository

1. Never commit to `main` directly (the one exception was the bootstrap commit, ADR-20261119-75e6). Commit, push or merge only with the owner's go-ahead.
2. The decisions that need an ADR are listed in the table in `docs/adr/README.md`. A change to behaviour also updates `SWEREPO-SPEC.md` in the same change.
3. The privacy check before committing also covers `file:///` links.
4. Never publish a package, approve a SeamSpec rule, or create a GitHub repository or organisation unless the owner explicitly asks. Those are the owner's. Never edit a file in `.seamspec/`; request a supersede instead.
5. A phase ends with `CODE_REVIEW.md` (format in ADR-20261119-9f87). Answer every reviewer finding: fix it, push back with reasons, or defer it to a named phase. On a pull request, reply in every Copilot thread with the fix commit or the reason; the owner resolves threads, unless they ask the agent to (ADR-20261120-2e50).

## Commands for this repository

- SeamSpec for the commit hook: `uv tool install seamspec==0.1.2`
- Locked rules: `uv run seamspec verify --all`
- SWERepo itself, from this checkout: `uv run swerepo check` (and `uv run swerepo adr new`, `uv run swerepo progress`)

<!-- seamspec:begin (managed by `seamspec init`; edit outside these markers) -->
# SeamSpec Protocol

This repository uses SeamSpec. Locked invariants are enforced by hooks and git pre-commit (and by
CI where the SeamSpec workflow is installed): failing them blocks you from finishing and blocks commits.

1. Before editing a file, call `get_constraints(files)` (or run `seamspec context <files>`).
   Respect every LOCKED invariant. Approaches listed as previously failed (dead ends) failed for
   the stated reason; don't reuse them unless that reason no longer applies.
2. When the user states an agreement or a rule the code must keep, or you establish a behavior
   worth protecting, capture it right away: call `propose_invariant` with a focused,
   behavior-level test (not implementation details). If its code doesn't exist yet, say so and
   propose it once the code works. The tool does not run the test: run
   `seamspec verify --proposed <id>` with your shell tool and fix the test until it passes.
   If the project keeps a list of rules it intends to lock (for example a section of its
   plan), propose each one when its code exists and works.
3. When an approach fails, or the user tells you about one that failed before, call
   `log_dead_end` with what was tried and why it failed. When you and the user settle a design
   choice that shapes future work on specific files (for example deferring a feature after
   measuring it, choosing an algorithm or a data representation, or setting a module boundary),
   and it is a rationale or trade-off rather than something a test can check or a failed attempt,
   call `propose_decision` scoped to those files, so `get_constraints` shows it in later sessions.
4. If your change must intentionally break a LOCKED invariant, do not edit or delete its test.
   Call `request_supersede(invariant_id, reason, replacement_id)` and tell the user.
5. Never edit files under `.seamspec/` directly; use SeamSpec tools. If they are missing or fail,
   use the matching `seamspec` command in your shell (`seamspec --help`). Never search outside
   this project for SeamSpec's settings; if neither works, stop and tell the user.
6. BRAINDUMP.md holds the user's own notes. Never edit it. When asked to sort it, follow
   `/seamspec-drain`. When SeamSpec reports new notes at the start of a session, ask the user once
   whether to sort them; don't sort without a yes, and don't ask again this session after a no.
7. Only humans approve invariants. When proposals are pending, offer an explanation from
   SeamSpec's reviewer (`/seamspec-explain`), and offer to open `seamspec review` for the user in a
   terminal they type into (never in your own shell; never answer its prompts), or remind them to
   run it.
8. When the user runs a `/seamspec-*` workflow command, follow its steps exactly and end with
   the SeamSpec summary block.
9. Users don't have to type commands. Treat plain requests as the matching workflow command:
   "sort my braindump" → drain; "protect this" / "lock that" / an agreement the user states → lock;
   "that didn't work" / a failure the user describes → dead-end;
   a changed requirement for a LOCKED rule → supersede; "what applies here?" → context;
   "wrap up" → checkpoint.
<!-- seamspec:end -->

<!-- swerepo:begin -->
## Working rules

These rules apply to every agent and every person working on swerepo (the SWERepo standard).

1. Start by reading `docs/PROGRESS.md` and the latest entries in `docs/progress/` (or run `swerepo progress`).
2. Never push to the default branch: one branch and one pull request per piece of work.
3. Add one progress entry in `docs/progress/` (`YYYYMMDD-<slug>.md`) in the same pull request as the work. Only trivial changes skip it, with the commit trailer `Progress: none`.
4. Any change to the design, the process (CI workflows included) or the runtime dependencies gets an ADR in `docs/adr/` (`swerepo adr new "Title"`).
5. Run the full test suite before saying tests pass, even for docs-only changes.
6. Before committing: no personal emails, home-folder paths, keys or passwords in the change.
7. Answer every review thread before asking for a merge: fix it and reply with the commit, or reply why not.
8. Never publish a package, approve a deployment or merge without the person's explicit go-ahead.
9. When a test fails, fix the code; never weaken the test. With SeamSpec, never edit a locked rule's test: request a supersede.

## Commands

- Install: `uv sync`
- Test: `uv run pytest`
- Lint: `uv run ruff check .` and `uv run ruff format --check .`
- Check the standard: `swerepo check`

## Runbooks

Step-by-step guides in `docs/agents/`, read when needed: `prepare-pr.md`, `address-review.md`, `record-adr.md`.
<!-- swerepo:end -->
