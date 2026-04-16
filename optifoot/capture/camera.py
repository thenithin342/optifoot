"""
NIR Camera wrapper for dual-wavelength image capture.

Real implementation uses PiCamera2 with the NoIR camera module.
DemoCamera generates synthetic grayscale images for laptop development.
"""

import logging
from abc import ABC, abstractmethod
from typing import Tuple

import numpy as np

from optifoot import config
from optifoot.capture.led_controller import BaseLEDController, create_led_controller

log = logging.getLogger(__name__)


class BaseCamera(ABC):
    """Interface for camera implementations."""

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def capture_frame(self) -> np.ndarray:
        """Return a single grayscale frame as uint8 numpy array."""
        ...

    @abstractmethod
    def capture_dual_wavelength(self) -> Tuple[np.ndarray, np.ndarray]:
        """Capture under 650 nm then 850 nm illumination.
        Returns (img_650, img_850) as grayscale uint8 arrays.
        """
        ...

    def close(self) -> None:
        self.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()


class NIRCamera(BaseCamera):
    """Real PiCamera2 wrapper for Raspberry Pi NoIR camera."""

    def __init__(self, led_controller: BaseLEDController | None = None):
        self._leds = led_controller or create_led_controller()
        self._picam2 = None

    def start(self) -> None:
        from picamera2 import Picamera2
        self._picam2 = Picamera2()

        cam_config = self._picam2.create_still_configuration(
            main={"size": config.CAMERA_RESOLUTION, "format": "RGB888"},
        )
        self._picam2.configure(cam_config)

        # Lock exposure and gain for consistent NIR imaging
        self._picam2.set_controls({
            "ExposureTime": config.EXPOSURE_TIME_US,
            "AnalogueGain": config.ANALOGUE_GAIN,
            "AwbEnable": config.AWB_ENABLE,
        })

        self._picam2.start()
        log.info("NIRCamera started (%s)", config.CAMERA_RESOLUTION)

    def stop(self) -> None:
        if self._picam2 is not None:
            self._picam2.stop()
            self._picam2.close()
            self._picam2 = None
        self._leds.all_off()
        log.info("NIRCamera stopped")

    def capture_frame(self) -> np.ndarray:
        """Capture a single frame, convert to grayscale."""
        rgb = self._picam2.capture_array(config.CAMERA_FORMAT)
        gray = np.mean(rgb, axis=2).astype(np.uint8)
        return gray

    def capture_dual_wavelength(self) -> Tuple[np.ndarray, np.ndarray]:
        """Sequential dual-wavelength capture:
        1. 650 nm LED ON → capture → OFF
        2. 850 nm LED ON → capture → OFF
        """
        # --- 650 nm ---
        self._leds.activate_650nm()
        img_650 = self.capture_frame()
        self._leds.all_off()

        # --- 850 nm ---
        self._leds.activate_850nm()
        img_850 = self.capture_frame()
        self._leds.all_off()

        log.info("Dual-wavelength capture complete (650 nm + 850 nm)")
        return img_650, img_850


class DemoCamera(BaseCamera):
    """Synthetic camera for development without hardware.

    Generates a fake foot-shaped region with plausible intensity values
    that differ between 650 nm and 850 nm to simulate oxygenation contrast.
    """

    def __init__(self, led_controller: BaseLEDController | None = None):
        self._leds = led_controller
        self._h, self._w = config.CAMERA_RESOLUTION[1], config.CAMERA_RESOLUTION[0]
        self._rng = np.random.default_rng(42)

    def start(self) -> None:
        log.info("[DEMO] Camera started (%d×%d)", self._w, self._h)

    def stop(self) -> None:
        log.info("[DEMO] Camera stopped")

    def _make_foot_mask(self) -> np.ndarray:
        """Elliptical foot-like region in centre of frame."""
        cy, cx = self._h // 2, self._w // 2
        ry, rx = int(self._h * 0.35), int(self._w * 0.18)
        yy, xx = np.ogrid[:self._h, :self._w]
        mask = ((yy - cy) ** 2 / ry ** 2 + (xx - cx) ** 2 / rx ** 2) <= 1.0
        return mask

    def capture_frame(self) -> np.ndarray:
        return self._rng.integers(40, 200, (self._h, self._w), dtype=np.uint8)

    def capture_dual_wavelength(self) -> Tuple[np.ndarray, np.ndarray]:
        mask = self._make_foot_mask()
        bg_val = 30  # dark background

        # 650 nm: deoxygenated blood absorbs more → lower reflection in low-SpO2 areas
        base_650 = self._rng.integers(100, 180, (self._h, self._w)).astype(np.float64)
        # add a "critical zone" patch in the lower-left of foot
        cy, cx = int(self._h * 0.62), int(self._w * 0.42)
        yy, xx = np.ogrid[:self._h, :self._w]
        patch = ((yy - cy) ** 2 / 80 ** 2 + (xx - cx) ** 2 / 60 ** 2) <= 1.0
        base_650[patch] *= 0.55  # reduced reflection → simulates low SpO2

        img_650 = np.where(mask, base_650, bg_val).clip(1, 255).astype(np.uint8)

        # 850 nm: HbO2 and HHb absorb more similarly → less spatial variation
        base_850 = self._rng.integers(110, 190, (self._h, self._w)).astype(np.float64)
        base_850[patch] *= 0.85  # less dramatic difference at 850 nm

        img_850 = np.where(mask, base_850, bg_val).clip(1, 255).astype(np.uint8)

        log.info("[DEMO] Dual-wavelength capture generated (synthetic)")
        return img_650, img_850


def create_camera(led_controller: BaseLEDController | None = None) -> BaseCamera:
    """Factory: returns real camera on Pi, demo camera otherwise."""
    if config.DEMO_MODE:
        return DemoCamera(led_controller)
    try:
        cam = NIRCamera(led_controller)
        return cam
    except Exception:
        log.warning("PiCamera2 unavailable — falling back to DemoCamera")
        return DemoCamera(led_controller)
