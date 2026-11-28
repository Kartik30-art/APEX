"""Deterministic, fail-closed pre-trade risk checks. No order routing lives here."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

from .models import Quote, TradeIntent


@dataclass(frozen=True)
class RiskConfig:
    max_risk_fraction_per_trade: Decimal = Decimal("0.005")
    max_daily_loss_fraction: Decimal = Decimal("0.02")
    max_open_positions: int = 3
    max_spread_bps: Decimal = Decimal("30")
    max_quote_age_seconds: int = 15
    max_intent_age_seconds: int = 30

    def __post_init__(self):
        for name in ("max_risk_fraction_per_trade", "max_daily_loss_fraction", "max_spread_bps"):
            value = getattr(self, name)
            if not value.is_finite() or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.max_risk_fraction_per_trade > 1 or self.max_daily_loss_fraction > 1:
            raise ValueError("risk and daily-loss fractions cannot exceed 1")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be positive")
        if self.max_quote_age_seconds < 0 or self.max_intent_age_seconds < 0:
            raise ValueError("timestamp age limits cannot be negative")


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reasons: tuple[str, ...]


class RiskGuardian:
    """Independent deterministic checks; approval is not a broker instruction."""

    def __init__(self, config: RiskConfig = RiskConfig()):
        self.config = config

    def evaluate(
        self, intent: TradeIntent, quote: Quote, *, equity: Decimal,
        daily_loss: Decimal, open_positions: int, now: datetime | None = None,
    ) -> RiskDecision:
        reasons = []
        now = now or datetime.now(timezone.utc)

        # Reject invalid numeric inputs before arithmetic. Never let NaN/Infinity
        # or malformed accounting state accidentally pass a comparison.
        numeric = {
            "equity": equity, "daily_loss": daily_loss,
            "bid": quote.bid, "ask": quote.ask,
            "quantity": intent.quantity, "entry_price": intent.entry_price,
            "stop_price": intent.stop_price,
        }
        for name, value in numeric.items():
            if not isinstance(value, Decimal) or not value.is_finite():
                reasons.append(f"{name} must be a finite decimal")
        if reasons:
            return RiskDecision(False, tuple(reasons))

        if equity <= 0:
            reasons.append("equity must be positive")
        if daily_loss < 0:
            reasons.append("daily_loss cannot be negative")
        if open_positions < 0:
            reasons.append("open_positions cannot be negative")

        if now.tzinfo is None or now.utcoffset() is None:
            reasons.append("current timestamp must be timezone-aware")
        if quote.timestamp.tzinfo is None or quote.timestamp.utcoffset() is None:
            reasons.append("quote timestamp must be timezone-aware")
        if intent.timestamp.tzinfo is None or intent.timestamp.utcoffset() is None:
            reasons.append("intent timestamp must be timezone-aware")

        if (now.tzinfo is not None and now.utcoffset() is not None
                and quote.timestamp.tzinfo is not None and quote.timestamp.utcoffset() is not None):
            age = (now - quote.timestamp).total_seconds()
            if age < -1:
                reasons.append("quote timestamp is in the future")
            elif age > self.config.max_quote_age_seconds:
                reasons.append("quote is stale")

        if (now.tzinfo is not None and now.utcoffset() is not None
                and intent.timestamp.tzinfo is not None and intent.timestamp.utcoffset() is not None):
            age = (now - intent.timestamp).total_seconds()
            if age < -1:
                reasons.append("intent timestamp is in the future")
            elif age > self.config.max_intent_age_seconds:
                reasons.append("trade intent is stale")

        if quote.bid <= 0 or quote.ask <= 0 or quote.ask < quote.bid:
            reasons.append("quote bid/ask is invalid")
        else:
            mid = (quote.bid + quote.ask) / Decimal("2")
            spread_bps = ((quote.ask - quote.bid) / mid) * Decimal("10000")
            if spread_bps > self.config.max_spread_bps:
                reasons.append("spread exceeds configured limit")

        if intent.quantity <= 0:
            reasons.append("quantity must be positive")
        if intent.entry_price <= 0 or intent.stop_price <= 0:
            reasons.append("entry and stop prices must be positive")
        if intent.side == "buy" and intent.stop_price >= intent.entry_price:
            reasons.append("buy stop must be below entry")
        if intent.side == "sell" and intent.stop_price <= intent.entry_price:
            reasons.append("sell stop must be above entry")
        if intent.instrument != quote.instrument:
            reasons.append("intent and quote instruments do not match")

        if equity > 0:
            risk_amount = abs(intent.entry_price - intent.stop_price) * intent.quantity
            if risk_amount > equity * self.config.max_risk_fraction_per_trade:
                reasons.append("trade risk exceeds per-trade limit")
            if daily_loss >= equity * self.config.max_daily_loss_fraction:
                reasons.append("daily loss limit reached")

        if open_positions >= self.config.max_open_positions:
            reasons.append("maximum open positions reached")

        return RiskDecision(not reasons, tuple(dict.fromkeys(reasons)))
