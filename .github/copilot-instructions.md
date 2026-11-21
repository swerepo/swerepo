# Instructions for GitHub Copilot code review

SWERepo is a model-free Python CLI that sets up and checks repositories against an engineering standard. Behaviour is specified in `SWEREPO-SPEC.md`; decisions are in `docs/adr/`. Every review thread must be resolved before a pull request merges, so comment only where it matters.

## Comment on

- **Wrong behaviour**: code that contradicts `SWEREPO-SPEC.md` or an ADR in `docs/adr/`, or a decision that changes either without an ADR in the same pull request.
- **Data safety**: anything that could overwrite or lose a file a person edited, write during a read-only operation (detection, `check`), or run project code.
- **Tests that don't test**: assertions that can't fail, missing failure cases, a test weakened to pass.
- **Security and privacy**: injection, unsafe subprocess use, secrets, personal email addresses or home-folder paths in tracked files.
- **Edge cases with a concrete failing input**: say the input and the wrong result.

## Don't comment on

- Formatting, import order, line length or naming style: ruff enforces them in CI.
- Files under `.seamspec/`: locked rule tests can't be changed except by superseding the rule.
- Wording in Markdown documents, unless it states something false.
