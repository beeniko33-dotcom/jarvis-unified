import asyncio
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError

from research.cloudflare_signal_publisher import CloudflareSignalPublisher, build_signal_body
from research.live_signal_runner import LiveSignalRunner
from tests.test_live_signal_runner import CROSS_UP, FLAT, FakeBinance, Recorder


class Capture:
    """Records requests and fakes the worker's HTTP response."""

    def __init__(self, status=202, error=None):
        self.requests, self.status, self.error = [], status, error

    def __call__(self, request, timeout):
        if self.error:
            raise self.error
        self.requests.append(request)
        outer = self

        class R:
            status = outer.status
            def __enter__(s): return s
            def __exit__(s, *a): return False
        return R()


class FlakyPublisher:
    def __init__(self): self.bodies, self.fail = [], False
    def publish(self, body):
        if self.fail:
            raise RuntimeError("Jarvis worker could not be reached")
        self.bodies.append(body)


class PublisherTests(unittest.TestCase):
    def test_posts_bearer_authenticated_json_to_signals_route(self):
        cap = Capture()
        CloudflareSignalPublisher("https://jarvis.example.workers.dev", "tok123", opener=cap).publish({"a": 1})
        req = cap.requests[0]
        self.assertEqual(req.full_url, "https://jarvis.example.workers.dev/signals")
        self.assertEqual(req.get_header("Authorization"), "Bearer tok123")
        self.assertEqual(json.loads(req.data), {"a": 1})

    def test_url_and_token_validation(self):
        for url, token in (("http://evil.example.com", "t"), ("https://u:p@x.dev", "t"), ("https://x.dev?q=1", "t"),
                           ("", "t"), ("https://x.dev", " ")):
            with self.assertRaises(ValueError, msg=url):
                CloudflareSignalPublisher(url, token)
        CloudflareSignalPublisher("http://127.0.0.1:8787", "t")  # local dev allowed

    def test_errors_never_leak_token_or_response_body(self):
        for err in (URLError("connect to https://x.dev with Bearer SECRETTOKEN failed"),
                    HTTPError("https://x.dev/signals", 401, "Unauthorized SECRETTOKEN", {}, None)):
            with self.assertRaises(RuntimeError) as ctx:
                CloudflareSignalPublisher("https://x.dev", "SECRETTOKEN", opener=Capture(error=err)).publish({})
            self.assertNotIn("SECRETTOKEN", str(ctx.exception))
            self.assertIsNone(ctx.exception.__cause__)

    def test_unexpected_status_is_an_error(self):
        with self.assertRaises(RuntimeError):
            CloudflareSignalPublisher("https://x.dev", "t", opener=Capture(status=204)).publish({})

    def test_body_is_whitelisted_stable_and_idempotent(self):
        payload = {"signal": "buy", "close": "100.5", "fast_sma": "99", "slow_sma": "98", "secret": "nope"}
        a = build_signal_body("observation", "2026-11-17T10:00:00+00:00", "BTCUSDT", "15m", payload, entries_allowed=False)
        b = build_signal_body("observation", "2026-11-17T10:00:00+00:00", "BTCUSDT", "15m", payload, entries_allowed=False)
        self.assertEqual(a, b)
        self.assertNotIn("secret", json.dumps(a))
        self.assertEqual((a["kind"], a["side"], a["price"]), ("signal", "buy", "100.5"))
        fill = build_signal_body("exit_fill", "2026-11-17T10:00:00+00:00", "BTCUSDT", "15m",
                                 {"price": "101", "quantity": "0.1", "realized_net_pnl": "-1.2"}, entries_allowed=True)
        self.assertEqual((fill["kind"], fill["side"], fill["net_pnl"]), ("paper_fill", "sell", "-1.2"))
        self.assertNotEqual(a["idempotency_key"], fill["idempotency_key"])
        with self.assertRaises(ValueError):
            build_signal_body("balance", "t", "BTCUSDT", "15m", {}, entries_allowed=False)


class RunnerSinkTests(unittest.TestCase):
    def make(self, tmp, net, **kw):
        return LiveSignalRunner(Path(tmp) / "l.sqlite3", symbol="BTCUSDT", interval="15m", fast=2, slow=5,
                                opener=net, **kw)

    def test_publishes_signals_and_fills_with_entries_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            net, pub = FakeBinance(FLAT), FlakyPublisher()
            runner = self.make(tmp, net, publisher=pub, allow_entries=True)
            runner.step()
            net.closes += CROSS_UP
            runner.step()
            runner.close()
        kinds = [(b["kind"], b["side"]) for b in pub.bodies]
        self.assertIn(("signal", "buy"), kinds)
        self.assertIn(("paper_fill", "buy"), kinds)
        self.assertTrue(all(b["entries_allowed"] for b in pub.bodies))
        self.assertEqual(len({b["idempotency_key"] for b in pub.bodies}), len(pub.bodies))

    def test_sinks_fail_and_recover_independently_without_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            net, pub, tg = FakeBinance(FLAT), FlakyPublisher(), Recorder()
            runner = self.make(tmp, net, publisher=pub, notifier=tg, allow_entries=True)
            runner.step()
            pub.fail = True
            net.closes += CROSS_UP
            runner.step()
            self.assertEqual(pub.bodies, [])
            self.assertGreater(len(tg.messages), 0)  # Telegram unaffected by Cloudflare being down
            telegram_count = len(tg.messages)
            pub.fail = False
            runner.step()
            runner.step()
            runner.close()
        self.assertGreater(len(pub.bodies), 0)
        self.assertEqual(len(tg.messages), telegram_count)  # nothing re-sent to Telegram
        keys = [b["idempotency_key"] for b in pub.bodies]
        self.assertEqual(len(keys), len(set(keys)))


class WorkerRouteTests(unittest.TestCase):
    """Runs cloudflare/worker.py against a stubbed Workers runtime."""

    @classmethod
    def setUpClass(cls):
        stub = types.ModuleType("workers")
        stub.WorkerEntrypoint = type("WorkerEntrypoint", (), {})

        class Response:
            def __init__(self, body="", status=200, headers=None):
                self.body, self.status, self.headers = body, status, headers or {}
            @classmethod
            def json(cls, data, status=200): return cls(json.dumps(data), status)
        stub.Response = Response
        cls.calls = []

        async def fake_fetch(url, options):
            cls.calls.append((url, options))

            class Up:
                status, ok = 202, True
                async def text(self): return '{"inserted": true}'
            return Up()
        stub.fetch = fake_fetch
        sys.modules["workers"] = stub
        sys.modules.pop("cloudflare.worker", None)
        import importlib.util
        spec = importlib.util.spec_from_file_location("jarvis_worker_under_test",
                                                      Path(__file__).resolve().parents[1] / "cloudflare" / "worker.py")
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def call(self, path, *, method="POST", auth="Bearer collector", body='{"a":1}'):
        env = types.SimpleNamespace(SUPABASE_URL="https://proj.supabase.co", SUPABASE_SECRET_KEY="svc",
                                    JARVIS_COLLECTOR_TOKEN="collector", JARVIS_INGEST_TOKEN="ingest")
        worker = self.module.Default()
        worker.env = env

        class Req:
            url = "https://w.dev" + path
            headers = {"authorization": auth}
            async def text(s): return body
        Req.method = method
        self.calls.clear()
        return asyncio.run(worker.fetch(Req())), list(self.calls)

    def test_signals_route_forwards_to_signal_ingest_with_ingest_token(self):
        response, calls = self.call("/signals")
        self.assertEqual(response.status, 202)
        url, options = calls[0]
        self.assertEqual(url, "https://proj.supabase.co/functions/v1/signal-ingest")
        self.assertEqual(options["headers"]["x-jarvis-ingest-token"], "ingest")

    def test_market_data_route_still_targets_its_own_function(self):
        _, calls = self.call("/market-data")
        self.assertTrue(calls[0][0].endswith("/functions/v1/market-data-ingest"))

    def test_signals_requires_collector_token_post_and_small_json_object(self):
        self.assertEqual(self.call("/signals", auth="Bearer wrong")[0].status, 401)
        self.assertEqual(self.call("/signals", auth="")[0].status, 401)
        self.assertEqual(self.call("/signals", method="GET")[0].status, 405)
        self.assertEqual(self.call("/signals", body="not json")[0].status, 400)
        self.assertEqual(self.call("/signals", body="[1]")[0].status, 400)
        self.assertEqual(self.call("/signals", body='{"x":"' + "a" * 17000 + '"}')[0].status, 413)
        response, calls = self.call("/signals", auth="Bearer wrong")
        self.assertEqual(calls, [])  # nothing is forwarded when unauthenticated


if __name__ == "__main__":
    unittest.main()
