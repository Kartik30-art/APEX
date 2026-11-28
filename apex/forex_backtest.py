"""Walk-forward Forex ML strategy evaluation with explicit friction assumptions.

Signals are computed from completed candles and filled at the next bar open.
All simulated exposure is capped at 1x notional. This is research only; it is
not a broker valuation or a recommendation to trade.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .forex_ml import (
    CLASS_NAMES,
    CLASSES,
    Sample,
    _features_at,
    build_samples,
    train_model,
)


@dataclass(frozen=True)
class TradingCosts:
    spread_bps_per_side: float = 0.8
    commission_bps_per_side: float = 0.0
    slippage_bps_per_side: float = 0.2

    def __post_init__(self):
        values = (
            self.spread_bps_per_side,
            self.commission_bps_per_side,
            self.slippage_bps_per_side,
        )
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("trading costs must be finite and non-negative")
        if sum(values) >= 1000:
            raise ValueError("combined one-side trading costs are unreasonably large")

    @property
    def total_per_side_bps(self) -> float:
        return (
            self.spread_bps_per_side
            + self.commission_bps_per_side
            + self.slippage_bps_per_side
        )


def _trade_simulation(
    candles: Sequence[dict],
    signals: dict[int, int],
    *,
    start_index: int,
    end_index: int,
    costs: TradingCosts,
    initial_equity: float = 10_000.0,
) -> dict:
    if not (31 <= start_index < end_index <= len(candles)):
        raise ValueError("invalid test window")
    if not math.isfinite(initial_equity) or initial_equity <= 0:
        raise ValueError("initial_equity must be finite and positive")
    for index, side in signals.items():
        if not isinstance(index, int) or side not in (-1, 0, 1):
            raise ValueError("signals must map candle indices to -1, 0 or 1")

    equity = initial_equity
    peak = initial_equity
    max_drawdown = 0.0
    cost_fraction = 2.0 * costs.total_per_side_bps / 10_000.0
    position = None
    trades = []
    marked_equity = []

    def close_position(exit_price: float, exit_time: str, reason: str):
        nonlocal equity, position
        direction = position["side"]
        gross_return = direction * (exit_price / position["entry_price"] - 1.0)
        net_return = gross_return - cost_fraction
        before = equity
        equity = max(0.0, equity * (1.0 + net_return))
        trades.append({
            "side": "buy" if direction == 1 else "sell",
            "entry_time": position["entry_time"],
            "exit_time": exit_time,
            "entry_price": position["entry_price"],
            "exit_price": exit_price,
            "gross_return_fraction": gross_return,
            "estimated_round_trip_cost_fraction": cost_fraction,
            "net_return_fraction": net_return,
            "equity_before": before,
            "equity_after": equity,
            "exit_reason": reason,
        })
        position = None

    # A signal at candle i can only be filled at candle i+1 open.
    for signal_index in range(start_index, end_index - 1):
        fill_index = signal_index + 1
        fill_bar = candles[fill_index]
        desired = signals.get(signal_index, 0)
        fill_price = float(fill_bar["open"])

        if position is not None and desired != position["side"]:
            close_position(fill_price, str(fill_bar["timestamp"]), "signal_change")

        if position is None and desired != 0:
            position = {
                "side": desired,
                "entry_price": fill_price,
                "entry_time": str(fill_bar["timestamp"]),
            }

        mark_price = float(fill_bar["close"])
        current_equity = equity
        if position is not None:
            unrealized = position["side"] * (
                mark_price / position["entry_price"] - 1.0
            )
            current_equity = max(0.0, equity * (1.0 + unrealized - cost_fraction))
        peak = max(peak, current_equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - current_equity) / peak)
        marked_equity.append(current_equity)

    if position is not None:
        final_bar = candles[end_index - 1]
        close_position(
            float(final_bar["close"]),
            str(final_bar["timestamp"]),
            "end_of_test_window",
        )
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak)

    wins = sum(1 for trade in trades if trade["net_return_fraction"] > 0)
    net_wins = sum(
        trade["net_return_fraction"]
        for trade in trades if trade["net_return_fraction"] > 0
    )
    net_losses = -sum(
        trade["net_return_fraction"]
        for trade in trades if trade["net_return_fraction"] < 0
    )
    return {
        "initial_equity": initial_equity,
        "final_equity": equity,
        "net_pnl": equity - initial_equity,
        "net_return_fraction": equity / initial_equity - 1.0,
        "max_drawdown_fraction": max_drawdown,
        "trade_count": len(trades),
        "win_rate": wins / len(trades) if trades else 0.0,
        "profit_factor": net_wins / net_losses if net_losses > 0 else None,
        "trades": trades,
        "assumptions": {
            "spread_bps_per_side": costs.spread_bps_per_side,
            "commission_bps_per_side": costs.commission_bps_per_side,
            "slippage_bps_per_side": costs.slippage_bps_per_side,
            "execution": "completed-candle signal; next-candle open fill",
            "exposure": "maximum 1.0x unlevered notional; no margin model",
            "financing": "swap, rollover, funding and overnight financing omitted",
            "fill_model": "OHLC next-open approximation; no gaps beyond observed open, partial fills or market impact",
        },
    }


def _classification_report(
    samples: Sequence[Sample],
    predictions: dict[int, int],
) -> dict:
    confusion = {
        str(actual): {str(predicted): 0 for predicted in CLASSES}
        for actual in CLASSES
    }
    support = {label: 0 for label in CLASSES}
    predicted_count = {label: 0 for label in CLASSES}
    correct = 0
    for sample in samples:
        predicted = predictions[sample.source_index]
        confusion[str(sample.label)][str(predicted)] += 1
        support[sample.label] += 1
        predicted_count[predicted] += 1
        correct += int(predicted == sample.label)

    recalls = []
    f1s = []
    for label in CLASSES:
        tp = confusion[str(label)][str(label)]
        fp = predicted_count[label] - tp
        fn = support[label] - tp
        if support[label]:
            recalls.append(tp / support[label])
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(
            2.0 * precision * recall / (precision + recall)
            if precision + recall else 0.0
        )
    majority_label = max(CLASSES, key=lambda label: support[label])
    return {
        "rows": len(samples),
        "accuracy": correct / len(samples) if samples else 0.0,
        "balanced_accuracy": sum(recalls) / len(recalls) if recalls else 0.0,
        "macro_f1": sum(f1s) / len(f1s) if f1s else 0.0,
        "majority_class_accuracy": support[majority_label] / len(samples) if samples else 0.0,
        "majority_class": CLASS_NAMES[str(majority_label)],
        "confusion_matrix_actual_rows_predicted_columns": confusion,
    }


def _aggregate_folds(folds: list[dict], strategy: str) -> dict:
    equity = 10_000.0
    for fold in folds:
        equity *= 1.0 + fold["strategies"][strategy]["net_return_fraction"]
    returns = [fold["strategies"][strategy]["net_return_fraction"] for fold in folds]
    return {
        "folds": len(folds),
        "combined_compounded_return_fraction": equity / 10_000.0 - 1.0,
        "average_fold_return_fraction": sum(returns) / len(returns) if returns else 0.0,
        "positive_folds": sum(value > 0 for value in returns),
        "total_trades": sum(fold["strategies"][strategy]["trade_count"] for fold in folds),
        "worst_fold_drawdown_fraction": max(
            (fold["strategies"][strategy]["max_drawdown_fraction"] for fold in folds),
            default=0.0,
        ),
    }


def walk_forward_ml_backtest(
    candles: Sequence[dict],
    *,
    initial_train_bars: int = 3000,
    test_bars: int = 1800,
    max_folds: int = 5,
    horizon_bars: int = 3,
    min_move_bps: float = 1.5,
    min_confidence: float = 0.45,
    epochs: int = 100,
    learning_rate: float = 0.06,
    l2: float = 0.001,
    patience: int = 12,
    costs: TradingCosts = TradingCosts(),
    initial_equity: float = 10_000.0,
) -> dict:
    """Retrain on expanding history, then test only on the following unseen block."""
    if initial_train_bars < 500 or test_bars < 100:
        raise ValueError("initial_train_bars must be >= 500 and test_bars >= 100")
    if max_folds < 1 or max_folds > 20:
        raise ValueError("max_folds must be between 1 and 20")
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence must be between 0 and 1")
    if len(candles) <= initial_train_bars + 100:
        raise ValueError("not enough history for the requested walk-forward evaluation")

    all_samples = build_samples(
        candles, horizon_bars=horizon_bars, min_move_bps=min_move_bps
    )
    by_index = {sample.source_index: sample for sample in all_samples}
    folds = []
    train_end = initial_train_bars

    while train_end < len(candles) and len(folds) < max_folds:
        test_end = min(train_end + test_bars, len(candles))
        if test_end - train_end < 100:
            break

        history = candles[:train_end]
        model, training_report = train_model(
            history,
            horizon_bars=horizon_bars,
            min_move_bps=min_move_bps,
            epochs=epochs,
            learning_rate=learning_rate,
            l2=l2,
            patience=patience,
        )

        test_samples = [
            by_index[index]
            for index in range(train_end, test_end - horizon_bars)
            if index in by_index
        ]
        predictions = {}
        model_signals = {}
        for index in range(train_end, test_end - 1):
            probabilities = model.probabilities(_features_at(candles, index))
            predicted = max(probabilities, key=probabilities.get)
            confidence = probabilities[predicted]
            action = predicted if predicted in (-1, 1) and confidence >= min_confidence else 0
            predictions[index] = predicted
            model_signals[index] = action

        training_samples = build_samples(
            history,
            horizon_bars=horizon_bars,
            min_move_bps=min_move_bps,
        )
        train_support = {
            label: sum(sample.label == label for sample in training_samples)
            for label in CLASSES
        }
        majority_label = max(CLASSES, key=lambda label: train_support[label])
        model_report = _classification_report(test_samples, predictions)

        model_result = _trade_simulation(
            candles, model_signals, start_index=train_end, end_index=test_end,
            costs=costs, initial_equity=initial_equity,
        )
        majority_result = _trade_simulation(
            candles,
            {index: majority_label for index in range(train_end, test_end - 1)},
            start_index=train_end, end_index=test_end,
            costs=costs, initial_equity=initial_equity,
        )
        buy_hold_result = _trade_simulation(
            candles,
            {index: 1 for index in range(train_end, test_end - 1)},
            start_index=train_end, end_index=test_end,
            costs=costs, initial_equity=initial_equity,
        )
        flat_result = _trade_simulation(
            candles, {}, start_index=train_end, end_index=test_end,
            costs=costs, initial_equity=initial_equity,
        )
        stress_costs = TradingCosts(
            spread_bps_per_side=costs.spread_bps_per_side * 2.0,
            commission_bps_per_side=costs.commission_bps_per_side * 2.0,
            slippage_bps_per_side=costs.slippage_bps_per_side * 2.0,
        )
        stress_result = _trade_simulation(
            candles, model_signals, start_index=train_end, end_index=test_end,
            costs=stress_costs, initial_equity=initial_equity,
        )

        folds.append({
            "fold": len(folds) + 1,
            "train_start": str(history[0]["timestamp"]),
            "train_end": str(history[-1]["timestamp"]),
            "test_start": str(candles[train_end]["timestamp"]),
            "test_end": str(candles[test_end - 1]["timestamp"]),
            "training_history_bars": train_end,
            "test_bars": test_end - train_end,
            "training_inner_splits": training_report["splits"],
            "classification": model_report,
            "strategies": {
                "ml_model": model_result,
                "training_majority_class": majority_result,
                "buy_and_hold_long": buy_hold_result,
                "always_flat": flat_result,
                "ml_model_double_cost_stress": stress_result,
            },
        })
        train_end = test_end

    if not folds:
        raise ValueError("no complete walk-forward folds could be evaluated")

    strategy_names = (
        "ml_model",
        "training_majority_class",
        "buy_and_hold_long",
        "always_flat",
        "ml_model_double_cost_stress",
    )
    aggregate = {
        name: _aggregate_folds(folds, name)
        for name in strategy_names
    }
    total_classification_rows = sum(fold["classification"]["rows"] for fold in folds)
    weighted_accuracy = (
        sum(fold["classification"]["accuracy"] * fold["classification"]["rows"] for fold in folds)
        / total_classification_rows
        if total_classification_rows else 0.0
    )
    weighted_baseline = (
        sum(
            fold["classification"]["majority_class_accuracy"] * fold["classification"]["rows"]
            for fold in folds
        ) / total_classification_rows
        if total_classification_rows else 0.0
    )
    return {
        "status": "RESEARCH_ONLY",
        "trading_authorized": False,
        "method": "expanding-window walk-forward; retrain before each forward test block",
        "symbol_data_rows": len(candles),
        "configuration": {
            "initial_train_bars": initial_train_bars,
            "test_bars": test_bars,
            "max_folds": max_folds,
            "horizon_bars": horizon_bars,
            "min_move_bps": min_move_bps,
            "minimum_directional_confidence": min_confidence,
            "epochs": epochs,
            "starting_equity_per_fold": initial_equity,
            "costs": {
                "spread_bps_per_side": costs.spread_bps_per_side,
                "commission_bps_per_side": costs.commission_bps_per_side,
                "slippage_bps_per_side": costs.slippage_bps_per_side,
            },
        },
        "out_of_sample_classification": {
            "rows": total_classification_rows,
            "weighted_accuracy": weighted_accuracy,
            "weighted_majority_baseline_accuracy": weighted_baseline,
        },
        "aggregate_strategies": aggregate,
        "folds": folds,
        "limitations": [
            "Public Yahoo Finance history is unofficial and may differ from broker quotes.",
            "Spread, commission and slippage are explicit illustrative assumptions, not verified broker costs.",
            "No contract size, leverage, margin, liquidation, swaps, rollover, financing, market impact or partial fills are modeled.",
            "The simulator uses 1x unlevered notional and next-bar open fills; it is not MT5 account P&L.",
            "Fold returns are compounded across non-overlapping test windows; worst_fold_drawdown is the largest individual fold drawdown, not a continuous live equity curve.",
            "Repeated strategy/model changes after inspecting the same test results can create selection bias.",
        ],
    }
