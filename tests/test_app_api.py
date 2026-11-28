import base64
import json
import threading
import sys
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


@pytest.fixture
def apex_server(tmp_path, monkeypatch):
    monkeypatch.setenv("APEX_ACCESS_PASSWORD", "test-only-password")
    monkeypatch.setenv("APEX_DATA_DIR", str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def call(base, path, *, payload=None, authenticated=True):
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(base + path, data=data, method="GET" if payload is None else "POST")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if authenticated:
        token = base64.b64encode(b"apex:test-only-password").decode()
        request.add_header("Authorization", "Basic " + token)
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, exc.read().decode()


def test_dashboard_health_is_public_and_paper_api_requires_auth(apex_server):
    status, health = call(apex_server, "/healthz", authenticated=False)
    assert status == 200 and health["live_trading_enabled"] is False
    status, _ = call(apex_server, "/api/paper/trades", authenticated=False)
    assert status == 401


def test_paper_trade_create_list_close_flow(apex_server, tmp_path):
    payload = {
        "instrument": "EURUSD", "side": "buy", "quantity": "1",
        "entry_price": "1.1000", "stop_price": "1.0900",
        "strategy_id": "manual-test", "client_id": "paper-test-001",
        "paper_mode_enabled": True, "user_confirmed": True,
    }
    status, created = call(apex_server, "/api/paper/trades", payload=payload)
    assert status == 200 and created["status"] == "open" and created["mode"] == "paper"

    status, listing = call(apex_server, "/api/paper/trades")
    assert status == 200 and len(listing["trades"]) == 1

    status, closed = call(apex_server, f"/api/paper/trades/{created['trade_id']}/close",
                          payload={"exit_price": "1.1100", "user_confirmed": True})
    assert status == 200 and closed["status"] == "closed"

    status, summary = call(apex_server, "/api/paper/summary")
    assert status == 200 and summary["closed_trades"] == 1
    assert summary["realized_gross_pnl"] == "0.0100"

    # The paper ledger must be part of the same database snapshot.
    from apex.storage import APEXStore
    import sqlite3
    snapshot = tmp_path / "apex-snapshot.sqlite3"
    APEXStore().backup(str(snapshot))
    with sqlite3.connect(snapshot) as db:
        assert db.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0] == 1


def test_paper_trade_rejects_missing_confirmation(apex_server):
    payload = {
        "instrument": "EURUSD", "side": "buy", "quantity": "1",
        "entry_price": "1.1000", "stop_price": "1.0900",
        "strategy_id": "manual-test", "client_id": "paper-test-002",
        "paper_mode_enabled": True, "user_confirmed": False,
    }
    status, _ = call(apex_server, "/api/paper/trades", payload=payload)
    assert status == 400
