# Level 3 forward-validation evidence collector

This is a conservative evidence-ingestion and audit tool. It does not fetch market data,
place orders, create signals, or enable any broker.

## Evidence contract and limitations

Each JSONL observation must contain an ISO-8601 timestamp with an explicit offset,
instrument, provider, source, interval, strategy ID/version and positive price.

The collector generates its own UTC ingestion timestamp and rejects observations older
than ten minutes or more than one minute in the future. This prevents a batch of old
historical rows from being imported later and counted as fresh forward evidence.
Duplicate instrument/interval/timestamp rows are ignored. Reports also fail closed with
`BLOCKED_STALE` when the newest verified observation is older than the configured ten-minute
freshness limit (or exceeds the allowed future tolerance); a historic 30-day streak cannot
remain green after collection stops. SQLite uses WAL and FULL synchronous mode; records are
SHA-256 hash chained. Appends acquire `BEGIN IMMEDIATE` before reading the previous hash and
writing the next row, serializing chain-tail selection across concurrent SQLite writers.

**Freshness is not authenticity.** The default CLI has no provider-specific verifier.
It can retain fresh observations as unverified candidates, but those candidates do not
contribute to the verified UTC-day streak and the gate reports BLOCKED_PROVENANCE.
A provider-specific verifier must independently validate the provider's signed payload,
signature or equivalent authenticated source evidence before any row can be marked
verified. The generic CLI intentionally does not provide or simulate such a verifier.
A test callback demonstrates the interface only; it is not production provider verification.

Do not set a JSON field to claim verification. Verification is determined only by the
trusted verifier callback configured by an operator-controlled integration. Keep original
provider payloads, signatures, provider event IDs, collection logs and licensing evidence
outside the database and retain them with backups. A hash chain proves stored-record
integrity, not the truth or origin of market data.

## Run

\`\`\`bash
python -m research.forward_validation observations.jsonl \\
  --db var/forward_validation.sqlite3 \\
  --instrument EURUSD --provider YOUR_PROVIDER --interval 1h \\
  --strategy-id sma-crossover-long --strategy-version 1.0.0 \\
  --required-days 30
\`\`\`

The default CLI will report BLOCKED_PROVENANCE until a provider-specific verifier is
implemented and independently reviewed. A coverage pass is necessary but not sufficient
for Level 3 certification. Independent review, complete fill/cost/position reconciliation,
spread-aware execution, instrument contract specifications, portfolio risk limits,
out-of-sample evaluation and failure/recovery tests remain required.

## Operational safety

- Use a durable local or managed persistent volume; never use ephemeral CI storage.
- Use one instrument/provider/interval/strategy version per database.
- Keep the kill switch engaged and Deriv/MT5/wallet/live adapters disabled.
- Never put API keys or credentials in JSONL, SQLite metadata, source control or CI logs.
- Historical replay, CI fixtures, synthetic/demo data and simulated trades never count.
