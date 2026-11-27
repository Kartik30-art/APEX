# APEX — Personal AI-Assisted Market Research

APEX is a personal-use, research-first workbench for studying global Forex and Indian exchange-traded currency derivatives. It keeps the two market profiles separate. It is not a broker, signal service, investment adviser, or production trading system.

## What is implemented

- Separate global Forex and India currency-derivative profiles; execution disabled in both.
- Typed instruments, quotes, trade intents, and OHLCV candle validation.
- Deterministic moving-average crossover example.
- Event-driven historical OHLC backtester with next-bar-open fills, configurable per-side fee/slippage assumptions, opposite-signal exits, final-bar liquidation, and basic performance statistics.
- SQLite paper-trade journal requiring both paper mode and explicit user confirmation; unique client IDs prevent duplicate journal entries.
- Append-only JSONL audit logger.
- Research-only web dashboard with CSV upload for historical backtests.
- Automated unit tests and GitHub Actions test workflow.

## Web workbench

The Render service is intended for personal research access. Upload a CSV containing:
`timestamp,open,high,low,close` and optional `volume`.

Use timezone-aware ISO timestamps, e.g. `2026-01-01T09:15:00+05:30`. Rows must be strictly chronological and OHLC values valid. The workbench caps uploads at 100,000 candles and requests at 15 MB.

## Run locally

```bash
python -m pip install -e ".[dev]"
pytest
python -m apex demo
python app.py
```

## Critical limitations

- Backtest output is denominated in the instrument quote currency. It does not model exchange contract multipliers, tick-value conversions, margin, financing, swaps, rollover, taxes, broker/exchange fee schedules, market impact, partial fills, liquidity, or market-specific sessions/calendars.
- The default MA strategy is a coding example, not a validated trading edge. There is no parameter search, walk-forward/holdout framework, robustness analysis, or protection against multiple-testing/data-snooping bias yet.
- Historical OHLC bars cannot reproduce intrabar order sequencing. Stop-loss execution, gaps, spread dynamics and realistic fills are not modeled by the current backtester.
- The SQLite paper ledger is a local module and is not exposed through the public dashboard. Render's free filesystem is ephemeral; data stored there can disappear on restart/redeploy/spin-down. Do not treat cloud storage as durable.
- No licensed market-data provider, live feed, broker, credentials, order router, or live execution is connected. No profitability is promised.
- AI model connections are not configured. Any future AI research output must remain advisory and cannot override deterministic risk checks.
- Render free services may sleep when idle and cannot guarantee 24/7 uptime.

## Safety and India-specific use

This release is research/backtesting only. Global Forex and Indian exchange-traded currency derivatives must not be treated as interchangeable. Before considering any real-world use, independently verify current RBI, SEBI, exchange, and broker rules, permitted products, eligibility, contract specifications, data licensing, and all costs using official sources. No live trading is implemented or enabled.

Never put passwords, OTPs, broker PINs, or API secrets in this repository or in chat.

See [architecture](docs/ARCHITECTURE.md), [backtesting assumptions](docs/BACKTESTING.md), and [roadmap](docs/ROADMAP.md).
