from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import os
import base64
import hmac

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>APEX | Research Workbench</title>
<style>
:root{color-scheme:dark;--bg:#090d16;--panel:#111a2b;--line:#26344c;--muted:#9aa9bf;--text:#edf3ff;--accent:#70d6b2;--warn:#f3c875}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% 0%,#172843 0,transparent 38%),var(--bg);color:var(--text);font:15px/1.6 Inter,system-ui,sans-serif}
main{max-width:1080px;margin:auto;padding:40px 22px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
.brand{font-weight:800;letter-spacing:.2em;font-size:22px}.pill{border:1px solid #397d69;color:var(--accent);padding:6px 12px;border-radius:99px;font-size:12px}
h1{font-size:clamp(36px,7vw,60px);line-height:1.03;letter-spacing:-.04em;margin:55px 0 18px}h1 span{color:var(--accent)}
.lead{color:var(--muted);max-width:760px;font-size:16px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:30px 0}
.card{background:linear-gradient(145deg,#152238,#101827);border:1px solid var(--line);border-radius:16px;padding:20px}.card h2{font-size:14px;margin:0 0 8px}.state{font-size:19px;font-weight:700}.muted{color:var(--muted);font-size:13px}
section.work{background:#101827;border:1px solid var(--line);border-radius:18px;padding:22px;margin:18px 0}input,button{font:inherit}input[type=file]{display:block;margin:14px 0;color:var(--muted);max-width:100%}
button{background:var(--accent);color:#08130f;border:0;border-radius:9px;padding:10px 16px;font-weight:700;cursor:pointer}button:disabled{opacity:.5;cursor:wait}
label{display:block;color:var(--muted);font-size:13px;margin:10px 0 4px}.fields{display:flex;gap:14px;flex-wrap:wrap}.fields label{min-width:130px}
input[type=number]{background:#0b1220;border:1px solid var(--line);color:var(--text);padding:8px;border-radius:8px;width:145px}
#result{white-space:pre-wrap;color:var(--accent);font:13px/1.7 ui-monospace,monospace;margin-top:16px;overflow-wrap:anywhere}
.notice{border:1px solid #705d35;background:#241f16;border-radius:14px;padding:18px;color:#f4dfb5;margin-top:22px}
footer{border-top:1px solid var(--line);margin-top:42px;padding-top:18px;color:var(--muted);font-size:12px}
</style></head><body><main>
<div class="top"><div class="brand">APEX<span style="color:var(--accent)">.</span></div><div class="pill">PERSONAL WORKBENCH · NO LIVE TRADING</div></div>
<h1>Research first.<br><span>Evidence over hype.</span></h1>
<p class="lead">A private-use research workbench foundation for global Forex and Indian exchange-traded currency derivatives. Run a basic historical OHLC backtest using your own CSV data. No broker connection, live orders, or market feed.</p>
<div class="grid">
<section class="card"><h2>GLOBAL FOREX</h2><div class="state">Research only</div><div class="muted">Separate market profile · execution off</div></section>
<section class="card"><h2>INDIA CURRENCY DERIVATIVES</h2><div class="state">Research only</div><div class="muted">Separate market profile · execution off</div></section>
<section class="card"><h2>BACKTESTER</h2><div class="state">OHLC · next-bar fills</div><div class="muted">Fees and slippage are configurable</div></section>
<section class="card"><h2>PAPER LEDGER</h2><div class="state">Local module</div><div class="muted">Explicit confirmation required; not exposed on this public page</div></section>
</div>
<section class="work"><h2>Historical backtest</h2>
<p class="muted">Upload a CSV with columns timestamp, open, high, low, close and optional volume. Timestamps must include a timezone (for example 2026-01-01T09:15:00+05:30). Use clean, chronological candles from a source you are licensed to use.</p>
<input id="file" type="file" accept=".csv,text/csv">
<div class="fields">
<label>Fast average<input id="fast" type="number" min="1" max="100" value="5"></label>
<label>Slow average<input id="slow" type="number" min="2" max="500" value="20"></label>
<label>Fee (bps/side)<input id="fee" type="number" min="0" step="0.1" value="0"></label>
<label>Slippage (bps/side)<input id="slip" type="number" min="0" step="0.1" value="0"></label>
<label>Quantity<input id="qty" type="number" min="0.000001" step="any" value="1"></label>
</div><button id="run">Run backtest</button><div id="result" aria-live="polite"></div>
</section>
<div class="notice"><strong>Important limitations</strong><br>Backtest P&L is in the instrument's quote currency and excludes contract multipliers, financing, swaps, margin, taxes, exchange/broker fees and currency conversion. This is not a realistic exchange-specific simulation. Historical results do not predict future returns. Do not use this for position sizing or live trading.</div>
<footer>APEX · Personal research build · Live execution permanently disabled in this release · <a href="/healthz" style="color:var(--accent)">health</a></footer>
</main>
<script>
const fileInput=document.getElementById('file'),out=document.getElementById('result'),run=document.getElementById('run');
function parseCSV(text){
 const lines=text.trim().split(/\r?\n/); if(lines.length<3)throw Error('CSV needs a header and at least two candles');
 const headers=lines[0].split(',').map(x=>x.trim().toLowerCase());
 for(const k of ['timestamp','open','high','low','close'])if(!headers.includes(k))throw Error('Missing column: '+k);
 return lines.slice(1).filter(Boolean).map((line,i)=>{const cols=line.split(',');const row={};headers.forEach((h,j)=>row[h]=cols[j]?.trim());return {timestamp:row.timestamp,open:row.open,high:row.high,low:row.low,close:row.close,volume:row.volume||'0'};});
}
run.addEventListener('click',async()=>{
 try{
  if(!fileInput.files.length)throw Error('Choose a CSV file first');
  run.disabled=true;out.textContent='Running…';
  const raw=await fileInput.files[0].text(),candles=parseCSV(raw);
  const payload={candles,fast_window:Number(document.getElementById('fast').value),slow_window:Number(document.getElementById('slow').value),fee_bps_per_side:Number(document.getElementById('fee').value),slippage_bps_per_side:Number(document.getElementById('slip').value),quantity:Number(document.getElementById('qty').value)};
  const response=await fetch('/api/backtest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const data=await response.json();if(!response.ok)throw Error(data.error||'Backtest failed');
  out.textContent=JSON.stringify(data,null,2);
 }catch(e){out.textContent='Error: '+e.message;}finally{run.disabled=false;}
});
</script></body></html>"""

def _backtest(payload):
    from apex.backtest import BacktestConfig, run_backtest
    from apex.data_validation import Candle
    from apex.strategies import MovingAverageCross
    candles = []
    for row in payload.get("candles", []):
        stamp = datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00"))
        candles.append(Candle(stamp, Decimal(str(row["open"])), Decimal(str(row["high"])),
                              Decimal(str(row["low"])), Decimal(str(row["close"])),
                              Decimal(str(row.get("volume", "0")))))
    fast, slow = int(payload.get("fast_window", 5)), int(payload.get("slow_window", 20))
    if len(candles) > 100000:
        raise ValueError("Maximum upload is 100000 candles")
    strategy = MovingAverageCross(fast_window=fast, slow_window=slow)
    config = BacktestConfig(quantity=Decimal(str(payload.get("quantity", 1))),
        fee_bps_per_side=Decimal(str(payload.get("fee_bps_per_side", 0))),
        slippage_bps_per_side=Decimal(str(payload.get("slippage_bps_per_side", 0))))
    result = run_backtest(candles, strategy, config)
    def dec(value):
        return str(value) if value is not None else None
    return {
        "strategy": result.strategy_id, "bars": result.bars, "trade_count": len(result.trades),
        "initial_equity": dec(result.initial_equity), "final_equity": dec(result.final_equity),
        "net_pnl": dec(result.net_pnl), "return_fraction": dec(result.return_fraction),
        "max_drawdown_fraction": dec(result.max_drawdown_fraction), "win_rate": dec(result.win_rate),
        "profit_factor": dec(result.profit_factor), "assumptions": result.assumptions,
        "trades": [{"side":t.side,"entry_time":t.entry_time,"exit_time":t.exit_time,
          "entry_price":dec(t.entry_price),"exit_price":dec(t.exit_price),"gross_pnl":dec(t.gross_pnl),
          "fees":dec(t.fees),"net_pnl":dec(t.net_pnl),"exit_reason":t.exit_reason} for t in result.trades]
    }

class Handler(BaseHTTPRequestHandler):
    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        configured = os.environ.get("APEX_ACCESS_PASSWORD", "")
        if not configured:
            self._send(503, "text/plain; charset=utf-8",
                       b"APEX is locked: set APEX_ACCESS_PASSWORD in the Render environment first.")
            return False
        header = self.headers.get("Authorization", "")
        try:
            scheme, encoded = header.split(" ", 1)
            if scheme.lower() != "basic":
                raise ValueError("unsupported auth scheme")
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
            username, password = decoded.split(":", 1)
        except Exception:
            username, password = "", ""
        valid_user = hmac.compare_digest(username.encode(), b"apex")
        valid_password = hmac.compare_digest(password.encode(), configured.encode())
        if not (valid_user and valid_password):
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="APEX Personal Workbench", charset="UTF-8"')
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return False
        return True

    def do_GET(self):
        if not self._authorized():
            return
        path = urlsplit(self.path).path
        if path == "/healthz":
            body = json.dumps({"status":"ok","mode":"research","live_trading_enabled":False}).encode()
            self._send(200, "application/json", body)
        else:
            self._send(200, "text/html; charset=utf-8", PAGE.encode())

    def do_POST(self):
        if not self._authorized():
            return
        if urlsplit(self.path).path != "/api/backtest":
            self._send(404, "application/json", b'{"error":"not_found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 15_000_000:
                raise ValueError("Request must be between 1 byte and 15 MB")
            payload = json.loads(self.rfile.read(length))
            result = _backtest(payload)
            body = json.dumps(result, allow_nan=False).encode()
            self._send(200, "application/json", body)
        except (ValueError, KeyError, TypeError, InvalidOperation, ArithmeticError) as exc:
            self._send(400, "application/json", json.dumps({"error":str(exc)}).encode())
        except Exception:
            self._send(500, "application/json", b'{"error":"internal_error"}')

    def log_message(self, fmt, *args):
        print(fmt % args)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
