"""Persistent one-bar shadow ledger. Records signals only; never creates orders."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class ShadowLedger:
    """Evaluate completed-candle signals against the next observed completed close."""

    def __init__(self, database_path: str | Path):
        self.path = str(database_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS shadow_predictions (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    signal TEXT NOT NULL CHECK(signal IN ('buy','sell','neutral')),
                    signal_time TEXT NOT NULL,
                    entry_price REAL NOT NULL CHECK(entry_price > 0),
                    exit_price REAL,
                    evaluated_at TEXT,
                    outcome TEXT,
                    return_pct REAL,
                    reason TEXT NOT NULL,
                    UNIQUE(symbol, signal_time)
                )
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        return db

    def observe(self, symbol: str, signal: str, signal_time: str,
                price: float, reason: str) -> dict:
        if signal not in {"buy", "sell", "neutral"}:
            raise ValueError("signal must be buy, sell, or neutral")
        if not symbol or not signal_time or not reason:
            raise ValueError("symbol, signal_time, and reason are required")
        price = float(price)
        if not price > 0 or price == float("inf") or price != price:
            raise ValueError("price must be finite and positive")
        now = datetime.now(timezone.utc).isoformat()
        evaluated = 0
        with self._connect() as db:
            pending = db.execute(
                "SELECT * FROM shadow_predictions WHERE symbol=? AND evaluated_at IS NULL AND signal_time < ?",
                (symbol, signal_time),
            ).fetchall()
            for row in pending:
                move = (price / row["entry_price"] - 1.0) * 100.0
                if row["signal"] == "buy":
                    outcome = "correct" if move > 0 else ("incorrect" if move < 0 else "flat")
                    signed_return = move
                elif row["signal"] == "sell":
                    outcome = "correct" if move < 0 else ("incorrect" if move > 0 else "flat")
                    signed_return = -move
                else:
                    outcome = "neutral"
                    signed_return = None
                db.execute("""
                    UPDATE shadow_predictions
                    SET exit_price=?, evaluated_at=?, outcome=?, return_pct=?
                    WHERE id=? AND evaluated_at IS NULL
                """, (price, now, outcome, signed_return, row["id"]))
                evaluated += 1
            db.execute("""
                INSERT OR IGNORE INTO shadow_predictions
                (id,symbol,signal,signal_time,entry_price,reason)
                VALUES(?,?,?,?,?,?)
            """, (uuid.uuid4().hex, symbol, signal, signal_time, price, reason))
            inserted = db.execute("SELECT changes()").fetchone()[0] == 1
        return {"evaluated": evaluated, "inserted": inserted}

    def summary(self, limit: int = 100) -> dict:
        limit = max(1, min(int(limit), 1000))
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM shadow_predictions ORDER BY signal_time DESC LIMIT ?", (limit,)
            ).fetchall()
            totals = db.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN evaluated_at IS NOT NULL THEN 1 ELSE 0 END) AS evaluated,
                       SUM(CASE WHEN outcome='correct' THEN 1 ELSE 0 END) AS correct,
                       SUM(CASE WHEN outcome='incorrect' THEN 1 ELSE 0 END) AS incorrect,
                       SUM(CASE WHEN outcome='flat' THEN 1 ELSE 0 END) AS flat,
                       SUM(CASE WHEN signal='neutral' THEN 1 ELSE 0 END) AS neutral
                FROM shadow_predictions
            """).fetchone()
        data = dict(totals)
        data["directional_evaluated"] = (data["correct"] or 0) + (data["incorrect"] or 0) + (data["flat"] or 0)
        denominator = (data["correct"] or 0) + (data["incorrect"] or 0)
        data["directional_accuracy_pct"] = round(100 * (data["correct"] or 0) / denominator, 2) if denominator else None
        data["records"] = [dict(row) for row in rows]
        data["mode"] = "SHADOW_ONLY"
        data["orders_created"] = 0
        return data
