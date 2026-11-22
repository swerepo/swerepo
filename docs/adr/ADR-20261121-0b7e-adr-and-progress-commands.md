---
id: ADR-20261121-0b7e
title: swerepo adr new, adr index and progress - SeamSpec's ADR names, a generated index in name order, read-only progress
status: ACCEPTED
date: 2026-11-21
scopes: ["swerepo/adr.py", "swerepo/progress.py", "swerepo/cli.py"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261121-0b7e: swerepo adr new, adr index and progress

## Context

Spec §6.5 and §7 add three small commands so agents never hand-make ADR names or index rows: `swerepo adr new TITLE`, `swerepo adr index`, and `swerepo progress [-n N]`. This repository kept its ADR index by hand until now (docs/adr/README.md said so).

## Decision

1. **`adr new`** creates `ADR-YYYYMMDD-xxxx-<slug>.md` in the ADR folder (`[adopted] adr_dir`, else `docs/adr`), with `xxxx` from `secrets.token_hex(2)` and a slug of at most 60 characters. It fills the folder's own `TEMPLATE.md` (SWERepo's template when there is none) by replacing `ADR-YYYYMMDD-xxxx`, `YYYY-MM-DD` and `One line that states the decision`. It creates the file exclusively and picks another id if one is taken. Then it regenerates the index when the README has index markers, and says so when it doesn't. The frontmatter title is written as YAML reads it back: as it is, or double-quoted when it holds `#`, `: `, quotes, a leading indicator, or reads as a number or a YAML 1.1 boolean. The heading keeps the title as typed.
2. **`adr index`** rewrites only the lines between `<!-- swerepo:adr-index:begin -->` and `<!-- swerepo:adr-index:end -->` with a table `| ID | Title | Status |` (this repository's format), one row per `ADR-*.md` file, **in file-name order** (the date, then the random part): every clone produces the same index, and a merge conflict is fixed by running it again. Title and status come from the frontmatter (the first heading when there is none); a superseded ADR shows `SUPERSEDED by <id>`; `|` in a title is escaped. No markers or broken markers: exit 1, nothing written. Frontmatter values may be quoted; a `#` inside quotes is text, not a comment. Unreadable or non-UTF-8 files are errors naming the repository-relative path, never the absolute one; the README keeps its line endings. ADR files are decoded strictly: a file that isn't UTF-8 stops the index, never writes a garbled title. Double-quoted titles decode YAML's escapes (`\u2014`, `\x..`, `\U...`, `\_`, …); an unknown escape is kept as written. The ADR folder and its README must not be links out of the repository.
3. **`progress`** prints the `## Now` and `## Next` sections of `docs/PROGRESS.md` and the newest N entries (by name) of the progress folder (`[adopted] progress_dir`, else `docs/progress`), default 3. It only reads. `## ` lines inside fenced code blocks aren't sections. A `--path` that isn't a folder is wrong usage (exit 2), for `adr` too. Fences follow CommonMark as `find_block` does: a backtick fence's info string has no backticks, and a closing fence has only spaces or tabs after it.

**Alternatives considered:**
- **Index in writing order.** Not reproducible from the files; two branches would order it differently.
- **Status as written** (`SUPERSEDED` only). The successor is the first thing a reader needs.

## Enforced Invariants

None yet.

## Consequences

- This repository's hand-kept index can be generated: the rows are the same, in name order.
- ADR folders adopted from other conventions (`0001-title.md`) get SeamSpec-style names for new ADRs.
