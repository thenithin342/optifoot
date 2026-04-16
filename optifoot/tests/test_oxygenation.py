"""Tests for SpO₂ oxygenation calculation."""

import numpy as np
import pytest

from optifoot import config


# We need a mask for tests
def _foot_mask(shape):
    mask = np.ones(shape, dtype=np.uint8) * 255
    return mask


class TestCalculateSpO2Map:
    """Verify Beer-Lambert SpO₂ calculation with controlled inputs."""

    def test_identical_images_return_valid_spo2(self):
        """When 650 nm and 850 nm images are identical, ratio R = 1.0
        and the SpO₂ should be a specific (constant) value across all pixels."""
        from optifoot.processing.oxygenation import calculate_spo2_map

        img = np.full((100, 100), 128, dtype=np.uint8)
        mask = _foot_mask((100, 100))
        spo2 = calculate_spo2_map(img, img, mask)

        assert spo2.shape == (100, 100)
        foot_vals = spo2[mask > 0]
        # All values should be the same (R=1 → constant SpO₂)
        assert np.std(foot_vals) < 0.01
        # Should be in valid range
        assert 0 <= foot_vals.mean() <= 100

    def test_brighter_650_gives_different_spo2_than_brighter_850(self):
        """Higher 650 nm reflection relative to 850 nm should shift SpO₂."""
        from optifoot.processing.oxygenation import calculate_spo2_map

        mask = _foot_mask((100, 100))
        # Scenario A: 650 nm brighter → R > 1
        img_650_bright = np.full((100, 100), 200, dtype=np.uint8)
        img_850_dim = np.full((100, 100), 80, dtype=np.uint8)
        spo2_a = calculate_spo2_map(img_650_bright, img_850_dim, mask)

        # Scenario B: 850 nm brighter → R < 1
        img_650_dim = np.full((100, 100), 80, dtype=np.uint8)
        img_850_bright = np.full((100, 100), 200, dtype=np.uint8)
        spo2_b = calculate_spo2_map(img_650_dim, img_850_bright, mask)

        # The two scenarios should produce different mean SpO₂
        mean_a = spo2_a[mask > 0].mean()
        mean_b = spo2_b[mask > 0].mean()
        assert mean_a != pytest.approx(mean_b, abs=1.0)

    def test_background_is_zero(self):
        """Pixels outside the mask should remain 0."""
        from optifoot.processing.oxygenation import calculate_spo2_map

        img = np.full((100, 100), 128, dtype=np.uint8)
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[20:80, 20:80] = 255  # only centre is foot

        spo2 = calculate_spo2_map(img, img, mask)
        assert spo2[0, 0] == 0.0
        assert spo2[10, 10] == 0.0
        assert spo2[50, 50] > 0  # inside mask

    def test_output_clamped_0_100(self):
        """SpO₂ values should never exceed [0, 100]."""
        from optifoot.processing.oxygenation import calculate_spo2_map

        # Extreme intensity difference
        img_650 = np.full((50, 50), 250, dtype=np.uint8)
        img_850 = np.full((50, 50), 2, dtype=np.uint8)
        mask = _foot_mask((50, 50))

        spo2 = calculate_spo2_map(img_650, img_850, mask)
        assert spo2.min() >= 0.0
        assert spo2.max() <= 100.0
