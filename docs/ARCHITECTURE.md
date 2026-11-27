# Architecture and trust boundaries

AI outputs are untrusted research proposals. Strategy implementations are deterministic code. RiskGuardian is deterministic and independent. Phase 0 contains no execution adapter.

Market profiles keep global Forex and Indian exchange-traded currency derivatives separate. Future adapters must separately implement contract specs, calendars, sessions, costs, pricing conventions, data licensing and legal eligibility checks.

Data flow (future): provider/importer -> normalized candles -> validation -> research -> backtesting -> paper simulator -> reports.

Safety invariants: default live_trading_enabled is false; both market profiles disable execution; no broker credentials, network clients or order-routing modules are included.

Known limitation: risk amount currently uses simplified price-distance * quantity. It is not contract-aware and must be replaced with market-specific valuation and FX conversion before meaningful portfolio simulation.
