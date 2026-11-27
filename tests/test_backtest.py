from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from apex.backtest import BacktestConfig, run_backtest
from apex.data_validation import Candle
from apex.strategies import StrategySignal


class SequenceStrategy:
    strategy_id = "test_sequence"
    version = "1"

    def __init__(self, sides):
        self.sides = sides

    def generate_signal(self, candles):
        side = self.sides.get(len(candles))
        return StrategySignal(side, "test") if side else None


def bars(closes):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = []
    previous = Decimal(str(closes[0]))
    for index, value in enumerate(closes):
        close = Decimal(str(value))
        open_price = previous
        result.append(Candle(
            start + timedelta(hours=index),
            open_price,
            max(open_price, close) + Decimal("0.1"),
            min(open_price, close) - Decimal("0.1"),
            close,
            Decimal("1"),
        ))
        previous = close
    return result


def test_backtest_executes_on_next_bar_and_closes_at_end():
    candles = bars([10, 11, 12])
    result = run_backtest(candles, SequenceStrategy({1: "buy"}))
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_time == candles[1].timestamp.isoformat()
    assert trade.exit_time == candles[2].timestamp.isoformat()
    assert trade.net_pnl == Decimal("1")


def test_backtest_applies_round_trip_fee_and_slippage():
    result = run_backtest(
        bars([10, 11, 12]),
        SequenceStrategy({1: "buy"}),
        BacktestConfig(
            quantity=Decimal("1"),
            fee_bps_per_side=Decimal("10"),
            slippage_bps_per_side=Decimal("10"),
        ),
    )
    assert result.trades[0].fees > 0
    assert result.trades[0].net_pnl < Decimal("1")


def test_backtest_rejects_non_finite_configuration():
    with pytest.raises(ValueError, match="finite"):
        BacktestConfig(quantity=Decimal("NaN"))


def test_backtest_rejects_unknown_strategy_side():
    with pytest.raises(ValueError, match="side"):
        run_backtest(bars([10, 11, 12]), SequenceStrategy({1: "hold"}))


def test_profit_factor_is_json_safe_when_no_losses():
    result = run_backtest(bars([10, 11, 12]), SequenceStrategy({1: "buy"}))
    assert result.profit_factor is None


def test_drawdown_is_marked_on_bars_without_new_signals():
    result = run_backtest(
        bars([10, 12, 8, 9]),
        SequenceStrategy({1: "buy"}),
    )
    assert result.max_drawdown_fraction > 0
