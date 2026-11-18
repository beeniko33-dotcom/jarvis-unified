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
python -m packages.scraper --allow-host example.com https://example.com
python -m unittest discover -s tests -v
python scripts/diagnose.py
python scripts/paper_session.py --allow-entries --ledger var/paper_ledger.jsonl
python scripts/paper_report.py var/paper_ledger.jsonl --min-days 30
python scripts/paper_reconcile.py var/paper_ledger.jsonl
python scripts/paper_daily_check.py var/paper_ledger.jsonl --observations-db var/paper_ledger.observations.sqlite3
python scripts/paper_session.py --allow-entries --account-db var/paper_account.sqlite3
python scripts/paper_account_audit.py var/paper_account.sqlite3
python scripts/paper_daily_check.py --account-db var/paper_account.sqlite3
python main.py --import-paper-ledger --paper-ledger-db var/paper/paper.sqlite --learning-db var/learning/observations.sqlite3
python main.py --paper-outcomes --learning-db var/learning/observations.sqlite3
python main.py --paper-reflections --learning-db var/learning/observations.sqlite3 --reflection-db var/learning/reflections.sqlite3
python main.py --shadow-review --learning-db var/learning/observations.sqlite3 --shadow-db var/learning/shadow_candidates.sqlite3
python main.py --shadow-history --shadow-db var/learning/shadow_candidates.sqlite3
# Append a human review decision; valid values: accepted_for_manual_review, declined, needs_more_evidence
python main.py --shadow-decision CANDIDATE_ID needs_more_evidence --shadow-db var/learning/shadow_candidates.sqlite3
python main.py --experiment-list --experience-db var/learning/experience.sqlite3
python main.py --experiment-verify EXPERIMENT_ID --experience-db var/learning/experience.sqlite3
python main.py --experiment-verify-sources EXPERIMENT_ID /local/paper-ledger.sqlite /local/learning-journal.sqlite --experience-db var/learning/experience.sqlite3
python main.py --experiment-compare LEFT_ID RIGHT_ID --experience-db var/learning/experience.sqlite3
```

`--paper-reflections` creates deterministic, idempotent factual session reflections from all verified learning-journal event classes. It groups imported ledger facts by source-ledger identity and UTC day, retains each journal event ID/hash as a source reference, and leaves market-data authenticity, strategy lineage and causal conclusions explicitly unknown. Reflections are stored separately; the source broker ledger and learning journal are read-only to this bridge.

The learning commands import an existing persistent paper-broker SQLite ledger into a separate, hash-chained learning journal, then print loss-inclusive outcome analytics. The importer opens the source ledger read-only and rejects broken hash chains or snapshot mismatches before importing. Repeated imports are idempotent. Reports retain realized P&L and commissions separately, show net results after costs, and calculate drawdown only when source snapshots contain the required marks and account data. P&L is attributed to ledger events and UTC days, not individual entry orders where the source ledger cannot prove that allocation.

`--shadow-review` generates persistent, evidence-linked review suggestions for negative net outcomes, partial fills, rejections, drawdown and missing mark coverage. Each candidate records its evidence, sample size, confidence label, review date and expiry. The advisor is descriptive and advisory only: it cannot change strategies, parameters, risk limits, kill switches, permissions or execution. Use `--shadow-history` to inspect candidate and owner-review history, and `--shadow-decision` to append a human review outcome. An accepted review is not strategy approval or deployment.

Shadow candidates explicitly carry experiment_id=null and experiment_attribution=unknown when report-to-experiment lineage cannot be proven. The system does not infer a strategy or experiment from matching dates, symbols, or outcomes.
Session reflections now use deterministic content identities. Replaying the same session facts in a different input order returns the original reflection without duplicating history; a changed source fact creates a separate revision rather than overwriting the prior reflection.
 
The experiment registry stores canonical local config snapshots (credential-like keys are rejected), config and metrics hashes, dataset identity, time window and optional SHA-256 references to the exact paper-ledger and learning-journal files. `--experiment-verify` checks stored config and metrics integrity. `--experiment-verify-sources` hashes the actual local files and appends an immutable match/mismatch record; local file paths are not stored. `--experiment-compare` emits metric deltas only when both records have matching dataset identity/hash, verified data-status labels, identical time windows, matching source-file hashes and successful local source-artifact verification. Otherwise it returns explicit reasons and does not rank the experiments. A matching file hash proves byte identity with the recorded reference, not independent provider authenticity; upstream provenance gates remain authoritative. Legacy records without config snapshots fail closed on integrity verification. The registry does not calculate strategy performance from raw fills, promote candidates, or influence the Level 3 evidence clock.

`--demo` runs one risk-gated in-memory paper entry, demonstrates a rejected oversized order, closes the demo position, and leaves the kill switch engaged. It does not create forward-validation evidence.

## Local dashboard and mobile

The dashboard is a paper-trading observatory: a seeded, deterministic simulation (`research/showcase.py`) runs the real paper replay engine, risk limits and hash-chained audit trail, and the page charts the equity curve, drawdown, price with moving averages, trade markers, closed-trade ledger and result metrics. Pick any seed to get a different market. The simulation is synthetic: it proves the pipeline works end to end, is labeled as such on screen, and never counts toward Level 3 or the 30-day live-trading gate. The `/gate` route and the gate panel show that live trading is locked and why.

Start `python main.py --serve`, then open `http://127.0.0.1:8787/dashboard`. The status page is a read-only installable web app and works offline only for its static shell; live health and account status are never cached. The API remains bound to localhost. Install steps for Android, iOS and desktop are in `apps/mobile/README.md`.

## Live signals to Telegram (paper trading)

`research/live_signal_runner.py` follows real market prices and trades them on paper. Each cycle it reads the newest fully closed Binance candles (public market data, no API key, never an account or order endpoint), runs the SMA-crossover strategy, applies the paper engine's risk limits, fees and slippage, and sends a Telegram alert for each buy or sell signal, paper fill and blocked entry. State is kept in SQLite, so a restart never repeats a trade or an alert, and an alert that fails to send is retried in order.

```bash
export TELEGRAM_BOT_TOKEN='your-bot-token'
export TELEGRAM_CHAT_ID='your-chat-id'
# Alerts only: the kill switch stays engaged, signals are sent, no paper positions open
python -m research.live_signal_runner --symbol BTCUSDT --interval 15m --telegram
# Paper trading on: signals also open and close paper positions
python -m research.live_signal_runner --symbol BTCUSDT --interval 15m --telegram --allow-entries
# Or in Docker: docker compose --profile signals up --build
```

To also record every signal and paper fill in your Jarvis cloud ledger, add `--cloudflare` with `JARVIS_WORKER_URL` (your deployed `jarvis-control-worker` address) and `JARVIS_COLLECTOR_TOKEN` set. Events are POSTed to the worker's `/signals` route, which forwards them to Supabase as `research_only` rows with no evidence credit. Telegram and Cloudflare each keep their own delivery cursor, so one being down never blocks or duplicates the other. See `docs/CLOUDFLARE_WORKER_MIGRATION.md` for the one-time deploy steps.

Alerts contain signal and paper-fill details only, never balances, credentials or broker data. The message layout lives in `format_alert()`. Public candles are unverified, so this never counts toward Level 3 or the 30-day live-trading gate, and live trading stays locked.

## Local Docker

With Docker Compose, run `docker compose up --build` and open `http://127.0.0.1:8787/dashboard`. The API listens on the container interface but Compose publishes the port only on the host loopback address; do not change that mapping. Stop any existing Jarvis process using port 8787 first.

The optional Telegram integration only reports a fixed paper-only health message to one configured chat. It does not send account balances, positions, or credentials:

```bash
export TELEGRAM_BOT_TOKEN='your-bot-token'
export TELEGRAM_CHAT_ID='your-chat-id'
docker compose --profile telegram up --build
```

Only `/health` and `/status` are supported, and messages from other chats are ignored. Keep the token in a local secret store or environment, never in git or chat.

## Architecture and safety

- Paper broker and central risk-gated execution
- Localhost-only read-only status API
- SSRF-safe single-page metadata extraction
- Deriv and MT5 adapters intentionally disabled
- No live execution path

See `docs/START_HERE.md`, `docs/ARCHITECTURE.md`, `docs/MATURITY.md`, `docs/RISK.md`, `docs/SCRAPER.md`, and `docs/LEVEL_3_RUNBOOK.md`.

**Experimental research software. No signal or strategy guarantees profit.**
