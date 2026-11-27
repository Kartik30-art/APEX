"""Event-driven, long/short OHLC backtester with next-bar execution.

Results are denominated in the instrument's quote currency. This module deliberately
does not infer contract multipliers, financing, swaps, margin, or exchange fees.
Supply explicit per-side fee/slippage assumptions; never treat output as live P&L.
"""
from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Sequence
from .data_validation import Candle, validate_candles
from .strategies import Strategy

@dataclass(frozen=True)
class BacktestConfig:
    quantity: Decimal = Decimal("1")
    fee_bps_per_side: Decimal = Decimal("0")
    slippage_bps_per_side: Decimal = Decimal("0")
    initial_equity: Decimal = Decimal("10000")

    def __post_init__(self):
        if self.quantity <= 0 or self.initial_equity <= 0:
            raise ValueError("quantity and initial_equity must be positive")
        if self.fee_bps_per_side < 0 or self.slippage_bps_per_side < 0:
            raise ValueError("fees and slippage cannot be negative")
        if self.slippage_bps_per_side >= Decimal("10000"):
            raise ValueError("slippage must be below 10000 bps")

@dataclass(frozen=True)
class BacktestTrade:
    side: str
    quantity: Decimal
    entry_time: str
    exit_time: str
    entry_price: Decimal
    exit_price: Decimal
    gross_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal
    exit_reason: str

@dataclass(frozen=True)
class BacktestResult:
    strategy_id: str
    bars: int
    trades: tuple[BacktestTrade, ...]
    initial_equity: Decimal
    final_equity: Decimal
    net_pnl: Decimal
    return_fraction: Decimal
    max_drawdown_fraction: Decimal
    win_rate: Decimal
    profit_factor: Decimal | None
    assumptions: dict

def _execution_price(raw: Decimal, side: str, slippage: Decimal) -> Decimal:
    # side is the transaction direction, not the held position direction.
    factor = Decimal("1") + slippage / Decimal("10000") if side == "buy" else Decimal("1") - slippage / Decimal("10000")
    return raw * factor

def run_backtest(candles: Sequence[Candle], strategy: Strategy, config: BacktestConfig = BacktestConfig()) -> BacktestResult:
    report = validate_candles(candles)
    if not report.valid:
        raise ValueError("invalid candles: " + "; ".join(report.errors))
    if len(candles) < 2:
        raise ValueError("at least two candles are required")
    trades = []
    position = None
    equity = config.initial_equity
    peak = equity
    max_dd = Decimal("0")
    slippage = config.slippage_bps_per_side
    fee_rate = config.fee_bps_per_side / Decimal("10000")

    def mark_to_market(bar: Candle):
        nonlocal peak, max_dd
        unrealized = Decimal("0")
        if position is not None:
            unrealized = (bar.close - position["entry_price"]) * Decimal(position["direction"]) * config.quantity
        marked_equity = equity + unrealized
        peak = max(peak, marked_equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - marked_equity) / peak)

    def close_position(bar: Candle, raw_price: Decimal, reason: str):
        nonlocal position, equity, peak, max_dd
        held = position["direction"]
        transaction_side = "sell" if held == 1 else "buy"
        exit_price = _execution_price(raw_price, transaction_side, slippage)
        gross = (exit_price - position["entry_price"]) * Decimal(held) * config.quantity
        fees = (position["entry_price"] + exit_price) * config.quantity * fee_rate
        net = gross - fees
        equity += net
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
        trades.append(BacktestTrade(
            side="long" if held == 1 else "short", quantity=config.quantity,
            entry_time=position["entry_time"], exit_time=bar.timestamp.isoformat(),
            entry_price=position["entry_price"], exit_price=exit_price,
            gross_pnl=gross, fees=fees, net_pnl=net, exit_reason=reason))
        position = None

    # Signal is computed only from bars available at index i; fills occur at i+1 open.
    for i in range(len(candles) - 1):
        signal = strategy.generate_signal(candles[:i + 1])
        if signal is None:
            continue
        next_bar = candles[i + 1]
        desired = 1 if signal.side == "buy" else -1
        if position and position["direction"] != desired:
            close_position(next_bar, next_bar.open, "opposite_signal")
        if position is None:
            entry_transaction = "buy" if desired == 1 else "sell"
            entry = _execution_price(next_bar.open, entry_transaction, slippage)
            position = {"direction": desired, "entry_price": entry, "entry_time": next_bar.timestamp.isoformat()}
        mark_to_market(next_bar)

    if position is not None:
        last = candles[-1]
        close_position(last, last.close, "end_of_data")

    wins = sum(1 for t in trades if t.net_pnl > 0)
    gross_profit = sum((t.net_pnl for t in trades if t.net_pnl > 0), Decimal("0"))
    gross_loss = -sum((t.net_pnl for t in trades if t.net_pnl < 0), Decimal("0"))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (None if gross_profit == 0 else Decimal("Infinity"))
    net = equity - config.initial_equity
    return BacktestResult(
        strategy_id=strategy.strategy_id, bars=len(candles), trades=tuple(trades),
        initial_equity=config.initial_equity, final_equity=equity, net_pnl=net,
        return_fraction=net / config.initial_equity, max_drawdown_fraction=max_dd,
        win_rate=(Decimal(wins) / Decimal(len(trades))) if trades else Decimal("0"),
        profit_factor=profit_factor,
        assumptions={"quantity": str(config.quantity), "fee_bps_per_side": str(config.fee_bps_per_side),
                     "slippage_bps_per_side": str(config.slippage_bps_per_side),
                     "execution": "next bar open; forced close at final close",
                     "currency": "instrument quote currency; no contract multiplier/financing/margin model"})
