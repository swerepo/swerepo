"""Rebuilding what SWERepo rendered from a record's inputs (ADR-20261124-7afa points 3 and 10).

Every record keeps the inputs its render used: the values a plain template's placeholders took, or, for a file
built in code, the few settings it was built from. `rebuild` turns a template id and those inputs back into the
exact text, so `update` can three-way merge against it and `check` can compare with it. Callers trust a rebuild
only when its fingerprint equals the record's `rendered`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from swerepo import ci, github
from swerepo.render import Template, TemplateError, TemplateStore, parse_id


def used(template: Template, values: Mapping[str, Any]) -> dict[str, str]:
    """The values a plain template's render used: its placeholders, nothing more."""
    return {name: str(values[name]) for name in sorted(template.placeholders) if name in values}


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _listed(text: str) -> list[str]:
    return [part for part in text.split(",") if part]


def workflow_inputs(inputs: ci.Inputs) -> dict[str, str]:
    """`swerepo-ci.yml`'s inputs, as text."""
    projects = [{"folder": project.folder, **project.inputs} for project in inputs.projects]
    return {
        "default_branch": inputs.default_branch,
        "install": inputs.install,
        "python": ",".join(inputs.python),
        "lint": inputs.lint,
        "linters": ",".join(inputs.linters),
        "swerepo": inputs.swerepo,
        "seamspec": inputs.seamspec,
        "copilot_review": _flag(inputs.copilot_review),
        "projects": json.dumps(projects, sort_keys=True, separators=(",", ":")),
    }


def workflow_from(inputs: Mapping[str, str]) -> ci.Inputs:
    projects = []
    for entry in json.loads(inputs["projects"]):
        project = ci.Project.from_inputs(str(entry["folder"]), entry)
        if project is None:
            raise ValueError("a project's inputs aren't ones standard 1 writes")
        projects.append(project)
    python = _listed(inputs["python"])
    if not python:  # no Python version: there is no matrix to rebuild (PR #18 review)
        raise ValueError("a workflow's inputs name no Python version")
    return ci.Inputs(
        inputs["default_branch"], inputs["install"], python, inputs["lint"],
        _listed(inputs["linters"]), inputs["swerepo"], inputs["seamspec"], projects,
        inputs["copilot_review"] == "true",
    )  # fmt: skip


def settings_block_inputs(*, ruff: bool, pytest: bool, ruff_line_length: str | None) -> dict[str, str]:
    """The pyproject.toml settings block's inputs, as text."""
    return {"ruff": _flag(ruff), "pytest": _flag(pytest), "ruff_line_length": ruff_line_length or ""}


def github_inputs(settings: github.Settings) -> dict[str, str]:
    """The ruleset's and the merge settings' inputs, as text."""
    return {
        "mode": settings.mode,
        "code_owner": settings.code_owner or "",
        "copilot_review": _flag(settings.copilot_review),
        "extra_checks": json.dumps(list(settings.extra_checks), separators=(",", ":")),  # names hold commas (P6-F05)
        "merge_methods": ",".join(settings.merge_methods),
    }


def _checks(text: str) -> list[str]:
    """Extra required checks: a JSON list; a plain comma-separated list as recorded before P6-F05."""
    if not text.startswith("["):
        return _listed(text)
    found = json.loads(text)
    if not isinstance(found, list) or not all(isinstance(name, str) for name in found):
        raise ValueError("extra_checks isn't a list of names")
    return found


def _github_from(inputs: Mapping[str, str]) -> github.Settings:
    return github.Settings(
        inputs["mode"], inputs["code_owner"] or None, inputs["copilot_review"] == "true",
        tuple(_checks(inputs["extra_checks"])), tuple(_listed(inputs["merge_methods"])),
    )  # fmt: skip


def rebuild(store: TemplateStore, template_id: str, inputs: Mapping[str, str]) -> str | None:
    """The text `template_id` renders from `inputs`, or None when it can't be rebuilt: an unknown template or
    builder, or inputs it doesn't take. A block's content for a block, the whole file for a file."""
    try:
        component, name, version = parse_id(template_id)
        family = f"{component}/{name}"
        if family == ci.WORKFLOW:
            return ci.render_workflow(store, workflow_from(inputs), version)[1]
        if family == ci.PYPROJECT:
            block = ci.settings_block(
                store, ruff=inputs["ruff"] == "true", pytest=inputs["pytest"] == "true",
                ruff_line_length=inputs["ruff_line_length"] or None, version=version,
            )  # fmt: skip
            return block[1] if block else None
        if github.is_builder(template_id):
            return github.render(name, _github_from(inputs), template_id)[1]
        return store.get(template_id).render(inputs)
    except (TemplateError, KeyError, ValueError, TypeError):
        return None
