import json
import math
from datetime import datetime, timedelta, timezone

import pytest

from apex.backtest_forex_v3 import (
    apply_temperature,
    fit_temperature,
    multiclass_probability_metrics,
    walk_forward_v3,
)
from apex.forex_models_v2 import build_v2_samples, fit_gaussian_nb


def candles(count=1100):
    rows = []
    price = 1.10
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        drift = [0.00006, -0.00004, 0.00002, -0.00001][(i // 50) % 4]
        wave = math.sin(i / 7.0) * 0.0001
        previous = price
        price *= 1 + drift + wave
        rows.append({
            "timestamp": (start + timedelta(hours=i)).isoformat(),
            "open": previous,
            "high": max(previous, price) + 0.00012,
            "low": min(previous, price) - 0.00012,
            "close": price,
            "volume": 0,
        })
    return rows


def test_temperature_scaling_is_normalized_and_preserves_class_order():
    raw = {-1: 0.70, 0: 0.20, 1: 0.10}
    calibrated = apply_temperature(raw, 1.0)
    assert calibrated == pytest.approx(raw)
    sharpened = apply_temperature(raw, 0.5)
    softened = apply_temperature(raw, 2.0)
    assert sum(sharpened.values()) == pytest.approx(1.0)
    assert sum(softened.values()) == pytest.approx(1.0)
    assert sharpened[-1] > raw[-1]
    assert softened[-1] < raw[-1]


def test_temperature_fit_and_probability_metrics_use_explicit_validation_samples():
    samples = build_v2_samples(candles())
    training = samples[:450]
    calibration = samples[500:700]
    model = fit_gaussian_nb(training)
    result = fit_temperature(model, calibration)
    assert 0.5 <= result["temperature"] <= 3.0
    assert result["calibration_rows"] == len(calibration)
    probabilities = {
        sample.source_index: apply_temperature(
            model.probabilities(sample.features), result["temperature"]
        )
        for sample in calibration
    }
    metrics = multiclass_probability_metrics(calibration, probabilities)
    assert metrics["rows"] == len(calibration)
    assert math.isfinite(metrics["log_loss"])
    assert math.isfinite(metrics["multiclass_brier_score"])
    assert 0 <= metrics["expected_calibration_error_10_bins"] <= 1


def test_v3_walk_forward_purges_splits_and_exports_research_only_artifacts(tmp_path):
    report = walk_forward_v3(
        candles(),
        initial_train_bars=800,
        test_bars=100,
        max_folds=2,
        locked_test_end="2024-10-01",
        min_validation_trades=3,
        trees=5,
        model_dir=tmp_path,
        symbol="EURUSD=X",
    )
    assert report["status"] == "RESEARCH_ONLY"
    assert report["trading_authorized"] is False
    assert report["outer_test_period_is_disjoint_from_v2_recent_hourly_window"] is True
    assert len(report["folds"]) == 2
    for fold in report["folds"]:
        assert fold["fit_rows"] >= 100
        assert fold["calibration_rows"] >= 30
        assert fold["threshold_selection_rows"] >= 30
        assert fold["purge_horizon_bars"] == 3
        assert fold["fit_end"] < fold["calibration_start"]
        assert fold["calibration_end"] < fold["threshold_selection_start"]
        assert fold["threshold_selection_end"] < fold["outer_test_start"]
        assert fold["outer_test_end"] < "2024-10-01"
        assert set(fold["temperature_fit"]) == {
            "v2_gaussian_nb", "v2_random_forest"
        }
        assert set(fold["outer_test_probability_metrics"]) == {
            "v2_gaussian_nb", "v2_random_forest"
        }
    assert "v3_gaussian_nb_selected_double_cost_stress" in report["aggregate_strategies"]
    for model in ("v2_gaussian_nb", "v2_random_forest"):
        metadata = tmp_path / f"EURUSD_X_{model}_v3_calibration.json"
        payload = json.loads(metadata.read_text())
        assert payload["research_only"] is True
        assert payload["trading_authorized"] is False
