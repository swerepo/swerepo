---
id: ADR-20261123-24e0
title: Secrets are caught locally by a pre-push privacy hook
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-23
scopes: ["swerepo/hook.py", "swerepo/privacy.py", "swerepo/check.py", "swerepo/cli.py"]
invariants: [inv_960b67a8]  # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261123-24e0: Secrets are caught locally by a pre-push privacy hook

## Context

The privacy scan (spec §6.4, ADR-20261122-a48e) finds personal email addresses, home-folder paths and about ten kinds of key and token. It runs in `swerepo check` and in the `swerepo-privacy.yml` workflow on every push and pull request. By the time the workflow fails, the commit is already on GitHub. A leaked key must then be rotated, because git history keeps it.

GitHub's secret scanning and push protection close most of that gap for keys. They are the repository owner's settings, and `check` warns while they are off. They know nothing of personal email addresses or home-folder paths, though, and they work only once the push reaches GitHub.

Spec §19 question 5 asked whether to add a local scanner. Its proposal was "GitHub's plus the privacy check; a local scanner with the pre-commit option later". The owner decided on 2026-11-23 to add the local step now, before Phase 6, using SWERepo's own scan. The other options it weighed:
- a large list of SWERepo's own token patterns, which GitHub and gitleaks already maintain;
- guessing passwords from their shape, which gives too many false alarms.

## Decision

1. **A pre-push hook, not pre-commit** (owner's choice, 2026-11-23). SeamSpec installs `.git/hooks/pre-commit`, and that file ends with `exec seamspec verify`, so a step added after it would never run. Putting SWERepo's step first would edit a file SeamSpec rewrites. A pre-push hook is a file of SWERepo's own. It checks every commit about to leave the machine, so a leak never reaches GitHub. Fixing a hit means amending or rewriting a local commit, which publishes nothing.
2. **`swerepo hook install`** writes the hook into the folder git uses for hooks (`git rev-parse --git-path hooks`, so `core.hooksPath` and worktrees are respected). It handles an existing hook this way:
   - A hook SWERepo wrote is rewritten when its text changed, and made executable again when it isn't: git skips a hook it can't run without a word, and `check` reports it (review H55-F01).
   - Any other pre-push hook, a link included, is left as it is. The command then prints the line to add to it and exits 1.
   - Hooks aren't tracked by git, so each clone installs its own. Nothing is recorded in `.swerepo.toml`.
3. **The hook runs `swerepo privacy --pre-push`** through the command the privacy workflow already uses: the recorded `privacy_command`, or `swerepo`. It reads the refs git passes on standard input and scans the lines each pushed commit adds:
   - **New commits only:** those not on the remote yet (`<remote sha>..<local sha>`). For a branch new to that remote, the commits its remote-tracking branches don't have: the hook passes the remote's name, so a branch already on `origin` is still scanned when first pushed to `public` (review H55-F03). A push to a URL is measured against every remote.
   - **Merges too:** the lines a merge adds that no parent had, such as a conflict resolved by hand, through git's combined diff (`--cc`, review H55-F02). Lines taken from one parent are scanned with that parent's commits.
   - **Strict input:** a line from git that isn't `<ref> <sha> <ref> <sha>` refuses the push rather than being skipped (review H55-F05).
   - **Same rules as CI:** `privacy.line_kinds`, with the project's declared emails, `[privacy] allow_paths` and the `swerepo: allow-privacy` marker.
   - **What it reports:** the kind, the commit and `file:line`, never the matched text, as everywhere else (inv_5e3b5ef3, inv_ab57c6ff).
   - **Every file name:** names with spaces, quotes, backslashes, tabs or non-ASCII letters are read as git writes them, without its trailing tab and with its C-quoting undone (review H55-F06).
   - **Read as CI reads it** (Copilot's review of PR #15):
     - a `-diff` or `binary` attribute doesn't hide a text file (`--text`), while a file with a NUL byte, or larger than the CI scan reads, is still skipped;
     - a lone carriage return splits a line, numbered as CI numbers it, so a `swerepo: allow-privacy` marker covers only its own line;
     - diff prefixes are fixed, whatever the person's settings.
   - **Installed where git looks:** the hooks folder is kept as git gives it, a name ending in a space included. The hook is compared as bytes, so a copy turned to CRLF, which `/bin/sh` can't run, is rewritten.
   - **Not scanned:** deleted refs, deleted lines and binary files.
   - **Found where uv lives:** the hook adds `~/.local/bin`, `/opt/homebrew/bin` and `/usr/local/bin` to `PATH`, since GUI git clients often start hooks without them (review H55-F05).
4. **It fails closed.** When SWERepo can't run, the push is refused with the reason. `git push --no-verify` skips the hook on purpose, as git allows for every hook. CI's privacy workflow remains the guard on GitHub.
5. **`check` reports a missing hook locally:** "pre-push privacy hook not installed (swerepo hook install)", as a warning, never blocking. It doesn't report it with `--ci`, where no hook can exist. Reading the hooks folder writes nothing.
6. **This repository installs it** (one clone at a time: the owner's).

**Alternatives considered:**
- **Pre-commit, as a block placed first in SeamSpec's hook.** It catches a leak earliest, but `seamspec init` rewrites that file and would drop the block without anyone noticing.
- **The pre-commit framework or prek, with gitleaks.** Another tool for every contributor to install, and a separate binary (spec §19.5). gitleaks may still come later as an option, for history and its long list of formats.
- **Scanning the whole tree on push.** That repeats CI. A hit already in `main` would block every push until someone fixed it, even pushes that don't touch it.

## Enforced Invariants

`inv_960b67a8` (critical, approved by the owner 2026-11-23) locks that a real push adding a key, a GitHub token, an email address or a home-folder path is refused, naming where and never what on either stream, and that a pre-push hook of the person's own, a link included, is never replaced.

## Consequences

- A key, personal email address or home-folder path in a new commit stops the push on a machine with the hook, before GitHub sees it.
- Everyone pushing should run `swerepo hook install` once per clone; `check` reminds them.
- Spec §19 question 5 is answered: GitHub's secret scanning and push protection, plus SWERepo's scan in CI and in the pre-push hook. gitleaks stays an option for later.
