import math
from datetime import datetime, timedelta, timezone

import pytest

from apex.forex_backtest import TradingCosts, walk_forward_ml_backtest


def market_candles(count=1200):
    rows = []
    price = 1.10
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    for index in range(count):
        phase = (index // 60) % 4
        drift = [0.00008, -0.00007, 0.00004, -0.00003][phase]
        wave = math.sin(index / 7.0) * 0.00012
        previous = price
        price = max(0.5, price * (1.0 + drift + wave))
        rows.append({
            "timestamp": (start + timedelta(hours=index)).isoformat(),
            "open": previous,
            "high": max(previous, price) + 0.00012,
            "low": min(previous, price) - 0.00012,
            "close": price,
            "volume": 0,
        })
    return rows


def test_costs_reject_invalid_values():
    with pytest.raises(ValueError, match="finite and non-negative"):
        TradingCosts(spread_bps_per_side=-1)
    with pytest.raises(ValueError, match="unreasonably large"):
        TradingCosts(spread_bps_per_side=1000)


def test_walk_forward_is_chronological_and_research_only():
    rows = market_candles()
    report = walk_forward_ml_backtest(
        rows,
        initial_train_bars=600,
        test_bars=150,
        max_folds=2,
        epochs=20,
        patience=5,
    )
    assert report["status"] == "RESEARCH_ONLY"
    assert report["trading_authorized"] is False
    assert len(report["folds"]) == 2
    first, second = report["folds"]
    assert first["train_end"] < first["test_start"]
    assert first["test_end"] < second["test_start"]
    assert first["strategies"]["ml_model"]["assumptions"]["execution"].startswith(
        "completed-candle signal"
    )
    assert "ml_model_double_cost_stress" in report["aggregate_strategies"]


def test_zero_signal_baseline_has_no_trades():
    from apex.forex_backtest import _trade_simulation

    rows = market_candles()
    result = _trade_simulation(
        rows, {}, start_index=600, end_index=750,
        costs=TradingCosts(),
    )
    assert result["trade_count"] == 0
    assert result["net_return_fraction"] == 0
