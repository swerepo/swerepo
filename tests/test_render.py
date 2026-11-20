from pathlib import Path

import pytest

from swerepo.render import TemplateError, TemplateStore, parse_id, render


@pytest.fixture
def store(tmp_path: Path) -> TemplateStore:
    (tmp_path / "docs" / "adr-template").mkdir(parents=True)
    (tmp_path / "docs" / "adr-template" / "1.md").write_text("# ADR for @@project@@\n", encoding="utf-8")
    second = "# @@project@@ ADR\nStatus: @@status@@\n"
    (tmp_path / "docs" / "adr-template" / "2.md").write_text(second, encoding="utf-8")
    (tmp_path / "docs" / "adr-template" / "notes.md").write_text("not a version\n", encoding="utf-8")
    (tmp_path / "docs" / "README.md").write_text("not a template\n", encoding="utf-8")
    (tmp_path / "github" / "codeowners").mkdir(parents=True)
    (tmp_path / "github" / "codeowners" / "1").write_text("@@owner@@\n", encoding="utf-8")
    return TemplateStore(tmp_path)


class TestRender:
    def test_replaces_every_placeholder(self):
        assert render("@@a@@ and @@b@@ and @@a@@", {"a": "1", "b": "2"}) == "1 and 2 and 1"

    def test_extra_values_are_ignored(self):
        assert render("@@a@@", {"a": "1", "unused": "x"}) == "1"

    def test_a_missing_value_is_an_error_naming_it(self):
        with pytest.raises(TemplateError, match=r"ci/python@1: no value for @@matrix@@, @@name@@"):
            render("@@name@@ @@matrix@@", {}, template_id="ci/python@1")

    def test_values_must_be_text(self):
        with pytest.raises(TemplateError, match=r"@@versions@@ must be text, not list"):
            render("@@versions@@", {"versions": ["3.11", "3.12"]})  # type: ignore[dict-item]

    @pytest.mark.parametrize(
        "text",
        [
            "if: ${{ github.event_name == 'push' }}",  # GitHub expression
            "[[tool.uv.index]]",  # TOML array of tables
            "{{ jinja }} and $SHELL_VAR and ${BRACED}",
            "a @@ b @@",  # @@ without a valid name
            "@@Upper@@ @@1digit@@",  # names must be lower-case and start with a letter
        ],
    )
    def test_other_syntax_is_left_alone(self, text):
        assert render(text, {}) == text

    def test_values_are_not_rendered_again(self):
        assert render("@@a@@", {"a": "@@b@@", "b": "x"}) == "@@b@@"


class TestIds:
    def test_parse(self):
        assert parse_id("docs/adr-template@12") == ("docs", "adr-template", 12)

    @pytest.mark.parametrize(
        "bad", ["docs/adr-template", "docs/adr-template@0", "Docs/x@1", "docs/x@1.0", "x@1", "docs/x/y@1"]
    )
    def test_malformed_ids_are_errors(self, bad):
        with pytest.raises(TemplateError, match="not a template id"):
            parse_id(bad)


class TestStore:
    def test_get_a_version(self, store):
        template = store.get("docs/adr-template@1")
        assert (template.component, template.name, template.version) == ("docs", "adr-template", 1)
        assert template.render({"project": "invoices"}) == "# ADR for invoices\n"

    def test_versions_oldest_first_and_latest(self, store):
        assert store.versions("docs", "adr-template") == [1, 2]
        assert store.latest("docs", "adr-template").id == "docs/adr-template@2"

    def test_old_versions_stay_available(self, store):
        assert store.get("docs/adr-template@1").text != store.get("docs/adr-template@2").text

    def test_placeholders(self, store):
        assert store.get("docs/adr-template@2").placeholders == {"project", "status"}

    def test_a_template_without_an_extension(self, store):
        assert store.get("github/codeowners@1").render({"owner": "@team"}) == "@team\n"

    def test_files_not_named_by_a_version_are_ignored(self, store):
        assert store.versions("docs", "README") == []
        assert store.versions("docs", "adr-template") == [1, 2]  # notes.md isn't a version

    def test_missing_templates_are_errors(self, store):
        with pytest.raises(TemplateError, match="no template docs/adr-template@3"):
            store.get("docs/adr-template@3")
        with pytest.raises(TemplateError, match="no template ci/python"):
            store.latest("ci", "python")

    def test_two_files_for_one_version_are_ambiguous(self, store, tmp_path):
        (tmp_path / "docs" / "adr-template" / "1.txt").write_text("other\n", encoding="utf-8")
        with pytest.raises(TemplateError, match=r"ambiguous: 1\.md, 1\.txt"):
            store.get("docs/adr-template@1")
        assert store.versions("docs", "adr-template") == [1, 2]

    def test_the_package_store_is_the_bundled_folder(self):
        store = TemplateStore()
        assert store.root.is_dir()
        assert (store.root / "README.md").is_file()
        assert store.versions("docs", "README") == []
