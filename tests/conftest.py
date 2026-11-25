"""Shared test setup."""

import pytest
from fake_seamspec import no_seamspec


@pytest.fixture(autouse=True)
def _no_real_seamspec(monkeypatch):
    """No test reaches a real `seamspec` on PATH (its answers depend on the machine); the SeamSpec tests use
    `FakeSeamspec` instead (ADR-20261124-cd64)."""
    no_seamspec(monkeypatch)
