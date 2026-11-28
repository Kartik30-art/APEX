from apex.shadow import ShadowLedger


def test_shadow_signal_is_evaluated_on_next_new_observation(tmp_path):
    ledger = ShadowLedger(tmp_path / "shadow.sqlite3")
    first = ledger.observe("EUR/USD", "buy", "2026-01-01T00:00:00+00:00", 1.10, "test")
    assert first == {"evaluated": 0, "inserted": True}

    # Repeated polling of the same completed candle must not duplicate a record.
    duplicate = ledger.observe("EUR/USD", "buy", "2026-01-01T00:00:00+00:00", 1.10, "test")
    assert duplicate["inserted"] is False

    next_bar = ledger.observe("EUR/USD", "neutral", "2026-01-01T00:15:00+00:00", 1.111, "no setup")
    assert next_bar == {"evaluated": 1, "inserted": True}
    summary = ledger.summary()
    assert summary["total"] == 2
    assert summary["evaluated"] == 1
    assert summary["correct"] == 1
    assert summary["directional_accuracy_pct"] == 100.0
    assert summary["orders_created"] == 0
    assert summary["mode"] == "SHADOW_ONLY"


def test_shadow_sell_return_is_direction_adjusted(tmp_path):
    ledger = ShadowLedger(tmp_path / "shadow.sqlite3")
    ledger.observe("GBP/USD", "sell", "2026-01-01T00:00:00+00:00", 1.30, "test")
    ledger.observe("GBP/USD", "neutral", "2026-01-01T00:15:00+00:00", 1.29, "test")
    row = ledger.summary()["records"][1]
    assert row["outcome"] == "correct"
    assert row["return_pct"] > 0


def test_shadow_rejects_invalid_signal_and_price(tmp_path):
    ledger = ShadowLedger(tmp_path / "shadow.sqlite3")
    for signal, price in (("long", 1.0), ("buy", 0), ("buy", float("nan"))):
        try:
            ledger.observe("EUR/USD", signal, "2026-01-01T00:00:00+00:00", price, "test")
        except ValueError:
            pass
        else:
            raise AssertionError("invalid shadow prediction was accepted")
