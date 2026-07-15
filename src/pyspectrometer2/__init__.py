"""PySpectrometer2 — modular, cross-platform scientific spectrometer application.

Design philosophy: *Think like a physicist. Build like an engineer.*

This package hosts one platform-neutral scientific core. Operating-system and
camera-hardware specifics live behind adapters in the ``platform`` and
``cameras`` subpackages; dependencies point inward toward the science.

See the Rev 1.1 engineering documents (Requirements, Architecture & Design,
Migration Plan) for the governing requirements and phase/gate plan.
"""

__version__ = "2.0.0.dev0"

__all__ = ["__version__"]
