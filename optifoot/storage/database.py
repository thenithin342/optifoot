"""
SQLite database for patient records and scan history.

Tables:
  patients(id TEXT PK, name TEXT, notes TEXT, created TEXT)
  scans(id INTEGER PK, patient_id TEXT FK, timestamp TEXT,
        spo2_map_path TEXT, heatmap_path TEXT,
        risk_score REAL, risk_label TEXT, metrics_json TEXT)
"""

import json
import logging
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from optifoot import config

log = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str | None = None):
        self._path = db_path or config.DB_PATH
        self._conn: Optional[sqlite3.Connection] = None
        self._open()
        self._migrate()

    # ── Connection ─────────────────────────────────────────────────────

    def _open(self):
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        log.info("Database opened: %s", self._path)

    def _migrate(self):
        cur = self._conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id      TEXT PRIMARY KEY,
                name    TEXT DEFAULT '',
                notes   TEXT DEFAULT '',
                created TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id      TEXT NOT NULL,
                timestamp       TEXT NOT NULL,
                spo2_map_path   TEXT,
                heatmap_path    TEXT,
                risk_score      REAL,
                risk_label      TEXT,
                metrics_json    TEXT,
                FOREIGN KEY (patient_id) REFERENCES patients(id)
            )
        """)
        self._conn.commit()
        log.info("Database schema ready")

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Patients ───────────────────────────────────────────────────────

    def ensure_patient(self, patient_id: str, name: str = ""):
        """Insert patient if not already present."""
        cur = self._conn.execute("SELECT id FROM patients WHERE id = ?", (patient_id,))
        if cur.fetchone() is None:
            self._conn.execute(
                "INSERT INTO patients (id, name, created) VALUES (?, ?, ?)",
                (patient_id, name, datetime.now().isoformat()),
            )
            self._conn.commit()

    # ── Scans ──────────────────────────────────────────────────────────

    def save_scan(
        self,
        patient_id: str,
        spo2_map: np.ndarray,
        heatmap: np.ndarray,
        risk_score: float,
        risk_label: str,
        metrics: Dict[str, Any],
    ) -> int:
        """Persist a scan: save images to disk, metadata to SQLite.

        Returns the scan row id.
        """
        self.ensure_patient(patient_id)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        scan_dir = os.path.join(config.SCANS_DIR, patient_id)
        os.makedirs(scan_dir, exist_ok=True)

        # Save SpO2 map as compressed numpy
        spo2_path = os.path.join(scan_dir, f"spo2_{ts}.npz")
        np.savez_compressed(spo2_path, spo2=spo2_map)

        # Save heatmap as PNG
        heatmap_path = os.path.join(scan_dir, f"heatmap_{ts}.png")
        cv2.imwrite(heatmap_path, heatmap)

        cur = self._conn.execute(
            """INSERT INTO scans
               (patient_id, timestamp, spo2_map_path, heatmap_path,
                risk_score, risk_label, metrics_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                patient_id,
                datetime.now().isoformat(),
                spo2_path,
                heatmap_path,
                risk_score,
                risk_label,
                json.dumps(metrics),
            ),
        )
        self._conn.commit()
        scan_id = cur.lastrowid
        log.info("Scan %d saved for patient %s", scan_id, patient_id)
        return scan_id

    def list_scans(self, patient_id: str | None = None) -> List[Dict]:
        """Return scans ordered by timestamp (newest first)."""
        if patient_id:
            rows = self._conn.execute(
                "SELECT * FROM scans WHERE patient_id = ? ORDER BY timestamp DESC",
                (patient_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM scans ORDER BY timestamp DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_scan(self, scan_id: int) -> Optional[Dict]:
        row = self._conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
        return dict(row) if row else None

    def load_spo2_map(self, scan_id: int) -> Optional[np.ndarray]:
        """Load the saved SpO₂ map numpy array for a scan."""
        scan = self.get_scan(scan_id)
        if scan and scan.get("spo2_map_path"):
            data = np.load(scan["spo2_map_path"])
            return data["spo2"]
        return None
