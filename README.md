# Jarvis Unified — Forex Signal & Forecast Intelligence

Jarvis Unified is being refocused as a Forex market-analysis, directional-forecast and alerting system. It observes market data and produces transparent bullish, bearish or neutral research forecasts. It does not place trades.

## Product scope
- FX market-data collection with source, timestamp, freshness and quality metadata.
- Multi-timeframe trend and momentum analysis.
- Directional forecasts with an explainable strength score and explicit data-quality status.
- Forecast history, signal-change tracking and configurable alerts.
- Research dashboards, watchlists and market-session context.
- Historical forecast evaluation and calibration reporting when sufficient verified data exists.

## Explicitly out of scope
- Live trading, demo trading and paper trading.
- Broker order APIs, order routing, execution adapters and trade lifecycle management.
- Positions, balances, portfolios, leverage, lot sizing and position sizing.
- Entry prices, stop-losses, take-profits and execution plans.
- Trading kill switches, entry pauses and paper-mode gates.

No forecast is a trade instruction or a promise of future performance. The forecast strength score is a heuristic, not a calibrated probability. Forecasts must show source and freshness; stale, malformed or future-dated observations are rejected.

## Quick start

    python -m unittest tests.test_forex_forecast -v
    python scripts/forex_forecast.py candles.json --instrument EURUSD --timeframe M5
    python -m unittest discover -s tests -v

The JSON input is an array of ordered OHLC candles. Each candle contains an ISO-8601 timezone-aware timestamp and positive open, high, low and close values. At least 20 fresh candles are required.

## Migration note
The forecast engine is being added on a dedicated feature branch. Legacy trading and paper-trading modules remain in the repository pending a separately tested removal of imports, routes, schemas, workflows and deployment references. They must not be exposed by the signal-only product. Production services have not been changed.
