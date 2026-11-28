from datetime import datetime, timedelta, timezone
from decimal import Decimal
from apex.contract_backtest import run_contract_backtest
from apex.data_validation import Candle
from apex.instruments import NSE_INR_FUTURES, FeeSchedule
from apex.strategies import StrategySignal

class OneLong:
    strategy_id="one_long"
    version="1"
    def generate_signal(self,candles):
        return StrategySignal("buy","test") if len(candles)==1 else None

def test_contract_backtest_applies_contract_multiplier_and_tick_slippage():
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    bars=[]
    for i,p in enumerate((83,83.01,83.02)):
        x=Decimal(str(p))
        bars.append(Candle(start+timedelta(hours=i),x,x+Decimal("0.01"),x-Decimal("0.01"),x,Decimal("1")))
    result=run_contract_backtest(bars,OneLong(),NSE_INR_FUTURES["USDINR"],contracts=2,slippage_ticks_per_side=Decimal("1"))
    assert result.symbol=="USDINR"
    assert result.trades[0].valuation.gross_pnl_quote==Decimal("10")
    assert result.net_pnl_quote==Decimal("10")
    assert result.assumptions["tick_value_per_contract"]=="2.5"

def test_contract_backtest_includes_configured_fees():
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    bars=[]
    for i,p in enumerate((83,83.01,83.02)):
        x=Decimal(str(p))
        bars.append(Candle(start+timedelta(hours=i),x,x+Decimal("0.01"),x-Decimal("0.01"),x,Decimal("1")))
    result=run_contract_backtest(bars,OneLong(),NSE_INR_FUTURES["USDINR"],fees=FeeSchedule(brokerage_per_order=Decimal("10")))
    assert result.estimated_fees_quote==Decimal("20")
    assert result.net_pnl_quote<result.gross_pnl_quote
def test_contract_backtest_drawdown_marks_open_trade_before_recovery():
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    prices=((83,83,83),(83,82,82),(82,82,84))
    bars=[]
    for i,(op,lo,cl) in enumerate(prices):
        o,l,c=Decimal(str(op)),Decimal(str(lo)),Decimal(str(cl))
        bars.append(Candle(start+timedelta(hours=i),o,max(o,c),l,c,Decimal("1")))
    result=run_contract_backtest(bars,OneLong(),NSE_INR_FUTURES["USDINR"])
    assert result.net_pnl_quote > 0
    assert result.max_drawdown_fraction > 0
    assert "intrabar extremes are not modeled" in result.assumptions["drawdown"]
