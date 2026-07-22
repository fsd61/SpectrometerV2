"""Presentation layer: rendering and (future) GUI.

Non-interactive PNG rendering lives here now (render_spectrum, render_waterfall);
the interactive GUI is future work (Migration Plan Phase 7). No scientific
algorithms in this layer.
"""

from .plotting import render_spectrum, render_waterfall

__all__ = ["render_spectrum", "render_waterfall"]
