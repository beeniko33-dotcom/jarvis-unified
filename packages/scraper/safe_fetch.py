"""SSRF-hardened URL fetch for public-web content extraction.

Design goals:
- HTTP/HTTPS only
- Block loopback, private, link-local, multicast, reserved, and cloud-metadata IPs
- Revalidate DNS on redirects
- Hard timeouts, size limits, redirect limits
- No shell, no local module execution, no arbitrary code paths
"""
from __future__ import annotations

import http.client
import ipaddress
import math
import socket
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 5
DEFAULT_TIMEOUT_S = 10.0
DEFAULT_MAX_BYTES = 2_000_000  # 2 MiB
MAX_TIMEOUT_S = 60.0
MAX_RESPONSE_BYTES = 10_000_000
MAX_REDIRECT_COUNT = 10

# Common cloud metadata / link-local ranges
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]


class SafeFetchError(ValueError):
    """Raised when a URL is rejected for safety or fetch policy reasons."""


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved:
        return True
    if ip.is_unspecified:
        return True
    for net in BLOCKED_NETWORKS:
        if ip in net:
            return True
    return False


def _resolve_and_validate_host(hostname: str) -> list[str]:
    if not hostname or hostname.lower() in {"localhost", "metadata", "metadata.google.internal"}:
        raise SafeFetchError(f"blocked hostname: {hostname!r}")
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SafeFetchError(f"DNS resolution failed for {hostname!r}: {exc}") from exc
    resolved: list[str] = []
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise SafeFetchError(f"invalid resolved address {ip_str!r}") from exc
        # Normalize IPv4-mapped IPv6
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if _is_blocked_ip(ip):
            raise SafeFetchError(f"blocked address for host {hostname!r}: {ip}")
        resolved.append(str(ip))
    if not resolved:
        raise SafeFetchError(f"no usable addresses for {hostname!r}")
    return resolved


def _validate_url(url: str) -> tuple[str, str, str, int, list[str]]:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as exc:
        raise SafeFetchError("invalid URL") from exc
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise SafeFetchError(f"unsupported scheme: {scheme!r}")
    if parsed.username is not None or parsed.password is not None:
        raise SafeFetchError("URLs with embedded credentials are not allowed")
    hostname = parsed.hostname
    if not hostname:
        raise SafeFetchError("URL must include a hostname")
    default_port = 443 if scheme == "https" else 80
    if port not in {None, default_port}:
        raise SafeFetchError("only standard HTTP and HTTPS ports are supported")
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise SafeFetchError("invalid hostname") from exc
    # Reject direct IP literals that are blocked
    try:
        ip = ipaddress.ip_address(hostname)
        if _is_blocked_ip(ip):
            raise SafeFetchError(f"blocked literal address: {ip}")
    except ValueError:
        pass  # hostname is not an IP literal
    resolved_addresses = _resolve_and_validate_host(hostname)
    return scheme, hostname, parsed.geturl(), default_port, resolved_addresses


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, hostname: str, port: int, address: str, timeout_s: float) -> None:
        super().__init__(hostname, port, timeout=timeout_s)
        self._resolved_address = address

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._resolved_address, self.port),
            timeout=self.timeout,
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname: str, port: int, address: str, timeout_s: float) -> None:
        super().__init__(hostname, port, timeout=timeout_s)
        self._resolved_address = address

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._resolved_address, self.port),
            timeout=self.timeout,
        )
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)


def safe_fetch_url(
    url: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = MAX_REDIRECTS,
    user_agent: str = "JarvisUnifiedScraper/0.2 (+safe-fetch)",
) -> FetchResult:
    """Fetch a public HTTP(S) URL, pinning and revalidating each destination."""
    if (
        not math.isfinite(timeout_s)
        or timeout_s <= 0
        or timeout_s > MAX_TIMEOUT_S
        or max_bytes <= 0
        or max_bytes > MAX_RESPONSE_BYTES
        or max_redirects < 0
        or max_redirects > MAX_REDIRECT_COUNT
    ):
        raise SafeFetchError("invalid fetch limits")
    if not user_agent or len(user_agent) > 256 or "\r" in user_agent or "\n" in user_agent:
        raise SafeFetchError("invalid user agent")

    current = url
    deadline = time.monotonic() + timeout_s
    for _ in range(max_redirects + 1):
        scheme, hostname, current, port, addresses = _validate_url(current)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SafeFetchError(f"timeout fetching {hostname}")
        parsed = urlparse(current)
        target = parsed.path or "/"
        if parsed.params:
            target += ";" + parsed.params
        if parsed.query:
            target += "?" + parsed.query
        if any(ord(char) < 32 or ord(char) == 127 for char in target):
            raise SafeFetchError("URL path contains control characters")

        connection_type = _PinnedHTTPSConnection if scheme == "https" else _PinnedHTTPConnection
        connection = connection_type(hostname, port, addresses[0], remaining)
        try:
            connection.request(
                "GET",
                target,
                headers={
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                    "User-Agent": user_agent,
                },
            )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SafeFetchError(f"timeout fetching {hostname}")
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            response = connection.getresponse()
            status = response.status
            if status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise SafeFetchError("redirect without Location header")
                current = urljoin(current, location)
                continue
            if status >= 400:
                raise SafeFetchError(f"HTTP error {status} for {hostname}")
            content_encoding = (response.getheader("Content-Encoding") or "identity").lower()
            if content_encoding != "identity":
                raise SafeFetchError("compressed responses are not supported")
            content_type = response.getheader("Content-Type", "application/octet-stream")
            content_length = response.getheader("Content-Length")
            if content_length is not None:
                try:
                    declared_length = int(content_length)
                except ValueError as exc:
                    raise SafeFetchError("invalid response content length") from exc
                if declared_length < 0 or declared_length > max_bytes:
                    raise SafeFetchError(f"response exceeded max_bytes={max_bytes}")

            chunks: list[bytes] = []
            total = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SafeFetchError(f"timeout fetching {hostname}")
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read(min(64 * 1024, max_bytes - total + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise SafeFetchError(f"response exceeded max_bytes={max_bytes}")
                chunks.append(chunk)
            return FetchResult(
                url=url,
                final_url=current,
                status=int(status),
                content_type=content_type,
                body=b"".join(chunks),
            )
        except SafeFetchError:
            raise
        except (http.client.HTTPException, OSError) as exc:
            raise SafeFetchError(f"request failed for {hostname}: {exc}") from exc
        finally:
            connection.close()

    raise SafeFetchError(f"too many redirects (>{max_redirects})")


def is_public_hostname(hostname: str) -> bool:
    """Return True if hostname resolves only to public addresses."""
    try:
        _resolve_and_validate_host(hostname)
        return True
    except SafeFetchError:
        return False
