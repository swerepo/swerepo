# 2026-11-23 · Secrets are caught before a push

**Branch:** `feat/privacy-hook` · **ADR:** ADR-20261123-24e0

## Done

- **Owner decisions** (2026-11-23):
  - catch leaks locally, before Phase 6;
  - in a pre-push hook, since SeamSpec owns the pre-commit hook;
  - not by maintaining a long list of SWERepo's own token patterns, or by guessing passwords.
- **`swerepo hook install`** (`swerepo/hook.py`) writes a git `pre-push` hook into the folder git uses (`core.hooksPath` and worktrees respected):
  - it never replaces a pre-push hook of the person's own, and prints the line to add instead;
  - it runs SWERepo through the recorded `privacy_command` when it's one SWERepo writes, else `swerepo`.
- **`swerepo privacy --pre-push`** scans the lines each commit about to be pushed adds:
  - only commits the remote doesn't have yet;
  - the same rules and allowances as CI;
  - it names the kind, the commit and `file:line`, never what it found, and refuses the push.

  `swerepo privacy` on its own runs the full scan.
- **`swerepo check` reminds locally** when the hook is missing (a warning; never with `--ci`).
- **Review (H55), five findings, all fixed with regression tests (`TestReviewH55`):**
  - a hook git can't run is reported and made executable again, and a link counts as someone else's hook (F01);
  - merges are scanned with `--cc`, so a secret typed while resolving a conflict is found (F02);
  - the hook passes the remote's name, so a branch already on `origin` is scanned when first pushed to another remote (F03);
  - `inv_960b67a8` is proposed as critical (F04);
  - Homebrew's folders are on the hook's `PATH`, and git's input is read strictly (F05).
- **Review round 2 (H55-F06):** files whose names hold a space, a quote, a backslash or a tab were skipped or kept a trailing tab; they are read as git writes them now. Noted: `[privacy] allow_paths` reads a backslash as a folder separator, so such a name is allowed only through `?` or `*` (as before, in CI too).
- **Copilot's review of PR #15:** five findings (`TestCopilotReviewPR15`):
  - fixed: a hooks folder ending in a space, a hook turned to CRLF, files marked `-diff`, and lone carriage returns;
  - didn't reproduce: `diff.noprefix` (`git diff-tree` ignores it), but the prefixes are now fixed explicitly and a test covers it.
- **SeamSpec:** the owner approved `inv_960b67a8` (critical), so 16 rules are locked; `docs/EARNED_SPEC.md` regenerated.
- **Tests:** `tests/test_hook.py`, including a real `git push` to a local bare repository that the hook refuses, with nothing reaching the remote. Spec v0.12 answers open question 5.

## Next

- Install the hook in each clone: `swerepo hook install`.
- **Owner, on GitHub:** secret scanning and push protection are now on; Dependabot security updates are still off (Settings → Advanced Security).
- Phase 6: `update`, three-way merge, `diff`, `status`.
