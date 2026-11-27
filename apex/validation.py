"""Sequential walk-forward evaluation with strict pre-test signal gating.

Each fold uses an expanding history for indicator warm-up, but suppresses all
signals until the first test bar. This prevents warm-up trades leaking into
out-of-sample fold statistics. It is a basic research aid, not a substitute
for nested validation, multiple-testing controls, or realistic market costs.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from .backtest import BacktestConfig, BacktestResult, run_backtest
from .data_validation import Candle
from .strategies import Strategy, StrategySignal


@dataclass(frozen=True)
class WalkForwardFold:
    number: int
    train_bars: int
    test_start: str
    test_end: str
    result: BacktestResult


@dataclass(frozen=True)
class WalkForwardResult:
    folds: tuple[WalkForwardFold, ...]
    total_test_bars: int
    total_trades: int
    aggregate_net_pnl: Decimal
    profitable_folds: int


class _TestOnlyStrategy:
    def __init__(self, wrapped: Strategy, first_test_signal_index: int):
        self.wrapped = wrapped
        self.first_test_signal_index = first_test_signal_index
        self.strategy_id = wrapped.strategy_id + "_walk_forward"
        self.version = wrapped.version

    def generate_signal(self, candles: Sequence[Candle]) -> StrategySignal | None:
        if len(candles) < self.first_test_signal_index:
            return None
        return self.wrapped.generate_signal(candles)


def walk_forward(
    candles: Sequence[Candle],
    strategy_factory,
    *,
    initial_train_bars: int,
    test_bars: int,
    config: BacktestConfig = BacktestConfig(),
    max_folds: int = 20,
) -> WalkForwardResult:
    """Run expanding-window folds; strategy_factory returns a fresh Strategy per fold."""
    if initial_train_bars < 3 or test_bars < 2:
        raise ValueError("initial_train_bars must be >= 3 and test_bars >= 2")
    if max_folds < 1:
        raise ValueError("max_folds must be positive")
    if len(candles) <= initial_train_bars:
        raise ValueError("not enough candles beyond the initial training window")

    folds = []
    train_end = initial_train_bars
    while train_end < len(candles) and len(folds) < max_folds:
        test_end = min(train_end + test_bars, len(candles))
        if test_end - train_end < 2:
            break
        strategy = strategy_factory()
        gated = _TestOnlyStrategy(strategy, train_end)
        # Include all prior history for indicators; no signal can execute before
        # the test boundary. The backtest executes the boundary signal at its open.
        result = run_backtest(candles[:test_end], gated, config)
        folds.append(WalkForwardFold(
            number=len(folds) + 1,
            train_bars=train_end,
            test_start=candles[train_end].timestamp.isoformat(),
            test_end=candles[test_end - 1].timestamp.isoformat(),
            result=result,
        ))
        train_end = test_end

    if not folds:
        raise ValueError("no complete test folds could be formed")
    return WalkForwardResult(
        folds=tuple(folds),
        total_test_bars=sum(f.result.bars - f.train_bars for f in folds),
        total_trades=sum(len(f.result.trades) for f in folds),
        aggregate_net_pnl=sum((f.result.net_pnl for f in folds), Decimal("0")),
        profitable_folds=sum(1 for f in folds if f.result.net_pnl > 0),
    )
