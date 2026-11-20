"""Run a Forex direction forecast from a JSON array of OHLC candles."""
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from research.forex_forecast import Candle, forecast_direction

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON file containing ordered OHLC candles")
    parser.add_argument("--instrument", required=True, help="FX instrument, e.g. EURUSD")
    parser.add_argument("--timeframe", required=True, help="candle timeframe, e.g. M5")
    parser.add_argument("--horizon", default="next candle")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, list): parser.error("input must be a JSON array")
    candles = [Candle.from_values(datetime.fromisoformat(x["timestamp"].replace("Z", "+00:00")), x["open"], x["high"], x["low"], x["close"]) for x in payload]
    result = forecast_direction(candles, instrument=args.instrument, timeframe=args.timeframe, horizon=args.horizon, now=datetime.now(timezone.utc))
    print(json.dumps(result.to_dict(), indent=2))
    return 0

if __name__ == "__main__": raise SystemExit(main())
