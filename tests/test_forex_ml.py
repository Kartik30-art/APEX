import math
from datetime import datetime, timedelta, timezone

import pytest

from apex.forex_data import save_history, validate_history
from apex.forex_ml import (
    build_samples,
    load_model,
    predict_latest,
    save_model,
    train_model,
)


def synthetic_candles(count=900):
    rows = []
    price = 1.10
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for index in range(count):
        cycle = math.sin(index / 9.0) * 0.00025
        drift = 0.000035 if (index // 90) % 2 == 0 else -0.000035
        previous = price
        price = max(0.5, price * (1.0 + drift + cycle))
        rows.append({
            "timestamp": (start + timedelta(hours=index)).isoformat(),
            "open": previous,
            "high": max(previous, price) + 0.00015,
            "low": min(previous, price) - 0.00015,
            "close": price,
            "volume": 0,
        })
    return rows


def test_history_validation_orders_rows_and_rejects_duplicates():
    rows = synthetic_candles(10)
    assert len(validate_history(rows)) == 10
    with pytest.raises(ValueError, match="duplicate"):
        validate_history(rows + [rows[-1]])


def test_dataset_csv_roundtrip_and_manifest(tmp_path):
    rows = synthetic_candles(20)
    path = tmp_path / "EURUSD_1h.csv"
    manifest = save_history(
        rows, path, symbol="EURUSD=X", interval="1h", period="2y"
    )
    assert manifest["source_is_official_or_licensed"] is False
    assert path.with_suffix(".csv.manifest.json").exists()


def test_training_creates_research_only_model_and_holdout_metrics(tmp_path):
    rows = synthetic_candles()
    samples = build_samples(rows, horizon_bars=3)
    assert len(samples) > 700
    model_path = tmp_path / "model.json"
    model, metrics = train_model(
        rows, model_path=model_path, epochs=30, patience=5
    )
    assert model_path.exists()
    assert metrics["status"] == "RESEARCH_ONLY"
    assert metrics["trading_authorized"] is False
    assert metrics["holdout"]["rows"] > 20
    assert 0 <= metrics["holdout"]["accuracy"] <= 1

    loaded = load_model(model_path)
    prediction = predict_latest(loaded, rows)
    assert prediction["research_only"] is True
    assert prediction["trading_authorized"] is False
    assert prediction["signal"] in {"sell", "hold", "buy"}
    assert abs(sum(prediction["probabilities"].values()) - 1.0) < 1e-8


def test_model_save_load_preserves_probabilities(tmp_path):
    rows = synthetic_candles()
    model, _ = train_model(rows, epochs=20, patience=5)
    features = build_samples(rows)[-1].features
    before = model.predict(features)
    path = tmp_path / "roundtrip.json"
    save_model(model, path)
    after = load_model(path).predict(features)
    assert before["signal"] == after["signal"]
    for key in before["probabilities"]:
        assert before["probabilities"][key] == pytest.approx(
            after["probabilities"][key]
        )


def test_model_rejects_bad_training_parameters():
    with pytest.raises(ValueError, match="horizon_bars"):
        build_samples(synthetic_candles(), horizon_bars=0)
