# Architecture and trust boundaries

## Current components

- `models.py`: typed market, instrument, quote and trade-intent data.
- `markets.py`: separate global Forex and Indian currency-derivative profiles; both disable execution.
- `data_validation.py`: timezone, OHLCV, duplicate and chronology checks.
- `strategies.py`: deterministic strategy protocol and example moving-average cross.
- `backtest.py`: next-bar OHLC backtest with explicit fee/slippage assumptions and mark-to-market drawdown.
- `risk.py`: deterministic baseline checks; not contract-aware and not approved for live sizing.
- `paper.py`: SQLite paper journal with explicit confirmation and idempotent client IDs; not exposed by the web API.
- `audit.py`: append-only JSONL event log.
- `app.py`: research-only dashboard and CSV backtest endpoint.

## Trust boundaries

AI outputs, if connected later, are untrusted research proposals. They cannot change risk settings, execute code, or place orders. Strategy implementations are deterministic code. The Risk Guardian remains independent. No execution adapter or broker credential interface exists.

## Data flow

CSV upload -> timestamp/OHLCV parsing -> validation -> deterministic strategy -> next-bar simulation -> metrics and trade list.

The paper journal is a separate local module and is not automatically fed from backtests or connected to any broker.

## Safety invariants

- Live trading is disabled and no live order-routing code exists.
- Both market profiles have execution disabled.
- The public web API exposes only historical backtesting, not paper-journal write operations.
- No passwords, OTPs, broker PINs or API secrets are stored.
- Backtest assumptions are explicit and materially incomplete; see BACKTESTING.md.

## Deployment caveats

Render free web services may sleep when idle. Their filesystem is ephemeral; SQLite/JSONL files written to the service can be lost on restart, redeploy or spin-down. Do not use Render's local filesystem as durable trade storage. The current dashboard has no user authentication, so the public URL must not be treated as a private or confidential workspace.
