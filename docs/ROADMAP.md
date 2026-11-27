# Roadmap and completion gates

## Implemented foundation

- Typed market/instrument/quote/trade-intent models and separate market profiles.
- OHLCV validation and deterministic MA crossover example.
- Basic deterministic Risk Guardian (not contract-aware; research-only).
- Append-only audit logger.
- Minimal next-bar OHLC backtester with explicit fee/slippage assumptions.
- SQLite paper journal with explicit confirmation and idempotent client IDs.
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
