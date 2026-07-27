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

**Measurement integrity:** every point is tagged ``source`` (synthetic / camera /
unknown, from ``Spectrum.metadata``), so simulated data can never be mistaken for
real measurements downstream — the same discipline as the GUI's ``[SIMULATED]``
marker. Telemetry failures are swallowed with a warning: a dashboard write must
never break an acquisition.
"""

from __future__ import annotations

import logging
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import urlencode

from processing.spectrum import Spectrum
from .sinks import SpectrumSink

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

    Base fields (derivable from the spectrum alone): ``n_samples``,
    ``total_flux``, ``peak_intensity``, ``calibrated``. Callers pass richer
    analysis-derived scalars via ``extra_fields`` (e.g. :func:`summarize_features`)
    and extra string labels via ``extra_tags``. ``source`` is always tagged.
    """
    meta = spectrum.metadata or {}
    tags = {"source": str(meta.get("source", "unknown"))}
    if extra_tags:
        tags.update({k: str(v) for k, v in extra_tags.items()})

    intensities = [float(v) for v in spectrum.intensities]
    fields: dict[str, Any] = {
        "n_samples": len(intensities),
        "total_flux": float(sum(intensities)) if intensities else 0.0,
        "peak_intensity": float(max(intensities)) if intensities else 0.0,
        "calibrated": len(spectrum.wavelengths) > 0,
    }
    if extra_fields:
        fields.update(extra_fields)

    tag_str = "".join(f",{_esc_tag(k)}={_esc_tag(v)}" for k, v in tags.items())
    field_str = ",".join(f"{_esc_tag(k)}={_fmt_field(v)}" for k, v in fields.items())
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
    """

    def __init__(self, config: InfluxConfig, poster: Optional[Callable] = None):
        self.config = config
        self._post = poster or _http_post

    def write(self, spectrum: Spectrum, name: Optional[str] = None):
        cfg = self.config
        meta = spectrum.metadata or {}
        ts = meta.get("timestamp_ns")
        timestamp_ns = int(ts) if ts is not None else time.time_ns()
        line = build_line_protocol(
            spectrum, cfg.measurement,
            timestamp_ns=timestamp_ns,
            extra_tags=meta.get("influx_tags"),
            extra_fields=meta.get("influx_fields"),
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


def build_sink(config, output):
    """The output sink for a run: CSV, plus InfluxDB teed in when enabled."""
    from .sinks import CsvSpectrumSink, MultiSink

    sinks = [CsvSpectrumSink(output)]
    cfg = InfluxConfig.from_section(config.section("influx"))
    if cfg.enabled:
        sinks.append(InfluxDbSpectrumSink(cfg))
    return sinks[0] if len(sinks) == 1 else MultiSink(sinks)
