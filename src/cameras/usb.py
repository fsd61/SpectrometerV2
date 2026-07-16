"""Generic USB / OpenCV camera adapter (HW-002; Migration Plan Phase 5).

OpenCV (``cv2``) is imported lazily inside ``initialize`` so the module loads
without OpenCV present. Unlike the baseline (which hard-coded a Linux
``/dev/video`` V4L path), this opens the device by index, which works on Windows,
macOS, and Linux — a step toward first-class Windows support (PLAT-002).
"""

from __future__ import annotations

from typing import Any, Optional

from errors import CameraError
from .base import CameraAdapter, FrameMetadata


class UsbCameraAdapter(CameraAdapter):
    def __init__(self, device_index: int = 0, width: int = 800, height: int = 600,
                 fps: int = 30, api_preference: Optional[int] = None):
        self.device_index = int(device_index)
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)
        self.api_preference = api_preference
        self._cap = None

    @staticmethod
    def _import_cv2():
        try:
            import cv2  # noqa: PLC0415 (lazy on purpose)
        except ImportError as exc:
            raise CameraError("OpenCV (opencv-python) is required for the USB camera") from exc
        return cv2

    def initialize(self) -> None:
        cv2 = self._import_cv2()
        cap = (cv2.VideoCapture(self.device_index) if self.api_preference is None
               else cv2.VideoCapture(self.device_index, self.api_preference))
        if not cap.isOpened():
            raise CameraError(f"could not open USB camera at index {self.device_index}")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        self._cap = cap

    def discover_capabilities(self) -> dict[str, Any]:
        if self._cap is None:
            return {"backend": "usb", "requested": {"width": self.width, "height": self.height, "fps": self.fps}}
        cv2 = self._import_cv2()
        return {
            "backend": "usb",
            "width": int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": self._cap.get(cv2.CAP_PROP_FPS),
        }

    def configure(self, **settings: Any) -> None:
        for key in ("device_index", "width", "height", "fps", "api_preference"):
            if key in settings:
                setattr(self, key, settings[key])
        if self._cap is not None:
            cv2 = self._import_cv2()
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self._cap.set(cv2.CAP_PROP_FPS, self.fps)

    def acquire_frame(self) -> tuple[Any, FrameMetadata]:
        if self._cap is None:
            raise CameraError("camera not initialized")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise CameraError("failed to read a frame from the USB camera")
        height, width = frame.shape[0], frame.shape[1]
        meta = FrameMetadata(width=width, height=height, pixel_format="BGR",
                             extra={"source": "usb", "device_index": self.device_index})
        return frame, meta

    def status(self) -> dict[str, Any]:
        return {"backend": "usb", "open": self._cap is not None and bool(self._cap.isOpened()),
                "device_index": self.device_index}

    def shutdown(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
