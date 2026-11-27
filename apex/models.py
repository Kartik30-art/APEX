from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

class Market(str, Enum):
    GLOBAL_FOREX = "global_forex"
    INDIA_CURRENCY_DERIVATIVES = "india_currency_derivatives"

@dataclass(frozen=True)
class Instrument:
    symbol: str
    market: Market
    base_currency: str
    quote_currency: str
    tick_size: Decimal
    lot_size: Decimal
    expiry: Optional[datetime] = None
    def __post_init__(self):
        if not self.symbol.strip(): raise ValueError("symbol must not be empty")
        if self.tick_size <= 0 or self.lot_size <= 0: raise ValueError("tick_size and lot_size must be positive")
        if self.market == Market.GLOBAL_FOREX and self.expiry is not None: raise ValueError("global Forex spot profile cannot have exchange expiry")

@dataclass(frozen=True)
class Quote:
    instrument: str
    bid: Decimal
    ask: Decimal
    timestamp: datetime
    source: str
    def __post_init__(self):
        if self.bid <= 0 or self.ask <= 0 or self.ask < self.bid: raise ValueError("invalid bid/ask")
        if not self.source.strip(): raise ValueError("source is required")

@dataclass(frozen=True)
class TradeIntent:
    instrument: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    stop_price: Decimal
    timestamp: datetime
    strategy_id: str
    def __post_init__(self):
        if self.side not in {"buy", "sell"}: raise ValueError("side must be buy or sell")
        if min(self.quantity, self.entry_price, self.stop_price) <= 0: raise ValueError("quantity and prices must be positive")
        if not self.strategy_id.strip(): raise ValueError("strategy_id is required")
