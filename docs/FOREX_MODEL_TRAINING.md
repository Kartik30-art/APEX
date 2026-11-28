# APEX Forex model training — Step 1

## What this step adds

- Free, best-effort historical OHLCV collection for EUR/USD, GBP/USD, AUD/USD and NZD/USD.
- Candle validation, UTC normalization, duplicate checks, CSV storage and provenance manifests.
- A three-class model (sell / hold / buy) using standard-library multinomial logistic regression.
- Ten price and volatility features, volatility-adjusted future-return labels, and chronological 70/15/15 train/validation/holdout splits.
- A horizon-sized purge at split boundaries to reduce target leakage.
- Validation-loss early stopping, holdout accuracy, balanced accuracy, macro-F1, confusion matrix and a majority-class baseline.
- Versioned JSON model artifacts and a repeatable command-line training workflow.

## Run it

Python 3.10 or newer is required. No paid API key or third-party machine-learning package is needed.

    python -m pip install -e ".[dev]"
    python -m apex.train_forex --symbol EURUSD=X --period 2y --interval 1h

Other supported symbols: GBPUSD=X, AUDUSD=X and NZDUSD=X.

To train from an existing CSV:

    python -m apex.train_forex --symbol EURUSD=X --csv path/to/candles.csv

The CSV must contain timestamp, open, high, low and close columns. Volume is optional. Timestamps must include a timezone.

The command writes downloaded data under data/forex/, model weights under artifacts/forex-models/, and a metrics report beside the model. These generated files are ignored by Git.

## Data source and limitations

The default downloader uses Yahoo Finance's public chart endpoint. It is unofficial, may change, be delayed, omit data, impose rate limits, or stop working. It is not licensed execution data, and returned FX candles may not match a broker's prices or timezone. The dataset manifest records this provenance. Reported FX volume is not centralized Forex trading volume.

The model predicts a three-class label over the next three bars by default. Labels use a volatility-adjusted threshold. The model is a deliberately simple and auditable baseline, not a claim of predictive edge. Results can vary by pair, period, feed and market regime.

The holdout set is not used for gradient updates or early stopping. The forward-return horizon is purged at chronological split boundaries. Holdout metrics are classification metrics, not net trading returns. They exclude spread, commissions, swaps, financing, slippage, leverage and realistic fills.

## Safety gate

Every model artifact and prediction is marked research_only; trading_authorized is always false. This step does not connect the model to MT5, a broker, a paper-trading executor, or a live account. Do not use the model for actual trading.

Before demo execution is considered in a later step, APEX still needs cost-aware walk-forward backtesting, strategy comparison, robustness and regime checks, and an independent risk-control layer. A model that performs poorly on holdout must be rejected or redesigned, not deployed.
