import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

from apps.api.status import StatusHandler
from research.showcase import gate_payload, run_showcase, synthetic_bars


class ShowcaseSimulationTests(unittest.TestCase):
    def test_same_seed_is_deterministic_and_different_seed_differs(self):
        a, b, c = run_showcase(3, 300), run_showcase(3, 300), run_showcase(4, 300)
        self.assertEqual(a, b)
        self.assertNotEqual(a["data_sha256"], c["data_sha256"])

    def test_audit_chain_and_accounting_are_consistent(self):
        result = run_showcase(7, 500)
        metrics = result["metrics"]
        self.assertTrue(result["simulation"])
        self.assertTrue(metrics["audit_chain_valid"])
        self.assertEqual(metrics["entries"] - metrics["exits"], metrics["open_positions"])
        self.assertEqual(len(result["trades"]), metrics["exits"])
        self.assertAlmostEqual(sum(t["net_pnl"] for t in result["trades"]), metrics["realized_net_pnl"], places=1)
        self.assertGreaterEqual(metrics["max_drawdown_pct"], 0)
        self.assertEqual(len(result["equity"]), 500 - 21)

    def test_bars_are_valid_ohlc(self):
        for bar in synthetic_bars(1, 200):
            self.assertGreaterEqual(bar.high, max(bar.open, bar.close))
            self.assertLessEqual(bar.low, min(bar.open, bar.close))
            self.assertGreater(bar.low, 0)

    def test_invalid_parameters_are_rejected(self):
        for kwargs in ({"seed": -1}, {"seed": "7"}, {"count": 5}, {"count": 10**6}):
            with self.assertRaises(ValueError):
                run_showcase(**{"seed": 1, "count": 200, **kwargs})

    def test_live_gate_is_always_blocked(self):
        gate = gate_payload()
        self.assertFalse(gate["live_trading_enabled"])
        self.assertEqual(gate["status"], "blocked")
        self.assertEqual(gate["verified_demo_days"], 0)
        self.assertTrue(gate["reasons"])


class ShowcaseApiTests(unittest.TestCase):
    def setUp(self):
        handler = type("H", (StatusHandler,), {"status_provider": staticmethod(lambda: {})})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_showcase_and_gate_routes(self):
        with urlopen(self.base + "/showcase?seed=2&bars=300", timeout=20) as response:
            payload = json.loads(response.read())
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertTrue(payload["simulation"])
        self.assertEqual(payload["seed"], 2)
        with urlopen(self.base + "/gate", timeout=5) as response:
            self.assertFalse(json.loads(response.read())["live_trading_enabled"])

    def test_bad_query_is_a_400_not_a_crash(self):
        for query in ("seed=abc", "bars=5", "seed=99999999999", "bars=-3"):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + "/showcase?" + query, timeout=5)
            error.exception.close()
            self.assertEqual(error.exception.code, 400, query)


if __name__ == "__main__":
    unittest.main()
