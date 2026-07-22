"""Data persistence: raw frames, spectra, metadata, calibration, synthetic params.

Spectra are written through a pluggable SpectrumSink so storage backends (CSV
today; InfluxDB / SQL / Grafana exporters later) are swappable without touching
the scientific core (DATA-001, DATA-002; see BACKLOG.md).
"""

from .sinks import CsvSpectrumSink, NullSink, SpectrumSink, read_csv_spectrum

__all__ = ["SpectrumSink", "CsvSpectrumSink", "NullSink", "read_csv_spectrum"]
