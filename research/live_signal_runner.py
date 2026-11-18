"""Live-price signal runner: Binance public candles -> paper trades -> Telegram alerts.

Pipeline per closed candle: fetch (market data only, no API key) -> SMA-crossover signal ->
paper replay engine (risk limits, fees, slippage, hash-chained audit) -> Telegram alert.

Safety: paper money only. No broker, account or order endpoint is ever contacted. Entries are
blocked unless --allow-entries is passed (the kill switch is engaged by default); without it
you still receive signal alerts, and every blocked entry is logged as a risk rejection.
Candles are unverified public data: nothing here counts toward Level 3 or the 30-day gate.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import urlencode
from urllib.request import urlopen

from research.binance_public_feed import ALLOWED_INTERVALS, _get_json
from research.paper_replay import Bar, PaperReplay

_LOG = logging.getLogger(__name__)
INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
_ALERT_KINDS = ("entry_fill", "exit_fill", "risk_reject")


class Notifier(Protocol):
    def send(self, text: str) -> None: ...


class Publisher(Protocol):
    def publish(self, body: dict) -> None: ...


def fetch_closed_bars(symbol: str, interval: str, limit: int, *, opener: Callable = urlopen) -> list[Bar]:
    """Newest `limit` fully closed candles, oldest first. Open candles are always dropped."""
    symbol = symbol.strip().upper()
    if not symbol or not symbol.isalnum():
        raise ValueError("symbol must be an alphanumeric Binance spot symbol")
    if interval not in ALLOWED_INTERVALS:
        raise ValueError("unsupported candle interval")
    if not 2 <= limit <= 1000:
        raise ValueError("limit must be between 2 and 1000")
    server = _get_json("/api/v3/time", opener=opener)
    try:
        server_ms = int(server["serverTime"])  # type: ignore[index]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Binance server-time response is malformed") from exc
    rows = _get_json("/api/v3/klines?" + urlencode({"symbol": symbol, "interval": interval, "limit": limit + 1}),
                     opener=opener)
    if not isinstance(rows, list):
        raise ValueError("Binance returned malformed candle data")
    bars: list[Bar] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 7:
            raise ValueError("Binance candle row is malformed")
        open_ms, close_ms = int(row[0]), int(row[6])
        if close_ms >= server_ms:
            continue  # still forming
        o, h, l, c, v = (Decimal(str(row[i])) for i in range(1, 6))
        if min(o, h, l, c) <= 0 or h < max(o, c, l) or l > min(o, c, h):
            raise ValueError("Binance OHLC values are inconsistent")
        stamp = datetime.fromtimestamp(open_ms / 1000, timezone.utc).isoformat()
        bars.append(Bar(stamp, symbol, o, h, l, c, v))
    return bars[-limit:]


def format_alert(kind: str, ts: str, symbol: str, interval: str, payload: dict) -> str:
    """Plain-text alert. Edit this one function to change the Telegram message layout."""
    head = f"{symbol} {interval} · {ts[:16].replace('T', ' ')} UTC"
    foot = "Paper trading only. Not financial advice."
    if kind == "observation":
        side = payload["signal"].upper()
        icon = "🟢" if side == "BUY" else "🔴"
        return (f"{icon} {side} signal\n{head}\nPrice {payload['close']}\n"
                f"SMA fast {Decimal(payload['fast_sma']):.2f} / slow {Decimal(payload['slow_sma']):.2f}\n{foot}")
    if kind == "entry_fill":
        return (f"📄 Paper BUY filled\n{head}\nQty {Decimal(payload['quantity']):.6f} @ {Decimal(payload['price']):.2f}\n"
                f"Notional {Decimal(payload['notional']):.2f}, fee {Decimal(payload['fee']):.4f}\n{foot}")
    if kind == "exit_fill":
        pnl = Decimal(payload["realized_net_pnl"])
        return (f"📄 Paper SELL filled\n{head}\nQty {Decimal(payload['quantity']):.6f} @ {Decimal(payload['price']):.2f}\n"
                f"Net P&L {pnl:+.2f} after fees\n{foot}")
    return f"⛔ Entry blocked by risk gate: {payload.get('reason')}\n{head}\n{foot}"


class LiveSignalRunner:
    def __init__(self, database: Path, *, symbol: str = "BTCUSDT", interval: str = "15m", fast: int = 10,
                 slow: int = 30, allow_entries: bool = False, notifier: Notifier | None = None,
                 publisher: Publisher | None = None,
                 opener: Callable = urlopen, starting_cash: Decimal = Decimal("10000")) -> None:
        if interval not in ALLOWED_INTERVALS:
            raise ValueError("unsupported candle interval")
        self.symbol, self.interval, self.slow = symbol.strip().upper(), interval, slow
        self.notifier, self.publisher, self.opener = notifier, publisher, opener
        self.allow_entries = allow_entries
        self.engine = PaperReplay(database, starting_cash=starting_cash, fast=fast, slow=slow,
                                  allow_entries=allow_entries)
        self.engine.db.execute("CREATE TABLE IF NOT EXISTS sink_state(sink TEXT PRIMARY KEY,last_event_id INTEGER NOT NULL)")
        self.engine.db.commit()
        self._primed = bool(self.engine.db.execute("SELECT 1 FROM bars LIMIT 1").fetchone())

    def close(self) -> None:
        self.engine.close()

    def _cursor(self, sink: str) -> int:
        row = self.engine.db.execute("SELECT last_event_id FROM sink_state WHERE sink=?", (sink,)).fetchone()
        return row[0] if row else 0

    def _pending_alerts(self, after: int) -> list[tuple[int, str, str, dict]]:
        rows = self.engine.db.execute(
            "SELECT id,ts,kind,payload FROM events WHERE id>? AND (kind IN (?,?,?) OR "
            "(kind='observation' AND json_extract(payload,'$.signal')!='hold')) ORDER BY id",
            (after, *_ALERT_KINDS)).fetchall()
        return [(i, ts, kind, json.loads(payload)) for i, ts, kind, payload in rows]

    def _sinks(self) -> dict[str, Callable[[str, str, dict], None]]:
        sinks: dict[str, Callable[[str, str, dict], None]] = {}
        if self.notifier is not None:
            sinks["telegram"] = lambda kind, ts, p: self.notifier.send(format_alert(kind, ts, self.symbol, self.interval, p))
        if self.publisher is not None:
            from research.cloudflare_signal_publisher import build_signal_body
            sinks["cloudflare"] = lambda kind, ts, p: self.publisher.publish(
                build_signal_body(kind, ts, self.symbol, self.interval, p, entries_allowed=self.allow_entries))
        return sinks

    def flush_alerts(self) -> int:
        """Deliver unsent events to each sink in order. Every sink has its own cursor, so one sink
        being down never blocks, skips or duplicates another. A failed send is retried next cycle."""
        sent = 0
        sinks = self._sinks()
        if not sinks:
            top = self.engine.db.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0]
            self.engine.db.execute("INSERT OR REPLACE INTO sink_state VALUES('none',?)", (top,))
            self.engine.db.commit()
            return 0
        for name, send in sinks.items():
            for event_id, ts, kind, payload in self._pending_alerts(self._cursor(name)):
                try:
                    send(kind, ts, payload)
                except RuntimeError as exc:
                    _LOG.warning("%s delivery failed (%s); will retry", name, exc)
                    break
                self.engine.db.execute("INSERT OR REPLACE INTO sink_state VALUES(?,?)", (name, event_id))
                self.engine.db.commit()
                sent += 1
        return sent

    def step(self) -> dict:
        """Process any newly closed candles, trade on paper, then deliver alerts."""
        bars = fetch_closed_bars(self.symbol, self.interval, self.slow + 5, opener=self.opener)
        if not bars:
            raise RuntimeError("no closed candles returned")
        warmed = 0
        if not self._primed:
            # First run: prime the averages with history but trade nothing from the past.
            warmed = self.engine.warmup(bars[:-1])
            bars = bars[-1:]
            self._primed = True
        report = self.engine.replay(bars, "binance-public-live")
        alerts = self.flush_alerts()
        report.update({"warmup_bars": warmed, "alerts_sent": alerts, "latest_close": str(bars[-1].close)})
        return report

    def run(self, *, poll_seconds: int = 30, sleep: Callable[[float], None] = time.sleep,
            max_iterations: int | None = None) -> None:
        delay, count = poll_seconds, 0
        while max_iterations is None or count < max_iterations:
            count += 1
            try:
                report = self.step()
                _LOG.info("%s close=%s equity=%s entries=%s exits=%s alerts=%s", self.symbol, report["latest_close"],
                          report["equity"], report["entries"], report["exits"], report["alerts_sent"])
                delay = poll_seconds
            except (RuntimeError, ValueError) as exc:
                _LOG.warning("cycle failed (%s); retrying in %ss", exc, delay)
                delay = min(delay * 2, 300)
            sleep(delay)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="15m", choices=sorted(ALLOWED_INTERVALS, key=INTERVAL_SECONDS.get))
    parser.add_argument("--fast", type=int, default=10)
    parser.add_argument("--slow", type=int, default=30)
    parser.add_argument("--db", type=Path, default=Path("var/live/live_paper.sqlite3"))
    parser.add_argument("--allow-entries", action="store_true", help="release the paper kill switch so signals open paper positions")
    parser.add_argument("--telegram", action="store_true", help="send alerts using TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    parser.add_argument("--cloudflare", action="store_true",
                        help="publish events to your Jarvis Cloudflare worker (JARVIS_WORKER_URL, JARVIS_COLLECTOR_TOKEN)")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--once", action="store_true", help="process the latest closed candle once and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    notifier = None
    if args.telegram:
        from apps.telegram.notifier import TelegramNotifier
        try:
            notifier = TelegramNotifier.from_env()
        except ValueError as exc:
            parser.error(str(exc))
    publisher = None
    if args.cloudflare:
        from research.cloudflare_signal_publisher import CloudflareSignalPublisher
        try:
            publisher = CloudflareSignalPublisher.from_env()
        except ValueError as exc:
            parser.error(str(exc))
    try:
        runner = LiveSignalRunner(args.db, symbol=args.symbol, interval=args.interval, fast=args.fast, slow=args.slow,
                                  allow_entries=args.allow_entries, notifier=notifier, publisher=publisher)
    except ValueError as exc:
        parser.error(str(exc))
    try:
        if args.once:
            print(json.dumps(runner.step(), indent=2))
        else:
            mode = "paper trading ON" if args.allow_entries else "alerts only (kill switch engaged)"
            print(f"Jarvis live signals: {runner.symbol} {args.interval}, {mode}. Ctrl+C to stop.", file=sys.stderr)
            runner.run(poll_seconds=max(10, args.poll_seconds))
    except KeyboardInterrupt:
        pass
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        runner.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
