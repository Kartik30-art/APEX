# APEX MetaTrader 5 demo bridge

This bridge runs on **your Windows PC**, beside the MetaTrader 5 desktop terminal. Render cannot host the MT5 terminal.

## Safety
- The bridge refuses to trade unless MT5 reports an account in DEMO mode.
- It re-checks demo mode every polling cycle.
- It mirrors APEX paper positions only; it does not use the unvalidated ML models.
- Hard cap: 0.01 MT5 lots per position.
- It rejects broker quotes more than 0.5% away from the APEX reference price.
- Orders carry broker-side stop-loss and take-profit.
- Stop the bridge with Ctrl+C. Open broker positions remain protected by their attached SL/TP.

## Windows setup
1. Install MetaTrader 5 from your broker and sign in to a **demo** account.
2. In MT5, enable algorithmic trading / Expert Advisors. Keep the terminal open.
3. Install Python 3.11+ (64-bit).
4. Open PowerShell in this folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install MetaTrader5 requests
python apex_mt5_bridge.py
```

5. Enter your APEX dashboard password when prompted. It is hidden and is not stored by the script.
6. Confirm the terminal output says DEMO account and the correct broker/server.

Default APEX URL is prefilled. APEX username defaults to `apex`.

## Important limitations
- APEX market data currently comes from Yahoo Finance's unofficial feed, not the broker's live feed. The bridge checks price deviation and rejects mismatches.
- APEX strategy is deterministic EMA/RSI/ATR rules, not a validated trained ML model.
- The bridge mirrors at most one open APEX position at a time. It uses a fixed 0.01 lot cap rather than scaling APEX's abstract quantity into broker lots.
- Broker minimum lot sizes, symbol naming, filling modes, stop-distance rules, and account permissions vary. If the broker rejects an order, the bridge prints the rejection; it does not retry blindly.
- Test on demo only. This is experimental software, not a profitability claim.
