"""Standard 1: the components, their files, and which checks later phases add (SWEREPO-SPEC §6, §8).

`check` reads this; `init` uses the same names to know what to create (ADR-20261120-fc5a).
"""

from __future__ import annotations

from swerepo.state import COMPONENTS

STANDARD = 1

# Checked when no `.swerepo.toml` says otherwise; `openspec` and `release` are optional (spec §6.7, §6.9).
DEFAULT_COMPONENTS = ("docs", "agents", "ci", "security", "github", "seamspec")
OPTIONAL_COMPONENTS = ("openspec", "release")
assert set(DEFAULT_COMPONENTS + OPTIONAL_COMPONENTS) == set(COMPONENTS)

# Spec §10's recommended order, one pull request per group; `check` suggests the first group with gaps.
RECOMMENDED_ORDER = (("docs", "agents"), ("ci", "security"), ("seamspec",), ("github",))

ADR_DIR = "docs/adr"
PROGRESS_FILE = "docs/PROGRESS.md"
PROGRESS_DIR = "docs/progress"
RUNBOOKS = ("docs/agents/prepare-pr.md", "docs/agents/address-review.md", "docs/agents/record-adr.md")
CI_WORKFLOW = ".github/workflows/swerepo-ci.yml"
PRIVACY_WORKFLOW = ".github/workflows/swerepo-privacy.yml"
RELEASE_WORKFLOW = ".github/workflows/release.yml"
EARNED_SPEC = "docs/EARNED_SPEC.md"
GITHUB_FILES = (
    (".github/swerepo/ruleset.json", "ruleset as code"),
    (".github/swerepo/repo-settings.json", "merge settings as code"),
    (".github/copilot-instructions.md", "Copilot review instructions"),
    (".github/dependabot.yml", "Dependabot"),
)

# Checks a later phase adds: shown as "?" until then, never silently left out (ADR-20261120-fc5a point 4).
LATER = {
    "release": (("release.environment", "protected release environment", 8),),
}

# Markdown files in an ADR folder that aren't decisions (lower-cased names).
NOT_ADRS = frozenset({"readme.md", "template.md", "index.md"})
