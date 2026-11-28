"""APEX Model V2: alternative, auditable classifiers and richer causal features.

The module deliberately has no broker/execution interfaces. All estimators are
small pure-Python research baselines so model comparison is reproducible and
requires no paid service or third-party ML dependency.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .forex_ml import (
    CLASSES,
    FEATURE_NAMES,
    Sample,
    _ema,
    _features_at,
)

FEATURE_NAMES_V2 = FEATURE_NAMES + (
    "ema_gap_21_55",
    "return_24",
    "return_48",
    "rsi_7_centered",
    "volatility_ratio_12_48",
    "close_location",
)
MODEL_V2_VERSION = 2


def features_at_v2(candles: Sequence[dict], index: int) -> tuple[float, ...]:
    """Build V2 features using only candles at or before index."""
    base = _features_at(candles, index)
    if index < 60:
        raise ValueError("V2 features require at least 61 candles")
    close = [float(row["close"]) for row in candles[: index + 1]]
    high = [float(row["high"]) for row in candles[: index + 1]]
    low = [float(row["low"]) for row in candles[: index + 1]]
    current = close[-1]

    ema_21 = _ema(close[-110:], 21)
    ema_55 = _ema(close[-275:], 55)
    ema_gap_21_55 = ema_21 / ema_55 - 1.0
    return_24 = current / close[-25] - 1.0
    return_48 = current / close[-49] - 1.0

    changes_7 = [
        close[i] / close[i - 1] - 1.0
        for i in range(len(close) - 7, len(close))
    ]
    gains = sum(max(value, 0.0) for value in changes_7) / 7
    losses = sum(max(-value, 0.0) for value in changes_7) / 7
    rsi_7 = 100.0 if losses == 0 and gains > 0 else (
        50.0 if losses == 0 else 100.0 - 100.0 / (1.0 + gains / losses)
    )

    returns_12 = [
        close[i] / close[i - 1] - 1.0
        for i in range(len(close) - 12, len(close))
    ]
    returns_48 = [
        close[i] / close[i - 1] - 1.0
        for i in range(len(close) - 48, len(close))
    ]
    mean_12 = sum(returns_12) / len(returns_12)
    mean_48 = sum(returns_48) / len(returns_48)
    vol_12 = math.sqrt(sum((v - mean_12) ** 2 for v in returns_12) / len(returns_12))
    vol_48 = math.sqrt(sum((v - mean_48) ** 2 for v in returns_48) / len(returns_48))
    volatility_ratio = vol_12 / max(vol_48, 1e-12)

    bar_range = high[-1] - low[-1]
    close_location = (
        (2.0 * current - high[-1] - low[-1]) / bar_range
        if bar_range > 0 else 0.0
    )
    result = base + (
        ema_gap_21_55,
        return_24,
        return_48,
        (rsi_7 - 50.0) / 50.0,
        volatility_ratio,
        close_location,
    )
    if len(result) != len(FEATURE_NAMES_V2) or not all(math.isfinite(v) for v in result):
        raise ValueError("invalid V2 feature vector")
    return result


def build_v2_samples(
    candles: Sequence[dict],
    *,
    horizon_bars: int = 3,
    min_move_bps: float = 1.5,
) -> list[Sample]:
    """Reuse Step 1 labels; replace features with the expanded causal feature set."""
    from .forex_ml import build_samples

    base_samples = build_samples(
        candles, horizon_bars=horizon_bars, min_move_bps=min_move_bps
    )
    return [
        Sample(
            timestamp=sample.timestamp,
            source_index=sample.source_index,
            features=features_at_v2(candles, sample.source_index),
            label=sample.label,
            forward_return=sample.forward_return,
        )
        for sample in base_samples
    ]


@dataclass(frozen=True)
class GaussianNBV2:
    feature_names: tuple[str, ...]
    means: tuple[tuple[float, ...], ...]
    variances: tuple[tuple[float, ...], ...]
    priors: tuple[float, ...]
    created_at: str
    model_name: str = "v2_gaussian_naive_bayes"

    def probabilities(self, features: Sequence[float]) -> dict[int, float]:
        if len(features) != len(self.feature_names):
            raise ValueError("feature vector has the wrong size")
        log_scores = []
        for class_index, label in enumerate(CLASSES):
            score = math.log(max(self.priors[class_index], 1e-15))
            for value, mean, variance in zip(
                features, self.means[class_index], self.variances[class_index]
            ):
                variance = max(variance, 1e-12)
                delta = float(value) - mean
                score -= 0.5 * (math.log(2.0 * math.pi * variance) + delta * delta / variance)
            log_scores.append(score)
        peak = max(log_scores)
        exp_values = [math.exp(max(-700.0, value - peak)) for value in log_scores]
        total = sum(exp_values)
        return {label: value / total for label, value in zip(CLASSES, exp_values)}


@dataclass(frozen=True)
class ForestNode:
    feature: int
    threshold: float
    probabilities: tuple[float, float, float]
    left: "ForestNode | None" = None
    right: "ForestNode | None" = None


@dataclass(frozen=True)
class RandomForestV2:
    feature_names: tuple[str, ...]
    trees: tuple[ForestNode, ...]
    created_at: str
    model_name: str = "v2_random_forest"

    def probabilities(self, features: Sequence[float]) -> dict[int, float]:
        if len(features) != len(self.feature_names):
            raise ValueError("feature vector has the wrong size")
        totals = [0.0, 0.0, 0.0]
        for tree in self.trees:
            node = tree
            while node.feature >= 0:
                if node.left is None or node.right is None:
                    raise ValueError("invalid forest tree node")
                node = node.left if float(features[node.feature]) <= node.threshold else node.right
            for i, probability in enumerate(node.probabilities):
                totals[i] += probability
        count = max(len(self.trees), 1)
        result = [value / count for value in totals]
        return {label: result[i] for i, label in enumerate(CLASSES)}


def fit_gaussian_nb(samples: Sequence[Sample]) -> GaussianNBV2:
    if len(samples) < 30:
        raise ValueError("at least 30 training samples are required")
    width = len(FEATURE_NAMES_V2)
    if any(len(sample.features) != width for sample in samples):
        raise ValueError("Gaussian NB requires V2 feature vectors")
    global_means = [
        sum(sample.features[j] for sample in samples) / len(samples)
        for j in range(width)
    ]
    global_variances = [
        sum((sample.features[j] - global_means[j]) ** 2 for sample in samples) / len(samples)
        for j in range(width)
    ]
    means = []
    variances = []
    priors = []
    for label in CLASSES:
        group = [sample for sample in samples if sample.label == label]
        if not group:
            raise ValueError(f"training set is missing class {label}")
        class_means = [
            sum(sample.features[j] for sample in group) / len(group)
            for j in range(width)
        ]
        class_variances = [
            sum((sample.features[j] - class_means[j]) ** 2 for sample in group) / len(group)
            for j in range(width)
        ]
        means.append(tuple(class_means))
        variances.append(tuple(
            max(class_variances[j], global_variances[j] * 0.01, 1e-12)
            for j in range(width)
        ))
        priors.append((len(group) + 1.0) / (len(samples) + 3.0))
    return GaussianNBV2(
        feature_names=FEATURE_NAMES_V2,
        means=tuple(means),
        variances=tuple(variances),
        priors=tuple(priors),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _class_probabilities(samples: Sequence[Sample]) -> tuple[float, float, float]:
    counts = [sum(sample.label == label for sample in samples) for label in CLASSES]
    total = len(samples) + len(CLASSES)
    return tuple((count + 1.0) / total for count in counts)


def _gini(samples: Sequence[Sample]) -> float:
    if not samples:
        return 0.0
    probs = _class_probabilities(samples)
    return 1.0 - sum(value * value for value in probs)


def _fit_tree(
    samples: Sequence[Sample],
    *,
    rng: random.Random,
    depth: int,
    max_depth: int,
    min_leaf: int,
    max_features: int,
) -> ForestNode:
    node_probabilities = _class_probabilities(samples)
    leaf = ForestNode(-1, 0.0, node_probabilities)
    if depth >= max_depth or len(samples) < 2 * min_leaf or _gini(samples) < 1e-9:
        return leaf

    feature_count = len(FEATURE_NAMES_V2)
    candidate_features = rng.sample(
        range(feature_count), k=min(max_features, feature_count)
    )
    parent_impurity = _gini(samples)
    best_score = float("inf")
    best_split = None
    for feature in candidate_features:
        values = sorted(sample.features[feature] for sample in samples)
        thresholds = []
        for fraction in (0.25, 0.5, 0.75):
            position = min(len(values) - 1, max(0, int((len(values) - 1) * fraction)))
            threshold = values[position]
            if values[0] < threshold < values[-1] and threshold not in thresholds:
                thresholds.append(threshold)
        for threshold in thresholds:
            left = [sample for sample in samples if sample.features[feature] <= threshold]
            right = [sample for sample in samples if sample.features[feature] > threshold]
            if len(left) < min_leaf or len(right) < min_leaf:
                continue
            score = (
                len(left) * _gini(left) + len(right) * _gini(right)
            ) / len(samples)
            gain = parent_impurity - score
            if gain > 1e-10 and score < best_score:
                best_score = score
                best_split = (feature, threshold, left, right)

    if best_split is None:
        return leaf
    feature, threshold, left_samples, right_samples = best_split
    return ForestNode(
        feature=feature,
        threshold=threshold,
        probabilities=node_probabilities,
        left=_fit_tree(
            left_samples, rng=rng, depth=depth + 1, max_depth=max_depth,
            min_leaf=min_leaf, max_features=max_features,
        ),
        right=_fit_tree(
            right_samples, rng=rng, depth=depth + 1, max_depth=max_depth,
            min_leaf=min_leaf, max_features=max_features,
        ),
    )


def fit_random_forest(
    samples: Sequence[Sample],
    *,
    n_trees: int = 13,
    max_depth: int = 3,
    min_leaf: int = 35,
    max_features: int = 4,
    seed: int = 271828,
) -> RandomForestV2:
    if len(samples) < 100:
        raise ValueError("at least 100 training samples are required")
    if n_trees < 3 or n_trees > 101 or max_depth < 1 or max_depth > 8:
        raise ValueError("invalid random forest size or depth")
    if min_leaf < 5 or max_features < 1:
        raise ValueError("invalid random forest split constraints")
    if any(len(sample.features) != len(FEATURE_NAMES_V2) for sample in samples):
        raise ValueError("random forest requires V2 feature vectors")

    rng = random.Random(seed)
    trees = []
    for _ in range(n_trees):
        bootstrap = [samples[rng.randrange(len(samples))] for _ in range(len(samples))]
        trees.append(_fit_tree(
            bootstrap, rng=rng, depth=0, max_depth=max_depth,
            min_leaf=min_leaf, max_features=max_features,
        ))
    return RandomForestV2(
        feature_names=FEATURE_NAMES_V2,
        trees=tuple(trees),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def save_v2_model(model, path: str | Path) -> None:
    """Write an explicit research-only artifact for later inspection."""
    def node_payload(node: ForestNode) -> dict:
        return {
            "feature": node.feature,
            "threshold": node.threshold,
            "probabilities": list(node.probabilities),
            "left": node_payload(node.left) if node.left else None,
            "right": node_payload(node.right) if node.right else None,
        }

    if isinstance(model, GaussianNBV2):
        payload = {
            "format_version": MODEL_V2_VERSION,
            "model": model.model_name,
            "feature_names": list(model.feature_names),
            "means": [list(row) for row in model.means],
            "variances": [list(row) for row in model.variances],
            "priors": list(model.priors),
            "created_at": model.created_at,
        }
    elif isinstance(model, RandomForestV2):
        payload = {
            "format_version": MODEL_V2_VERSION,
            "model": model.model_name,
            "feature_names": list(model.feature_names),
            "trees": [node_payload(tree) for tree in model.trees],
            "created_at": model.created_at,
        }
    else:
        raise TypeError("unsupported V2 model type")
    payload.update({"research_only": True, "trading_authorized": False})
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8"
    )
    temporary.replace(destination)
