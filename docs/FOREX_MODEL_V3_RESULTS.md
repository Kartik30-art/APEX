# APEX Model V3 — four-pair results and decision

**Evaluation:** [GitHub Actions run 46135005609](https://github.com/Kartik30-art/APEX/actions/runs/46135005609)  
**Status:** all four pair jobs completed successfully; all five outer daily test folds ran for each pair.  
**Decision:** **No model is approved for demo or live execution.**

## What was tested

V3 compared the V2 Gaussian Naive Bayes (NB) and shallow random forest (RF) classifiers in three signal modes:

- **V2 raw .45:** uncalibrated model probabilities, with the existing 0.45 directional-confidence gate.
- **V3 calibrated .45:** temperature-scaled probabilities, retaining the fixed 0.45 gate.
- **V3 validation-selected:** temperature-scaled probabilities with a threshold selected only on the earlier threshold-selection segment.

For every outer fold, the model was fitted on the first chronological segment, its temperature was selected on a later calibration segment, and its confidence threshold was selected on a still-later validation segment. The three-bar label horizon was purged at the boundaries. The outer test segment was not used for fitting, calibration or threshold selection.

V3 used a separate daily dataset, cut off at **2024-10-01 (exclusive)**. Its test windows therefore precede the recent two-year hourly V2 evaluation window. Each pair has five expanding-window test folds:

| Pair | V3 test period | Outer folds |
|---|---|---:|
| EUR/USD | 2019-11-07 to 2024-09-30 | 5 |
| GBP/USD | 2019-11-06 to 2024-09-30 | 5 |
| AUD/USD | 2019-11-21 to 2024-09-30 | 5 |
| NZD/USD | 2019-12-23 to 2024-09-30 | 5 |

This is a separate daily-frequency experiment. It is **not** evidence that a daily strategy will work on intraday hourly or 15-minute data.

## Compounded outer-test returns

Returns below are compounded across the five non-overlapping outer test folds. Each fold used a separate illustrative USD 10,000 starting balance. These are historical backtest outputs under the assumptions below, not actual account returns.

| Pair | V2 raw NB .45 | V3 calibrated NB .45 | V3 selected NB | V2 raw RF .45 | V3 calibrated RF .45 | V3 selected RF |
|---|---:|---:|---:|---:|---:|---:|
| EUR/USD | -18.37% | -11.40% | -5.74% | +1.40% | -7.46% | +2.82% |
| GBP/USD | -2.02% | +4.02% | -0.59% | -0.77% | -2.12% | -8.51% |
| AUD/USD | -25.72% | -14.82% | -9.44% | +9.76% | -15.60% | -14.62% |
| NZD/USD | -16.90% | -2.40% | -9.12% | -17.75% | -28.45% | -1.32% |

The validation-selected variants did not produce consistent positive results. Gaussian NB selected was negative on all four pairs. Random forest selected was negative on three pairs; its EUR/USD result was only +2.82% before the higher-cost stress test.

## Validation-selected strategy trade counts

| Pair | NB trades | NB positive folds | RF trades | RF positive folds |
|---|---:|---:|---:|---:|
| EUR/USD | 73 | 1/5 | 171 | 3/5 |
| GBP/USD | 75 | 1/5 | 78 | 0/5 |
| AUD/USD | 126 | 1/5 | 235 | 2/5 |
| NZD/USD | 57 | 0/5 | 57 | 1/5 |

The threshold selector explicitly chose **NO_TRADE** in several individual folds when no eligible candidate produced a positive validation objective with enough trades. A zero-trade fold is a decision to remain flat; it is not a profitable result.

## Doubled-cost stress test

This table applies double the already illustrative spread, commission and slippage assumptions to the V3 validation-selected variants.

| Pair | NB selected, double costs | RF selected, double costs |
|---|---:|---:|
| EUR/USD | -7.11% | -0.64% |
| GBP/USD | -2.07% | -9.93% |
| AUD/USD | -11.70% | -18.55% |
| NZD/USD | -10.15% | -2.44% |

No selected model is consistently profitable across pairs and resistant to the doubled-cost test. Calibration was not a universal improvement: for example, AUD/USD raw RF returned +9.76%, while its calibrated and validation-selected versions were substantially negative. EUR/USD selected RF was +2.82% at base costs but turned negative at doubled costs.

## Conclusion and model decision

- **Gaussian NB:** not approved. Its selected version lost money on all four pairs.
- **Random forest:** not approved. Its validation-selected results were inconsistent and all four pairs failed the doubled-cost stress test.
- **Temperature scaling:** useful to investigate probability sharpness, but it did not reliably improve trading outcomes across pairs. The calibration temperature and selected threshold varied materially by pair and fold.
- **Threshold selection:** the later outer tests did not consistently reproduce the positive returns seen in the inner selection segment. This is a warning against treating validation-optimal thresholds as persistent trading edges.

APEX therefore keeps every V3 model and calibration artifact as `research_only: true` and `trading_authorized: false`. No model is connected to MT5, a broker, or any order executor. No demo execution is authorized by these results.

## Costs, data and limitations

- Data: Yahoo Finance's free public chart endpoint, which is unofficial and is not a licensed broker bid/ask feed. History may be incomplete, revised, delayed or unavailable.
- Frequency and label: daily candles with a three-daily-bar forward label horizon. This is not the same as an intraday signal horizon.
- Execution approximation: signal from a completed candle and fill at the next candle open.
- Exposure: maximum 1x unlevered notional; each fold starts with a separate illustrative USD 10,000 balance.
- Base costs: spread 0.8 bps per side, slippage 0.2 bps per side, zero commission. Costs are illustrative rather than broker quotes.
- Stress test: doubles the base cost assumptions.
- Excluded: broker-specific bid/ask dynamics, actual commission schedules, swaps, rollover, financing, contract sizes, margin, liquidation, liquidity, partial fills and market impact.

These limitations mean that even a positive historical fold result would not establish a tradable edge. A candidate would need stable evidence across genuinely later forward data, broker-specific costs and a separately monitored demo-shadow phase before execution could even be reconsidered.

## Reproducible artifacts

Each artifact contains that pair's downloaded V1/V2/V3 history, reports and research-only model/calibration metadata. GitHub Actions retains the artifacts for 30 days.

- [EUR/USD artifact](https://github.com/Kartik30-art/APEX/actions/runs/46135005609/artifacts/15259551970)
- [GBP/USD artifact](https://github.com/Kartik30-art/APEX/actions/runs/46135005609/artifacts/15259038221)
- [AUD/USD artifact](https://github.com/Kartik30-art/APEX/actions/runs/46135005609/artifacts/15259546395)
- [NZD/USD artifact](https://github.com/Kartik30-art/APEX/actions/runs/46135005609/artifacts/15258879236)

See the [V3 methodology](FOREX_MODEL_V3.md), [V3 implementation](../apex/backtest_forex_v3.py), and [complete workflow run](https://github.com/Kartik30-art/APEX/actions/runs/46135005609).
