# Persistent paper ledger

## Purpose and boundaries

`PersistentPaperBroker` is an opt-in SQLite-backed simulation adapter. It is not a live
broker and has no network or account-authentication capability. The default in-memory
`PaperBroker` remains available for unit tests.

## State and recovery

The persistent adapter stores the complete paper account snapshot: balance, positions,
average prices and open timestamps, order results, client-order idempotency fingerprints,
commissions, realized PnL and last marks. Each mutation obtains SQLite's
`BEGIN IMMEDIATE` writer reservation, reloads the authoritative snapshot, applies the
operation, and commits the new snapshot plus a SHA-256 chained event in one transaction.
This serializes writes across independent connections and processes sharing the same DB.

On startup and before reads/writes, the adapter verifies the event chain and checks that the
state snapshot exactly matches the final event. A broken chain, missing state or mismatch
raises an integrity error; it does not silently reset or reconstruct from partial data.
Back up the database using SQLite's online backup facilities while the application is
running; do not copy only the main database file while WAL writes may be pending.

## UTC daily risk accounting

Every event is stamped using an injected timezone-aware clock and assigned a UTC calendar
day. Daily realized PnL and commissions are calculated from event deltas for that UTC day.
The lifetime totals remain separately available. At UTC midnight, the daily aggregates roll
over without resetting lifetime account state. The execution service uses daily aggregates
only when the broker explicitly marks them available.

## Use

```python
from decimal import Decimal
from brokers.paper import PersistentPaperBroker
from core.execution import ExecutionService
from core.risk import RiskEngine, RiskLimits

broker = PersistentPaperBroker(
    Decimal("1000"),
    database_path="var/paper-ledger.sqlite3",
)
risk = RiskEngine(RiskLimits(kill_switch=True))
service = ExecutionService(broker, risk)
# Keep the kill switch engaged unless an explicit paper-test operator action is made.
```

Use one shared database path for cooperating processes. Treat the database and backups as
sensitive operational records. This adapter remains paper-only.

## Quote freshness and exposure gates

The risk engine can require `quote_timestamp` and `quote_source` in each order's metadata.
When a timestamp is present, it must be timezone-aware, not in the future, and no older than
`RiskLimits.max_quote_age_seconds`. Set `require_quote_metadata=True` to reject missing
metadata. The timestamp and source are provenance metadata only: they do not cryptographically
authenticate a provider or turn a public feed into verified evidence. Provider identity,
transport/session binding and independent provenance verification remain separate controls.

An optional `max_symbol_exposure` caps current absolute position notional plus proposed order
notional. `ExecutionService` supplies existing exposure from broker positions. This is a
conservative average-entry-price estimate, not a live mark, margin or correlated-risk model.

## Known gaps

Peak-equity drawdown, cross-symbol/correlated exposure reservations, partial-fill simulation,
crash-injection tests and independent external ledger attestation remain outstanding.
These controls are required before any higher-level validation claim. No Level 3
certification is implied.
