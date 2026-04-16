"""
Risk scoring from SpO₂ maps.

Uses a strategy pattern so the scoring method can be swapped later:
  - ThresholdScorer (default): rule-based, no training data needed
  - MLScorer (future):         drop-in replacement using TFLite/ONNX model

Both return the same RiskResult dataclass.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict

import cv2
import numpy as np

from optifoot import config

log = logging.getLogger(__name__)


# ── Result container ───────────────────────────────────────────────────────

@dataclass
class RiskResult:
    """Structured output from any risk scorer."""
    score: float             # composite risk 0 (safe) → 100 (critical)
    label: str               # "Normal" | "Monitor" | "At Risk" | "Critical"
    mean_spo2: float
    min_spo2: float
    pct_critical: float      # % of foot area below 85 %
    pct_at_risk: float       # % of foot area 85-90 %
    pct_monitor: float       # % of foot area 90-95 %
    pct_normal: float        # % of foot area >= 95 %
    largest_critical_area_px: int  # largest contiguous critical zone (pixels)
    metrics: Dict = field(default_factory=dict)  # extra key-value pairs


# ── Scorer interface ───────────────────────────────────────────────────────

class BaseScorer(ABC):
    @abstractmethod
    def score(self, spo2_map: np.ndarray) -> RiskResult: ...


# ── Threshold-based scorer ─────────────────────────────────────────────────

class ThresholdScorer(BaseScorer):
    """Rule-based risk scoring using SpO₂ statistics and thresholds."""

    def score(self, spo2_map: np.ndarray) -> RiskResult:
        foot_mask = spo2_map > 0
        foot_vals = spo2_map[foot_mask]

        if foot_vals.size == 0:
            return RiskResult(
                score=0, label="Unknown", mean_spo2=0, min_spo2=0,
                pct_critical=0, pct_at_risk=0, pct_monitor=0, pct_normal=0,
                largest_critical_area_px=0,
            )

        total = foot_vals.size
        mean_spo2 = float(foot_vals.mean())
        min_spo2 = float(foot_vals.min())

        pct_critical = float(np.sum(foot_vals < config.SPO2_AT_RISK_MIN) / total * 100)
        pct_at_risk = float(np.sum(
            (foot_vals >= config.SPO2_AT_RISK_MIN) & (foot_vals < config.SPO2_MONITOR_MIN)
        ) / total * 100)
        pct_monitor = float(np.sum(
            (foot_vals >= config.SPO2_MONITOR_MIN) & (foot_vals < config.SPO2_NORMAL_MIN)
        ) / total * 100)
        pct_normal = float(np.sum(foot_vals >= config.SPO2_NORMAL_MIN) / total * 100)

        # Largest contiguous critical region
        critical_mask = ((spo2_map < config.SPO2_AT_RISK_MIN) & foot_mask).astype(np.uint8) * 255
        largest_area = 0
        if np.any(critical_mask):
            contours, _ = cv2.findContours(critical_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest_area = int(max(cv2.contourArea(c) for c in contours))

        # ── Composite risk score ──────────────────────────────────────
        # Higher is worse.  Each component normalised to 0-100.
        #   mean_spo2 component: invert so lower SpO2 = higher risk
        mean_component = max(0.0, (100.0 - mean_spo2))  # 0 when SpO2=100, 100 when SpO2=0

        #   critical-area component: direct percentage (0-100)
        crit_component = min(pct_critical, 100.0)

        #   at-risk area component
        risk_component = min(pct_at_risk + pct_monitor, 100.0)

        #   cluster size: normalise against 5 % of foot (arbitrary cap)
        cluster_cap = total * 0.05
        cluster_component = min(largest_area / max(cluster_cap, 1) * 100, 100.0)

        composite = (
            config.WEIGHT_MEAN_SPO2 * mean_component
            + config.WEIGHT_CRITICAL_AREA * crit_component
            + config.WEIGHT_AT_RISK_AREA * risk_component
            + config.WEIGHT_CLUSTER_SIZE * cluster_component
        )
        composite = round(min(composite, 100.0), 1)

        # ── Classification ────────────────────────────────────────────
        if composite >= 60:
            label = "Critical"
        elif composite >= 40:
            label = "At Risk"
        elif composite >= 20:
            label = "Monitor"
        else:
            label = "Normal"

        result = RiskResult(
            score=composite,
            label=label,
            mean_spo2=round(mean_spo2, 1),
            min_spo2=round(min_spo2, 1),
            pct_critical=round(pct_critical, 1),
            pct_at_risk=round(pct_at_risk, 1),
            pct_monitor=round(pct_monitor, 1),
            pct_normal=round(pct_normal, 1),
            largest_critical_area_px=largest_area,
        )

        log.info(
            "Risk assessment — score: %.1f (%s)  mean SpO₂: %.1f%%",
            result.score, result.label, result.mean_spo2,
        )
        return result


# ── Factory ────────────────────────────────────────────────────────────────

def create_scorer() -> BaseScorer:
    """Return the active scorer.  Swap this to MLScorer when ready."""
    return ThresholdScorer()
