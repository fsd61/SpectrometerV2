"""Optional InfluxDB telemetry sink (BACKLOG telemetry workstream).

Writes each spectrum's scalar features to InfluxDB as one line-protocol point,
over plain HTTP — **stdlib only, no client library**, so enabling telemetry adds
no dependency. The InfluxDB *server* is installed and run separately (local or
remote); this just POSTs to it.

The write API is identical across InfluxDB versions (line protocol); only the
endpoint and auth differ, so v1/v2/v3 are one small switch:

* v1: ``POST /write?db=<database>`` (optional ``u``/``p`` query params)
* v2: ``POST /api/v2/write?org=<org>&bucket=<bucket>`` + ``Authorization: Token``
* v3: uses the v2 write endpoint (``bucket`` = the database name)

**Measurement integrity:** every point carries the locked core tag set from
:mod:`data.schema_core` — ``source``, ``backend``, ``pixel_format`` and
``calibration_id`` — so simulated data can never be mistaken for real
measurements, and a series that spans a recalibration or a backend change is
visibly split rather than silently blended. Tags are emitted in sorted order,
the canonical line-protocol form.

**Cardinality is gated, not trusted.** Extra tags no longer come from free-form
metadata. They must be declared in the user manifest (:mod:`data.user_schema`)
with an enumerated ``allowed`` list, because an undeclared tag whose value
varies per capture creates one series per capture and destroys the database.
Extra *fields* are unindexed and so only need to be declared, not enumerated.

Telemetry failures are swallowed with a warning: a dashboard write must never
break an acquisition.
"""

from __future__ import annotations

import logging
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import urlencode

from processing.spectrum import Spectrum

from .schema_core import build_core_record
from .sinks import SpectrumSink
from .user_schema import UserSchema

logger = logging.getLogger(__name__)

# ns -> requested precision divisor, and v1's spelling of microseconds ("u").
_PRECISION_DIVISOR = {"ns": 1, "us": 1_000, "ms": 1_000_000, "s": 1_000_000_000}
_V1_PRECISION = {"ns": "ns", "us": "u", "ms": "ms", "s": "s"}


# --------------------------------------------------------------------------- #
# Line protocol (pure, testable — no HTTP)
# --------------------------------------------------------------------------- #
def _esc_meas(s) -> str:
    return str(s).replace("\\", "\\\\").replace(",", "\\,").replace(" ", "\\ ")


def _esc_tag(s) -> str:
    return (str(s).replace("\\", "\\\\").replace(",", "\\,")
            .replace("=", "\\=").replace(" ", "\\ "))


def _fmt_field(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return f"{value}i"
    if isinstance(value, float):
        return repr(float(value))
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def build_line_protocol(
    spectrum: Spectrum,
    measurement: str,
    *,
    timestamp_ns: Optional[int] = None,
    extra_tags: Optional[dict] = None,
    extra_fields: Optional[dict] = None,
    precision: str = "ns",
) -> str:
    """Build one InfluxDB line-protocol point from a spectrum.

    The locked core (:mod:`data.schema_core`) supplies the tag set —
    ``source``, ``backend``, ``pixel_format``, ``calibration_id`` — plus the
    provenance fields. Intensity aggregates (``total_flux``, ``peak_intensity``)
    are derived here. Callers pass analysis-derived scalars via ``extra_fields``
    (e.g. :func:`summarize_features`) and manifest-declared labels via
    ``extra_tags``; neither may shadow a core name.
    """
    meta = spectrum.metadata or {}
    ts = meta.get("timestamp_ns")
    record = build_core_record(
        spectrum,
        uuid=str(meta.get("capture_uuid", "")),
        captured_at_ns=int(ts) if ts is not None else (timestamp_ns or 0),
    )

    tags = record.influx_tags()
    if extra_tags:
        # Core names win: a user field can never overwrite provenance.
        tags.update({k: str(v) for k, v in extra_tags.items() if k not in tags})

    intensities = [float(v) for v in spectrum.intensities]
    fields: dict[str, Any] = {
        "total_flux": float(sum(intensities)) if intensities else 0.0,
        "peak_intensity": float(max(intensities)) if intensities else 0.0,
    }
    fields.update(record.influx_fields())
    # The cross-store join key: lets a Grafana point resolve to its SQLite row.
    if record.uuid:
        fields["capture_uuid"] = record.uuid
    if extra_fields:
        fields.update({k: v for k, v in extra_fields.items() if k not in fields})

    # Sorted tags are the canonical line-protocol form (better server-side
    # indexing, and a stable string for tests).
    tag_str = "".join(
        f",{_esc_tag(k)}={_esc_tag(v)}" for k, v in sorted(tags.items())
    )
    field_str = ",".join(
        f"{_esc_tag(k)}={_fmt_field(v)}" for k, v in sorted(fields.items())
    )
    line = f"{_esc_meas(measurement)}{tag_str} {field_str}"
    if timestamp_ns is not None:
        line += f" {int(timestamp_ns) // _PRECISION_DIVISOR.get(precision, 1)}"
    return line


def summarize_features(result) -> dict:
    """Compact scalar features from a SpectralAnalysis, for telemetry fields."""
    peaks = list(getattr(result, "peaks", []) or [])
    out: dict[str, Any] = {"n_peaks": len(peaks)}
    if peaks:
        strongest = max(peaks, key=lambda p: float(p.intensity))
        if getattr(strongest, "wavelength", None) is not None:
            out["strongest_nm"] = float(strongest.wavelength)
        out["strongest_pixel"] = int(strongest.pixel)
        out["strongest_intensity"] = float(strongest.intensity)
        if getattr(strongest, "fwhm_nm", None) is not None:
            out["strongest_fwhm_nm"] = float(strongest.fwhm_nm)
        elif getattr(strongest, "fwhm", None) is not None:
            out["strongest_fwhm_px"] = float(strongest.fwhm)
        if getattr(strongest, "snr", None) is not None:
            out["strongest_snr"] = float(strongest.snr)
    return out


# --------------------------------------------------------------------------- #
# Config + sink
# --------------------------------------------------------------------------- #
@dataclass
class InfluxConfig:
    """Resolved ``[influx]`` settings."""

    enabled: bool = False
    version: int = 2
    url: str = "http://localhost:8086"
    org: str = ""
    bucket: str = "spectrometer"
    token: str = ""
    database: str = "spectrometer"
    username: str = ""
    password: str = ""
    measurement: str = "spectrum"
    precision: str = "ns"
    timeout: float = 5.0
    dry_run: bool = False

    @classmethod
    def from_section(cls, section) -> "InfluxConfig":
        g = section.get
        return cls(
            enabled=bool(g("enabled", False)),
            version=int(g("version", 2)),
            url=str(g("url", "http://localhost:8086")).rstrip("/"),
            org=str(g("org", "")),
            bucket=str(g("bucket", "spectrometer")),
            token=str(g("token", "")),
            database=str(g("database", "spectrometer")),
            username=str(g("username", "")),
            password=str(g("password", "")),
            measurement=str(g("measurement", "spectrum")),
            precision=str(g("precision", "ns")),
            timeout=float(g("timeout", 5.0)),
            dry_run=bool(g("dry_run", False)),
        )

    def write_endpoint(self) -> tuple:
        """Return ``(url, headers)`` for the write request, per InfluxDB version."""
        if self.version == 1:
            q = {"db": self.database, "precision": _V1_PRECISION.get(self.precision, self.precision)}
            if self.username:
                q["u"] = self.username
                q["p"] = self.password
            return f"{self.url}/write?{urlencode(q)}", {}
        # v2 and v3 share the v2 write API.
        q = {"org": self.org, "bucket": self.bucket, "precision": self.precision}
        headers = {"Authorization": f"Token {self.token}"} if self.token else {}
        return f"{self.url}/api/v2/write?{urlencode(q)}", headers


def _http_post(url: str, body: bytes, headers: dict, timeout: float):
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "text/plain; charset=utf-8")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - user-configured URL
        return getattr(resp, "status", None)


class InfluxDbSpectrumSink(SpectrumSink):
    """Write a spectrum's scalar features to InfluxDB (write-only telemetry).

    ``poster`` is injectable so tests assert the URL/headers/body without a live
    server. Write failures are logged and swallowed — telemetry must never break
    an acquisition.

    Extra tags and fields come from the validated user manifest, never from raw
    metadata: that is what keeps tag cardinality bounded.
    """

    def __init__(
        self,
        config: InfluxConfig,
        poster: Optional[Callable] = None,
        user_schema: Optional[UserSchema] = None,
        hook: Optional[Callable] = None,
        on_violation: str = "error",
    ):
        self.config = config
        self._post = poster or _http_post
        self.user_schema = user_schema or UserSchema()
        self.hook = hook
        self.on_violation = on_violation

    def _user_tags_and_fields(self, spectrum: Spectrum) -> tuple:
        """Split validated user values into Influx tags and fields by role."""
        if not len(self.user_schema):
            return {}, {}
        values = self.user_schema.resolve(
            spectrum, hook=self.hook, on_violation=self.on_violation
        )
        tag_names = {f.name for f in self.user_schema.influx_tags()}
        field_names = {f.name for f in self.user_schema.influx_fields()}
        tags = {k: v for k, v in values.items() if k in tag_names}
        fields = {k: v for k, v in values.items() if k in field_names}
        return tags, fields

    def write(self, spectrum: Spectrum, name: Optional[str] = None):
        cfg = self.config
        meta = spectrum.metadata or {}
        ts = meta.get("timestamp_ns")
        timestamp_ns = int(ts) if ts is not None else time.time_ns()
        user_tags, user_fields = self._user_tags_and_fields(spectrum)
        extra_fields = dict(meta.get("features") or {})
        extra_fields.update(user_fields)
        line = build_line_protocol(
            spectrum, cfg.measurement,
            timestamp_ns=timestamp_ns,
            extra_tags=user_tags,
            extra_fields=extra_fields,
            precision=cfg.precision,
        )
        if cfg.dry_run:
            print(f"[influx dry-run] {line}")
            logger.info("[influx dry-run] %s", line)
            return line
        url, headers = cfg.write_endpoint()
        try:
            self._post(url, line.encode("utf-8"), headers, cfg.timeout)
        except Exception as exc:  # noqa: BLE001 - telemetry must not break acquisition
            logger.warning("InfluxDB write failed (%s): %s", url, exc)
            return None
        logger.info("Wrote telemetry point to InfluxDB %s", url)
        return line


# ``build_sink`` moved to :mod:`data.factory` — a factory that chooses between
# backends does not belong inside one of those backends. Re-exported here so
# existing imports keep working.
def build_sink(config, output):
    """Deprecated alias for :func:`data.factory.build_sink`."""
    from .factory import build_sink as _build_sink

    return _build_sink(config, output)
