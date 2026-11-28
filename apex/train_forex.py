"""Download historical Forex bars and train the APEX research model.

Run: python -m apex.train_forex --symbol EURUSD=X --period 2y --interval 1h
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .forex_data import (
    SUPPORTED_PERIODS,
    SUPPORTED_SYMBOLS,
    fetch_yahoo_history,
    safe_symbol_name,
    save_history,
)
from .forex_ml import dataset_sha256, train_model


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train an APEX Forex research model")
    parser.add_argument("--symbol", choices=sorted(SUPPORTED_SYMBOLS), default="EURUSD=X")
    parser.add_argument("--period", choices=sorted(SUPPORTED_PERIODS), default="2y")
    parser.add_argument("--interval", choices=("1h", "1d"), default="1h")
    parser.add_argument("--data-dir", default="data/forex")
    parser.add_argument("--model-dir", default="artifacts/forex-models")
    parser.add_argument("--horizon-bars", type=int, default=3)
    parser.add_argument("--min-move-bps", type=float, default=1.5)
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--csv", help="Use an existing validated CSV instead of downloading")
    parser.add_argument("--download-only", action="store_true", help="Download and validate history without fitting a model")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    symbol_name = safe_symbol_name(args.symbol)
    data_dir = Path(args.data_dir)
    model_dir = Path(args.model_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    if args.csv:
        from .forex_data import load_history
        csv_path = Path(args.csv)
        candles = load_history(csv_path)
        dataset_manifest = {
            "symbol": args.symbol,
            "interval": args.interval,
            "source": "user-supplied CSV; provenance not independently verified",
            "row_count": len(candles),
            "csv_file": str(csv_path),
        }
    else:
        candles = fetch_yahoo_history(
            args.symbol, period=args.period, interval=args.interval
        )
        csv_path = data_dir / f"{symbol_name}_{args.interval}.csv"
        dataset_manifest = save_history(
            candles,
            csv_path,
            symbol=args.symbol,
            interval=args.interval,
            period=args.period,
        )

    if args.download_only:
        print(json.dumps({"dataset": dataset_manifest, "csv_file": str(csv_path)}, indent=2))
        return 0

    model_path = model_dir / f"{symbol_name}_{args.interval}.json"
    model, metrics = train_model(
        candles,
        model_path=model_path,
        horizon_bars=args.horizon_bars,
        min_move_bps=args.min_move_bps,
        epochs=args.epochs,
    )
    report = {
        "dataset": dataset_manifest,
        "dataset_sha256": dataset_sha256(candles),
        "model_file": str(model_path),
        "model_created_at": model.created_at,
        "metrics": metrics,
        "next_step": (
            "Review holdout results and proceed to cost-aware walk-forward "
            "backtesting. The model is not authorized to place trades."
        ),
    }
    report_path = model_dir / f"{symbol_name}_{args.interval}.metrics.json"
    report_path.write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
