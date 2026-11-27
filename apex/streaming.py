"""Opt-in Twelve Data WebSocket price stream for entitled FX symbols.

A stream is process-local and stops when the service restarts or sleeps. It is
not a guaranteed 24/7 feed and does not create historical candles.
"""
from __future__ import annotations
import asyncio
import json
import os
import threading
import time
from urllib.parse import quote


class StreamNotConfigured(RuntimeError): pass


class TwelveDataForexStream:
    def __init__(self, api_key: str | None = None):
        self.api_key=api_key or os.getenv("TWELVEDATA_API_KEY")
        if not self.api_key:
            raise StreamNotConfigured("Set TWELVEDATA_API_KEY")
        self._lock=threading.RLock()
        self._stop=threading.Event()
        self._thread=None
        self._latest={}
        self._status={"state":"stopped","message":"not started","updated_at":None}
        self._symbols=[]

    def start(self,symbols: list[str]):
        cleaned=sorted(set(x.strip().upper() for x in symbols if x.strip()))
        if not cleaned or len(cleaned)>8:
            raise ValueError("Provide 1 to 8 symbols; provider trial plans may restrict allowed symbols")
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("A stream is already running")
            self._symbols=cleaned
            self._latest={}
            self._stop.clear()
            self._status={"state":"connecting","message":"opening provider WebSocket","updated_at":time.time()}
            self._thread=threading.Thread(target=self._thread_main,daemon=True,name="apex-fx-stream")
            self._thread.start()
        return self.status()

    def _thread_main(self):
        try:
            asyncio.run(self._run())
        except Exception as exc:
            with self._lock:
                self._status={"state":"error","message":type(exc).__name__,"updated_at":time.time()}

    async def _run(self):
        try:
            import websockets
        except ImportError as exc:
            raise StreamNotConfigured("Install websockets dependency") from exc
        url="wss://ws.twelvedata.com/v1/quotes/price?apikey="+quote(self.api_key,safe="")
        try:
            async with websockets.connect(url,ping_interval=None,open_timeout=15,close_timeout=5) as ws:
                await ws.send(json.dumps({"action":"subscribe","params":{"symbols":",".join(self._symbols)}}))
                with self._lock:
                    self._status={"state":"connected","message":"subscription requested; waiting for provider status","updated_at":time.time()}
                while not self._stop.is_set():
                    try:
                        raw=await asyncio.wait_for(ws.recv(),timeout=10)
                    except asyncio.TimeoutError:
                        await ws.send(json.dumps({"action":"heartbeat"}))
                        continue
                    data=json.loads(raw)
                    event=data.get("event")
                    with self._lock:
                        if event=="price":
                            self._latest[data.get("symbol","?")]={
                                "symbol":data.get("symbol"),"timestamp":data.get("timestamp"),
                                "price":data.get("price"),"bid":data.get("bid"),"ask":data.get("ask"),
                                "currency":data.get("currency"),"type":data.get("type"),
                                "received_at":time.time()
                            }
                            self._status={"state":"streaming","message":"receiving ticks","updated_at":time.time()}
                        elif event=="subscribe-status":
                            self._status={"state":"subscribed" if data.get("status")=="ok" else "subscription_error",
                                "message":"provider subscription response","success":data.get("success",[]),
                                "fails":data.get("fails",[]),"updated_at":time.time()}
                        elif event=="error":
                            self._status={"state":"error","message":"provider reported an error","updated_at":time.time()}
                with self._lock:
                    self._status={"state":"stopped","message":"stopped by user","updated_at":time.time()}
        except Exception as exc:
            with self._lock:
                self._status={"state":"error","message":type(exc).__name__,"updated_at":time.time()}

    def stop(self):
        self._stop.set()
        with self._lock:
            if self._status.get("state") not in {"error","stopped"}:
                self._status={"state":"stopping","message":"closing stream","updated_at":time.time()}
        return self.status()

    def status(self):
        with self._lock:
            return {**self._status,"symbols":list(self._symbols),"latest":dict(self._latest)}
