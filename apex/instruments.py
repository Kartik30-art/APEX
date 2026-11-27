"""Versioned instrument metadata and contract-aware P&L/cost calculations."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from enum import Enum

class Venue(str, Enum):
    NSE = "NSE"
    GENERIC = "GENERIC"

@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    venue: Venue
    base_currency: str
    quote_currency: str
    units_per_contract: Decimal
    quote_units: Decimal
    tick_size: Decimal
    tick_value: Decimal
    contract_type: str = "future"
    metadata_version: str = "2026-11-reference"
    source: str = "NSE published currency derivative contract specifications"

    def __post_init__(self):
        for name in ("units_per_contract", "quote_units", "tick_size", "tick_value"):
            value = getattr(self, name)
            if not value.is_finite() or value <= 0:
                raise ValueError(f"{name} must be finite and positive")

# NSE INR futures reference specs. JPYINR is quoted per 100 JPY.
NSE_INR_FUTURES = {
    "USDINR": ContractSpec("USDINR", Venue.NSE, "USD", "INR", Decimal("1000"), Decimal("1"), Decimal("0.0025"), Decimal("2.5")),
    "EURINR": ContractSpec("EURINR", Venue.NSE, "EUR", "INR", Decimal("1000"), Decimal("1"), Decimal("0.0025"), Decimal("2.5")),
    "GBPINR": ContractSpec("GBPINR", Venue.NSE, "GBP", "INR", Decimal("1000"), Decimal("1"), Decimal("0.0025"), Decimal("2.5")),
    "JPYINR": ContractSpec("JPYINR", Venue.NSE, "JPY", "INR", Decimal("100000"), Decimal("100"), Decimal("0.0025"), Decimal("2.5")),
}

@dataclass(frozen=True)
class FeeSchedule:
    """Explicit configurable charges. Rates are fractions of traded notional."""
    brokerage_per_order: Decimal = Decimal("0")
    exchange_rate: Decimal = Decimal("0")
    sebi_rate: Decimal = Decimal("0")
    stamp_rate: Decimal = Decimal("0")
    transaction_tax_rate: Decimal = Decimal("0")
    gst_rate: Decimal = Decimal("0")
    other_per_order: Decimal = Decimal("0")

    def __post_init__(self):
        for name, value in self.__dict__.items():
            if not value.is_finite() or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")

@dataclass(frozen=True)
class Valuation:
    contracts: int
    notional_quote: Decimal
    tick_value_quote: Decimal
    gross_pnl_quote: Decimal
    estimated_fees_quote: Decimal
    net_pnl_quote: Decimal

def whole_contracts(requested_units: Decimal, spec: ContractSpec) -> int:
    if requested_units <= 0:
        raise ValueError("requested units must be positive")
    return int((requested_units / spec.units_per_contract).to_integral_value(rounding=ROUND_FLOOR))

def calculate_futures_valuation(spec: ContractSpec, *, contracts: int,
        entry_price: Decimal, exit_price: Decimal, side: str,
        fees: FeeSchedule = FeeSchedule()) -> Valuation:
    if contracts <= 0:
        raise ValueError("contracts must be a positive whole number")
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    if entry_price <= 0 or exit_price <= 0:
        raise ValueError("prices must be positive")
    direction = Decimal("1") if side == "buy" else Decimal("-1")
    units = spec.units_per_contract * contracts
    quote_factor = units / spec.quote_units
    notional = entry_price * quote_factor
    gross = (exit_price - entry_price) * quote_factor * direction
    traded_notional = (entry_price + exit_price) * quote_factor
    variable_rate = fees.exchange_rate + fees.sebi_rate + fees.stamp_rate + fees.transaction_tax_rate
    variable = traded_notional * variable_rate
    fixed = (fees.brokerage_per_order + fees.other_per_order) * 2
    gst = (variable + fees.brokerage_per_order * 2 + fees.other_per_order * 2) * fees.gst_rate
    total_fees = variable + fixed + gst
    return Valuation(contracts, notional, spec.tick_value * contracts, gross, total_fees, gross-total_fees)
