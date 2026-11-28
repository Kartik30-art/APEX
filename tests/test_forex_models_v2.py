import math
from datetime import datetime, timedelta, timezone

import pytest

from apex.forex_models_v2 import (
    FEATURE_NAMES_V2,
    build_v2_samples,
    features_at_v2,
    fit_gaussian_nb,
    fit_random_forest,
    save_v2_model,
)


def candles(count=850):
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


def test_v2_features_are_causal_and_have_expected_width():
    rows = candles()
    before = features_at_v2(rows, 500)
    changed_future = [dict(row) for row in rows]
    for row in changed_future[501:]:
        row["open"] *= 2
        row["high"] *= 2
        row["low"] *= 2
        row["close"] *= 2
    after = features_at_v2(changed_future, 500)
    assert len(before) == len(FEATURE_NAMES_V2)
    assert before == after


def test_v2_classifiers_return_valid_probabilities_and_save_artifacts(tmp_path):
    samples = build_v2_samples(candles())
    train = samples[:500]
    nb = fit_gaussian_nb(train)
    forest = fit_random_forest(train, n_trees=5, max_depth=2, min_leaf=20)
    for model in (nb, forest):
        probabilities = model.probabilities(train[-1].features)
        assert set(probabilities) == {-1, 0, 1}
        assert all(0 <= p <= 1 for p in probabilities.values())
        assert sum(probabilities.values()) == pytest.approx(1.0)
    path = tmp_path / "v2.json"
    save_v2_model(forest, path)
    import json
    payload = json.loads(path.read_text())
    assert payload["research_only"] is True
    assert payload["trading_authorized"] is False
    assert payload["format_version"] == 2
