# 2026-11-26 · `check` reports the CI tools `uv sync` won't install, and code owners GitHub doesn't know

**Branch:** `phase-8/check-gaps`

## Done

- **Two gaps, from dogfooding on an established repository:**
  - `check` never repeated `init`'s note that the tools CI runs aren't installed, so the person found out from a red CI;
  - the code-owner question's example, `@login`, was recorded and written into CODEOWNERS, and nothing checked it on GitHub.
- **Designed first, reviewed by Gemini** (`P8-K01` to `P8-K07`, two rounds, all accepted, in `CODE_REVIEW.md`); agreed by the owner (ADR-20261126-a7ce). Read-only GETs on GitHub settled the lookups: an unknown login answers 404 "`<login>` is not a user", the permission read answers 403 without push access, and a team answers 404 to a non-member.
- **`ci.tools` and `agents.tools`:** warnings, never failing `--ci`, in `init`'s words from one function in `swerepo/ci.py`, with a runnable fix. Read from the workflow's recorded inputs while it is as SWERepo wrote it (newer action pins aside). `commands()` moved to `swerepo/commands.py`. A warning never hides a blocking finding on the same file.
- **Code owners:** `check` reads SWERepo's CODEOWNERS block offline (also under `--ci`) and, with `gh`, looks each owner up (`GitHub.owner_verdict`, GET only). `init` refuses the question's examples and an owner GitHub says can't be one, and notes the rest. A recorded example is asked about again in a terminal and never written. `GitHubError` carries the HTTP status (P8-K07).
- **Gemini's code review** (`P8-K08` to `P8-K11`), each fix reproduced first and broken on purpose (eight breakages, all caught): recorded project folders must be ones SWERepo writes and inside the repository; `agents.tools` reads the verified block and only fixed-set tools; a recorded example with CODEOWNERS missing points at `--code-owner …`; escaped spaces in CODEOWNERS patterns.
- **Spec v0.19** (§6.1, §6.2, §6.6, §7, §12, §15, Appendix A).
- **Tests:** `tests/test_check_gaps.py` (81), plus `tests/fake_gh.py` answering failures as `gh` prints them. 41 breakages of the build and 8 of the review's fixes, all caught.

## Next

- Gemini's code review, then the pull request.
- On the established repository: `swerepo init --only github --code-owner @<real>` replaces the recorded `@login`.
- Phase 11: `uv.lock`'s resolved graph for installed tools; `codeowners/errors` as a second signal.
