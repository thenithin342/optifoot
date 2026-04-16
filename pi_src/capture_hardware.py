#!/usr/bin/env python3
"""Pi camera + LEDs only (no tkinter). Imported by capture_web_interface and capture_two_images."""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from gpiozero import LED
from picamera2 import Picamera2

LED_650_PIN = 17
LED_850_PIN = 27
LED_STABILIZE_SEC = 0.08

PREVIEW_RES = (320, 240)
CAPTURE_RES = (1640, 1232)

EXPOSURE_TIME_US = 20000
ANALOGUE_GAIN = 4.0
AWB_ENABLE = False

OUT_DIR = Path("/home/pi/New folder/captures")


def to_gray(rgb):
    return np.mean(rgb, axis=2).astype(np.uint8)


class CaptureHardware:
    """Camera + LEDs: Start 650 → Capture 650 → Start 850 → Capture 850."""

    def __init__(self, *, for_gui: bool = False):
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.p650 = OUT_DIR / f"{ts}_650nm.png"
        self.p850 = OUT_DIR / f"{ts}_850nm.png"
        self.mode: str | None = None
        self.for_gui = for_gui
        self.has_650 = False
        self.has_850 = False

        self.led650 = LED(LED_650_PIN)
        self.led850 = LED(LED_850_PIN)
        self.led650.off()
        self.led850.off()

        self.cam = Picamera2()
        if for_gui:
            cfg = self.cam.create_preview_configuration(
                main={"size": CAPTURE_RES, "format": "RGB888"},
                lores={"size": PREVIEW_RES, "format": "YUV420"},
                buffer_count=4,
            )
        else:
            cfg = self.cam.create_preview_configuration(
                main={"size": CAPTURE_RES, "format": "RGB888"},
                buffer_count=4,
            )
        self.cam.configure(cfg)
        self.cam.set_controls({
            "ExposureTime": EXPOSURE_TIME_US,
            "AnalogueGain": ANALOGUE_GAIN,
            "AwbEnable": AWB_ENABLE,
            "FrameDurationLimits": (33333, 33333),
        })
        self.cam.start()
        time.sleep(0.2)

    def assign_next_pair_paths(self) -> None:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.p650 = OUT_DIR / f"{ts}_650nm.png"
        self.p850 = OUT_DIR / f"{ts}_850nm.png"
        self.has_650 = False
        self.has_850 = False

    def start_650(self) -> None:
        self.led850.off()
        self.led650.on()
        time.sleep(LED_STABILIZE_SEC)
        self.mode = "650"

    def capture_650(self) -> bool:
        if self.mode != "650":
            return False
        rgb = self.cam.capture_array("main")
        cv2.imwrite(str(self.p650), to_gray(rgb))
        self.led650.off()
        self.mode = None
        self.has_650 = True
        return True

    def start_850(self) -> None:
        self.led650.off()
        self.led850.on()
        time.sleep(LED_STABILIZE_SEC)
        self.mode = "850"

    def capture_850(self) -> bool:
        if self.mode != "850":
            return False
        rgb = self.cam.capture_array("main")
        cv2.imwrite(str(self.p850), to_gray(rgb))
        self.led850.off()
        self.mode = None
        self.has_850 = True
        return True

    def shutdown(self) -> None:
        try:
            self.led650.off()
            self.led850.off()
            self.cam.stop()
            self.cam.close()
            self.led650.close()
            self.led850.close()
        except Exception:
            pass


def run_auto_sequence() -> int:
    hw: CaptureHardware | None = None
    try:
        hw = CaptureHardware(for_gui=False)
        hw.start_650()
        if not hw.capture_650():
            print("AUTO_CAPTURE_FAIL: bad state before 650 save", file=sys.stderr)
            return 1
        hw.start_850()
        if not hw.capture_850():
            print("AUTO_CAPTURE_FAIL: bad state before 850 save", file=sys.stderr)
            return 1
        print(f"AUTO_CAPTURE_OK {hw.p650.name} {hw.p850.name}", flush=True)
        return 0
    except Exception as e:
        print(f"AUTO_CAPTURE_FAIL: {e}", file=sys.stderr)
        return 1
    finally:
        if hw is not None:
            hw.shutdown()
