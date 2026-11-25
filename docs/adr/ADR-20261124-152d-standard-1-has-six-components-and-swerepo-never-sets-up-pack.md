---
id: ADR-20261124-152d
title: Standard 1 has six components, and SWERepo never sets up package publishing
status: ACCEPTED            # PROPOSED | ACCEPTED | SUPERSEDED | REJECTED
date: 2026-11-24
scopes: ["SWEREPO-SPEC.md", "swerepo/standard.py", "swerepo/state.py", "swerepo/detect.py", "swerepo/check.py", "swerepo/init.py", "swerepo/cli.py", "swerepo/github.py"]
invariants: []              # SeamSpec rule ids that enforce it, if any
supersedes: null
superseded_by: null
---

# ADR-20261124-152d: Standard 1 has six components, and SWERepo never sets up package publishing

## Context

The spec lists eight components (§7, §8): six built in Phases 3 to 7 (`docs`, `agents`, `ci`, `security`, `github`, `seamspec`) and two optional ones planned for Phase 8, `openspec` (§6.7, §14) and `release` (§6.9). The code already carries both as placeholders:
- `state.COMPONENTS` and `standard.OPTIONAL_COMPONENTS`;
- `init.LATER`, which plans them as "init adds it from Phase 8";
- `standard.LATER`, which shows `? release.environment` until Phase 8;
- `detect`'s `openspec` flag;
- `check`'s `openspec.setup` and `release.workflow` items;
- `github.codeowners_lines(openspec=…)`.

ADR-20261124-4d76 replaces OpenSpec with a native `SPEC.md`. For `release`, the owner decided on 2026-11-24 that wiring up publishing to PyPI isn't SWERepo's job. SWERepo helps engineers set up safe, well-governed repositories. Publishing is a decision with its own accounts, credentials and approvals, and a project that publishes sets it up itself. SWERepo's own release workflow is a fact about this repository, not part of the standard (ADR-20261124-4699).

## Decision

1. **Standard 1 (v0.1) ships six components:** `docs`, `agents`, `ci`, `security`, `github` and `seamspec`. All six are complete and universal, with no placeholder for a later phase: no `LATER` entries, and no `?` items naming Phase 8.
2. **`openspec` and `release` are removed** from the code and the spec:
   - **the component lists** in `standard.py` and `state.py`;
   - **detection:** `openspec/` and a release workflow are no longer looked for;
   - **`check`:** no `openspec.setup`, `release.workflow` or `release.environment`, and the `– not chosen` lines for them go;
   - **`init`:** no Phase 8 placeholders: `AVAILABLE`, `LATER` and the `LATER_VERB` plan verb go;
   - **`cli`:** `--only openspec`, `--only release`, `--no-openspec`, `--no-release`, `--openspec` and `--release` all become wrong usage (`--only` itself stays). The module docstring and `init`'s help text stop saying "the others come in later phases" (review P8-D07);
   - **the tests** that assert the placeholders (`openspec` reported as not chosen, `only=["openspec"]`, `LATER_VERB`) change with them;
   - **`github.codeowners_lines`:** no `openspec` parameter;
   - **`[tools] openspec`** goes from the state file;
   - **in the spec:** §6.7 and §14 now describe `SPEC.md`, and §6.9 goes. §7, §8, §9, §15 and §20 lose both components. §15's example shows `docs.spec`, and its rule for checks a later phase adds now says standard 1 has none (P8-D07).
3. **A component name SWERepo doesn't know** is wrong usage, as it already is (exit 2). Nothing released ever wrote `openspec` or `release` into a `.swerepo.toml`, so nothing needs migrating.
4. **SWERepo never sets up publishing.** It writes no workflow, flag or template that publishes to a package registry (`pypa/gh-action-pypi-publish`, `uv publish`, `twine upload`). The agents block's rule that only the person publishes stays. A SeamSpec rule on this repository guards this (ADR-20261124-41e9).
5. **Phase 8's scope changes** from the spec's "`openspec` and `release` components; dogfooding" (ADR-20261119-9f87's table) to:
   - the native `SPEC.md` (ADR-20261124-4d76);
   - removing the two components;
   - SWERepo's own release workflow (ADR-20261124-4699);
   - the two rules of ADR-20261124-41e9;
   - dogfooding on this repository and on one established repository of the owner's;
   - the `0.1.0` release.

**Alternatives considered:**
- **Keep `release` as an optional component.** It would put PyPI accounts, trusted publishers and protected environments into SWERepo's plans. Those are decisions a team makes once, deliberately, about its own package, and SWERepo would be advertising a path it can't check end to end: it makes no PyPI calls, so it never sees the PyPI side.
- **Keep the components as `– not chosen` placeholders for later.** A component that can't be applied is noise in every plan and every `check`. A later standard can add one with its own ADR.

## Enforced Invariants

To be proposed in Phase 8 (ADR-20261124-41e9): the shipped package exposes no `release` component, flag or template that publishes to PyPI.

## Consequences

- Every plan and every `check` shows six components, each one SWERepo can apply.
- Principle 10 (few tools to install) holds without exceptions: nothing in the standard needs Node.
- Spec §6.9's build provenance becomes a property of SWERepo's own releases only; Appendix B is updated to say so.
- A team that wants a release workflow writes its own; a later standard could offer one again with its own ADR.
