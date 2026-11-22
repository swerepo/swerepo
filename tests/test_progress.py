"""`swerepo progress` (spec §6.5)."""

from pathlib import Path

from repo_helpers import make
from typer.testing import CliRunner

from swerepo.cli import app
from swerepo.progress import report, sections
from swerepo.state import State

PROGRESS = (
    "# Progress\n\nIntro.\n\n## Now\n\n- Phase 3\n\n## Later\n\n- skip me\n\n## Next\n\n- Phase 4\n### Detail\n- kept\n"
)


def test_sections_keep_sub_headings_and_skip_others():
    assert sections(PROGRESS) == [("Now", "- Phase 3"), ("Next", "- Phase 4\n### Detail\n- kept")]


def test_report_shows_now_next_and_the_newest_entries_first(tmp_path: Path):
    make(tmp_path, {
        "docs/PROGRESS.md": PROGRESS,
        "docs/progress/20260101-a.md": "# A\n",
        "docs/progress/20260301-c.md": "# C\n",
        "docs/progress/20260201-b.md": "# B\n",
    })  # fmt: skip
    text = report(tmp_path, count=2)
    assert (
        text.index("## Now") < text.index("## Next") < text.index("### 20260301-c.md") < text.index("### 20260201-b.md")
    )
    assert "20260101-a.md" not in text and "skip me" not in text


def test_missing_files_are_said_plainly(tmp_path: Path):
    text = report(tmp_path)
    assert "docs/PROGRESS.md is missing" in text and "no entries in docs/progress/" in text


def test_command_line_follows_an_adopted_progress_folder(tmp_path: Path):
    make(tmp_path, {"docs/PROGRESS.md": PROGRESS, "docs/changes/20260101-x.md": "# X\n"})
    state = State.new(version="0.0.1")
    state.set_adopted("progress_dir", "docs/changes")
    state.save(tmp_path, running="0.0.1")
    result = CliRunner().invoke(app, ["progress", "--path", str(tmp_path), "-n", "1"])
    assert result.exit_code == 0 and "### 20260101-x.md" in result.output and "docs/changes/" in result.output


def test_p3_f06_headings_in_code_blocks_and_lone_cr():
    text = "## Now\r- a\n```md\n## Not a section\n```\n~~~\n## Nor this\n~~~\n- b\n## Next\n- c"
    assert sections(text) == [("Now", "- a\n```md\n## Not a section\n```\n~~~\n## Nor this\n~~~\n- b"), ("Next", "- c")]
