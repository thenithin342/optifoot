"""
History Tab — scan timeline, side-by-side comparison, risk-score trend.

Layout:
  ┌──────────────┬──────────────────────────────┐
  │  Scan list   │  Side-by-side comparison      │
  │  (scrollable │  ┌────────┬────────┐         │
  │   with date, │  │ Scan A │ Scan B │         │
  │   score,     │  └────────┴────────┘         │
  │   thumbnail) │                               │
  │              ├──────────────────────────────┤
  │              │  Risk score trend (chart)     │
  └──────────────┴──────────────────────────────┘
"""

import logging
from datetime import datetime

import cv2
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap, QFont
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QGroupBox, QSplitter, QPushButton,
)

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

log = logging.getLogger(__name__)


def _bgr_thumb(img: np.ndarray, size: int = 80) -> QPixmap:
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class HistoryTab(QWidget):
    def __init__(self, pipeline, parent=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self._scans = []        # list of scan dicts from DB
        self._selected = []     # up to 2 indices for comparison
        self._build_ui()

    # ── UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)

        # -- Left: scan list --
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)

        lbl = QLabel("Patient Scans")
        lbl.setFont(QFont("Inter", 13, QFont.Bold))
        left_layout.addWidget(lbl)

        self._scan_list = QListWidget()
        self._scan_list.itemClicked.connect(self._on_scan_clicked)
        left_layout.addWidget(self._scan_list)

        btn_refresh = QPushButton("🔄  Refresh")
        btn_refresh.clicked.connect(self.load_scans)
        left_layout.addWidget(btn_refresh)

        splitter.addWidget(left_widget)

        # -- Right: comparison + trend --
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Side-by-side comparison
        comp_group = QGroupBox("Comparison (select two scans)")
        comp_layout = QHBoxLayout(comp_group)
        self._comp_a = QLabel("Scan A")
        self._comp_a.setAlignment(Qt.AlignCenter)
        self._comp_a.setMinimumSize(250, 200)
        self._comp_a.setStyleSheet("background: #1a1a1a; color: #666;")
        self._comp_b = QLabel("Scan B")
        self._comp_b.setAlignment(Qt.AlignCenter)
        self._comp_b.setMinimumSize(250, 200)
        self._comp_b.setStyleSheet("background: #1a1a1a; color: #666;")
        comp_layout.addWidget(self._comp_a)
        comp_layout.addWidget(self._comp_b)
        right_layout.addWidget(comp_group)

        # Trend chart
        trend_group = QGroupBox("Risk Score Trend")
        trend_layout = QVBoxLayout(trend_group)
        self._figure = Figure(figsize=(5, 2.2), dpi=100)
        self._figure.patch.set_facecolor("#1a1a1a")
        self._canvas = FigureCanvas(self._figure)
        self._canvas.setMinimumHeight(160)
        trend_layout.addWidget(self._canvas)
        right_layout.addWidget(trend_group)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        outer = QHBoxLayout(self)
        outer.addWidget(splitter)

    # ── Data ───────────────────────────────────────────────────────────

    def load_scans(self):
        """Reload scan list from database for the current patient."""
        main_win = self.window()
        patient_id = getattr(main_win, "patient_id", "") or None
        self._scans = self._pipeline.db.list_scans(patient_id)
        self._selected.clear()
        self._populate_list()
        self._update_trend()

    def _populate_list(self):
        self._scan_list.clear()
        for scan in self._scans:
            ts = scan.get("timestamp", "")
            score = scan.get("risk_score", 0)
            label = scan.get("risk_label", "")
            item = QListWidgetItem(f"{ts}   Score: {score:.0f}  [{label}]")
            self._scan_list.addItem(item)

    # ── Selection for comparison ───────────────────────────────────────

    def _on_scan_clicked(self, item: QListWidgetItem):
        idx = self._scan_list.row(item)
        if idx in self._selected:
            self._selected.remove(idx)
        else:
            self._selected.append(idx)
            if len(self._selected) > 2:
                self._selected.pop(0)
        self._update_comparison()

    def _update_comparison(self):
        labels = [self._comp_a, self._comp_b]
        for i, lbl in enumerate(labels):
            if i < len(self._selected):
                scan = self._scans[self._selected[i]]
                heatmap_path = scan.get("heatmap_path")
                if heatmap_path:
                    img = cv2.imread(heatmap_path)
                    if img is not None:
                        pix = _bgr_thumb(img, 250)
                        lbl.setPixmap(pix)
                        continue
                lbl.setText(f"Scan {self._selected[i] + 1}")
            else:
                lbl.clear()
                lbl.setText("Select a scan")

    # ── Trend chart ────────────────────────────────────────────────────

    def _update_trend(self):
        self._figure.clear()
        if not self._scans:
            self._canvas.draw()
            return

        ax = self._figure.add_subplot(111)
        ax.set_facecolor("#1a1a1a")

        scores = [s.get("risk_score", 0) for s in self._scans]
        dates = list(range(1, len(scores) + 1))

        ax.plot(dates, scores, "-o", color="#00d4aa", markersize=5, linewidth=2)
        ax.axhline(y=60, color="#D32F2F", linestyle="--", linewidth=0.8, alpha=0.6)
        ax.axhline(y=40, color="#FF5722", linestyle="--", linewidth=0.8, alpha=0.6)
        ax.axhline(y=20, color="#FF9800", linestyle="--", linewidth=0.8, alpha=0.6)

        ax.set_xlabel("Scan #", color="white", fontsize=9)
        ax.set_ylabel("Risk Score", color="white", fontsize=9)
        ax.set_ylim(-5, 105)
        ax.tick_params(colors="white", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#444")

        self._figure.tight_layout()
        self._canvas.draw()
