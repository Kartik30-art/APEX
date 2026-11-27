# APEX — AI-Assisted Market Research

APEX is a research-first foundation for global Forex and Indian exchange-traded currency derivatives. The two markets are intentionally separated because their legal eligibility, contracts, sessions, pricing, and costs differ.

## Current status: Phase 0 foundation
- Typed market, instrument, quote, and trade-intent models
- Separate market profiles; execution disabled for both
- OHLCV candle validation and stale-data warnings
- Deterministic moving-average crossover example
- Basic deterministic Risk Guardian
- Append-only JSONL audit logger
- Automated unit tests

## Safety
Research and paper trading only. No broker adapter, order routing, live trading, or credentials are included. AI-generated research is untrusted and cannot override deterministic risk controls. The current risk calculation is simplified and is not contract-aware; do not use it for real position sizing.

## Run
```bash
python -m pip install -e ".[dev]"
pytest
python -m apex demo
```

See `docs/ARCHITECTURE.md` and `docs/ROADMAP.md`. This is a tested foundation, not a completed or profit-guaranteeing trading system.
