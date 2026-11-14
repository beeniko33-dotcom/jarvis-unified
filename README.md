# Jarvis Unified

**Single source of truth** for the Jarvis trading ecosystem.

The repository consolidates the core application, Deriv execution research, signal logic, dashboard, AI/research concepts and the advanced scraper migration foundation.

## Core principles

1. **Paper-first** — live trading is disabled; paper validation precedes any production discussion.
2. **Risk is king** — every new order must pass the central risk gate.
3. **Broker-agnostic** — strategies use a common broker contract.
4. **Preserve capability** — migrate the complete legitimate scraper feature set and retain source history; do not discard the original repository.
5. **No secrets in git** — credentials belong in local environment configuration, never commits.

## Maturity

**Last confirmed baseline: Level 2 — Operational tooling.**

The `level-3-paper-validation` branch adds fill-level account snapshots and ledger analytics. The `level-3-research-engine` branch adds a restart-safe SQLite historical-data paper replay engine, a versioned SMA reference strategy, source-data hashing and a hash-chained event audit. These are Level 3 preparation, not a Level 3 performance claim. Level 3 requires sustained multi-day evidence and review.

## Quick start

```bash
python main.py --check
python main.py --health
python main.py --summary
python main.py --report
python main.py --demo
python -m unittest discover -s tests -v
python scripts/diagnose.py
python scripts/paper_session.py --allow-entries --ledger var/paper_ledger.jsonl
python scripts/paper_report.py var/paper_ledger.jsonl --min-days 30
python main.py --import-paper-ledger --paper-ledger-db var/paper/paper.sqlite --learning-db var/learning/observations.sqlite3
python main.py --paper-outcomes --learning-db var/learning/observations.sqlite3
python main.py --shadow-review --learning-db var/learning/observations.sqlite3 --shadow-db var/learning/shadow_candidates.sqlite3
python main.py --shadow-history --shadow-db var/learning/shadow_candidates.sqlite3
# Append a human review decision; valid values: accepted_for_manual_review, declined, needs_more_evidence
python main.py --shadow-decision CANDIDATE_ID needs_more_evidence --shadow-db var/learning/shadow_candidates.sqlite3
python main.py --experiment-list --experience-db var/learning/experience.sqlite3
python main.py --experiment-verify EXPERIMENT_ID --experience-db var/learning/experience.sqlite3
python main.py --experiment-verify-sources EXPERIMENT_ID /local/paper-ledger.sqlite /local/learning-journal.sqlite --experience-db var/learning/experience.sqlite3
python main.py --experiment-compare LEFT_ID RIGHT_ID --experience-db var/learning/experience.sqlite3
```

The learning commands import an existing persistent paper-broker SQLite ledger into a separate, hash-chained learning journal, then print loss-inclusive outcome analytics. The importer opens the source ledger read-only and rejects broken hash chains or snapshot mismatches before importing. Repeated imports are idempotent. Reports retain realized P&L and commissions separately, show net results after costs, and calculate drawdown only when source snapshots contain the required marks and account data. P&L is attributed to ledger events and UTC days, not individual entry orders where the source ledger cannot prove that allocation.

`--shadow-review` generates persistent, evidence-linked review suggestions for negative net outcomes, partial fills, rejections, drawdown and missing mark coverage. Each candidate records its evidence, sample size, confidence label, review date and expiry. The advisor is descriptive and advisory only: it cannot change strategies, parameters, risk limits, kill switches, permissions or execution. Use `--shadow-history` to inspect candidate and owner-review history, and `--shadow-decision` to append a human review outcome. An accepted review is not strategy approval or deployment.

The experiment registry stores canonical local config snapshots (credential-like keys are rejected), config and metrics hashes, dataset identity, time window and optional SHA-256 references to the exact paper-ledger and learning-journal files. `--experiment-verify` checks stored config and metrics integrity. `--experiment-verify-sources` hashes the actual local files and appends an immutable match/mismatch record; local file paths are not stored. `--experiment-compare` emits metric deltas only when both records have matching dataset identity/hash, verified data-status labels, identical time windows, matching source-file hashes and successful local source-artifact verification. Otherwise it returns explicit reasons and does not rank the experiments. A matching file hash proves byte identity with the recorded reference, not independent provider authenticity; upstream provenance gates remain authoritative. Legacy records without config snapshots fail closed on integrity verification. The registry does not calculate strategy performance from raw fills, promote candidates, or influence the Level 3 evidence clock.

`--demo` runs one risk-gated in-memory paper entry, demonstrates a rejected oversized order, closes the demo position, and leaves the kill switch engaged. It does not create forward-validation evidence.

## Architecture and safety

- Paper broker and central risk-gated execution
- Localhost-only read-only status API
- SSRF-safe scraper fetch foundation
- Deriv and MT5 adapters intentionally disabled
- No live execution path

See `docs/START_HERE.md`, `docs/ARCHITECTURE.md`, `docs/MATURITY.md`, `docs/RISK.md`, `docs/SCRAPER.md`, and `docs/LEVEL_3_RUNBOOK.md`.

**Experimental research software. No signal or strategy guarantees profit.**
