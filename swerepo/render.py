"""Bundled templates and how they are rendered (ADR-20261120-b25a).

A template is a plain file at `templates/<component>/<name>/<version>[.<ext>]`, identified as
`<component>/<name>@<version>`. (No `@` in file names: a name, `@`, a version and an extension reads as an
email address to the locked privacy rule.) Rendering only replaces `@@name@@` placeholders with string values:
templates are data, never code (spec §17).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable

_PART = r"[a-z][a-z0-9-]*"
TEMPLATE_ID = re.compile(rf"^(?P<component>{_PART})/(?P<name>{_PART})@(?P<version>[1-9][0-9]*)$")
_VERSION_FILE = re.compile(r"^(?P<version>[1-9][0-9]*)(?:\.[A-Za-z0-9.]+)?$")
PLACEHOLDER = re.compile(r"@@([a-z][a-z0-9_]*)@@")


class TemplateError(ValueError):
    """A template id is malformed, a template is missing or ambiguous, or a value is missing."""


@dataclass(frozen=True)
class Template:
    id: str
    component: str
    name: str
    version: int
    text: str

    @property
    def placeholders(self) -> frozenset[str]:
        return frozenset(PLACEHOLDER.findall(self.text))

    def render(self, values: Mapping[str, str]) -> str:
        return render(self.text, values, template_id=self.id)


def parse_id(template_id: str) -> tuple[str, str, int]:
    """(component, name, version) from an id such as `docs/adr-template@1`."""
    match = TEMPLATE_ID.fullmatch(template_id)
    if not match:
        raise TemplateError(f"not a template id: {template_id!r} (expected <component>/<name>@<version>)")
    return match["component"], match["name"], int(match["version"])


def render(text: str, values: Mapping[str, str], *, template_id: str = "<text>") -> str:
    """Replace every `@@name@@` with `values[name]`. A missing or non-string value is an error;
    extra values are ignored."""
    missing = sorted({name for name in PLACEHOLDER.findall(text) if name not in values})
    if missing:
        raise TemplateError(f"{template_id}: no value for {', '.join('@@' + n + '@@' for n in missing)}")

    def substitute(match: re.Match[str]) -> str:
        value = values[match[1]]
        if not isinstance(value, str):
            raise TemplateError(f"{template_id}: value for @@{match[1]}@@ must be text, not {type(value).__name__}")
        return value

    return PLACEHOLDER.sub(substitute, text)


class TemplateStore:
    """Templates under a root folder: the package's own by default, or a test's."""

    def __init__(self, root: Traversable | None = None) -> None:
        self.root: Traversable = root if root is not None else files("swerepo") / "templates"

    def _entries(self, component: str, name: str) -> Iterable[Traversable]:
        folder = self.root / component / name
        return folder.iterdir() if folder.is_dir() else ()

    def versions(self, component: str, name: str) -> list[int]:
        """Every version of a template, oldest first."""
        found = []
        for entry in self._entries(component, name):
            match = _VERSION_FILE.fullmatch(entry.name)
            if entry.is_file() and match:
                found.append(int(match["version"]))
        return sorted(set(found))

    def latest(self, component: str, name: str) -> Template:
        versions = self.versions(component, name)
        if not versions:
            raise TemplateError(f"no template {component}/{name}")
        return self.get(f"{component}/{name}@{versions[-1]}")

    def get(self, template_id: str) -> Template:
        component, name, version = parse_id(template_id)
        matches = [
            entry
            for entry in self._entries(component, name)
            if entry.is_file() and (m := _VERSION_FILE.fullmatch(entry.name)) and int(m["version"]) == version
        ]
        if not matches:
            raise TemplateError(f"no template {template_id}")
        if len(matches) > 1:
            names = ", ".join(sorted(entry.name for entry in matches))
            raise TemplateError(f"template {template_id} is ambiguous: {names}")
        text = matches[0].read_text(encoding="utf-8")
        return Template(id=template_id, component=component, name=name, version=version, text=text)
