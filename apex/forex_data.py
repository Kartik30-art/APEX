"""Historical Forex dataset collection and validation.

Yahoo Finance's public chart endpoint is a free, best-effort source. It is
unofficial, may be delayed/rate-limited, and is not an execution feed.
"""
from __future__ import annotations

import csv
import json
import math
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

SUPPORTED_SYMBOLS = {
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "AUDUSD=X": "AUD/USD",
    "NZDUSD=X": "NZD/USD",
}
SUPPORTED_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"}
INTERVAL_SECONDS = {"1h": 3600, "1d": 86400}
CSV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def _validate_request(symbol: str, period: str, interval: str) -> None:
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f"unsupported Forex symbol: {symbol}")
    if period not in SUPPORTED_PERIODS:
        raise ValueError(f"unsupported period: {period}")
    if interval not in INTERVAL_SECONDS:
        raise ValueError("interval must be 1h or 1d")
    if interval == "1h" and period in {"5y", "10y", "max"}:
        raise ValueError("Yahoo hourly history is limited; use 2y or less for 1h data")


def _valid_bar(bar: dict) -> bool:
    try:
        values = [float(bar[key]) for key in ("open", "high", "low", "close")]
        volume = float(bar.get("volume", 0) or 0)
    except (KeyError, TypeError, ValueError):
        return False
    if not all(math.isfinite(value) and value > 0 for value in values):
        return False
    if not math.isfinite(volume) or volume < 0:
        return False
    opened, high, low, close = values
    return high >= max(opened, close, low) and low <= min(opened, close, high)


def fetch_yahoo_history(
    symbol: str,
    *,
    period: str = "2y",
    interval: str = "1h",
    timeout: int = 20,
) -> list[dict]:
    """Download completed historical OHLCV candles from Yahoo's public endpoint."""
    _validate_request(symbol, period, interval)
    if timeout < 1 or timeout > 120:
        raise ValueError("timeout must be between 1 and 120 seconds")

    query = urllib.parse.urlencode({
        "range": period,
        "interval": interval,
        "events": "history",
        "includeAdjustedClose": "false",
    })
    ticker = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{query}"
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 APEX-research/1.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    chart = payload.get("chart") or {}
    result = chart.get("result") or []
    if not result:
        error = chart.get("error") or {}
        raise RuntimeError(error.get("description") or "Yahoo returned no historical data")

    item = result[0]
    timestamps = item.get("timestamp") or []
    quotes = (item.get("indicators") or {}).get("quote") or []
    if not timestamps or not quotes:
        raise RuntimeError("Yahoo response did not contain OHLCV candles")

    quote = quotes[0]
    now = datetime.now(timezone.utc)
    duration = INTERVAL_SECONDS[interval]
    bars = []
    for index, stamp in enumerate(timestamps):
        try:
            values = {
                key: (quote.get(key) or [None] * len(timestamps))[index]
                for key in ("open", "high", "low", "close")
            }
            if any(value is None for value in values.values()):
                continue
            timestamp = datetime.fromtimestamp(int(stamp), timezone.utc)
            if timestamp + timedelta(seconds=duration) > now:
                continue
            bar = {
                "timestamp": timestamp.isoformat(),
                **{key: float(value) for key, value in values.items()},
                "volume": float((quote.get("volume") or [0] * len(timestamps))[index] or 0),
            }
            if _valid_bar(bar):
                bars.append(bar)
        except (IndexError, TypeError, ValueError, OverflowError):
            continue

    bars.sort(key=lambda row: row["timestamp"])
    deduplicated = {row["timestamp"]: row for row in bars}
    output = [deduplicated[key] for key in sorted(deduplicated)]
    if len(output) < 300:
        raise RuntimeError(
            f"Only {len(output)} completed candles were returned; at least 300 are required"
        )
    return output


def validate_history(bars: Iterable[dict]) -> list[dict]:
    """Validate, normalize and chronologically order a candle collection."""
    normalized = []
    for index, original in enumerate(bars):
        bar = dict(original)
        try:
            timestamp = datetime.fromisoformat(
                str(bar["timestamp"]).replace("Z", "+00:00")
            )
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError("timestamp must include a timezone")
            timestamp = timestamp.astimezone(timezone.utc)
            row = {
                "timestamp": timestamp.isoformat(),
                "open": float(bar["open"]),
                "high": float(bar["high"]),
                "low": float(bar["low"]),
                "close": float(bar["close"]),
                "volume": float(bar.get("volume", 0) or 0),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid candle at row {index}: {exc}") from exc
        if not _valid_bar(row):
            raise ValueError(f"invalid OHLCV values at row {index}")
        normalized.append(row)

    normalized.sort(key=lambda row: row["timestamp"])
    result = []
    previous = None
    for row in normalized:
        if row["timestamp"] == previous:
            raise ValueError(f"duplicate candle timestamp: {row['timestamp']}")
        result.append(row)
        previous = row["timestamp"]
    if len(result) < 2:
        raise ValueError("at least two candles are required")
    return result


def safe_symbol_name(symbol: str) -> str:
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f"unsupported Forex symbol: {symbol}")
    return re.sub(r"[^A-Za-z0-9]+", "_", symbol).strip("_")


def save_history(
    bars: Iterable[dict],
    output_path: str | Path,
    *,
    symbol: str,
    interval: str,
    period: str,
    source: str = "Yahoo Finance public chart endpoint (unofficial)",
) -> dict:
    _validate_request(symbol, period, interval)
    rows = validate_history(bars)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(destination)

    manifest = {
        "symbol": symbol,
        "display_symbol": SUPPORTED_SYMBOLS[symbol],
        "interval": interval,
        "requested_period": period,
        "source": source,
        "source_is_official_or_licensed": False,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "first_timestamp": rows[0]["timestamp"],
        "last_timestamp": rows[-1]["timestamp"],
        "csv_file": destination.name,
    }
    manifest_path = destination.with_suffix(destination.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_history(path: str | Path) -> list[dict]:
    source = Path(path)
    with source.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = set(CSV_COLUMNS[:5]) - set(reader.fieldnames or [])
        if missing:
            raise ValueError("CSV is missing required columns: " + ", ".join(sorted(missing)))
        bars = []
        for row in reader:
            bars.append({
                "timestamp": row["timestamp"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row.get("volume") or 0,
            })
    return validate_history(bars)
