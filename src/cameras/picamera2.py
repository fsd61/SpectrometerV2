"""Raspberry Pi native camera adapter (HW-003, PLAT-005; Migration Plan Phase 5).

``picamera2`` is imported lazily so the module loads off-Pi. Kept behind the
common contract so Pi-specific APIs never leak into the scientific core
(PLAT-004: support without coupling).
"""

from __future__ import annotations

from typing import Any

from errors import CameraError
from .base import CameraAdapter, FrameMetadata


class Picamera2Adapter(CameraAdapter):
    def __init__(self, width: int = 800, height: int = 600, fps: int = 30, gain: float = 10.0):
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)
        self.gain = float(gain)
        self._cam = None

    @staticmethod
    def _import_picamera2():
        try:
            from picamera2 import Picamera2  # noqa: PLC0415 (lazy, Pi-only)
        except ImportError as exc:
            raise CameraError(
                "picamera2 is required for the CSI (Raspberry Pi) camera but is not "
                "installed. Install it with 'sudo apt install -y python3-picamera2' and "
                "use a virtualenv created with '--system-site-packages'."
            ) from exc
        return Picamera2

    def initialize(self) -> None:
        Picamera2 = self._import_picamera2()
        cam = Picamera2()
        frame_us = int(1_000_000 / self.fps)
        config = cam.create_video_configuration(
            main={"format": "RGB888", "size": (self.width, self.height)},
            controls={"FrameDurationLimits": (frame_us, frame_us)},
        )
        cam.configure(config)
        cam.start()
        try:
            cam.set_controls({"AnalogueGain": self.gain})
        except Exception:  # noqa: BLE001 - gain control is best-effort
            pass
        self._cam = cam

    def discover_capabilities(self) -> dict[str, Any]:
        return {"backend": "picamera2", "width": self.width, "height": self.height,
                "fps": self.fps, "gain": self.gain, "formats": ["RGB888"]}

    def configure(self, **settings: Any) -> None:
        for key in ("width", "height", "fps", "gain"):
            if key in settings:
                setattr(self, key, settings[key])
        if self._cam is not None and "gain" in settings:
            try:
                self._cam.set_controls({"AnalogueGain": self.gain})
            except Exception:  # noqa: BLE001
                pass

    def acquire_frame(self) -> tuple[Any, FrameMetadata]:
        if self._cam is None:
            raise CameraError("camera not initialized")
        frame = self._cam.capture_array()
        height, width = frame.shape[0], frame.shape[1]
        meta = FrameMetadata(width=width, height=height, pixel_format="RGB888",
                             extra={"source": "picamera2", "gain": self.gain})
        return frame, meta

    def status(self) -> dict[str, Any]:
        return {"backend": "picamera2", "open": self._cam is not None, "gain": self.gain}

    def shutdown(self) -> None:
        if self._cam is not None:
            try:
                self._cam.stop()
            finally:
                self._cam = None
