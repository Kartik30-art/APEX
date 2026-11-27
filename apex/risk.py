from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone
from .models import Quote, TradeIntent

@dataclass(frozen=True)
class RiskConfig:
    max_risk_fraction_per_trade: Decimal = Decimal("0.005")
    max_daily_loss_fraction: Decimal = Decimal("0.02")
    max_open_positions: int = 3
    max_spread_bps: Decimal = Decimal("30")
    max_quote_age_seconds: int = 15

@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reasons: tuple[str, ...]

class RiskGuardian:
    # Deterministic checks only; this module cannot route orders.
    def __init__(self, config: RiskConfig = RiskConfig()): self.config = config
    def evaluate(self, intent: TradeIntent, quote: Quote, *, equity: Decimal, daily_loss: Decimal, open_positions: int, now: datetime | None = None) -> RiskDecision:
        reasons = []
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or quote.timestamp.tzinfo is None or intent.timestamp.tzinfo is None: reasons.append("timestamps must be timezone-aware")
        else:
            age = (now - quote.timestamp).total_seconds()
            if age < -1: reasons.append("quote timestamp is in the future")
            elif age > self.config.max_quote_age_seconds: reasons.append("quote is stale")
        mid = (quote.bid + quote.ask) / Decimal("2")
        spread_bps = ((quote.ask - quote.bid) / mid) * Decimal("10000")
        if spread_bps > self.config.max_spread_bps: reasons.append("spread exceeds configured limit")
        if equity <= 0: reasons.append("equity must be positive")
        else:
            risk_amount = abs(intent.entry_price - intent.stop_price) * intent.quantity
            if risk_amount > equity * self.config.max_risk_fraction_per_trade: reasons.append("trade risk exceeds per-trade limit")
            if daily_loss >= equity * self.config.max_daily_loss_fraction: reasons.append("daily loss limit reached")
        if open_positions >= self.config.max_open_positions: reasons.append("maximum open positions reached")
        if intent.instrument != quote.instrument: reasons.append("intent and quote instruments do not match")
        if intent.side == "buy" and intent.stop_price >= intent.entry_price: reasons.append("buy stop must be below entry")
        if intent.side == "sell" and intent.stop_price <= intent.entry_price: reasons.append("sell stop must be above entry")
        return RiskDecision(not reasons, tuple(reasons))
