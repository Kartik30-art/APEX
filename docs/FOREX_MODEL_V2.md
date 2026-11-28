# APEX Model V2

## What is V2

V2 adds two separate classifiers to the V1 logistic-regression baseline:

- Gaussian Naive Bayes with class-conditional feature distributions.
- A compact random forest (13 shallow trees by default) using deterministic bootstrap sampling and random feature subsets.

V2 also adds six causal features: EMA 21/55 gap, 24- and 48-bar returns, 7-period RSI, short/long realized-volatility ratio, and candle close location. All features are calculated using candles available at or before the evaluated candle.

No neural network or external AI service is used. The purpose is a controlled comparison of different model assumptions without adding cost or opaque dependencies.

## Evaluation design

For every outer walk-forward fold:
1. Only candles before the test window are available for fitting.
2. The historical training sample is split chronologically; V2 estimators fit the earlier 70% portion.
3. Validation metrics are reported separately and are not used to select the outer test winner.
4. Each candidate predicts the following unseen block.
5. Signals enter at the next candle open and are compared after the same explicit friction assumptions.
6. A doubled-cost version is calculated for every ML candidate.

The comparison includes V1 logistic regression, V2 Gaussian Naive Bayes and V2 random forest. Benchmarks include training-majority class, buy-and-hold, EMA 8/21 and always-flat.

## Run V2 comparison

    python -m pip install -e ".[dev]"
    python -m apex.backtest_forex_v2 --csv data/forex/EURUSD_X_1h.csv --symbol EURUSD=X

Results are saved under \`artifacts/forex-v2-backtests/\`. Reports are research-only and no model is authorized to place trades.

## Limitations

The random forest is intentionally shallow and standard-library based; it is a baseline, not a claim of optimality. The data source remains Yahoo Finance's unofficial public chart endpoint. Spread, commission and slippage are illustrative assumptions, and the simulator does not model broker contract sizes, leverage, margin, swaps, financing, partial fills, liquidity, market impact or liquidation.

Do not tune candidate settings repeatedly against the same outer folds. A model candidate must show a stable edge on independent, untouched data before any demo-only shadow or forward simulation is considered.
