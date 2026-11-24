# 2026-11-23 · SWERepo sets up its own GitHub settings

**Branch:** `chore/dogfood-github` · **ADR:** ADR-20261123-e2f8

## Done

- `uv run swerepo init --only github --mode solo --code-owner @<owner> --yes` on this repository, with the owner's choices (solo, the owner's login, squash only, Copilot's review awaited). It wrote:
  - `.github/swerepo/repo-settings.json`, `.github/dependabot.yml`, the PR template and two issue templates;
  - SWERepo's review block in `.github/copilot-instructions.md`;
  - `swerepo-ci.yml` at `ci/workflow@2`, so `ci-ok` now waits for Copilot's review;
  - `.swerepo.toml`, recording `github`.
- **Kept:** the hand-made `ruleset.json`, already solo with Copilot review and current on GitHub, and the hand-made CODEOWNERS block, which already names the owner.
- **Merge settings applied on GitHub:**
  - squash only;
  - head branches deleted after merge;
  - the squash commit takes the PR's title and body.

  `swerepo check` confirms that the ruleset and the merge settings on GitHub match the committed files.
- **Fixed while dogfooding:** the plan asked to edit `ruleset.json` and CODEOWNERS although both already held the choices given. It now names only what a kept file lacks (`TestDogfoodGithub`).

## Next

- This pull request is the first to wait for Copilot's review inside `ci-ok`. If the review comes after 20 minutes, re-run `copilot-review`.
- **Owner, on GitHub:** secret scanning and push protection are still off (`check` warns).
- Phase 6: `update`, three-way merge, `diff`, `status`; and explaining or asking about `delete_branch_on_merge` for teams that keep merged branches. The owner keeps it on here.
