"""Data persistence: raw frames, spectra, metadata, calibration, user extensions.

Spectra are written through a pluggable ``SpectrumSink``, so storage backends
are added without touching the scientific core (DATA-001, DATA-002).

The layer is split three ways:

* :mod:`data.schema_core` — the **locked** core schema. Closed to extension;
  carries capture identity, backend provenance and calibration linkage.
* :mod:`data.user_schema` — the **open** extension point. A declarative INI
  manifest (plus an optional hook) defines extra fields, validated once and
  applied to every backend.
* Backends — :mod:`data.sinks` (CSV), :mod:`data.sqlite` (system of record),
  :mod:`data.influx` (time-series telemetry) — assembled by
  :mod:`data.factory`.

SQLite and InfluxDB are deliberately *not* interchangeable: SQLite holds
spectra, calibrations and provenance; InfluxDB holds scalar metrics over time.
"""

from .schema_core import CORE_SCHEMA_VERSION, CoreRecord, build_core_record
from .sinks import CsvSpectrumSink, MultiSink, NullSink, SpectrumSink, read_csv_spectrum
from .user_schema import UserField, UserSchema

__all__ = [
    "SpectrumSink",
    "CsvSpectrumSink",
    "MultiSink",
    "NullSink",
    "read_csv_spectrum",
    "CORE_SCHEMA_VERSION",
    "CoreRecord",
    "build_core_record",
    "UserSchema",
    "UserField",
]
