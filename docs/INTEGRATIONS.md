# APEX integrations and assumptions

## Capability status

| Capability | Code delivered | External activation |
|---|---|---|
| Global FX data | Twelve Data REST adapter | API key and vendor entitlement/licence |
| India exchange data | Licensed JSON vendor adapter | User-selected licensed vendor endpoint and token |
| OpenAI, Gemini, Anthropic | Advisory-only REST clients | Each provider API key; usage may be billed |
| INR futures valuation | Contract multiplier, quote convention and tick value | Verify current contract master and expiry |
| Costs | Configurable fee schedule | Current broker/exchange/tax inputs; defaults zero |
| SQLite | WAL, candles, paper orders, audit and research tables | Persistent mount or managed DB |
| Backup | Online backup, integrity check, SHA-256 | Copy to separate durable destination |
| Broker | Paper broker + adapter protocol | Broker account/API setup |
| Live orders | Hard disabled | Not implemented; cannot be enabled by env flag |

## Global Forex data

TwelveDataForexProvider reads TWELVEDATA_API_KEY and supports historical OHLC time-series calls. TwelveDataForexStream opens an opt-in WebSocket for live price ticks; only symbols and bid/ask fields actually returned by the vendor are exposed. The dashboard lets you start/stop a stream and inspect its latest in-memory ticks. Confirm the vendor plan permits your intended use. The free Basic plan limits WebSocket use to trial symbols (up to 8 simultaneous subscriptions); full WebSocket coverage requires a higher tier. Each subscribed symbol consumes a WebSocket credit. No stream starts automatically and Render free hosting cannot guarantee 24/7 connections. Docs: https://twelvedata.com/docs/websocket/websocket-getting-started

## India exchange data

LicensedIndiaJSONProvider reads APEX_INDIA_DATA_URL and optional APEX_INDIA_DATA_TOKEN. The endpoint must return a JSON list or an object with values array, containing timestamp/open/high/low/close and optional volume. No exchange-page scraping or licence circumvention.

## AI research

Set GEMINI_API_KEY for Gemini, or the corresponding provider key for other models. Defaults use the OpenAI Responses API (`gpt-6.2-astra`), Gemini `generateContent` (`gemini-3.8-flash`) and Anthropic Messages API (`claude-sonnet-5-5`). Override model IDs with OPENAI_MODEL, GEMINI_MODEL and ANTHROPIC_MODEL after checking provider availability in your account. Gemini calls are only attempted when its key is configured. OpenAI and Anthropic are treated as paid APIs and are blocked by default; explicitly set `APEX_ALLOW_PAID_AI=true` only after approving charges. `AIResearch.compare()` invokes only eligible configured providers. ChatGPT subscriptions do not automatically include API credits. AI output is advisory and never routed to a broker.

Official docs: https://developers.openai.com/api/reference ; https://ai.google.dev/api ; https://platform.claude.com/docs/en/claude_api_primer

## NSE INR futures reference metadata

The initial reference table encodes USDINR, EURINR and GBPINR as 1,000 base-currency units per contract; JPYINR as 100,000 JPY quoted per 100 JPY; tick size INR 0.0025; derived tick value INR 2.50 per contract for these four pairs. Source: NSE India, Contract Specifications - Futures & Options on INR pairs: https://www.nseindia.com/static/products-services/currency-derivatives-contract-specification-inr

This is a reference snapshot, not a live contract master. Verify current symbol, expiry, lot and tick against the current exchange contract master. Options valuation is not implemented.

## Costs

FeeSchedule accepts explicit brokerage, exchange, SEBI, stamp, transaction-tax and GST inputs. Defaults are zero for software tests, not actual charge estimates. The generic model is simplified; actual tax bases differ. Obtain current broker tariff/contract note and encode its exact bases before relying on net P&L.

## Durable storage and backup

APEXStore defaults to data/apex.sqlite3; set APEX_DATA_DIR to a persistent mount. backup(path) uses SQLite online backup and checks PRAGMA integrity_check, returning SHA-256. The dashboard's explicit backup action can upload a verified snapshot to AWS S3 or an S3-compatible endpoint (including R2) when APEX_S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, optional AWS_DEFAULT_REGION, and optional APEX_S3_ENDPOINT_URL are configured. Set APEX_S3_PREFIX if desired. No upload occurs automatically. Object storage may incur charges; create and configure your own bucket and lifecycle policy. Render free service storage is ephemeral, so code alone does not make the live database durable.

## Broker and Indian regulatory gate

PaperBroker writes a unique client order ID to SQLite. LiveBrokerGateway always raises LiveExecutionLocked; no environment variable unlock exists.

RBI FAQ states residents may undertake forex only with authorised persons and for permitted purposes; electronic transactions must use RBI-authorised ETPs or recognised exchanges under applicable conditions. RBI's exchange-traded derivative direction lists permitted pairs and conditions for INR-involving derivatives. Verify current RBI master direction, exchange circulars, broker eligibility and personal circumstances before any real-world use.

Official references: https://rbi.org.in/Scripts/FAQView.aspx?Id=146 ; https://rbi.org.in/scripts/FS_Notification.aspx?Id=12594&Mode=0&fn=6 ; https://www.nseindia.com/static/products-services/currency-derivatives-contract-specification-inr

## Deployment limitations

Render free filesystem is ephemeral, instances sleep when idle, and no always-on or durable-storage promise is made. A persistent disk or managed DB requires a paid plan; APEX does not provision one under the zero-rupee budget. Never store API keys in GitHub, source files or chat.
