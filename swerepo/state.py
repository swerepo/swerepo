"""`.swerepo.toml`: what SWERepo applied to a repository (spec §9, ADR-20261120-ecf7).

Read and written with tomlkit, so comments, key order and keys this version doesn't know survive.
Validated on load; never saved over a file that a newer SWERepo wrote.
"""

from __future__ import annotations

import datetime
import os
import re
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import tomlkit
from packaging.version import InvalidVersion, Version
from tomlkit.exceptions import TOMLKitError
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument

from swerepo import __version__
from swerepo.fingerprint import is_fingerprint
from swerepo.render import TEMPLATE_ID

FILE_NAME = ".swerepo.toml"
SUPPORTED_STANDARD = 1
COMPONENTS = ("docs", "agents", "ci", "security", "github", "seamspec", "openspec", "release")
MODES = ("solo", "team")
DEFAULT_EXEMPT_AUTHORS = ("dependabot[bot]",)
HEADER = "# Written by SWERepo (SWEREPO-SPEC §9). Commit this file. Settings may be edited; fingerprints may not."


class StateError(ValueError):
    """`.swerepo.toml` is malformed, or can't be saved."""


@dataclass(frozen=True)
class Record:
    """What SWERepo wrote at a path: the template, the template's own output, and what was written."""

    template: str
    rendered: str
    written: str


def check_path(path: object, *, key: str) -> str:
    """A repository-relative POSIX path, written one way only: not empty or `.`, not absolute, no `.` or
    `..` parts, no empty parts (`a//b`), no trailing `/`, no backslashes or control characters."""
    # The rejected value is never repeated: it may be an absolute path naming a home folder, and the
    # message reaches `check` output and CI logs (ADR-20261120-fc5a point 7).
    if not isinstance(path, str) or not path or path.strip() != path or any(ord(c) < 32 for c in path):
        raise StateError(f"{key}: a path is not a repository path")
    if "\\" in path or path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise StateError(f"{key}: a path must be relative and use '/'")
    if any(part in ("", ".", "..") for part in path.split("/")):
        raise StateError(f"{key}: a path must not have empty, '.' or '..' parts, or end with '/'")
    return PurePosixPath(path).as_posix()


def _version(value: str, *, key: str) -> Version:
    try:
        return Version(value)
    except InvalidVersion as error:
        raise StateError(f"{key}: {value!r} is not a version") from error


class State:
    def __init__(self, doc: TOMLDocument, *, running: str = __version__) -> None:
        self.doc = doc
        _validate(doc, running)

    # --- creating, reading, writing --------------------------------------------------------------

    @classmethod
    def new(cls, *, standard: int = SUPPORTED_STANDARD, version: str = __version__) -> State:
        doc = tomlkit.document()
        doc.add(tomlkit.comment(HEADER.removeprefix("# ")))
        doc.add("standard", standard)
        doc.add("swerepo", version)
        doc.add("components", tomlkit.array())
        return cls(doc)

    @classmethod
    def parse(cls, text: str, *, source: str = FILE_NAME, running: str = __version__) -> State:
        try:
            doc = tomlkit.parse(text)
        except TOMLKitError as error:
            raise StateError(f"{source}: not valid TOML: {error}") from error
        try:
            return cls(doc, running=running)
        except StateError as error:
            raise StateError(f"{source}: {error}") from error

    @classmethod
    def load(cls, root: Path, *, running: str = __version__) -> State | None:
        """The state of the repository at `root`, or None if it has no `.swerepo.toml`."""
        path = root / FILE_NAME
        if not path.is_file():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise StateError(f"{FILE_NAME}: can't read it: {_reason(error)}") from error
        return cls.parse(text, source=FILE_NAME, running=running)

    def dumps(self) -> str:
        return tomlkit.dumps(self.doc)

    def written_by_newer(self, running: str = __version__) -> str | None:
        """Why this file must not be saved by the running SWERepo, or None if it may be."""
        return _newer_reason(self.standard, self.swerepo_version, running)

    def save(self, root: Path, *, running: str = __version__) -> Path:
        """Write atomically, recording the running version. Refuses when this state, or the file it would
        replace on disk, was written by a newer SWERepo or in a newer standard (review: Copilot on PR #2)."""
        reason = self.written_by_newer(running)
        if reason:
            raise StateError(f"{FILE_NAME} not saved: {reason}. Upgrade SWERepo.")
        target = root / FILE_NAME
        on_disk = _on_disk_reason(target, running)
        if on_disk:
            raise StateError(f"{FILE_NAME} not saved: {on_disk}")
        self.doc["swerepo"] = running
        mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
        fd, temp_name = tempfile.mkstemp(dir=root, prefix=f"{FILE_NAME}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(self.dumps())
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, mode)
            os.replace(temp_name, target)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
        return target

    # --- reading values --------------------------------------------------------------------------

    @property
    def standard(self) -> int:
        return int(self.doc["standard"])

    @property
    def swerepo_version(self) -> str:
        return str(self.doc["swerepo"])

    @property
    def components(self) -> list[str]:
        return [str(c) for c in self.doc.get("components", [])]

    @property
    def mode(self) -> str | None:
        mode = self.doc.get("mode")
        return None if mode is None else str(mode)

    @property
    def values(self) -> dict[str, Any]:
        table = self.doc.get("values")
        return {} if table is None else table.unwrap()

    @property
    def project_ignore(self) -> list[str]:
        projects = self.doc.get("projects")
        return [] if projects is None else [str(p) for p in projects.get("ignore", [])]

    @property
    def projects_listed(self) -> list[str]:
        """Python projects with their own CI jobs (`[projects] listed`, spec §11)."""
        projects = self.doc.get("projects")
        return [] if projects is None else [str(p) for p in projects.get("listed", [])]

    @property
    def project_inputs(self) -> dict[str, dict[str, Any]]:
        """What each listed project's CI jobs were rendered from (`[projects.inputs."<folder>"]`: python, install,
        lint, linters), so `update` can rebuild them (review: Copilot on PR #8)."""
        projects = self.doc.get("projects")
        inputs = projects.get("inputs") if projects is not None else None
        return {} if inputs is None else {str(k): dict(v) for k, v in inputs.unwrap().items()}

    @property
    def projects_not_covered(self) -> list[str]:
        """Project roots knowingly outside every required check (`[projects] not_covered`, spec §11)."""
        projects = self.doc.get("projects")
        return [] if projects is None else [str(p) for p in projects.get("not_covered", [])]

    @property
    def privacy_allow_paths(self) -> list[str]:
        """Files or globs the privacy scan skips (`[privacy] allow_paths`, spec §6.4)."""
        privacy = self.doc.get("privacy")
        return [] if privacy is None else [str(p) for p in privacy.get("allow_paths", [])]

    @property
    def tools(self) -> dict[str, str]:
        """Versions of other tools the workflows pin (`[tools]`), e.g. `seamspec`."""
        table = self.doc.get("tools")
        return {} if table is None else {str(k): str(v) for k, v in table.unwrap().items()}

    @property
    def components_chosen(self) -> bool:
        """Whether the file records `components`, even as an empty list (then nothing is chosen)."""
        return "components" in self.doc

    @property
    def hosts_chosen(self) -> bool:
        """Whether the file records `[agents] hosts`, even as an empty list (then no editor is chosen)."""
        agents = self.doc.get("agents")
        return agents is not None and "hosts" in agents

    @property
    def hosts(self) -> list[str]:
        """Editors chosen for the `agents` component (`[agents] hosts`), or [] if not recorded."""
        agents = self.doc.get("agents")
        return [] if agents is None else [str(h) for h in agents.get("hosts", [])]

    @property
    def adopted(self) -> dict[str, Any]:
        """Existing conventions SWERepo follows (`[adopted]`): adr_dir, progress_dir, linters."""
        table = self.doc.get("adopted")
        return {} if table is None else table.unwrap()

    @property
    def pr_enforce(self) -> bool:
        """Whether pull-request rules fail `check --ci` (`[pr] enforce`; enforced when absent)."""
        pr = self.doc.get("pr")
        return True if pr is None else bool(pr.get("enforce", True))

    @property
    def exempt_authors(self) -> list[str]:
        pr = self.doc.get("pr")
        if pr is None or "exempt_authors" not in pr:
            return list(DEFAULT_EXEMPT_AUTHORS)
        return [str(a) for a in pr["exempt_authors"]]

    def files(self) -> dict[str, Record]:
        return _records(self.doc.get("files"))

    def blocks(self) -> dict[str, Record]:
        return _records(self.doc.get("blocks"))

    # --- changing values -------------------------------------------------------------------------

    def set_components(self, components: list[str]) -> None:
        _check_components(components, key="components")
        array = tomlkit.array()  # tomlkit.array(x) would parse x as TOML text, not take a list
        array.extend(components)
        self.doc["components"] = array

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise StateError(f"mode: {mode!r} is not one of {', '.join(MODES)}")
        self.doc["mode"] = mode

    def set_value(self, name: str, value: str | list[str]) -> None:
        _check_value(name, value)
        self._table("values")[name] = value

    def set_hosts(self, hosts: list[str]) -> None:
        """Record the editors chosen for the `agents` component (`[agents] hosts`)."""
        _text_list(hosts, key="agents.hosts")
        array = tomlkit.array()
        array.extend(hosts)
        self._table("agents")["hosts"] = array

    def set_adopted(self, name: str, value: str) -> None:
        """Record an existing convention SWERepo follows (`[adopted] adr_dir` or `progress_dir`)."""
        if name not in ("adr_dir", "progress_dir"):
            raise StateError(f"adopted.{name}: not a folder setting")
        self._table("adopted")[name] = check_path(value, key=f"adopted.{name}")

    def set_adopted_linters(self, linters: list[str]) -> None:
        """Record the linters kept instead of ruff (`[adopted] linters`, spec §6.3)."""
        _text_list(linters, key="adopted.linters")
        array = tomlkit.array()
        array.extend(linters)
        self._table("adopted")["linters"] = array

    def set_projects_listed(self, folders: list[str]) -> None:
        """Record the Python projects that have their own CI jobs (`[projects] listed`, spec §11)."""
        _text_list(folders, key="projects.listed")
        array = tomlkit.array()
        array.extend(check_path(folder, key="projects.listed") for folder in folders)
        self._table("projects")["listed"] = array

    def set_project_inputs(self, inputs: dict[str, dict[str, Any]]) -> None:
        """Record each listed project's rendering inputs, replacing those of projects no longer listed."""
        table = tomlkit.table(is_super_table=True)
        for folder, values in inputs.items():
            check_path(folder, key="projects.inputs")
            _check_project_inputs(folder, values)
            entry = tomlkit.table()
            for name, value in values.items():
                if isinstance(value, list):
                    array = tomlkit.array()
                    array.extend(value)
                    entry.add(name, array)
                else:
                    entry.add(name, value)
            table.add(folder, entry)
        self._table("projects")["inputs"] = table

    def set_tool(self, name: str, version: str) -> None:
        """Record the version of another tool a workflow pins (`[tools] seamspec`)."""
        _check_tool(name, version)
        self._table("tools")[name] = version

    def set_pr_rules(self, *, enforce: bool, warn_since: datetime.date | None = None) -> None:
        """`[pr] enforce` (and, when warn-only, `warn_since`), spec §10. Other `[pr]` keys stay."""
        table = self._table("pr")
        table["enforce"] = enforce
        if warn_since is not None:
            table["warn_since"] = warn_since

    def set_file(self, path: str, record: Record) -> None:
        self._set_record("files", path, record)

    def set_block(self, path: str, record: Record) -> None:
        self._set_record("blocks", path, record)

    def remove_file(self, path: str) -> None:
        files = self.doc.get("files")
        if files is not None and path in files:
            del files[path]

    def _table(self, name: str) -> Table:
        if name not in self.doc:
            self.doc.add(name, tomlkit.table())
        return self.doc[name]

    def _set_record(self, kind: str, path: str, record: Record) -> None:
        key = f"{kind}.{path}"
        check_path(path, key=key)
        _check_record(record.template, record.rendered, record.written, key=key)
        if kind not in self.doc:
            self.doc.add(kind, tomlkit.table(is_super_table=True))
        values = {"template": record.template, "rendered": record.rendered, "written": record.written}
        existing = self.doc[kind].get(path)
        if existing is not None:
            # Update the known keys in place: a person's comments and extra keys in the record stay
            # (review: Copilot on PR #2).
            for name, value in values.items():
                existing[name] = value
            return
        entry = tomlkit.table()
        for name, value in values.items():
            entry.add(name, value)
        self.doc[kind][path] = entry


# --- validation ----------------------------------------------------------------------------------


def _newer_reason(standard: int, version: str, running: str) -> str | None:
    if standard > SUPPORTED_STANDARD:
        return f"it uses standard {standard}; this SWERepo supports up to {SUPPORTED_STANDARD}"
    if Version(version) > Version(running):
        return f"SWERepo {version} wrote it; this is {running}"
    return None


def _on_disk_reason(target: Path, running: str) -> str | None:
    """Why the file already at `target` must not be replaced, or None. It may have been written by a
    newer SWERepo since this state was loaded, or this state may be new (State.new) and never have
    seen it. A file that can't be read is not replaced either."""
    if not target.exists():
        return None
    try:
        data = tomllib.loads(target.read_text(encoding="utf-8"))
        standard, version = data.get("standard"), data.get("swerepo")
        if not isinstance(standard, int) or isinstance(standard, bool) or not isinstance(version, str):
            raise ValueError("no standard or swerepo version")
        reason = _newer_reason(standard, version, running)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError, InvalidVersion) as error:
        return f"the existing file can't be read ({_reason(error)}), so it isn't replaced. Fix or remove it first."
    return None if reason is None else f"the file on disk: {reason}. Upgrade SWERepo."


def _reason(error: Exception) -> str:
    """An error's text without the file's path: an OSError's message names the absolute path, which
    would put a home folder into `check` output and CI logs (ADR-20261120-fc5a point 7)."""
    if isinstance(error, OSError):
        return error.strerror or type(error).__name__
    return str(error)


def _records(table: Any) -> dict[str, Record]:
    if table is None:
        return {}
    return {
        str(path): Record(str(entry["template"]), str(entry["rendered"]), str(entry["written"]))
        for path, entry in table.items()
    }


def _check_components(components: Any, *, key: str) -> None:
    if not isinstance(components, list) or not all(isinstance(c, str) for c in components):
        raise StateError(f"{key}: must be a list of component names")
    unknown = [c for c in components if c not in COMPONENTS]
    if unknown:
        raise StateError(f"{key}: unknown component {', '.join(map(repr, unknown))} (known: {', '.join(COMPONENTS)})")


def _check_record(template: Any, rendered: Any, written: Any, *, key: str) -> None:
    if not isinstance(template, str) or not TEMPLATE_ID.fullmatch(template):
        raise StateError(f"{key}.template: {template!r} is not a template id")
    for name, value in (("rendered", rendered), ("written", written)):
        if not is_fingerprint(value):
            raise StateError(f"{key}.{name}: not a fingerprint (64 lower-case hex characters)")


def _check_value(name: str, value: Any) -> None:
    text_list = isinstance(value, list) and all(isinstance(v, str) for v in value)
    if not (isinstance(value, str) or text_list):
        raise StateError(f"values.{name}: must be text or a list of text")


def _validate(doc: TOMLDocument, running: str = __version__) -> None:
    data = doc.unwrap()
    standard = data.get("standard")
    if not isinstance(standard, int) or isinstance(standard, bool) or standard < 1:
        raise StateError("standard: must be a positive whole number")
    version = data.get("swerepo")
    if not isinstance(version, str):
        raise StateError("swerepo: must be the version that last wrote this file")
    # A file from a newer SWERepo or standard may name components and modes this version doesn't know.
    # It must still load, so `check` can say "upgrade SWERepo"; `save` refuses it (written_by_newer).
    written_by = _version(version, key="swerepo")  # always validated, whatever the standard (P1-F10)
    newer = standard > SUPPORTED_STANDARD or written_by > Version(running)
    components = data.get("components", [])
    if newer:
        if not isinstance(components, list) or not all(isinstance(c, str) for c in components):
            raise StateError("components: must be a list of component names")
        if "mode" in data and not isinstance(data["mode"], str):
            raise StateError("mode: must be text")
    else:
        _check_components(components, key="components")
        if "mode" in data and data["mode"] not in MODES:
            raise StateError(f"mode: {data['mode']!r} is not one of {', '.join(MODES)}")
    values = data.get("values", {})
    if not isinstance(values, dict):
        raise StateError("values: must be a table")
    for name, value in values.items():
        _check_value(name, value)
    for kind in ("files", "blocks"):
        table = data.get(kind, {})
        if not isinstance(table, dict):
            raise StateError(f"{kind}: must be a table of paths")
        for path, entry in table.items():
            check_path(path, key=kind)  # the key names the table, not the path it rejects
            key = f"{kind}.{path}"
            if not isinstance(entry, dict):
                raise StateError(f"{key}: must be a table with template, rendered and written")
            _check_record(entry.get("template"), entry.get("rendered"), entry.get("written"), key=key)
    _validate_settings(data)
    projects = data.get("projects", {})
    if not isinstance(projects, dict):
        raise StateError("projects: must be a table")
    inputs = projects.get("inputs", {})
    if not isinstance(inputs, dict):
        raise StateError("projects.inputs: must be a table of folders")
    for folder, values in inputs.items():
        check_path(folder, key="projects.inputs")
        _check_project_inputs(folder, values)
    for key in ("ignore", "listed", "not_covered"):
        folders = projects.get(key, [])
        if not isinstance(folders, list):
            raise StateError(f"projects.{key}: must be a list of folders")
        for folder in folders:
            check_path(folder, key=f"projects.{key}")
    privacy = data.get("privacy", {})
    if not isinstance(privacy, dict):
        raise StateError("privacy: must be a table")
    if "allow_paths" in privacy:
        _text_list(privacy["allow_paths"], key="privacy.allow_paths")
    tools = data.get("tools", {})
    if not isinstance(tools, dict):
        raise StateError("tools: must be a table of versions")
    for name, version in tools.items():
        _check_tool(name, version)


# A tool's version (or a word such as "absent"): written into workflow commands, so one plain word only (P4-F03).
_TOOL_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+!_-]*$")


def _check_tool(name: str, version: Any) -> None:
    if not isinstance(version, str) or not _TOOL_VERSION.fullmatch(version):
        raise StateError(f"tools.{name}: must be a version")


def _check_project_inputs(folder: str, values: Any) -> None:
    """A listed project's recorded inputs: text and lists of text only (their meaning is checked where used)."""
    if not isinstance(values, dict):
        raise StateError(f"projects.inputs.{folder}: must be a table")
    for name, value in values.items():
        if not (isinstance(value, str) or (isinstance(value, list) and all(isinstance(v, str) for v in value))):
            raise StateError(f"projects.inputs.{folder}.{name}: must be text or a list of text")


def _text_list(value: Any, *, key: str) -> None:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise StateError(f"{key}: must be a list of text")


def _validate_settings(data: dict[str, Any]) -> None:
    """`[agents]`, `[adopted]` and `[pr]` (ADR-20261120-5e21)."""
    for name in ("agents", "adopted", "pr"):
        if name in data and not isinstance(data[name], dict):
            raise StateError(f"{name}: must be a table")
    agents, adopted, pr = data.get("agents", {}), data.get("adopted", {}), data.get("pr", {})
    if "hosts" in agents:
        _text_list(agents["hosts"], key="agents.hosts")
    for key in ("adr_dir", "progress_dir"):
        if key in adopted:
            check_path(adopted[key], key=f"adopted.{key}")
    if "linters" in adopted:
        _text_list(adopted["linters"], key="adopted.linters")
    if "enforce" in pr and not isinstance(pr["enforce"], bool):
        raise StateError("pr.enforce: must be true or false")
    if "exempt_authors" in pr:
        _text_list(pr["exempt_authors"], key="pr.exempt_authors")
    if "skip_progress_label" in pr and not isinstance(pr["skip_progress_label"], str):
        raise StateError("pr.skip_progress_label: must be text")
