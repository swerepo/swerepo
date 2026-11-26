"""Standard 1: the components and their files (SWEREPO-SPEC §6, §8).

`check` reads this; `init` uses the same names to know what to create (ADR-20261120-fc5a).
"""

from __future__ import annotations

from swerepo.state import COMPONENTS

STANDARD = 1

# Checked when no `.swerepo.toml` says otherwise: all six (ADR-20261124-152d).
DEFAULT_COMPONENTS = COMPONENTS

# Spec §10's recommended order, one pull request per group; `check` suggests the first group with gaps.
RECOMMENDED_ORDER = (("docs", "agents"), ("ci", "security"), ("seamspec",), ("github",))

ADR_DIR = "docs/adr"
PROGRESS_FILE = "docs/PROGRESS.md"
PROGRESS_DIR = "docs/progress"
RUNBOOKS = (
    "docs/agents/prepare-pr.md",
    "docs/agents/address-review.md",
    "docs/agents/record-adr.md",
    "docs/agents/update-spec.md",
)
CI_WORKFLOW = ".github/workflows/swerepo-ci.yml"
PRIVACY_WORKFLOW = ".github/workflows/swerepo-privacy.yml"
EARNED_SPEC = "docs/EARNED_SPEC.md"
GITHUB_FILES = (
    (".github/swerepo/ruleset.json", "ruleset as code"),
    (".github/swerepo/repo-settings.json", "merge settings as code"),
    (".github/copilot-instructions.md", "Copilot review instructions"),
    (".github/dependabot.yml", "Dependabot"),
)

# Markdown files in an ADR folder that aren't decisions (lower-cased names).
NOT_ADRS = frozenset({"readme.md", "template.md", "index.md"})

# Each editor's own file, written by the agents component when one of its editors is chosen (spec §6.6)
EDITOR_FILES = {"CLAUDE.md": ("claude",), "GEMINI.md": ("antigravity", "gemini")}


def editor_chosen(path: str, hosts: list[str]) -> bool:
    """Whether the editor file at `path` belongs to an editor in `hosts`."""
    return bool(set(EDITOR_FILES[path]) & set(hosts))
