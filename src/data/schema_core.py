"""The locked core persistence schema (DATA-001, DATA-002).

This module is the single source of truth for the fields the *application*
depends on. Everything here is closed: storage backends may not invent core
columns, and user extensions (see :mod:`data.user_schema`) may not shadow,
redefine, or remove them. That separation is what makes "lock down the schema"
and "let users collect whatever they like" compatible rather than contradictory.

Two invariants are enforced here rather than left to convention:

**Backend provenance.** Every record carries the capture backend identity
(``backend``) alongside the integrity flag (``source``). A wavelength
calibration fitted on one backend is not valid on another — the geometry,
pixel format, and bit depth differ — so a store that cannot name its backend
cannot be trusted to serve a wavelength axis. ``backend`` distinguishes
``synthetic-camera`` (a simulated *frame*, extracted through the real pixel
path) from ``synthetic-generator`` (a directly-synthesized calibrated
spectrum); conflating those two is exactly the silent-bad-data case this exists
to prevent.

**Calibration identity.** ``calibration_id`` is a short fingerprint of the
calibration actually applied. It changes whenever the fit changes, so a
downstream consumer can detect that a series spans a recalibration instead of
silently plotting two different wavelength axes as one.

Bumping :data:`CORE_SCHEMA_VERSION` is a deliberate, breaking act: existing
stores will refuse to open until they are migrated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

CORE_SCHEMA_VERSION = 1

#: Backend identities. Anything not in this set is recorded as ``unknown``.
KNOWN_BACKENDS = frozenset(
    {"usb", "picamera2", "synthetic-camera", "synthetic-generator", "unknown"}
)

#: Names reserved by the core. User-declared fields may never use these,
#: in either store, in any role.
RESERVED_NAMES = frozenset(
    {
        # Core capture identity / provenance
        "id", "capture_id", "uuid", "captured_at_ns", "time", "timestamp",
        "source", "backend", "pixel_format", "simulated",
        "frame_width", "frame_height", "center_row", "average_rows",
        "n_samples", "calibrated", "calibration_id", "schema_version",
        "metadata_json",
        # Core scalar telemetry written by every sink
        "total_flux", "peak_intensity",
        # SQLite structural columns
        "axis_kind", "dtype", "axis", "intensities", "name", "value",
    }
)


def _backend_of(metadata: Mapping[str, Any]) -> str:
    """Derive the capture backend identity from spectrum metadata.

    Adapters set ``backend`` explicitly. Older records (and the synthetic
    generator, which never went through a camera) are resolved from the
    fields that *are* present, so provenance is never simply missing.
    """
    explicit = metadata.get("backend")
    if explicit:
        return str(explicit) if str(explicit) in KNOWN_BACKENDS else "unknown"
    frame = metadata.get("frame")
    if isinstance(frame, Mapping) and frame.get("backend"):
        candidate = str(frame["backend"])
        return candidate if candidate in KNOWN_BACKENDS else "unknown"
    # No camera frame at all + a generator stamp => directly synthesized.
    if metadata.get("generator") is not None and not isinstance(frame, Mapping):
        return "synthetic-generator"
    source = str(metadata.get("source", "")).lower()
    if source in ("usb", "picamera2"):
        return source
    if source == "synthetic":
        return "synthetic-camera" if isinstance(frame, Mapping) else "synthetic-generator"
    return "unknown"


def calibration_fingerprint(
    coefficients=None, order: Optional[int] = None, width: Optional[int] = None
) -> Optional[str]:
    """Short, stable fingerprint of an applied wavelength calibration.

    Returns ``None`` when the spectrum is uncalibrated. Any change to the fit —
    coefficients, polynomial order, or sensor width — yields a different
    fingerprint, which is the signal that a prior calibration no longer applies.
    """
    if coefficients is None:
        return None
    try:
        coeffs = [float(c) for c in coefficients]
    except (TypeError, ValueError):
        return None
    payload = json.dumps(
        {"c": [round(c, 12) for c in coeffs], "o": order, "w": width},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class CoreRecord:
    """The locked per-capture core. Every sink writes exactly these fields."""

    uuid: str
    captured_at_ns: int
    source: str
    backend: str
    simulated: bool
    pixel_format: str
    frame_width: Optional[int]
    frame_height: Optional[int]
    center_row: Optional[int]
    average_rows: Optional[int]
    n_samples: int
    calibrated: bool
    calibration_id: Optional[str]
    schema_version: int = CORE_SCHEMA_VERSION

    def as_dict(self) -> dict:
        return asdict(self)

    def influx_tags(self) -> dict:
        """Core tag set: bounded cardinality by construction.

        ``calibration_id`` is a tag despite being a hash: its cardinality is the
        number of distinct calibrations, which grows only when the instrument is
        recalibrated. That is precisely the axis dashboards need to split on.
        """
        return {
            "source": self.source,
            "backend": self.backend,
            "pixel_format": self.pixel_format,
            "calibration_id": self.calibration_id or "none",
        }

    def influx_fields(self) -> dict:
        """Core field set (scalars that vary per capture)."""
        return {
            "n_samples": int(self.n_samples),
            "calibrated": bool(self.calibrated),
            "simulated": bool(self.simulated),
        }


def _opt_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_core_record(spectrum, *, uuid: str, captured_at_ns: int) -> CoreRecord:
    """Project a :class:`~processing.spectrum.Spectrum` onto the locked core."""
    meta = dict(spectrum.metadata or {})
    frame = meta.get("frame") if isinstance(meta.get("frame"), Mapping) else {}
    backend = _backend_of(meta)
    calibrated = len(spectrum.wavelengths) > 0
    cal_id = meta.get("calibration_id")
    if cal_id is None and calibrated:
        cal_id = calibration_fingerprint(
            meta.get("calibration_coefficients"),
            _opt_int(meta.get("calibration_order")),
            _opt_int(meta.get("width")) or _opt_int(frame.get("width")),
        )
    return CoreRecord(
        uuid=uuid,
        captured_at_ns=int(captured_at_ns),
        source=str(meta.get("source", "unknown")),
        backend=backend,
        simulated=backend.startswith("synthetic"),
        pixel_format=str(frame.get("pixel_format", meta.get("pixel_format", "none"))),
        frame_width=_opt_int(frame.get("width", meta.get("width"))),
        frame_height=_opt_int(frame.get("height", meta.get("height"))),
        center_row=_opt_int(meta.get("center_row")),
        average_rows=_opt_int(meta.get("average_rows")),
        n_samples=len(spectrum.intensities),
        calibrated=calibrated,
        calibration_id=str(cal_id) if cal_id else None,
    )
