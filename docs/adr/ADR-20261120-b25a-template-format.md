---
id: ADR-20261120-b25a
title: Templates are plain files with @@name@@ placeholders, versioned by file name and never changed once released
status: ACCEPTED
date: 2026-11-20
scopes: ["swerepo/templates/", "swerepo/render.py", "SWEREPO-SPEC.md"]
invariants: []
supersedes: null
superseded_by: null
---

# ADR-20261120-b25a: Templates are plain files with @@name@@ placeholders, versioned by file name and never changed once released

## Context

Generated files are "rendered from templates bundled in the package, with a few values filled in", and "every released template version stays in the package" so an earlier render can be rebuilt for a three-way merge (spec §8, §16). Templates are data, never code (§17). The templates will be Markdown, YAML (GitHub workflows, which use `${{ … }}` expressions), TOML (which uses `[[…]]` tables), JSON and plain text, so the placeholder syntax must not collide with any of them.

## Decision

1. **Placeholder syntax: `@@name@@`**, where `name` is lower-case letters, digits and `_`, starting with a letter. It doesn't occur in GitHub expressions (`${{ }}`), TOML tables (`[[ ]]`), Markdown links, Jinja-like text (`{{ }}`) or shell (`$VAR`).
2. **Rendering is substitution only.** No conditionals, loops, filters or code. Each placeholder must have a value, and every value must be a string: the caller formats lists (for example the Python version matrix). A missing value is an error naming the placeholder; extra values are ignored, so one set of values serves many templates. Text that merely contains `@@` without forming a placeholder is left alone.
3. **Where and how templates are named:** one folder per template, one file per version: `swerepo/templates/<component>/<name>/<version>[.<ext>]`, for example `swerepo/templates/docs/adr-template/1.md`. The template id is `<component>/<name>@<version>` (`docs/adr-template@1`), as recorded in `.swerepo.toml` (spec §9). The extension is optional (`github/codeowners/1`) and only helps editors. Files not named by a version number (such as `README.md`) are not templates. **No `@` in file names:** a first design put the version after an `@` in the file name, followed by the extension, and the locked privacy rule (inv_62d51113) read every such name as an email address, with the version and extension as its domain (`.md` is a real top-level domain), so the commit hook would have blocked them. Folders per template also keep a template's versions together.
4. **Released versions never change.** A template that needs to change gets a new version (`@2`); the old file stays, so `update` can rebuild what an earlier SWERepo wrote. Once the first release exists (Phase 8), a SeamSpec rule will lock the released files by hash.
5. **Templates are read with `importlib.resources`**, so they work from a wheel, a zip or a source checkout. The template store takes its root as a parameter, so tests can use their own templates.
6. **Templates are stored with LF line endings and UTF-8**, and rendered output is written as rendered (spec §9's normalisation applies to fingerprints, not to what is written).

**Alternatives considered:**
- **Jinja2.** A runtime dependency, and a template language (conditionals, filters) that turns data into logic and makes three-way merges of rendered output harder to reason about. Also collides with `${{ }}` in workflows unless escaped.
- **`string.Template` (`$name`).** Collides with `${{ }}` in GitHub workflows and with shell in YAML `run:` steps; every `$` would need escaping.
- **One file per component with sections.** Harder to version one file at a time.
- **`<name>@<version>.<ext>` file names.** Tripped the locked privacy rule (see point 3); weakening that rule to allow `.md` domains would let real addresses through.
- **Conditionals for optional parts** (for example a workflow job only some projects get). Deferred: when a component needs one, it uses separate template files or composes rendered pieces in code, decided with that component's ADR.

## Enforced Invariants

None yet: "rendering fails on a missing value" was considered for Phase 1 and left as a question for the review. Phase 8: released templates never change.

## Consequences

- Template authors can open a template in any editor and see almost exactly the output.
- Some logic that a template language would hold moves into Python code, where it is tested.
