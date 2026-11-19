# Gate.io candidate market-analysis integration

Jarvis Unified now uses Gate.io public Spot REST for BTC/USDT 5-minute completed candles and demo-market last-trade marks.

## Endpoints

- `GET https://api.gateio.ws/api/v4/spot/time`
- `GET /spot/candlesticks?currency_pair=BTC_USDT&interval=5m&limit=100`
- `GET /spot/trades?currency_pair=...&limit=1`
- `GET /spot/tickers?currency_pair=...`
- `GET /spot/order_book?currency_pair=...&limit=1`

These market-data endpoints are public and do not require a Gate.io API token. The collector intentionally does not use private account endpoints or authenticated permissions.

## Trust and execution gates

- Provider observations remain `candidate_unverified` / `unverified_market_data`.
- `provenance_verified=false` and `evidence_credit=false`.
- Signals are research output only.
- Position size is zero; risk gate is blocked; paper execution remains disabled in market-analysis.
- Demo trading remains a simulated ledger path only and uses fresh Gate.io public trades for marks.
- No live order, account access, wallet connection, or token use is performed.
- This does not establish the required forward-validation period or Level 3 certification.

## Run read-only smoke

`python -m scripts.gateio_public_smoke --symbol BTCUSDT --interval 1m`

The scheduled GitHub workflow `.github/workflows/gateio-readonly-market-smoke.yml` runs hourly. The five-minute authenticated Supabase collector workflow uses the existing `JARVIS_SUPABASE_URL` and `JARVIS_SUPABASE_SERVICE_ROLE_KEY` repository secrets. Missing secrets result in an explicit skipped report.

## API token

No token is needed for these public endpoints. Do not put a Gate.io token in repository code, client-side code, logs, chat, or workflow output. Any future private API use must be a separate reviewed integration with read-only account permissions and IP restrictions; trading permissions must remain disabled.
