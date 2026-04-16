"""Tests for threshold-based risk scorer."""

import numpy as np
import pytest

from optifoot.analysis.risk_scorer import ThresholdScorer, RiskResult


class TestThresholdScorer:

    def setup_method(self):
        self.scorer = ThresholdScorer()

    def test_all_normal_spo2(self):
        """A foot with uniformly high SpO₂ should score as Normal."""
        spo2 = np.full((100, 100), 98.0)
        result = self.scorer.score(spo2)
        assert result.label == "Normal"
        assert result.score < 20
        assert result.mean_spo2 == pytest.approx(98.0, abs=0.1)
        assert result.pct_critical == 0.0
        assert result.pct_normal > 99.0

    def test_all_critical_spo2(self):
        """A foot with uniformly low SpO₂ should score as Critical."""
        spo2 = np.full((100, 100), 50.0)  # very low SpO₂
        result = self.scorer.score(spo2)
        assert result.label == "Critical"
        assert result.score >= 60
        assert result.pct_critical > 99.0

    def test_mixed_zones(self):
        """A foot with mixed oxygenation should produce intermediate score."""
        spo2 = np.zeros((100, 100))
        spo2[:50, :] = 97.0    # top half is normal
        spo2[50:, :] = 80.0    # bottom half is critical
        result = self.scorer.score(spo2)
        assert result.label in ("Monitor", "At Risk", "Critical")
        assert 20 < result.score < 80
        assert result.pct_normal > 40
        assert result.pct_critical > 40

    def test_empty_mask_returns_unknown(self):
        """If no foot pixels exist, result should be Unknown with score 0."""
        spo2 = np.zeros((100, 100))  # all zeros = no foot
        result = self.scorer.score(spo2)
        assert result.label == "Unknown"
        assert result.score == 0

    def test_result_has_all_fields(self):
        """RiskResult should contain all expected metrics."""
        spo2 = np.full((50, 50), 92.0)
        result = self.scorer.score(spo2)
        assert isinstance(result, RiskResult)
        assert hasattr(result, "score")
        assert hasattr(result, "label")
        assert hasattr(result, "mean_spo2")
        assert hasattr(result, "min_spo2")
        assert hasattr(result, "pct_critical")
        assert hasattr(result, "pct_at_risk")
        assert hasattr(result, "pct_monitor")
        assert hasattr(result, "pct_normal")
        assert hasattr(result, "largest_critical_area_px")
