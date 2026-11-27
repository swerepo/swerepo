"""The commands agents and people run (spec §6.6), kept apart from `init` so `check` can read them too: `init` imports
`check`, so `check` can't import `init` (review P8-K)."""

from __future__ import annotations

import re
from pathlib import Path

from swerepo.detect import Detection


def _make_targets(root: Path) -> set[str]:
    try:
        text = (root / "Makefile").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return set(re.findall(r"^(install|test|lint|check)\s*:", text, re.MULTILINE))


_KEPT_LINT = {"black": "black --check .", "isort": "isort --check-only .", "flake8": "flake8", "pylint": "pylint ."}
TOOLS = frozenset({"pytest", "ruff", *_KEPT_LINT})  # the only tools the commands SWERepo writes run


def commands(
    root: Path, detection: Detection, adopted_linters: list[str] | None = None, lint_mode: str | None = None
) -> dict[str, list[str]]:
    """The commands agents and people run, from what the project uses (spec §6.6): uv by default, poetry
    when it has a poetry.lock, a Makefile's `install`, `test` and `lint` targets when it has them, and the
    linters recorded under `[adopted] linters` (as `check` reads them) before the detected ones. `lint_mode`
    (the `ci` component's choice) decides between ruff and kept linters, the same on every run (P4-F07)."""
    poetry = (root / "poetry.lock").is_file() and not (root / "uv.lock").is_file()
    runner, install = ("poetry run", "poetry install") if poetry else ("uv run", "uv sync")
    linters = set(adopted_linters) if adopted_linters else {linter.name for linter in detection.linters}
    if lint_mode == "gradual":
        files = "--force-exclude <changed .py files>"
        lint = [f"{runner} ruff check {files}", f"{runner} ruff format --check {files}"]
    elif lint_mode == "ruff" or (lint_mode is None and ("ruff" in linters or not linters)):
        lint = [f"{runner} ruff check .", f"{runner} ruff format --check ."]
    else:
        lint = [f"{runner} {_KEPT_LINT[name]}" for name in sorted(linters) if name in _KEPT_LINT]
    targets = _make_targets(root)
    return {
        "install": ["make install" if "install" in targets else install],
        "test": ["make test" if "test" in targets else f"{runner} pytest"],
        "lint": ["make lint"] if "lint" in targets else lint,
        "check": ["swerepo check"],
    }


def uv_run_tools(commands_found: dict[str, list[str]]) -> list[str]:
    """The tools the test and lint commands run through `uv run`, in order, each once: what `uv sync` must install for
    them to run. A Makefile target or Poetry runs its own (review P8-A02)."""
    run = []
    for line in (line for key in ("test", "lint") for line in commands_found[key]):
        words = line.split()
        # only a tool from the fixed set: never a flag, a path or anything else a hand-edited command holds (P8-K09)
        if words[:2] == ["uv", "run"] and len(words) >= 3 and words[2] in TOOLS:
            run.append(words[2])
    return list(dict.fromkeys(run))
