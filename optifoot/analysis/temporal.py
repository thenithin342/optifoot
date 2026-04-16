"""
Temporal analysis — compare sequential scans and generate trends.

Provides:
  - Pixel-wise SpO₂ difference maps (improvement / deterioration)
  - Summary statistics of change between two scans
  - Risk-score trend data for charting
"""

import logging
from dataclasses import dataclass
from typing import Dict, List

import cv2
import numpy as np

from optifoot import config

log = logging.getLogger(__name__)


@dataclass
class ComparisonResult:
    """Output of comparing two SpO₂ maps."""
    diff_map: np.ndarray         # signed float: positive = improvement
    mean_change: float           # positive = overall improvement
    critical_area_change: float  # negative = more critical area (worse)
    at_risk_area_change: float
    improved_pct: float          # % of foot pixels that improved
    worsened_pct: float          # % of foot pixels that worsened


def compare_scans(
    spo2_current: np.ndarray,
    spo2_previous: np.ndarray,
) -> ComparisonResult:
    """Compute per-pixel and summary differences between two scans.

    Positive diff = oxygenation improved (current > previous).
    Negative diff = oxygenation worsened.
    """
    # Intersect masks so we only compare overlapping foot regions
    mask_curr = spo2_current > 0
    mask_prev = spo2_previous > 0
    mask = mask_curr & mask_prev

    diff = np.zeros_like(spo2_current, dtype=np.float64)
    diff[mask] = spo2_current[mask] - spo2_previous[mask]

    foot_count = np.count_nonzero(mask)
    if foot_count == 0:
        return ComparisonResult(
            diff_map=diff, mean_change=0, critical_area_change=0,
            at_risk_area_change=0, improved_pct=0, worsened_pct=0,
        )

    mean_change = float(diff[mask].mean())

    # Critical area fraction change
    crit_curr = np.count_nonzero(
        (spo2_current < config.SPO2_AT_RISK_MIN) & mask
    ) / foot_count * 100
    crit_prev = np.count_nonzero(
        (spo2_previous < config.SPO2_AT_RISK_MIN) & mask
    ) / foot_count * 100
    critical_area_change = crit_curr - crit_prev  # positive = more critical = worse

    # At-risk area change
    ar_curr = np.count_nonzero(
        (spo2_current >= config.SPO2_AT_RISK_MIN)
        & (spo2_current < config.SPO2_MONITOR_MIN) & mask
    ) / foot_count * 100
    ar_prev = np.count_nonzero(
        (spo2_previous >= config.SPO2_AT_RISK_MIN)
        & (spo2_previous < config.SPO2_MONITOR_MIN) & mask
    ) / foot_count * 100
    at_risk_area_change = ar_curr - ar_prev

    improved_pct = float(np.count_nonzero(diff[mask] > 1.0) / foot_count * 100)
    worsened_pct = float(np.count_nonzero(diff[mask] < -1.0) / foot_count * 100)

    result = ComparisonResult(
        diff_map=diff,
        mean_change=round(mean_change, 2),
        critical_area_change=round(critical_area_change, 2),
        at_risk_area_change=round(at_risk_area_change, 2),
        improved_pct=round(improved_pct, 1),
        worsened_pct=round(worsened_pct, 1),
    )
    log.info(
        "Temporal comparison — mean ΔSpO₂: %+.2f%%  improved: %.1f%%  worsened: %.1f%%",
        result.mean_change, result.improved_pct, result.worsened_pct,
    )
    return result


def generate_diff_heatmap(diff_map: np.ndarray) -> np.ndarray:
    """Visualise the difference map as a diverging colourmap image.

    Green = improved, Red = worsened, Black = no change / background.
    """
    mask = diff_map != 0
    vis = np.zeros((*diff_map.shape, 3), dtype=np.uint8)

    if not np.any(mask):
        return vis

    # Normalise diff to 0-255 range around centre (128)
    max_abs = max(np.abs(diff_map[mask]).max(), 1.0)
    norm = ((diff_map / max_abs) * 127 + 128).clip(0, 255).astype(np.uint8)

    # Use a diverging colourmap (red-blue inverted so red = negative, blue = positive)
    coloured = cv2.applyColorMap(norm, cv2.COLORMAP_COOL)
    vis[mask] = coloured[mask]

    return vis


def generate_trend(scan_history: List[Dict]) -> Dict:
    """Extract trend data from a list of scan records.

    Returns dict with 'timestamps' and 'scores' lists for plotting.
    """
    timestamps = []
    scores = []
    for scan in sorted(scan_history, key=lambda s: s.get("timestamp", "")):
        timestamps.append(scan.get("timestamp", ""))
        scores.append(scan.get("risk_score", 0))
    return {"timestamps": timestamps, "scores": scores}
