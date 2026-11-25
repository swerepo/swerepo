"""A fake `seamspec` for tests (ADR-20261124-cd64): logs every call with its stdin, and acts like SeamSpec on the
repository it runs in, from a JSON file of settings, without running anyone's tests.

- `--version`: prints the version set (default 0.1.2).
- `init ...`: writes `.seamspec/config.toml` (mode from `--mode`, else enforced), unless `init_fails` is set.
- `propose --json -`: writes a PROPOSED rule to `.seamspec/invariants/` and prints `{"id": ...}`.
- `verify ...`: exits with `verify_exit` (0), printing `verify_says`.
- `spec --out PATH` writes PATH; `spec --check PATH` exits `spec_check_exit` (0).
- `doctor --json`: prints `doctor` (no findings by default). `review`: logs only.
"""

import json
import os
import stat
import sys
from pathlib import Path

SCRIPT = """#!{python}
import hashlib, json, os, sys
from pathlib import Path
args = sys.argv[1:]
folder = os.environ["FAKE_SEAMSPEC_DIR"]
body = sys.stdin.read() if args[:1] == ["propose"] else None
with open(os.path.join(folder, "calls.jsonl"), "a") as log:
    log.write(json.dumps({{"args": args, "body": body, "cwd": os.getcwd()}}) + "\\n")
settings = json.load(open(os.path.join(folder, "settings.json")))
root = Path(os.getcwd())
if args == ["--version"]:
    print("seamspec " + settings.get("version", "0.1.2"))
elif args[:1] == ["init"]:
    if settings.get("init_fails"):
        sys.exit(1)
    mode = args[args.index("--mode") + 1] if "--mode" in args else "enforced"
    config = root / ".seamspec" / "config.toml"
    if not config.exists():
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('mode = "' + mode + '"\\n')
elif args[:1] == ["propose"]:
    data = json.loads(body)
    rule_id = "inv_" + hashlib.sha256(data["title"].encode()).hexdigest()[:8]
    folder_ = root / ".seamspec" / "invariants"
    folder_.mkdir(parents=True, exist_ok=True)
    rule = {{"id": rule_id, "status": "PROPOSED", "title": data["title"],
             "origin": {{"type": data.get("origin_type"), "text": data["origin_text"], "ref": data.get("origin_ref")}}}}
    (folder_ / (rule_id + ".json")).write_text(json.dumps(rule))
    print(json.dumps({{"id": rule_id, "status": "PROPOSED"}}))
elif args[:1] == ["verify"]:
    print(settings.get("verify_says", ""))
    sys.exit(settings.get("verify_exit", 0))
elif args[:2] == ["spec", "--out"]:
    (root / args[2]).parent.mkdir(parents=True, exist_ok=True)
    (root / args[2]).write_text("# Earned spec\\n")
elif args[:2] == ["spec", "--check"]:
    sys.exit(settings.get("spec_check_exit", 0))
elif args[:2] == ["doctor", "--json"]:
    print(json.dumps(settings.get("doctor", {{"ok": True, "findings": []}})))
"""


class FakeSeamspec:
    def __init__(self, folder: Path, monkeypatch) -> None:
        from swerepo import seamspec_component

        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self.script = folder / "seamspec"
        self.script.write_text(SCRIPT.format(python=sys.executable))
        self.script.chmod(self.script.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("FAKE_SEAMSPEC_DIR", str(folder))
        monkeypatch.setattr(seamspec_component, "command", lambda: str(self.script))
        self.settings: dict = {}
        self.save()

    def save(self) -> None:
        (self.folder / "settings.json").write_text(json.dumps(self.settings))

    def set(self, key: str, value) -> None:
        self.settings[key] = value
        self.save()

    def calls(self) -> list[dict]:
        log = self.folder / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def ran(self, word: str) -> list[list[str]]:
        """The argument lists of every call starting with `word`."""
        return [call["args"] for call in self.calls() if call["args"][:1] == [word]]


def no_seamspec(monkeypatch) -> None:
    """SWERepo's tests never reach a real `seamspec` on PATH: its results would depend on the machine."""
    from swerepo import seamspec_component

    monkeypatch.setattr(seamspec_component, "command", lambda: None)
    monkeypatch.delenv("FAKE_SEAMSPEC_DIR", raising=False)
    assert os.environ.get("FAKE_SEAMSPEC_DIR") is None
