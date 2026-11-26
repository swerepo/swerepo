"""Rule: `check`, `init`'s plan and `threads` only read GitHub (and `check --ci` doesn't call it); `init` and `update`
change GitHub only when asked for by name (a terminal's yes, or `--yes --apply-github`; never `--yes` alone), and only
the ruleset named `swerepo` and the repository's merge settings (ADR-20261123-4e40, ADR-20261125-5f22 point 5;
SWEREPO-SPEC §7, §12, §15, §17). Replaces inv_ef31cc79, where `--yes` alone applied them. GitHub is a fake `gh` on PATH that logs every call and its request
body: nothing leaves the test. Calls are judged by an allow-list: anything but `gh auth status`, a REST GET, or a
GraphQL query (never a mutation) counts as a change, however it is spelled."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from swerepo.cli import app

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]
SLUG = "acme/app"
FAKE = """#!{python}
import json, os, sys
args = sys.argv[1:]
folder = os.environ["FAKE_GH_DIR"]
body = sys.stdin.read() if any(a == "--input" or a.startswith("--input=") for a in args) else None
with open(os.path.join(folder, "calls.jsonl"), "a") as log:
    log.write(json.dumps({{"args": args, "body": body}}) + "\\n")
if args[:2] == ["auth", "status"]:
    sys.exit(0)
responses = json.load(open(os.path.join(folder, "responses.json")))
if args[:2] == ["api", "graphql"]:
    key = "graphql"
else:
    method = args[args.index("-X") + 1] if "-X" in args else "GET"
    path = [a for a in args[1:] if not a.startswith("-") and a != method and not a.startswith("Accept")][0]
    key = method + " " + path.split("?")[0]
if key not in responses:
    print(json.dumps({{"message": "Not Found"}}))
    sys.exit(1)
print(json.dumps(responses[key]))
"""
# gh api options that carry a body, which makes gh send a POST unless a method is named, in every spelling:
# separate (`-f x=1`), attached (`-fx=1`) or with `=` (`--field=x=1`)
BODY_OPTIONS = ("-f", "-F", "--field", "--raw-field", "--input")


def _is_body_option(arg: str) -> bool:
    for option in BODY_OPTIONS:
        if arg == option or arg.startswith(option + "="):
            return True
        if len(option) == 2 and arg.startswith(option) and len(arg) > 2:  # -fkey=value, -Fkey=value
            return True
    return False


def _setup(tmp_path: Path, monkeypatch, rulesets: list[dict]) -> tuple[Path, Path]:
    root = tmp_path / "app"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "app"\nrequires-python = ">=3.12"\n')
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run([*GIT, "-C", str(root), "remote", "add", "origin", f"https://github.com/{SLUG}.git"], check=True)
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "gh").write_text(FAKE.format(python=sys.executable))
    (fake / "gh").chmod((fake / "gh").stat().st_mode | stat.S_IEXEC)
    responses = {
        f"GET repos/{SLUG}": {"owner": {"login": "dev", "type": "User"}, "allow_merge_commit": True},
        f"GET repos/{SLUG}/rulesets": rulesets,
        f"GET repos/{SLUG}/dependency-graph/sbom": {"sbom": {}},
        f"POST repos/{SLUG}/rulesets": {"id": 9},
        f"PATCH repos/{SLUG}": {},
        "graphql": {
            "data": {
                "repository": {"pullRequest": {"reviewThreads": {"pageInfo": {"hasNextPage": False}, "nodes": []}}}
            }
        },
    }
    for ruleset in rulesets:
        responses[f"GET repos/{SLUG}/rulesets/{ruleset['id']}"] = {**ruleset, "rules": []}
        responses[f"PUT repos/{SLUG}/rulesets/{ruleset['id']}"] = {"id": ruleset["id"]}
    (fake / "responses.json").write_text(json.dumps(responses))
    monkeypatch.setenv("PATH", f"{fake}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_DIR", str(fake))
    return root, fake


def _calls(fake: Path) -> list[dict]:
    log = fake / "calls.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def _method(args: list[str]) -> str:
    """The HTTP method a `gh api` call sends, however the method is spelled: `-X PUT`, `-XPUT`, `--method PUT`,
    `--method=PUT`; with none named, gh sends a POST when the call carries a body."""
    for index, arg in enumerate(args):
        if arg in ("-X", "--method") and index + 1 < len(args):
            return args[index + 1].upper()
        if arg.startswith("--method="):
            return arg.split("=", 1)[1].upper()
        if arg.startswith("-X") and len(arg) > 2:
            return arg[2:].upper()
    return "POST" if any(_is_body_option(arg) for arg in args) else "GET"  # gh's own default


def _changes(calls: list[dict]) -> list[tuple[str, str]]:
    """Every call that isn't on the allow-list, as (method, what): an allow-list, so a change sent any new way
    still counts."""
    found = []
    for call in calls:
        args = call["args"]
        if args[:2] == ["auth", "status"]:
            continue
        if args[:2] == ["api", "graphql"]:
            sent = " ".join(args) + " " + (call.get("body") or "")  # the query may come as an argument or on stdin
            if "mutation" not in sent.lower():
                continue  # a GraphQL query: sent as a POST, but it only reads
            found.append(("GRAPHQL", "mutation"))
            continue
        if args[:1] == ["api"]:
            method = _method(args)
            if method == "GET":
                continue
            path = next((a for a in args[1:] if a.startswith("repos/") or a == "user"), " ".join(args[1:]))
            found.append((method, path))
            continue
        found.append(("GH", " ".join(args[:2])))  # any other gh command (repo edit, pr review, ...)
    return found


def _committed(root: Path, name: str) -> dict:
    return json.loads((root / ".github/swerepo" / name).read_text())


def _body(calls: list[dict], method: str, path: str) -> dict:
    call = next(c for c in calls if c["args"][:1] == ["api"] and _method(c["args"]) == method and path in c["args"])
    return json.loads(call["body"])


def test_github_changes_only_after_a_yes_and_only_swerepos_ruleset(tmp_path: Path, monkeypatch):
    root, fake = _setup(tmp_path, monkeypatch, [{"id": 3, "name": "theirs"}, {"id": 7, "name": "swerepo"}])
    runner = CliRunner()
    check = runner.invoke(app, ["check", "--path", str(root)])
    as_json = runner.invoke(app, ["check", "--path", str(root), "--json"])
    dry = runner.invoke(app, ["init", "--path", str(root), "--only", "github", "--dry-run"])
    threads = runner.invoke(app, ["threads", "1", "--path", str(root)])
    assert check.exit_code in (0, 1) and as_json.exit_code in (0, 1) and dry.exit_code == 0
    assert threads.exit_code == 0 and "no open review threads" in threads.output
    assert "apply" in dry.output and "ruleset" in dry.output  # the plan read GitHub and has work to do
    reads = _calls(fake)
    assert any(c["args"][:2] == ["api", "graphql"] for c in reads)  # threads asked
    assert any(c["args"][:1] == ["api"] and c["args"][1:2] != ["graphql"] for c in reads)  # GitHub was read
    assert _changes(reads) == []  # ... and never changed

    before = len(_calls(fake))
    ci = runner.invoke(app, ["check", "--path", str(root), "--ci"])
    assert ci.exit_code in (0, 1) and len(_calls(fake)) == before  # --ci never calls gh

    stopped = runner.invoke(app, ["init", "--path", str(root), "--only", "github"])  # no terminal, no --yes
    assert stopped.exit_code == 2 and _changes(_calls(fake)) == []

    # --yes alone writes the files and never changes GitHub: on a first run, and on a second (SeamSpec de_00bb3c21)
    first = runner.invoke(app, ["init", "--path", str(root), "--only", "github", "--yes"])
    assert first.exit_code == 0, first.output
    assert (root / ".github/swerepo/ruleset.json").is_file() and _changes(_calls(fake)) == []
    second = runner.invoke(app, ["init", "--path", str(root), "--only", "github", "--yes"])
    assert second.exit_code == 0 and "Nothing to do." in second.output and _changes(_calls(fake)) == []
    update = runner.invoke(app, ["update", "--path", str(root), "--only", "github", "--yes"])
    assert update.exit_code == 0 and _changes(_calls(fake)) == []
    plain = runner.invoke(app, ["update", "--path", str(root), "--only", "github"])  # no terminal, no --yes
    assert plain.exit_code in (0, 2) and _changes(_calls(fake)) == []
    # --apply-github without --yes and without a terminal, with something to apply: exit 2, nothing changed
    for command in ("init", "update"):
        unasked = runner.invoke(app, [command, "--path", str(root), "--only", "github", "--apply-github"])
        assert unasked.exit_code == 2 and _changes(_calls(fake)) == []

    done = runner.invoke(app, ["init", "--path", str(root), "--only", "github", "--yes", "--apply-github"])
    assert done.exit_code == 0, done.output
    calls = _calls(fake)
    assert sorted(_changes(calls)) == [("PATCH", f"repos/{SLUG}"), ("PUT", f"repos/{SLUG}/rulesets/7")]
    # what was sent is exactly what the repository now commits: the ruleset in place of "swerepo", not "theirs"
    assert _body(calls, "PUT", f"repos/{SLUG}/rulesets/7") == _committed(root, "ruleset.json")
    assert _body(calls, "PATCH", f"repos/{SLUG}") == _committed(root, "repo-settings.json")
    # update does the same: in place of "swerepo", never "theirs", with exactly the committed files
    before = len(_calls(fake))
    again = runner.invoke(app, ["update", "--path", str(root), "--only", "github", "--yes", "--apply-github"])
    assert again.exit_code == 0, again.output
    new = _calls(fake)[before:]
    assert sorted(_changes(new)) == [("PATCH", f"repos/{SLUG}"), ("PUT", f"repos/{SLUG}/rulesets/7")]
    assert _body(new, "PUT", f"repos/{SLUG}/rulesets/7") == _committed(root, "ruleset.json")
    assert _body(new, "PATCH", f"repos/{SLUG}") == _committed(root, "repo-settings.json")

    # with the ruleset files now committed, check compares them with GitHub: still reads only
    for extra in ([], ["--json"]):
        before = len(_calls(fake))
        after = runner.invoke(app, ["check", "--path", str(root), *extra])
        assert after.exit_code in (0, 1)
        new = _calls(fake)[before:]
        assert any(f"repos/{SLUG}/rulesets/7" in c["args"] for c in new) and _changes(new) == []
    before = len(_calls(fake))
    ci = runner.invoke(app, ["check", "--path", str(root), "--ci"])
    assert ci.exit_code in (0, 1) and len(_calls(fake)) == before  # --ci: no gh call, files present or not


@pytest.mark.parametrize("command", ["init", "update"])
def test_without_a_swerepo_ruleset_one_is_created_and_others_left_alone(tmp_path: Path, monkeypatch, command: str):
    root, fake = _setup(tmp_path, monkeypatch, [{"id": 3, "name": "theirs"}])
    runner = CliRunner()
    files = runner.invoke(app, ["init", "--path", str(root), "--only", "github", "--yes"])
    assert files.exit_code == 0 and _changes(_calls(fake)) == [], files.output
    done = runner.invoke(app, [command, "--path", str(root), "--only", "github", "--yes", "--apply-github"])
    assert done.exit_code == 0, done.output
    calls = _calls(fake)
    assert sorted(_changes(calls)) == [("PATCH", f"repos/{SLUG}"), ("POST", f"repos/{SLUG}/rulesets")]
    assert _body(calls, "POST", f"repos/{SLUG}/rulesets") == _committed(root, "ruleset.json")
    assert _body(calls, "PATCH", f"repos/{SLUG}") == _committed(root, "repo-settings.json")


def test_saying_no_in_a_terminal_changes_nothing_on_github(tmp_path: Path, monkeypatch):
    from swerepo import cli

    root, fake = _setup(tmp_path, monkeypatch, [{"id": 7, "name": "swerepo"}])
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    runner = CliRunner()
    command = ["init", "--path", str(root), "--only", "github"]
    # the mode and code owner (their defaults), then "Apply?": no
    declined = runner.invoke(app, command, input="\n\nn\n")
    assert declined.exit_code == 0 and "Nothing applied." in declined.output
    assert _changes(_calls(fake)) == []
    # yes to the files, then no to the ruleset and no to the merge settings
    files_only = runner.invoke(app, command, input="\n\ny\nn\nn\n")
    assert files_only.exit_code == 0, files_only.output
    # both GitHub questions were asked (and answered no), each after showing what it would send
    assert 'Apply ruleset "swerepo" on the default branch?' in files_only.output
    assert "Apply merge settings?" in files_only.output and "GitHub: nothing applied" in files_only.output
    assert (root / ".github/swerepo/ruleset.json").is_file() and _changes(_calls(fake)) == []
    # update in a terminal: no at "Apply?", then no to the ruleset and no to the merge settings
    update = ["update", "--path", str(root), "--only", "github"]
    no_update = runner.invoke(app, update, input="n\n")
    assert no_update.exit_code == 0 and "Nothing applied." in no_update.output and _changes(_calls(fake)) == []
    both_no = runner.invoke(app, update, input="y\nn\nn\n")
    assert both_no.exit_code == 0, both_no.output
    assert 'Apply ruleset "swerepo" on the default branch?' in both_no.output
    assert "Apply merge settings?" in both_no.output and _changes(_calls(fake)) == []
    # --yes in a terminal is still --yes alone: nothing on GitHub, and nothing asked
    for command in ("init", "update"):
        yes = runner.invoke(app, [command, "--path", str(root), "--only", "github", "--yes"])
        assert yes.exit_code == 0 and "Apply ruleset" not in yes.output and _changes(_calls(fake)) == [], yes.output


@pytest.mark.parametrize("command", ["init", "update"])
def test_a_yes_in_a_terminal_changes_only_swerepos_ruleset_and_the_merge_settings(
    tmp_path: Path, monkeypatch, command: str
):
    from swerepo import cli

    root, fake = _setup(tmp_path, monkeypatch, [{"id": 3, "name": "theirs"}, {"id": 7, "name": "swerepo"}])
    runner = CliRunner()
    files = runner.invoke(app, ["init", "--path", str(root), "--only", "github", "--yes"])  # the files, no GitHub
    assert files.exit_code == 0 and _changes(_calls(fake)) == [], files.output
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    # in a terminal (the mode and code owner now recorded): "Apply?" yes, then yes to the ruleset and the settings
    done = runner.invoke(app, [command, "--path", str(root), "--only", "github"], input="y\ny\ny\n")
    assert done.exit_code == 0, done.output
    assert 'Apply ruleset "swerepo" on the default branch?' in done.output and "Apply merge settings?" in done.output
    calls = _calls(fake)
    assert sorted(_changes(calls)) == [("PATCH", f"repos/{SLUG}"), ("PUT", f"repos/{SLUG}/rulesets/7")]
    assert _body(calls, "PUT", f"repos/{SLUG}/rulesets/7") == _committed(root, "ruleset.json")
    assert _body(calls, "PATCH", f"repos/{SLUG}") == _committed(root, "repo-settings.json")


def test_every_spelling_of_a_change_is_caught():
    """The allow-list itself: what a change can look like on gh's command line."""
    path = f"repos/{SLUG}"
    for args in (["api", "-X", "PUT", path], ["api", "-XPUT", path], ["api", "--method", "PATCH", path],
                 ["api", "--method=PATCH", path], ["api", path, "-f", "x=1"], ["api", path, "-fx=1"],
                 ["api", path, "-Fx=1"], ["api", path, "--field=x=1"], ["api", path, "--raw-field=x=1"],
                 ["api", path, "--input=-"], ["api", path, "--input", "-"], ["repo", "edit"]):  # fmt: skip
        assert _changes([{"args": args, "body": None}]), args
    mutation = {"args": ["api", "graphql", "--input", "-"], "body": '{"query": "mutation { x }"}'}
    assert _changes([mutation]) == [("GRAPHQL", "mutation")]
    for args in (["api", path], ["api", "-X", "GET", path], ["api", "-XGET", path], ["auth", "status"],
                 ["api", "graphql", "-f", "query=query { x }"]):  # fmt: skip
        assert not _changes([{"args": args, "body": None}]), args


def test_a_mutation_on_stdin_is_seen_however_input_is_spelled(tmp_path: Path, monkeypatch):
    """Through the fake gh itself: the body it logs is what the allow-list judges."""
    _, fake = _setup(tmp_path, monkeypatch, [])
    body = json.dumps({"query": 'mutation { resolveReviewThread(input: {threadId: "x"}) { thread { id } } }'})
    for spelling in (["--input", "-"], ["--input=-"]):
        before = len(_calls(fake))
        subprocess.run(["gh", "api", "graphql", *spelling], input=body, text=True, capture_output=True, check=False)
        sent = _calls(fake)[before:]
        assert sent and sent[0]["body"] == body, spelling
        assert _changes(sent) == [("GRAPHQL", "mutation")], spelling
