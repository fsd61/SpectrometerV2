"""Exception hierarchy for PySpectrometer2.

A single base exception lets callers catch any application-level failure while
still allowing precise handling of specific failure classes. Supports the
graceful-failure requirements (ERR-001, ERR-002, CFG-005).
"""


class PySpectrometerError(Exception):
    """Base class for all PySpectrometer2 application errors."""


class ConfigError(PySpectrometerError):
    """Configuration is missing, unreadable, or fails schema validation (CFG-005)."""


class HardwareError(PySpectrometerError):
    """A hardware device could not be initialized or operated (ERR-001)."""


class CameraError(HardwareError):
    """A camera adapter failed (discovery, configuration, acquisition, shutdown)."""


class AcquisitionError(PySpectrometerError):
    """Frame acquisition failed."""


class CalibrationError(PySpectrometerError):
    """Wavelength calibration failed, is missing, or is invalid."""


class AnalysisError(PySpectrometerError):
    """A scientific analysis step failed."""


class PersistenceError(PySpectrometerError):
    """Reading or writing persisted data/metadata failed."""
