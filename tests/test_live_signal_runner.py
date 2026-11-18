import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from apps.telegram.notifier import TelegramNotifier
from research.live_signal_runner import LiveSignalRunner, fetch_closed_bars, format_alert

STEP_MS = 900_000
T0 = 1_760_000_000_000


class FakeBinance:
    """Stands in for the Binance public REST host; the last candle is optionally still forming."""

    def __init__(self, closes, *, forming_last=False):
        self.closes, self.forming_last = list(closes), forming_last

    def __call__(self, request, timeout=10):
        parts = urlsplit(request.full_url)
        if parts.path == "/api/v3/time":
            body = {"serverTime": T0 + len(self.closes) * STEP_MS + (STEP_MS // 2 if self.forming_last else 5000)}
        elif parts.path == "/api/v3/klines":
            limit = int(parse_qs(parts.query)["limit"][0])
            rows = []
            for i, c in enumerate(self.closes):
                o = self.closes[i - 1] if i else c
                hi, lo = max(o, c) + 0.5, min(o, c) - 0.5
                rows.append([T0 + i * STEP_MS, str(o), str(hi), str(lo), str(c), "10",
                             T0 + (i + 1) * STEP_MS - 1, "0", 1, "0", "0", "0"])
            if self.forming_last:
                rows[-1][6] = T0 + len(self.closes) * STEP_MS + STEP_MS  # close time in the future
            body = rows[-limit:]
        else:
            raise AssertionError("unexpected endpoint " + parts.path)

        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(body).encode()
        return Response()


class Recorder:
    def __init__(self): self.messages, self.fail = [], False
    def send(self, text):
        if self.fail:
            raise RuntimeError("Telegram sendMessage could not reach Telegram")
        self.messages.append(text)


FLAT = [100.0] * 12
CROSS_UP = [96, 92, 90, 98, 108, 118]
CROSS_DOWN = [110, 100, 92, 85]


def make(tmp, closes, **kw):
    net = FakeBinance(closes)
    note = kw.pop("notifier", Recorder())
    runner = LiveSignalRunner(Path(tmp) / "live.sqlite3", symbol="BTCUSDT", interval="15m", fast=2, slow=5,
                              opener=net, notifier=note, **kw)
    return runner, net, note


class LiveSignalRunnerTests(unittest.TestCase):
    def test_first_run_primes_history_without_trading_or_alerting(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner, _, note = make(tmp, FLAT, allow_entries=True)
            report = runner.step()
            runner.close()
        self.assertGreater(report["warmup_bars"], 0)
        self.assertEqual((report["entries"], report["exits"]), (0, 0))
        self.assertEqual(note.messages, [])

    def test_cross_up_then_down_trades_on_paper_and_alerts(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner, net, note = make(tmp, FLAT, allow_entries=True)
            runner.step()
            net.closes += CROSS_UP
            up = runner.step()
            net.closes += CROSS_DOWN
            down = runner.step()
            runner.close()
        self.assertEqual(up["entries"], 1)
        self.assertEqual(down["exits"], 1)
        text = "\n".join(note.messages)
        self.assertIn("BUY signal", text)
        self.assertIn("Paper BUY filled", text)
        self.assertIn("SELL signal", text)
        self.assertIn("Paper SELL filled", text)
        self.assertTrue(down["event_chain_valid"])

    def test_alerts_only_mode_blocks_entries_but_still_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner, net, note = make(tmp, FLAT, allow_entries=False)
            runner.step()
            net.closes += CROSS_UP
            report = runner.step()
            runner.close()
        self.assertEqual(report["entries"], 0)
        self.assertEqual(report["risk_rejections"], 1)
        text = "\n".join(note.messages)
        self.assertIn("BUY signal", text)
        self.assertIn("kill_switch_engaged", text)
        self.assertNotIn("filled", text)

    def test_restart_and_repeat_polls_do_not_resend_or_retrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner, net, note = make(tmp, FLAT, allow_entries=True)
            runner.step()
            net.closes += CROSS_UP
            runner.step()
            sent = len(note.messages)
            runner.step()  # same candles again
            runner.close()
            again, _, note2 = make(tmp, net.closes, allow_entries=True)  # restart on same database
            report = again.step()
            again.close()
        self.assertEqual(len(note.messages), sent)
        self.assertEqual(note2.messages, [])
        self.assertEqual(report["entries"], 1)

    def test_failed_telegram_send_is_retried_in_order_without_losing_alerts(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner, net, note = make(tmp, FLAT, allow_entries=True)
            runner.step()
            note.fail = True
            net.closes += CROSS_UP
            runner.step()  # trading continues even though delivery fails
            self.assertEqual(note.messages, [])
            note.fail = False
            runner.step()
            runner.close()
        text = "\n".join(note.messages)
        # Alerts arrive complete and in event order: the early down-cross, then the buy and its fill.
        self.assertLess(text.index("SELL signal"), text.index("BUY signal"))
        self.assertLess(text.index("BUY signal"), text.index("Paper BUY filled"))

    def test_forming_candle_is_never_used(self):
        net = FakeBinance([100.0] * 8 + [500.0], forming_last=True)
        bars = fetch_closed_bars("BTCUSDT", "15m", 6, opener=net)
        self.assertTrue(all(b.close == 100 for b in bars))

    def test_bad_inputs_are_rejected(self):
        for kwargs in ({"symbol": "BTC/USDT"}, {"interval": "7m"}, {"limit": 1}):
            with self.assertRaises(ValueError):
                fetch_closed_bars(**{"symbol": "BTCUSDT", "interval": "15m", "limit": 10, **kwargs},
                                  opener=FakeBinance(FLAT))

    def test_alert_text_has_no_balance_and_no_secrets(self):
        text = format_alert("exit_fill", "2026-11-17T10:00:00+00:00", "BTCUSDT", "15m",
                            {"quantity": "0.1", "price": "100", "realized_net_pnl": "-1.5"})
        self.assertIn("-1.50", text)
        for word in ("balance", "equity", "token"):
            self.assertNotIn(word, text.lower())


class TelegramNotifierTests(unittest.TestCase):
    def test_posts_to_the_configured_chat_only(self):
        seen = {}

        def opener(request, timeout):
            seen["url"], seen["body"] = request.full_url, json.loads(request.data)
            class R:
                def __enter__(s): return s
                def __exit__(s, *a): return False
                def read(s): return b'{"ok": true, "result": {}}'
            return R()
        TelegramNotifier("SECRET:TOKEN", "12345", opener=opener).send("hello")
        self.assertTrue(seen["url"].endswith("/sendMessage"))
        self.assertEqual(seen["body"]["chat_id"], "12345")

    def test_errors_never_contain_the_token(self):
        def opener(request, timeout):
            raise URLError("failed connecting to https://api.telegram.org/botSECRET:TOKEN/sendMessage")
        with self.assertRaises(RuntimeError) as err:
            TelegramNotifier("SECRET:TOKEN", "12345", opener=opener).send("x")
        self.assertNotIn("SECRET", str(err.exception))
        self.assertIsNone(err.exception.__cause__)

    def test_missing_credentials_are_rejected(self):
        for args in (("", "1"), ("t", " ")):
            with self.assertRaises(ValueError):
                TelegramNotifier(*args)


if __name__ == "__main__":
    unittest.main()
