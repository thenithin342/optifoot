"""
OptiFoot main window — PyQt5 application shell.

Three-tab layout: Capture | Results | History
Includes status bar and patient ID entry.
"""

import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QToolBar,
    QLabel, QLineEdit, QAction, QWidget, QHBoxLayout,
)

from optifoot.gui.capture_tab import CaptureTab
from optifoot.gui.results_tab import ResultsTab
from optifoot.gui.history_tab import HistoryTab

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, pipeline):
        """
        Parameters
        ----------
        pipeline : optifoot.pipeline.Pipeline
            Central pipeline object that coordinates capture → process → score.
        """
        super().__init__()
        self._pipeline = pipeline
        self.setWindowTitle("OptiFoot — Diabetic Foot Ulcer Early Detection")
        self.setMinimumSize(1024, 700)

        self._build_toolbar()
        self._build_tabs()
        self._build_statusbar()

    # ── Toolbar with patient ID ────────────────────────────────────────

    def _build_toolbar(self):
        toolbar = QToolBar("Patient")
        toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        lbl = QLabel("  Patient ID: ")
        lbl.setStyleSheet("font-weight: bold;")
        toolbar.addWidget(lbl)

        self._patient_input = QLineEdit()
        self._patient_input.setPlaceholderText("Enter patient identifier…")
        self._patient_input.setMaximumWidth(250)
        toolbar.addWidget(self._patient_input)

        toolbar.addSeparator()

        # Quick actions
        act_export = QAction("Export Report", self)
        act_export.triggered.connect(self._on_export)
        toolbar.addAction(act_export)

    # ── Tabs ───────────────────────────────────────────────────────────

    def _build_tabs(self):
        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        self._capture_tab = CaptureTab(self._pipeline, parent=self)
        self._results_tab = ResultsTab(self._pipeline, parent=self)
        self._history_tab = HistoryTab(self._pipeline, parent=self)

        self._tabs.addTab(self._capture_tab, "📷  Capture")
        self._tabs.addTab(self._results_tab, "🔬  Results")
        self._tabs.addTab(self._history_tab, "📊  History")

        # Wire signals: after processing, switch to Results tab
        self._capture_tab.processing_complete.connect(self._on_processing_done)

    # ── Status bar ─────────────────────────────────────────────────────

    def _build_statusbar(self):
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._status_label = QLabel("Ready")
        self._statusbar.addPermanentWidget(self._status_label)

    def set_status(self, text: str):
        self._status_label.setText(text)

    # ── Accessors ──────────────────────────────────────────────────────

    @property
    def patient_id(self) -> str:
        return self._patient_input.text().strip()

    # ── Slots ──────────────────────────────────────────────────────────

    def _on_processing_done(self):
        """Switch to Results tab after capture + process finishes."""
        self._results_tab.refresh()
        self._tabs.setCurrentWidget(self._results_tab)
        self.set_status("Processing complete")

    def _on_export(self):
        """Trigger report export from the Results tab."""
        self._results_tab.export_report()

    # ── Lifecycle ──────────────────────────────────────────────────────

    def closeEvent(self, event):
        log.info("Shutting down GUI")
        self._pipeline.shutdown()
        event.accept()
