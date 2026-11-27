"""SQLite persistence and online backups. Use APEX_DATA_DIR on a persistent disk."""
from __future__ import annotations
import hashlib
import os
import sqlite3
from datetime import datetime,timezone
from pathlib import Path

class APEXStore:
    def __init__(self,path: str | None=None):
        root=Path(os.getenv("APEX_DATA_DIR","data"))
        self.path=Path(path) if path else root/"apex.sqlite3"
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self._initialize()
    def connect(self):
        db=sqlite3.connect(self.path,timeout=20)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=20000")
        return db
    def _initialize(self):
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS market_candles(market TEXT NOT NULL,symbol TEXT NOT NULL,interval TEXT NOT NULL,timestamp TEXT NOT NULL,open TEXT NOT NULL,high TEXT NOT NULL,low TEXT NOT NULL,close TEXT NOT NULL,volume TEXT NOT NULL,source TEXT NOT NULL,PRIMARY KEY(market,symbol,interval,timestamp));
            CREATE TABLE IF NOT EXISTS paper_orders(client_order_id TEXT PRIMARY KEY,created_at TEXT NOT NULL,market TEXT NOT NULL,symbol TEXT NOT NULL,side TEXT NOT NULL,quantity TEXT NOT NULL,order_type TEXT NOT NULL,status TEXT NOT NULL,payload_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS research_runs(run_id TEXT PRIMARY KEY,created_at TEXT NOT NULL,category TEXT NOT NULL,input_hash TEXT NOT NULL,output_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit_events(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,event_type TEXT NOT NULL,payload_json TEXT NOT NULL);
            INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(1,datetime('now'));
            """)
    def save_candles(self,market,symbol,interval,candles,source):
        rows=[(market,symbol,interval,c.timestamp.isoformat(),str(c.open),str(c.high),str(c.low),str(c.close),str(c.volume),source) for c in candles]
        with self.connect() as db: db.executemany("INSERT OR REPLACE INTO market_candles VALUES(?,?,?,?,?,?,?,?,?,?)",rows)
        return len(rows)
    def load_candles(self,market,symbol,interval):
        from datetime import datetime
        from decimal import Decimal
        from .data_validation import Candle
        with self.connect() as db:
            rows=db.execute("SELECT * FROM market_candles WHERE market=? AND symbol=? AND interval=? ORDER BY timestamp",(market,symbol,interval)).fetchall()
        return [Candle(datetime.fromisoformat(r["timestamp"]),Decimal(r["open"]),Decimal(r["high"]),Decimal(r["low"]),Decimal(r["close"]),Decimal(r["volume"])) for r in rows]
    def audit(self,event_type,payload_json):
        with self.connect() as db:
            db.execute("INSERT INTO audit_events(created_at,event_type,payload_json) VALUES(?,?,?)",(datetime.now(timezone.utc).isoformat(),event_type,payload_json))
    def backup(self,destination: str) -> dict:
        target=Path(destination); target.parent.mkdir(parents=True,exist_ok=True)
        source=self.connect()
        dest=sqlite3.connect(target)
        try:
            source.backup(dest)
            if dest.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise RuntimeError("SQLite backup integrity check failed")
            dest.commit()
        finally:
            source.close()
            dest.close()
        digest=hashlib.sha256()
        with target.open("rb") as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b""):
                digest.update(chunk)
        return {"path":str(target),"sha256":digest.hexdigest(),"bytes":target.stat().st_size,"integrity":"ok","created_at":datetime.now(timezone.utc).isoformat()}
