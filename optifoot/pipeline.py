"""
Central processing pipeline -- wires capture -> preprocess -> SpO2 -> heatmap -> risk score.

Holds references to other components and stores the latest results so the
GUI tabs can read them.
"""

import logging
from dataclasses import asdict

import numpy as np

from optifoot import config
from optifoot.capture.led_controller import BaseLEDController, create_led_controller
from optifoot.capture.camera import BaseCamera, create_camera
from optifoot.processing.preprocessing import preprocess, align_images, create_foot_mask, apply_roi
from optifoot.processing.oxygenation import calculate_spo2_map
from optifoot.processing.heatmap import generate_heatmap, overlay_risk_zones, add_colorbar
from optifoot.analysis.risk_scorer import RiskResult, create_scorer
from optifoot.storage.database import Database

log = logging.getLogger(__name__)


# -- Demo override profiles --------------------------------------------------
_OVERRIDE_PROFILES = {
    "1": {
        "score": 5.0, "label": "Normal",
        "mean_spo2": 97.2, "min_spo2": 95.0,
        "pct_critical": 0.0, "pct_at_risk": 0.0,
        "pct_monitor": 2.8, "pct_normal": 97.2,
        "spo2_range": (93.0, 98.0),
    },
    "0": {
        "score": 82.0, "label": "Critical",
        "mean_spo2": 3.0, "min_spo2": 1.0,
        "pct_critical": 78.0, "pct_at_risk": 15.0,
        "pct_monitor": 5.0, "pct_normal": 2.0,
        "spo2_range": (1.0, 5.0),
    },
}


class Pipeline:
    """Orchestrates the full image-processing pipeline."""

    def __init__(self):
        self._leds: BaseLEDController = create_led_controller()
        self._camera: BaseCamera = create_camera(self._leds)
        self._scorer = create_scorer()
        self._db = Database()

        # Cached results from last run
        self.last_spo2_map: np.ndarray | None = None
        self.last_heatmap: np.ndarray | None = None
        self.last_heatmap_no_zones: np.ndarray | None = None
        self.last_risk_result: RiskResult | None = None

    # ── Accessors ──────────────────────────────────────────────────────

    @property
    def camera(self) -> BaseCamera:
        return self._camera

    @property
    def db(self) -> Database:
        return self._db

    # ── Main processing entry point ────────────────────────────────────

    def process(self, img_650: np.ndarray, img_850: np.ndarray) -> RiskResult:
        """Run the full pipeline on a pair of captured images.

        Steps:
          1. Preprocess (blur + grayscale)
          2. Align the two captures
          3. Create foot mask
          4. Compute SpO₂ map (Beer-Lambert)
          5. Generate heatmap visualisation
          6. Score risk
        """
        # 1. Preprocess
        img_650 = preprocess(img_650)
        img_850 = preprocess(img_850)

        # 2. Align
        img_650, img_850 = align_images(img_650, img_850)

        # 3. Foot mask
        mask = create_foot_mask(img_650)

        # 4. SpO₂ map
        spo2_map = calculate_spo2_map(img_650, img_850, mask)
        self.last_spo2_map = spo2_map

        # 5. Heatmap
        heatmap_base = generate_heatmap(spo2_map)
        self.last_heatmap_no_zones = add_colorbar(heatmap_base.copy())
        heatmap_zones = overlay_risk_zones(heatmap_base, spo2_map)
        self.last_heatmap = add_colorbar(heatmap_zones)

        # 6. Risk scoring
        result = self._scorer.score(spo2_map)

        # 7. Demo override (if enabled via config.DEMO_OVERRIDE)
        if config.DEMO_OVERRIDE in _OVERRIDE_PROFILES:
            profile = _OVERRIDE_PROFILES[config.DEMO_OVERRIDE]
            # Replace SpO2 map values so heatmaps match
            foot_mask = spo2_map > 0
            lo, hi = profile["spo2_range"]
            spo2_map[foot_mask] = np.random.uniform(lo, hi, size=np.sum(foot_mask)).astype(np.float32)
            self.last_spo2_map = spo2_map
            # Regenerate heatmaps from overridden SpO2 map
            heatmap_base = generate_heatmap(spo2_map)
            self.last_heatmap_no_zones = add_colorbar(heatmap_base.copy())
            heatmap_zones = overlay_risk_zones(heatmap_base, spo2_map)
            self.last_heatmap = add_colorbar(heatmap_zones)
            # Override the result
            result = RiskResult(
                score=profile["score"], label=profile["label"],
                mean_spo2=profile["mean_spo2"], min_spo2=profile["min_spo2"],
                pct_critical=profile["pct_critical"], pct_at_risk=profile["pct_at_risk"],
                pct_monitor=profile["pct_monitor"], pct_normal=profile["pct_normal"],
                largest_critical_area_px=result.largest_critical_area_px,
            )
            log.info("DEMO OVERRIDE applied: %s", profile["label"])

        self.last_risk_result = result
        log.info("Pipeline complete -- risk score: %.1f (%s)", result.score, result.label)
        return result

    # ── Persistence ────────────────────────────────────────────────────

    def save_scan(self, patient_id: str) -> int:
        """Save the latest processed scan to the database."""
        if self.last_spo2_map is None or self.last_risk_result is None:
            raise RuntimeError("No processed scan to save")

        r = self.last_risk_result
        metrics = asdict(r)
        return self._db.save_scan(
            patient_id=patient_id,
            spo2_map=self.last_spo2_map,
            heatmap=self.last_heatmap,
            risk_score=r.score,
            risk_label=r.label,
            metrics=metrics,
        )

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start(self):
        self._camera.start()
        log.info("Pipeline started")

    def shutdown(self):
        self._camera.close()
        self._leds.close()
        self._db.close()
        log.info("Pipeline shut down")
