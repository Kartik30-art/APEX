"""APEX -> MetaTrader 5 demo-only execution bridge.

Runs on the Windows PC where the MetaTrader 5 desktop terminal is installed.
It mirrors APEX autonomous paper positions to a DEMO MT5 account only.
"""
from __future__ import annotations

import getpass
import os
import sys
import time
from pathlib import Path

import requests
import MetaTrader5 as mt5

MAGIC = 28112026
POLL_SECONDS = 5
MAX_VOLUME = 0.01
MAX_PRICE_DEVIATION = 0.005  # Reject if broker quote differs from APEX reference by >0.5%.


def api_session(base_url: str, username: str, password: str) -> requests.Session:
    session = requests.Session()
    session.auth = (username, password)
    session.headers.update({"User-Agent": "APEX-MT5-Demo-Bridge/1.0"})
    session.base_url = base_url.rstrip("/")
    return session


def api_get(session: requests.Session, path: str):
    response = session.get(session.base_url + path, timeout=15)
    response.raise_for_status()
    return response.json()


def mt5_symbol(pair: str) -> str:
    """Resolve common broker suffix/prefix variants using MT5's symbol catalogue."""
    compact = pair.replace("/", "").upper()
    symbols = mt5.symbols_get()
    if not symbols:
        raise RuntimeError(f"MT5 returned no symbols: {mt5.last_error()}")
    names = [x.name for x in symbols]
    exact = [n for n in names if n.upper() == compact]
    candidates = exact or [n for n in names if n.upper().endswith(compact) or n.upper().startswith(compact)]
    if not candidates:
        raise RuntimeError(f"No broker symbol found for {pair}")
    # Prefer the shortest suffix/prefix variant; do not guess among equally ranked names.
    candidates.sort(key=lambda n: (len(n), n))
    if len(candidates) > 1 and len(candidates[0]) == len(candidates[1]):
        raise RuntimeError(f"Ambiguous broker symbols for {pair}: {candidates[:5]}")
    name = candidates[0]
    if not mt5.symbol_select(name, True):
        raise RuntimeError(f"Could not select {name}: {mt5.last_error()}")
    return name


def owned_positions(symbol: str | None = None):
    rows = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if rows is None:
        raise RuntimeError(f"MT5 positions_get failed: {mt5.last_error()}")
    return [p for p in rows if p.magic == MAGIC]


def check_demo_account():
    info = mt5.account_info()
    if info is None:
        raise RuntimeError(f"MT5 account unavailable: {mt5.last_error()}")
    if info.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise RuntimeError("SAFETY STOP: connected MT5 account is not DEMO. No orders sent.")
    if not info.trade_allowed or not info.trade_expert:
        raise RuntimeError("MT5 trading or expert trading is disabled in terminal/account.")
    return info


def supported_market_filling(spec):
    """Choose a market-order filling policy from the broker's supported flags."""
    flags = int(spec.filling_mode)
    if flags & getattr(mt5, "SYMBOL_FILLING_FOK", 1):
        return mt5.ORDER_FILLING_FOK
    if flags & getattr(mt5, "SYMBOL_FILLING_IOC", 2):
        return mt5.ORDER_FILLING_IOC
    raise RuntimeError(
        f"Broker does not advertise FOK/IOC market filling for {spec.name}; refusing order"
    )


def send_open(trade: dict):
    pair = trade["symbol"]
    symbol = mt5_symbol(pair)
    tick = mt5.symbol_info_tick(symbol)
    spec = mt5.symbol_info(symbol)
    if tick is None or spec is None:
        raise RuntimeError(f"No live broker quote/specification for {symbol}")
    side = str(trade["side"]).lower()
    if side not in {"buy", "sell"}:
        raise RuntimeError(f"Unsupported APEX trade side: {side!r}")
    expected = float(trade["entry_price"])
    market = tick.ask if side == "buy" else tick.bid
    if expected <= 0 or abs(market - expected) / expected > MAX_PRICE_DEVIATION:
        raise RuntimeError(f"Quote mismatch for {symbol}; APEX={expected}, broker={market}. Order rejected.")
    sl, tp = float(trade["stop_price"]), float(trade["target_price"])
    if side == "buy" and not (sl < market < tp):
        raise RuntimeError(f"Invalid BUY stop/target relative to broker quote for {symbol}")
    if side == "sell" and not (tp < market < sl):
        raise RuntimeError(f"Invalid SELL stop/target relative to broker quote for {symbol}")
    # Never round a requested volume upward: stay at or below the hard cap.
    minimum, maximum = float(spec.volume_min), float(spec.volume_max)
    step = float(spec.volume_step or 0.01)
    if minimum <= 0 or step <= 0 or minimum > MAX_VOLUME or maximum < minimum:
        raise RuntimeError(
            f"Broker volume constraints are incompatible with {MAX_VOLUME} lot cap: "
            f"min={minimum}, max={maximum}, step={step}"
        )
    ceiling = min(MAX_VOLUME, maximum)
    steps = int((ceiling - minimum + 1e-10) // step)
    volume = round(minimum + steps * step, 8)
    if volume < minimum - 1e-9 or volume > MAX_VOLUME + 1e-9:
        raise RuntimeError(f"Safe volume cannot be represented under {MAX_VOLUME} lot cap")
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL,
        "price": market,
        "sl": round(sl, spec.digits),
        "tp": round(tp, spec.digits),
        "deviation": 20,
        "magic": MAGIC,
        "comment": "APEX:" + str(trade["id"])[:20],
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": supported_market_filling(spec),
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        raise RuntimeError(f"MT5 order rejected: {result}; last_error={mt5.last_error()}")
    print(f"OPENED DEMO {side.upper()} {symbol} {volume} lots, ticket={result.order}")


def close_position(position):
    tick = mt5.symbol_info_tick(position.symbol)
    if tick is None:
        raise RuntimeError(f"No quote to close {position.symbol}")
    is_buy = position.type == mt5.POSITION_TYPE_BUY
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": position.volume,
        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
        "position": position.ticket,
        "price": tick.bid if is_buy else tick.ask,
        "deviation": 20,
        "magic": MAGIC,
        "comment": "APEX DEMO close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": supported_market_filling(mt5.symbol_info(position.symbol)),
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        raise RuntimeError(f"MT5 close rejected: {result}; last_error={mt5.last_error()}")
    print(f"CLOSED DEMO {position.symbol}, ticket={position.ticket}")


def main():
    base = input("APEX URL [https://apex-research-3alb.onrender.com]: ").strip()
    base = base or "https://apex-research-3alb.onrender.com"
    username = input("APEX username [apex]: ").strip() or "apex"
    password = getpass.getpass("APEX dashboard password (input hidden): ")
    terminal = input("MT5 terminal64.exe path (Enter if MT5 is already running): ").strip()
    if terminal:
        if not mt5.initialize(path=terminal):
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    elif not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    session = api_session(base, username, password)
    account = check_demo_account()
    print(f"Connected to DEMO account login={account.login}, server={account.server}, balance={account.balance}")
    print("APEX bridge active. Hard cap: 0.01 lots per mirrored position. Ctrl+C to stop.")
    seen_open: set[str] = set()
    try:
        while True:
            check_demo_account()  # Re-check demo status every poll.
            status = api_get(session, "/api/agent/status")
            acct = status.get("account") or {}
            apex_open = {str(t["id"]): t for t in acct.get("open_trades", [])}
            # One APEX position at a time; mirror only trades not previously opened by this process.
            current = owned_positions()
            if not current and len(apex_open) == 1:
                trade_id, trade = next(iter(apex_open.items()))
                if trade_id not in seen_open:
                    try:
                        send_open(trade)
                        seen_open.add(trade_id)
                    except Exception as exc:
                        print(f"OPEN REJECTED {trade.get('symbol')}: {exc}")
            # If APEX has closed a mirrored position, close only this bridge's MT5 position.
            closed_ids = {str(t["id"]) for t in acct.get("closed_trades", [])}
            for pos in owned_positions():
                # The order comment stores the APEX trade ID for exact close matching.
                matched = next((tid for tid in closed_ids if tid[:20] in (pos.comment or "")), None)
                if matched:
                    try:
                        close_position(pos)
                    except Exception as exc:
                        print(f"CLOSE FAILED {pos.ticket}: {exc}")
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("Bridge stopped by user. Existing MT5 demo positions are left protected by broker SL/TP.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
