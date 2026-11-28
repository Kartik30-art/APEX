"""Auditable Forex ML research model and chronological evaluation.

Uses only the Python standard library. Trains a three-class multinomial
logistic-regression baseline (sell / hold / buy) on completed OHLCV candles.
This is a research artifact, not an execution signal.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

FEATURE_NAMES = (
    "return_1", "return_3", "return_6", "return_12", "ema_gap_8_21",
    "rsi_centered", "atr_fraction", "candle_body_fraction",
    "candle_range_fraction", "volatility_12",
)
CLASSES = (-1, 0, 1)
CLASS_NAMES = {"-1": "sell", "0": "hold", "1": "buy"}
MODEL_FORMAT_VERSION = 1


@dataclass(frozen=True)
class Sample:
    timestamp: str
    source_index: int
    features: tuple[float, ...]
    label: int
    forward_return: float


@dataclass(frozen=True)
class ForexLogisticModel:
    feature_names: tuple[str, ...]
    classes: tuple[int, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[tuple[float, ...], ...]
    biases: tuple[float, ...]
    horizon_bars: int
    min_move_bps: float
    created_at: str

    def probabilities(self, features: Sequence[float]) -> dict[int, float]:
        if len(features) != len(self.feature_names):
            raise ValueError("feature vector has the wrong size")
        standardized = [
            (float(value) - mean) / scale
            for value, mean, scale in zip(features, self.means, self.scales)
        ]
        logits = [
            bias + sum(weight * value for weight, value in zip(row, standardized))
            for row, bias in zip(self.weights, self.biases)
        ]
        peak = max(logits)
        exponents = [math.exp(max(-700.0, value - peak)) for value in logits]
        total = sum(exponents)
        return {label: value / total for label, value in zip(self.classes, exponents)}

    def predict(self, features: Sequence[float]) -> dict:
        probabilities = self.probabilities(features)
        predicted = max(probabilities, key=probabilities.get)
        return {
            "class": predicted,
            "signal": CLASS_NAMES[str(predicted)],
            "confidence": probabilities[predicted],
            "probabilities": {
                CLASS_NAMES[str(key)]: value for key, value in probabilities.items()
            },
            "research_only": True,
            "trading_authorized": False,
        }


def _ema(values: Sequence[float], period: int) -> float:
    alpha = 2.0 / (period + 1)
    value = values[0]
    for item in values[1:]:
        value = alpha * item + (1.0 - alpha) * value
    return value


def _features_at(candles: Sequence[dict], index: int) -> tuple[float, ...]:
    if index < 30:
        raise ValueError("at least 31 candles are required for feature warm-up")
    close = [float(row["close"]) for row in candles[: index + 1]]
    high = [float(row["high"]) for row in candles[: index + 1]]
    low = [float(row["low"]) for row in candles[: index + 1]]
    opened = float(candles[index]["open"])
    current = close[-1]

    def pct_change(period: int) -> float:
        return current / close[-period - 1] - 1.0

    fast_ema = _ema(close[-40:], 8)
    slow_ema = _ema(close[-105:], 21)
    changes = [
        close[i] / close[i - 1] - 1.0
        for i in range(len(close) - 14, len(close))
    ]
    gains = sum(max(change, 0.0) for change in changes) / 14
    losses = sum(max(-change, 0.0) for change in changes) / 14
    rsi = 100.0 if losses == 0 and gains > 0 else (
        50.0 if losses == 0 else 100.0 - 100.0 / (1.0 + gains / losses)
    )

    true_ranges = []
    for i in range(len(close) - 14, len(close)):
        true_ranges.append(max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        ))
    atr_fraction = (sum(true_ranges) / len(true_ranges)) / current
    last_returns = [
        close[i] / close[i - 1] - 1.0
        for i in range(len(close) - 12, len(close))
    ]
    mean_return = sum(last_returns) / len(last_returns)
    volatility = math.sqrt(
        sum((value - mean_return) ** 2 for value in last_returns) / len(last_returns)
    )
    candle_body = (current - opened) / opened
    candle_range = (float(candles[index]["high"]) - float(candles[index]["low"])) / current

    vector = (
        pct_change(1), pct_change(3), pct_change(6), pct_change(12),
        fast_ema / slow_ema - 1.0, (rsi - 50.0) / 50.0,
        atr_fraction, candle_body, candle_range, volatility,
    )
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("non-finite feature generated")
    return vector


def build_samples(
    candles: Sequence[dict],
    *,
    horizon_bars: int = 3,
    min_move_bps: float = 1.5,
) -> list[Sample]:
    if horizon_bars < 1 or horizon_bars > 48:
        raise ValueError("horizon_bars must be between 1 and 48")
    if not math.isfinite(min_move_bps) or min_move_bps < 0:
        raise ValueError("min_move_bps must be finite and non-negative")
    if len(candles) < 100:
        raise ValueError("at least 100 candles are required")
    samples = []
    final_index = len(candles) - horizon_bars
    for index in range(30, final_index):
        features = _features_at(candles, index)
        entry = float(candles[index]["close"])
        future = float(candles[index + horizon_bars]["close"])
        forward_return = future / entry - 1.0
        threshold = max(min_move_bps / 10000.0, features[6] * 0.5)
        label = 1 if forward_return > threshold else (-1 if forward_return < -threshold else 0)
        samples.append(Sample(
            timestamp=str(candles[index]["timestamp"]),
            source_index=index,
            features=features,
            label=label,
            forward_return=forward_return,
        ))
    return samples


def _softmax(logits: Sequence[float]) -> list[float]:
    peak = max(logits)
    values = [math.exp(max(-700.0, value - peak)) for value in logits]
    total = sum(values)
    return [value / total for value in values]


def _log_loss(
    data: Sequence[Sample],
    weights: Sequence[Sequence[float]],
    biases: Sequence[float],
    means: Sequence[float],
    scales: Sequence[float],
) -> float:
    total = 0.0
    for sample in data:
        x = [(v - m) / s for v, m, s in zip(sample.features, means, scales)]
        probs = _softmax([
            bias + sum(weight * value for weight, value in zip(row, x))
            for row, bias in zip(weights, biases)
        ])
        total -= math.log(max(probs[CLASSES.index(sample.label)], 1e-15))
    return total / len(data)


def _metrics(data: Sequence[Sample], model: ForexLogisticModel) -> dict:
    confusion = {
        str(actual): {str(predicted): 0 for predicted in CLASSES}
        for actual in CLASSES
    }
    correct = 0
    class_support = {label: 0 for label in CLASSES}
    predicted_counts = {label: 0 for label in CLASSES}
    for sample in data:
        probabilities = model.probabilities(sample.features)
        prediction = max(probabilities, key=probabilities.get)
        confusion[str(sample.label)][str(prediction)] += 1
        class_support[sample.label] += 1
        predicted_counts[prediction] += 1
        correct += int(prediction == sample.label)

    recalls = []
    f1_values = []
    for label in CLASSES:
        tp = confusion[str(label)][str(label)]
        fp = predicted_counts[label] - tp
        fn = class_support[label] - tp
        if class_support[label]:
            recalls.append(tp / class_support[label])
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1_values.append(
            2 * precision * recall / (precision + recall)
            if precision + recall else 0.0
        )
    majority = max(class_support.values()) / len(data)
    return {
        "rows": len(data),
        "accuracy": correct / len(data),
        "balanced_accuracy": sum(recalls) / len(recalls) if recalls else 0.0,
        "macro_f1": sum(f1_values) / len(f1_values),
        "majority_baseline_accuracy": majority,
        "class_support": {
            CLASS_NAMES[str(key)]: value for key, value in class_support.items()
        },
        "confusion_matrix_actual_rows_predicted_columns": confusion,
    }


def train_model(
    candles: Sequence[dict],
    *,
    model_path: str | Path | None = None,
    horizon_bars: int = 3,
    min_move_bps: float = 1.5,
    epochs: int = 150,
    learning_rate: float = 0.06,
    l2: float = 0.001,
    patience: int = 15,
) -> tuple[ForexLogisticModel, dict]:
    if epochs < 1 or epochs > 2000:
        raise ValueError("epochs must be between 1 and 2000")
    if not math.isfinite(learning_rate) or not 0 < learning_rate <= 1:
        raise ValueError("learning_rate must be between 0 and 1")
    if not math.isfinite(l2) or l2 < 0:
        raise ValueError("l2 must be finite and non-negative")
    if patience < 1:
        raise ValueError("patience must be positive")

    samples = build_samples(
        candles, horizon_bars=horizon_bars, min_move_bps=min_move_bps
    )
    count = len(samples)
    train_end = int(count * 0.70)
    validation_end = int(count * 0.85)
    train = samples[: train_end - horizon_bars]
    validation = samples[train_end : validation_end - horizon_bars]
    holdout = samples[validation_end:]
    if min(len(train), len(validation), len(holdout)) < 20:
        raise ValueError(
            "not enough samples for chronological train/validation/holdout splits; "
            "collect more historical candles"
        )
    counts = {
        label: sum(sample.label == label for sample in train)
        for label in CLASSES
    }
    if sum(value > 0 for value in counts.values()) < 2:
        raise ValueError("training data has insufficient class diversity")

    feature_count = len(FEATURE_NAMES)
    means = [
        sum(sample.features[j] for sample in train) / len(train)
        for j in range(feature_count)
    ]
    variances = [
        sum((sample.features[j] - means[j]) ** 2 for sample in train) / len(train)
        for j in range(feature_count)
    ]
    scales = [math.sqrt(value) if value > 1e-16 else 1.0 for value in variances]
    class_weights = {
        label: len(train) / (3 * max(1, counts[label]))
        for label in CLASSES
    }
    weights = [[0.0] * feature_count for _ in CLASSES]
    biases = [math.log(max(counts[label], 1) / len(train)) for label in CLASSES]
    best_weights = [row[:] for row in weights]
    best_biases = biases[:]
    best_loss = float("inf")
    best_epoch = 0
    stale_epochs = 0

    for epoch in range(1, epochs + 1):
        grad_w = [[0.0] * feature_count for _ in CLASSES]
        grad_b = [0.0] * len(CLASSES)
        total_weight = 0.0
        for sample in train:
            x = [
                (value - mean) / scale
                for value, mean, scale in zip(sample.features, means, scales)
            ]
            probabilities = _softmax([
                bias + sum(weight * value for weight, value in zip(row, x))
                for row, bias in zip(weights, biases)
            ])
            actual_index = CLASSES.index(sample.label)
            sample_weight = class_weights[sample.label]
            total_weight += sample_weight
            for class_index in range(len(CLASSES)):
                error = (
                    probabilities[class_index] - int(class_index == actual_index)
                ) * sample_weight
                grad_b[class_index] += error
                for feature_index, value in enumerate(x):
                    grad_w[class_index][feature_index] += error * value

        denominator = max(total_weight, 1e-12)
        for class_index in range(len(CLASSES)):
            biases[class_index] -= learning_rate * grad_b[class_index] / denominator
            for feature_index in range(feature_count):
                gradient = (
                    grad_w[class_index][feature_index] / denominator
                    + l2 * weights[class_index][feature_index]
                )
                weights[class_index][feature_index] -= learning_rate * gradient

        validation_loss = _log_loss(validation, weights, biases, means, scales)
        if validation_loss < best_loss - 1e-8:
            best_loss = validation_loss
            best_epoch = epoch
            best_weights = [row[:] for row in weights]
            best_biases = biases[:]
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= patience:
                break

    model = ForexLogisticModel(
        feature_names=FEATURE_NAMES,
        classes=CLASSES,
        means=tuple(means),
        scales=tuple(scales),
        weights=tuple(tuple(row) for row in best_weights),
        biases=tuple(best_biases),
        horizon_bars=horizon_bars,
        min_move_bps=min_move_bps,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    metrics = {
        "status": "RESEARCH_ONLY",
        "trading_authorized": False,
        "model": "multinomial_logistic_regression",
        "classes": {"sell": -1, "hold": 0, "buy": 1},
        "feature_names": list(FEATURE_NAMES),
        "sample_count": count,
        "splits": {
            "train_rows": len(train),
            "validation_rows": len(validation),
            "holdout_rows": len(holdout),
            "method": "chronological 70/15/15 with horizon purging",
        },
        "training": {
            "epochs_run": epoch,
            "best_epoch": best_epoch,
            "best_validation_log_loss": best_loss,
            "learning_rate": learning_rate,
            "l2": l2,
        },
        "train_class_distribution": {
            CLASS_NAMES[str(label)]: counts[label] for label in CLASSES
        },
        "validation": _metrics(validation, model),
        "holdout": _metrics(holdout, model),
        "warning": (
            "Research classification metrics only. This is not a profitability test; "
            "spread, commissions, swaps, financing, slippage and executable fills "
            "are not modeled. Do not connect this model to order execution."
        ),
    }
    if model_path is not None:
        save_model(model, model_path, metrics=metrics)
    return model, metrics


def predict_latest(model: ForexLogisticModel, candles: Sequence[dict]) -> dict:
    if len(candles) < 31:
        raise ValueError("at least 31 candles are required")
    result = model.predict(_features_at(candles, len(candles) - 1))
    result.update({
        "timestamp": str(candles[-1]["timestamp"]),
        "horizon_bars": model.horizon_bars,
        "model_created_at": model.created_at,
    })
    return result


def save_model(
    model: ForexLogisticModel,
    path: str | Path,
    *,
    metrics: dict | None = None,
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format_version": MODEL_FORMAT_VERSION,
        "created_at": model.created_at,
        "feature_names": list(model.feature_names),
        "classes": list(model.classes),
        "means": list(model.means),
        "scales": list(model.scales),
        "weights": [list(row) for row in model.weights],
        "biases": list(model.biases),
        "horizon_bars": model.horizon_bars,
        "min_move_bps": model.min_move_bps,
        "metrics": metrics,
        "research_only": True,
        "trading_authorized": False,
    }
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8"
    )
    temporary.replace(destination)


def load_model(path: str | Path) -> ForexLogisticModel:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("format_version") != MODEL_FORMAT_VERSION:
        raise ValueError("unsupported model artifact version")
    if payload.get("feature_names") != list(FEATURE_NAMES):
        raise ValueError("model feature schema does not match this APEX version")
    model = ForexLogisticModel(
        feature_names=tuple(payload["feature_names"]),
        classes=tuple(int(value) for value in payload["classes"]),
        means=tuple(float(value) for value in payload["means"]),
        scales=tuple(float(value) for value in payload["scales"]),
        weights=tuple(tuple(float(value) for value in row) for row in payload["weights"]),
        biases=tuple(float(value) for value in payload["biases"]),
        horizon_bars=int(payload["horizon_bars"]),
        min_move_bps=float(payload["min_move_bps"]),
        created_at=str(payload["created_at"]),
    )
    if len(model.classes) != 3 or len(model.weights) != 3 or len(model.biases) != 3:
        raise ValueError("invalid model dimensions")
    if any(scale <= 0 or not math.isfinite(scale) for scale in model.scales):
        raise ValueError("invalid model feature scaling")
    return model


def dataset_sha256(candles: Sequence[dict]) -> str:
    serialized = json.dumps(list(candles), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
