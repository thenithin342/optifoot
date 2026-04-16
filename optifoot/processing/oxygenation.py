"""
Tissue oxygenation (SpO₂) estimation from dual-wavelength NIR images.

Uses the modified Beer-Lambert law to compute a per-pixel SpO₂ map
from 650 nm and 850 nm reflected-light images.

Theory (simplified for reflectance imaging):
    R  = ln(I_650) / ln(I_850)          per-pixel intensity ratio
    SpO₂ = (ε_HHb_850  -  R · ε_HHb_650)
          / ((ε_HHb_850 - ε_HbO2_850) - R · (ε_HHb_650 - ε_HbO2_650))

This gives the fraction of oxygenated haemoglobin [0–100 %].
"""

import logging

import numpy as np

from optifoot import config

log = logging.getLogger(__name__)

# Pre-compute denominator constant parts from extinction coefficients
_E_HBO2_650 = config.EPSILON_HBO2_650
_E_HBO2_850 = config.EPSILON_HBO2_850
_E_HHB_650 = config.EPSILON_HHB_650
_E_HHB_850 = config.EPSILON_HHB_850


def calculate_spo2_map(
    img_650: np.ndarray,
    img_850: np.ndarray,
    mask: np.ndarray,
) -> np.ndarray:
    """Compute a per-pixel SpO₂ map from dual-wavelength images.

    Parameters
    ----------
    img_650 : uint8 grayscale image captured under 650 nm illumination
    img_850 : uint8 grayscale image captured under 850 nm illumination
    mask    : binary mask (255 = foot region, 0 = background)

    Returns
    -------
    spo2_map : float64 array, same shape as inputs, values in [0, 100].
               Background pixels are 0.
    """
    # Work in float; clamp minimum to 2 to avoid log(0)
    i650 = np.clip(img_650.astype(np.float64), 2.0, 255.0)
    i850 = np.clip(img_850.astype(np.float64), 2.0, 255.0)

    # Optical-density ratio  R = ln(I_650) / ln(I_850)
    ln_650 = np.log(i650)
    ln_850 = np.log(i850)

    # Avoid division by zero where 850 nm is very dark
    with np.errstate(divide="ignore", invalid="ignore"):
        R = np.where(ln_850 > 0.01, ln_650 / ln_850, 1.0)

    # Beer-Lambert SpO₂ formula
    numerator = _E_HHB_850 - R * _E_HHB_650
    denominator = (_E_HHB_850 - _E_HBO2_850) - R * (_E_HHB_650 - _E_HBO2_650)

    with np.errstate(divide="ignore", invalid="ignore"):
        spo2 = np.where(
            np.abs(denominator) > 1e-8,
            (numerator / denominator) * 100.0,
            0.0,
        )

    # Clamp to physiologically meaningful range
    spo2 = np.clip(spo2, 0.0, 100.0)

    # Zero out background
    foot_mask = mask > 0
    spo2[~foot_mask] = 0.0

    # Stats for logging
    foot_vals = spo2[foot_mask]
    if foot_vals.size > 0:
        log.info(
            "SpO₂ map — mean: %.1f%%  min: %.1f%%  max: %.1f%%",
            foot_vals.mean(), foot_vals.min(), foot_vals.max(),
        )
    else:
        log.warning("SpO₂ map — no foot pixels found in mask")

    return spo2
