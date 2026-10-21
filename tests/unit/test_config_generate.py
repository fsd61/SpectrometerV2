"""Unit tests for config generation + project-local discovery."""

from config import (
    config_path, discover_config_path, find_project_root, load_config, render_ini,
)


def test_render_ini_round_trips(tmp_path):
    p = tmp_path / "c.ini"
    p.write_text(render_ini(), encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.get("camera", "backend") == "auto"
    assert cfg.get("camera", "on_missing") == "prompt"


def test_render_ini_is_documented():
    ini = render_ini()
    assert "[camera]" in ini and "[synthetic]" in ini and "choices=" in ini


def test_find_project_root_walks_up(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / "sub").mkdir(parents=True)
    (root / "pyproject.toml").write_text("")
    monkeypatch.chdir(root / "sub")
    assert find_project_root() == root
    assert config_path() == root / "config" / "config.ini"


def test_discover_finds_project_config(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    (root / "pyproject.toml").write_text("")
    monkeypatch.chdir(root)
    assert discover_config_path() is None
    (root / "config" / "config.ini").write_text(render_ini(), encoding="utf-8")
    assert discover_config_path() == root / "config" / "config.ini"
