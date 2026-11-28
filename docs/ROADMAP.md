# Roadmap and completion gates

## Implemented foundation

- Typed market/instrument/quote/trade-intent models and separate market profiles.
- OHLCV validation and deterministic MA crossover example.
- Basic deterministic Risk Guardian (not contract-aware; research-only).
- Append-only audit logger.
- Minimal next-bar OHLC backtester with explicit fee/slippage assumptions.
- SQLite paper journal exposed in the authenticated dashboard, with explicit confirmation to create/close records and idempotent client IDs.
- CSV backtest web workbench and automated tests.

## Remaining before credible paper research

1. Licensed data importers, source metadata, timezone/session calendars, and data quality monitoring.
2. Market-specific contract metadata and valuation: contract multiplier, tick value, settlement currency, expiry, roll rules, margin, and cost schedules.
3. Portfolio-level accounting, exposure limits, currency conversion, drawdown controls, and independent risk review.
4. Stop/limit execution simulation, spread-aware fills, gaps, partial fills, liquidity and market-impact assumptions.
5. Walk-forward/holdout, robustness, benchmark, regime and multiple-testing controls.
6. Durable storage and backups; monitoring and failure recovery. Free Render disk is not durable.
7. Security review, dependency scanning, privacy controls, and regulatory/legal review before any real-world use.

## Live trading

Out of scope. No live execution code or broker adapter is present. Any future proposal would require a separate explicit user decision, official regulatory and broker eligibility checks, security review, independent risk controls, operational controls, and a validated paper record. AI must never autonomously authorize or place live orders.


## Shadow observation (implemented; no execution)

- The autonomous scanner records each completed-candle heuristic signal (buy/sell/neutral) in a separate SQLite shadow ledger.
- Duplicate polling of the same symbol/candle is idempotent.
- A pending signal is evaluated against the next newer completed candle observed for that symbol; directional returns are sign-adjusted for buys and sells.
- The dashboard agent snapshot exposes aggregate counts, directional accuracy, and recent records under `shadow`.
- This is a one-observation research diagnostic, not the trained V1/V2/V3 model, not a broker quote feed, and not an order simulator. Neutral signals are counted separately and excluded from directional accuracy.
- Gaps in provider data can make the next observed candle later than one 15-minute interval. Results must be interpreted with timestamps and source limitations.
- No MT5 connection, broker order, or live execution is added. The existing model authorization remains disabled.
