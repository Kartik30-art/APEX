"""APEX V3: validation-only calibration and conservative signal selection.

This is a research-only experiment. It deliberately has no order-routing code.
The default date lock keeps its daily holdout before 2024-10-01, separate from
APEX V2's recent two-year hourly evaluation period.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Sequence

from .forex_backtest import TradingCosts, _aggregate_folds, _classification_report, _trade_simulation
from .forex_data import load_history, safe_symbol_name
from .forex_ml import Sample
from .forex_models_v2 import (
    build_v2_samples,
    features_at_v2,
    fit_gaussian_nb,
    fit_random_forest,
    save_v2_model,
)


DEFAULT_THRESHOLDS = (0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70)
DEFAULT_TEMPERATURES = tuple(round(0.50 + i * 0.05, 2) for i in range(51))
CLASSES = (-1, 0, 1)
HORIZON_BARS = 3


def apply_temperature(probabilities: dict[int, float], temperature: float) -> dict[int, float]:
    """Apply multiclass temperature scaling without changing model parameters."""
    if not math.isfinite(temperature) or not 0.25 <= temperature <= 4.0:
        raise ValueError("temperature must be finite and between 0.25 and 4.0")
    if set(probabilities) != set(CLASSES):
        raise ValueError("probabilities must contain sell, hold and buy classes")
    values = [float(probabilities[label]) for label in CLASSES]
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError("class probabilities must be finite and non-negative")
    total = sum(values)
    if total <= 0:
        raise ValueError("class probabilities must have positive total")
    logits = [math.log(max(value / total, 1e-12)) / temperature for value in values]
    peak = max(logits)
    exps = [math.exp(max(-700.0, value - peak)) for value in logits]
    denominator = sum(exps)
    return {label: exps[i] / denominator for i, label in enumerate(CLASSES)}


def multiclass_probability_metrics(
    samples: Sequence[Sample],
    probabilities_by_index: dict[int, dict[int, float]],
) -> dict:
    """Return NLL, multiclass Brier score and top-label expected calibration error."""
    if not samples:
        raise ValueError("at least one sample is required for probability metrics")
    nll = 0.0
    brier = 0.0
    bins = [{"count": 0, "confidence": 0.0, "accuracy": 0.0} for _ in range(10)]
    for sample in samples:
        probs = probabilities_by_index[sample.source_index]
        predicted = max(CLASSES, key=lambda label: probs[label])
        confidence = probs[predicted]
        nll -= math.log(max(probs[sample.label], 1e-12))
        brier += sum((probs[label] - float(sample.label == label)) ** 2 for label in CLASSES)
        bucket = min(9, int(confidence * 10))
        bins[bucket]["count"] += 1
        bins[bucket]["confidence"] += confidence
        bins[bucket]["accuracy"] += float(predicted == sample.label)
    count = len(samples)
    ece = 0.0
    bin_report = []
    for index, bucket in enumerate(bins):
        size = bucket["count"]
        if size:
            avg_confidence = bucket["confidence"] / size
            avg_accuracy = bucket["accuracy"] / size
            ece += (size / count) * abs(avg_confidence - avg_accuracy)
            bin_report.append({
                "bin": index,
                "rows": size,
                "mean_confidence": avg_confidence,
                "accuracy": avg_accuracy,
            })
    return {
        "rows": count,
        "log_loss": nll / count,
        "multiclass_brier_score": brier / count,
        "expected_calibration_error_10_bins": ece,
        "reliability_bins": bin_report,
    }


def fit_temperature(
    model,
    calibration_samples: Sequence[Sample],
    *,
    candidates: Sequence[float] = DEFAULT_TEMPERATURES,
) -> dict:
    """Choose temperature using only a chronological calibration segment."""
    if len(calibration_samples) < 30:
        raise ValueError("at least 30 calibration samples are required")
    if not candidates:
        raise ValueError("temperature candidate grid cannot be empty")
    raw = {
        sample.source_index: model.probabilities(sample.features)
        for sample in calibration_samples
    }
    best = None
    for temperature in candidates:
        if not math.isfinite(temperature) or not 0.25 <= temperature <= 4.0:
            raise ValueError("temperature candidates must be in [0.25, 4.0]")
        loss = 0.0
        for sample in calibration_samples:
            calibrated = apply_temperature(raw[sample.source_index], temperature)
            loss -= math.log(max(calibrated[sample.label], 1e-12))
        loss /= len(calibration_samples)
        candidate = (loss, abs(temperature - 1.0), temperature)
        if best is None or candidate < best:
            best = candidate
    assert best is not None
    return {
        "temperature": best[2],
        "calibration_fit_log_loss": best[0],
        "calibration_rows": len(calibration_samples),
        "method": "bounded multiclass temperature scaling; chronological calibration segment only",
    }


def _probabilities_for_samples(model, samples: Sequence[Sample], temperature: float) -> dict[int, dict[int, float]]:
    return {
        sample.source_index: apply_temperature(
            model.probabilities(sample.features), temperature
        )
        for sample in samples
    }


def _signal_for_probability(probabilities: dict[int, float], threshold: float) -> int:
    """Require a directional class to beat hold and clear the confidence gate."""
    direction = max((-1, 1), key=lambda label: probabilities[label])
    if probabilities[direction] > probabilities[0] and probabilities[direction] >= threshold:
        return direction
    return 0


def _signals_from_probabilities(
    probabilities_by_index: dict[int, dict[int, float]],
    threshold: float,
) -> dict[int, int]:
    return {
        index: _signal_for_probability(probabilities, threshold)
        for index, probabilities in probabilities_by_index.items()
    }


def select_threshold(
    candles: Sequence[dict],
    selection_samples: Sequence[Sample],
    probabilities_by_index: dict[int, dict[int, float]],
    *,
    costs: TradingCosts,
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
    min_trades: int = 10,
    drawdown_penalty: float = 0.25,
) -> dict:
    """Select a confidence gate on a separate pre-test threshold-selection segment."""
    if len(selection_samples) < 30:
        raise ValueError("at least 30 threshold-selection samples are required")
    if min_trades < 1:
        raise ValueError("min_trades must be positive")
    if not math.isfinite(drawdown_penalty) or drawdown_penalty < 0:
        raise ValueError("drawdown_penalty must be finite and non-negative")
    start_index = selection_samples[0].source_index
    end_index = selection_samples[-1].source_index + 2
    if end_index > len(candles):
        raise ValueError("selection window exceeds candle history")

    candidates = []
    for threshold in sorted(set(float(value) for value in thresholds)):
        if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            raise ValueError("thresholds must be between 0 and 1")
        signals = _signals_from_probabilities(probabilities_by_index, threshold)
        simulation = _trade_simulation(
            candles, signals, start_index=start_index, end_index=end_index, costs=costs
        )
        if simulation["trade_count"] < min_trades:
            continue
        objective = (
            simulation["net_return_fraction"]
            - drawdown_penalty * simulation["max_drawdown_fraction"]
        )
        candidates.append({
            "threshold": threshold,
            "objective": objective,
            "net_return_fraction": simulation["net_return_fraction"],
            "max_drawdown_fraction": simulation["max_drawdown_fraction"],
            "trade_count": simulation["trade_count"],
            "win_rate": simulation["win_rate"],
        })

    # Flat is a valid outcome and wins whenever every eligible strategy has
    # a non-positive validation objective. No threshold is then carried forward.
    best = max(candidates, key=lambda row: (row["objective"], row["threshold"])) if candidates else None
    if best is None or best["objective"] <= 0.0:
        return {
            "threshold": None,
            "decision": "NO_TRADE",
            "objective": 0.0,
            "validation_trade_count": 0,
            "validation_net_return_fraction": 0.0,
            "validation_max_drawdown_fraction": 0.0,
            "minimum_validation_trades": min_trades,
            "candidate_results": candidates,
        }
    return {
        "threshold": best["threshold"],
        "decision": "THRESHOLD_SELECTED",
        "objective": best["objective"],
        "validation_trade_count": best["trade_count"],
        "validation_net_return_fraction": best["net_return_fraction"],
        "validation_max_drawdown_fraction": best["max_drawdown_fraction"],
        "validation_win_rate": best["win_rate"],
        "minimum_validation_trades": min_trades,
        "candidate_results": candidates,
    }


def _strategy_metrics(candles, signals, start_index, end_index, costs):
    return _trade_simulation(
        candles, signals, start_index=start_index, end_index=end_index, costs=costs
    )


def walk_forward_v3(
    candles: list[dict],
    *,
    initial_train_bars: int = 750,
    test_bars: int = 250,
    max_folds: int = 5,
    locked_test_end: str = "2024-10-01",
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
    min_validation_trades: int = 10,
    costs: TradingCosts = TradingCosts(),
    trees: int = 13,
    model_dir: str | Path | None = None,
    symbol: str = "EURUSD=X",
) -> dict:
    """Run V3 on a date-locked daily dataset with purged chronological sub-splits."""
    if initial_train_bars < 500 or test_bars < 100:
        raise ValueError("initial_train_bars must be >= 500 and test_bars >= 100")
    if max_folds < 1 or max_folds > 20:
        raise ValueError("max_folds must be between 1 and 20")
    if not locked_test_end or len(locked_test_end) < 10:
        raise ValueError("locked_test_end must be an ISO date or timestamp")
    candles = [row for row in candles if str(row["timestamp"]) < locked_test_end]
    if len(candles) <= initial_train_bars + 100:
        raise ValueError("not enough pre-lock candles for V3 walk-forward evaluation")

    all_samples = {
        sample.source_index: sample for sample in build_v2_samples(candles)
    }
    folds = []
    train_end = initial_train_bars
    final_models = {}
    final_metadata = {}
    strategy_names = (
        "v2_gaussian_nb_raw_045",
        "v3_gaussian_nb_calibrated_045",
        "v3_gaussian_nb_selected",
        "v2_random_forest_raw_045",
        "v3_random_forest_calibrated_045",
        "v3_random_forest_selected",
        "always_flat",
    )

    while train_end < len(candles) and len(folds) < max_folds:
        test_end = min(train_end + test_bars, len(candles))
        if test_end - train_end < 100:
            break

        # Labels are only available when the full three-bar forward horizon
        # remains inside the current training history.
        history_samples = [
            all_samples[index]
            for index in sorted(all_samples)
            if index < train_end - HORIZON_BARS
        ]
        count = len(history_samples)
        fit_boundary = int(count * 0.60)
        calibration_boundary = int(count * 0.80)
        fit_samples = history_samples[:fit_boundary - HORIZON_BARS]
        calibration_samples = history_samples[
            fit_boundary:calibration_boundary - HORIZON_BARS
        ]
        selection_samples = history_samples[calibration_boundary:]

        if min(len(fit_samples), len(calibration_samples), len(selection_samples)) < 30:
            raise ValueError("insufficient data for V3 fit/calibration/selection segments")
        if len(fit_samples) < 100:
            raise ValueError("V3 model-fitting segment must contain at least 100 samples")
        if fit_samples[-1].source_index + HORIZON_BARS >= calibration_samples[0].source_index:
            raise ValueError("label leakage across fit/calibration boundary")
        if calibration_samples[-1].source_index + HORIZON_BARS >= selection_samples[0].source_index:
            raise ValueError("label leakage across calibration/selection boundary")
        if selection_samples[-1].source_index + HORIZON_BARS >= train_end:
            raise ValueError("label leakage from threshold selection into outer test")

        models = {
            "v2_gaussian_nb": fit_gaussian_nb(fit_samples),
            "v2_random_forest": fit_random_forest(fit_samples, n_trees=trees),
        }
        temperatures = {}
        threshold_choices = {}
        selection_diagnostics = {}
        calibration_diagnostics = {}
        selection_probabilities = {}

        for name, model in models.items():
            calibration = fit_temperature(model, calibration_samples)
            temperatures[name] = calibration
            calibrated_calibration = _probabilities_for_samples(
                model, calibration_samples, calibration["temperature"]
            )
            calibration_diagnostics[name] = multiclass_probability_metrics(
                calibration_samples, calibrated_calibration
            )
            selection_probabilities[name] = _probabilities_for_samples(
                model, selection_samples, calibration["temperature"]
            )
            threshold_choices[name] = select_threshold(
                candles, selection_samples, selection_probabilities[name],
                costs=costs, thresholds=thresholds,
                min_trades=min_validation_trades,
            )
            selection_diagnostics[name] = multiclass_probability_metrics(
                selection_samples, selection_probabilities[name]
            )

        start_index = train_end
        end_index = test_end
        test_samples = [
            all_samples[index]
            for index in sorted(all_samples)
            if train_end <= index < test_end - HORIZON_BARS
        ]
        predictions = {}
        test_probabilities = {}
        strategy_signals = {
            "v2_gaussian_nb_raw_045": {},
            "v3_gaussian_nb_calibrated_045": {},
            "v3_gaussian_nb_selected": {},
            "v2_random_forest_raw_045": {},
            "v3_random_forest_calibrated_045": {},
            "v3_random_forest_selected": {},
        }

        test_samples_by_index = {sample.source_index: sample for sample in test_samples}
        for index in range(train_end, test_end - 1):
            sample = all_samples.get(index)
            features = sample.features if sample is not None else features_at_v2(candles, index)
            for name, model in models.items():
                raw = model.probabilities(features)
                calibrated = apply_temperature(raw, temperatures[name]["temperature"])
                predicted = max(CLASSES, key=lambda label: calibrated[label])
                predictions.setdefault(name, {})[index] = predicted
                if index in test_samples_by_index:
                    test_probabilities.setdefault(name, {})[index] = calibrated
                legacy_name = (
                    "v2_gaussian_nb_raw_045" if name == "v2_gaussian_nb"
                    else "v2_random_forest_raw_045"
                )
                calibrated_name = (
                    "v3_gaussian_nb_calibrated_045" if name == "v2_gaussian_nb"
                    else "v3_random_forest_calibrated_045"
                )
                selected_name = (
                    "v3_gaussian_nb_selected" if name == "v2_gaussian_nb"
                    else "v3_random_forest_selected"
                )
                strategy_signals[legacy_name][index] = _signal_for_probability(raw, 0.45)
                strategy_signals[calibrated_name][index] = _signal_for_probability(calibrated, 0.45)
                chosen_threshold = threshold_choices[name]["threshold"]
                strategy_signals[selected_name][index] = (
                    _signal_for_probability(calibrated, chosen_threshold)
                    if chosen_threshold is not None else 0
                )

        test_probability_metrics = {
            name: multiclass_probability_metrics(test_samples, test_probabilities[name])
            for name in models
        }
        class_report = {
            name: _classification_report(test_samples, {
                sample.source_index: predictions[name][sample.source_index]
                for sample in test_samples
            })
            for name in models
        }
        strategies = {
            name: _strategy_metrics(candles, signals, start_index, end_index, costs)
            for name, signals in strategy_signals.items()
        }
        strategies["always_flat"] = _strategy_metrics(
            candles, {}, start_index, end_index, costs
        )
        stress = TradingCosts(
            spread_bps_per_side=costs.spread_bps_per_side * 2,
            commission_bps_per_side=costs.commission_bps_per_side * 2,
            slippage_bps_per_side=costs.slippage_bps_per_side * 2,
        )
        for name in ("v3_gaussian_nb_selected", "v3_random_forest_selected"):
            strategies[name + "_double_cost_stress"] = _strategy_metrics(
                candles, strategy_signals[name], start_index, end_index, stress
            )

        fold = {
            "fold": len(folds) + 1,
            "fit_start": str(candles[fit_samples[0].source_index]["timestamp"]),
            "fit_end": str(candles[fit_samples[-1].source_index]["timestamp"]),
            "calibration_start": str(candles[calibration_samples[0].source_index]["timestamp"]),
            "calibration_end": str(candles[calibration_samples[-1].source_index]["timestamp"]),
            "threshold_selection_start": str(candles[selection_samples[0].source_index]["timestamp"]),
            "threshold_selection_end": str(candles[selection_samples[-1].source_index]["timestamp"]),
            "outer_test_start": str(candles[train_end]["timestamp"]),
            "outer_test_end": str(candles[test_end - 1]["timestamp"]),
            "training_history_rows": count,
            "fit_rows": len(fit_samples),
            "calibration_rows": len(calibration_samples),
            "threshold_selection_rows": len(selection_samples),
            "purge_horizon_bars": HORIZON_BARS,
            "temperature_fit": temperatures,
            "calibration_segment_diagnostics": calibration_diagnostics,
            "threshold_selection": threshold_choices,
            "threshold_selection_segment_diagnostics": selection_diagnostics,
            "outer_test_probability_metrics": test_probability_metrics,
            "outer_test_classification": class_report,
            "strategies": strategies,
        }
        folds.append(fold)
        final_models = models
        final_metadata = {
            name: {
                "temperature": temperatures[name],
                "threshold_selection": threshold_choices[name],
            }
            for name in models
        }
        train_end = test_end

    if not folds:
        raise ValueError("no complete V3 outer test folds were evaluated")

    aggregate_names = strategy_names + (
        "v3_gaussian_nb_selected_double_cost_stress",
        "v3_random_forest_selected_double_cost_stress",
    )
    aggregate = {name: _aggregate_folds(folds, name) for name in aggregate_names}

    model_artifacts = {}
    if model_dir is not None:
        destination = Path(model_dir)
        destination.mkdir(parents=True, exist_ok=True)
        base = safe_symbol_name(symbol)
        for name, model in final_models.items():
            model_path = destination / f"{base}_{name}_v3_base.json"
            save_v2_model(model, model_path)
            metadata_path = destination / f"{base}_{name}_v3_calibration.json"
            payload = {
                "model_version": "APEX V3 research calibration",
                "research_only": True,
                "trading_authorized": False,
                "base_model_file": model_path.name,
                **final_metadata[name],
            }
            metadata_path.write_text(
                json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8"
            )
            model_artifacts[name] = {
                "base_model": str(model_path),
                "calibration_and_selection": str(metadata_path),
            }

    return {
        "status": "RESEARCH_ONLY",
        "trading_authorized": False,
        "model_version": "APEX V3 chronological calibration and confidence selection",
        "dataset_frequency": "daily",
        "locked_test_end_exclusive": locked_test_end,
        "outer_test_period_is_disjoint_from_v2_recent_hourly_window": True,
        "method": (
            "Expanding outer walk-forward; each fold uses disjoint chronological fit, "
            "temperature-calibration and threshold-selection segments with a three-bar purge; "
            "the next outer block is not used for fitting or selection."
        ),
        "configuration": {
            "initial_train_bars": initial_train_bars,
            "test_bars": test_bars,
            "max_folds": max_folds,
            "threshold_grid": list(thresholds),
            "minimum_validation_trades": min_validation_trades,
            "temperature_grid": list(DEFAULT_TEMPERATURES),
            "trees": trees,
            "tree_depth": 3,
            "random_forest_seed": 271828,
            "drawdown_penalty_in_validation_objective": 0.25,
            "costs": {
                "spread_bps_per_side": costs.spread_bps_per_side,
                "commission_bps_per_side": costs.commission_bps_per_side,
                "slippage_bps_per_side": costs.slippage_bps_per_side,
            },
        },
        "aggregate_strategies": aggregate,
        "folds": folds,
        "model_artifacts": model_artifacts,
        "limitations": [
            "The locked daily test period is a different frequency and earlier calendar period than V2's recent hourly evaluation; this improves date separation but does not prove intraday performance.",
            "Threshold selection is an inner validation procedure and can still overfit its finite selection segment; minimum-trade gating and the flat fallback reduce but do not remove that risk.",
            "Temperature scaling adjusts class probabilities only; it does not create predictive information or guarantee calibration stability across market regimes.",
            "Yahoo Finance public history is unofficial, may be revised or incomplete, and is not a broker quote feed.",
            "Costs are illustrative assumptions, not verified broker prices; swaps, rollover, margin, liquidity, partial fills and market impact are omitted.",
            "A three-daily-bar label horizon is not equivalent to an intraday strategy horizon.",
            "No model is selected or approved for demo or live execution; artifacts remain research-only.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="APEX V3 date-locked calibration experiment")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--symbol", default="EURUSD=X")
    parser.add_argument("--report-dir", default="artifacts/forex-v3-backtests")
    parser.add_argument("--initial-train-bars", type=int, default=750)
    parser.add_argument("--test-bars", type=int, default=250)
    parser.add_argument("--max-folds", type=int, default=5)
    parser.add_argument("--locked-test-end", default="2024-10-01")
    parser.add_argument("--min-validation-trades", type=int, default=10)
    parser.add_argument("--trees", type=int, default=13)
    parser.add_argument("--spread-bps-per-side", type=float, default=0.8)
    parser.add_argument("--commission-bps-per-side", type=float, default=0.0)
    parser.add_argument("--slippage-bps-per-side", type=float, default=0.2)
    args = parser.parse_args(argv)

    candles = load_history(args.csv)
    report = walk_forward_v3(
        candles,
        initial_train_bars=args.initial_train_bars,
        test_bars=args.test_bars,
        max_folds=args.max_folds,
        locked_test_end=args.locked_test_end,
        min_validation_trades=args.min_validation_trades,
        costs=TradingCosts(
            spread_bps_per_side=args.spread_bps_per_side,
            commission_bps_per_side=args.commission_bps_per_side,
            slippage_bps_per_side=args.slippage_bps_per_side,
        ),
        trees=args.trees,
        model_dir=Path(args.report_dir) / "models",
        symbol=args.symbol,
    )
    report["symbol"] = args.symbol
    report["dataset_file"] = args.csv
    destination = Path(args.report_dir)
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / f"{safe_symbol_name(args.symbol)}_v3_walk_forward.json"
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
