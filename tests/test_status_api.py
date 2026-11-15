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
            self.assertIn("/dashboard", payload["routes"])

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

    def test_dashboard_and_pwa_assets_are_served_from_same_origin(self):
        for path, content_type in (
            ("/dashboard", "text/html"),
            ("/manifest.webmanifest", "application/manifest+json"),
            ("/service-worker.js", "text/javascript"),
            ("/icon.svg", "image/svg+xml"),
        ):
            with self.subTest(path=path), urlopen(self.base + path, timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(content_type, response.headers["Content-Type"])
                self.assertGreater(len(response.read()), 0)

    def test_query_string_does_not_break_routing(self):
        # An installed PWA can be launched as /dashboard?source=pwa.
        with urlopen(self.base + "/dashboard?source=pwa", timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.headers["Content-Type"])
        with urlopen(self.base + "/health?probe=1", timeout=2) as response:
            self.assertEqual(json.loads(response.read()), {"ok": True})
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + "/execute?x=/health", timeout=2)
        error.exception.close()
        self.assertEqual(error.exception.code, 404)

    def test_png_icons_are_real_pngs_with_declared_sizes(self):
        import struct

        manifest = json.loads(self._get("/manifest.webmanifest"))
        png_icons = [icon for icon in manifest["icons"] if icon["type"] == "image/png"]
        self.assertTrue({"any", "maskable"} <= {icon["purpose"] for icon in png_icons})
        for icon in png_icons:
            with self.subTest(src=icon["src"]):
                body = self._get(icon["src"])
                self.assertEqual(body[:8], b"\x89PNG\r\n\x1a\n")
                width, height = struct.unpack(">II", body[16:24])
                self.assertEqual(f"{width}x{height}", icon["sizes"])
        apple = self._get("/icons/apple-touch-icon.png")
        self.assertEqual(apple[:8], b"\x89PNG\r\n\x1a\n")
        self.assertIn('href="/icons/apple-touch-icon.png"', self._get("/dashboard").decode())

    def test_every_manifest_icon_and_shell_entry_is_served(self):
        import re

        manifest = json.loads(self._get("/manifest.webmanifest"))
        for icon in manifest["icons"]:
            with self.subTest(icon=icon["src"]):
                self.assertGreater(len(self._get(icon["src"])), 0)
        worker = self._get("/service-worker.js").decode()
        shell = re.findall(r"'(/[^']*)'", worker.split("APP_SHELL = [", 1)[1].split("];", 1)[0])
        self.assertIn("/dashboard", shell)
        for path in shell:
            with self.subTest(shell=path):
                self.assertGreater(len(self._get(path)), 0)

    def test_service_worker_never_caches_live_endpoints(self):
        import re

        worker = self._get("/service-worker.js").decode()
        shell = re.findall(r"'(/[^']*)'", worker.split("APP_SHELL = [", 1)[1].split("];", 1)[0])
        for live in ("/health", "/status", "/features", "/self-check", "/"):
            self.assertNotIn(live, shell)
        # Requests outside the shell must fall through to the network untouched.
        self.assertIn("!APP_SHELL.includes(url.pathname)) return;", worker)

    def _get(self, path):
        with urlopen(self.base + path, timeout=2) as response:
            return response.read()

    def _raw_get(self, path, host):
        import http.client

        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        try:
            connection.putrequest("GET", path, skip_host=True)
            if host is not None:
                connection.putheader("Host", host)
            connection.endheaders()
            response = connection.getresponse()
            response.read()
            return response.status, response
        finally:
            connection.close()

    def test_unexpected_host_header_is_rejected(self):
        # DNS-rebinding defence: a page on evil.example resolving to 127.0.0.1 must get nothing.
        for host in ("evil.example", "evil.example:8787", "127.0.0.1.evil.example", "localhost.evil.example", "", None):
            with self.subTest(host=host):
                status, _ = self._raw_get("/status", host)
                self.assertEqual(status, 403)

    def test_expected_host_headers_are_accepted_on_any_port(self):
        for host in ("127.0.0.1", "127.0.0.1:8787", "localhost:9999", "LOCALHOST", "[::1]:8787", "jarvis:8787"):
            with self.subTest(host=host):
                status, _ = self._raw_get("/health", host)
                self.assertEqual(status, 200)

    def test_security_headers_are_sent_on_every_response(self):
        for path in ("/health", "/dashboard", "/missing"):
            with self.subTest(path=path):
                _, response = self._raw_get(path, "127.0.0.1")
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(response.headers["X-Frame-Options"], "DENY")
                self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        _, rejected = self._raw_get("/status", "evil.example")
        self.assertEqual(rejected.headers["X-Content-Type-Options"], "nosniff")

    def test_provider_failure_returns_plain_500_without_internals(self):
        def broken():
            raise RuntimeError("secret internal detail")

        handler = type("BrokenHandler", (StatusHandler,), {"status_provider": staticmethod(broken)})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(HTTPError) as error:
                urlopen(f"http://127.0.0.1:{server.server_port}/status", timeout=2)
            body = error.exception.read().decode()
            error.exception.close()
            self.assertEqual(error.exception.code, 500)
            self.assertNotIn("secret internal detail", body)
            # The server survives and keeps answering.
            with urlopen(f"http://127.0.0.1:{server.server_port}/health", timeout=2) as response:
                self.assertEqual(response.status, 200)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

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

    def test_non_local_bind_requires_container_opt_in(self):
        from apps.api.status import serve

        with self.assertRaisesRegex(ValueError, "localhost"):
            serve("0.0.0.0", 0, lambda: {})


if __name__ == "__main__":
    unittest.main()
