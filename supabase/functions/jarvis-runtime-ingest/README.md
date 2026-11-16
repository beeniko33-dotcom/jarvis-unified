# Jarvis runtime ingest

This Edge Function accepts authenticated service-role requests for paper-mode worker heartbeats, market observations, and operational audit events.

- Supabase gateway JWT verification is enabled; the handler additionally requires a `service_role` JWT claim.
- It writes only to the private `jarvis_private` schema using the server-side `SUPABASE_DB_URL` connection.
- Worker mode is constrained to `paper`.
- Market observations are stamped `candidate_unverified`; this endpoint does not certify a data vendor, license, or source authenticity.
- Audit payloads reject credential-like field names and are hashed before insertion.
- It does not place, route, or authorize orders. The Python trading worker remains a separate process and must report heartbeats and evidence to this endpoint.

## Request examples

Heartbeat:

```json
{"kind":"heartbeat","worker_id":"jarvis-paper-01","worker_type":"paper-trader","software_version":"0.1.0","git_commit":"<commit>","health":"healthy","details":{"account_id":"<persistent-account-id>"}}
```

Market observation:

```json
{"kind":"market_observation","source_id":"<licensed-provider-id>","symbol":"EURUSD","timeframe":"1m","event_time":"2026-11-16T12:00:00Z","values_json":{"open":"1.0","high":"1.1","low":"0.9","close":"1.05","volume":"0"}}
```

Audit event:

```json
{"kind":"audit_event","event_type":"paper_session_started","component":"paper_runner","payload":{"mode":"paper","account_id":"<persistent-account-id>"}}
```

Send `Authorization: Bearer <service-role JWT>` and `Content-Type: application/json`. Never put service-role credentials in browser code, Git, logs, or chat.
