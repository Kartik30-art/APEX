# Architecture and trust boundaries

## Current components

- \`models.py\`: typed market, instrument, quote and trade-intent data.
- \`markets.py\`: separate global Forex and Indian currency-derivative profiles; both disable execution.
- \`data_validation.py\`: timezone, OHLCV, duplicate and chronology checks.
- \`forex_data.py\`: historical public-chart collection, candle validation, CSV persistence and provenance manifests.
- \`forex_ml.py\`: feature engineering, a three-class logistic-regression baseline, chronological validation, holdout metrics, and versioned model artifacts.
- \`train_forex.py\`: repeatable data-download and training command.
- \`strategies.py\`: deterministic strategy protocol and example moving-average cross.
- \`backtest.py\`: next-bar OHLC backtest with explicit fee/slippage assumptions and mark-to-market drawdown.
- \`risk.py\`: deterministic baseline checks; not contract-aware and not approved for live sizing.
- \`paper.py\`: SQLite paper journal with explicit confirmation and idempotent client IDs; it is separate from model training.
- \`audit.py\`: append-only JSONL event log.
- \`app.py\`: HTTP Basic-authenticated research-only dashboard and CSV backtest endpoint. It requires \`APEX_ACCESS_PASSWORD\` and refuses access if it is unset.

## Trust boundaries

ML model outputs are untrusted research predictions. They cannot change risk settings, execute code, or place orders. The model artifact explicitly carries \`trading_authorized: false\`. Strategy implementations and the Risk Guardian remain separate. No execution adapter or broker credential interface exists.

## Data flow

Historical public candles -> OHLCV validation -> feature and label generation -> chronological train/validation/holdout split -> model training with validation early stopping -> untouched holdout report -> repeated expanding-window retraining -> next-bar-open cost-aware backtesting -> baseline and stress comparisons.

CSV upload -> timestamp/OHLCV parsing -> validation -> deterministic strategy -> next-bar simulation -> metrics and trade list.

The paper journal is a separate local module and is not automatically fed from ML predictions or connected to any broker.

## Safety invariants

- Live trading is disabled and no live order-routing code exists.
- Both market profiles have execution disabled.
- ML models are labeled research-only; training cannot authorize execution.
- Generated datasets and model artifacts are not committed to Git.
- No passwords, OTPs, broker PINs or API secrets are stored.
- Backtest assumptions are explicit and materially incomplete; see BACKTESTING.md.

## Deployment caveats

Render free web services may sleep when idle. Their filesystem is ephemeral; SQLite/JSONL files written to the service can be lost on restart, redeploy or spin-down. Do not use Render's local filesystem as durable trade storage. The dashboard now uses HTTP Basic authentication. Configure a strong \`APEX_ACCESS_PASSWORD\` in Render; until configured, it returns HTTP 503. Treat the password as a secret and rotate it if exposed.
