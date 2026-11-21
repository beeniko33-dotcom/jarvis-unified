# Twelve Data Forex provider qualification

## Decision

Twelve Data is the first external Forex market-data provider to qualify for **private, internal research validation**. It is not yet an approved production/public data source, and no observation from this adapter is considered provenance-verified.

Twelve Data describes its Forex API v2 as a composite feed aggregating more than 60 liquidity providers, prime brokers and central banks. It documents minute-updated mid-price streaming and OHLC candles from 1-minute to 1-month intervals. Supported coverage includes major, minor and exotic fiat pairs.

References:
- Forex API v2 source, coverage and delivery: https://support.twelvedata.com/en/articles/12520817-forex-api-v2
- Time-series request and interval documentation: https://twelvedata.com/docs
- Timezone parameter: https://support.twelvedata.com/en/articles/5745849-timezones
- Basic plan pricing and API quota: https://twelvedata.com/pricing
- Commercial and personal usage: https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage
- Terms of Use: https://twelvedata.com/terms

## Free-tier and licensing boundary

The current pricing page advertises a Basic plan at $0 with 8 API credits per minute and 800 API credits per day. Entitlements can vary by endpoint and account, so the account must be checked before collection.

The free/individual plans are for personal or internal non-commercial use. They do not permit commercial display to third parties or redistribution. Twelve Data's terms also prohibit use of free-tier data for commercial purposes. Therefore:

- Keep the API key in a server-side secret named `TWELVE_DATA_API_KEY`.
- Do not place the key in GitHub source, browser JavaScript, Pages configuration, or chat.
- Use the adapter only for private operator research, development and QA.
- Do not expose raw quotes, candles or data-derived public dashboards to Jarvis users on the free plan.
- Before public/commercial display, request the appropriate business entitlement, regional approval for non-US FX data, and any required redistribution licence. No paid plan or licence is being purchased by this change.

## Adapter behavior

`research/twelvedata_feed.py`:

- Requests a specific ISO-style currency pair and intraday interval from the official `/time_series` endpoint.
- Explicitly requests UTC timestamps, ascending order and OHLC values.
- Validates returned symbol, interval, candle count, timezone-aware timestamps, chronological uniqueness, positive prices and OHLC invariants.
- Rejects provider error, quota and entitlement responses instead of treating HTTP 200 as usable data.
- Produces a raw-response SHA-256 for integrity/deduplication only. This hash does not authenticate the provider or prove the origin of individual observations.
- Labels every result `candidate_unverified`, `provenance_verified=false`, and `evidence_credit=false`.
- Does not persist observations, create trading signals, publish data, or submit orders.

## Live validation still required

A real provider test cannot be completed until an owner-controlled Twelve Data API key is placed in the QA server secret store. Set `TWELVE_DATA_API_KEY` only in the isolated QA Edge Function / server environment. Do not send it in chat or add it to GitHub source.

For the first validation, request EUR/USD 5-minute candles and record:
1. Provider HTTP result and entitlement status.
2. Returned pair, interval, instrument type and timezone semantics.
3. Latest provider candle timestamp versus collector UTC time.
4. Chronological uniqueness, gaps, stale/future candles and OHLC consistency.
5. Raw response digest and exact retrieval time.
6. Whether the account's actual plan permits the requested interval and retention.

The adapter's deterministic tests use mocked provider responses; they are not a substitute for this live API check.

## Provenance decision

Twelve Data's aggregate vendor feed is a genuine external Forex data service, but an HTTPS response and payload hash do not establish cryptographic authenticity of each underlying tick. The provider's own description of source aggregation is useful lineage information, not an independently auditable per-message signature or contractual event trail.

Accordingly, Twelve Data may qualify as a **research/reference provider** after live API and account-entitlement checks. It does not satisfy Jarvis's separate Level 3 provenance gate for verified forward evidence. Keep the 30-day evidence clock stopped until the existing signature or contractually auditable source-lineage requirements are independently met.
