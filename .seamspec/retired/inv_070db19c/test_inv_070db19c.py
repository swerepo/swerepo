"""Locked rule: a `.swerepo.toml` written by a newer SWERepo, or in a newer standard, still loads, even
naming components this version doesn't know; but this older SWERepo refuses to save over it and leaves it
unchanged (ADR-20261120-ecf7; SWEREPO-SPEC §9)."""

from pathlib import Path

import pytest

from swerepo.state import FILE_NAME, State, StateError

NEWER_VERSION = 'standard = 1\nswerepo = "0.2.0"\ncomponents = ["docs", "from-the-future"]\n'
NEWER_STANDARD = 'standard = 99\nswerepo = "0.1.0"\ncomponents = ["docs", "from-the-future"]\n'


@pytest.mark.parametrize("text", [NEWER_VERSION, NEWER_STANDARD])
def test_a_newer_file_loads_but_is_never_overwritten(tmp_path: Path, text: str):
    (tmp_path / FILE_NAME).write_text(text)
    state = State.load(tmp_path, running="0.1.0")
    assert "from-the-future" in state.components
    with pytest.raises(StateError):
        state.save(tmp_path, running="0.1.0")
    assert (tmp_path / FILE_NAME).read_text() == text
