# APEX Forex model validation — Step 2

## What the evaluation does

Step 2 evaluates models on multiple forward-only windows. For each fold, APEX trains using candles strictly before that fold, selects training epochs using an inner chronological validation split, then evaluates only on the next unseen block. The following fold expands the historical training window and repeats the process.

The simulator reports:
- Out-of-sample sell/hold/buy classification accuracy, balanced accuracy, macro-F1 and confusion matrix.
- Next-bar-open simulated trades, win rate, profit factor, ending equity and drawdown.
- An always-flat baseline, a training-majority-class baseline and buy-and-hold.
- A doubled-cost stress test to expose sensitivity to spread/slippage assumptions.

## Run it

After downloading history with Step 1, run:

    python -m apex.backtest_forex --csv data/forex/EURUSD_X_1h.csv --symbol EURUSD=X

Defaults: 3,000 initial hourly bars, 1,800 bars per test window, up to five expanding-window folds, 0.45 minimum directional probability, 0.8 basis points of spread per side, 0.2 basis points of slippage per side, and zero commission unless changed.

Override costs when your broker's documented demo-account pricing is known:

    python -m apex.backtest_forex --csv path/to/candles.csv --symbol EURUSD=X --spread-bps-per-side 1.2 --commission-bps-per-side 0.3 --slippage-bps-per-side 0.5

Reports are written to artifacts/forex-backtests/. The simulator uses 1x unlevered notional and does not model lot sizing, margin, swaps, rollover, funding, partial fills or market impact. Its friction settings are transparent assumptions, not actual broker quotes.

## Decision rule

Do not choose the best-looking model or confidence threshold on the same out-of-sample folds and then treat those results as independent confirmation. Use these reports to reject weak approaches and define a new experiment. A candidate must beat simple baselines after costs across multiple folds and remain stable under doubled costs before additional demo-only forward testing is considered.

All reports are marked research-only and trading_authorized=false. Nothing here connects to a broker or enables execution.
