# APEX Step 2 — observed walk-forward results

**Evaluation workflow:** [GitHub Actions run 46133191915](https://github.com/Kartik30-art/APEX/actions/runs/46133191915)  
**Source revision:** `49a2c3ec` (walk-forward engine and EMA benchmark)  
**Decision:** **No pair/model is approved for demo execution.**

## Method

Each pair used five sequential forward test folds. APEX retrained on historical candles available before each fold, then predicted only the following unseen block. The five test blocks covered 9,000 hourly bars per pair; 8,985 samples were eligible for classification metrics after the three-bar label horizon was purged at block boundaries.

The simulated ML strategy used completed-candle signals filled at the next candle open. It used at most 1x unlevered notional. Base costs were assumed at 0.8 bps spread per side, 0.2 bps slippage per side and 0.0 bps commission per side. A second run doubled those assumptions. These are illustrative assumptions, not broker quotations.

## Results

| Pair | Out-of-sample accuracy | Training-majority accuracy | ML net return | ML trades | Positive folds | Double-cost ML return |
|---|---:|---:|---:|---:|---:|---:|
| EUR/USD | 39.69% | 38.95% | -0.67% | 14 | 1/5 | -0.94% |
| GBP/USD | 41.55% | 40.03% | -1.40% | 27 | 1/5 | -1.93% |
| AUD/USD | 38.22% | 37.55% | +0.44% | 1 | 1/5 | +0.42% |
| NZD/USD | 36.93% | 34.52% | +0.16% | 1 | 1/5 | +0.14% |

For context, the buy-and-hold baseline returned -3.02% on EUR/USD, -2.08% on GBP/USD, +7.76% on AUD/USD and -5.38% on NZD/USD. The EMA 8/21 trend reference lost money on all four pairs in these same windows. Neither reference is a guaranteed or universally suitable strategy.

## Interpretation

- The logistic model beat the training-majority classifier by a small amount in classification accuracy, but that did not translate into consistent net trading returns.
- EUR/USD and GBP/USD lost money after the assumed costs.
- AUD/USD and NZD/USD were slightly positive only because each model made one trade across all five test folds. One trade is not a meaningful performance sample.
- Each pair was profitable in only one of five folds.
- The doubled-cost test did not rescue the negative EUR/USD and GBP/USD results.

## Decision and next work

All four models remain **research-only**. Do not connect them to MT5, the APEX autonomous demo agent or any order executor.

The next model iteration should compare alternative classifiers and feature sets using the training/validation portions only. The forward folds documented here must remain out-of-sample; do not repeatedly tune the confidence threshold or strategy against these same test windows and then call the result independent validation.

This is not a profitability claim or a recommendation to trade. The data source is Yahoo Finance's unofficial public chart endpoint and the simulation does not reproduce broker bid/ask quotes, contract sizing, margin, swaps, rollover, financing, partial fills, market impact or liquidation.
