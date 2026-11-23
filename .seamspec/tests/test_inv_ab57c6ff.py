"""Rule: the privacy scan reports where personal data or a secret is, never what it is (ADR-20261122-a48e;
SWEREPO-SPEC §6.4). Samples are assembled at run time, so this file never holds them literally."""

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from swerepo.cli import app

GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=t"]
AT = "@"
EMAILS = [f"person{n:02d}" + AT + "mail.test.com" for n in range(1, 12)]
USER = "alicewonder"
HOME = "/" + "Users/" + USER + "/project"
KEY = "AKIA" + "QWERTYUIOPASDFGH"
# 13 places in file and line order: the first ten are named, then "and 3 more"
NAMED = ["config.py:1", "config.py:2", *[f"people/p{n:02d}.md:1" for n in range(1, 9)]]
KINDS = "1 home-folder path, 1 AWS access key, 11 email addresses"
MESSAGE = f"{KINDS} in tracked files ({', '.join(NAMED)}, and 3 more)"
# the values, and fragments of them that are no part of the expected message
SECRETS = [*EMAILS, HOME, USER, KEY, "person", "mail.test", "alicew", "wonder", "/project", "QWERTY", "ASDFGH"]


def _privacy_annotation(output: str) -> str:
    lines = [line for line in output.splitlines() if line.startswith("::error ") and "in tracked files (" in line]
    assert len(lines) == 1, output  # the privacy finding's own annotation, exactly one
    return lines[0]


def test_findings_name_places_never_values(tmp_path: Path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    (tmp_path / "people").mkdir()
    for n, email in enumerate(EMAILS, start=1):
        (tmp_path / f"people/p{n:02d}.md").write_text(f"contact {email}\n")
    subprocess.run([*GIT, "init", "-q", "-b", "main", str(tmp_path)], check=True)
    subprocess.run([*GIT, "-c", "user.email=t@example.com", "-C", str(tmp_path), "add", "people"], check=True)
    subprocess.run([*GIT, "-c", "user.email=t@example.com", "-C", str(tmp_path), "commit", "-qm", "x"], check=True)
    (tmp_path / "config.py").write_text(f"ROOT = '{HOME}'\nKEY = '{KEY}'\n")  # untracked: git would add it
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    runner = CliRunner()
    base = ["check", "--path", str(tmp_path), "--only", "security"]
    text = runner.invoke(app, [*base, "--ci"])
    as_json = runner.invoke(app, [*base, "--json"])
    plan = runner.invoke(app, ["init", "--path", str(tmp_path), "--only", "security", "--dry-run"])
    assert text.exit_code == 1 and as_json.exit_code == 1 and plan.exit_code == 0
    finding = next(f for f in json.loads(as_json.output)["findings"] if f["item"] == "security.privacy-scan")
    assert finding["status"] == "missing" and finding["message"] == MESSAGE  # nothing else in it
    assert _privacy_annotation(text.output).endswith("::security: " + MESSAGE)
    assert f"✗ {MESSAGE}" in text.output
    assert f"privacy scan: {MESSAGE}: fix them before committing" in plan.output
    for out in (as_json.output, text.output, plan.output):
        for secret in SECRETS:
            assert secret not in out, secret
