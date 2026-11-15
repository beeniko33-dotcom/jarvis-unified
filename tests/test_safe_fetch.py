import ipaddress
import socket
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

from packages.scraper.safe_fetch import (
    SafeFetchError,
    _is_blocked_ip,
    _PinnedHTTPConnection,
    _PinnedHTTPSConnection,
    _validate_url,
    is_public_hostname,
    safe_fetch_url,
)


class SafeFetchTests(unittest.TestCase):
    def test_rejects_file_scheme(self):
        with self.assertRaises(SafeFetchError):
            safe_fetch_url("file:///etc/passwd", allowed_hosts=["example.com"])

    def test_rejects_localhost(self):
        with self.assertRaises(SafeFetchError):
            safe_fetch_url("http://localhost/admin", allowed_hosts=["localhost"])

    def test_rejects_loopback_ip(self):
        with self.assertRaises(SafeFetchError):
            safe_fetch_url("http://127.0.0.1/", allowed_hosts=["127.0.0.1"])

    def test_rejects_private_ip(self):
        with self.assertRaises(SafeFetchError):
            safe_fetch_url("http://192.168.1.10/", allowed_hosts=["192.168.1.10"])

    def test_rejects_metadata_host(self):
        with self.assertRaises(SafeFetchError):
            safe_fetch_url(
                "http://metadata.google.internal/",
                allowed_hosts=["metadata.google.internal"],
            )

    def test_rejects_credentials_in_url(self):
        with self.assertRaises(SafeFetchError):
            safe_fetch_url(
                "https://user:pass@example.com/",
                allowed_hosts=["example.com"],
            )

    def test_requires_a_nonempty_host_allowlist(self):
        for allowed_hosts in ([], None):
            with self.subTest(allowed_hosts=allowed_hosts), self.assertRaises(SafeFetchError):
                safe_fetch_url("https://example.com/", allowed_hosts=allowed_hosts)

    def test_blocked_ip_literals_cover_embedded_ipv4_and_special_ranges(self):
        # Locks in behavior independent of the Python version's ipaddress classification.
        blocked = (
            "::ffff:127.0.0.1",  # IPv4-mapped loopback
            "::7f00:1",  # IPv4-compatible loopback
            "64:ff9b::a9fe:a9fe",  # NAT64 -> cloud metadata
            "64:ff9b::7f00:1",  # NAT64 -> loopback
            "64:ff9b:1::a9fe:a9fe",  # local-use NAT64
            "2002:7f00:1::",  # 6to4 -> loopback
            "2002:a9fe:a9fe::",  # 6to4 -> cloud metadata
            "2001:0:4136:e378:8000:63bf:3fff:fdd2",  # Teredo
            "fec0::1",  # deprecated site-local
            "fe80::1",
            "fd00::1",
            "100.64.0.1",
            "169.254.169.254",
        )
        for literal in blocked:
            with self.subTest(literal=literal):
                self.assertTrue(_is_blocked_ip(ipaddress.ip_address(literal)))
        for literal in ("93.184.216.34", "2606:4700:4700::1111"):
            with self.subTest(literal=literal):
                self.assertFalse(_is_blocked_ip(ipaddress.ip_address(literal)))

    def test_hostname_resolving_to_embedded_ipv4_address_is_rejected(self):
        for answer in ("64:ff9b::a9fe:a9fe", "2002:7f00:1::", "::ffff:169.254.169.254", "fec0::1"):
            with self.subTest(answer=answer), patch(
                "packages.scraper.safe_fetch._resolve_dns", return_value=[answer]
            ):
                with self.assertRaisesRegex(SafeFetchError, "blocked address"):
                    _validate_url("https://example.com/")

    def test_is_public_hostname_localhost_false(self):
        self.assertFalse(is_public_hostname("localhost"))

    def test_validate_url_returns_the_public_addresses_to_pin(self):
        resolved = ["93.184.216.34"]
        with patch("packages.scraper.safe_fetch._resolve_dns", return_value=resolved):
            scheme, hostname, url, port, addresses = _validate_url("https://example.com/")

        self.assertEqual(
            (scheme, hostname, url, port),
            ("https", "example.com", "https://example.com/", 443),
        )
        self.assertEqual(addresses, ["93.184.216.34"])

    def test_hostname_with_any_private_dns_answer_is_rejected(self):
        resolved = ["93.184.216.34", "192.168.1.10"]
        with patch("packages.scraper.safe_fetch._resolve_dns", return_value=resolved):
            with self.assertRaisesRegex(SafeFetchError, "blocked address"):
                _validate_url("https://example.com/")

    def test_dns_resolution_is_given_a_finite_timeout(self):
        with patch(
            "packages.scraper.safe_fetch.subprocess.run",
            side_effect=subprocess.TimeoutExpired("python", 0.25),
        ) as run:
            with self.assertRaisesRegex(SafeFetchError, "DNS resolution timed out"):
                _validate_url("https://example.com/", timeout_s=0.25)

        self.assertEqual(run.call_args.kwargs["timeout"], 0.25)

    def test_allowed_host_is_normalized_and_fetches(self):
        resolved = ["93.184.216.34"]
        response = Mock(status=200)
        response.getheader.side_effect = lambda name, default=None: {
            "Content-Length": "0",
            "Content-Type": "text/html",
            "Content-Encoding": "identity",
        }.get(name, default)
        response.read.return_value = b""
        connection = Mock(sock=None)
        connection.getresponse.return_value = response
        with (
            patch("packages.scraper.safe_fetch._resolve_dns", return_value=resolved),
            patch(
                "packages.scraper.safe_fetch._PinnedHTTPSConnection",
                return_value=connection,
            ) as connection_factory,
        ):
            result = safe_fetch_url(
                "https://example.com/",
                allowed_hosts=["EXAMPLE.COM."],
            )

        self.assertEqual(result.status, 200)
        connection_factory.assert_called_once()

    def test_host_outside_allowlist_is_rejected_before_dns(self):
        with patch("packages.scraper.safe_fetch._resolve_dns") as resolve:
            with self.assertRaisesRegex(SafeFetchError, "not in the allowlist"):
                safe_fetch_url(
                    "https://sub.example.com/",
                    allowed_hosts=["example.com"],
                )

        resolve.assert_not_called()

    def test_redirect_destination_must_be_in_allowlist(self):
        response = Mock(status=302)
        response.getheader.return_value = "https://other.example/final"
        connection = Mock(sock=None)
        connection.getresponse.return_value = response
        resolved = ["93.184.216.34"]
        with (
            patch("packages.scraper.safe_fetch._resolve_dns", return_value=resolved) as resolve,
            patch(
                "packages.scraper.safe_fetch._PinnedHTTPSConnection",
                return_value=connection,
            ),
        ):
            with self.assertRaisesRegex(SafeFetchError, "not in the allowlist"):
                safe_fetch_url(
                    "https://example.com/",
                    allowed_hosts=["example.com"],
                    max_redirects=1,
                )

        resolve.assert_called_once()

    def test_unreachable_validated_address_fails_over_to_next_address(self):
        response = Mock(status=200)
        response.getheader.side_effect = lambda name, default=None: {
            "Content-Length": "0",
            "Content-Type": "text/html",
            "Content-Encoding": "identity",
        }.get(name, default)
        response.read.return_value = b""
        failed_connection = Mock(sock=None)
        failed_connection.request.side_effect = OSError("address unreachable")
        working_connection = Mock(sock=None)
        working_connection.getresponse.return_value = response
        addresses = ["93.184.216.34", "1.1.1.1"]
        with (
            patch("packages.scraper.safe_fetch._resolve_dns", return_value=addresses),
            patch(
                "packages.scraper.safe_fetch._PinnedHTTPSConnection",
                side_effect=[failed_connection, working_connection],
            ) as connection_factory,
        ):
            result = safe_fetch_url(
                "https://example.com/",
                allowed_hosts=["example.com"],
            )

        self.assertEqual(result.status, 200)
        self.assertEqual(
            [call.args[2] for call in connection_factory.call_args_list],
            addresses,
        )
        failed_connection.close.assert_called_once()

    def test_http_connection_uses_the_validated_ip_not_the_hostname(self):
        connection = _PinnedHTTPConnection("example.com", 80, "93.184.216.34", 5)
        connected_socket = Mock()
        with patch(
            "packages.scraper.safe_fetch.socket.create_connection",
            return_value=connected_socket,
        ) as create_connection:
            connection.connect()

        create_connection.assert_called_once_with(("93.184.216.34", 80), timeout=5.0)
        connection.close()

    def test_https_connection_preserves_hostname_for_tls_validation(self):
        connection = _PinnedHTTPSConnection("example.com", 443, "93.184.216.34", 5)
        raw_socket = Mock()
        tls_socket = Mock()
        context = Mock()
        context.wrap_socket.return_value = tls_socket
        connection._context = context
        with patch(
            "packages.scraper.safe_fetch.socket.create_connection",
            return_value=raw_socket,
        ) as create_connection:
            connection.connect()

        create_connection.assert_called_once_with(("93.184.216.34", 443), timeout=5.0)
        context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="example.com")
        connection.close()

    def test_nonstandard_ports_are_rejected(self):
        with self.assertRaisesRegex(SafeFetchError, "standard HTTP and HTTPS ports"):
            _validate_url("http://example.com:8080/")

    def test_fetch_limits_and_headers_are_bounded(self):
        for kwargs in (
            {"timeout_s": float("nan")},
            {"timeout_s": 61},
            {"max_bytes": 10_000_001},
            {"max_redirects": 11},
            {"user_agent": "invalid\r\nheader"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(SafeFetchError):
                safe_fetch_url(
                    "https://example.com/",
                    allowed_hosts=["example.com"],
                    **kwargs,
                )

    def test_redirect_destination_is_revalidated_and_pinned(self):
        class FakeResponse:
            def __init__(self, status, headers=None, body=b""):
                self.status = status
                self.headers = headers or {}
                self.body = body

            def getheader(self, name, default=None):
                return self.headers.get(name, default)

            def read(self, size):
                body, self.body = self.body[:size], self.body[size:]
                return body

        class FakeConnection:
            sock = None

            def __init__(self, hostname, port, address, timeout_s):
                instances.append((hostname, port, address, timeout_s))
                self.response = responses.pop(0)

            def request(self, method, target, headers):
                return None

            def getresponse(self):
                return self.response

            def close(self):
                return None

        instances = []
        responses = [
            FakeResponse(302, {"Location": "https://other.example/final"}),
            FakeResponse(200, {"Content-Type": "text/html", "Content-Length": "4"}, b"done"),
        ]
        addresses = {
            "example.com": "93.184.216.34",
            "other.example": "1.1.1.1",
        }

        def resolve(hostname, _timeout_s):
            return [addresses[hostname]]

        with (
            patch("packages.scraper.safe_fetch._resolve_dns", side_effect=resolve),
            patch("packages.scraper.safe_fetch._PinnedHTTPSConnection", FakeConnection),
        ):
            result = safe_fetch_url(
                "https://example.com/start",
                max_redirects=1,
                allowed_hosts=["example.com", "other.example"],
            )

        self.assertEqual(result.final_url, "https://other.example/final")
        self.assertEqual(result.body, b"done")
        self.assertEqual(
            [instance[:3] for instance in instances],
            [
                ("example.com", 443, "93.184.216.34"),
                ("other.example", 443, "1.1.1.1"),
            ],
        )
        for instance in instances:
            self.assertLessEqual(instance[3], 10.0)
            self.assertGreater(instance[3], 0.0)


class SafeFetchHttpIntegrationTests(unittest.TestCase):
    def setUp(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.server.paths.append(self.path)
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "http://rebound.example/")
                    self.end_headers()
                    return
                body = b"<h1>Safe</h1>" if self.path != "/large" else b"too much data"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                if self.path == "/compressed":
                    self.send_header("Content-Encoding", "gzip")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.paths = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _network_patches(self):
        original_getaddrinfo = socket.getaddrinfo
        original_create_connection = socket.create_connection

        def resolve(host, _timeout_s):
            if host == "example.com":
                return ["93.184.216.34"]
            if host == "rebound.example":
                return ["127.0.0.1"]
            return [
                info[4][0]
                for info in original_getaddrinfo(host, None, type=socket.SOCK_STREAM)
            ]

        def connect(address, timeout=None, source_address=None):
            if address == ("93.184.216.34", 80):
                address = ("127.0.0.1", self.server.server_port)
            return original_create_connection(address, timeout, source_address)

        return (
            patch("packages.scraper.safe_fetch._resolve_dns", side_effect=resolve),
            patch(
                "packages.scraper.safe_fetch.socket.create_connection",
                side_effect=connect,
            ),
        )

    def test_fetch_uses_pinned_destination_and_returns_bounded_body(self):
        dns_patch, connection_patch = self._network_patches()
        with dns_patch, connection_patch:
            result = safe_fetch_url("http://example.com/", allowed_hosts=["example.com"])

        self.assertEqual(result.status, 200)
        self.assertEqual(result.body, b"<h1>Safe</h1>")
        self.assertEqual(self.server.paths, ["/"])

    def test_redirect_to_private_dns_target_is_blocked_before_connect(self):
        dns_patch, connection_patch = self._network_patches()
        with dns_patch, connection_patch:
            with self.assertRaisesRegex(SafeFetchError, "blocked address"):
                safe_fetch_url(
                    "http://example.com/redirect",
                    allowed_hosts=["example.com", "rebound.example"],
                )

        self.assertEqual(self.server.paths, ["/redirect"])

    def test_response_size_limit_is_enforced(self):
        dns_patch, connection_patch = self._network_patches()
        with dns_patch, connection_patch:
            with self.assertRaisesRegex(SafeFetchError, "exceeded max_bytes"):
                safe_fetch_url(
                    "http://example.com/large",
                    max_bytes=4,
                    allowed_hosts=["example.com"],
                )

    def test_compressed_response_is_rejected(self):
        dns_patch, connection_patch = self._network_patches()
        with dns_patch, connection_patch:
            with self.assertRaisesRegex(SafeFetchError, "compressed responses"):
                safe_fetch_url(
                    "http://example.com/compressed",
                    allowed_hosts=["example.com"],
                )


if __name__ == "__main__":
    unittest.main()
