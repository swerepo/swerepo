"""`tools/released_snapshot.py`, which writes each release's snapshot of the renders put together in code
(ADR-20261124-41e9 rule 2)."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from swerepo import rebuild
from swerepo.render import TemplateStore

TOOL = Path(__file__).resolve().parent.parent / "tools" / "released_snapshot.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("released_snapshot", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_covers_every_render_put_together_in_code(tool):
    store = TemplateStore()
    data = tool.snapshot("0.1.0", store)
    covered = {entry["template"] for entry in data["renders"]}
    assert covered == set(tool.assembled_ids(store))
    assert {"github/ruleset@1", "github/repo-settings@1", "ci/pyproject@1", "ci/workflow@1", "ci/workflow@2"} <= covered
    for entry in data["renders"]:  # each fingerprint is what rebuilding gives, every time
        text = rebuild.rebuild(store, entry["template"], entry["inputs"])
        assert text is not None and hashlib.sha256(text.encode()).hexdigest() == entry["fingerprint"]


def test_every_input_set_is_kept(tool):
    """Also those that render what another does: which inputs leave a render unchanged was released too (P8-F03)."""
    data = tool.snapshot("0.1.0")
    count = {t: sum(e["template"] == t for e in data["renders"]) for t in {e["template"] for e in data["renders"]}}
    assert count["ci/workflow@2"] == len(tool._workflows()) and count["ci/pyproject@1"] == 5
    assert count["github/ruleset@1"] == count["github/repo-settings@1"] == len(tool._settings())
    keys = [(e["template"], json.dumps(e["inputs"], sort_keys=True)) for e in data["renders"]]
    assert len(set(keys)) == len(keys)
    workflow = [e["fingerprint"] for e in data["renders"] if e["template"] == "ci/workflow@2"]
    assert len(set(workflow)) == len(workflow)  # each workflow input set reaches a branch of its own
    merges = {e["inputs"]["merge_methods"] for e in data["renders"] if e["template"] == "github/repo-settings@1"}
    assert {"squash", "merge,rebase"} <= merges  # with and without squash, and rebase


def test_it_writes_a_release_once_and_nothing_else(tool, tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    monkeypatch.setattr(tool, "FOLDER", tmp_path / "tests" / "released")
    assert tool.main(["--version", "0.1.0.dev0"]) == 2 and not (tmp_path / "tests").exists()
    assert tool.main(["--version", "0.1.0"]) == 0
    written = json.loads((tmp_path / "tests" / "released" / "0.1.0.json").read_text())
    assert written["version"] == "0.1.0" and written["renders"]
    assert tool.main(["--version", "0.1.0"]) == 1  # a released snapshot never changes
    assert "never changes" in capsys.readouterr().err
