"""Camera selection with graceful 'no camera' handling (application layer).

Keeps the interactive/policy logic out of the pure camera factory. Honors
``camera.backend``; for ``auto`` it probes for a real camera and, when none is
found, applies ``camera.on_missing`` (prompt / error / synthetic).
"""

from __future__ import annotations

import logging
import sys
from typing import Callable, Optional, Tuple

from cameras.base import CameraAdapter
from cameras.factory import _auto, create_camera_from_config
from cameras.synthetic_camera import SyntheticCameraAdapter
from errors import CameraError

SIMULATED_BANNER = "*** SIMULATED DATA — not a real measurement ***"


def _default_prompt() -> bool:
    try:
        answer = input("No camera detected. Continue with SIMULATED data? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def _try_real_camera(section, logger: logging.Logger) -> Optional[CameraAdapter]:
    """Build + initialize the platform-appropriate real camera; None if none opens."""
    try:
        camera = _auto(
            width=section.get("width", 800),
            height=section.get("height", 600),
            device_index=section.get("device_index", 0),
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("Auto: could not construct a camera adapter (%s)", exc)
        return None
    try:
        camera.initialize()
        return camera
    except CameraError as exc:
        logger.info("Auto: no real camera available (%s)", exc)
        try:
            camera.shutdown()
        except Exception:  # noqa: BLE001
            pass
        return None


def _should_use_synthetic(policy: str, *, isatty: Optional[bool],
                          prompt: Optional[Callable[[], bool]],
                          logger: logging.Logger) -> bool:
    """Decide whether to fall back to synthetic when no camera is present."""
    policy = (policy or "prompt").lower()
    if policy == "synthetic":
        return True
    if policy == "error":
        return False
    # policy == "prompt": only meaningful with an interactive terminal
    if isatty is None:
        isatty = sys.stdin.isatty()
    if not isatty:
        logger.info("Non-interactive session; treating on_missing=prompt as error.")
        return False
    return bool((prompt or _default_prompt)())


def select_camera(config, logger: logging.Logger, *, isatty: Optional[bool] = None,
                  prompt: Optional[Callable[[], bool]] = None) -> Tuple[CameraAdapter, bool]:
    """Return an initialized camera and whether it produces simulated data.

    Raises CameraError if no usable camera is available and policy says to stop.
    """
    backend = str(config.get("camera", "backend")).lower()
    section = config.section("camera")

    if backend == "none":
        raise CameraError(
            "no camera is configured (camera.backend = 'none'). Use 'analyze' or "
            "'generate-synthetic', or set camera.backend to auto/usb/csi/synthetic."
        )
    if backend != "auto":
        camera = create_camera_from_config(section)
        camera.initialize()  # explicit choice: any failure propagates as an error
        return camera, backend == "synthetic"

    camera = _try_real_camera(section, logger)
    if camera is not None:
        return camera, False

    policy = str(config.get("camera", "on_missing")).lower()
    if _should_use_synthetic(policy, isatty=isatty, prompt=prompt, logger=logger):
        logger.warning("No camera detected — using SIMULATED data.")
        print(SIMULATED_BANNER)
        camera = SyntheticCameraAdapter(
            width=int(section.get("width", 800)), height=int(section.get("height", 600)),
        )
        camera.initialize()
        return camera, True

    raise CameraError(
        "No camera detected. Connect a camera, or run hardware-free with "
        "'--set camera.backend=synthetic'."
    )
