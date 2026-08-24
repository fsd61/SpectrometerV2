"""SQLite persistence sink — the queryable system of record.

Complements, rather than duplicates, the InfluxDB sink. The two stores are not
interchangeable backends behind one interface; they hold different data because
they are good at different things:

* **SQLite** holds what must be *kept and re-examined*: the spectrum arrays
  themselves, calibration records, and full per-capture provenance.
* **InfluxDB** holds what must be *watched over time*: scalar features and
  derived metrics, for Grafana.

Forcing a 1280-sample spectrum into a time-series database (as 1280 fields, or
1280 points) is what this split exists to avoid.

**Array storage.** Each spectrum is one row, with intensities (and the
wavelength axis, when calibrated) packed as little-endian ``float64`` BLOBs.
Explicit endianness keeps a database file portable between the Pi and the
workstation. The alternative — one row per sample — is directly queryable but
multiplies row count by the sample width, so a single session's captures run to
millions of rows. Use :func:`read_spectrum` or the ``export`` path to get arrays
back out.

**Schema integrity.** The store stamps the core schema version and the user
manifest fingerprint on creation and verifies both on every open. A core
version mismatch, or a user field whose declared type has changed, refuses to
open rather than writing records that cannot be interpreted later — the same
discipline that governs backend/calibration provenance.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid as uuid_mod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from errors import PersistenceError
from processing.spectrum import Spectrum

from .schema_core import CORE_SCHEMA_VERSION, build_core_record
from .sinks import SpectrumSink
from .user_schema import UserSchema

logger = logging.getLogger(__name__)

#: On-disk array encoding. Explicit byte order for cross-machine portability.
_DTYPE = "<f8"

CORE_DDL = (
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS calibration (
        id              INTEGER PRIMARY KEY,
        calibration_id  TEXT NOT NULL UNIQUE,
        created_at_ns   INTEGER NOT NULL,
        backend         TEXT NOT NULL,
        poly_order      INTEGER,
        coefficients    TEXT,
        r_squared       REAL,
        width           INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS capture (
        id              INTEGER PRIMARY KEY,
        uuid            TEXT NOT NULL UNIQUE,
        captured_at_ns  INTEGER NOT NULL,
        source          TEXT NOT NULL,
        backend         TEXT NOT NULL,
        simulated       INTEGER NOT NULL,
        pixel_format    TEXT,
        frame_width     INTEGER,
        frame_height    INTEGER,
        center_row      INTEGER,
        average_rows    INTEGER,
        n_samples       INTEGER NOT NULL,
        calibrated      INTEGER NOT NULL,
        calibration_id  TEXT,
        schema_version  INTEGER NOT NULL,
        label           TEXT,
        metadata_json   TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spectrum (
        capture_id  INTEGER PRIMARY KEY REFERENCES capture(id) ON DELETE CASCADE,
        axis_kind   TEXT NOT NULL,
        dtype       TEXT NOT NULL,
        axis        BLOB,
        intensities BLOB NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feature (
        capture_id INTEGER NOT NULL REFERENCES capture(id) ON DELETE CASCADE,
        name       TEXT NOT NULL,
        value      REAL,
        PRIMARY KEY (capture_id, name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS capture_ext (
        capture_id INTEGER PRIMARY KEY REFERENCES capture(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_column (
        name TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        role TEXT NOT NULL,
        unit TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_capture_time ON capture(captured_at_ns)",
    "CREATE INDEX IF NOT EXISTS idx_capture_backend ON capture(backend)",
    "CREATE INDEX IF NOT EXISTS idx_capture_calibration ON capture(calibration_id)",
    "CREATE INDEX IF NOT EXISTS idx_feature_name ON feature(name)",
)


@dataclass
class SqliteConfig:
    """Resolved ``[sqlite]`` settings."""

    enabled: bool = False
    path: str = "data/spectrometer.db"
    store_metadata_json: bool = True
    timeout: float = 5.0
    journal_mode: str = "wal"

    @classmethod
    def from_section(cls, section) -> "SqliteConfig":
        g = section.get
        return cls(
            enabled=bool(g("enabled", False)),
            path=str(g("path", "data/spectrometer.db")),
            store_metadata_json=bool(g("store_metadata_json", True)),
            timeout=float(g("timeout", 5.0)),
            journal_mode=str(g("journal_mode", "wal")),
        )


# --------------------------------------------------------------------------- #
# Array codec
# --------------------------------------------------------------------------- #
def pack_array(values) -> bytes:
    """Pack a numeric sequence to a little-endian float64 BLOB."""
    return np.asarray(values, dtype=_DTYPE).tobytes()


def unpack_array(blob, dtype: str = _DTYPE) -> list:
    """Unpack a BLOB written by :func:`pack_array`."""
    if blob is None:
        return []
    return [float(v) for v in np.frombuffer(blob, dtype=dtype)]


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
class SqliteStore:
    """Owns the connection, the schema check, and the generated migrations."""

    def __init__(self, config: SqliteConfig, user_schema: Optional[UserSchema] = None):
        self.config = config
        self.user_schema = user_schema or UserSchema()
        self._conn: Optional[sqlite3.Connection] = None

    # -- lifecycle --------------------------------------------------------- #
    def connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        path = Path(self.config.path)
        if path.parent != Path(""):
            path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(str(path), timeout=self.config.timeout)
        except sqlite3.Error as exc:
            raise PersistenceError(f"cannot open SQLite store {path}: {exc}") from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if self.config.journal_mode:
            # WAL lets a Grafana/notebook reader query while acquisition writes.
            conn.execute(f"PRAGMA journal_mode = {self.config.journal_mode}")
        try:
            self._create_core(conn)
            self._verify_core_version(conn)
            self._migrate_user_columns(conn)
            conn.commit()
        except Exception:
            conn.close()
            raise
        self._conn = conn
        return conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "SqliteStore":
        self.connect()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- schema ------------------------------------------------------------ #
    @staticmethod
    def _create_core(conn) -> None:
        for statement in CORE_DDL:
            conn.execute(statement)

    @staticmethod
    def _meta_get(conn, key: str) -> Optional[str]:
        row = conn.execute("SELECT value FROM schema_meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    @staticmethod
    def _meta_set(conn, key: str, value) -> None:
        conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    def _verify_core_version(self, conn) -> None:
        stored = self._meta_get(conn, "core_schema_version")
        if stored is None:
            self._meta_set(conn, "core_schema_version", CORE_SCHEMA_VERSION)
            self._meta_set(conn, "created_at_ns", time.time_ns())
            return
        if int(stored) != CORE_SCHEMA_VERSION:
            raise PersistenceError(
                f"SQLite store {self.config.path} was written with core schema "
                f"version {stored}, but this build expects {CORE_SCHEMA_VERSION}. "
                f"Refusing to open: records written under a different core schema "
                f"cannot be reinterpreted safely. Point [sqlite] path at a new "
                f"file, or migrate the existing one deliberately."
            )

    def _migrate_user_columns(self, conn) -> None:
        """Add columns for newly declared user fields; refuse on retypes.

        Additive changes are applied automatically — that is what makes
        extending the schema trivial. A *changed type* on an existing column is
        refused, because the stored values would silently change meaning.
        Removing a declaration is allowed; the column is retained (SQLite cannot
        drop columns before 3.35) and simply stops being written.
        """
        recorded = {
            row["name"]: dict(row)
            for row in conn.execute("SELECT name, type, role, unit FROM user_column")
        }
        declared = {f.name: f for f in self.user_schema.sqlite_fields()}

        conflicts = [
            f"{name}: stored as {recorded[name]['type']}, manifest now says {field.type}"
            for name, field in declared.items()
            if name in recorded and recorded[name]["type"] != field.type
        ]
        if conflicts:
            raise PersistenceError(
                "user field type change would reinterpret existing rows in "
                f"{self.config.path}:\n  - " + "\n  - ".join(conflicts)
                + "\nRename the field, or point [sqlite] path at a new file."
            )

        existing_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(capture_ext)")
        }
        for name, field in declared.items():
            if name not in existing_columns:
                conn.execute(
                    f'ALTER TABLE capture_ext ADD COLUMN "{name}" {field.sql_type}'
                )
                logger.info("Added user column capture_ext.%s (%s)", name, field.sql_type)
            conn.execute(
                "INSERT INTO user_column(name, type, role, unit) VALUES(?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET role = excluded.role, unit = excluded.unit",
                (name, field.type, field.role, field.unit),
            )

        for name in recorded:
            if name not in declared:
                logger.info(
                    "user column capture_ext.%s is no longer declared; retained "
                    "but no longer written.", name,
                )
        self._meta_set(conn, "user_manifest_fingerprint", self.user_schema.fingerprint())

    # -- writes ------------------------------------------------------------ #
    def insert_capture(
        self,
        spectrum: Spectrum,
        *,
        label: Optional[str] = None,
        user_values: Optional[dict] = None,
        features: Optional[dict] = None,
    ) -> str:
        """Insert one capture and return its UUID."""
        conn = self.connect()
        meta = dict(spectrum.metadata or {})
        ts = meta.get("timestamp_ns")
        captured_at_ns = int(ts) if ts is not None else time.time_ns()
        # Honour an identity already assigned by the sink factory, so this row
        # can be joined to the matching InfluxDB point.
        record = build_core_record(
            spectrum,
            uuid=str(meta.get("capture_uuid") or uuid_mod.uuid4()),
            captured_at_ns=captured_at_ns,
        )
        try:
            with conn:  # one transaction; a partial capture is never visible
                self._insert_calibration(conn, record, meta)
                cursor = conn.execute(
                    """
                    INSERT INTO capture (
                        uuid, captured_at_ns, source, backend, simulated,
                        pixel_format, frame_width, frame_height, center_row,
                        average_rows, n_samples, calibrated, calibration_id,
                        schema_version, label, metadata_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        record.uuid, record.captured_at_ns, record.source,
                        record.backend, int(record.simulated), record.pixel_format,
                        record.frame_width, record.frame_height, record.center_row,
                        record.average_rows, record.n_samples, int(record.calibrated),
                        record.calibration_id, record.schema_version, label,
                        json.dumps(meta, default=str)
                        if self.config.store_metadata_json else None,
                    ),
                )
                capture_id = int(cursor.lastrowid)

                calibrated = bool(spectrum.wavelengths)
                conn.execute(
                    "INSERT INTO spectrum (capture_id, axis_kind, dtype, axis, intensities) "
                    "VALUES (?,?,?,?,?)",
                    (
                        capture_id,
                        "wavelength_nm" if calibrated else "pixel",
                        _DTYPE,
                        pack_array(spectrum.wavelengths) if calibrated else None,
                        pack_array(spectrum.intensities),
                    ),
                )

                for name, value in (features or {}).items():
                    try:
                        numeric = float(value)
                    except (TypeError, ValueError):
                        continue  # non-scalar features live in metadata_json
                    conn.execute(
                        "INSERT INTO feature (capture_id, name, value) VALUES (?,?,?)",
                        (capture_id, str(name), numeric),
                    )

                self._insert_ext(conn, capture_id, user_values or {})
        except sqlite3.Error as exc:
            raise PersistenceError(f"SQLite write failed: {exc}") from exc
        return record.uuid

    @staticmethod
    def _insert_calibration(conn, record, meta) -> None:
        """Record the calibration this capture used, once per distinct fit."""
        if not record.calibration_id:
            return
        coefficients = meta.get("calibration_coefficients")
        conn.execute(
            "INSERT OR IGNORE INTO calibration "
            "(calibration_id, created_at_ns, backend, poly_order, coefficients, "
            " r_squared, width) VALUES (?,?,?,?,?,?,?)",
            (
                record.calibration_id, record.captured_at_ns, record.backend,
                meta.get("calibration_order"),
                json.dumps([float(c) for c in coefficients]) if coefficients else None,
                meta.get("calibration_r_squared"),
                record.frame_width,
            ),
        )

    @staticmethod
    def _insert_ext(conn, capture_id: int, values: dict) -> None:
        if not values:
            conn.execute("INSERT INTO capture_ext (capture_id) VALUES (?)", (capture_id,))
            return
        names = list(values)
        columns = ", ".join(f'"{n}"' for n in names)
        placeholders = ", ".join("?" for _ in names)
        payload = [
            int(values[n]) if isinstance(values[n], bool) else values[n] for n in names
        ]
        conn.execute(
            f"INSERT INTO capture_ext (capture_id, {columns}) "
            f"VALUES (?, {placeholders})",
            [capture_id, *payload],
        )


class SqliteSpectrumSink(SpectrumSink):
    """Persist spectra to SQLite. Returns the capture UUID."""

    def __init__(
        self,
        config: SqliteConfig,
        user_schema: Optional[UserSchema] = None,
        hook: Optional[Callable] = None,
        on_violation: str = "error",
    ):
        self.config = config
        self.user_schema = user_schema or UserSchema()
        self.hook = hook
        self.on_violation = on_violation
        self.store = SqliteStore(config, self.user_schema)

    def write(self, spectrum: Spectrum, name: Optional[str] = None) -> Optional[str]:
        meta = spectrum.metadata or {}
        user_values = self.user_schema.resolve(
            spectrum, hook=self.hook, on_violation=self.on_violation
        )
        return self.store.insert_capture(
            spectrum,
            label=name,
            user_values=user_values,
            features=meta.get("features"),
        )

    def close(self) -> None:
        self.store.close()


# --------------------------------------------------------------------------- #
# Read side
# --------------------------------------------------------------------------- #
def read_spectrum(path: str | Path, capture_uuid: str) -> Spectrum:
    """Load one capture back as a :class:`Spectrum`, with its metadata."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT c.*, s.axis_kind, s.dtype, s.axis, s.intensities "
            "FROM capture c JOIN spectrum s ON s.capture_id = c.id "
            "WHERE c.uuid = ?",
            (capture_uuid,),
        ).fetchone()
        if row is None:
            raise PersistenceError(f"no capture {capture_uuid!r} in {path}")
        metadata: dict[str, Any] = {}
        if row["metadata_json"]:
            try:
                metadata = json.loads(row["metadata_json"])
            except json.JSONDecodeError:
                metadata = {}
        metadata.update(
            {
                "uuid": row["uuid"],
                "backend": row["backend"],
                "calibration_id": row["calibration_id"],
                "timestamp_ns": row["captured_at_ns"],
            }
        )
        ext = conn.execute(
            "SELECT * FROM capture_ext WHERE capture_id = ?", (row["id"],)
        ).fetchone()
        if ext is not None:
            user_values = {k: ext[k] for k in ext.keys() if k != "capture_id"}
            if any(v is not None for v in user_values.values()):
                metadata["user_fields"] = user_values
        return Spectrum(
            wavelengths=unpack_array(row["axis"], row["dtype"]),
            intensities=unpack_array(row["intensities"], row["dtype"]),
            metadata=metadata,
        )
    finally:
        conn.close()
