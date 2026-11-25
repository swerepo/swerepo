"""Shared test setup."""

import pytest
from fake_seamspec import no_seamspec


@pytest.fixture(autouse=True)
def _no_real_seamspec(monkeypatch):
    """No test reaches a real `seamspec` on PATH (its answers depend on the machine); the SeamSpec tests use
    `FakeSeamspec` instead (ADR-20261124-cd64)."""
    no_seamspec(monkeypatch)


@pytest.fixture
def unreleased(monkeypatch):
    """SWERepo as an unreleased build, whatever version the package is now: no `governance` job, no privacy workflow
    without `--with-governance`. Tests of that case ask for it, so a release changes no test (review P8-D03)."""
    import swerepo

    monkeypatch.setattr(swerepo, "__version__", "0.1.0.dev0")
