"""
Heatmap generation from SpO₂ maps.

Converts the float SpO₂ array into a colour-mapped image with
risk-zone contour overlays and an optional colour-bar legend.
"""

import logging

import cv2
import numpy as np

from optifoot import config

log = logging.getLogger(__name__)


def generate_heatmap(spo2_map: np.ndarray) -> np.ndarray:
    """Map SpO₂ values [0-100] to a JET colourmap image (BGR).

    Blue = high oxygen (good), Red = low oxygen (critical).
    Background (0) stays black.
    """
    # Normalise to 0-255 for colourmap (invert so red = low SpO2)
    norm = np.zeros_like(spo2_map, dtype=np.uint8)
    foot_mask = spo2_map > 0
    if np.any(foot_mask):
        # Map 0-100% → 0-255 (inverted: 100 %→255 blue, 0%→0 red)
        norm[foot_mask] = (spo2_map[foot_mask] * 2.55).clip(0, 255).astype(np.uint8)

    heatmap = cv2.applyColorMap(norm, cv2.COLORMAP_JET)

    # Black out the background
    heatmap[~foot_mask] = 0

    log.info("Heatmap generated")
    return heatmap


def overlay_risk_zones(
    heatmap: np.ndarray,
    spo2_map: np.ndarray,
) -> np.ndarray:
    """Draw contour outlines around critical and at-risk regions.

    - Critical (<85 %): thick red contour
    - At-Risk (85-90 %): yellow contour
    - Monitor (90-95 %): thin cyan contour
    """
    output = heatmap.copy()

    zones = [
        (spo2_map < config.SPO2_AT_RISK_MIN,   (0, 0, 255),   2, "Critical"),
        (
            (spo2_map >= config.SPO2_AT_RISK_MIN) & (spo2_map < config.SPO2_MONITOR_MIN),
            (0, 255, 255),
            2,
            "At Risk",
        ),
        (
            (spo2_map >= config.SPO2_MONITOR_MIN) & (spo2_map < config.SPO2_NORMAL_MIN),
            (255, 255, 0),
            1,
            "Monitor",
        ),
    ]

    for zone_mask, colour, thickness, label in zones:
        # Only consider foot pixels
        zone_mask = zone_mask & (spo2_map > 0)
        if not np.any(zone_mask):
            continue
        binary = (zone_mask.astype(np.uint8)) * 255
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(output, contours, -1, colour, thickness)
        log.debug("Drew %d contours for %s zone", len(contours), label)

    return output


def add_colorbar(image: np.ndarray, bar_width: int = 40, padding: int = 10) -> np.ndarray:
    """Append a vertical SpO₂ colour-bar legend to the right of the image.

    Returns a wider image with the bar and tick labels.
    """
    h, w = image.shape[:2]

    # Build gradient strip (bottom=0%, top=100%)
    gradient = np.linspace(0, 255, h, dtype=np.uint8).reshape(-1, 1)
    gradient = np.repeat(gradient, bar_width, axis=1)
    bar_colour = cv2.applyColorMap(gradient, cv2.COLORMAP_JET)

    # Canvas for bar + labels
    label_width = 60
    canvas = np.zeros((h, bar_width + label_width + padding, 3), dtype=np.uint8)
    canvas[:, padding: padding + bar_width] = bar_colour

    # Tick labels
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.4
    for pct in (0, 25, 50, 75, 100):
        y = h - 1 - int(pct / 100 * (h - 1))
        x_text = padding + bar_width + 4
        cv2.putText(canvas, f"{pct}%", (x_text, y + 4), font, font_scale, (255, 255, 255), 1)
        cv2.line(canvas, (padding, y), (padding + bar_width, y), (255, 255, 255), 1)

    # Concatenate
    combined = np.hstack([image, canvas])
    log.info("Colour bar appended")
    return combined


def create_full_visualisation(spo2_map: np.ndarray) -> np.ndarray:
    """Convenience: heatmap + risk zone contours + colour bar."""
    heatmap = generate_heatmap(spo2_map)
    heatmap = overlay_risk_zones(heatmap, spo2_map)
    heatmap = add_colorbar(heatmap)
    return heatmap
