import pytest

from apex.forex_data import fetch_yahoo_history, validate_history


def test_data_provider_rejects_unknown_symbol_before_network():
    with pytest.raises(ValueError, match="unsupported Forex symbol"):
        fetch_yahoo_history("BTC-USD")


def test_data_provider_rejects_unsupported_interval_before_network():
    with pytest.raises(ValueError, match="interval"):
        fetch_yahoo_history("EURUSD=X", interval="5m")


def test_hourly_history_rejects_unsupported_lookback_before_network():
    with pytest.raises(ValueError, match="limited"):
        fetch_yahoo_history("EURUSD=X", period="5y", interval="1h")


def test_history_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError, match="timezone"):
        validate_history([{
            "timestamp": "2026-01-01T00:00:00",
            "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15,
        }])
