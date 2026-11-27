from dataclasses import dataclass
from .models import Market

@dataclass(frozen=True)
class MarketProfile:
    market: Market
    timezone: str
    execution_allowed: bool
    notes: str

GLOBAL_FOREX = MarketProfile(Market.GLOBAL_FOREX, "UTC", False, "Research only; India-based execution requires separate legal and provider review.")
INDIA_CURRENCY_DERIVATIVES = MarketProfile(Market.INDIA_CURRENCY_DERIVATIVES, "Asia/Kolkata", False, "Verify current exchange contract specifications and regulatory requirements.")
PROFILES = {Market.GLOBAL_FOREX: GLOBAL_FOREX, Market.INDIA_CURRENCY_DERIVATIVES: INDIA_CURRENCY_DERIVATIVES}

def profile_for(market: Market) -> MarketProfile:
    return PROFILES[market]
