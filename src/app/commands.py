"""Application command handlers (Architecture §3: application core orchestration).

Each handler wires the platform-neutral components together — configuration,
platform detection, camera factory, acquisition, analysis, calibration, and a
persistence sink — and returns a process exit code. No scientific algorithms
live here.
"""

from __future__ import annotations

import logging
from pathlib import Path

from acquisition.service import acquire_spectrum
from analysis.pipeline import analyze
from calibration.persistence import load_calibration_points
from calibration.wavelength import calibrate
from cameras.factory import create_camera_from_config
from data.sinks import CsvSpectrumSink, read_csv_spectrum
from errors import PySpectrometerError
from platforms import detect_platform
from synthetic.generator import SyntheticSpectrumSpec, generate

# A small demonstration line set (center nm, amplitude, FWHM nm) for the
# headless 'generate-synthetic' command.
DEMO_LINES = [(405.0, 200.0, 2.0), (436.0, 120.0, 1.5), (546.0, 180.0, 3.0), (612.0, 90.0, 2.0)]


def _report_peaks(result, logger: logging.Logger) -> None:
    if not result.peaks:
        print("  (no peaks detected)")
    for peak in result.peaks:
        where = f"{peak.wavelength:.2f} nm" if peak.wavelength is not None else f"pixel {peak.pixel}"
        extra = ""
        if peak.fwhm is not None:
            extra += f" fwhm={peak.fwhm:.2f}px"
            if peak.fwhm_nm is not None:
                extra += f" ({peak.fwhm_nm:.3f} nm)"
        if peak.snr is not None:
            extra += f" snr={peak.snr:.1f}"
        line = f"  peak @ {where}{extra}"
        print(line)
        logger.info("peak %s", line.strip())


def test_camera(config, logger: logging.Logger) -> int:
    backend = config.get("camera", "backend")
    logger.info("Testing camera backend=%s", backend)
    camera = create_camera_from_config(config.section("camera"))
    camera.initialize()
    try:
        caps = camera.discover_capabilities()
        _frame, meta = camera.acquire_frame()
    finally:
        camera.shutdown()
    msg = f"Camera OK: backend={caps.get('backend')} frame={meta.width}x{meta.height} {meta.pixel_format}"
    print(msg)
    logger.info(msg)
    return 0


def verify_hardware(config, logger: logging.Logger) -> int:
    info = detect_platform()
    tag = " [Raspberry Pi]" if info.is_raspberry_pi else ""
    print(f"Platform: {info.system} ({info.machine}){tag}, Python {info.python_version}")
    logger.info("Platform: %s %s pi=%s", info.system, info.machine, info.is_raspberry_pi)

    backend = config.get("camera", "backend")
    camera = create_camera_from_config(config.section("camera"))
    try:
        camera.initialize()
        try:
            _frame, meta = camera.acquire_frame()
        finally:
            camera.shutdown()
    except PySpectrometerError as exc:
        print(f"Camera [{backend}]: FAILED — {exc}")
        logger.warning("Camera check failed: %s", exc)
        return 1
    print(f"Camera [{backend}]: OK ({meta.width}x{meta.height} {meta.pixel_format})")
    logger.info("Camera check OK")
    return 0


def check_calibration(config, logger: logging.Logger) -> int:
    path = Path(str(config.get("calibration", "file")))
    if not path.exists():
        print(f"No calibration file at {path}. Run a calibration first.")
        logger.warning("No calibration file: %s", path)
        return 1
    pixels, wavelengths = load_calibration_points(path)
    width = int(config.get("camera", "width"))
    result = calibrate(pixels, wavelengths, width)
    order = {2: "2nd", 3: "3rd"}[result.order]
    r2 = f", R²={result.r_squared:.6f}" if result.r_squared is not None else ""
    print(f"Calibration OK: {len(pixels)} points, {order}-order fit{r2}")
    print(f"  Range over {width}px: {result.wavelengths[0]:.2f}..{result.wavelengths[-1]:.2f} nm")
    logger.info("Calibration OK: %d points order=%d", len(pixels), result.order)
    return 0


def generate_synthetic(config, logger: logging.Logger, output: str) -> int:
    spec = SyntheticSpectrumSpec.from_config(
        config.section("synthetic"),
        [c for c, _, _ in DEMO_LINES],
        [a for _, a, _ in DEMO_LINES],
        per_line_fwhm=[f for _, _, f in DEMO_LINES],
    )
    spectrum = generate(spec)
    result = analyze(spectrum.intensities, wavelengths=spectrum.wavelengths, measure=True)
    path = CsvSpectrumSink(output).write(spectrum, name="synthetic")
    print(f"Generated {len(spectrum)} samples -> {path}")
    logger.info("Generated synthetic spectrum -> %s", path)
    _report_peaks(result, logger)
    return 0


def run(config, logger: logging.Logger, output: str) -> int:
    camera = create_camera_from_config(config.section("camera"))
    camera.initialize()
    try:
        spectrum = acquire_spectrum(camera)
    finally:
        camera.shutdown()
    result = analyze(spectrum.intensities, wavelengths=spectrum.wavelengths or None, measure=True)
    path = CsvSpectrumSink(output).write(spectrum, name="acquisition")
    print(f"Acquired {len(spectrum)} samples -> {path}")
    logger.info("Acquired spectrum -> %s", path)
    _report_peaks(result, logger)
    return 0


def analyze_file(config, logger: logging.Logger, input_path: str) -> int:
    if not input_path:
        print("analyze requires --input PATH")
        logger.error("analyze called without --input")
        return 2
    spectrum = read_csv_spectrum(input_path)
    result = analyze(spectrum.intensities, wavelengths=spectrum.wavelengths or None, measure=True)
    print(f"Analyzed {len(spectrum)} samples from {input_path}")
    logger.info("Analyzed %s", input_path)
    _report_peaks(result, logger)
    return 0
