"""The three-way merge `update` uses (spec §16) and its rule for action pins (ADR-20261123-f571): Dependabot owns
pins, `update` never moves one backwards, and nothing but a clean, parseable pin line is ever decided for you."""

import pytest
from packaging.version import Version

from swerepo.merge import merge3, pin, pins_only_newer

A = "a" * 40
B = "b" * 40
C = "c" * 40


def uses(action: str, commit: str, version: str, indent: str = "      ") -> str:
    return f"{indent}- uses: {action}@{commit}  # v{version}"


def workflow(*steps: str, extra: str = "") -> str:
    return "\n".join(["name: ci", "jobs:", "  test:", "    steps:", *steps, "      - run: pytest" + extra]) + "\n"


class TestPinLines:
    def test_a_pin_is_a_full_commit_with_a_version(self):
        found = pin(uses("actions/checkout", A, "7.0.1"))
        assert found is not None and found.action == "actions/checkout" and found.version == Version("7.0.1")
        assert pin("    uses: actions/checkout@" + A + " #v7") is not None  # without `- `, tighter spacing

    @pytest.mark.parametrize(
        "line",
        [
            "      - uses: actions/checkout@v7  # v7.0.1",  # a tag, not a commit
            "      - uses: actions/checkout@" + A[:39] + "  # v7.0.1",  # too short
            "      - uses: actions/checkout@" + A.upper() + "  # v7.0.1",  # not lowercase
            "      - uses: actions/checkout@" + A,  # no version comment
            "      - uses: actions/checkout@" + A + "  # 7.0.1",  # no `v`
            "      - uses: actions/checkout@" + A + "  # vnext",  # not a version
            "      - uses: actions/checkout@" + A + "  # v7.0.1 pinned by hand",  # more after the version
            "      - run: echo uses: x@" + A + "  # v1",  # not a uses: line
            "      - uses: actions/checkout@" + A + "  # vv7.0.1",  # a second v (review M6-F02)
            "      - uses: actions/checkout@" + A + "  # v1!7.0.1",  # an epoch
        ],
    )
    def test_anything_else_is_not_a_pin(self, line: str):
        assert pin(line) is None

    def test_a_pin_keeps_its_version_as_written(self):
        """`packaging` writes 2026.03.01 as 2026.3.1 and 1.2.0-rc.1 as 1.2.0rc1: a pin keeps what was written."""
        for raw in ("2026.03.01", "1.2.0-rc.1"):
            found = pin(uses("acme/tool", A, raw))
            assert found is not None and found.raw == raw
            text = workflow(uses("acme/tool", A, raw))
            assert merge3(text, text, text).text == text  # nothing touched, nothing rewritten
        older, newer = workflow(uses("acme/tool", A, "2026.03.01")), workflow(uses("acme/tool", B, "2026.04.01"))
        assert merge3(older, newer, older).text == newer  # the winner's version, as written

    def test_check_counts_newer_pins_only_as_current(self):
        recorded = workflow(uses("actions/checkout", A, "7.0.1"), uses("astral-sh/setup-uv", A, "10.3.3"))
        bumped = workflow(uses("actions/checkout", B, "7.0.2"), uses("astral-sh/setup-uv", A, "10.3.3"))
        assert pins_only_newer(recorded, recorded) and pins_only_newer(recorded, bumped)
        assert not pins_only_newer(bumped, recorded)  # older
        same_version = workflow(uses("actions/checkout", B, "7.0.1"), uses("astral-sh/setup-uv", A, "10.3.3"))
        assert not pins_only_newer(recorded, same_version)  # the same version, another commit
        assert not pins_only_newer(recorded, bumped.replace("pytest", "pytest -x"))  # and another edit
        assert not pins_only_newer(recorded, bumped + "# more\n")

    def test_check_compares_as_fingerprints_do(self):
        """BOM, line endings, trailing spaces and the final newline don't count; a line separator inside a line
        isn't a new line (review M6-F04)."""
        recorded = workflow(uses("actions/checkout", A, "7.0.1"))
        bumped = workflow(uses("actions/checkout", B, "7.0.2"))
        assert pins_only_newer(recorded, "\ufeff" + bumped.replace("\n", "  \r\n") + "\r\n")
        with_separator = recorded.replace("name: ci", "name: ci\u2028more")
        assert pins_only_newer(with_separator, bumped.replace("name: ci", "name: ci\u2028more"))

    def test_check_never_counts_one_version_on_two_commits(self):
        recorded = workflow(uses("actions/checkout", A, "7.0.1"), uses("actions/checkout", A, "7.0.1", indent="  "))
        mixed = workflow(uses("actions/checkout", B, "7.0.2"), uses("actions/checkout", C, "7.0.2", indent="  "))
        assert not pins_only_newer(recorded, mixed)


class TestMerge:
    def test_edits_on_both_sides_merge(self):
        base = workflow(uses("actions/checkout", A, "7.0.1"))
        ours = base.replace("name: ci", "name: ci  # ours")
        theirs = base.replace("- run: pytest", "- run: pytest -q")
        result = merge3(base, ours, theirs)
        assert result.text == ours.replace("- run: pytest", "- run: pytest -q") and result.conflicts == 0

    def test_dependabots_pin_is_kept_when_the_template_didnt_move_it(self):
        base = workflow(uses("astral-sh/setup-uv", A, "10.3.3"))
        ours = workflow(uses("astral-sh/setup-uv", B, "10.4.0"))  # Dependabot, merged
        theirs = base.replace("- run: pytest", "- run: pytest -q")  # the template changed something else
        assert merge3(base, ours, theirs).text == ours.replace("- run: pytest", "- run: pytest -q")

    @pytest.mark.parametrize(("mine", "new"), [("10.4.0", "10.5.0"), ("10.5.0", "10.4.0")])
    def test_when_both_moved_a_pin_the_newer_wins(self, mine: str, new: str):
        commits = {"10.4.0": B, "10.5.0": C}
        base = workflow(uses("astral-sh/setup-uv", A, "10.3.3"))
        ours = workflow(uses("astral-sh/setup-uv", commits[mine], mine))
        theirs = workflow(uses("astral-sh/setup-uv", commits[new], new))
        result = merge3(base, ours, theirs)
        assert result.text == workflow(uses("astral-sh/setup-uv", C, "10.5.0")) and result.conflicts == 0

    def test_dependabots_pin_next_to_a_line_the_template_changed(self):
        """A workflow puts `with:` lines right under a pin: git alone would call these neighbours a conflict."""
        base = workflow(uses("astral-sh/setup-uv", A, "10.3.3"), "        with:", '          version: "0.9.28"')
        ours = base.replace(A + "  # v10.3.3", B + "  # v10.4.0")  # Dependabot
        theirs = base.replace('"0.9.28"', '"0.10.0"')  # the template moves uv on the next line but one
        result = merge3(base, ours, theirs)
        assert result.text == ours.replace('"0.9.28"', '"0.10.0"') and result.conflicts == 0

    def test_a_pin_line_the_template_reshaped_is_an_ordinary_edit(self):
        base = workflow(uses("astral-sh/setup-uv", A, "10.3.3"))
        ours = workflow(uses("astral-sh/setup-uv", B, "10.4.0"))
        theirs = workflow(uses("astral-sh/setup-uv", C, "10.5.0", indent="        "))  # moved, not just re-pinned
        assert merge3(base, ours, theirs).text is None

    def test_a_new_line_from_the_template_never_brings_an_older_pin(self):
        base = workflow(uses("actions/checkout", A, "7.0.1"))
        ours = workflow(uses("actions/checkout", B, "7.0.2"))  # Dependabot
        second = uses("actions/checkout", A, "7.0.1", indent="        ")  # a step the new template adds
        theirs = workflow(uses("actions/checkout", A, "7.0.1"), second)
        result = merge3(base, ours, theirs)
        expected = workflow(
            uses("actions/checkout", B, "7.0.2"), uses("actions/checkout", B, "7.0.2", indent="        ")
        )
        assert result.text == expected and result.pins_kept == ["actions/checkout"]

    def test_a_pin_the_person_lowered_is_their_edit(self):
        """Review M6-F03: kept when the template left the line alone, a conflict when it changed it."""
        base = workflow(uses("actions/checkout", B, "7.0.2"))
        lowered = workflow(uses("actions/checkout", A, "7.0.1"))
        elsewhere = base.replace("name: ci", "name: ci-new")  # not next to the pin: git would call that a conflict
        assert merge3(base, lowered, elsewhere).text == lowered.replace("name: ci", "name: ci-new")
        assert merge3(base, lowered, base).text == lowered  # nothing else changed
        moved = workflow(uses("actions/checkout", C, "7.1.0"))
        assert merge3(base, lowered, moved).text is None

    def test_a_crlf_checkout_merges_with_lf_templates(self):
        """Review M6-F01: templates render LF; a CRLF checkout keeps CRLF, and still merges line by line."""
        base = workflow(uses("astral-sh/setup-uv", A, "10.3.3"))
        ours = workflow(uses("astral-sh/setup-uv", B, "10.4.0"), "      - run: echo extra").replace("\n", "\r\n")
        theirs = base.replace("name: ci", "name: ci-new")
        result = merge3(base, ours, theirs)
        expected = workflow(uses("astral-sh/setup-uv", B, "10.4.0"), "      - run: echo extra")
        assert result.text == expected.replace("name: ci", "name: ci-new").replace("\n", "\r\n")
        lf = merge3(base, ours.replace("\r\n", "\n"), theirs)
        assert lf.text == expected.replace("name: ci", "name: ci-new")  # an LF file stays LF

    def test_an_untouched_file_isnt_moved_backwards_either(self):
        base = ours = workflow(uses("actions/checkout", B, "7.0.2"))
        theirs = workflow(uses("actions/checkout", A, "7.0.1"))  # an older template, somehow
        assert merge3(base, ours, theirs).text == ours

    @pytest.mark.parametrize(
        "theirs_line",
        [
            uses("astral-sh/setup-uv", C, "10.4.0"),  # the same version, another commit: never guessed
            "      - uses: astral-sh/setup-uv@v10  # v10.5.0",  # a tag
            "      - uses: astral-sh/setup-uv@" + C + "  # v10.5.0 (pinned)",  # more on the line
        ],
    )
    def test_anything_but_a_clean_pin_conflict_stays_a_conflict(self, theirs_line: str):
        base = workflow(uses("astral-sh/setup-uv", A, "10.3.3"))
        ours = workflow(uses("astral-sh/setup-uv", B, "10.4.0"))
        result = merge3(base, ours, workflow(theirs_line))
        assert result.text is None and result.conflicts == 1

    def test_an_ordinary_conflict_is_reported_never_written(self):
        base = workflow(uses("actions/checkout", A, "7.0.1"))
        ours = base.replace("- run: pytest", "- run: pytest -x")
        theirs = base.replace("- run: pytest", "- run: pytest -q")
        result = merge3(base, ours, theirs)
        assert result.text is None and result.conflicts == 1

    def test_a_pin_conflict_next_to_another_conflict_leaves_the_file_alone(self):
        base = workflow(uses("astral-sh/setup-uv", A, "10.3.3"))
        ours = workflow(uses("astral-sh/setup-uv", B, "10.4.0"), extra=" -x")
        theirs = workflow(uses("astral-sh/setup-uv", C, "10.5.0"), extra=" -q")
        result = merge3(base, ours, theirs)
        assert result.text is None and result.conflicts >= 1

    def test_the_files_own_marker_like_lines_are_just_text(self):
        base = workflow(uses("actions/checkout", A, "7.0.1")) + "<<<<<<< not a marker\n=======\n>>>>>>> nor this\n"
        ours = base.replace("name: ci", "name: ours")
        theirs = base.replace("- run: pytest", "- run: pytest -q")
        result = merge3(base, ours, theirs)
        assert result.text is not None and "<<<<<<< not a marker" in result.text and "name: ours" in result.text


def test_two_commits_for_one_version_across_lines_of_ours_conflict():
    """Two lines of the person's file pinning one version to two commits conflict, even when the new render adds
    no pin line (review of inv_d60ffffd)."""
    commit = "1" * 40
    base = f"a\n- uses: actions/checkout@{commit}  # v7.0.1\nb\n- uses: actions/checkout@{commit}  # v7.0.1\nc\n"
    ours = base.replace(f"@{commit}  # v7.0.1", "@" + "f" * 40 + "  # v99.0.0", 1)
    ours = ours.replace(f"@{commit}  # v7.0.1", "@" + "e" * 40 + "  # v99.0.0", 1)
    theirs = base.replace("c\n", "c changed\n")
    result = merge3(base, ours, theirs)
    assert result.text is None and result.conflicts
