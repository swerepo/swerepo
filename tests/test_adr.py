"""`swerepo adr new` and `swerepo adr index` (spec §6.5, ADR-20261121-0b7e)."""

import datetime
from pathlib import Path

import pytest
from repo_helpers import make
from typer.testing import CliRunner

from swerepo.adr import AdrError, index_table, list_adrs, new_adr, read_adr, slug, with_index, write_index
from swerepo.cli import app
from swerepo.state import State

DAY = datetime.date(2026, 11, 21)
README = "# ADRs\n\nOurs.\n\n<!-- swerepo:adr-index:begin -->\nold\n<!-- swerepo:adr-index:end -->\n\nAfter.\n"


def adr(title: str, status: str = "ACCEPTED", extra: str = "") -> str:
    return f"---\nid: x\ntitle: {title}\nstatus: {status}            # a comment\n{extra}---\n\n# Body\n"


class TestReading:
    def test_frontmatter(self, tmp_path: Path):
        make(tmp_path, {"ADR-20260101-abcd-x.md": adr("Use | pipes")})
        found = read_adr(tmp_path / "ADR-20260101-abcd-x.md")
        assert (found.id, found.title, found.status) == ("ADR-20260101-abcd", "Use \\| pipes", "ACCEPTED")

    def test_superseded_names_its_successor(self, tmp_path: Path):
        make(tmp_path, {"ADR-20260101-abcd-x.md": adr("Old", "SUPERSEDED", "superseded_by: ADR-20260202-beef\n")})
        assert read_adr(tmp_path / "ADR-20260101-abcd-x.md").status == "SUPERSEDED by ADR-20260202-beef"

    def test_without_frontmatter_the_heading_is_the_title(self, tmp_path: Path):
        make(tmp_path, {"ADR-20260101-abcd-x.md": "# ADR-20260101-abcd: Use uv\n\nText.\n"})
        found = read_adr(tmp_path / "ADR-20260101-abcd-x.md")
        assert (found.title, found.status) == ("Use uv", "?")

    def test_only_adr_files_are_listed_oldest_first(self, tmp_path: Path):
        make(tmp_path, {
            "ADR-20260202-0001-b.md": adr("B"), "ADR-20260101-ffff-a.md": adr("A"),
            "README.md": "x", "TEMPLATE.md": "x", "ADR-notes.md": "x",
        })  # fmt: skip
        assert [a.title for a in list_adrs(tmp_path)] == ["A", "B"]


class TestIndex:
    def test_the_table(self, tmp_path: Path):
        make(tmp_path, {"ADR-20260101-abcd-x.md": adr("X")})
        assert index_table(list_adrs(tmp_path)) == (
            "| ID | Title | Status |\n|---|---|---|\n| [ADR-20260101-abcd](ADR-20260101-abcd-x.md) | X | ACCEPTED |\n"
        )

    def test_only_the_text_between_the_markers_changes(self, tmp_path: Path):
        make(tmp_path, {"README.md": README, "ADR-20260101-abcd-x.md": adr("X")})
        assert write_index(tmp_path) is True
        text = (tmp_path / "README.md").read_text()
        assert text.startswith("# ADRs\n\nOurs.\n\n<!-- swerepo:adr-index:begin -->\n| ID |")
        assert text.endswith("<!-- swerepo:adr-index:end -->\n\nAfter.\n") and "old" not in text
        assert write_index(tmp_path) is False  # current: nothing to write

    def test_no_markers_or_broken_markers(self, tmp_path: Path):
        with pytest.raises(AdrError, match="no index markers"):
            with_index("# ADRs\n", [])
        with pytest.raises(AdrError, match="broken"):
            with_index("<!-- swerepo:adr-index:begin -->\n", [])
        with pytest.raises(AdrError, match="missing"):
            write_index(tmp_path)


class TestNew:
    def test_named_and_filled_from_the_folders_template(self, tmp_path: Path):
        template = "id: ADR-YYYYMMDD-xxxx\ndate: YYYY-MM-DD\n# ADR-YYYYMMDD-xxxx: One line that states the decision\n"
        make(tmp_path, {"TEMPLATE.md": template})
        created = new_adr(tmp_path, "  Use Postgres,  for invoices! ", today=DAY, token="beef")
        assert created.name == "ADR-20261121-beef-use-postgres-for-invoices.md"
        assert created.read_text() == (
            "id: ADR-20261121-beef\ndate: 2026-11-21\n# ADR-20261121-beef: Use Postgres, for invoices!\n"
        )

    def test_without_a_template_swerepos_own_is_used(self, tmp_path: Path):
        created = new_adr(tmp_path, "Pick a queue", today=DAY, token="0001")
        text = created.read_text()
        assert text.startswith("---\nid: ADR-20261121-0001\ntitle: Pick a queue\nstatus: PROPOSED")

    def test_a_taken_id_and_bad_input_are_errors(self, tmp_path: Path):
        new_adr(tmp_path, "One", today=DAY, token="abcd")
        with pytest.raises(AdrError, match="already exists"):
            new_adr(tmp_path, "Two", today=DAY, token="abcd")
        with pytest.raises(AdrError, match="empty"):
            new_adr(tmp_path, "   ")
        with pytest.raises(AdrError, match="doesn't exist"):
            new_adr(tmp_path / "nope", "Three")

    def test_random_ids_differ(self, tmp_path: Path):
        names = {new_adr(tmp_path, "Same title", today=DAY).name for _ in range(5)}
        assert len(names) == 5

    @pytest.mark.parametrize(("title", "expected"), [("Use uv!", "use-uv"), ("***", "decision"), ("a" * 80, "a" * 60)])
    def test_slug(self, title: str, expected: str):
        assert slug(title) == expected


class TestCommandLine:
    runner = CliRunner()

    def test_new_then_index(self, tmp_path: Path):
        make(tmp_path, {"docs/adr/README.md": README})
        result = self.runner.invoke(app, ["adr", "new", "Use uv", "--path", str(tmp_path)])
        assert (
            result.exit_code == 0
            and result.output.startswith("Created docs/adr/ADR-")
            and "Index updated." in result.output
        )
        assert "Use uv | PROPOSED |" in (tmp_path / "docs/adr/README.md").read_text()
        assert self.runner.invoke(app, ["adr", "index", "--path", str(tmp_path)]).output == "Index already current.\n"

    def test_an_adopted_folder_is_used(self, tmp_path: Path):
        make(tmp_path, {"doc/decisions/README.md": README})
        state = State.new(version="0.0.1")
        state.set_adopted("adr_dir", "doc/decisions")
        state.save(tmp_path, running="0.0.1")
        result = self.runner.invoke(app, ["adr", "new", "Adopted", "--path", str(tmp_path)])
        assert result.exit_code == 0 and "Created doc/decisions/ADR-" in result.output

    def test_errors_exit_1(self, tmp_path: Path):
        assert self.runner.invoke(app, ["adr", "new", "X", "--path", str(tmp_path)]).exit_code == 1
        make(tmp_path, {"docs/adr/README.md": "# no markers\n"})
        result = self.runner.invoke(app, ["adr", "index", "--path", str(tmp_path)])
        assert result.exit_code == 1 and "no index markers" in result.output
        new = self.runner.invoke(app, ["adr", "new", "Still created", "--path", str(tmp_path)])
        assert new.exit_code == 0 and "Index not updated: no index markers" in new.output


class TestGeminiReviewRound1:
    """Phase 3 review findings P3-F02, P3-F03, P3-F05."""

    def test_p3_f02_unicode_line_breaks_above_the_index_stay_put(self, tmp_path: Path):
        readme = "﻿# ADRs second\x0cthird\r\n" + README
        make(tmp_path, {"README.md": readme, "ADR-20260101-abcd-x.md": adr("X")})
        write_index(tmp_path)
        text = (tmp_path / "README.md").read_bytes().decode("utf-8")  # as it is on disk, CRLF included
        assert text.startswith("﻿# ADRs second\x0cthird\r\n# ADRs\n") and "| X | ACCEPTED |" in text
        assert text.count("<!-- swerepo:adr-index:begin -->") == 1 and "old" not in text

    @pytest.mark.parametrize(
        "title", ["Fix #12: handle retries", 'Say "hi" | bye', "[draft] plan", "on", "2026 roadmap", "it's: fine"]
    )
    def test_p3_f05_titles_survive_frontmatter_and_the_index(self, tmp_path: Path, title: str):
        new_adr(tmp_path, title, today=DAY, token="abcd")
        assert list_adrs(tmp_path)[0].title == title.replace("|", "\\|")

    def test_p3_f05_quoted_values_keep_their_hash(self, tmp_path: Path):
        make(tmp_path, {
            "ADR-20260101-0001-a.md": '---\ntitle: "Fix #12: retries"  # note\nstatus: ACCEPTED\n---\n',
            "ADR-20260101-0002-b.md": "---\ntitle: 'It''s #1'\n---\n",
        })  # fmt: skip
        assert [a.title for a in list_adrs(tmp_path)] == ["Fix #12: retries", "It's #1"]

    def test_p3_f03_unreadable_files_are_errors_without_paths(self, tmp_path: Path):
        make(tmp_path, {"docs/adr/README.md": "x"})
        (tmp_path / "docs/adr/README.md").write_bytes(b"\xff\xfe broken")
        result = CliRunner().invoke(app, ["adr", "index", "--path", str(tmp_path)])
        assert result.exit_code == 1 and "docs/adr/README.md: can't read it (not UTF-8 text)" in result.output
        assert str(tmp_path) not in result.output

    def test_p3_f03_a_missing_folder_is_wrong_usage_and_names_are_relative(self, tmp_path: Path):
        runner = CliRunner()
        assert runner.invoke(app, ["adr", "new", "X", "--path", str(tmp_path / "nope")]).exit_code == 2
        assert runner.invoke(app, ["progress", "--path", str(tmp_path / "nope")]).exit_code == 2
        result = runner.invoke(app, ["adr", "new", "X", "--path", str(tmp_path)])
        assert result.exit_code == 1 and "docs/adr/ doesn't exist" in result.output


def test_p3_f08_a_crlf_readme_keeps_crlf_and_settles(tmp_path: Path):
    make(tmp_path, {"ADR-20260101-abcd-x.md": adr("X")})
    (tmp_path / "README.md").write_bytes(
        b"# ADRs\r\n<!-- swerepo:adr-index:begin -->\r\nold\r\n<!-- swerepo:adr-index:end -->\r\nAfter.\r\n"
    )
    assert write_index(tmp_path) is True
    raw = (tmp_path / "README.md").read_bytes()
    assert b"\n" not in raw.replace(b"\r\n", b"") and b"| X | ACCEPTED |\r\n" in raw
    assert write_index(tmp_path) is False  # a second run finds it current


class TestCopilotReviewOfPR6:
    def test_a_title_that_isnt_utf8_stops_the_index(self, tmp_path: Path):
        make(tmp_path, {"README.md": README})
        (tmp_path / "ADR-20260101-abcd-x.md").write_bytes(b"---\ntitle: Caf\xe9\n---\n")
        with pytest.raises(AdrError, match="not UTF-8"):
            write_index(tmp_path)
        assert (tmp_path / "README.md").read_text() == README

    @pytest.mark.parametrize(
        ("value", "title"),
        [
            (r'"Use — for separators"', "Use — for separators"),
            (r'"Caf\xe9 \U0001F600"', "Caf\xe9 \U0001f600"),
            (r'"a\_b\Lc"', "a b c"),  # a no-break space and a line separator: a table cell folds both to spaces
            (r'"keep \q as written"', "keep \\q as written"),
        ],
    )
    def test_yaml_double_quoted_escapes(self, tmp_path: Path, value: str, title: str):
        make(tmp_path, {"ADR-20260101-abcd-x.md": f"---\ntitle: {value}\n---\n"})
        assert list_adrs(tmp_path)[0].title == title

    def test_adr_commands_never_write_through_a_link_out_of_the_repository(self, tmp_path: Path, tmp_path_factory):
        outside = tmp_path_factory.mktemp("outside")
        make(outside, {"adr/README.md": README})
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs/adr").symlink_to(outside / "adr", target_is_directory=True)
        runner = CliRunner()
        for args in (["adr", "new", "X"], ["adr", "index"]):
            result = runner.invoke(app, [*args, "--path", str(tmp_path)])
            assert result.exit_code == 1 and "leads out of the repository" in result.output
        assert sorted(p.name for p in (outside / "adr").iterdir()) == ["README.md"]
        assert (outside / "adr/README.md").read_text() == README

    def test_a_readme_link_out_of_the_repository_is_refused(self, tmp_path: Path, tmp_path_factory):
        outside = tmp_path_factory.mktemp("outside")
        make(outside, {"README.md": README})
        (tmp_path / "docs/adr").mkdir(parents=True)
        (tmp_path / "docs/adr/README.md").symlink_to(outside / "README.md")
        result = CliRunner().invoke(app, ["adr", "index", "--path", str(tmp_path)])
        assert result.exit_code == 1 and (outside / "README.md").read_text() == README
