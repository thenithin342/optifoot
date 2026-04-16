"""
Image preprocessing for dual-wavelength NIR foot images.

Handles noise reduction, image alignment between the two captures,
and foot-region segmentation (masking out the background).
"""

import logging

import cv2
import numpy as np

from optifoot import config

log = logging.getLogger(__name__)


def preprocess(image: np.ndarray) -> np.ndarray:
    """Convert to grayscale (if needed) and apply Gaussian blur."""
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(
        image, (0, 0), sigmaX=config.GAUSSIAN_BLUR_SIGMA
    )
    return blurred


def align_images(
    img_650: np.ndarray, img_850: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Align the 850 nm image to the 650 nm reference using ECC.

    Compensates for slight patient/device movement between the two
    sequential captures.  Falls back to identity if alignment fails.
    """
    try:
        warp_matrix = np.eye(2, 3, dtype=np.float32)
        criteria = (
            cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
            50,      # max iterations
            1e-4,    # epsilon
        )
        _, warp_matrix = cv2.findTransformECC(
            img_650.astype(np.float32),
            img_850.astype(np.float32),
            warp_matrix,
            cv2.MOTION_EUCLIDEAN,
            criteria,
        )
        h, w = img_650.shape[:2]
        img_850_aligned = cv2.warpAffine(
            img_850, warp_matrix, (w, h),
            flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        )
        log.info("Image alignment succeeded (ECC)")
        return img_650, img_850_aligned

    except cv2.error:
        log.warning("Image alignment failed — proceeding without alignment")
        return img_650, img_850


def create_foot_mask(image: np.ndarray) -> np.ndarray:
    """Segment the foot region from the dark background.

    Uses Otsu thresholding + morphological cleanup to produce a
    binary mask (255 = foot, 0 = background).
    """
    # Otsu's binarisation
    _, mask = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Morphological close (fill holes) then open (remove noise)
    k = config.MORPH_KERNEL_SIZE
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    # Reject if the detected region is too small (likely failed segmentation)
    foot_ratio = np.count_nonzero(mask) / mask.size
    if foot_ratio < config.MIN_FOOT_AREA_RATIO:
        log.warning(
            "Foot mask covers only %.1f%% of image — segmentation may have failed",
            foot_ratio * 100,
        )

    log.info("Foot mask created (%.1f%% coverage)", foot_ratio * 100)
    return mask


def apply_roi(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Zero out pixels outside the foot mask."""
    return cv2.bitwise_and(image, image, mask=mask)
