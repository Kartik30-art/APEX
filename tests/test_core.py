from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from apex.models import Instrument, Market, Quote, TradeIntent
from apex.data_validation import Candle, validate_candles
from apex.risk import RiskGuardian

def test_invalid_instrument():
    with pytest.raises(ValueError): Instrument("EURUSD", Market.GLOBAL_FOREX, "EUR", "USD", Decimal("0"), Decimal("1"))

def test_candle_validation_and_duplicate_detection():
    t = datetime.now(timezone.utc)
    c = Candle(t, Decimal("1"), Decimal("1.2"), Decimal(".9"), Decimal("1.1"))
    assert validate_candles([c]).valid
    assert not validate_candles([c, c]).valid

def test_stale_candle_warning():
    now = datetime.now(timezone.utc)
    c = Candle(now-timedelta(hours=1), Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"))
    assert validate_candles([c], max_age=timedelta(minutes=1), now=now).warnings

def test_risk_guardian_rejects_stale_quote():
    now = datetime.now(timezone.utc)
    intent = TradeIntent("EURUSD", "buy", Decimal("10"), Decimal("1.1"), Decimal("1.09"), now, "test")
    quote = Quote("EURUSD", Decimal("1.0999"), Decimal("1.1001"), now-timedelta(minutes=1), "test")
    result = RiskGuardian().evaluate(intent, quote, equity=Decimal("100000"), daily_loss=Decimal("0"), open_positions=0, now=now)
    assert not result.approved
    assert "quote is stale" in result.reasons

def test_market_execution_disabled():
    from apex.markets import GLOBAL_FOREX, INDIA_CURRENCY_DERIVATIVES
    assert not GLOBAL_FOREX.execution_allowed
    assert not INDIA_CURRENCY_DERIVATIVES.execution_allowed

def test_non_finite_candles_are_rejected():
    now = datetime.now(timezone.utc)
    bad = Candle(now, Decimal("1"), Decimal("Infinity"), Decimal("0.9"), Decimal("NaN"))
    report = validate_candles([bad])
    assert not report.valid
    assert any("finite" in error for error in report.errors)


def test_risk_guardian_rejects_stale_intent_even_with_fresh_quote():
    now = datetime.now(timezone.utc)
    intent = TradeIntent("EURUSD", "buy", Decimal("1"), Decimal("1.1"),
                         Decimal("1.09"), now-timedelta(minutes=2), "test")
    quote = Quote("EURUSD", Decimal("1.0999"), Decimal("1.1001"), now, "test")
    result = RiskGuardian().evaluate(intent, quote, equity=Decimal("100000"),
                                     daily_loss=Decimal("0"), open_positions=0, now=now)
    assert not result.approved
    assert "trade intent is stale" in result.reasons


def test_risk_guardian_rejects_future_intent():
    now = datetime.now(timezone.utc)
    intent = TradeIntent("EURUSD", "buy", Decimal("1"), Decimal("1.1"),
                         Decimal("1.09"), now+timedelta(minutes=1), "test")
    quote = Quote("EURUSD", Decimal("1.0999"), Decimal("1.1001"), now, "test")
    result = RiskGuardian().evaluate(intent, quote, equity=Decimal("100000"),
                                     daily_loss=Decimal("0"), open_positions=0, now=now)
    assert not result.approved
    assert "intent timestamp is in the future" in result.reasons


def test_risk_guardian_rejects_negative_daily_loss_and_positions():
    now = datetime.now(timezone.utc)
    intent = TradeIntent("EURUSD", "buy", Decimal("1"), Decimal("1.1"),
                         Decimal("1.09"), now, "test")
    quote = Quote("EURUSD", Decimal("1.0999"), Decimal("1.1001"), now, "test")
    result = RiskGuardian().evaluate(intent, quote, equity=Decimal("100000"),
                                     daily_loss=Decimal("-1"), open_positions=-1, now=now)
    assert not result.approved
    assert "daily_loss cannot be negative" in result.reasons
    assert "open_positions cannot be negative" in result.reasons


def test_risk_config_rejects_invalid_limits():
    from apex.risk import RiskConfig
    with pytest.raises(ValueError):
        RiskConfig(max_daily_loss_fraction=Decimal("1.5"))
    with pytest.raises(ValueError):
        RiskConfig(max_quote_age_seconds=-1)
