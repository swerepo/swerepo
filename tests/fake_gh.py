"""A fake `gh` for tests (spec §18): answers from a JSON file of canned responses, logs every call, and never
reaches GitHub. Responses are keyed "METHOD path" (query strings dropped) or "graphql"; a missing key fails the
call as GitHub would (exit 1, message on stdout as JSON); `fail` answers a status and message as gh prints
them."""

import json
import os
import stat
import sys
from pathlib import Path

SCRIPT = """#!{python}
import json, os, sys
args = sys.argv[1:]
folder = os.environ["FAKE_GH_DIR"]
with open(os.path.join(folder, "calls.jsonl"), "a") as log:
    body = sys.stdin.read() if "--input" in args else None
    log.write(json.dumps({{"args": args, "body": body}}) + "\\n")
responses = json.load(open(os.path.join(folder, "responses.json")))
if args[:2] == ["auth", "status"]:
    sys.exit(0 if responses.get("logged_in", True) else 1)
if args[:2] == ["api", "graphql"]:
    key = "graphql"
else:
    method = args[args.index("-X") + 1] if "-X" in args else "GET"
    values = {{i + 1 for i, a in enumerate(args) if a in ("-X", "-H")}}  # an option's value is never the path
    path = [a for i, a in enumerate(args) if i > 0 and i not in values and not a.startswith("-")][0]
    key = method + " " + path.split("?")[0]
if key not in responses:
    print(json.dumps({{"message": "Not Found"}}))
    sys.exit(1)
answer = responses[key]
if isinstance(answer, dict) and "$error" in answer:  # a failure, as gh prints one: JSON on stdout, (HTTP nnn) on stderr
    status, message = answer["$error"]["status"], answer["$error"]["message"]
    print(json.dumps({{"message": message, "status": str(status)}}))
    sys.stderr.write(f"gh: {{message}} (HTTP {{status}})\\n")
    sys.exit(1)
print(json.dumps(answer))
"""


class FakeGh:
    def __init__(self, folder: Path, monkeypatch) -> None:
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        script = folder / "gh"
        script.write_text(SCRIPT.format(python=sys.executable))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("FAKE_GH_DIR", str(folder))
        self.responses: dict = {}
        self.save()

    def save(self) -> None:
        (self.folder / "responses.json").write_text(json.dumps(self.responses))

    def set(self, key: str, value) -> None:
        self.responses[key] = value
        self.save()

    def fail(self, key: str, status: int, message: str) -> None:
        """Answer `key` with an HTTP failure, as gh prints one (review P8-K07)."""
        self.set(key, {"$error": {"status": status, "message": message}})

    def accepts(self) -> list[str]:
        """The `Accept` headers of every `gh api` call (P8-K06: exactly one each)."""
        return [a for call in self.calls() for a in call["args"] if a.startswith("Accept:")]

    def calls(self) -> list[dict]:
        log = self.folder / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def methods(self) -> list[str]:
        """The HTTP method of every `gh api` call (GET when none is named)."""
        found = []
        for call in self.calls():
            args = call["args"]
            if args[:1] == ["api"] and args[1:2] != ["graphql"]:
                found.append(args[args.index("-X") + 1] if "-X" in args else "GET")
        return found
