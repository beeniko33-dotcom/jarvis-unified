import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

from apps.api.status import StatusHandler


class StatusApiTests(unittest.TestCase):
    def setUp(self):
        handler = type(
            "TestStatusHandler",
            (StatusHandler,),
            {"status_provider": staticmethod(lambda: {"mode": "paper", "kill_switch": True})},
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_root_endpoint(self):
        with urlopen(self.base + "/", timeout=2) as response:
            self.assertEqual(response.status, 200)
            payload = json.loads(response.read())
            self.assertTrue(payload["ok"])
            self.assertIn("/health", payload["routes"])

    def test_health_endpoint(self):
        with urlopen(self.base + "/health", timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read()), {"ok": True})

    def test_status_endpoint(self):
        with urlopen(self.base + "/status", timeout=2) as response:
            payload = json.loads(response.read())
            self.assertEqual(payload["mode"], "paper")
            self.assertTrue(payload["kill_switch"])

    def test_features_endpoint_is_read_only_and_paper_only(self):
        with urlopen(self.base + "/features", timeout=2) as response:
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertTrue(payload["read_only"])
            self.assertEqual(payload["execution_mode"], "paper_only")
            ids = {item["id"] for item in payload["features"]}
            self.assertIn("kill_switch", ids)
            self.assertIn("demo_live_execution", ids)

    def test_unknown_route_is_not_found(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + "/execute", timeout=2)
        error.exception.close()
        self.assertEqual(error.exception.code, 404)

    def test_self_check_endpoint(self):
        with urlopen(self.base + "/self-check", timeout=2) as response:
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["ok"], True)
            self.assertEqual(payload["status"], "healthy")
            self.assertEqual(payload["mode"], "paper")

    def test_serve_reports_port_in_use(self):
        occupied = ThreadingHTTPServer(("127.0.0.1", 0), StatusHandler)
        port = occupied.server_port
        thread = threading.Thread(target=occupied.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(RuntimeError) as error:
                from apps.api.status import serve

                serve("127.0.0.1", port, lambda: {"ok": True})
            self.assertIn("could not bind", str(error.exception).lower())
            self.assertIn(str(port), str(error.exception))
        finally:
            occupied.shutdown()
            occupied.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
