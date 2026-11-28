"""Run cost-aware walk-forward Forex ML research from a validated CSV.

Run: python -m apex.backtest_forex --csv data/forex/EURUSD_X_1h.csv
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .forex_data import load_history, safe_symbol_name
from .forex_backtest import TradingCosts, walk_forward_ml_backtest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cost-aware walk-forward APEX Forex backtest")
    parser.add_argument("--csv", required=True, help="Validated OHLCV CSV")
    parser.add_argument("--symbol", default="EURUSD=X")
    parser.add_argument("--report-dir", default="artifacts/forex-backtests")
    parser.add_argument("--initial-train-bars", type=int, default=3000)
    parser.add_argument("--test-bars", type=int, default=1800)
    parser.add_argument("--max-folds", type=int, default=5)
    parser.add_argument("--min-confidence", type=float, default=0.45)
    parser.add_argument("--spread-bps-per-side", type=float, default=0.8)
    parser.add_argument("--commission-bps-per-side", type=float, default=0.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=0.2)
    parser.add_argument("--epochs", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    candles = load_history(args.csv)
    costs = TradingCosts(
        spread_bps_per_side=args.spread_bps_per_side,
        commission_bps_per_side=args.commission_bps_per_side,
        slippage_bps_per_side=args.slippage_bps_per_side,
    )
    report = walk_forward_ml_backtest(
        candles,
        initial_train_bars=args.initial_train_bars,
        test_bars=args.test_bars,
        max_folds=args.max_folds,
        min_confidence=args.min_confidence,
        epochs=args.epochs,
        costs=costs,
    )
    report["symbol"] = args.symbol
    report["dataset_file"] = str(args.csv)
    destination = Path(args.report_dir)
    destination.mkdir(parents=True, exist_ok=True)
    report_path = destination / f"{safe_symbol_name(args.symbol)}_walk_forward.json"
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
