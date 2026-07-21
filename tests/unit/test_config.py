"""Unit tests for the configuration service (CFG-002..CFG-006)."""

import pytest

from config import load_config
from errors import ConfigError

DEFAULT_INI = "config/config.ini.example"


def test_defaults_load_without_file():
    cfg = load_config()
    assert cfg.get("logging", "level") == "INFO"
    assert cfg.get("synthetic", "seed") == 0
    assert cfg.get("logging", "console") is True


def test_load_default_ini():
    cfg = load_config(DEFAULT_INI)
    assert cfg.get("camera", "backend") == "auto"
    assert cfg.get("synthetic", "wavelength_max") == pytest.approx(750.0)



def test_cli_override_wins():
    cfg = load_config(DEFAULT_INI, overrides=["synthetic.seed=99", "logging.level=ERROR"])
    assert cfg.get("synthetic", "seed") == 99
    assert cfg.get("logging", "level") == "ERROR"


def test_choices_are_case_insensitive_and_normalized():
    # Any case is accepted and normalized to the schema's canonical spelling.
    for value in ("auto", "AuTo", "AUTO"):
        cfg = load_config(overrides=[f"camera.backend={value}"])
        assert cfg.get("camera", "backend") == "auto"
    # logging.level's canonical spelling is upper-case.
    cfg = load_config(overrides=["logging.level=info"])
    assert cfg.get("logging", "level") == "INFO"


def test_surrounding_whitespace_is_ignored(tmp_path):
    ini = tmp_path / "ws.ini"
    ini.write_text("[camera]\nbackend =   AuTo   \n", encoding="utf-8")
    cfg = load_config(ini)
    assert cfg.get("camera", "backend") == "auto"


def test_invalid_choice_raises():
    with pytest.raises(ConfigError) as exc:
        load_config(overrides=["logging.level=LOUD"])
    assert "logging" in str(exc.value)


def test_invalid_type_raises():
    with pytest.raises(ConfigError):
        load_config(overrides=["synthetic.seed=not-an-int"])


def test_out_of_range_raises():
    with pytest.raises(ConfigError):
        load_config(overrides=["camera.device_index=-5"])


def test_unknown_key_raises():
    with pytest.raises(ConfigError):
        load_config(overrides=["synthetic.bogus=1"])


def test_missing_file_raises():
    with pytest.raises(ConfigError):
        load_config("config/does-not-exist.ini")


def test_multiple_errors_reported_together():
    with pytest.raises(ConfigError) as exc:
        load_config(overrides=["logging.level=LOUD", "synthetic.seed=x"])
    message = str(exc.value)
    assert "logging" in message and "synthetic" in message
