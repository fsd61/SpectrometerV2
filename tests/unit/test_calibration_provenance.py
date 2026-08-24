"""Calibration provenance end-to-end (schema_core + live engine + stores).

A record may not claim to be calibrated without naming *which* calibration
produced it. These tests pin that invariant across the pieces that enforce it.
"""

import sqlite3

import pytest

from calibration.wavelength import calibrate
from data.schema_core import build_core_record, calibration_fingerprint
from data.sqlite import SqliteConfig, SqliteStore
from processing.spectrum import Spectrum
from ui.live import LiveEngine


class _Source:
    """Minimal FrameSource: uncalibrated frames, like the camera path."""

    def __init__(self, n=16):
        self.n = n

    def next_spectrum(self):
        return Spectrum(
            wavelengths=[], intensities=[float(i) for i in range(self.n)],
            metadata={"source": "usb", "frame": {"backend": "usb"}},
        )

    def close(self):
        pass


# --------------------------------------------------------------------------- #
# Fingerprint
# --------------------------------------------------------------------------- #
def test_fingerprint_is_stable_for_the_same_fit():
    coefficients = [1e-6, 0.5, 400.0]
    assert calibration_fingerprint(coefficients, 2, 1280) == calibration_fingerprint(
        coefficients, 2, 1280
    )


@pytest.mark.parametrize(
    "coefficients, order, width",
    [
        ([1e-6, 0.5, 400.1], 2, 1280),   # coefficients changed
        ([1e-6, 0.5, 400.0], 3, 1280),   # order changed
        ([1e-6, 0.5, 400.0], 2, 800),    # sensor width changed
    ],
)
def test_any_change_to_the_fit_changes_the_fingerprint(coefficients, order, width):
    """Every geometry change voids the prior calibration; that must be visible."""
    baseline = calibration_fingerprint([1e-6, 0.5, 400.0], 2, 1280)
    assert calibration_fingerprint(coefficients, order, width) != baseline


def test_uncalibrated_has_no_fingerprint():
    assert calibration_fingerprint(None) is None


# --------------------------------------------------------------------------- #
# Live engine
# --------------------------------------------------------------------------- #
def test_applied_calibration_stamps_its_identity():
    engine = LiveEngine(source=_Source())
    result = calibrate([1, 8, 15], [400.0, 600.0, 800.0], 16)
    engine.set_calibration(result.wavelengths, result)

    spectrum, _ = engine.step()
    assert spectrum.metadata["calibration"] == "applied"
    assert spectrum.metadata["calibration_id"] == calibration_fingerprint(
        [float(c) for c in result.coefficients], result.order, len(result.wavelengths)
    )
    assert spectrum.metadata["calibration_order"] == result.order


def test_clearing_calibration_clears_its_identity():
    engine = LiveEngine(source=_Source())
    result = calibrate([1, 8, 15], [400.0, 600.0, 800.0], 16)
    engine.set_calibration(result.wavelengths, result)
    engine.clear_calibration()

    spectrum, _ = engine.step()
    assert engine.calibration_meta == {}
    assert "calibration_id" not in spectrum.metadata
    assert len(spectrum.wavelengths) == 0


def test_axis_only_calibration_still_works():
    """Backward compatible: passing just the axis is allowed, id is simply absent."""
    engine = LiveEngine(source=_Source())
    engine.set_calibration([400.0 + i for i in range(16)])
    spectrum, _ = engine.step()
    assert len(spectrum.wavelengths) == 16
    assert "calibration_id" not in spectrum.metadata


# --------------------------------------------------------------------------- #
# Reaching the stores
# --------------------------------------------------------------------------- #
def test_core_record_carries_the_calibration_id():
    engine = LiveEngine(source=_Source())
    result = calibrate([1, 8, 15], [400.0, 600.0, 800.0], 16)
    engine.set_calibration(result.wavelengths, result)
    spectrum, _ = engine.step()

    record = build_core_record(spectrum, uuid="u", captured_at_ns=1)
    assert record.calibrated is True
    assert record.calibration_id == spectrum.metadata["calibration_id"]
    assert record.backend == "usb"


def test_recalibration_is_visible_in_the_store(tmp_path):
    """Two different fits must never look like one continuous series."""
    cfg = SqliteConfig(enabled=True, path=str(tmp_path / "spec.db"))
    engine = LiveEngine(source=_Source())
    store = SqliteStore(cfg)

    for wavelengths in ([400.0, 600.0, 800.0], [400.0, 600.0, 805.0]):
        result = calibrate([1, 8, 15], wavelengths, 16)
        engine.set_calibration(result.wavelengths, result)
        spectrum, _ = engine.step()
        store.insert_capture(spectrum)

    conn = store.connect()
    ids = [r["calibration_id"] for r in conn.execute("SELECT calibration_id FROM capture")]
    assert len(set(ids)) == 2
    assert conn.execute("SELECT COUNT(*) AS n FROM calibration").fetchone()["n"] == 2
    store.close()


def test_calibration_table_records_the_fit_and_its_backend(tmp_path):
    cfg = SqliteConfig(enabled=True, path=str(tmp_path / "spec.db"))
    engine = LiveEngine(source=_Source())
    result = calibrate([1, 8, 15], [400.0, 600.0, 800.0], 16)
    engine.set_calibration(result.wavelengths, result)
    spectrum, _ = engine.step()

    store = SqliteStore(cfg)
    store.insert_capture(spectrum)
    store.close()

    conn = sqlite3.connect(cfg.path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM calibration").fetchone()
    finally:
        conn.close()
    assert row["backend"] == "usb"
    assert row["poly_order"] == result.order
    assert row["coefficients"] is not None
