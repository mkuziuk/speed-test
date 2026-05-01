"""Shared pytest fixtures."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_speed_test_config(monkeypatch):
    """Ensure every test uses a temporary config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("SPEED_TEST_CONFIG_DIR", tmpdir)
        yield Path(tmpdir)
