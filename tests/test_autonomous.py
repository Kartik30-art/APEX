from decimal import Decimal

from apex.autonomous import AutonomousDemoAgent, _indicators


def test_agent_starts_with_demo_balance_and_adds_virtual_funds(tmp_path):
    agent = AutonomousDemoAgent(tmp_path / "agent.sqlite3")
    before = agent.snapshot()["account"]
    assert before["starting_balance"] == "10000"
    assert before["balance"] == "10000"
    after = agent.add_demo_funds("2500") 
    assert Decimal(after["balance"]) == Decimal("12500")
    assert Decimal(after["equity"]) == Decimal("12500")


def test_agent_rejects_invalid_demo_funding(tmp_path):
    agent = AutonomousDemoAgent(tmp_path / "agent.sqlite3")
    for amount in ("0", "-1", "NaN", "Infinity", "100000001"):
        try:
            agent.add_demo_funds(amount)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid virtual funding amount: {amount}")


def test_indicators_produce_finite_values():
    bars = []
    for i in range(80):
        close = 1.05 + i * 0.0001
        bars.append({"open": close - 0.00005, "high": close + 0.0001,
                     "low": close - 0.0001, "close": close})
    values = _indicators(bars)
    assert values["ema_fast"] > values["ema_slow"]
    assert 0 <= values["rsi"] <= 100
    assert values["atr"] > 0
