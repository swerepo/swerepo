# Templates

Files SWERepo renders into repositories (ADR-20261120-b25a).

- **Location and name:** one folder per template, one file per version: `<component>/<name>/<version>[.<ext>]`, for example `docs/adr-template/1.md`. The template id is `<component>/<name>@<version>` (`docs/adr-template@1`). File names never contain `@`: a name, `@`, a version and an extension reads as an email address to the privacy rule.
- **Placeholders:** `@@name@@` (lower-case letters, digits, `_`). Every placeholder needs a text value; there are no conditionals or loops.
- **Released versions never change.** To change a template, add the next version and keep the old file: `swerepo update` rebuilds earlier renders from it for three-way merges.
- **UTF-8, LF line endings.**
- **Multi-line values** (for example a YAML job): put the placeholder at column 0, so lines after the first keep their own indentation.
- **Structured files** (JSON such as `ruleset.json`): build them in Python, or use separate templates per variant; don't place non-text values through `@@name@@`.

This folder holds no templates yet: components add them from Phase 3 on. Files that aren't named by a version number, like this one, are not templates.
