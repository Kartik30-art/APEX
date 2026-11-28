"""Cost-aware outer walk-forward comparison of APEX V1 and V2 models."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .forex_backtest import (
    TradingCosts,
    _aggregate_folds,
    _classification_report,
    _trade_simulation,
)
from .forex_data import load_history, safe_symbol_name
from .forex_ml import build_samples, train_model, _features_at
from .forex_models_v2 import (
    build_v2_samples,
    features_at_v2,
    fit_gaussian_nb,
    fit_random_forest,
)


def walk_forward_v2(
    candles: list[dict],
    *,
    initial_train_bars: int = 3000,
    test_bars: int = 1800,
    max_folds: int = 5,
    min_confidence: float = 0.45,
    costs: TradingCosts = TradingCosts(),
    epochs: int = 100,
    trees: int = 13,
) -> dict:
    if initial_train_bars < 500 or test_bars < 100:
        raise ValueError("initial_train_bars must be >= 500 and test_bars >= 100")
    if max_folds < 1 or max_folds > 20:
        raise ValueError("max_folds must be between 1 and 20")
    if not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1")
    if len(candles) <= initial_train_bars + 100:
        raise ValueError("not enough data for V2 walk-forward evaluation")

    all_samples_v1 = {sample.source_index: sample for sample in build_samples(candles)}
    all_samples_v2 = {sample.source_index: sample for sample in build_v2_samples(candles)}
    candidate_names = ("v1_logistic", "v2_gaussian_nb", "v2_random_forest")
    strategy_names = candidate_names + (
        "training_majority_class", "buy_and_hold_long", "ema_8_21_trend",
        "always_flat",
    )
    folds = []
    train_end = initial_train_bars
    final_models = {}

    while train_end < len(candles) and len(folds) < max_folds:
        test_end = min(train_end + test_bars, len(candles))
        if test_end - train_end < 100:
            break

        history = candles[:train_end]
        v1_model, _ = train_model(history, epochs=epochs, patience=12)
        v1_samples = [s for idx, s in all_samples_v1.items() if idx < train_end - 3]
        v2_samples = [s for idx, s in all_samples_v2.items() if idx < train_end - 3]
        if len(v1_samples) < 100 or len(v2_samples) != len(v1_samples):
            raise ValueError("V1/V2 training samples are not aligned")

        split = int(len(v2_samples) * 0.70)
        v2_train = v2_samples[:split - 3]
        v2_validation = v2_samples[split:]
        if len(v2_train) < 100 or len(v2_validation) < 20:
            raise ValueError("not enough V2 samples for chronological train/validation")
        nb_model = fit_gaussian_nb(v2_train)
        forest_model = fit_random_forest(v2_train, n_trees=trees)
        models = {
            "v1_logistic": v1_model,
            "v2_gaussian_nb": nb_model,
            "v2_random_forest": forest_model,
        }
        final_models = models

        # Validation is reported for diagnosis only. Outer forward blocks remain
        # untouched and no candidate selection is performed on them.
        v2_validation_report = {}
        for name, model in (
            ("v2_gaussian_nb", nb_model),
            ("v2_random_forest", forest_model),
        ):
            v2_validation_report[name] = _classification_report(
                v2_validation,
                {
                    sample.source_index: max(
                        model.probabilities(sample.features), key=model.probabilities(sample.features).get
                    )
                    for sample in v2_validation
                },
            )

        test_samples = [
            all_samples_v1[index]
            for index in range(train_end, test_end - 3)
            if index in all_samples_v1
        ]
        predictions = {name: {} for name in candidate_names}
        signals = {name: {} for name in candidate_names}
        ema_signals = {}

        for index in range(train_end, test_end - 1):
            sample_v1 = all_samples_v1.get(index)
            sample_v2 = all_samples_v2.get(index)
            if sample_v1 is None or sample_v2 is None:
                continue
            features_v1 = sample_v1.features
            features_v2 = sample_v2.features
            for name, model in models.items():
                features = features_v1 if name == "v1_logistic" else features_v2
                probabilities = model.probabilities(features)
                predicted = max(probabilities, key=probabilities.get)
                predictions[name][index] = predicted
                confidence = probabilities[predicted]
                signals[name][index] = (
                    predicted if predicted in (-1, 1) and confidence >= min_confidence else 0
                )
            ema_signals[index] = 1 if features_v1[4] > 0 else -1

        class_report = {
            name: _classification_report(
                test_samples, predictions[name]
            )
            for name in candidate_names
        }
        support = {
            label: sum(s.label == label for s in v1_samples)
            for label in (-1, 0, 1)
        }
        majority = max((-1, 0, 1), key=lambda label: support[label])
        strategies = {
            name: _trade_simulation(
                candles, signals[name], start_index=train_end, end_index=test_end,
                costs=costs,
            )
            for name in candidate_names
        }
        strategies["training_majority_class"] = _trade_simulation(
            candles,
            {i: majority for i in range(train_end, test_end - 1)},
            start_index=train_end, end_index=test_end, costs=costs,
        )
        strategies["buy_and_hold_long"] = _trade_simulation(
            candles,
            {i: 1 for i in range(train_end, test_end - 1)},
            start_index=train_end, end_index=test_end, costs=costs,
        )
        strategies["ema_8_21_trend"] = _trade_simulation(
            candles, ema_signals, start_index=train_end, end_index=test_end, costs=costs,
        )
        strategies["always_flat"] = _trade_simulation(
            candles, {}, start_index=train_end, end_index=test_end, costs=costs,
        )
        stress = TradingCosts(
            spread_bps_per_side=costs.spread_bps_per_side * 2,
            commission_bps_per_side=costs.commission_bps_per_side * 2,
            slippage_bps_per_side=costs.slippage_bps_per_side * 2,
        )
        for name in candidate_names:
            strategies[name + "_double_cost_stress"] = _trade_simulation(
                candles, signals[name], start_index=train_end, end_index=test_end,
                costs=stress,
            )

        folds.append({
            "fold": len(folds) + 1,
            "train_start": str(history[0]["timestamp"]),
            "train_end": str(history[-1]["timestamp"]),
            "test_start": str(candles[train_end]["timestamp"]),
            "test_end": str(candles[test_end - 1]["timestamp"]),
            "training_bars": train_end,
            "test_bars": test_end - train_end,
            "v2_train_rows": len(v2_train),
            "v2_validation_rows": len(v2_validation),
            "v2_validation_metrics_not_used_for_outer_fit": v2_validation_report,
            "out_of_sample_classification": class_report,
            "strategies": strategies,
        })
        train_end = test_end

    if not folds:
        raise ValueError("no complete V2 walk-forward folds were evaluated")

    aggregate = {
        name: _aggregate_folds(folds, name)
        for name in strategy_names
    }
    for name in candidate_names:
        stress_name = name + "_double_cost_stress"
        aggregate[stress_name] = _aggregate_folds(folds, stress_name)

    return {
        "status": "RESEARCH_ONLY",
        "trading_authorized": False,
        "model_version": "APEX V2 candidates compared with V1 logistic baseline",
        "method": "five-fold expanding-window outer walk-forward; candidate models refit before each unseen block",
        "configuration": {
            "initial_train_bars": initial_train_bars,
            "test_bars": test_bars,
            "max_folds": max_folds,
            "minimum_directional_confidence": min_confidence,
            "trees": trees,
            "tree_depth": 3,
            "random_forest_seed": 271828,
            "costs": {
                "spread_bps_per_side": costs.spread_bps_per_side,
                "commission_bps_per_side": costs.commission_bps_per_side,
                "slippage_bps_per_side": costs.slippage_bps_per_side,
            },
        },
        "aggregate_strategies": aggregate,
        "folds": folds,
        "limitations": [
            "V2 candidates are deliberately compact Gaussian naive Bayes and shallow random forest research baselines, not deep learning.",
            "V2 feature set adds only causal historical features; public Yahoo candles may still differ from broker bid/ask quotes.",
            "Costs are illustrative assumptions, not verified broker prices.",
            "The simulator uses 1x unlevered notional and does not model contract sizes, leverage, margin, swaps, financing, liquidation, partial fills or market impact.",
            "No model is selected or approved for execution from these results.",
            "Repeated tuning against these same outer folds would invalidate them as independent confirmation.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="APEX V2 outer walk-forward model comparison")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--symbol", default="EURUSD=X")
    parser.add_argument("--report-dir", default="artifacts/forex-v2-backtests")
    parser.add_argument("--initial-train-bars", type=int, default=3000)
    parser.add_argument("--test-bars", type=int, default=1800)
    parser.add_argument("--max-folds", type=int, default=5)
    parser.add_argument("--min-confidence", type=float, default=0.45)
    parser.add_argument("--spread-bps-per-side", type=float, default=0.8)
    parser.add_argument("--commission-bps-per-side", type=float, default=0.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=0.2)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--trees", type=int, default=13)
    args = parser.parse_args(argv)
    candles = load_history(args.csv)
    report = walk_forward_v2(
        candles,
        initial_train_bars=args.initial_train_bars,
        test_bars=args.test_bars,
        max_folds=args.max_folds,
        min_confidence=args.min_confidence,
        costs=TradingCosts(
            spread_bps_per_side=args.spread_bps_per_side,
            commission_bps_per_side=args.commission_bps_per_side,
            slippage_bps_per_side=args.slippage_bps_per_side,
        ),
        epochs=args.epochs,
        trees=args.trees,
    )
    report["symbol"] = args.symbol
    report["dataset_file"] = args.csv
    destination = Path(args.report_dir)
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / f"{safe_symbol_name(args.symbol)}_v2_walk_forward.json"
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
