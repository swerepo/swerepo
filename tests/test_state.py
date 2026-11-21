from pathlib import Path

import pytest

from swerepo.fingerprint import fingerprint
from swerepo.state import FILE_NAME, Record, State, StateError

HASH_A = fingerprint("a")
HASH_B = fingerprint("b")

SPEC_EXAMPLE = f"""\
# Written by SWERepo (SWEREPO-SPEC §9). Commit this file.
standard = 1
swerepo = "0.1.0"
components = ["docs", "agents", "ci"]
mode = "solo"  # a person's comment

[values]
project = "invoices"
python = ["3.11", "3.12"]

[files."docs/adr/TEMPLATE.md"]
template = "docs/adr-template@1"
rendered = "{HASH_A}"
written = "{HASH_B}"

[blocks."AGENTS.md"]
template = "agents/block@1"
rendered = "{HASH_A}"
written = "{HASH_A}"

[projects]
ignore = ["tools", "examples/legacy"]

[from_a_newer_swerepo]
something = true
"""


def test_reads_the_spec_example():
    state = State.parse(SPEC_EXAMPLE)
    assert (state.standard, state.swerepo_version, state.mode) == (1, "0.1.0", "solo")
    assert state.components == ["docs", "agents", "ci"]
    assert state.values == {"project": "invoices", "python": ["3.11", "3.12"]}
    assert state.files() == {"docs/adr/TEMPLATE.md": Record("docs/adr-template@1", HASH_A, HASH_B)}
    assert state.blocks() == {"AGENTS.md": Record("agents/block@1", HASH_A, HASH_A)}
    assert state.project_ignore == ["tools", "examples/legacy"]


def test_round_trip_keeps_comments_order_and_unknown_keys():
    assert State.parse(SPEC_EXAMPLE).dumps() == SPEC_EXAMPLE


def test_changes_keep_the_rest_of_the_file():
    state = State.parse(SPEC_EXAMPLE)
    state.set_file("docs/PROGRESS.md", Record("docs/progress@1", HASH_B, HASH_B))
    text = state.dumps()
    assert "# a person's comment" in text
    assert "[from_a_newer_swerepo]" in text
    assert State.parse(text).files()["docs/PROGRESS.md"] == Record("docs/progress@1", HASH_B, HASH_B)


def test_a_new_state_round_trips():
    state = State.new(version="0.1.0")
    state.set_components(["docs", "ci"])
    state.set_mode("team")
    state.set_value("default_branch", "main")
    state.set_file(".github/workflows/swerepo-ci.yml", Record("ci/python@1", HASH_A, HASH_A))
    state.set_block("CLAUDE.md", Record("agents/block@1", HASH_B, HASH_B))
    text = state.dumps()
    assert text.startswith("# Written by SWERepo")
    assert 'components = ["docs", "ci"]' in text
    again = State.parse(text)
    assert again.components == ["docs", "ci"] and again.mode == "team"
    assert again.files() == state.files() and again.blocks() == state.blocks()


def test_remove_file():
    state = State.parse(SPEC_EXAMPLE)
    state.remove_file("docs/adr/TEMPLATE.md")
    state.remove_file("not/there.md")
    assert state.files() == {}


class TestLoadAndSave:
    def test_load_without_a_file_is_none(self, tmp_path: Path):
        assert State.load(tmp_path) is None

    def test_save_then_load(self, tmp_path: Path):
        state = State.new(version="0.1.0")
        state.set_components(["docs"])
        path = state.save(tmp_path, running="0.1.0")
        assert path == tmp_path / FILE_NAME
        assert State.load(tmp_path).components == ["docs"]
        assert [p.name for p in tmp_path.iterdir()] == [FILE_NAME]  # no temporary file left behind

    def test_save_records_the_running_version(self, tmp_path: Path):
        state = State.parse(SPEC_EXAMPLE)
        state.save(tmp_path, running="0.2.0")
        assert State.load(tmp_path).swerepo_version == "0.2.0"

    def test_save_keeps_the_file_mode(self, tmp_path: Path):
        (tmp_path / FILE_NAME).write_text(SPEC_EXAMPLE, encoding="utf-8")
        (tmp_path / FILE_NAME).chmod(0o640)
        State.load(tmp_path).save(tmp_path, running="0.1.0")
        assert (tmp_path / FILE_NAME).stat().st_mode & 0o777 == 0o640

    def test_an_older_swerepo_does_not_overwrite_a_newer_ones_file(self, tmp_path: Path):
        (tmp_path / FILE_NAME).write_text(SPEC_EXAMPLE.replace('"0.1.0"', '"0.3.0"'), encoding="utf-8")
        state = State.load(tmp_path)  # reading is fine
        assert state.written_by_newer("0.2.0") == "SWERepo 0.3.0 wrote it; this is 0.2.0"
        with pytest.raises(StateError, match="not saved: SWERepo 0.3.0 wrote it; this is 0.2.0. Upgrade"):
            state.save(tmp_path, running="0.2.0")
        assert "0.3.0" in (tmp_path / FILE_NAME).read_text(encoding="utf-8")  # untouched

    def test_a_newer_standard_is_not_overwritten(self, tmp_path: Path):
        state = State.parse(SPEC_EXAMPLE.replace("standard = 1", "standard = 2"))
        with pytest.raises(StateError, match="standard 2; this SWERepo supports up to 1"):
            state.save(tmp_path, running="0.9.0")

    def test_a_development_version_counts_as_older_than_its_release(self):
        state = State.parse(SPEC_EXAMPLE)
        assert state.written_by_newer("0.1.0.dev0") is not None
        assert state.written_by_newer("0.1.0") is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("standard = 1", "standard = 0"), "standard: must be a positive whole number"),
        (("standard = 1", 'standard = "1"'), "standard: must be a positive whole number"),
        (('swerepo = "0.1.0"', 'swerepo = "latest"'), "swerepo: 'latest' is not a version"),
        (('"docs", "agents"', '"docs", "lint"'), "components: unknown component 'lint'"),
        (('mode = "solo"', 'mode = "pair"'), "mode: 'pair' is not one of solo, team"),
        (('template = "docs/adr-template@1"', 'template = "adr-template"'), "template: 'adr-template' is not a"),
        ((f'written = "{HASH_B}"', 'written = "abc"'), r"files\.docs/adr/TEMPLATE\.md\.written: not a fingerprint"),
        (('[files."docs/adr/TEMPLATE.md"]', '[files."../outside.md"]'), "must not have empty, '.' or '..' parts"),
        (('[files."docs/adr/TEMPLATE.md"]', '[files."/etc/passwd"]'), "must be relative"),
        (('[files."docs/adr/TEMPLATE.md"]', '[files."docs\\\\adr.md"]'), "must be relative and use '/'"),
        (('[files."docs/adr/TEMPLATE.md"]', '[files."docs//adr/TEMPLATE.md"]'), "must not have empty"),
        (('[files."docs/adr/TEMPLATE.md"]', '[files."docs/./adr.md"]'), "must not have empty, '.' or '..'"),
        (('[files."docs/adr/TEMPLATE.md"]', '[files."docs/a\\u0000b.md"]'), "is not a repository path"),
        (('ignore = ["tools", "examples/legacy"]', 'ignore = ["."]'), "projects.ignore: '.'"),
        (('template = "docs/adr-template@1"', 'template = "docs/adr-template@1\\n"'), "is not a template id"),
        (('ignore = ["tools", "examples/legacy"]', 'ignore = ["tools/"]'), "projects.ignore: 'tools/'"),
        (('python = ["3.11", "3.12"]', "python = 3.11"), "values.python: must be text or a list of text"),
    ],
)
def test_invalid_files_are_errors_naming_the_key(change, message):
    old, new = change
    assert old in SPEC_EXAMPLE
    with pytest.raises(StateError, match=message):
        State.parse(SPEC_EXAMPLE.replace(old, new), running="0.1.0")


def test_a_newer_swerepos_file_loads_even_with_components_this_version_does_not_know(tmp_path: Path):
    # Review finding P1-F03: `check` must be able to read it and say "upgrade SWERepo".
    newer = SPEC_EXAMPLE.replace('"0.1.0"', '"0.3.0"').replace('"docs", "agents"', '"docs", "hooks"')
    newer = newer.replace('mode = "solo"', 'mode = "pair"')
    (tmp_path / FILE_NAME).write_text(newer, encoding="utf-8")
    state = State.load(tmp_path, running="0.2.0")
    assert state.components == ["docs", "hooks", "ci"] and state.mode == "pair"
    with pytest.raises(StateError, match="not saved: SWERepo 0.3.0 wrote it"):
        state.save(tmp_path, running="0.2.0")
    assert (tmp_path / FILE_NAME).read_text(encoding="utf-8") == newer


def test_a_file_from_this_or_an_older_version_must_name_known_components():
    older = SPEC_EXAMPLE.replace('"docs", "agents"', '"docs", "hooks"')
    with pytest.raises(StateError, match="unknown component 'hooks'"):
        State.parse(older, running="0.1.0")


def test_the_version_is_validated_even_in_a_newer_standard():  # review finding P1-F10
    with pytest.raises(StateError, match="swerepo: 'not-a-version' is not a version"):
        State.parse('standard = 2\nswerepo = "not-a-version"\ncomponents = ["docs"]\n', running="0.1.0")


def test_a_newer_file_still_needs_the_right_types():
    newer = SPEC_EXAMPLE.replace('"0.1.0"', '"0.3.0"').replace(
        'components = ["docs", "agents", "ci"]', "components = 3"
    )
    with pytest.raises(StateError, match="components: must be a list"):
        State.parse(newer, running="0.2.0")


def test_an_unreadable_file_is_a_state_error(tmp_path: Path):
    (tmp_path / FILE_NAME).write_bytes(b'standard = 1\nswerepo = "\xff"\n')
    with pytest.raises(StateError, match=r"\.swerepo\.toml: can't read it"):
        State.load(tmp_path)


class TestTheFileOnDisk:  # review: Copilot on PR #2 (finding 1)
    NEWER_ON_DISK = 'standard = 1\nswerepo = "0.3.0"\ncomponents = ["docs"]\n'

    def test_a_new_state_is_not_saved_over_a_newer_file(self, tmp_path: Path):
        (tmp_path / FILE_NAME).write_text(self.NEWER_ON_DISK, encoding="utf-8")
        with pytest.raises(StateError, match="the file on disk: SWERepo 0.3.0 wrote it; this is 0.1.0"):
            State.new(version="0.1.0").save(tmp_path, running="0.1.0")
        assert (tmp_path / FILE_NAME).read_text(encoding="utf-8") == self.NEWER_ON_DISK

    def test_a_stale_state_is_not_saved_over_a_file_a_newer_swerepo_wrote_since(self, tmp_path: Path):
        (tmp_path / FILE_NAME).write_text(SPEC_EXAMPLE, encoding="utf-8")
        state = State.load(tmp_path, running="0.1.0")
        (tmp_path / FILE_NAME).write_text(SPEC_EXAMPLE.replace("standard = 1", "standard = 2"), encoding="utf-8")
        with pytest.raises(StateError, match="the file on disk: it uses standard 2"):
            state.save(tmp_path, running="0.1.0")

    def test_an_unreadable_file_on_disk_is_not_replaced(self, tmp_path: Path):
        (tmp_path / FILE_NAME).write_text("standard = \n", encoding="utf-8")
        with pytest.raises(StateError, match="the existing file can't be read"):
            State.new(version="0.1.0").save(tmp_path, running="0.1.0")
        assert (tmp_path / FILE_NAME).read_text(encoding="utf-8") == "standard = \n"

    def test_an_older_file_on_disk_is_replaced(self, tmp_path: Path):
        (tmp_path / FILE_NAME).write_text(self.NEWER_ON_DISK.replace("0.3.0", "0.0.9"), encoding="utf-8")
        State.new(version="0.1.0").save(tmp_path, running="0.1.0")
        assert State.load(tmp_path, running="0.1.0").swerepo_version == "0.1.0"
        assert [p.name for p in tmp_path.iterdir()] == [FILE_NAME]


def test_updating_a_record_keeps_its_comments_and_extra_keys():  # review: Copilot on PR #2 (finding 2)
    text = SPEC_EXAMPLE.replace('template = "docs/adr-template@1"', 'template = "docs/adr-template@1"  # why')
    text = text.replace(f'written = "{HASH_B}"', f'written = "{HASH_B}"\nnote = "mine"')
    state = State.parse(text, running="0.1.0")
    state.set_file("docs/adr/TEMPLATE.md", Record("docs/adr-template@2", HASH_B, HASH_B))
    state.set_block("AGENTS.md", Record("agents/block@2", HASH_B, HASH_B))
    out = state.dumps()
    assert "# why" in out and 'note = "mine"' in out
    again = State.parse(out, running="0.1.0")
    assert again.files()["docs/adr/TEMPLATE.md"] == Record("docs/adr-template@2", HASH_B, HASH_B)
    assert again.blocks()["AGENTS.md"] == Record("agents/block@2", HASH_B, HASH_B)


class TestSettings:  # [agents], [adopted], [pr] (ADR-20261120-5e21)
    BASE = 'standard = 1\nswerepo = "0.1.0"\n'

    def test_defaults_without_the_tables(self):
        state = State.parse(self.BASE, running="0.1.0")
        assert state.hosts == [] and state.adopted == {}
        assert state.pr_enforce is True and state.exempt_authors == ["dependabot[bot]"]

    def test_values_are_read(self):
        state = State.parse(
            self.BASE + '[agents]\nhosts = ["claude"]\n[adopted]\nadr_dir = "doc/decisions"\nlinters = ["black"]\n'
            '[pr]\nenforce = false\nexempt_authors = []\nskip_progress_label = "no-progress"\n',
            running="0.1.0",
        )
        assert state.hosts == ["claude"] and state.adopted["adr_dir"] == "doc/decisions"
        assert state.pr_enforce is False and state.exempt_authors == []

    @pytest.mark.parametrize(
        ("body", "message"),
        [
            ('[pr]\nenforce = "no"\n', "pr.enforce: must be true or false"),
            ('[pr]\nexempt_authors = "bot"\n', "pr.exempt_authors: must be a list of text"),
            ("[pr]\nskip_progress_label = 1\n", "pr.skip_progress_label: must be text"),
            ('[adopted]\nadr_dir = "../decisions"\n', "adopted.adr_dir"),
            ("[adopted]\nlinters = [1]\n", "adopted.linters: must be a list of text"),
            ('[agents]\nhosts = "claude"\n', "agents.hosts: must be a list of text"),
            ('pr = "x"\n', "pr: must be a table"),
        ],
    )
    def test_invalid_settings(self, body: str, message: str):
        with pytest.raises(StateError, match=message):
            State.parse(self.BASE + body, running="0.1.0")


def test_invalid_toml_is_an_error():
    with pytest.raises(StateError, match=r"\.swerepo\.toml: not valid TOML"):
        State.parse("standard = \n")


def test_setters_validate():
    state = State.new()
    with pytest.raises(StateError, match="unknown component"):
        state.set_components(["everything"])
    with pytest.raises(StateError, match="mode"):
        state.set_mode("pair")
    with pytest.raises(StateError, match="not a fingerprint"):
        state.set_file("a.md", Record("docs/a@1", "x", HASH_A))
    with pytest.raises(StateError, match="must be relative"):
        state.set_block("/abs.md", Record("docs/a@1", HASH_A, HASH_A))
