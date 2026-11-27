from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Sequence
from .data_validation import Candle

@dataclass(frozen=True)
class StrategySignal:
    side: str
    reason: str

class Strategy(Protocol):
    strategy_id: str
    version: str
    def generate_signal(self, candles: Sequence[Candle]) -> StrategySignal | None: ...

@dataclass(frozen=True)
class MovingAverageCross:
    strategy_id: str = "ma_cross"
    version: str = "0.1.0"
    fast_window: int = 5
    slow_window: int = 20
    def __post_init__(self):
        if self.fast_window < 1 or self.slow_window <= self.fast_window: raise ValueError("require 1 <= fast_window < slow_window")
    def generate_signal(self, candles: Sequence[Candle]) -> StrategySignal | None:
        if len(candles) < self.slow_window + 1: return None
        closes = [c.close for c in candles]
        pf = sum(closes[-self.fast_window-1:-1], Decimal("0")) / self.fast_window
        ps = sum(closes[-self.slow_window-1:-1], Decimal("0")) / self.slow_window
        cf = sum(closes[-self.fast_window:], Decimal("0")) / self.fast_window
        cs = sum(closes[-self.slow_window:], Decimal("0")) / self.slow_window
        if pf <= ps and cf > cs: return StrategySignal("buy", "fast average crossed above slow average")
        if pf >= ps and cf < cs: return StrategySignal("sell", "fast average crossed below slow average")
        return None
