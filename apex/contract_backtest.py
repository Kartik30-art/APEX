"""Contract-aware futures backtest wrapper.

Runs the signal engine on OHLC bars, then revalues every completed trade using
contract units, quotation units, tick slippage and explicit fee inputs.
No margin/financing/liquidation model is inferred.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from .backtest import BacktestConfig, run_backtest
from .data_validation import Candle
from .instruments import ContractSpec, FeeSchedule, Valuation, calculate_futures_valuation
from .strategies import Strategy


@dataclass(frozen=True)
class ContractTrade:
    side: str
    entry_time: str
    exit_time: str
    entry_price: Decimal
    exit_price: Decimal
    valuation: Valuation
    exit_reason: str


@dataclass(frozen=True)
class ContractBacktestResult:
    symbol: str
    contracts: int
    trades: tuple[ContractTrade, ...]
    gross_pnl_quote: Decimal
    estimated_fees_quote: Decimal
    net_pnl_quote: Decimal
    win_rate: Decimal
    max_drawdown_fraction: Decimal
    assumptions: dict


def run_contract_backtest(
    candles: Sequence[Candle],
    strategy: Strategy,
    spec: ContractSpec,
    *,
    contracts: int = 1,
    fees: FeeSchedule = FeeSchedule(),
    slippage_ticks_per_side: Decimal = Decimal("0"),
) -> ContractBacktestResult:
    if contracts < 1:
        raise ValueError("contracts must be a positive integer")
    if not slippage_ticks_per_side.is_finite() or slippage_ticks_per_side < 0:
        raise ValueError("slippage_ticks_per_side must be finite and non-negative")
    raw = run_backtest(candles, strategy, BacktestConfig())
    trades = []
    running = Decimal("0")
    peak = Decimal("0")
    drawdown = Decimal("0")
    gross_total = Decimal("0")
    fees_total = Decimal("0")
    wins = 0
    slip = spec.tick_size * slippage_ticks_per_side
    for trade in raw.trades:
        if trade.side == "long":
            side = "buy"
            entry = trade.entry_price + slip
            exit_price = max(spec.tick_size, trade.exit_price - slip)
        else:
            side = "sell"
            entry = max(spec.tick_size, trade.entry_price - slip)
            exit_price = trade.exit_price + slip
        value = calculate_futures_valuation(
            spec, contracts=contracts, entry_price=entry,
            exit_price=exit_price, side=side, fees=fees,
        )
        trades.append(ContractTrade(trade.side, trade.entry_time, trade.exit_time,
                                    entry, exit_price, value, trade.exit_reason))
        gross_total += value.gross_pnl_quote
        fees_total += value.estimated_fees_quote
        running += value.net_pnl_quote
        peak = max(peak, running)
        if peak > 0:
            drawdown = max(drawdown, (peak-running)/peak)
        if value.net_pnl_quote > 0:
            wins += 1
    return ContractBacktestResult(
        symbol=spec.symbol, contracts=contracts, trades=tuple(trades),
        gross_pnl_quote=gross_total, estimated_fees_quote=fees_total,
        net_pnl_quote=gross_total-fees_total,
        win_rate=Decimal(wins)/Decimal(len(trades)) if trades else Decimal("0"),
        max_drawdown_fraction=drawdown,
        assumptions={
            "currency":spec.quote_currency,
            "contract_units":str(spec.units_per_contract),
            "quote_units":str(spec.quote_units),
            "tick_size":str(spec.tick_size),
            "tick_value_per_contract":str(spec.tick_value),
            "slippage_ticks_per_side":str(slippage_ticks_per_side),
            "fees":"user-configured FeeSchedule; verify charge bases and current rates",
            "excluded":"margin, financing, rollover, taxes not entered in FeeSchedule, partial fills, market impact",
        },
    )
