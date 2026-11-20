"""Locked rule: saving `.swerepo.toml`, also after SWERepo changed values and records in it and when a
newer SWERepo saves, keeps a person's comments (on their own line, or at the end of a line SWERepo
changed) and every key SWERepo doesn't know: top-level, in a table it knows, in a record it updated, or in
a table of its own, with its value (ADR-20261120-ecf7; SWEREPO-SPEC §9)."""

import tomllib
from pathlib import Path

from swerepo.fingerprint import fingerprint
from swerepo.state import FILE_NAME, Record, State

A, B = fingerprint("a"), fingerprint("b")
TEXT = f"""\
# a person's note on its own line
standard = 1
swerepo = "0.2.0"
components = ["docs"]  # mine
mode = "solo"  # solo for now
future_setting = "kept"

[projects]
ignore = []
my_note = "inside a known table"

[files."docs/PROGRESS.md"]
template = "docs/progress@1"  # why this template
rendered = "{A}"
written = "{A}"
reviewed_by = "a person"

[added_later]
x = 1
"""


def test_comments_and_unknown_keys_survive_changes_and_saves(tmp_path: Path):
    (tmp_path / FILE_NAME).write_text(TEXT)
    state = State.load(tmp_path, running="0.3.0")
    state.set_components(["docs", "ci"])
    state.set_mode("team")
    state.set_file("docs/PROGRESS.md", Record("docs/progress@2", B, B))  # an existing record, updated
    state.set_file("CHANGELOG.md", Record("docs/changelog@1", B, B))  # a new one
    state.save(tmp_path, running="0.3.0")
    saved = (tmp_path / FILE_NAME).read_text()
    for comment in ("# a person's note on its own line", "# mine", "# solo for now", "# why this template"):
        assert comment in saved
    data = tomllib.loads(saved)
    assert data["components"] == ["docs", "ci"] and data["mode"] == "team" and data["swerepo"] == "0.3.0"
    assert data["files"]["docs/PROGRESS.md"]["template"] == "docs/progress@2"
    assert data["files"]["docs/PROGRESS.md"]["reviewed_by"] == "a person"
    assert data["future_setting"] == "kept" and data["projects"]["my_note"] == "inside a known table"
    assert data["added_later"] == {"x": 1}
