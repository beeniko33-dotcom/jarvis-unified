# Level 3 forward-validation evidence collector

This is a paper-evidence ingestion and audit tool. It does not connect to a market-data provider,
place orders, create signals, or enable any broker. A separate operator-controlled collector
must obtain observations from a licensed/authorized provider and write JSONL records.

## Evidence contract

Each line in the input JSONL must contain:

- `observed_at`: ISO-8601 timestamp with explicit timezone/offset
- `instrument`, `provider`, `source`, `interval`
- `strategy_id`, `strategy_version`
- `price`: positive decimal

The database is bound to one explicit instrument, provider, interval and strategy version.
Timestamps are normalized to UTC. Duplicate instrument/interval/timestamp records are ignored.
Records are append-only and SHA-256 hash chained. SQLite WAL and FULL synchronous mode are used.
Back up the database and original provider payloads together; retain provider licensing and
collection logs outside this database.

## Run

```bash
python -m research.forward_validation observations.jsonl \
  --db var/forward_validation.sqlite3 \
  --instrument EURUSD --provider YOUR_PROVIDER --interval 1h \
  --strategy-id sma-crossover-long --strategy-version 1.0.0 \
  --required-days 30
```

The command exits non-zero until the latest observation day has a 30-day uninterrupted UTC
calendar-day streak. A day counts only when at least one observation exists for that day.
Missing days reset the latest streak. The tool does not infer observations, backfill gaps,
or count historical CSV replay, synthetic fixtures, CI sessions, or simulated trades as forward
evidence. Run it repeatedly against newly collected JSONL records and retain each original file.

A passing coverage gate is necessary but not sufficient for Level 3 certification. Independent
review, complete fill/cost/position reconciliation, spread-aware execution, instrument contract
specifications, portfolio risk limits, out-of-sample evaluation and failure/recovery tests remain
required. The report deliberately keeps `level_3_certification=false`.

## Operational safety

- Use a durable local or managed persistent volume; never use ephemeral CI `/tmp` storage.
- Configure exactly one instrument/provider/interval/strategy version per database.
- Keep the kill switch engaged and Deriv/MT5/wallet/live adapters disabled.
- Never put API keys or credentials in JSONL, SQLite metadata, source control or CI logs.
- Do not treat this collector as a live data feed; it only audits records supplied to it.
