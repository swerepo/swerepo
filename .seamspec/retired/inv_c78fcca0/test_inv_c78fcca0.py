"""Hygiene rule (SWERepo, hygiene/ci-tests@1): the CI workflow still runs the test suite, and `ci-ok` still depends on
it, so an agent can't quietly weaken CI.

In `.github/workflows/swerepo-ci.yml`: a `test` job, and a `test-<project>` job for every folder in `.swerepo.toml`'s
`[projects] listed`. Each has a step that runs `uv run pytest` (`uv run` options such as `--locked` allowed), not
masked (`|| …`, `; …`, `… &`, `--version`, `--help`, `--collect-only`; folded `run: >` blocks and lines ending in a
backslash are joined first), and neither the job nor that step is switched off (`if: false`, also quoted or as `${{
false }}`) or allowed to fail (`continue-on-error: true`, likewise). `ci-ok`'s `needs:` names each of these jobs, and
`ci-ok` still fails when one of them fails: it runs `if: always()` (a skipped required check counts as passed), isn't
allowed to fail, and has a step, neither switched off nor allowed to fail, that reads the jobs' results (`NEEDS: ${{
toJSON(needs) }}`, then `$NEEDS` and `.result`) and can `exit` non-zero. Read as text, not parsed as YAML: action
pins, comments and the order of jobs don't matter. Standard library and pytest only.
"""

import re
import tomllib
from pathlib import Path

# The repository root holds .seamspec/config.toml, wherever SeamSpec keeps this file (.seamspec/proposed/<id>/ while
# proposed, .seamspec/tests/ once locked, or a copy of the staged tree).
ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".seamspec" / "config.toml").is_file())
WORKFLOW = ".github/workflows/swerepo-ci.yml"
JOB = re.compile(r"^  (?P<name>[A-Za-z0-9_-]+):\s*(?:#.*)?$")
PYTEST = re.compile(r"^uv run(?: --?[A-Za-z0-9][\w-]*(?:=\S+)?)* pytest(?P<rest>(?:\s.*)?)$")
NOT_A_RUN = re.compile(r"\|\||;|(?<!&)&(?!&)|(?:^|\s)(?:--version|--help|-h|--collect-only|--co)(?:\s|$)")
OFF = re.compile(r"^\s*if:\s*(?:\$\{\{\s*)?[\'\"]?false[\'\"]?\s*(?:\}\})?\s*(?:#.*)?$", re.IGNORECASE)
MAY_FAIL = re.compile(
    r"^\s*continue-on-error:\s*(?:\$\{\{\s*)?[\'\"]?true[\'\"]?\s*(?:\}\})?\s*(?:#.*)?$", re.IGNORECASE
)
ALWAYS = re.compile(r"^    if:\s*(?:\$\{\{\s*)?always\(\)\s*(?:\}\})?\s*(?:#.*)?$")
NEEDS_ENV = re.compile(r"^\s*NEEDS:\s*\$\{\{\s*toJSON\(needs\)\s*\}\}\s*(?:#.*)?$")
EXITS = re.compile(r"^exit\s+(?:[1-9]|\$)")
NEEDS_INLINE = re.compile(r"^    needs:\s*\[(?P<items>[^\]]*)\]")
NEEDS_BLOCK = re.compile(r"^    needs:\s*(?:#.*)?$")
NEEDS_ITEM = re.compile(r"^      -\s+(?P<name>[A-Za-z0-9_-]+)\s*(?:#.*)?$")
STEP = re.compile(r"^      - ")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _jobs(text: str) -> dict[str, list[str]]:
    """Each job's lines, by name: the jobs under `jobs:`, at two spaces."""
    jobs: dict[str, list[str]] = {}
    current, inside = None, False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            inside, current = line.rstrip().startswith("jobs:"), None
            continue
        match = JOB.match(line) if inside else None
        if match:
            current = match["name"]
            jobs[current] = []
        elif current is not None:
            jobs[current].append(line)
    return jobs


def _job_keys(lines: list[str]) -> list[str]:
    """The job's own keys (four spaces), not those of its steps."""
    return [line for line in lines if _indent(line) == 4]


def _steps(lines: list[str]) -> list[list[str]]:
    """The job's steps: each from its `- ` at six spaces to the next one, or the end of `steps:`."""
    steps: list[list[str]] = []
    inside = False
    for line in lines:
        if _indent(line) <= 4:
            inside = line.strip().startswith("steps:")
            continue
        if inside and STEP.match(line):
            steps.append(["        " + line[8:]])  # `- key: value` read as the step's first key, at eight spaces
        elif inside and steps:
            steps[-1].append(line)
    return steps


def _commands(step: list[str]) -> list[str]:
    """The shell commands a step runs: `run: …`, or a `run: |` block's lines; a folded `run: >` block is one command,
    and a line ending in `\\` goes on with the next."""
    commands: list[str] = []
    for i, line in enumerate(step):
        key = line.strip()
        if _indent(line) != 8 or not key.startswith("run:"):
            continue
        value = key[4:].strip()
        if value and value[0] not in "|>":
            commands.append(value)
            continue
        block = []
        for later in step[i + 1 :]:
            if _indent(later) <= 8:
                break
            block.append(later.strip())
        if value.startswith(">"):
            block = [" ".join(block)]
        joined: list[str] = []
        for text in block:
            if joined and joined[-1].endswith("\\"):
                joined[-1] = joined[-1][:-1].rstrip() + " " + text
            else:
                joined.append(text)
        commands += joined
    return commands


def _runs_the_tests(step: list[str]) -> bool:
    if any(_indent(line) == 8 and (OFF.match(line) or MAY_FAIL.match(line)) for line in step):
        return False
    for command in _commands(step):
        match = PYTEST.match(command.split("#", 1)[0].strip())
        if match and not NOT_A_RUN.search(match["rest"]):
            return True
    return False


def _judges(step: list[str]) -> bool:
    """Whether a step fails `ci-ok` when a needed job's result is wrong: it reads every job's result and can exit
    non-zero, and is neither switched off nor allowed to fail."""
    if any(_indent(line) == 8 and (OFF.match(line) or MAY_FAIL.match(line)) for line in step):
        return False
    commands = _commands(step)
    script = "\n".join(commands)
    reads = any(NEEDS_ENV.match(line) for line in step) and "$NEEDS" in script and ".result" in script
    return reads and any(EXITS.match(command) for command in commands)


def _needs(lines: list[str]) -> list[str]:
    for i, line in enumerate(lines):
        if match := NEEDS_INLINE.match(line):
            return [item.strip().strip("'\"") for item in match["items"].split(",") if item.strip()]
        if NEEDS_BLOCK.match(line):
            names = []
            for later in lines[i + 1 :]:  # the list ends where `needs:` ends
                item = NEEDS_ITEM.match(later)
                if item is None:
                    break
                names.append(item["name"])
            return names
    return []


def _job_name(folder: str) -> str:
    return "test-" + re.sub(r"[^a-z0-9-]+", "-", folder.lower()).strip("-")


def _expected() -> list[str]:
    try:
        state = tomllib.loads((ROOT / ".swerepo.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        state = {}
    projects = state.get("projects", {})
    listed = projects.get("listed", []) if isinstance(projects, dict) else []
    listed = listed if isinstance(listed, list) else []
    return ["test", *(_job_name(folder) for folder in listed if isinstance(folder, str))]


def _problems(text: str, expected: list[str]) -> list[str]:
    jobs = _jobs(text)
    if "ci-ok" not in jobs:
        return ["no ci-ok job"]
    needs, problems = _needs(jobs["ci-ok"]), []
    if any(OFF.match(line) for line in _job_keys(jobs["ci-ok"])):
        problems.append("ci-ok is switched off")
    if any(MAY_FAIL.match(line) for line in _job_keys(jobs["ci-ok"])):
        problems.append("ci-ok is allowed to fail")
    if not any(ALWAYS.match(line) for line in _job_keys(jobs["ci-ok"])):
        problems.append("ci-ok doesn't run when a job fails (if: always())")
    if not any(_judges(step) for step in _steps(jobs["ci-ok"])):
        problems.append("ci-ok doesn't fail when a needed job fails")
    for name in expected:
        lines = jobs.get(name)
        if lines is None:
            problems.append(f"no {name} job")
            continue
        keys = _job_keys(lines)
        if any(OFF.match(line) for line in keys):
            problems.append(f"{name} is switched off")
        if any(MAY_FAIL.match(line) for line in keys):
            problems.append(f"{name} is allowed to fail")
        if not any(_runs_the_tests(step) for step in _steps(lines)):
            problems.append(f"{name} doesn't run `uv run pytest`")
        if name not in needs:
            problems.append(f"ci-ok doesn't need {name}")
    return problems


def test_ci_still_runs_the_tests_and_ci_ok_needs_them():
    workflow = ROOT / WORKFLOW
    assert workflow.is_file(), f"{WORKFLOW} is missing"
    assert _problems(workflow.read_text(encoding="utf-8", errors="replace"), _expected()) == []


SAMPLE = """name: swerepo-ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@0123456789012345678901234567890123456789  # v9.9.9
        with:
          persist-credentials: false
      - run: uv sync --locked
      - run: uv run pytest
  test-services-api:
    runs-on: ubuntu-latest
    steps:
      - name: tests
        run: |
          uv sync --locked
          uv run --locked pytest -q
  ci-ok:
    if: always()
    needs: [test, test-services-api]
    runs-on: ubuntu-latest
    steps:
      - name: every job passed
        env:
          NEEDS: ${{ toJSON(needs) }}
        run: |
          wrong=$(printf '%s' "$NEEDS" | jq -r 'to_entries[] | select(.value.result != "success") | .key')
          if [ -n "$wrong" ]; then
            exit 1
          fi
"""
BOTH = ["test", "test-services-api"]


def test_the_workflow_is_read_as_text():
    assert _problems(SAMPLE, ["test", _job_name("services/API")]) == []
    assert _problems(SAMPLE.replace("      - run: uv run pytest\n", "      - run: echo skipped\n", 1), ["test"])
    assert _problems(SAMPLE.replace("needs: [test, ", "needs: ["), ["test"]) == ["ci-ok doesn't need test"]
    assert _problems(SAMPLE, ["test", "test-web"]) == ["no test-web job"]
    off = SAMPLE.replace("  test:\n", "  test:\n    if: false\n", 1)
    assert _problems(off, ["test"]) == ["test is switched off"]
    may_fail = SAMPLE.replace("  test:\n", "  test:\n    continue-on-error: true\n", 1)
    assert _problems(may_fail, ["test"]) == ["test is allowed to fail"]


def test_a_test_step_switched_off_or_masked_doesnt_count():
    step = "      - run: uv run pytest\n"
    for weakened in (
        "      - run: uv run pytest\n        if: false\n",
        "      - if: ${{ false }}\n        run: uv run pytest\n",
        "      - run: uv run pytest\n        continue-on-error: true\n",
        "      - run: uv run pytest || true\n",
        "      - run: uv run pytest; true\n",
        "      - run: uv run pytest --version\n",
        "      - run: uv run pytest --collect-only\n",
        "      - run: uv run pytest --help\n",
        "      - run: uv run pytest -h\n",
        "      - run: uv run pytest --co\n",
        "      - run: echo uv run pytest\n",
        "      - run: uv run pytest &\n",
        "      - if: 'false'\n        run: uv run pytest\n",
        "      - if: False\n        run: uv run pytest\n",
        "      - continue-on-error: ${{ true }}\n        run: uv run pytest\n",
        "      - run: >\n          uv run pytest\n          || true\n",
        "      - run: |\n          uv run pytest \\\n            --collect-only\n",
    ):
        assert _problems(SAMPLE.replace(step, weakened, 1), ["test"]) == ["test doesn't run `uv run pytest`"], weakened
    assert _problems(SAMPLE.replace(step, "      - run: uv run --locked pytest -x\n", 1), ["test"]) == []
    joined = "      - run: |\n          uv run pytest \\\n            -q\n"
    assert _problems(SAMPLE.replace(step, joined, 1), ["test"]) == []
    assert _problems(SAMPLE.replace(step, "      - run: uv run pytest && echo done\n", 1), ["test"]) == []


def test_ci_ok_itself_switched_off_or_allowed_to_fail():
    head = "  ci-ok:\n    if: always()\n"
    off = SAMPLE.replace(head, "  ci-ok:\n    if: ${{ false }}\n")
    assert _problems(off, BOTH) == ["ci-ok is switched off", "ci-ok doesn't run when a job fails (if: always())"]
    allowed = "  ci-ok:\n    if: always()\n    continue-on-error: 'true'\n"
    assert _problems(SAMPLE.replace(head, allowed), BOTH) == ["ci-ok is allowed to fail"]
    assert _problems(SAMPLE.replace(head, "  ci-ok:\n    if: ${{ always() }}\n"), BOTH) == []


def test_ci_ok_still_fails_when_a_job_fails():
    gate = "      - name: every job passed\n"
    judge = SAMPLE[SAMPLE.index(gate) :]
    cases = {
        "echo ok": SAMPLE.replace(judge, "      - run: echo ok\n"),
        "no exit": SAMPLE.replace("            exit 1\n", "            echo failed\n"),
        "exit masked": SAMPLE.replace("            exit 1\n", "            echo exit 1\n"),
        "no results": SAMPLE.replace("          NEEDS: ${{ toJSON(needs) }}\n", "          NEEDS: '{}'\n"),
        "step off": SAMPLE.replace(gate, gate + "        if: false\n"),
        "step may fail": SAMPLE.replace(gate, gate + "        continue-on-error: true\n"),
    }
    for case, text in cases.items():
        assert _problems(text, BOTH) == ["ci-ok doesn't fail when a needed job fails"], case
    no_always = SAMPLE.replace("  ci-ok:\n    if: always()\n", "  ci-ok:\n")
    assert _problems(no_always, BOTH) == ["ci-ok doesn't run when a job fails (if: always())"]


def test_a_needs_list_ends_where_it_ends():
    listed = "    needs:\n      - test\n      - test-services-api\n"
    assert _problems(SAMPLE.replace("    needs: [test, test-services-api]\n", listed), BOTH) == []
    later = "    needs:\n      - test-services-api\n    runs-on: ubuntu-latest\n    steps:\n      - test\n"
    block = SAMPLE.replace("    needs: [test, test-services-api]\n    runs-on: ubuntu-latest\n    steps:\n", later)
    assert _problems(block, BOTH) == ["ci-ok doesn't need test"]  # `- test` under steps isn't in needs
