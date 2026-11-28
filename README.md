# APEX — Personal AI-Assisted Market Research

APEX is a personal-use, demo-only autonomous Forex research and paper-trading workbench. Its monitoring dashboard is read-only except for requesting virtual demo funds. The agent ranks a small global-Forex watchlist, studies completed candles, applies deterministic indicators, and manages simulated positions. It is not a broker, signal service, investment adviser, or production trading system.

## What is implemented

- Separate global Forex and India currency-derivative profiles; execution disabled in both.
- Typed instruments, quotes, trade intents, and OHLCV candle validation.
- Deterministic moving-average crossover example.
- Event-driven OHLC backtester with next-bar-open fills and a separate contract-aware INR currency-futures backtester using contract units, JPY quotation convention, tick values, explicit fee inputs and tick slippage.
- Expanding-window walk-forward validation module.
- SQLite paper-trade journal exposed in the dashboard: create and close simulated records only after explicit confirmation; unique client IDs prevent duplicate entries. It never routes orders to a broker.
- Append-only JSONL audit logger.
- Read-only autonomous monitoring dashboard with asset rankings, price chart, agent status, execution timeline, virtual demo balance and simulated positions.
- Autonomous demo agent scans EUR/USD, GBP/USD, AUD/USD and NZD/USD on completed 15-minute candles, ranks momentum/trend setups using EMA 9/21, RSI 14 and ATR, and paper-manages a single open position with a 0.5% demo-equity risk budget, ATR stop and 2R target.
- Virtual demo account starts at USD 10,000 by default (\`APEX_DEMO_STARTING_BALANCE\` can override it); the dashboard can add virtual funds only. Demo trades are persisted in SQLite.
- Historical Forex data validation, CSV storage and provenance manifests for four USD pairs.
- Standard-library, three-class logistic-regression training pipeline with chronological train/validation/holdout splits, purging, early stopping and classification metrics.
- Repeatable CLI: \`python -m apex.train_forex --symbol EURUSD=X --period 2y --interval 1h\`.
- Existing historical backtesting, contract-aware INR futures research, licensed-provider adapters and database backup endpoints remain available as backend/research modules.
- Automated unit tests and GitHub Actions test workflow.

## Forex model training — Step 1

APEX includes a separate research pipeline to collect historical hourly/daily candles, validate and store them, train a sell/hold/buy model, and report out-of-sample classification metrics. The model is not connected to the existing autonomous scanner or any trading executor.

Run it locally:

\`\`\`bash
python -m pip install -e ".[dev]"
python -m apex.train_forex --symbol EURUSD=X --period 2y --interval 1h
\`\`\`

Generated CSV data is stored under \`data/forex/\`; model artifacts and metrics are stored under \`artifacts/forex-models/\`. Generated files are excluded from Git. The default Yahoo Finance endpoint is unofficial and not a licensed broker feed. See [the model-training guide](docs/FOREX_MODEL_TRAINING.md) for assumptions and limitations.

## Model validation — Step 2

Run the walk-forward evaluation using the saved historical CSV:

```bash
python -m apex.backtest_forex --csv data/forex/EURUSD_X_1h.csv --symbol EURUSD=X
```

It retrains the model on an expanding history before each unseen test block and compares cost-adjusted results with simple baselines. The default friction assumptions are illustrative rather than broker quotes. See [the Step 2 validation guide](docs/FOREX_MODEL_VALIDATION.md) and [the observed Step 2 results](docs/FOREX_MODEL_VALIDATION_RESULTS.md). Reports are saved under `artifacts/forex-backtests/`.

## Model V2 comparison

Run:

```bash
python -m apex.backtest_forex_v2 --csv data/forex/EURUSD_X_1h.csv --symbol EURUSD=X
```

V2 compares two alternative classifiers with the V1 logistic model using expanding-window retraining, unseen forward blocks and doubled-cost stress tests. Details are in [the V2 guide](docs/FOREX_MODEL_V2.md). All model versions remain research-only.

## Web workbench and access protection

The dashboard is protected by HTTP Basic authentication. Configure a strong, unique \`APEX_ACCESS_PASSWORD\` environment variable in the Render service before accessing it. The username is \`apex\`. If the variable is missing, the app remains locked and returns HTTP 503. Use HTTPS (Render's public URL provides TLS); do not commit the password or send it in chat. The password is not created automatically.

The Render service is intended for personal demo access. The dashboard itself is read-only apart from requesting additional virtual demo funds. The autonomous scanner starts when the dashboard requests agent status. It refreshes its scan every five minutes and the browser refreshes account and event status every ten seconds. Historical CSV backtesting remains available through the backend API and local CLI, not as a dashboard control.

## Run locally

\`\`\`bash
python -m pip install -e ".[dev]"
pytest
python -m apex demo
python app.py
\`\`\`

## Critical limitations

- The generic OHLC backtest reports quote-currency P&L. The separate INR futures backtest applies reference contract units, quotation convention, tick value and user-entered fee assumptions, but does not model margin, financing, swaps, rollover, market impact, partial fills, liquidity, or current market-specific sessions/calendars.
- The default MA strategy is a coding example, not a validated trading edge. A basic expanding-window walk-forward splitter exists, but there is no parameter-search discipline, broad robustness suite, or protection against multiple-testing/data-snooping bias.
- Historical OHLC bars cannot reproduce intrabar order sequencing. Stop-loss execution, gaps, spread dynamics and realistic fills are not modeled by the current backtester.
- SQLite storage includes market candles, paper orders, research/audit tables and integrity-checked backups. An explicit S3-compatible off-site backup action is included. Render's free filesystem is ephemeral; set APEX_DATA_DIR to a persistent mount for live database durability and configure an S3/R2 bucket for off-site snapshots. No cloud bucket or persistent disk is provisioned.
- Autonomous demo scanner uses Yahoo Finance's public chart endpoint as an unofficial, best-effort source. It may be delayed, rate-limited, changed or unavailable and is not a licensed execution feed. The Twelve Data FX adapter and user-selected licensed India endpoint remain optional research adapters; no feed credentials are required for the autonomous scanner.
- The autonomous scanner uses deterministic quantitative rules and does not call an external LLM. Optional OpenAI, Gemini and Anthropic research clients remain disabled by default; enabling them requires an explicit \`APEX_ALLOW_PAID_AI=true\` setting and may incur charges.
- No broker account or production broker adapter is connected. Live execution is hard-disabled. Every order generated by the autonomous agent is a simulated demo record. No profitability is promised.
- This initial autonomous engine covers only four USD-quoted global-Forex pairs. It does not trade Indian currency derivatives, and its indicator rules are an experimental baseline rather than a validated trading edge. The public data source is not guaranteed to be real-time or complete.
- Render free services may sleep when idle and cannot guarantee 24/7 uptime.
- The new ML model is a baseline classification model. Step 2 adds walk-forward evaluation with explicit illustrative spread/commission/slippage, next-bar open fills, baselines and doubled-cost stress. It still omits broker-specific pricing, swaps, rollover, financing, margin, partial fills and market impact. Every model output is research-only and trading authorization remains false.

## Safety and India-specific use

This release is research/backtesting only. Global Forex and Indian exchange-traded currency derivatives must not be treated as interchangeable. Before considering any real-world use, independently verify current RBI, SEBI, exchange, and broker rules, permitted products, eligibility, contract specifications, data licensing, and all costs using official sources. No live trading is implemented or enabled.

Never put passwords, OTPs, broker PINs, or API secrets in this repository or in chat.

See [architecture](docs/ARCHITECTURE.md), [integration setup and assumptions](docs/INTEGRATIONS.md), and [roadmap](docs/ROADMAP.md).
