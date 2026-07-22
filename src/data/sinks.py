"""Data persistence via pluggable sinks (DATA-001, DATA-002; Architecture §3).

A :class:`SpectrumSink` is the single seam through which spectra leave the
application. The default :class:`CsvSpectrumSink` writes CSV plus a sidecar
metadata JSON. Future backends — InfluxDB, SQL, or a Grafana exporter — are just
additional ``SpectrumSink`` implementations and never touch the scientific core
(see BACKLOG.md).
"""

from __future__ import annotations

import abc
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from processing.spectrum import Spectrum


class SpectrumSink(abc.ABC):
    """Destination for a :class:`Spectrum`."""

    @abc.abstractmethod
    def write(self, spectrum: Spectrum, name: Optional[str] = None) -> Any:
        """Persist ``spectrum``; return a backend-specific handle (e.g. a path)."""


class NullSink(SpectrumSink):
    """Discards spectra (useful for dry runs / tests)."""

    def write(self, spectrum: Spectrum, name: Optional[str] = None) -> None:
        return None


class CsvSpectrumSink(SpectrumSink):
    """Write a spectrum as CSV plus a sidecar ``<name>.meta.json`` of metadata.

    The CSV header is ``Wavelength,Intensity`` when the spectrum is calibrated,
    otherwise ``Pixel,Intensity`` (mirrors the baseline's CSV output).
    """

    def __init__(self, directory: str | Path = ".", write_metadata: bool = True):
        self.directory = Path(directory)
        self.write_metadata = write_metadata

    def write(self, spectrum: Spectrum, name: Optional[str] = None) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        if name is None:
            name = "spectrum-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        csv_path = self.directory / f"{name}.csv"
        calibrated = bool(spectrum.wavelengths)
        axis = spectrum.wavelengths if calibrated else range(len(spectrum.intensities))
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Wavelength" if calibrated else "Pixel", "Intensity"])
            for x, y in zip(axis, spectrum.intensities):
                writer.writerow([x, y])
        if self.write_metadata:
            (self.directory / f"{name}.meta.json").write_text(
                json.dumps(spectrum.metadata, indent=1, default=str), encoding="utf-8"
            )
        return csv_path


def read_csv_spectrum(path: str | Path) -> Spectrum:
    """Load a :class:`Spectrum` written by :class:`CsvSpectrumSink`."""
    path = Path(path)
    xs: list[float] = []
    ys: list[float] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        pixel_axis = bool(header) and header[0].strip().lower().startswith("pixel")
        for row in reader:
            if len(row) < 2:
                continue
            xs.append(float(row[0]))
            ys.append(float(row[1]))
    metadata: dict[str, Any] = {"source_file": str(path)}
    meta_path = path.with_suffix(".meta.json")
    if meta_path.exists():
        try:
            metadata.update(json.loads(meta_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    wavelengths = [] if pixel_axis else xs
    return Spectrum(wavelengths=wavelengths, intensities=ys, metadata=metadata)
