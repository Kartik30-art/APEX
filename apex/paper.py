"""Local SQLite paper-trade journal. No broker or order-routing capability."""
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from .models import TradeIntent

class PaperTradingDisabled(RuntimeError):
    pass

class PaperLedger:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _init_db(self):
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                instrument TEXT NOT NULL,
                side TEXT NOT NULL CHECK(side IN ('buy','sell')),
                quantity TEXT NOT NULL,
                entry_price TEXT NOT NULL,
                stop_price TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('open','closed')),
                exit_price TEXT,
                closed_at TEXT,
                notes TEXT NOT NULL DEFAULT ''
            )""")

    def record_approved_intent(self, intent: TradeIntent, *, client_id: str, user_confirmed: bool,
                               paper_mode_enabled: bool, notes: str = "") -> int:
        """Record a simulated intent only after an explicit user confirmation."""
        if not paper_mode_enabled:
            raise PaperTradingDisabled("paper mode is disabled")
        if not user_confirmed:
            raise PermissionError("explicit user confirmation is required")
        if not client_id.strip():
            raise ValueError("client_id is required for idempotency")
        with self._connect() as db:
            cur = db.execute("""INSERT INTO paper_trades
                (client_id,created_at,instrument,side,quantity,entry_price,stop_price,strategy_id,status,notes)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (client_id, datetime.now(timezone.utc).isoformat(), intent.instrument, intent.side,
                 str(intent.quantity), str(intent.entry_price), str(intent.stop_price),
                 intent.strategy_id, "open", notes))
            return int(cur.lastrowid)

    def close_trade(self, trade_id: int, *, exit_price: Decimal, user_confirmed: bool):
        if not user_confirmed:
            raise PermissionError("explicit user confirmation is required")
        if exit_price <= 0:
            raise ValueError("exit_price must be positive")
        with self._connect() as db:
            cur = db.execute("""UPDATE paper_trades SET status='closed', exit_price=?, closed_at=?
                WHERE id=? AND status='open'""",
                (str(exit_price), datetime.now(timezone.utc).isoformat(), trade_id))
            if cur.rowcount != 1:
                raise ValueError("trade not found or already closed")

    def list_trades(self, *, limit: int = 100):
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM paper_trades ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(row) for row in rows]

    def summary(self):
        trades = self.list_trades(limit=1000)
        opened = sum(1 for row in trades if row["status"] == "open")
        closed = [row for row in trades if row["status"] == "closed"]
        realized = Decimal("0")
        for row in closed:
            direction = Decimal("1") if row["side"] == "buy" else Decimal("-1")
            realized += (Decimal(row["exit_price"]) - Decimal(row["entry_price"])) * Decimal(row["quantity"]) * direction
        return {"open_trades": opened, "closed_trades": len(closed), "realized_gross_pnl": str(realized),
                "note": "Gross quote-currency P&L only; excludes costs, contract multipliers and FX conversion."}
