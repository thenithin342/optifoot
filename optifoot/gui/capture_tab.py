"""
Capture Tab — live camera preview and dual-wavelength capture controls.

Layout:
  ┌──────────────────────────────────────────┐
  │          Live Camera Preview              │
  ├────────────────┬─────────────────────────┤
  │  650 nm thumb  │  850 nm thumb           │
  ├────────────────┴─────────────────────────┤
  │  [ Capture ]          [ Process ]         │
  └──────────────────────────────────────────┘
"""

import logging

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QGroupBox,
)

log = logging.getLogger(__name__)


def _numpy_to_qpixmap(img: np.ndarray, max_w: int = 0, max_h: int = 0) -> QPixmap:
    """Convert a grayscale or BGR numpy array to QPixmap."""
    if img.ndim == 2:
        h, w = img.shape
        qimg = QImage(img.data, w, h, w, QImage.Format_Grayscale8)
    else:
        h, w, ch = img.shape
        bpl = ch * w
        fmt = QImage.Format_RGB888 if ch == 3 else QImage.Format_RGBA8888
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if ch == 3 else img
        qimg = QImage(rgb.data, w, h, bpl, fmt)
    pix = QPixmap.fromImage(qimg)
    if max_w and max_h:
        pix = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return pix


class CaptureTab(QWidget):
    """Tab for live preview, dual-wavelength capture, and processing trigger."""

    processing_complete = pyqtSignal()  # emitted after pipeline finishes

    def __init__(self, pipeline, parent=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self._img_650 = None
        self._img_850 = None

        self._build_ui()
        self._start_preview()

    # ── UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Live preview
        self._preview_label = QLabel("Camera preview will appear here")
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setMinimumHeight(350)
        self._preview_label.setStyleSheet("background: #111; color: #888; font-size: 14px;")
        layout.addWidget(self._preview_label)

        # Thumbnails of last capture
        thumb_group = QGroupBox("Last Capture")
        thumb_layout = QHBoxLayout(thumb_group)
        self._thumb_650 = QLabel("650 nm")
        self._thumb_650.setAlignment(Qt.AlignCenter)
        self._thumb_650.setMinimumSize(200, 150)
        self._thumb_650.setStyleSheet("background: #1a1a1a; color: #666;")
        self._thumb_850 = QLabel("850 nm")
        self._thumb_850.setAlignment(Qt.AlignCenter)
        self._thumb_850.setMinimumSize(200, 150)
        self._thumb_850.setStyleSheet("background: #1a1a1a; color: #666;")
        thumb_layout.addWidget(self._thumb_650)
        thumb_layout.addWidget(self._thumb_850)
        layout.addWidget(thumb_group)

        # Buttons
        btn_layout = QHBoxLayout()

        self._btn_capture = QPushButton("📷  Capture")
        self._btn_capture.setMinimumHeight(42)
        self._btn_capture.setStyleSheet(
            "QPushButton { background: #0D6E6E; color: white; font-size: 15px; "
            "border-radius: 6px; padding: 8px 24px; }"
            "QPushButton:hover { background: #0A5555; }"
        )
        self._btn_capture.clicked.connect(self._on_capture)

        self._btn_process = QPushButton("🔬  Process")
        self._btn_process.setMinimumHeight(42)
        self._btn_process.setEnabled(False)
        self._btn_process.setStyleSheet(
            "QPushButton { background: #2E7D32; color: white; font-size: 15px; "
            "border-radius: 6px; padding: 8px 24px; }"
            "QPushButton:hover { background: #1B5E20; }"
            "QPushButton:disabled { background: #555; color: #999; }"
        )
        self._btn_process.clicked.connect(self._on_process)

        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_capture)
        btn_layout.addWidget(self._btn_process)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Progress
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setTextVisible(True)
        layout.addWidget(self._progress)

    # ── Live preview via QTimer ────────────────────────────────────────

    def _start_preview(self):
        self._preview_timer = QTimer(self)
        self._preview_timer.timeout.connect(self._update_preview)
        self._preview_timer.start(100)  # ~10 fps preview

    def _update_preview(self):
        try:
            frame = self._pipeline.camera.capture_frame()
            pix = _numpy_to_qpixmap(frame, self._preview_label.width(), self._preview_label.height())
            self._preview_label.setPixmap(pix)
        except Exception:
            pass  # camera may not be ready yet

    # ── Capture ────────────────────────────────────────────────────────

    def _on_capture(self):
        self._btn_capture.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setFormat("Capturing…")

        try:
            self._img_650, self._img_850 = self._pipeline.camera.capture_dual_wavelength()
        except Exception as e:
            log.error("Capture failed: %s", e)
            self._progress.setVisible(False)
            self._btn_capture.setEnabled(True)
            return

        # Show thumbnails
        self._thumb_650.setPixmap(
            _numpy_to_qpixmap(self._img_650, 200, 150)
        )
        self._thumb_850.setPixmap(
            _numpy_to_qpixmap(self._img_850, 200, 150)
        )

        self._progress.setVisible(False)
        self._btn_capture.setEnabled(True)
        self._btn_process.setEnabled(True)
        log.info("Capture displayed in thumbnails")

    # ── Process ────────────────────────────────────────────────────────

    def _on_process(self):
        if self._img_650 is None:
            return

        self._btn_process.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._progress.setFormat("Processing…")

        try:
            self._pipeline.process(self._img_650, self._img_850)
        except Exception as e:
            log.error("Processing failed: %s", e)
            self._progress.setVisible(False)
            self._btn_process.setEnabled(True)
            return

        self._progress.setVisible(False)
        self._btn_process.setEnabled(True)
        self.processing_complete.emit()
        log.info("Processing complete — switching to Results tab")
