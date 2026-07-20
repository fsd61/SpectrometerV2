"""Unit tests for config generation + discovery (single-file config model)."""

from config import discover_config_path, load_config, render_ini, user_config_path


def test_render_ini_round_trips(tmp_path):
    p = tmp_path / "config.ini"
    p.write_text(render_ini())
    cfg = load_config(str(p))
    assert cfg.get("camera", "backend") == "auto"
    assert cfg.get("camera", "on_missing") == "prompt"


def test_render_ini_is_documented():
    ini = render_ini()
    assert "[camera]" in ini and "[synthetic]" in ini
    assert "# " in ini and "choices=" in ini


def test_user_config_path_honors_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert user_config_path() == tmp_path / "spectrometerv2" / "config.ini"


def test_discover_finds_project_local(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    assert discover_config_path() is None
    (tmp_path / "spectrometerv2.ini").write_text(render_ini())
    assert discover_config_path() == tmp_path / "spectrometerv2.ini"


def test_discover_finds_user_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    assert discover_config_path() is None
    target = xdg / "spectrometerv2" / "config.ini"
    target.parent.mkdir(parents=True)
    target.write_text(render_ini())
    assert discover_config_path() == target
