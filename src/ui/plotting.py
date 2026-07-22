"""Spectrum visualization (Migration Plan Phase 7; presentation layer).

Non-interactive rendering to PNG — a spectrum line plot and a waterfall
(stacked spectra over time). ``matplotlib`` is imported lazily inside the
functions (installed via the ``[plot]`` extra), so importing this module never
requires it. No scientific algorithms live here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Sequence

STATUS_COLOR = "#1b5e20"


def _pyplot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def render_spectrum(spectrum, peaks: Optional[Sequence] = None,
                    path: Optional[str | Path] = None, title: str = "Spectrum"):
    """Render an intensity trace (vs wavelength if calibrated, else pixel).

    Marks detected peaks with vertical lines. Saves a PNG when ``path`` is given
    and returns the path; otherwise returns the matplotlib Figure.
    """
    import numpy as np
    plt = _pyplot()

    y = np.asarray(spectrum.intensities, dtype=float)
    calibrated = bool(spectrum.wavelengths)
    x = np.asarray(spectrum.wavelengths, dtype=float) if calibrated else np.arange(len(y))
    xlabel = "wavelength (nm)" if calibrated else "pixel"

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(x, y, lw=0.8, color=STATUS_COLOR)
    for peak in peaks or []:
        pos = peak.wavelength if getattr(peak, "wavelength", None) is not None else peak.pixel
        ax.axvline(pos, color="#c62828", alpha=0.35, lw=0.8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("intensity")
    ax.set_title(title)
    ax.margins(x=0)
    fig.tight_layout()

    if path is not None:
        fig.savefig(path, dpi=90)
        plt.close(fig)
        return Path(path)
    return fig


def render_waterfall(spectra: Iterable, path: Optional[str | Path] = None,
                     title: str = "Waterfall", cmap: str = "viridis"):
    """Render a sequence of spectra as a 2-D waterfall (rows = frames/time).

    Saves a PNG when ``path`` is given (returns the path); else returns the
    Figure. Rows are truncated to the shortest spectrum for a rectangular image.
    """
    import numpy as np
    plt = _pyplot()

    rows = [np.asarray(s.intensities, dtype=float) for s in spectra]
    if not rows:
        raise ValueError("no spectra to render")
    width = min(len(r) for r in rows)
    image = np.vstack([r[:width] for r in rows])

    fig, ax = plt.subplots(figsize=(11, 5))
    im = ax.imshow(image, aspect="auto", origin="lower", cmap=cmap)
    ax.set_xlabel("spectral axis (sample)")
    ax.set_ylabel("frame (time)")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, label="intensity")
    fig.tight_layout()

    if path is not None:
        fig.savefig(path, dpi=90)
        plt.close(fig)
        return Path(path)
    return fig
