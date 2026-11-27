import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from .data_validation import Candle, validate_candles
from .markets import GLOBAL_FOREX, INDIA_CURRENCY_DERIVATIVES

def main():
    parser = argparse.ArgumentParser(prog="apex")
    parser.add_argument("command", choices=["demo"])
    args = parser.parse_args()
    if args.command == "demo":
        now = datetime.now(timezone.utc)
        data = [Candle(now-timedelta(minutes=1), Decimal("1.1"), Decimal("1.2"), Decimal("1.0"), Decimal("1.15"))]
        print("APEX Phase 0 demo")
        print("Global Forex execution enabled:", GLOBAL_FOREX.execution_allowed)
        print("India derivatives execution enabled:", INDIA_CURRENCY_DERIVATIVES.execution_allowed)
        print("Sample data valid:", validate_candles(data).valid)
        print("Live trading implemented: False")

if __name__ == "__main__": main()
