"""Placeholder that reserves the name `swerepo` on PyPI. SWERepo itself isn't released yet."""

import sys

PROJECT_URL = "https://github.com/swerepo/swerepo"


def main() -> None:
    print(
        f"SWERepo isn't released yet: this 0.0.1 package only reserves the name.\nFollow the project at {PROJECT_URL}",
        file=sys.stderr,
    )
    raise SystemExit(1)
