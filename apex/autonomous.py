"""Autonomous demo-only Forex research and paper-trading agent.

Uses Yahoo Finance public chart history as an unlicensed, best-effort research source.
No broker connectivity, live orders, paid API calls, or external LLM calls exist here.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from apex.shadow import ShadowLedger

WATCHLIST = {
    "EURUSD=X": "EUR/USD",
    "GBPUSD=X": "GBP/USD",
    "AUDUSD=X": "AUD/USD",
    "NZDUSD=X": "NZD/USD",
}
INTERVAL = "15m"
BAR_SECONDS = 900
SCAN_SECONDS = max(120, int(os.getenv("APEX_AGENT_SCAN_SECONDS", "300")))
STARTING_BALANCE = Decimal(os.getenv("APEX_DEMO_STARTING_BALANCE", "10000"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ema(values: list[float], period: int) -> float:
    alpha = 2.0 / (period + 1)
    value = values[0]
    for item in values[1:]:
        value = alpha * item + (1 - alpha) * value
    return value


def _indicators(bars: list[dict]) -> dict[str, float]:
    closes = [float(x["close"]) for x in bars]
    highs = [float(x["high"]) for x in bars]
    lows = [float(x["low"]) for x in bars]
    if len(closes) < 30:
        raise ValueError("At least 30 completed candles are required")
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(x, 0.0) for x in changes[-14:]]
    losses = [max(-x, 0.0) for x in changes[-14:]]
    avg_gain = sum(gains) / 14
    avg_loss = sum(losses) / 14
    rsi = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    true_ranges = []
    for i in range(1, len(bars)):
        true_ranges.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    atr = sum(true_ranges[-14:]) / 14
    return {
        "ema_fast": _ema(closes[-60:], 9),
        "ema_slow": _ema(closes[-120:], 21),
        "rsi": rsi,
        "atr": atr,
        "momentum_3": (closes[-1] / closes[-4] - 1) * 100,
        "price": closes[-1],
    }


def fetch_yahoo_bars(symbol: str) -> list[dict]:
    """Fetch recent 15-minute bars. Yahoo's public endpoint is unofficial and may change."""
    query = urllib.parse.urlencode({"range": "5d", "interval": INTERVAL, "events": "history"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 APEX-demo-research/1.0"})
    with urllib.request.urlopen(req, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload.get("chart", {}).get("result")
    if not result:
        error = payload.get("chart", {}).get("error") or {}
        raise RuntimeError(error.get("description") or "No market data returned")
    item = result[0]
    timestamps = item.get("timestamp") or []
    quote = (item.get("indicators", {}).get("quote") or [{}])[0]
    bars = []
    for i, stamp in enumerate(timestamps):
        values = [quote.get(k, [None] * len(timestamps))[i] for k in ("open", "high", "low", "close")]
        if any(v is None for v in values):
            continue
        when = datetime.fromtimestamp(stamp, timezone.utc)
        # Exclude the still-forming candle.
        if when + timedelta(seconds=BAR_SECONDS) > _now():
            continue
        o, h, low, close = map(float, values)
        if min(o, h, low, close) <= 0 or h < max(o, close, low) or low > min(o, close):
            continue
        bars.append({"timestamp": when.isoformat(), "open": o, "high": h, "low": low, "close": close})
    if len(bars) < 30:
        raise RuntimeError("Provider returned fewer than 30 completed candles")
    age = (_now() - datetime.fromisoformat(bars[-1]["timestamp"])).total_seconds()
    if age > 3600:
        age_minutes = int(age // 60)
        if _now().weekday() in (5, 6):
            raise RuntimeError(f"Forex market is closed for the weekend; latest completed candle is {age_minutes} minutes old. Trading is paused until fresh market data returns.")
        raise RuntimeError(f"Latest completed candle is stale ({age_minutes} minutes old); trading is paused until fresh data returns.")
    return bars[-240:]


class AutonomousDemoAgent:
    """Background scanner; all orders are simulated and persisted in SQLite."""

    def __init__(self, database_path: str | Path):
        self.path = str(database_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._bars: dict[str, list[dict]] = {}
        self._status: dict[str, Any] = {
            "state": "starting", "message": "Waiting for first market scan",
            "last_scan": None, "source": "Yahoo Finance public chart endpoint (unofficial)",
            "mode": "DEMO_ONLY", "live_trading_enabled": False,
        }
        self._events: list[dict] = []
        self._init_db()
        self.shadow = ShadowLedger(self.path)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        return db

    def _init_db(self):
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS agent_account (
                id INTEGER PRIMARY KEY CHECK(id=1),
                starting_balance TEXT NOT NULL,
                balance TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_trades (
                id TEXT PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL,
                quantity TEXT NOT NULL, entry_price TEXT NOT NULL, stop_price TEXT NOT NULL,
                target_price TEXT NOT NULL, exit_price TEXT, status TEXT NOT NULL,
                opened_at TEXT NOT NULL, closed_at TEXT, pnl TEXT NOT NULL DEFAULT '0',
                reason TEXT NOT NULL
            );
            """)
            db.execute(
                "INSERT OR IGNORE INTO agent_account(id,starting_balance,balance,updated_at) VALUES(1,?,?,?)",
                (str(STARTING_BALANCE), str(STARTING_BALANCE), _now().isoformat()),
            )

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="apex-demo-agent", daemon=True)
            self._thread.start()
            self._event("system", "Autonomous demo agent started; live trading is disabled.")

    def stop(self):
        self._stop.set()
        with self._lock:
            self._status["state"] = "stopping"
        return self.snapshot()

    def _event(self, kind: str, message: str, **extra):
        with self._lock:
            self._events.insert(0, {"time": _now().isoformat(), "type": kind, "message": message, **extra})
            del self._events[100:]

    def _account(self):
        with self._connect() as db:
            row = db.execute("SELECT * FROM agent_account WHERE id=1").fetchone()
            trades = db.execute("SELECT * FROM agent_trades ORDER BY opened_at DESC").fetchall()
        balance = Decimal(row["balance"])
        open_trades = [dict(x) for x in trades if x["status"] == "open"]
        closed = [dict(x) for x in trades if x["status"] == "closed"]
        unrealized = Decimal("0")
        for trade in open_trades:
            bars = self._bars.get(trade["symbol"])
            if bars:
                price = Decimal(str(bars[-1]["close"]))
                direction = Decimal("1") if trade["side"] == "buy" else Decimal("-1")
                unrealized += (price - Decimal(trade["entry_price"])) * Decimal(trade["quantity"]) * direction
        return {
            "starting_balance": row["starting_balance"], "balance": str(balance),
            "unrealized_pnl": str(unrealized), "equity": str(balance + unrealized),
            "open_trades": open_trades, "closed_trades": closed[:30],
            "trade_count": len(trades),
        }

    def _close(self, trade: sqlite3.Row | dict, price: float, reason: str):
        entry = Decimal(trade["entry_price"])
        qty = Decimal(trade["quantity"])
        direction = Decimal("1") if trade["side"] == "buy" else Decimal("-1")
        pnl = (Decimal(str(price)) - entry) * qty * direction
        with self._connect() as db:
            db.execute("UPDATE agent_trades SET status='closed',exit_price=?,closed_at=?,pnl=? WHERE id=? AND status='open'",
                       (str(price), _now().isoformat(), str(pnl), trade["id"]))
            row = db.execute("SELECT balance FROM agent_account WHERE id=1").fetchone()
            new_balance = Decimal(row["balance"]) + pnl
            db.execute("UPDATE agent_account SET balance=?,updated_at=? WHERE id=1",
                       (str(new_balance), _now().isoformat()))
        self._event("trade_closed", f"{trade['symbol']} {trade['side']} closed at {price:.6f}: {reason}", pnl=str(pnl))

    def _manage_open(self, symbol: str, bars: list[dict]):
        with self._connect() as db:
            trades = [dict(x) for x in db.execute("SELECT * FROM agent_trades WHERE status='open'").fetchall()]
        last = bars[-1]
        for trade in trades:
            if trade["symbol"] != symbol:
                continue
            stop, target = float(trade["stop_price"]), float(trade["target_price"])
            side = trade["side"]
            # Conservative ordering: if both levels occur in one candle, assume stop first.
            if side == "buy" and last["low"] <= stop:
                self._close(trade, stop, "stop loss")
            elif side == "sell" and last["high"] >= stop:
                self._close(trade, stop, "stop loss")
            elif side == "buy" and last["high"] >= target:
                self._close(trade, target, "take profit")
            elif side == "sell" and last["low"] <= target:
                self._close(trade, target, "take profit")

    def _scan_symbol(self, ticker: str, label: str):
        bars = fetch_yahoo_bars(ticker)
        indicators = _indicators(bars)
        self._bars[label] = bars
        self._manage_open(label, bars)
        fast, slow, rsi, mom = (indicators[k] for k in ("ema_fast", "ema_slow", "rsi", "momentum_3"))
        side = None
        reason = "No qualifying setup; monitoring"
        if fast > slow and 52 <= rsi <= 68 and mom > 0:
            side, reason = "buy", "EMA 9 above EMA 21; RSI confirms bullish momentum"
        elif fast < slow and 32 <= rsi <= 48 and mom < 0:
            side, reason = "sell", "EMA 9 below EMA 21; RSI confirms bearish momentum"
        score = min(100.0, abs((fast / slow - 1) * 10000) * 2 + abs(mom) * 4 + abs(rsi - 50) * 0.5)
        # Record a heuristic signal for observation only; this never routes an order.
        self.shadow.observe(label, side or "neutral", bars[-1]["timestamp"],
                            indicators["price"], reason)
        return {"symbol": label, "ticker": ticker, "price": indicators["price"],
                "ema_fast": fast, "ema_slow": slow, "rsi": rsi, "atr": indicators["atr"],
                "momentum_3": mom, "score": round(score, 2), "signal": side or "neutral",
                "reason": reason, "bars": len(bars), "last_bar": bars[-1]["timestamp"]}

    def _maybe_open(self, ranked: list[dict]):
        with self._connect() as db:
            exists = db.execute("SELECT 1 FROM agent_trades WHERE status='open' LIMIT 1").fetchone()
            account = db.execute("SELECT balance FROM agent_account WHERE id=1").fetchone()
        if exists:
            return
        candidates = [x for x in ranked if x["signal"] in {"buy", "sell"}]
        if not candidates:
            return
        best = max(candidates, key=lambda x: x["score"])
        entry, atr = float(best["price"]), float(best["atr"])
        if atr <= 0:
            return
        side = best["signal"]
        stop_distance = atr * 1.5
        stop = entry - stop_distance if side == "buy" else entry + stop_distance
        target = entry + stop_distance * 2 if side == "buy" else entry - stop_distance * 2
        equity = Decimal(account["balance"])
        risk_cash = equity * Decimal("0.005")
        qty_by_risk = risk_cash / Decimal(str(stop_distance))
        max_notional_qty = equity * Decimal("5") / Decimal(str(entry))
        quantity = min(qty_by_risk, max_notional_qty)
        if quantity <= 0:
            return
        trade_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("""INSERT INTO agent_trades
                (id,symbol,side,quantity,entry_price,stop_price,target_price,status,opened_at,reason)
                VALUES(?,?,?,?,?,?,?,'open',?,?)""",
                (trade_id, best["symbol"], side, str(quantity), str(entry), str(stop), str(target),
                 _now().isoformat(), best["reason"]))
        self._event("trade_opened", f"DEMO {side.upper()} {best['symbol']} at {entry:.6f}; stop {stop:.6f}; target {target:.6f}", trade_id=trade_id)

    def scan_once(self) -> dict:
        ranked, errors = [], []
        for ticker, label in WATCHLIST.items():
            try:
                ranked.append(self._scan_symbol(ticker, label))
            except Exception as exc:
                errors.append({"symbol": label, "error": f"{type(exc).__name__}: {exc}"})
                # Surface a concise provider reason in the authenticated dashboard timeline.
                detail = str(exc).replace("\\n", " ")[:180]
                self._event("data_error", f"{label}: {type(exc).__name__} — {detail}")
        ranked.sort(key=lambda x: x["score"], reverse=True)
        self._maybe_open(ranked)
        with self._lock:
            self._status.update({
                "state": "running" if ranked else ("waiting_for_data" if errors else "scanning"),
                "message": f"Scanned {len(ranked)} of {len(WATCHLIST)} assets",
                "last_scan": _now().isoformat(), "ranked_assets": ranked,
                "errors": errors, "source": "Yahoo Finance public chart endpoint (unofficial)",
                "interval": INTERVAL, "scan_interval_seconds": SCAN_SECONDS,
                "mode": "DEMO_ONLY", "live_trading_enabled": False,
            })
        return self.snapshot()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as exc:
                with self._lock:
                    self._status.update({"state": "error", "message": f"Scan failed: {type(exc).__name__}"})
                self._event("agent_error", f"Scan failed: {type(exc).__name__}")
            self._stop.wait(SCAN_SECONDS)

    def add_demo_funds(self, amount: str) -> dict:
        value = Decimal(str(amount))
        if not value.is_finite() or value <= 0 or value > Decimal("100000000"):
            raise ValueError("Demo-fund request must be between 0 and 100,000,000")
        with self._connect() as db:
            row = db.execute("SELECT balance FROM agent_account WHERE id=1").fetchone()
            new_balance = Decimal(row["balance"]) + value
            db.execute("UPDATE agent_account SET balance=?,updated_at=? WHERE id=1",
                       (str(new_balance), _now().isoformat()))
        self._event("demo_funds", f"Added {value} virtual demo funds; no real money was moved.")
        return self._account()

    def snapshot(self):
        with self._lock:
            status = dict(self._status)
            status["ranked_assets"] = list(status.get("ranked_assets", []))
            status["errors"] = list(status.get("errors", []))
            events = list(self._events)
        account = self._account()
        return {**status, "account": account, "events": events,
                "shadow": self.shadow.summary(limit=50),
                "watchlist": list(WATCHLIST.values()), "live_trading_enabled": False}

    def chart(self, symbol: str):
        if symbol not in WATCHLIST.values():
            raise ValueError("Symbol is not in the agent watchlist")
        bars = self._bars.get(symbol, [])
        return {"symbol": symbol, "interval": INTERVAL, "bars": bars,
                "source": "Yahoo Finance public chart endpoint (unofficial)"}
