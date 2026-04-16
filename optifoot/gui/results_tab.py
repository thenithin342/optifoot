"""
Results Tab — heatmap display, risk-score badge, metrics, and export.

Layout:
  ┌──────────────────────────────┬─────────────────┐
  │                              │  Risk Score      │
  │     Heatmap (zoomable)       │  ────────────    │
  │                              │  Mean SpO₂       │
  │                              │  Min SpO₂        │
  │                              │  % Critical      │
  │                              │  % At Risk       │
  ├──────────────────────────────┤  % Monitor       │
  │  [ Toggle Zones ]  [ Save ] │  % Normal        │
  │  [ Export PNG ]             │                   │
  └──────────────────────────────┴─────────────────┘
"""

import logging
import os
from datetime import datetime

import cv2
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap, QFont, QColor
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGroupBox, QGridLayout, QFileDialog, QMessageBox,
)

from optifoot import config
from optifoot.analysis.risk_scorer import RiskResult

log = logging.getLogger(__name__)

_LABEL_COLOURS = {
    "Normal": "#4CAF50",
    "Monitor": "#FF9800",
    "At Risk": "#FF5722",
    "Critical": "#D32F2F",
    "Unknown": "#757575",
}


def _bgr_to_qpixmap(img: np.ndarray) -> QPixmap:
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QPixmap.fromImage(QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888))


class ResultsTab(QWidget):
    def __init__(self, pipeline, parent=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self._zones_visible = True
        self._build_ui()

    # ── UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)

        # -- Left: heatmap viewer ----------------------------------------
        left = QVBoxLayout()

        self._scene = QGraphicsScene()
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHints(self._view.renderHints())
        self._view.setDragMode(QGraphicsView.ScrollHandDrag)
        self._view.setMinimumSize(500, 400)
        left.addWidget(self._view)

        btn_row = QHBoxLayout()
        self._btn_zones = QPushButton("Toggle Risk Zones")
        self._btn_zones.clicked.connect(self._toggle_zones)
        btn_row.addWidget(self._btn_zones)

        self._btn_save = QPushButton("💾  Save Scan")
        self._btn_save.setStyleSheet("background: #0D6E6E; color: white; padding: 6px 16px; border-radius: 4px;")
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_save)

        self._btn_export = QPushButton("📤  Export PNG")
        self._btn_export.clicked.connect(self._on_export_png)
        btn_row.addWidget(self._btn_export)
        btn_row.addStretch()

        left.addLayout(btn_row)
        root.addLayout(left, stretch=3)

        # -- Right: metrics panel ----------------------------------------
        right = QVBoxLayout()

        # Risk score badge
        self._score_label = QLabel("—")
        self._score_label.setAlignment(Qt.AlignCenter)
        self._score_label.setFont(QFont("Inter", 48, QFont.Bold))
        self._score_label.setMinimumHeight(80)
        right.addWidget(self._score_label)

        self._class_label = QLabel("No data")
        self._class_label.setAlignment(Qt.AlignCenter)
        self._class_label.setFont(QFont("Inter", 18, QFont.Bold))
        self._class_label.setStyleSheet("color: #757575; padding: 4px; border-radius: 4px;")
        right.addWidget(self._class_label)

        right.addSpacing(16)

        # Metrics grid
        metrics_group = QGroupBox("SpO₂ Metrics")
        grid = QGridLayout(metrics_group)
        self._metric_labels = {}
        names = [
            ("mean_spo2", "Mean SpO₂"),
            ("min_spo2", "Min SpO₂"),
            ("pct_critical", "% Critical (<85%)"),
            ("pct_at_risk", "% At Risk (85-90%)"),
            ("pct_monitor", "% Monitor (90-95%)"),
            ("pct_normal", "% Normal (≥95%)"),
        ]
        for row, (key, display) in enumerate(names):
            grid.addWidget(QLabel(display), row, 0)
            val = QLabel("—")
            val.setAlignment(Qt.AlignRight)
            val.setFont(QFont("Inter", 12, QFont.Bold))
            grid.addWidget(val, row, 1)
            self._metric_labels[key] = val
        right.addWidget(metrics_group)
        right.addStretch()

        root.addLayout(right, stretch=1)

    # ── Refresh after new processing ───────────────────────────────────

    def refresh(self):
        """Pull latest results from pipeline and update display."""
        heatmap = self._pipeline.last_heatmap
        result: RiskResult = self._pipeline.last_risk_result

        if heatmap is None or result is None:
            return

        self._show_heatmap(heatmap)
        self._show_risk(result)

    def _show_heatmap(self, img: np.ndarray):
        self._scene.clear()
        pix = _bgr_to_qpixmap(img)
        self._scene.addPixmap(pix)
        self._scene.setSceneRect(0, 0, pix.width(), pix.height())
        self._view.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)

    def _show_risk(self, r: RiskResult):
        self._score_label.setText(f"{r.score:.0f}")
        colour = _LABEL_COLOURS.get(r.label, "#757575")
        self._score_label.setStyleSheet(f"color: {colour};")

        self._class_label.setText(r.label)
        self._class_label.setStyleSheet(
            f"color: white; background: {colour}; padding: 6px 12px; border-radius: 6px;"
        )

        self._metric_labels["mean_spo2"].setText(f"{r.mean_spo2:.1f} %")
        self._metric_labels["min_spo2"].setText(f"{r.min_spo2:.1f} %")
        self._metric_labels["pct_critical"].setText(f"{r.pct_critical:.1f} %")
        self._metric_labels["pct_at_risk"].setText(f"{r.pct_at_risk:.1f} %")
        self._metric_labels["pct_monitor"].setText(f"{r.pct_monitor:.1f} %")
        self._metric_labels["pct_normal"].setText(f"{r.pct_normal:.1f} %")

    # ── Actions ────────────────────────────────────────────────────────

    def _toggle_zones(self):
        self._zones_visible = not self._zones_visible
        if self._zones_visible:
            heatmap = self._pipeline.last_heatmap
        else:
            heatmap = self._pipeline.last_heatmap_no_zones
        if heatmap is not None:
            self._show_heatmap(heatmap)

    def _on_save(self):
        """Save scan to the database."""
        main_win = self.window()
        patient_id = getattr(main_win, "patient_id", "") or "anonymous"
        try:
            self._pipeline.save_scan(patient_id)
            QMessageBox.information(self, "Saved", "Scan saved successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save scan:\n{e}")

    def _on_export_png(self):
        heatmap = self._pipeline.last_heatmap
        if heatmap is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Heatmap", "optifoot_heatmap.png", "PNG Files (*.png)"
        )
        if path:
            cv2.imwrite(path, heatmap)
            log.info("Heatmap exported to %s", path)

    def export_report(self):
        """Called from main window toolbar."""
        self._on_export_png()
