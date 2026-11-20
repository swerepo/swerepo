---
id: ADR-20261120-9495
title: Fingerprints hash normalised UTF-8 text with SHA-256; marked blocks are found by comment-style markers
status: ACCEPTED
date: 2026-11-20
scopes: ["swerepo/fingerprint.py", "SWEREPO-SPEC.md"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261120-9495: Fingerprints hash normalised UTF-8 text with SHA-256; marked blocks are found by comment-style markers

## Context

SWERepo decides whether a person edited a file by comparing a fingerprint of the file with the one it recorded when it wrote it (spec §5 principle 2, §9). The spec says hashes are of "normalised content: LF line endings, trailing whitespace removed from each line, exactly one final newline", but not the exact algorithm, how to treat encodings, or how to find a marked block (`<!-- swerepo:begin -->` … `<!-- swerepo:end -->`) inside a file the person also edits. `check` (Phase 2) needs both.

## Decision

1. **Normalisation**, in this order:
   1. decode as UTF-8 with `surrogateescape`, so any bytes, even invalid UTF-8, give a stable result instead of an error;
   2. drop a leading byte-order mark;
   3. turn CRLF and lone CR into LF;
   4. remove trailing whitespace (spaces, tabs, other non-newline whitespace) from each line;
   5. remove trailing empty lines, then end with exactly one `\n` (an empty file stays empty).

   Leading whitespace and blank lines inside the text are kept: YAML and Python indentation is meaning, not formatting.
2. **Fingerprint:** SHA-256 of the normalised text encoded back with UTF-8 and `surrogateescape`, as 64 lower-case hex characters. Stored without a prefix in `.swerepo.toml` (`rendered`, `written`).
3. **Marked blocks.** A block is the lines strictly between a begin line and an end line. Two comment styles, chosen from the file name:
   - **HTML** (Markdown): `<!-- swerepo:begin … -->` and `<!-- swerepo:end … -->`;
   - **hash** (`.gitignore`, `CODEOWNERS`, TOML, YAML, Python, shell, and anything else): `# swerepo:begin …` and `# swerepo:end …`.

   Text after the marker name (for example `# swerepo:begin (governance paths)`) is allowed, but a marker line holds that one comment and nothing else: an HTML marker's note may not contain `-->`, so `<!-- swerepo:begin --> text <!-- x -->` is not a marker. A byte-order mark before the first line is ignored, as in fingerprints. **In Markdown, markers inside fenced code blocks** (three or more backticks or tildes, CommonMark rules) are examples, not markers, so documentation can show what a block looks like (review finding P1-F02). The marker name is a parameter: `swerepo` for SWERepo's own block, `swerepo:adr-index` for the generated ADR index (`swerepo:adr-index:begin`). `swerepo:begin` never matches `swerepo:beginning` or `swerepo:adr-index:begin`.
4. **Errors are explicit.** No block: "not present" (`None`). A begin without an end, an end without a begin, or two blocks with the same marker: an error naming the line, never a guess.
5. **Sections** (TOML tables merged into `pyproject.toml`, spec §6.3) are not fingerprinted in Phase 1. Their design (text or parsed-value hashing) comes with the `ci` component in Phase 4, which is the first to write them.

**Alternatives considered:**
- **Hash raw bytes.** Line-ending conversion (`core.autocrlf`) and end-of-file fixers would report files as edited (spec §9 forbids that).
- **Also normalise indentation or blank lines inside the text.** Would hide real edits in YAML and Python.
- **A different hash (BLAKE2, xxHash).** SHA-256 is in the standard library, well known, and fast enough for repository files.
- **Fail on non-UTF-8 files.** A person converting a file's encoding is an edit, not an error; `surrogateescape` makes it simply a different fingerprint.

## Enforced Invariants

inv_7c5f3156 (proposed in Phase 1): a fingerprint ignores only line endings, trailing whitespace, trailing blank lines and a byte-order mark, and changes for any other edit.

## Consequences

- A file reformatted by Prettier or a Markdown formatter beyond whitespace still counts as edited (spec §9 says so).
- The fingerprint function is the single place this rule lives; `check`, `init` and `update` all call it.
