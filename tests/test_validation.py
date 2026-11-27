from datetime import datetime, timedelta, timezone
from decimal import Decimal

from apex.data_validation import Candle
from apex.strategies import StrategySignal
from apex.validation import walk_forward


def make_bars(count):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = []
    for i in range(count):
        close = Decimal(100 + i)
        op = close - Decimal("1")
        result.append(Candle(start + timedelta(hours=i), op, close + Decimal("1"),
                             op - Decimal("1"), close, Decimal("10")))
    return result


class BuyAtTrainingBoundary:
    strategy_id = "boundary_test"
    version = "1"

    def generate_signal(self, candles):
        if len(candles) == 5:
            return StrategySignal("buy", "boundary entry")
        return None


def test_walk_forward_uses_training_close_for_first_test_open():
    candles = make_bars(8)
    result = walk_forward(
        candles, BuyAtTrainingBoundary,
        initial_train_bars=5, test_bars=3,
    )
    assert len(result.folds) == 1
    fold = result.folds[0]
    assert fold.test_start == candles[5].timestamp.isoformat()
    assert fold.result.trades[0].entry_time == candles[5].timestamp.isoformat()
    assert fold.result.trades[0].exit_time == candles[7].timestamp.isoformat()
    assert result.total_test_bars == 3


def test_walk_forward_expands_training_window_and_resets_each_fold():
    class NoSignal:
        strategy_id = "none"
        version = "1"

        def generate_signal(self, candles):
            return None

    result = walk_forward(make_bars(12), NoSignal,
                          initial_train_bars=5, test_bars=3)
    assert [fold.train_bars for fold in result.folds] == [5, 8, 11]
    assert result.total_test_bars == 7
    assert result.total_trades == 0


def test_walk_forward_rejects_invalid_windows():
    import pytest
    with pytest.raises(ValueError):
        walk_forward(make_bars(8), BuyAtTrainingBoundary,
                     initial_train_bars=2, test_bars=3)
