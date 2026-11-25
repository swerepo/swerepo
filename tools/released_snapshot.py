"""Write `tests/released/<version>.json`: the fingerprints of every render put together in code, for a fixed set of
inputs that covers each branch (ADR-20261124-41e9 rule 2). The release PR runs it once:

    uv run python tools/released_snapshot.py

A locked rule then checks that today's code still produces each fingerprint, and that a released SWERepo has its
snapshot. This repository's own tool: `tools/` never ships in the package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import swerepo
from swerepo import ci, github, rebuild
from swerepo.render import TemplateStore

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "tests" / "released"
PROJECT = ci.Project("services/api", "uv sync --locked", ["3.12", "3.13", "3.14"], "ruff")
KEPT_PROJECT = ci.Project("tools/cli", "uv sync", ["3.13", "3.14"], "kept", ["black", "flake8"])


def _workflows() -> list[ci.Inputs]:
    """One base case, then each branch of the workflow changed on its own, then all of them together."""
    base = ci.Inputs("main", "uv sync --locked", ["3.11", "3.12", "3.13", "3.14"], "ruff")
    return [
        base,
        ci.Inputs("develop", "uv sync", ["3.13"], "ruff"),
        ci.Inputs("main", "uv sync --locked", base.python, "kept", ["black", "isort", "flake8", "pylint"]),
        ci.Inputs("main", "uv sync --locked", base.python, "gradual"),
        ci.Inputs("main", "uv sync --locked", base.python, "ruff", swerepo="uvx swerepo==0.1.0"),
        ci.Inputs("main", "uv sync --locked", base.python, "ruff", seamspec="0.2.0"),
        ci.Inputs("main", "uv sync --locked", base.python, "ruff", projects=[PROJECT, KEPT_PROJECT]),
        ci.Inputs("main", "uv sync --locked", base.python, "ruff", copilot_review=True),
        ci.Inputs("main", "uv sync", base.python, "gradual", swerepo="uvx swerepo==0.1.0", projects=[PROJECT],
                  copilot_review=True),
    ]  # fmt: skip


def _settings() -> list[github.Settings]:
    return [
        github.Settings(mode, owner, copilot)
        for mode in ("solo", "team")
        for owner in (None, "@owner", "@org/team")
        for copilot in (True, False)
    ] + [
        github.Settings("team", "@owner", True, ("lint (web)", "test, macOS"), ("squash", "merge")),
        github.Settings("solo", None, False, (), ("merge", "rebase")),  # no squash, and rebase (review P8-F03)
    ]


def _inputs(template_id: str) -> list[dict[str, str]]:
    """The input sets one template id is rendered with."""
    if template_id.startswith(ci.WORKFLOW + "@"):
        return [rebuild.workflow_inputs(inputs) for inputs in _workflows()]
    if template_id.startswith(ci.PYPROJECT + "@"):
        return [
            rebuild.settings_block_inputs(ruff=ruff, pytest=pytest, ruff_line_length=length)
            for ruff in (True, False)
            for pytest in (True, False)
            for length in ((None, "100") if ruff else (None,))  # a line length is ruff's setting
            if ruff or pytest  # neither: no block at all
        ]
    return [rebuild.github_inputs(settings) for settings in _settings()]


def assembled_ids(store: TemplateStore) -> list[str]:
    """Template ids whose render is put together in code: the `github` builders, every `ci/workflow` and
    `ci/pyproject` version."""
    ids = set(github.BUILDERS)
    for family in (ci.WORKFLOW, ci.PYPROJECT):
        component, name = family.split("/")
        ids |= {f"{family}@{v}" for v in store.versions(component, name)}
    return sorted(ids)


def snapshot(version: str, store: TemplateStore | None = None) -> dict:
    store = store or TemplateStore()
    renders = []
    for template_id in assembled_ids(store):
        for inputs in _inputs(template_id):
            text = rebuild.rebuild(store, template_id, inputs)
            if text is None:
                continue  # inputs this version doesn't take
            # every input set is kept, also when it renders what another does: which inputs leave the render
            # unchanged is part of what was released (a code owner in solo mode, Copilot off; review P8-F03)
            fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
            renders.append({"template": template_id, "inputs": inputs, "fingerprint": fingerprint})
    return {"version": version, "renders": renders}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", default=swerepo.__version__, help="the release (default: this SWERepo's)")
    args = parser.parse_args(argv)
    if not ci.released(args.version):
        print(f"{args.version} isn't a release: a snapshot is written for a released version only", file=sys.stderr)
        return 2
    path = FOLDER / f"{args.version}.json"
    if path.exists():
        print(f"{path.relative_to(ROOT)} exists: a released snapshot never changes", file=sys.stderr)
        return 1
    FOLDER.mkdir(parents=True, exist_ok=True)
    data = snapshot(args.version)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {path.relative_to(ROOT)}: {len(data['renders'])} renders.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
