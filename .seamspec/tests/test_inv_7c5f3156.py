"""Locked rule: a fingerprint ignores only line endings (CRLF, CR), trailing whitespace on any line,
trailing blank lines, a missing final newline and a leading byte-order mark, for text and bytes alike,
and changes for any other edit (ADR-20261120-9495; SWEREPO-SPEC §9). `update` relies on it never to
overwrite a person's change."""

from swerepo.fingerprint import fingerprint

BASE = "jobs:\n  test:\n    runs-on: ubuntu-latest\n"


def test_ignored_differences_keep_the_fingerprint():
    same = [
        BASE.replace("\n", "\r\n"),  # Windows line endings
        BASE.replace("\n", "\r"),  # old Mac line endings
        BASE.replace(":\n", ":  \n").replace("latest\n", "latest\t\n"),  # trailing spaces and tabs, several lines
        BASE + "\n\n",  # trailing blank lines
        BASE[:-1],  # no final newline
        "\ufeff" + BASE,  # byte-order mark
        BASE.encode(),  # the same text as bytes
        ("\ufeff" + BASE.replace("\n", "\r\n")).encode(),
    ]
    for text in same:
        assert fingerprint(text) == fingerprint(BASE), repr(text)


def test_every_other_edit_changes_the_fingerprint():
    edits = [
        BASE.replace("ubuntu", "macos"),  # a word
        BASE.replace("    runs", "      runs"),  # indentation
        BASE.replace("    runs", "\truns"),  # tabs instead of spaces
        BASE.replace("jobs:\n", "jobs:\n\n"),  # a blank line inside the text
        BASE.replace("  test:\n", ""),  # a deleted line
        BASE + "# note\n",  # an added line
    ]
    for text in edits:
        assert fingerprint(text) != fingerprint(BASE), repr(text)
