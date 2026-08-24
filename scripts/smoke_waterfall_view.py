"""Throwaway smoke check for WaterfallView (the offscreen pytest file hangs here)."""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, "src")

from PySide6 import QtWidgets
app = QtWidgets.QApplication([])

from analysis.pipeline import analyze
from processing.spectrum import Spectrum
from synthetic.generator import SyntheticSpectrumSpec, generate
from ui.qt.waterfall_view import WaterfallView

view = WaterfallView(frames=32, full_scale=255.0, colormap="inferno")

spec = SyntheticSpectrumSpec(center_wavelengths=[436.0, 546.0, 611.0],
                             amplitudes=[120.0, 180.0, 90.0],
                             per_line_fwhm=[2.0, 3.0, 2.0], snr=150.0, seed=1)
sp = generate(spec)
res = analyze(sp.intensities, wavelengths=sp.wavelengths, measure=False)
view.update_spectrum(sp, res)

assert view._buffer.levels() == (0.0, 255.0), view._buffer.levels()
assert tuple(view._image.getLevels()) == (0.0, 255.0), view._image.getLevels()
labels = [t for _v, t in view._applied_ticks[0]]
assert labels and all(l.endswith("nm") for l in labels), labels
assert view._plot.getAxis("bottom").labelText == "Wavelength (nm)"
print("calibrated ticks:", labels)

# Raw, not smoothed: row 0 is the acquired trace (floored at 0), not res.smoothed.
row = view._buffer.image()[0]
assert max(abs(a - max(b, 0.0)) for a, b in zip(row, sp.intensities)) == 0.0
assert max(abs(a - b) for a, b in zip(row, res.smoothed)) > 1e-6

# Uncalibrated frame -> pixel labels, no stale nm axis.
view.clear()
bare = Spectrum(wavelengths=[], intensities=[1.0, 5.0, 2.0, 8.0])
view.update_spectrum(bare, analyze(bare.intensities, wavelengths=None, measure=False))
assert view._applied_ticks is None
assert view._plot.getAxis("bottom").labelText == "Pixel"
print("uncalibrated axis:", view._plot.getAxis("bottom").labelText)

# Smoothed mode still available.
sm = WaterfallView(frames=8, use_smoothed=True)
sm.update_spectrum(sp, res)
assert max(abs(a - max(b, 0.0)) for a, b in zip(sm._buffer.image()[0], res.smoothed)) < 1e-9

print("OK")
