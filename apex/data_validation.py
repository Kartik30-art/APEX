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

def validate_candles(
    candles: Sequence[Candle],
    *,
    max_age: timedelta | None = None,
    now: datetime | None = None,
) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    seen = set()
    previous = None

    if not candles:
        return ValidationReport(False, ("dataset is empty",), ())

    for i, candle in enumerate(candles):
        if candle.timestamp.tzinfo is None or candle.timestamp.utcoffset() is None:
            errors.append(f"row {i}: timestamp must be timezone-aware")
        if candle.timestamp in seen:
            errors.append(f"row {i}: duplicate timestamp")
        seen.add(candle.timestamp)
        if previous is not None and candle.timestamp <= previous:
            errors.append(f"row {i}: timestamps must be strictly increasing")
        previous = candle.timestamp

        values = (candle.open, candle.high, candle.low, candle.close, candle.volume)
        if not all(value.is_finite() for value in values):
            errors.append(f"row {i}: OHLCV values must be finite")
            continue
        if min(candle.open, candle.high, candle.low, candle.close) <= 0:
            errors.append(f"row {i}: OHLC prices must be positive")
        if candle.high < max(candle.open, candle.close, candle.low):
            errors.append(f"row {i}: inconsistent high")
        if candle.low > min(candle.open, candle.close, candle.high):
            errors.append(f"row {i}: inconsistent low")
        if candle.volume < 0:
            errors.append(f"row {i}: volume cannot be negative")

    if max_age is not None and now is not None:
        if now.tzinfo is None or now.utcoffset() is None:
            errors.append("now must be timezone-aware")
        elif candles[-1].timestamp.tzinfo is not None:
            if candles[-1].timestamp < now - max_age:
                warnings.append("latest candle exceeds maximum age")

    return ValidationReport(not errors, tuple(errors), tuple(warnings))
