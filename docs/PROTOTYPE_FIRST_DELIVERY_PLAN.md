# Jarvis Unified — Prototype-First Delivery Plan

**Owner-approved direction (14 November 2026):** finish a useful personal-use prototype before undertaking the 30-day Level 3 paper-validation programme. The owner has stated that the system is for personal use and is not intended for sale.

This changes delivery order and prototype acceptance criteria. It does **not** change the truth status of evidence, provenance, or trading safety controls.

## Two separate milestones

### Milestone A — Personal prototype

The prototype may be completed without waiting for 30 consecutive qualifying UTC days. It may use:
- clearly labelled historical, sample, simulated, and unverified candidate market data;
- deterministic replay and synthetic scenarios for software testing (never represented as real market evidence);
- paper execution and a durable paper ledger;
- strategy research, dashboards, alerts, scraper/collector workflows, diagnostics, and risk-management simulations;
- local development and test infrastructure.

Prototype acceptance means the components work as software under documented test conditions. It is not a claim of profitable performance, authentic market-data provenance, operational endurance, or live-trading readiness.

### Milestone B — Validation and any later live-readiness review

Deferred until after the personal prototype is usable:
- approved provider and independently verified provenance mechanism;
- persistent host, monitoring, clock discipline, backups, and successful restore drill;
- 30 consecutive qualifying UTC days of forward evidence;
- independent review and any later live-readiness decision.

No validation clock starts until the existing acceptance conditions are met. The day count remains zero until then.

## Non-negotiable safety boundaries

- Keep `BLOCKED_PROVENANCE` for verified evidence when the source is not authenticated.
- Never convert TLS transport success, checksums, synthetic data, replay, or process heartbeats into proof of individual tick authenticity.
- Keep broker/account endpoints, credentials, wallet access, proposals, orders, and live execution disabled during prototype development.
- Keep the paper kill switch engaged and preserve auditable, append-only records.
- Label every dataset and report with its source and status: `historical`, `synthetic`, `unverified_candidate`, or `verified` (the last only after the trust policy is independently approved).
- Personal use and non-commercial intent do not make unverified data or untested execution safe.

## Prototype completion sequence

1. Close engineering defects in the persistent collector supervisor, including interrupting and reaping a child process on shutdown, and test normal session rotation and crash recovery.
2. Make the development environment reproducible with a reviewed dependency lock for core, market-data, and test dependencies.
3. Add a repeatable SQLite online-backup/restore drill and verify integrity, event-chain integrity, and record counts.
4. Complete end-to-end paper workflows: ingestion/replay, research, risk checks, simulated execution, ledger, reporting, and diagnostics.
5. Run deterministic regression and stress suites; publish their exact scope and results without calling them forward-market validation.
6. Deliver a local operator runbook and a prototype readiness report that lists known limitations and explicitly states that Level 3/4 validation is deferred.

## Status language

Use **prototype complete** only when the software acceptance checklist above is met. Do not use **Level 3 certified**, **verified data**, **live-ready**, or **Level 4 complete** until their separate acceptance criteria are met.
