# Binance candidate market-analysis function

This Edge Function fetches Binance public Spot server time and the newest 100 BTCUSDT 5-minute klines, excludes any still-open candle, checks OHLC consistency and freshness, computes SMA20/SMA50/Wilder RSI14, and stores one timestamped candidate observation plus an idempotent research-only directional signal.

## Safety and trust

- Uses public Binance market-data endpoints; no Binance account or API key is needed. Supabase invocation still requires a verified operator/service-role JWT.
- Provider data remains `candidate_unverified` / `unverified_market_data`; `evidence_credit=false`.
- Signal direction is research output, not a trade instruction.
- Risk gate is blocked; position size is zero; paper execution is disabled; no live orders can be created.
- The function requires a valid Supabase JWT (`verify_jwt=true`), checks the verified JWT role claim, and checks the JWT subject against `public.operator_allowlist`. Only an allowlisted authenticated operator or a service-role scheduler can invoke the collector. Anonymous and ordinary authenticated users are rejected.
- The latest closed 5-minute candle must be no more than 360 seconds old and local clock skew must be within 30 seconds.
- This does not replace the 30-day forward validation or resolve the provider provenance gate.

## Deploy and invoke

Deploy as `market-analysis` with JWT verification enabled. Invoke with an authenticated operator session using POST and an empty JSON object. The repository workflow `.github/workflows/binance-market-analysis.yml` polls every five minutes using the existing GitHub Actions secrets `JARVIS_SUPABASE_URL` and `JARVIS_SUPABASE_SERVICE_ROLE_KEY`. If either secret is absent, the workflow skips collection and records `SKIPPED_NOT_CONFIGURED`. Never place the service-role key in client code. Review the workflow run artifact and Supabase ledger counts to confirm actual persistence.

## Strategy

Long bias: SMA20 > SMA50, close > SMA20, RSI14 in [50,70).
Short bias: SMA20 < SMA50, close < SMA20, RSI14 in (30,50].
Otherwise neutral. This simple baseline requires out-of-sample evaluation before any paper eligibility.
