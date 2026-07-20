"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_user_config(monkeypatch, tmp_path):
    """Point XDG_CONFIG_HOME at an empty per-test dir so config auto-discovery
    never picks up a real user config on the host machine."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
