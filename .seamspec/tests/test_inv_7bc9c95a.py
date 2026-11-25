"""Rule (ADR-20261124-41e9 rule 2, ADR-20261120-b25a): what a release shipped never changes. Every file under
`swerepo/templates/` and `tests/released/` at every `v*` tag (versions read with `packaging`, oldest first) still exists
with the same content. Every snapshot in `tests/released/` (the fingerprints of renders put together in code, for a
fixed set of inputs) still matches what `rebuild.rebuild` produces today, tags or not. And a released SWERepo has its
own snapshot, covering every template id assembled in code: the `github` builders and every `ci/workflow` and
`ci/pyproject` version. A shallow clone fails (tags may be missing); a copy of the files without git passes the tag
part and says so. Its own self-check runs the tag comparison on a temporary git repository, so the core of the rule is
exercised before the first release; so does the snapshot requirement, on a temporary folder."""

import hashlib
import json
import subprocess
import tomllib
import warnings
from pathlib import Path

import pytest
from packaging.version import InvalidVersion, Version

import swerepo
from swerepo import ci, github, rebuild
from swerepo.render import TemplateStore

# The repository root holds .seamspec/config.toml, wherever SeamSpec keeps this file.
ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".seamspec" / "config.toml").is_file())
RELEASED = ("swerepo/templates", "tests/released")
SNAPSHOTS = ROOT / "tests" / "released"


GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
       "-c", "user.name=t", "-c", "user.email=t@example.com"]  # fmt: skip


def _git(root: Path, *args: str, stdin: str | None = None) -> str:
    done = subprocess.run([*GIT, "-C", str(root), *args], input=stdin, capture_output=True, text=True, check=True)
    return done.stdout


def _tags(names: list[str]) -> list[str]:
    """The `v*` tags that name a version, oldest first."""
    versions = []
    for name in names:
        try:
            versions.append((Version(name[1:]), name))
        except InvalidVersion:
            continue
    return [name for _, name in sorted(versions)]


def _real_file(root: Path, path: str) -> bool:
    """Whether `path` is a file of the repository itself: no link on the way to it, its own name included."""
    full = root / path
    hops = [full, *full.relative_to(root).parents]
    return full.is_file() and not any((root / hop).is_symlink() for hop in hops if str(hop) != ".")


def _changed_since(root: Path, tag: str) -> list[str]:
    """Files under RELEASED at `tag` that are gone or different in the working tree of `root`."""
    blobs = {}
    for line in _git(root, "ls-tree", "-r", tag, "--", *RELEASED).splitlines():
        meta, path = line.split("\t", 1)
        blobs[path] = meta.split()[2]
    # a released file replaced by a link, or reached through a linked folder, counts as changed, whatever the link
    # leads to (P8-F05, SeamSpec's reviewer)
    gone = sorted(p for p in blobs if not _real_file(root, p))
    present = sorted(p for p in blobs if p not in gone)
    # hashed as git would store them (line-ending filters applied), so a checkout's own line endings don't count
    now = _git(root, "hash-object", "--stdin-paths", stdin="\n".join(present) + "\n").split() if present else []
    return gone + [p for p, blob in zip(present, now, strict=True) if blobs[p] != blob]


def _assembled_ids(store: TemplateStore) -> set[str]:
    """Template ids whose render is put together in code rather than read from one file."""
    ids = set(github.BUILDERS)
    for family in (ci.WORKFLOW, ci.PYPROJECT):
        component, name = family.split("/")
        ids |= {f"{family}@{v}" for v in store.versions(component, name)}
    return ids


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _snapshot_problems(snapshot: dict, store: TemplateStore) -> list[str]:
    """Where today's renders differ from a snapshot's."""
    problems = []
    for entry in snapshot["renders"]:
        text = rebuild.rebuild(store, entry["template"], entry["inputs"])
        if text is None or _fingerprint(text) != entry["fingerprint"]:
            problems.append(f"{entry['template']} renders differently from {snapshot['version']}'s snapshot")
    return problems


def _tag_problems(root: Path) -> list[str] | None:
    """What changed since each release tag in the repository at `root`; None when there is no git to ask."""
    if not (root / ".git").exists():  # a file in a worktree, a folder otherwise
        return None
    if _git(root, "rev-parse", "--is-shallow-repository").strip() != "false":
        return ["a shallow clone may miss release tags"]
    problems = []
    for tag in _tags(_git(root, "tag", "--list", "v*").split()):
        problems += [f"{path}: changed since {tag}" for path in _changed_since(root, tag)]
    return problems


def _check_tags(root: Path) -> list[str]:
    """`_tag_problems`, warning instead when there is no git to compare with."""
    problems = _tag_problems(root)
    if problems is None:
        warnings.warn("no git here: the released files can't be compared with their tags", stacklevel=2)
        return []
    return problems


def test_released_files_never_change():
    assert _check_tags(ROOT) == [], "a released file needs a new version instead"


def test_released_renders_never_change():
    store = TemplateStore()
    problems = []
    for path in sorted(SNAPSHOTS.glob("*.json")):
        problems += _snapshot_problems(json.loads(path.read_text(encoding="utf-8")), store)
    assert problems == [], "the code that builds a released render changed: add a new template version instead"


def _versions() -> set[str]:
    """This SWERepo's version: as installed, and as `pyproject.toml` says it, which a bump changes first (P8-F05)."""
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    return {swerepo.__version__, str(declared)}


def _snapshot_requirement(folder: Path, versions: set[str], ids: set[str]) -> list[str]:
    """What a release lacks: for each released version, its snapshot in `folder`, covering every id in `ids`."""
    problems = []
    for version in sorted(v for v in versions if ci.released(v)):  # nothing to snapshot before a release
        path = folder / f"{version}.json"
        if not path.is_file():
            problems.append(f"tests/released/{version}.json missing: run tools/released_snapshot.py")
            continue
        covered = {entry["template"] for entry in json.loads(path.read_text(encoding="utf-8"))["renders"]}
        problems += [f"tests/released/{version}.json doesn't cover {t}" for t in sorted(ids - covered)]
    return problems


def test_a_release_has_its_snapshot():
    assert _snapshot_requirement(SNAPSHOTS, _versions(), _assembled_ids(TemplateStore())) == []


def test_the_tag_comparison_catches_what_it_guards(tmp_path: Path):
    """The rule's core, on a temporary repository: a released file changed, deleted or replaced by a link is reported
    against its tag; a new file isn't; a shallow clone fails; a worktree counts as git; no git is None."""
    repo = tmp_path / "repo"
    assert _tag_problems(tmp_path) is None  # no git at all
    folder = repo / "swerepo" / "templates" / "docs"
    folder.mkdir(parents=True)
    for name in ("a", "b", "c"):
        (folder / f"{name}.md").write_text(f"# {name}\n")
    (repo / "tests" / "released").mkdir(parents=True)
    (repo / "tests" / "released" / "0.1.0.json").write_text('{"version": "0.1.0", "renders": []}\n')
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "release")
    _git(repo, "tag", "v0.1.0")
    _git(repo, "tag", "vnext")  # not a version: ignored
    assert _tag_problems(repo) == []
    shallow = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth", "1", repo.as_uri(), str(shallow))
    assert _tag_problems(shallow) == ["a shallow clone may miss release tags"]
    worktree = tmp_path / "worktree"
    _git(repo, "worktree", "add", "-q", str(worktree), "v0.1.0")
    assert (worktree / ".git").is_file() and _tag_problems(worktree) == []
    (folder / "new.md").write_text("# new\n")  # added after the release: fine
    (folder / "a.md").write_text("# a, changed\n")
    (folder / "b.md").unlink()
    (tmp_path / "c-copy.md").write_text("# c\n")
    (folder / "c.md").unlink()
    (folder / "c.md").symlink_to(tmp_path / "c-copy.md")  # the same text, but a link
    (repo / "tests" / "released" / "0.1.0.json").write_text("{}\n")  # a snapshot is released too
    assert _tag_problems(repo) == [
        "swerepo/templates/docs/b.md: changed since v0.1.0",
        "swerepo/templates/docs/c.md: changed since v0.1.0",
        "swerepo/templates/docs/a.md: changed since v0.1.0",
        "tests/released/0.1.0.json: changed since v0.1.0",
    ]
    linked = tmp_path / "linked"  # a whole folder of the released files, replaced by a link to the same files
    _git(tmp_path, "clone", "-q", repo.as_uri(), str(linked))
    templates = linked / "swerepo" / "templates"
    templates.rename(tmp_path / "templates-copy")
    templates.symlink_to(tmp_path / "templates-copy", target_is_directory=True)
    assert _tag_problems(linked) == [
        "swerepo/templates/docs/a.md: changed since v0.1.0",
        "swerepo/templates/docs/b.md: changed since v0.1.0",
        "swerepo/templates/docs/c.md: changed since v0.1.0",
    ]
    with pytest.warns(UserWarning, match="no git here"):  # a copy without git says it couldn't look
        assert _check_tags(tmp_path / "templates-copy") == []


def test_the_snapshot_requirement_catches_what_it_guards(tmp_path: Path):
    assert ci.released("0.1.0") and ci.released("1.2.3") and not ci.released("0.1.0.dev0")
    ids = {"github/ruleset@1", "ci/workflow@2"}
    assert _snapshot_requirement(tmp_path, {"0.1.0.dev0"}, ids) == []  # before a release: nothing needed
    assert _snapshot_requirement(tmp_path, {"0.1.0.dev0", "0.1.0"}, ids) == [
        "tests/released/0.1.0.json missing: run tools/released_snapshot.py"
    ]
    (tmp_path / "0.1.0.json").write_text(json.dumps({"renders": [{"template": "github/ruleset@1"}]}))
    assert _snapshot_requirement(tmp_path, {"0.1.0"}, ids) == ["tests/released/0.1.0.json doesn't cover ci/workflow@2"]
    renders = [{"template": "github/ruleset@1"}, {"template": "ci/workflow@2"}]
    (tmp_path / "0.1.0.json").write_text(json.dumps({"renders": renders}))
    assert _snapshot_requirement(tmp_path, {"0.1.0"}, ids) == []


def test_the_helpers_read_what_they_should():
    assert _tags(["v0.10.0", "v0.2.0", "v1.0.0rc1", "vnext", "v0.9.0"]) == ["v0.2.0", "v0.9.0", "v0.10.0", "v1.0.0rc1"]
    store = TemplateStore()
    assert {"github/ruleset@1", "github/repo-settings@1", "ci/pyproject@1", "ci/workflow@1"} <= _assembled_ids(store)
    inputs = rebuild.github_inputs(github.Settings("solo", "@dev"))
    good = {"template": "github/ruleset@1", "inputs": inputs}
    good["fingerprint"] = _fingerprint(rebuild.rebuild(store, "github/ruleset@1", inputs) or "")
    assert _snapshot_problems({"version": "9.9.9", "renders": [good]}, store) == []
    stale = {**good, "fingerprint": "0" * 64}
    assert _snapshot_problems({"version": "9.9.9", "renders": [stale]}, store) == [
        "github/ruleset@1 renders differently from 9.9.9's snapshot"
    ]
