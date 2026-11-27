from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Sequence

@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")

@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

def validate_candles(candles: Sequence[Candle], *, max_age: timedelta | None = None, now: datetime | None = None) -> ValidationReport:
    errors, warnings, seen = [], [], set()
    if not candles: return ValidationReport(False, ("dataset is empty",), ())
    previous = None
    for i, c in enumerate(candles):
        if c.timestamp.tzinfo is None: errors.append(f"row {i}: timestamp must be timezone-aware")
        if c.timestamp in seen: errors.append(f"row {i}: duplicate timestamp")
        seen.add(c.timestamp)
        if previous is not None and c.timestamp <= previous: errors.append(f"row {i}: timestamps must be strictly increasing")
        previous = c.timestamp
        if min(c.open, c.high, c.low, c.close) <= 0: errors.append(f"row {i}: OHLC prices must be positive")
        if c.high < max(c.open, c.close, c.low): errors.append(f"row {i}: inconsistent high")
        if c.low > min(c.open, c.close, c.high): errors.append(f"row {i}: inconsistent low")
        if c.volume < 0: errors.append(f"row {i}: volume cannot be negative")
    if max_age is not None and now is not None and candles:
        if now.tzinfo is None: errors.append("now must be timezone-aware")
        elif candles[-1].timestamp < now - max_age: warnings.append("latest candle exceeds maximum age")
    return ValidationReport(not errors, tuple(errors), tuple(warnings))
