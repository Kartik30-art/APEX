"""Broker abstraction with a fail-closed live-trading gate."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
import json,uuid
from datetime import datetime,timezone
from .storage import APEXStore

@dataclass(frozen=True)
class OrderRequest:
    market: str
    symbol: str
    side: str
    quantity: Decimal
    order_type: str = "market"
    limit_price: Decimal | None = None
    def __post_init__(self):
        if self.side not in {"buy","sell"}: raise ValueError("side must be buy or sell")
        if not self.quantity.is_finite() or self.quantity<=0: raise ValueError("quantity must be finite and positive")
        if self.order_type not in {"market","limit"}: raise ValueError("unsupported order type")
        if self.order_type=="limit" and (self.limit_price is None or self.limit_price<=0): raise ValueError("limit order requires positive limit_price")

class BrokerAdapter(Protocol):
    def place_order(self,order: OrderRequest,client_order_id: str) -> dict: ...

class LiveExecutionLocked(RuntimeError): pass

class PaperBroker:
    def __init__(self,store: APEXStore): self.store=store
    def place_order(self,order: OrderRequest,client_order_id: str | None=None) -> dict:
        client_order_id=client_order_id or str(uuid.uuid4())
        payload={"market":order.market,"symbol":order.symbol,"side":order.side,"quantity":str(order.quantity),"order_type":order.order_type,"limit_price":str(order.limit_price) if order.limit_price else None}
        with self.store.connect() as db:
            db.execute("INSERT INTO paper_orders(client_order_id,created_at,market,symbol,side,quantity,order_type,status,payload_json) VALUES(?,?,?,?,?,?,?,?,?)",(client_order_id,datetime.now(timezone.utc).isoformat(),order.market,order.symbol,order.side,str(order.quantity),order.order_type,"PENDING_PAPER",json.dumps(payload,sort_keys=True)))
        return {"client_order_id":client_order_id,"status":"PENDING_PAPER","mode":"paper","broker_order_id":None}

class LiveBrokerGateway:
    """No production broker adapter is installed; every live request is rejected."""
    def __init__(self,adapter: BrokerAdapter | None=None): self.adapter=adapter
    def place_order(self,order: OrderRequest,client_order_id: str):
        raise LiveExecutionLocked("Live execution is disabled. Select a supported broker, verify legal eligibility and API permissions, then complete independent safety review.")
