"""Rule (ADR-20261124-41e9 rule 1, ADR-20261124-152d): the shipped package carries no publishing footprint. The wheel
and the sdist, both published and both built through the build backend's PEP 517 hooks (`uv_build`, which runs this
environment's own `uv-build`; no network), hold nothing outside `swerepo/` but their metadata: the wheel's `.dist-info`,
and the sdist's `PKG-INFO`, `pyproject.toml`, `README.md` and `LICENSE`. No file under `swerepo/` names a publishing
tool or endpoint, and `swerepo` offers no `release` component or flag. A package that can't be built fails the rule."""

import os
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import uv_build
from typer.testing import CliRunner

from swerepo.cli import app
from swerepo.state import COMPONENTS, State

# The repository root holds .seamspec/config.toml, wherever SeamSpec keeps this file.
ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".seamspec" / "config.toml").is_file())
SDIST_METADATA = {"PKG-INFO", "pyproject.toml", "README.md", "LICENSE"}  # what an sdist carries besides the code
PUBLISHING = ("gh-action-pypi-publish", "uv publish", "twine upload", "poetry publish", "hatch publish",
              "flit publish", "upload.pypi.org")  # fmt: skip


def _build(hook, out: Path) -> Path:
    """Build from ROOT with a PEP 517 hook of `uv_build`, the way pip or uv would. `uv_build` finds its `uv-build` on
    PATH, so this environment's own scripts folder goes first, also when the environment isn't activated (P8-F04)."""
    here, path = os.getcwd(), os.environ.get("PATH")
    os.chdir(ROOT)
    os.environ["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), *([path] if path else [])])
    try:
        return out / hook(str(out))
    finally:
        os.chdir(here)
        if path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = path


def _wheel(out: Path) -> list[str]:
    """The names inside the wheel built from ROOT."""
    with zipfile.ZipFile(_build(uv_build.build_wheel, out)) as wheel:
        return wheel.namelist()


def _sdist_names(archive: Path) -> list[str]:
    """The files inside an sdist, below its top folder (`<name>-<version>/`, named like the archive). Anything else in
    the archive is kept as it is named there, prefixed with `../`, so it shows as outside rather than being dropped."""
    top = archive.name.removesuffix(".tar.gz") + "/"
    with tarfile.open(archive) as sdist:
        names = [m.name for m in sdist.getmembers() if not m.isdir()]
    return [n[len(top) :] if n.startswith(top) else f"../{n}" for n in names]


def _sdist(out: Path) -> list[str]:
    """The files inside the sdist built from ROOT."""
    return _sdist_names(_build(uv_build.build_sdist, out))


def _outside(names: list[str]) -> list[str]:
    """The files of a wheel that would land outside the `swerepo` package."""
    return [n for n in names if not n.startswith("swerepo/") and not n.split("/", 1)[0].endswith(".dist-info")]


def _sdist_outside(names: list[str]) -> list[str]:
    """The files of an sdist, below its top folder, that are neither the package nor its metadata."""
    return [n for n in names if not n.startswith("swerepo/") and n not in SDIST_METADATA]


def _publishing(folder: Path) -> list[str]:
    """`file: tool` for every file in `folder` that names a publishing tool or endpoint."""
    found = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        text = path.read_bytes().decode("utf-8", errors="replace")
        found += [f"{path.relative_to(folder).as_posix()}: {tool}" for tool in PUBLISHING if tool in text]
    return found


def test_the_release_builds_with_uv_build():
    """The packages this rule checks are the ones a release builds: `uv build` uses the backend pyproject.toml names."""
    system = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["build-system"]
    assert system["build-backend"] == "uv_build"
    assert any(req.replace(" ", "").startswith("uv_build") for req in system["requires"])


def test_the_wheel_holds_only_the_package(tmp_path: Path):
    names = _wheel(tmp_path)
    assert any(n.startswith("swerepo/") for n in names) and any(".dist-info/" in n for n in names)
    assert _outside(names) == []


def test_the_sdist_holds_only_the_package_and_its_metadata(tmp_path: Path):
    names = _sdist(tmp_path)
    assert any(n.startswith("swerepo/") for n in names) and "PKG-INFO" in names
    assert _sdist_outside(names) == []


def test_the_package_names_no_publishing_tool():
    assert _publishing(ROOT / "swerepo") == []


def test_there_is_no_release_component_or_flag(tmp_path: Path):
    assert "release" not in COMPONENTS
    runner = CliRunner()
    set_up = tmp_path / "set-up"  # update reads its state before the component names, so it gets one
    set_up.mkdir()
    state = State.new()
    state.set_components(["docs"])
    state.save(set_up)
    for command in ("init", "check", "update"):
        folder = set_up if command == "update" else tmp_path
        shown = runner.invoke(app, [command, "--help"])
        assert shown.exit_code == 0 and "--path" in shown.output, command  # the help really printed
        assert "--release" not in shown.output and "--no-release" not in shown.output, command
        for args in (["--only", "release"], ["--no-release"], ["--release"]):
            dry = ["--dry-run"] if command != "check" else []  # check writes nothing and has no --dry-run
            refused = runner.invoke(app, [command, "--path", str(folder), *args, *dry])
            reason = refused.output.lower()  # refused because `release` is unknown, not for another reason
            assert refused.exit_code == 2 and "release" in reason and "unknown" in reason, (command, args)
    for command in ("check", "init"):  # the same folder with options that exist: not wrong usage
        for args in ([], ["--only", "docs"], ["--no-docs"]):
            run = [command, "--path", str(tmp_path), *args, *(["--dry-run"] if command == "init" else [])]
            assert runner.invoke(app, run).exit_code in (0, 1), (command, args)


def test_the_checks_catch_what_they_guard(tmp_path: Path):
    assert _outside(["swerepo/cli.py", "swerepo-0.1.0.dist-info/METADATA"]) == []
    assert _outside(["swerepo/cli.py", "tools/release.py", "swerepo-0.1.0.data/scripts/x"]) == [
        "tools/release.py",
        "swerepo-0.1.0.data/scripts/x",
    ]
    assert _sdist_outside(["swerepo/cli.py", "PKG-INFO", "pyproject.toml", "README.md", "LICENSE"]) == []
    archive = tmp_path / "swerepo-9.9.9.tar.gz"
    with tarfile.open(archive, "w:gz") as sdist:
        for name in ("swerepo-9.9.9/swerepo/x.py", "swerepo-9.9.9/PKG-INFO", "stray.txt", "other-1.0/y.py"):
            source = tmp_path / "member"
            source.write_text("x\n")
            sdist.add(source, arcname=name)
    assert _sdist_names(archive) == ["swerepo/x.py", "PKG-INFO", "../stray.txt", "../other-1.0/y.py"]
    assert _sdist_outside(["swerepo/cli.py", ".github/workflows/release.yml", "tests/test_x.py", "../stray.txt"]) == [
        ".github/workflows/release.yml",
        "tests/test_x.py",
        "../stray.txt",
    ]
    sample = tmp_path / "pkg"
    sample.mkdir()
    (sample / "flow.yml").write_text("- uses: pypa/" + "gh-action-pypi-publish@v1\n")
    (sample / "ok.md").write_text("Only the person publishes a package.\n")
    (sample / "run.sh").write_text("uv " + "publish dist/*\n")
    assert _publishing(sample) == ["flow.yml: gh-action-pypi-publish", "run.sh: uv publish"]
