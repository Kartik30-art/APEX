# APEX Model V3 — calibration and signal-selection experiment

## Purpose

V2 showed that better classification accuracy did not automatically translate into cost-adjusted returns. V3 tests two narrower questions:

1. Can a bounded multiclass temperature scaler make the sell/hold/buy probabilities less overconfident?
2. Can a conservative directional-confidence gate avoid low-quality trades when the model does not show a validation-period edge?

V3 is a research experiment only. It has no broker adapter, MT5 bridge, order-routing path or trading authorization.

## Date-separated daily evaluation

The automated workflow downloads up to ten years of daily history for EUR/USD, GBP/USD, AUD/USD and NZD/USD. The data is cut off at **2024-10-01 (exclusive)** before samples are built. This keeps the V3 outer-test period on earlier calendar dates than V2's recent two-year hourly dataset. It is a separate historical-frequency experiment, not evidence that a daily model will work intraday.

Default expanding-window configuration:

- Initial history: 750 daily bars.
- Outer test block: 250 daily bars.
- Maximum outer folds: 5.
- Label horizon: 3 bars.
- Model candidates: Gaussian Naive Bayes and the deterministic shallow random forest from V2.

The workflow uses the free, unofficial Yahoo Finance public chart endpoint. Data can be incomplete, revised, delayed or unavailable; it is not licensed broker bid/ask data.

## Strict chronological sub-splits

For every outer fold, only samples whose full three-bar labels are contained in the history before the test start are admitted. That historical sample sequence is split chronologically:

| Segment | Approximate share | Purpose |
|---|---:|---|
| Fit | First 60% | Fit model parameters |
| Calibration | Next 20% | Select temperature using multiclass log loss |
| Threshold selection | Final 20% | Choose a confidence gate using cost-adjusted simulated trades |

A three-sample purge is applied at each boundary. The fit segment cannot see calibration labels; calibration cannot see threshold-selection labels; and the threshold-selection labels must finish before the outer test begins. The outer test is not used for any model fitting, calibration or threshold choice.

Temperature scaling searches the fixed range 0.50 to 3.00 in 0.05 increments. It rescales the three class probabilities without changing model parameters or the predicted class order.

## Trade-selection rule

A sell or buy signal is eligible only when its calibrated probability both beats the hold probability and meets a candidate confidence threshold. The threshold grid is fixed before outer testing:

0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70

The threshold-selection segment evaluates each candidate with the same next-bar-open simulator and illustrative transaction costs used in the outer test. A candidate needs at least ten completed trades by default. Its validation objective is:

**Net compounded return − 0.25 × maximum drawdown**

If no candidate has a positive objective and enough trades, V3 chooses **NO_TRADE**. That is intentionally preferable to forcing a signal. The model is not guaranteed to maintain its selected threshold after a market-regime change.

Each outer test compares:
- The raw V2 probability output using the legacy 0.45 gate.
- Temperature-calibrated probabilities with a fixed 0.45 gate.
- Temperature-calibrated probabilities with the threshold selected on the earlier validation segment.

The report includes outer-test log loss, multiclass Brier score, 10-bin expected calibration error, classification diagnostics, compounded returns, trade counts, drawdown and a doubled-cost stress test for the selected strategy.

## Cost and fill assumptions

Default illustrative assumptions are 0.8 basis points spread per side, 0.2 basis points slippage per side and zero commission. The stress test doubles all costs. Entry is approximated at the next candle open, exposure is capped at 1x unlevered notional, and a USD 10,000 starting balance is used independently for each fold.

These assumptions are not broker quotes. The simulator omits margin, swaps, rollover, financing, contract specifications, market impact, partial fills, liquidity and intrabar stop/target sequencing.

## Reproduction

Download the separate daily series:

~~~bash
python -m apex.train_forex --symbol EURUSD=X --period 10y --interval 1d --data-dir data/forex-v3 --download-only
~~~

Run the V3 evaluation:

~~~bash
python -m apex.backtest_forex_v3 --csv data/forex-v3/EURUSD_X_1d.csv --symbol EURUSD=X
~~~

The four-pair GitHub Actions workflow uploads the daily data, research-only model/calibration metadata and full JSON reports as run artifacts. A published results document is added only after the workflow and tests complete.

## Decision rule

No model is selected for execution merely because it wins one fold, one currency pair or one validation segment. A candidate would need stable positive net results across pairs and folds, adequate trade counts, acceptable drawdown, resilience to doubled costs and a later forward demo-shadow period using broker-specific data. No MT5/demo execution is enabled by this experiment.

All exported model and calibration metadata explicitly contain research_only=true and trading_authorized=false.
