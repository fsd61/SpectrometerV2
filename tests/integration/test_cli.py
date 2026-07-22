"""Integration tests for the application CLI end-to-end (Phase 6 headless)."""

import json

import pytest

from app.main import main


def _base(tmp):
    return ["--set", "logging.console=false", "--set", f"logging.directory={tmp}/logs"]


def test_generate_synthetic_writes_outputs(tmp_path):
    rc = main(_base(tmp_path) + ["-o", str(tmp_path), "generate-synthetic"])
    assert rc == 0
    assert (tmp_path / "synthetic.csv").exists()
    meta = json.loads((tmp_path / "synthetic.meta.json").read_text())
    assert meta["source"] == "synthetic"


def test_test_camera_synthetic_ok(tmp_path):
    assert main(_base(tmp_path) + ["--set", "camera.backend=synthetic", "test-camera"]) == 0


def test_run_synthetic_writes_acquisition(tmp_path):
    rc = main(_base(tmp_path) + ["--set", "camera.backend=synthetic", "-o", str(tmp_path), "run"])
    assert rc == 0 and (tmp_path / "acquisition.csv").exists()


def test_analyze_reads_generated_spectrum(tmp_path):
    main(_base(tmp_path) + ["-o", str(tmp_path), "generate-synthetic"])
    assert main(_base(tmp_path) + ["-i", str(tmp_path / "synthetic.csv"), "analyze"]) == 0


def test_analyze_without_input_returns_2(tmp_path):
    assert main(_base(tmp_path) + ["analyze"]) == 2


def test_usb_camera_without_hardware_fails_gracefully(tmp_path):
    # No OpenCV/hardware in this environment -> CameraError -> graceful exit 1.
    assert main(_base(tmp_path) + ["--set", "camera.backend=usb", "test-camera"]) == 1


def test_invalid_config_returns_2(tmp_path):
    assert main(_base(tmp_path) + ["--set", "logging.level=LOUD", "validate-config"]) == 2


def test_verify_hardware_synthetic_ok(tmp_path):
    assert main(_base(tmp_path) + ["--set", "camera.backend=synthetic", "verify-hardware"]) == 0


def test_check_calibration_ok(tmp_path):
    cal = tmp_path / "caldata.txt"
    cal.write_text("35,250,470,700\r\n404.66,435.83,546.07,611.60\r\n")
    rc = main(_base(tmp_path) + ["--set", f"calibration.file={cal}",
                                 "--set", "camera.width=800", "check-calibration"])
    assert rc == 0


def test_check_calibration_missing_returns_1(tmp_path):
    rc = main(_base(tmp_path) + ["--set", f"calibration.file={tmp_path / 'none.txt'}",
                                 "check-calibration"])
    assert rc == 1


def test_stream_renders_waterfall(tmp_path):
    pytest.importorskip("matplotlib")
    rc = main(_base(tmp_path) + ["-o", str(tmp_path), "--frames", "15", "stream"])
    assert rc == 0 and (tmp_path / "waterfall.png").exists()


def test_generate_synthetic_plot_writes_png(tmp_path):
    pytest.importorskip("matplotlib")
    rc = main(_base(tmp_path) + ["-o", str(tmp_path), "--plot", "generate-synthetic"])
    assert rc == 0 and (tmp_path / "synthetic.png").exists()


def test_init_config_writes_validates_and_force(tmp_path):
    target = tmp_path / "config.ini"
    assert main(["-o", str(target), "init-config"]) == 0
    assert target.exists() and "[camera]" in target.read_text()
    assert main(["-o", str(target), "init-config"]) == 1            # refuses overwrite
    assert main(["--force", "-o", str(target), "init-config"]) == 0  # --force overwrites
    assert main(["--config", str(target), "--set", "logging.console=false",
                 "--set", f"logging.directory={tmp_path}/logs", "validate-config"]) == 0
