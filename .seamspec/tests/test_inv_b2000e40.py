"""Locked rule: CHANGELOG.md keeps an `[Unreleased]` section (Keep a Changelog; SWEREPO-SPEC §6.5)."""

import re
from pathlib import Path

# The repository root is the folder that holds .seamspec/config.toml, wherever SeamSpec keeps this file
# (.seamspec/proposed/<id>/ while proposed, .seamspec/tests/ once locked, or a copy of the staged tree).
ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".seamspec" / "config.toml").is_file())

# "## [Unreleased]", optionally with an inline comparison link: "## [Unreleased](https://…)".
HEADING = re.compile(r"^## \[Unreleased\](?:\([^)\n]+\))?[ \t]*$", flags=re.MULTILINE)


def test_changelog_has_an_unreleased_section():
    changelog = ROOT / "CHANGELOG.md"
    assert changelog.is_file(), "CHANGELOG.md is missing"
    assert HEADING.search(changelog.read_text(encoding="utf-8")), "no '## [Unreleased]' heading"


def test_heading_forms():
    assert HEADING.search("# Changelog\n\n## [Unreleased]\n\n### Added\n")
    assert HEADING.search("## [Unreleased](https://github.com/o/r/compare/v0.1.0...HEAD)\n")
    assert not HEADING.search("## [Unreleased] - 2026-01-01\n")
    assert not HEADING.search("### [Unreleased]\n")
    assert not HEADING.search("## Unreleased\n")
