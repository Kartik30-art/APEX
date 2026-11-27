from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit
import json
import os

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>APEX | Market Research</title>
<style>
:root{color-scheme:dark;--bg:#090d16;--panel:#111a2b;--line:#26344c;--muted:#9aa9bf;--text:#edf3ff;--accent:#70d6b2;--warn:#f3c875}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% 0%,#172843 0,transparent 38%),var(--bg);color:var(--text);font:15px/1.6 Inter,system-ui,sans-serif}
main{max-width:1080px;margin:auto;padding:48px 22px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
.brand{font-weight:800;letter-spacing:.2em;font-size:22px}.pill{border:1px solid #397d69;color:var(--accent);padding:6px 12px;border-radius:99px;font-size:12px}
h1{font-size:clamp(36px,7vw,64px);line-height:1.03;letter-spacing:-.04em;margin:70px 0 18px}h1 span{color:var(--accent)}
.lead{color:var(--muted);max-width:680px;font-size:17px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:36px 0}
.card{background:linear-gradient(145deg,#152238,#101827);border:1px solid var(--line);border-radius:16px;padding:20px}.card h2{font-size:15px;margin:0 0 12px}.state{font-size:21px;font-weight:700}.muted{color:var(--muted);font-size:13px}
.notice{border:1px solid #705d35;background:#241f16;border-radius:14px;padding:18px;color:#f4dfb5;margin-top:22px}
footer{border-top:1px solid var(--line);margin-top:56px;padding-top:18px;color:var(--muted);font-size:12px}
</style></head><body><main>
<div class="top"><div class="brand">APEX<span style="color:var(--accent)">.</span></div><div class="pill">RESEARCH MODE · LIVE EXECUTION OFF</div></div>
<h1>Think clearly.<br><span>Trade responsibly.</span></h1>
<p class="lead">An AI-assisted market research foundation for global Forex and Indian exchange-traded currency derivatives. Separate market engines, deterministic risk checks, and auditable research come before any paper simulation.</p>
<div class="grid">
<section class="card"><h2>GLOBAL FOREX</h2><div class="state">Research only</div><div class="muted">Execution disabled · UTC profile</div></section>
<section class="card"><h2>INDIA CURRENCY DERIVATIVES</h2><div class="state">Research only</div><div class="muted">Execution disabled · Asia/Kolkata profile</div></section>
<section class="card"><h2>RISK GUARDIAN</h2><div class="state">Baseline ready</div><div class="muted">Deterministic checks · no order routing</div></section>
<section class="card"><h2>DATA CONNECTIONS</h2><div class="state">Not connected</div><div class="muted">No live or licensed market feed configured</div></section>
</div>
<div class="notice"><strong>Safety notice</strong><br>This is the initial software foundation, not a trading recommendation or a completed trading system. No broker is connected, no orders can be placed, and no profitability is claimed. Risk sizing remains simplified and is not suitable for real positions.</div>
<footer>APEX · Phase 0 foundation · Health endpoint: /healthz</footer>
</main></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            body = json.dumps({"status": "ok", "mode": "research", "live_trading_enabled": False}).encode()
            content_type = "application/json"
            status = 200
        else:
            # Keep the dashboard reachable for deep links, query strings and browser probes.
            body = PAGE.encode()
            content_type = "text/html; charset=utf-8"
            status = 200
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, fmt, *args):
        print(fmt % args)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
