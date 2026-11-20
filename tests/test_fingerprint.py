import pytest

from swerepo.fingerprint import (
    HASH,
    HTML,
    BlockError,
    comment_style,
    find_block,
    fingerprint,
    is_fingerprint,
    normalise,
)

BASE = "jobs:\n  test:\n    runs-on: ubuntu-latest\n"


class TestNormalise:
    def test_line_endings_become_lf(self):
        assert normalise("a\r\nb\rc\n") == "a\nb\nc\n"

    def test_trailing_whitespace_is_removed_from_each_line(self):
        assert normalise("a  \nb\t\n") == "a\nb\n"

    def test_exactly_one_final_newline(self):
        assert normalise("a") == "a\n"
        assert normalise("a\n\n\n") == "a\n"

    def test_byte_order_mark_is_dropped(self):
        assert normalise("﻿a\n") == "a\n"

    def test_leading_whitespace_and_inner_blank_lines_are_kept(self):
        assert normalise("  a\n\n    b\n") == "  a\n\n    b\n"

    def test_empty_and_whitespace_only_text_is_empty(self):
        assert normalise("") == ""
        assert normalise(" \n\t\n") == ""

    def test_bytes_are_accepted_even_when_not_utf8(self):
        assert normalise(b"a\r\n") == "a\n"
        assert normalise(b"\xff\xfe x\n")  # no error


class TestFingerprint:
    def test_is_64_hex_characters(self):
        assert is_fingerprint(fingerprint(BASE))

    @pytest.mark.parametrize(
        "variant",
        [
            BASE.replace("\n", "\r\n"),  # Windows line endings
            BASE.replace("ubuntu-latest\n", "ubuntu-latest   \n"),  # trailing spaces
            BASE + "\n\n",  # extra blank lines at the end
            BASE.rstrip("\n"),  # no final newline
            "﻿" + BASE,  # byte-order mark
            BASE.encode(),  # same text as bytes
        ],
    )
    def test_whitespace_only_differences_do_not_count_as_edits(self, variant):
        assert fingerprint(variant) == fingerprint(BASE)

    @pytest.mark.parametrize(
        "edit",
        [
            BASE.replace("ubuntu-latest", "macos-latest"),  # a real change
            BASE.replace("    runs-on", "      runs-on"),  # indentation means something in YAML
            BASE.replace("jobs:\n", "jobs:\n\n"),  # a blank line inside the text
            BASE + "  # a comment\n",
        ],
    )
    def test_every_other_change_counts(self, edit):
        assert fingerprint(edit) != fingerprint(BASE)

    def test_invalid_utf8_gives_a_stable_fingerprint(self):
        assert fingerprint(b"\xff\n") == fingerprint(b"\xff\n") != fingerprint(b"\xfe\n")

    def test_is_fingerprint_rejects_other_values(self):
        assert not is_fingerprint("abc")
        assert not is_fingerprint("G" * 64)
        assert not is_fingerprint(fingerprint(BASE).upper())
        assert not is_fingerprint(None)


class TestCommentStyle:
    @pytest.mark.parametrize("path", ["AGENTS.md", "docs/adr/README.md", "notes.markdown"])
    def test_markdown_uses_html_comments(self, path):
        assert comment_style(path) == HTML

    @pytest.mark.parametrize("path", [".gitignore", ".github/CODEOWNERS", "pyproject.toml", "ci.yml", "x.py"])
    def test_everything_else_uses_hash_comments(self, path):
        assert comment_style(path) == HASH


class TestFindBlock:
    def test_finds_the_lines_between_html_markers(self):
        text = "# Title\n\n<!-- swerepo:begin -->\nrule 1\nrule 2\n<!-- swerepo:end -->\nmine\n"
        block = find_block(text, style=HTML)
        assert block is not None
        assert (block.begin_line, block.end_line) == (3, 6)
        assert block.content == "rule 1\nrule 2\n"

    def test_finds_the_lines_between_hash_markers_with_a_note(self):
        text = "/docs/ @team\n# swerepo:begin (governance paths)\n/.github/ @owner\n# swerepo:end\n"
        block = find_block(text, style=HASH)
        assert block is not None and block.content == "/.github/ @owner\n"

    def test_an_empty_block_has_empty_content(self):
        block = find_block("<!-- swerepo:begin -->\n<!-- swerepo:end -->\n", style=HTML)
        assert block is not None and block.content == ""

    def test_no_block_is_none(self):
        assert find_block("# Title\nno markers\n", style=HTML) is None

    def test_markers_with_crlf_line_endings(self):
        block = find_block("<!-- swerepo:begin -->\r\nx\r\n<!-- swerepo:end -->\r\n", style=HTML)
        assert block is not None and block.content == "x\n"

    def test_other_marker_names_are_separate_blocks(self):
        text = (
            "<!-- swerepo:adr-index:begin -->\nindex\n<!-- swerepo:adr-index:end -->\n"
            "<!-- swerepo:begin -->\nrules\n<!-- swerepo:end -->\n"
        )
        assert find_block(text, style=HTML).content == "rules\n"
        assert find_block(text, style=HTML, marker="swerepo:adr-index").content == "index\n"

    def test_a_longer_word_is_not_a_marker(self):
        assert find_block("# swerepo:beginning\n# swerepo:ending\n", style=HASH) is None

    def test_the_other_style_does_not_match(self):
        assert find_block("# swerepo:begin\nx\n# swerepo:end\n", style=HTML) is None

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            ("<!-- swerepo:begin -->\nx\n", "line 1: `swerepo:begin` has no `swerepo:end`"),
            ("x\n<!-- swerepo:end -->\n", "line 2: `swerepo:end` without"),
            (
                "<!-- swerepo:begin -->\n<!-- swerepo:begin -->\n<!-- swerepo:end -->\n",
                "line 2: `swerepo:begin` inside",
            ),
            (
                "<!-- swerepo:begin -->\n<!-- swerepo:end -->\n<!-- swerepo:begin -->\n<!-- swerepo:end -->\n",
                "line 3: a second `swerepo` block",
            ),
        ],
    )
    def test_malformed_blocks_are_errors_naming_the_line(self, text, message):
        with pytest.raises(BlockError, match=message.replace("`", ".")):
            find_block(text, style=HTML)

    def test_a_byte_order_mark_before_the_first_marker(self):  # review finding P1-F02
        block = find_block("﻿<!-- swerepo:begin -->\nrule\n<!-- swerepo:end -->\n", style=HTML)
        assert block is not None and block.content == "rule\n"

    def test_a_marker_line_holds_one_comment_and_nothing_else(self):  # P1-F02
        text = "<!-- swerepo:begin --> real text <!-- note -->\nx\n<!-- swerepo:end -->\n"
        with pytest.raises(BlockError, match="line 3: .swerepo:end. without"):
            find_block(text, style=HTML)

    def test_a_note_without_closing_text_after_it_is_allowed(self):
        text = "<!-- swerepo:begin (managed by swerepo) -->\nx\n<!-- swerepo:end -->\n"
        assert find_block(text, style=HTML).content == "x\n"

    @pytest.mark.parametrize("fence", ["```", "~~~", "````"])
    def test_markers_in_markdown_code_fences_are_examples(self, fence):  # P1-F02
        text = (
            f"How it looks:\n{fence}markdown\n<!-- swerepo:begin -->\n<!-- swerepo:end -->\n{fence}\n"
            "<!-- swerepo:begin -->\nreal\n<!-- swerepo:end -->\n"
        )
        block = find_block(text, style=HTML)
        assert block is not None and (block.begin_line, block.content) == (6, "real\n")

    def test_a_fence_closes_only_with_the_same_character_and_no_info_string(self):
        text = "```\n~~~\n```python\n<!-- swerepo:begin -->\n```\n<!-- swerepo:begin -->\nx\n<!-- swerepo:end -->\n"
        assert find_block(text, style=HTML).begin_line == 6

    def test_a_fence_inside_the_block_is_part_of_its_content(self):
        text = "<!-- swerepo:begin -->\n```\ncode\n```\n<!-- swerepo:end -->\n"
        assert find_block(text, style=HTML).content == "```\ncode\n```\n"

    def test_inline_code_with_three_backticks_is_not_a_fence(self):  # review finding P1-F09
        text = "```@@name@@``` placeholders are replaced once.\n<!-- swerepo:begin -->\nrule\n<!-- swerepo:end -->\n"
        block = find_block(text, style=HTML)
        assert block is not None and (block.begin_line, block.content) == (2, "rule\n")

    def test_a_tilde_fence_may_have_backticks_in_its_info_string(self):
        text = "~~~ `example`\n<!-- swerepo:begin -->\n~~~\n<!-- swerepo:begin -->\nx\n<!-- swerepo:end -->\n"
        assert find_block(text, style=HTML).begin_line == 4

    def test_only_spaces_and_tabs_may_follow_a_closing_fence(self):  # review: Copilot on PR #2 (finding 3)
        text = (
            "```\n<!-- swerepo:begin -->\n```\u00a0\n<!-- swerepo:end -->\n```\n"
            "<!-- swerepo:begin -->\nreal\n<!-- swerepo:end -->\n"
        )
        block = find_block(text, style=HTML)
        assert block is not None and (block.begin_line, block.content) == (6, "real\n")
        assert (
            find_block("```\nx\n``` \t\n<!-- swerepo:begin -->\ny\n<!-- swerepo:end -->\n", style=HTML).content == "y\n"
        )

    def test_fences_mean_nothing_in_hash_style_files(self):
        text = "```\n# swerepo:begin\nx\n# swerepo:end\n"
        assert find_block(text, style=HASH).content == "x\n"

    def test_unknown_style_is_an_error(self):
        with pytest.raises(ValueError, match="unknown comment style"):
            find_block("x", style="semicolon")
