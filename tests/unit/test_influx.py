"""Tests for the optional InfluxDB telemetry sink (data.influx).

No network: the line-protocol builder is pure, and the sink takes an injectable
``poster`` so we assert the exact URL / headers / body without a live server."""

from config.loader import load_config
from data.factory import IdentityStampingSink, build_sink
from data.influx import (
    InfluxConfig,
    InfluxDbSpectrumSink,
    build_line_protocol,
    summarize_features,
)
from data.sinks import CsvSpectrumSink, MultiSink
from processing.spectrum import Spectrum


def _spec(**meta):
    return Spectrum(wavelengths=[400.0, 500.0, 600.0], intensities=[1.0, 5.0, 2.0],
                    metadata=meta)


# --------------------------------------------------------------------------- #
# Line protocol
# --------------------------------------------------------------------------- #
def test_line_protocol_carries_locked_core_tags_and_fields():
    """Tags and fields are both emitted sorted (canonical line protocol)."""
    line = build_line_protocol(_spec(source="synthetic"), "spectrum",
                               timestamp_ns=1_700_000_000_000_000_000)
    assert line == (
        "spectrum,backend=synthetic-generator,calibration_id=none,"
        "pixel_format=none,source=synthetic "
        "calibrated=true,n_samples=3i,peak_intensity=5.0,simulated=true,"
        "total_flux=8.0 "
        "1700000000000000000"
    )


def test_backend_distinguishes_synthetic_camera_from_generator():
    """A simulated frame and a synthesized spectrum are different backends.

    A calibration fitted on one is not valid on the other, so they must not
    share a series.
    """
    frame_based = Spectrum(
        wavelengths=[], intensities=[1.0, 2.0],
        metadata={"source": "synthetic",
                  "frame": {"backend": "synthetic-camera", "pixel_format": "GRAY"}},
    )
    assert "backend=synthetic-camera" in build_line_protocol(frame_based, "spectrum")
    assert "backend=synthetic-generator" in build_line_protocol(
        _spec(source="synthetic"), "spectrum"
    )


def test_simulated_flag_tracks_backend():
    real = Spectrum(wavelengths=[], intensities=[1.0],
                    metadata={"source": "usb", "frame": {"backend": "usb"}})
    assert "simulated=false" in build_line_protocol(real, "spectrum")
    assert "simulated=true" in build_line_protocol(_spec(source="synthetic"), "spectrum")


def test_capture_uuid_is_a_field_not_a_tag():
    """The cross-store join key must never become an indexed tag."""
    line = build_line_protocol(_spec(source="usb", capture_uuid="abc-123"), "spectrum")
    tag_part, field_part = line.split(" ")[0], line.split(" ")[1]
    assert "capture_uuid" not in tag_part
    assert 'capture_uuid="abc-123"' in field_part


def test_source_defaults_to_unknown():
    assert ",source=unknown " in build_line_protocol(_spec(), "spectrum")


def test_uncalibrated_spectrum_reports_calibrated_false():
    sp = Spectrum(wavelengths=[], intensities=[1.0, 2.0], metadata={"source": "camera"})
    assert "calibrated=false" in build_line_protocol(sp, "spectrum")


def test_extra_tags_and_fields_are_merged():
    line = build_line_protocol(_spec(source="camera"), "spectrum",
                               extra_tags={"instrument": "ov9281"},
                               extra_fields={"n_peaks": 4, "strongest_nm": 811.4})
    assert "instrument=ov9281" in line
    assert "n_peaks=4i" in line and "strongest_nm=811.4" in line


def test_line_protocol_escaping():
    sp = _spec(source="lab bench,1")
    line = build_line_protocol(sp, "my spectrum")
    assert line.startswith("my\\ spectrum,")          # measurement space escaped
    assert "source=lab\\ bench\\,1" in line            # tag space + comma escaped


def test_timestamp_precision_scaling():
    sp = _spec(source="synthetic")
    ns = 1_000_000_000  # 1 second in ns
    assert build_line_protocol(sp, "s", timestamp_ns=ns, precision="s").endswith(" 1")
    assert build_line_protocol(sp, "s", timestamp_ns=ns, precision="ms").endswith(" 1000")


def test_summarize_features():
    class _Peak:
        def __init__(self, pixel, wavelength, intensity, fwhm_nm, snr):
            self.pixel, self.wavelength, self.intensity = pixel, wavelength, intensity
            self.fwhm, self.fwhm_nm, self.snr = 3.0, fwhm_nm, snr

    class _Result:
        peaks = [_Peak(100, 405.0, 50.0, 0.5, 30.0), _Peak(300, 811.0, 200.0, 0.6, 90.0)]

    feats = summarize_features(_Result())
    assert feats["n_peaks"] == 2
    assert feats["strongest_nm"] == 811.0        # strongest by intensity
    assert feats["strongest_snr"] == 90.0


# --------------------------------------------------------------------------- #
# Config + endpoints
# --------------------------------------------------------------------------- #
def test_endpoint_per_version():
    v1 = InfluxConfig(version=1, url="http://nms:8086", database="db", username="u", password="p")
    url1, h1 = v1.write_endpoint()
    assert url1.startswith("http://nms:8086/write?") and "db=db" in url1 and "u=u" in url1
    assert h1 == {}

    for v in (2, 3):                              # v3 rides the v2 write API
        cfg = InfluxConfig(version=v, url="http://nms:8086", org="home", bucket="b", token="TOK")
        url, h = cfg.write_endpoint()
        assert "/api/v2/write?" in url and "org=home" in url and "bucket=b" in url
        assert h == {"Authorization": "Token TOK"}


def test_from_section_reads_config():
    cfg = InfluxConfig.from_section(
        load_config(overrides=["influx.enabled=true", "influx.version=1",
                               "influx.url=http://nms:8086/"]).section("influx"))
    assert cfg.enabled is True and cfg.version == 1
    assert cfg.url == "http://nms:8086"          # trailing slash stripped


# --------------------------------------------------------------------------- #
# Sink behaviour (injected poster — no network)
# --------------------------------------------------------------------------- #
def test_sink_posts_url_headers_and_body():
    captured = {}

    def poster(url, body, headers, timeout):
        captured.update(url=url, body=body.decode(), headers=headers, timeout=timeout)
        return 204

    cfg = InfluxConfig(enabled=True, version=2, url="http://nms:8086",
                       org="home", bucket="spec", token="TOK")
    out = InfluxDbSpectrumSink(cfg, poster=poster).write(_spec(source="synthetic"))
    assert "/api/v2/write?" in captured["url"]
    assert captured["headers"]["Authorization"] == "Token TOK"
    assert captured["body"].startswith("spectrum,backend=synthetic-generator,")
    assert ",source=synthetic " in captured["body"]
    assert out == captured["body"]


def test_dry_run_does_not_post():
    posted = []
    cfg = InfluxConfig(version=2, dry_run=True)
    line = InfluxDbSpectrumSink(cfg, poster=lambda *a: posted.append(a)).write(_spec(source="camera"))
    assert posted == []                          # never called
    assert line.startswith("spectrum,")
    assert ",source=camera " in line


def test_write_failure_is_swallowed():
    def boom(*a):
        raise ConnectionError("server down")

    cfg = InfluxConfig(enabled=True, version=2, url="http://nms:8086")
    # Telemetry must never break an acquisition — returns None, raises nothing.
    assert InfluxDbSpectrumSink(cfg, poster=boom).write(_spec(source="camera")) is None


# --------------------------------------------------------------------------- #
# build_sink factory / tee
# --------------------------------------------------------------------------- #
def test_build_sink_csv_only_when_disabled(tmp_path):
    cfg = load_config(overrides=["influx.enabled=false", "sqlite.enabled=false"])
    sink = build_sink(cfg, tmp_path)
    # Always wrapped, so capture identity is assigned exactly once regardless
    # of how many backends are active.
    assert isinstance(sink, IdentityStampingSink)
    assert isinstance(sink.inner, CsvSpectrumSink)


def test_build_sink_tees_when_enabled(tmp_path):
    cfg = load_config(overrides=["influx.enabled=true", "influx.dry_run=true"])
    sink = build_sink(cfg, tmp_path)
    assert isinstance(sink.inner, MultiSink)
    # Primary (CSV) handle is returned, and the CSV file is actually written.
    path = sink.write(_spec(source="synthetic"), name="acq")
    assert str(path).endswith("acq.csv")
    assert (tmp_path / "acq.csv").exists()


def test_identity_is_assigned_once_and_shared(tmp_path):
    """Both stores must record the same capture id for the same capture."""
    cfg = load_config(overrides=["influx.enabled=true", "influx.dry_run=true"])
    spectrum = _spec(source="synthetic")
    build_sink(cfg, tmp_path).write(spectrum, name="acq")
    assert "capture_uuid" in spectrum.metadata
    assert "timestamp_ns" in spectrum.metadata


def test_existing_identity_is_not_overwritten(tmp_path):
    cfg = load_config(overrides=["influx.enabled=false", "sqlite.enabled=false"])
    spectrum = _spec(source="usb", capture_uuid="preset-id", timestamp_ns=42)
    build_sink(cfg, tmp_path).write(spectrum, name="acq")
    assert spectrum.metadata["capture_uuid"] == "preset-id"
    assert spectrum.metadata["timestamp_ns"] == 42
