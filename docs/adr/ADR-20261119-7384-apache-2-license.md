---
id: ADR-20261119-7384
title: SWERepo is licensed under Apache-2.0
status: ACCEPTED
date: 2026-11-19
scopes: ["LICENSE", "pyproject.toml", "SWEREPO-SPEC.md"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261119-7384: SWERepo is licensed under Apache-2.0

## Context

The license was an open question (spec §19.3: MIT or Apache-2.0, with SeamSpec's choice as the natural default). It has to be settled before the repository goes public: a public repository without a license gives nobody the right to use, copy or change the code. The package will be published on PyPI, so the license also goes into the package metadata.

## Decision

1. **Apache License 2.0**, decided by the owner on 2026-11-19.
2. **`LICENSE`** at the repository root holds the unmodified license text from apache.org (identical to SeamSpec's `LICENSE`).
3. **Package metadata** declares it with the SPDX expression: `license = "Apache-2.0"` and `license-files = ["LICENSE"]` in `pyproject.toml`, as SeamSpec does.
4. **No `NOTICE` file** for now. Apache-2.0 doesn't require one; it becomes useful only if the project bundles third-party material that needs attribution.
5. **Spec §19.3 is marked as decided.**

**Alternatives considered:**
- **MIT.** Shorter and just as permissive, but without Apache-2.0's explicit patent grant and patent-retaliation clause, which matter for a tool companies would run across many repositories.
- **A different license from SeamSpec.** No reason to make users of both tools read two licenses.

## Enforced Invariants

None. A rule "LICENSE exists and pyproject declares Apache-2.0" could be proposed, but a license change would be a deliberate owner decision with its own ADR anyway.

## Consequences

- The repository can go public.
- Contributions are accepted under Apache-2.0 (section 5 of the license); no separate contributor agreement.
- Templates SWERepo writes into other repositories (a `LICENSE` there is only written when the person chooses one, spec §6.5) are not affected by this decision.
