"""Tests for the SQLite store (data.sqlite).

Covers the array round-trip, the locked-core refusal behaviour, and the
generated user-column migrations.
"""

import sqlite3

import pytest

from config.loader import load_config
from data.factory import build_sink
from data.schema_core import CORE_SCHEMA_VERSION
from data.sqlite import (
    SqliteConfig,
    SqliteSpectrumSink,
    SqliteStore,
    pack_array,
    read_spectrum,
    unpack_array,
)
from data.user_schema import parse_manifest
from errors import PersistenceError
from processing.spectrum import Spectrum


def _cfg(tmp_path, **kw):
    return SqliteConfig(enabled=True, path=str(tmp_path / "spec.db"), **kw)


def _spec(**meta):
    meta.setdefault("source", "usb")
    meta.setdefault("frame", {"backend": "usb", "pixel_format": "BGR",
                              "width": 1280, "height": 800})
    return Spectrum(
        wavelengths=[800.0, 810.4, 811.5],
        intensities=[10.0, 250.0, 240.0],
        metadata=meta,
    )


# --------------------------------------------------------------------------- #
# Array codec
# --------------------------------------------------------------------------- #
def test_array_round_trip_is_exact():
    values = [0.0, 1.5, -2.25, 1e-9, 812.3456789]
    assert unpack_array(pack_array(values)) == values


def test_empty_and_null_blobs():
    assert unpack_array(None) == []
    assert unpack_array(pack_array([])) == []


def test_encoding_is_little_endian_float64():
    """Explicit byte order keeps a .db file portable between Pi and workstation."""
    assert pack_array([1.0]) == b"\x00\x00\x00\x00\x00\x00\xf0?"
    assert len(pack_array([1.0, 2.0, 3.0])) == 24


# --------------------------------------------------------------------------- #
# Core schema
# --------------------------------------------------------------------------- #
def test_creates_schema_and_stamps_version(tmp_path):
    with SqliteStore(_cfg(tmp_path)) as store:
        conn = store.connect()
        tables = {
            r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"capture", "spectrum", "calibration", "feature",
                "capture_ext", "schema_meta", "user_column"} <= tables
        assert int(SqliteStore._meta_get(conn, "core_schema_version")) == CORE_SCHEMA_VERSION


def test_refuses_to_open_a_store_from_a_different_core_version(tmp_path):
    cfg = _cfg(tmp_path)
    SqliteStore(cfg).connect().close()
    conn = sqlite3.connect(cfg.path)
    conn.execute("UPDATE schema_meta SET value = ? WHERE key = 'core_schema_version'",
                 (CORE_SCHEMA_VERSION + 1,))
    conn.commit()
    conn.close()

    with pytest.raises(PersistenceError, match="Refusing to open"):
        SqliteStore(cfg).connect()


def test_capture_records_backend_provenance(tmp_path):
    store = SqliteStore(_cfg(tmp_path))
    uuid = store.insert_capture(_spec())
    row = store.connect().execute(
        "SELECT * FROM capture WHERE uuid = ?", (uuid,)
    ).fetchone()
    assert row["backend"] == "usb"
    assert row["source"] == "usb"
    assert row["simulated"] == 0
    assert row["pixel_format"] == "BGR"
    assert row["frame_width"] == 1280
    assert row["calibrated"] == 1
    assert row["n_samples"] == 3
    store.close()


def test_synthetic_generator_is_flagged_simulated(tmp_path):
    store = SqliteStore(_cfg(tmp_path))
    spectrum = Spectrum(wavelengths=[400.0], intensities=[1.0],
                        metadata={"source": "synthetic", "generator": "synthgen-1"})
    uuid = store.insert_capture(spectrum)
    row = store.connect().execute(
        "SELECT backend, simulated FROM capture WHERE uuid = ?", (uuid,)
    ).fetchone()
    assert row["backend"] == "synthetic-generator"
    assert row["simulated"] == 1
    store.close()


def test_spectrum_round_trips_through_the_store(tmp_path):
    cfg = _cfg(tmp_path)
    store = SqliteStore(cfg)
    original = _spec()
    uuid = store.insert_capture(original)
    store.close()

    loaded = read_spectrum(cfg.path, uuid)
    assert list(loaded.intensities) == list(original.intensities)
    assert list(loaded.wavelengths) == list(original.wavelengths)
    assert loaded.metadata["backend"] == "usb"
    assert loaded.metadata["uuid"] == uuid


def test_uncalibrated_spectrum_stores_a_pixel_axis(tmp_path):
    cfg = _cfg(tmp_path)
    store = SqliteStore(cfg)
    uuid = store.insert_capture(
        Spectrum(wavelengths=[], intensities=[1.0, 2.0, 3.0],
                 metadata={"source": "usb", "frame": {"backend": "usb"}})
    )
    row = store.connect().execute(
        "SELECT axis_kind, axis FROM spectrum s JOIN capture c ON c.id = s.capture_id "
        "WHERE c.uuid = ?", (uuid,)
    ).fetchone()
    assert row["axis_kind"] == "pixel"
    assert row["axis"] is None            # implicit range(n); not stored twice
    store.close()


def test_features_are_stored_as_scalars(tmp_path):
    store = SqliteStore(_cfg(tmp_path))
    uuid = store.insert_capture(
        _spec(), features={"n_peaks": 2, "strongest_nm": 811.5, "note": "ignored"}
    )
    rows = dict(
        store.connect().execute(
            "SELECT f.name, f.value FROM feature f JOIN capture c ON c.id = f.capture_id "
            "WHERE c.uuid = ?", (uuid,)
        ).fetchall()
    )
    assert rows == {"n_peaks": 2.0, "strongest_nm": 811.5}   # non-numeric skipped
    store.close()


def test_calibration_row_is_deduplicated(tmp_path):
    store = SqliteStore(_cfg(tmp_path))
    meta = {"source": "usb", "frame": {"backend": "usb", "width": 1280},
            "calibration_coefficients": [1.0, 2.0, 3.0], "calibration_order": 2}
    for _ in range(3):
        store.insert_capture(_spec(**dict(meta)))
    count = store.connect().execute("SELECT COUNT(*) AS n FROM calibration").fetchone()["n"]
    assert count == 1                      # same fit -> one calibration record
    store.close()


def test_different_calibration_yields_a_new_record(tmp_path):
    store = SqliteStore(_cfg(tmp_path))
    base = {"source": "usb", "frame": {"backend": "usb", "width": 1280},
            "calibration_order": 2}
    store.insert_capture(_spec(calibration_coefficients=[1.0, 2.0, 3.0], **base))
    store.insert_capture(_spec(calibration_coefficients=[1.0, 2.0, 3.1], **base))
    ids = [r["calibration_id"] for r in
           store.connect().execute("SELECT calibration_id FROM calibration")]
    assert len(set(ids)) == 2              # recalibration is visible, not blended
    store.close()


# --------------------------------------------------------------------------- #
# User columns / generated migrations
# --------------------------------------------------------------------------- #
MANIFEST = """
[bench_humidity]
type = float
unit = %RH

[grating]
type    = str
role    = tag
allowed = 1000lpmm, 1200lpmm
"""


def test_user_columns_are_generated_from_the_manifest(tmp_path):
    schema = parse_manifest(MANIFEST)
    with SqliteStore(_cfg(tmp_path), schema) as store:
        columns = {
            r["name"] for r in store.connect().execute("PRAGMA table_info(capture_ext)")
        }
    assert {"capture_id", "bench_humidity", "grating"} == columns


def test_adding_a_field_migrates_an_existing_store(tmp_path):
    """Extending the schema must be trivial: reopen and the column appears."""
    cfg = _cfg(tmp_path)
    SqliteStore(cfg, parse_manifest(MANIFEST)).connect().close()

    extended = parse_manifest(MANIFEST + "\n[hv_rail_volts]\ntype = float\nunit = V\n")
    with SqliteStore(cfg, extended) as store:
        columns = {
            r["name"] for r in store.connect().execute("PRAGMA table_info(capture_ext)")
        }
    assert "hv_rail_volts" in columns


def test_retyping_an_existing_field_is_refused(tmp_path):
    """Silently reinterpreting stored values is the thing we will not do."""
    cfg = _cfg(tmp_path)
    SqliteStore(cfg, parse_manifest("[shots]\ntype = int\n")).connect().close()

    with pytest.raises(PersistenceError, match="would reinterpret existing rows"):
        SqliteStore(cfg, parse_manifest("[shots]\ntype = str\n")).connect()


def test_removing_a_field_is_allowed_and_retains_the_column(tmp_path):
    cfg = _cfg(tmp_path)
    SqliteStore(cfg, parse_manifest(MANIFEST)).connect().close()
    with SqliteStore(cfg, parse_manifest("[bench_humidity]\ntype = float\n")) as store:
        columns = {
            r["name"] for r in store.connect().execute("PRAGMA table_info(capture_ext)")
        }
    assert "grating" in columns            # retained (SQLite cannot drop pre-3.35)


def test_user_values_are_written_and_read_back(tmp_path):
    cfg = _cfg(tmp_path)
    schema = parse_manifest(MANIFEST)
    sink = SqliteSpectrumSink(cfg, user_schema=schema)
    uuid = sink.write(
        _spec(user_fields={"bench_humidity": 41.2, "grating": "1200lpmm"})
    )
    sink.close()

    loaded = read_spectrum(cfg.path, uuid)
    assert loaded.metadata["user_fields"] == {
        "bench_humidity": 41.2, "grating": "1200lpmm",
    }


def test_invalid_user_value_aborts_the_write(tmp_path):
    cfg = _cfg(tmp_path)
    sink = SqliteSpectrumSink(cfg, user_schema=parse_manifest(MANIFEST))
    with pytest.raises(PersistenceError, match="not one of"):
        sink.write(_spec(user_fields={"grating": "600lpmm"}))
    rows = sink.store.connect().execute("SELECT COUNT(*) AS n FROM capture").fetchone()
    assert rows["n"] == 0                  # nothing half-written
    sink.close()


# --------------------------------------------------------------------------- #
# Factory integration
# --------------------------------------------------------------------------- #
def test_factory_tees_csv_and_sqlite(tmp_path):
    db = tmp_path / "run.db"
    config = load_config(overrides=[
        "sqlite.enabled=true", f"sqlite.path={db}", "influx.enabled=false",
    ])
    sink = build_sink(config, tmp_path)
    path = sink.write(_spec(), name="acq")

    assert str(path).endswith("acq.csv")   # CSV stays the primary handle
    assert (tmp_path / "acq.csv").exists()
    assert db.exists()

    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0] == 1
    finally:
        conn.close()


def test_gui_snapshot_routes_through_every_enabled_store(tmp_path):
    """The GUI is the primary interface; its snapshots must not bypass the stores."""
    from ui.live import snapshot_spectrum

    db = tmp_path / "snap.db"
    config = load_config(overrides=[
        "sqlite.enabled=true", f"sqlite.path={db}", "influx.enabled=false",
    ])
    path = snapshot_spectrum(
        _spec(), tmp_path, name="snap", sink=build_sink(config, tmp_path)
    )
    assert str(path).endswith("snap.csv")
    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0] == 1
    finally:
        conn.close()


def test_snapshot_without_a_sink_still_writes_csv(tmp_path):
    """Headless/back-compat path: no config, no stores, still a CSV."""
    from ui.live import snapshot_spectrum

    path = snapshot_spectrum(_spec(), tmp_path, name="snap")
    assert (tmp_path / "snap.csv").exists()
    assert str(path).endswith("snap.csv")


def test_sqlite_and_influx_agree_on_capture_identity(tmp_path):
    """The join key that makes a Grafana point resolvable to its SQLite row."""
    db = tmp_path / "run.db"
    config = load_config(overrides=[
        "sqlite.enabled=true", f"sqlite.path={db}",
        "influx.enabled=true", "influx.dry_run=true",
    ])
    spectrum = _spec()
    build_sink(config, tmp_path).write(spectrum, name="acq")

    stamped = spectrum.metadata["capture_uuid"]
    conn = sqlite3.connect(str(db))
    try:
        stored = conn.execute("SELECT uuid FROM capture").fetchone()[0]
    finally:
        conn.close()
    assert stored == stamped
