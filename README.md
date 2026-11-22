# SWERepo

**Set up a repository the way an AI-assisted team should work, and keep it that way.**

`swerepo init` brings a new or existing Python repository up to an agent-first engineering standard: CI with a single required check, branch rules with code review, decision records and a progress log, instructions for AI agents, and locked rules through SeamSpec. `swerepo check` reports what a repository is missing; `swerepo update` brings it up to the latest standard.

> **Status: pre-alpha, under construction.** `swerepo check` works today (read-only); `init` and `update` are next. The full design is in [SWEREPO-SPEC.md](SWEREPO-SPEC.md); what is built so far is in [docs/PROGRESS.md](docs/PROGRESS.md).

SWERepo is an independent project. It is not part of, or endorsed by, SWE-agent, SWE-bench or Open SWE.

## Develop

Needs [uv](https://docs.astral.sh/uv/) and Python 3.11 or later.

```bash
uv sync
uv run swerepo --version
```

[SeamSpec](https://github.com/seamspec/seamspec) governs this repository. `uv sync` installs it for `uv run seamspec` and CI, but the git pre-commit hook and the Claude Code plugin run the `seamspec` on your PATH, so install the same version as a tool too:

```bash
uv tool install seamspec==0.1.2
```

## Test

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Contributing

Changes go through branches and pull requests, every decision gets an ADR, and every PR adds a progress entry. See [CONTRIBUTING.md](CONTRIBUTING.md).
