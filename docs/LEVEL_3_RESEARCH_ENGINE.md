# Level 3 research and paper replay engine

This milestone adds a deterministic, restart-safe historical-data research harness. It is not a live market-data feed and does not connect to Deriv, MT5, a wallet, or any real-money broker.

## Input contract

Provide a single-symbol CSV with timestamp,symbol,open,high,low,close,volume. The initial engine deliberately rejects multi-symbol input so its account and daily-risk accounting cannot silently mix unsynchronized markets. Timestamps must be ISO-8601 with an explicit timezone. Use a trusted data provider and preserve its licensing, timezone, instrument, candle interval, and adjustment metadata alongside the source file. The replay stores the SHA-256 of the exact CSV bytes.

## Strategy

The initial reference strategy is long-only fast/slow simple-moving-average crossover, version 1.0.0. It is deliberately a baseline for validating the research pipeline, not a recommendation or a profitable signal. It uses close-to-close historical replay, configurable fast/slow windows, notional sizing capped at 1% of current equity by default, and modeled fees/slippage. No leverage or short selling is used.

## Durable audit

SQLite uses WAL and FULL synchronous mode. Bars have a unique (symbol,timestamp) key so replaying the same input is idempotent. Events are append-only and SHA-256 hash chained. The database retains cash, equity, realized PnL, peak equity, positions, observations, fills, and risk rejections. Back up the SQLite database and source CSV together.

## Run

    python research/paper_replay.py data/ohlcv.csv --db var/research_paper.sqlite3 --fast 10 --slow 30
    python research/paper_replay.py data/ohlcv.csv --db var/research_paper.sqlite3 --fast 10 --slow 30 --min-days 30

The second command checks distinct UTC dates represented by input bars. It does not prove 30 consecutive days. Inspect actual date coverage and source provenance. Run on newly delivered data periodically; do not fabricate observations or reuse a deterministic CI fixture as trading evidence.

## Before Level 3 sign-off

- Use at least 30 consecutive UTC days of trusted, timestamped observations, preferably paper-forward observations rather than only historical backtests.
- Add instrument-specific contract sizing, tick/lot constraints, spread-aware bid/ask fills, market hours, data-gap checks and corporate-action/roll handling where applicable.
- Validate risk limits across the whole portfolio, including unrealized daily loss, peak-equity drawdown, correlated exposure, stale data and restart reconciliation.
- Separate in-sample development from a frozen out-of-sample period. Publish trade-level attribution, expectancy, win rate, profit factor, drawdown, costs, slippage and rejected signals.
- Independently review the data, strategy, event chain, open positions and failure/recovery tests.

The present engine is a meaningful validation foundation, not Level 3 certification. No profit is guaranteed. Live execution remains disabled.
