"""Finding the project's spec (SWEREPO-SPEC §6.7, §14; ADR-20261124-4d76 point 2).

`init`, `update` and `check` look the same way:

1. `[adopted] spec`, when set, is the spec; nothing is looked for.
2. Otherwise the candidates are the root `SPEC.md`, `docs/SPEC.md` and any root `<NAME>-SPEC.md`, whatever their case;
   `docs/EARNED_SPEC.md` never counts. Files are listed as detection lists them: through git where it can, so a file
   git ignores is never a candidate (ADR-20261120-25b5), and only files that stay inside the repository count, links
   included (review P8-F01).
3. None: `docs` writes the starter `SPEC.md`, and nothing is recorded.
4. One: exactly `SPEC.md` at the root is the default, with nothing recorded; any other is recorded as `[adopted] spec`.
5. Several: none is guessed. They are listed, and the person records one.

Read-only: it lists files and never reads one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from swerepo.blocks import inside
from swerepo.detect import list_files

DEFAULT = "SPEC.md"
EARNED = "docs/EARNED_SPEC.md"  # SeamSpec's enforced rules, never the spec
_SUFFIX = "-spec.md"


@dataclass(frozen=True)
class Found:
    """What the lookup found. `path`: the spec, when there is one to follow (it may be missing when adopted).
    `adopt`: a path to record as `[adopted] spec`. `several`: the candidates, when there is more than one."""

    path: str | None
    adopt: str | None = None
    several: tuple[str, ...] = ()
    adopted: bool = False  # `[adopted] spec` named it

    @property
    def name(self) -> str:
        """The spec as templates name it: the one followed, else `SPEC.md`."""
        return self.path or DEFAULT


def _is_candidate(path: str) -> bool:
    folder, _, name = path.rpartition("/")
    lower = name.lower()
    if folder == "":
        return lower == "spec.md" or (lower.endswith(_SUFFIX) and len(lower) > len(_SUFFIX))
    return folder == "docs" and lower == "spec.md"


def within(root: Path, path: str) -> bool:
    """Whether `path` is a file that stays inside the repository at `root`, after following links."""
    full = root.resolve() / path
    return full.is_file() and inside(root.resolve(), full)


def candidates(root: Path, files: list[str] | None = None) -> list[str]:
    """The files that could be the spec, repository-relative, in a stable order. `files`: the repository's files as
    detection lists them (listed here when not given)."""
    listed = list_files(root) if files is None else files
    found = [path for path in listed if _is_candidate(path) and path.lower() != EARNED.lower()]
    return sorted(path for path in found if within(root, path))


def find(root: Path, adopted: object = None, files: list[str] | None = None) -> Found:
    """The spec of the repository at `root`, given `[adopted] spec` (None when unset)."""
    if isinstance(adopted, str) and adopted:
        return Found(adopted, adopted=True)
    found = candidates(root, files)
    if not found:
        return Found(None)
    if len(found) > 1:
        return Found(None, several=tuple(found))
    only = found[0]
    return Found(only, adopt=None if only == DEFAULT else only)


def how_to_choose(several: tuple[str, ...]) -> str:
    """The plan's and `check`'s words when there are several candidates."""
    listed = ", ".join(several)
    return f"several specs ({listed}): record the one to follow as `spec` under `[adopted]` in .swerepo.toml"
