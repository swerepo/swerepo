"""Path globs as git and uv read them (review P4-F05, P4-F10, P4-F11).

`*` and `?` stay within one folder, `**` spans any number of folders (none included), and `[...]` is a
character class. Matching walks the path one folder at a time through the glob's parts, so its time grows with
the path's length times the glob's, never exponentially, and it never touches the file system. Empty and `.`
parts are dropped (`docs//x` and `docs/./x` are `docs/x`); a pattern that is empty after that matches nothing.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Glob:
    text: str
    parts: tuple[str, ...] = field(init=False)
    segments: tuple[re.Pattern[str] | None, ...] = field(init=False)  # None for `**`

    def __post_init__(self) -> None:
        parts: list[str] = []
        for part in self.text.replace("\\", "/").split("/"):
            if part in ("", "."):
                continue
            if part == "**" and parts and parts[-1] == "**":
                continue  # `**/**` is `**`
            parts.append(part)
        object.__setattr__(self, "parts", tuple(parts))
        # one folder name each: fnmatch's own translation (atomic, so no backtracking), never across a `/`
        segments = tuple(None if p == "**" else re.compile(fnmatch.translate(p)) for p in parts)
        object.__setattr__(self, "segments", segments)

    def _closure(self, states: set[int]) -> set[int]:
        done = set(states)
        for state in sorted(states):
            while state < len(self.parts) and self.parts[state] == "**":
                state += 1
                done.add(state)
        return done

    def matches(self, path: str, *, contents: bool = False) -> bool:
        """Whether `path` (repository-relative, `/`-separated) matches. `contents`: a glob naming a folder also
        matches everything inside it, as `[privacy] allow_paths` reads it."""
        if not self.parts:
            return False
        end = len(self.parts)
        states = self._closure({0})
        for name in [p for p in path.split("/") if p not in ("", ".")]:
            if contents and end in states:
                return True
            moved: set[int] = set()
            for state in states:
                if state == end:
                    continue
                pattern = self.segments[state]
                if pattern is None:
                    moved.add(state)  # `**` takes this folder and stays
                elif pattern.fullmatch(name):
                    moved.add(state + 1)
            states = self._closure(moved)
            if not states:
                return False
        return end in states


def compile_all(globs: list[str]) -> list[Glob]:
    return [Glob(text) for text in globs if isinstance(text, str)]
