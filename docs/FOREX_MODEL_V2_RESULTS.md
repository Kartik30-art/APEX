# APEX Model V2 — observed four-pair results

**Evaluation run:** [GitHub Actions run 46133933555](https://github.com/Kartik30-art/APEX/actions/runs/46133933555)  
**Result:** all four pair jobs succeeded; all reports and V2 model artifacts were uploaded.  
**Decision:** **No model is approved for demo execution.**

## Method

APEX compared the existing V1 logistic-regression model with two V2 candidates:

- Gaussian Naive Bayes using the V2 feature set.
- A deterministic shallow random forest (13 trees, depth 3) using the same V2 feature set.

V2 adds six historical-only features: EMA 21/55 gap, 24- and 48-bar returns, 7-period RSI, short/long volatility ratio, and candle close location. Each fold fits only on earlier candles, and the model is evaluated on the next unseen block. There are five non-overlapping outer test folds and 8,985 eligible labelled rows per pair.

Signals require a directional confidence of at least 0.45. Entries occur at the next candle open. The simulator assumes 1x unlevered notional, spread of 0.8 bps per side, slippage of 0.2 bps per side, and zero commission. A separate stress version doubles all three cost assumptions. The costs are illustrative, not verified broker quotations.

## Out-of-sample classification accuracy

The values below are the mean accuracy across the five outer folds. The majority baseline is the majority class within the corresponding test fold.

| Pair | Majority baseline | V1 logistic | V2 Gaussian NB | V2 random forest |
|---|---:|---:|---:|---:|
| EUR/USD | 38.90% | 39.68% | 40.81% | 41.47% |
| GBP/USD | 39.96% | 41.42% | 41.49% | 43.49% |
| AUD/USD | 37.55% | 38.22% | 36.79% | 38.17% |
| NZD/USD | 35.35% | 36.93% | 34.91% | 36.94% |

The random forest produced the best classification accuracy on EUR/USD and GBP/USD, but this did not produce a reliable trading result.

## Cost-adjusted outer walk-forward results

Returns are compounded across the five non-overlapping test folds. Each fold starts with a separate illustrative USD 10,000 account.

| Pair | V1 logistic | V2 Gaussian NB | NB trades | V2 random forest | RF trades |
|---|---:|---:|---:|---:|---:|
| EUR/USD | -0.50% | -20.47% | 856 | 0.00% | 0 |
| GBP/USD | -1.47% | -17.62% | 908 | -0.51% | 31 |
| AUD/USD | +0.44% | -10.50% | 917 | 0.00% | 0 |
| NZD/USD | +0.16% | +1.39% | 503 | -0.34% | 14 |

### Doubled-cost stress test

| Pair | V1 logistic | V2 Gaussian NB | V2 random forest |
|---|---:|---:|---:|
| EUR/USD | -0.80% | -32.99% | 0.00% |
| GBP/USD | -2.02% | -31.30% | -1.13% |
| AUD/USD | +0.42% | -25.50% | 0.00% |
| NZD/USD | +0.14% | -8.31% | -0.62% |

A zero return with zero trades means the model did not clear the confidence gate and stayed flat; it is not evidence of profitability. V1's small positive returns on AUD/USD and NZD/USD each came from just one trade across all five folds. V2 Gaussian Naive Bayes traded hundreds of times and lost significantly on three pairs. Its small positive NZD/USD result reversed under doubled costs.

## Decision

- **V1 logistic:** not approved. The isolated positive results came from one trade and are not a reliable sample.
- **V2 Gaussian Naive Bayes:** rejected in its current form. It overtrades and is highly sensitive to the illustrative costs.
- **V2 random forest:** not approved. Classification accuracy improved on two pairs, but the cost-adjusted return was flat or negative, with zero or very few trades.

No model is connected to MT5, the APEX autonomous agent, or an order executor. All artifacts remain `research_only` with `trading_authorized: false`.

## Next research step

The next experiment should address probability calibration and the difference between classification accuracy and actionable trade quality. Any confidence calibration or signal filter must be fitted only on data available before each outer test fold. The five outer windows above must not be re-used to tune a model and then be presented as independent validation. A new untouched period will be needed after the next iteration.

## Important limitations

The history comes from Yahoo Finance's unofficial public chart endpoint, not a licensed or broker-specific price feed. The simulator does not reproduce broker bid/ask quotes, lot sizes, leverage, margin, liquidation, swaps, rollover, financing, partial fills, liquidity, market impact or the broker's actual commission schedule. These results are research diagnostics, not evidence of future profitability or a recommendation to trade.
