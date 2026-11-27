# Backtesting assumptions and known gaps

## Current mechanics

- The moving-average strategy reads only candles available at the decision timestamp.
- A signal generated after candle close is filled at the next candle open.
- Entry and exit slippage are applied adversely to the transaction direction.
- Fees are applied on entry and exit as basis points of notional.
- Opposite signals close the current position and open the opposite position at that next open.
- Any remaining position is closed at the final candle close.
- The engine currently holds one position at a time and uses a fixed quantity.
- Results are denominated in quote currency.

## Not modeled

This is a minimal research engine, not a realistic market simulator. It does not model bid/ask spread from historical quotes, stop/limit order execution, intrabar path, gaps beyond the next-open fill assumption, partial fills, order-book depth, liquidity, market impact, swap/rollover, financing, borrow costs, contract multipliers, tick-value conversions, margin, liquidation, exchange fees/taxes, FX conversion, or market calendars.

Do not compare a Forex spot backtest with an Indian exchange derivative backtest as though the P&L units and costs were equivalent. Before adding an instrument, define its contract size, quote/base conventions, tick value, settlement currency, expiry/roll rules, sessions, holidays, permitted contract, and complete cost model from official and licensed sources.

## Validation protocol still required

A credible strategy research process needs pre-registered hypotheses, data provenance, clean train/validation/holdout splits, walk-forward evaluation, realistic costs, sensitivity analysis, parameter stability, regime analysis, benchmark comparison, and explicit controls for survivorship bias and multiple testing. Paper forward-testing must follow before any separate consideration of live use.

A profitable historical curve alone is not evidence of a durable edge.
