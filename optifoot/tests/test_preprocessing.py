"""Tests for image preprocessing functions."""

import numpy as np
import pytest

from optifoot.processing.preprocessing import preprocess, create_foot_mask, apply_roi


class TestPreprocess:

    def test_grayscale_passthrough(self):
        """Already grayscale images should pass through."""
        img = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
        result = preprocess(img)
        assert result.shape == (100, 100)
        assert result.dtype == np.uint8

    def test_reduces_noise(self):
        """Blurred image should have lower high-frequency content."""
        rng = np.random.default_rng(0)
        noisy = rng.integers(0, 255, (100, 100), dtype=np.uint8)
        smooth = preprocess(noisy)
        # Standard deviation should decrease after blur
        assert smooth.std() < noisy.std()


class TestCreateFootMask:

    def test_mask_is_binary(self):
        """Mask should only contain 0 and 255."""
        img = np.zeros((200, 200), dtype=np.uint8)
        img[50:150, 50:150] = 180  # bright square = "foot"
        mask = create_foot_mask(img)
        unique_vals = set(np.unique(mask))
        assert unique_vals <= {0, 255}

    def test_detects_bright_region(self):
        """A bright region on dark background should be detected as foot."""
        img = np.zeros((200, 200), dtype=np.uint8)
        img[40:160, 60:140] = 200
        mask = create_foot_mask(img)
        # Centre should be in the mask
        assert mask[100, 100] == 255
        # Corner should not
        assert mask[0, 0] == 0


class TestApplyROI:

    def test_zeros_outside_mask(self):
        img = np.full((100, 100), 150, dtype=np.uint8)
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[25:75, 25:75] = 255
        result = apply_roi(img, mask)
        assert result[0, 0] == 0
        assert result[50, 50] == 150
