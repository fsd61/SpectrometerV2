"""Scientific analysis: peak detection, line fitting, FWHM, SNR estimation.

Platform-neutral algorithms consuming the shared Spectrum object. Extracted from
the baseline and verified against golden data (Migration Plan Phase 3; TEST-002).
"""

from .peaks import peak_indexes
from .smoothing import savitzky_golay

__all__ = ["peak_indexes", "savitzky_golay"]
