from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from apex.data_validation import Candle
from apex.backtest import BacktestConfig, run_backtest
from apex.paper import PaperLedger, PaperTradingDisabled
from apex.models import TradeIntent

class ScriptedStrategy:
    strategy_id = "test_script"
    def generate_signal(self, candles):
        if len(candles) == 1:
            return type("Signal", (), {"side": "buy"})()
        if len(candles) == 2:
            return type("Signal", (), {"side": "sell"})()
        return None

def candles():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(t, Decimal("10"), Decimal("10"), Decimal("10"), Decimal("10")),
        Candle(t+timedelta(minutes=1), Decimal("10"), Decimal("12"), Decimal("10"), Decimal("11")),
        Candle(t+timedelta(minutes=2), Decimal("12"), Decimal("12"), Decimal("11"), Decimal("11")),
    ]

def test_backtest_uses_next_bar_and_closes_positions():
    result = run_backtest(candles(), ScriptedStrategy(), BacktestConfig(quantity=Decimal("1")))
    assert len(result.trades) == 2
    assert result.trades[0].entry_price == Decimal("10")
    assert result.trades[0].exit_price == Decimal("12")
    assert result.trades[0].exit_reason == "opposite_signal"
    assert result.trades[1].side == "short"
    assert result.trades[1].exit_reason == "end_of_data"
    assert result.net_pnl == Decimal("3")

def test_backtest_applies_fees_and_slippage():
    result = run_backtest(candles(), ScriptedStrategy(), BacktestConfig(
        fee_bps_per_side=Decimal("10"), slippage_bps_per_side=Decimal("5")))
    assert result.trades[0].fees > 0
    assert result.trades[0].entry_price > Decimal("10")

def test_paper_ledger_requires_explicit_confirmation(tmp_path):
    ledger = PaperLedger(tmp_path / "paper.sqlite")
    intent = TradeIntent("EURUSD", "buy", Decimal("1"), Decimal("1.1"), Decimal("1.09"),
                         datetime.now(timezone.utc), "manual")
    with pytest.raises(PaperTradingDisabled):
        ledger.record_approved_intent(intent, client_id="abc", user_confirmed=True, paper_mode_enabled=False)
    with pytest.raises(PermissionError):
        ledger.record_approved_intent(intent, client_id="abc", user_confirmed=False, paper_mode_enabled=True)
    trade_id = ledger.record_approved_intent(intent, client_id="abc", user_confirmed=True, paper_mode_enabled=True)
    assert ledger.list_trades()[0]["id"] == trade_id
    ledger.close_trade(trade_id, exit_price=Decimal("1.11"), user_confirmed=True)
    assert ledger.summary()["realized_gross_pnl"] == "0.01"
