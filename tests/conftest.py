"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _no_config_autodiscovery(monkeypatch):
    """main() must not pick up a real config/config.ini during tests."""
    monkeypatch.setattr("app.main.discover_config_path", lambda: None)
