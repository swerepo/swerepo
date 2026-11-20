"""Locked rule: an older SWERepo never replaces a `.swerepo.toml` written by a newer SWERepo or in a newer
standard: not after loading it (it still loads, even naming components this version doesn't know), not
with a new state, and not with a state loaded before the newer SWERepo rewrote the file
(ADR-20261120-ecf7; SWEREPO-SPEC §9)."""

from pathlib import Path

import pytest

from swerepo.state import FILE_NAME, State, StateError

NEWER_VERSION = 'standard = 1\nswerepo = "0.2.0"\ncomponents = ["docs", "from-the-future"]\n'
NEWER_STANDARD = 'standard = 99\nswerepo = "0.1.0"\ncomponents = ["docs", "from-the-future"]\n'
OLDER = 'standard = 1\nswerepo = "0.0.9"\ncomponents = ["docs"]\n'


@pytest.mark.parametrize("newer", [NEWER_VERSION, NEWER_STANDARD])
def test_a_newer_file_on_disk_is_never_replaced(tmp_path: Path, newer: str):
    path = tmp_path / FILE_NAME
    path.write_text(newer)
    loaded = State.load(tmp_path, running="0.1.0")
    assert "from-the-future" in loaded.components
    path.write_text(OLDER)
    stale = State.load(tmp_path, running="0.1.0")  # loaded before the newer SWERepo rewrote the file
    path.write_text(newer)
    for state in (loaded, State.new(version="0.1.0"), stale):
        with pytest.raises(StateError):
            state.save(tmp_path, running="0.1.0")
        assert path.read_text() == newer
