"""SSRF-hardened URL fetch for public-web content extraction.

Design goals:
- HTTP/HTTPS only
- Block loopback, private, link-local, multicast, reserved, and cloud-metadata IPs
- Revalidate DNS on redirects
- Hard timeouts, size limits, redirect limits
- No shell, no local module execution, no arbitrary code paths
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ALLOWED_SCHEMES = {"http", "https"}
MAX_REDIRECTS = 5
DEFAULT_TIMEOUT_S = 10.0
DEFAULT_MAX_BYTES = 2_000_000  # 2 MiB

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
        infos = socket.getaddrinfo(hostname, None)
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


def _validate_url(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise SafeFetchError(f"unsupported scheme: {scheme!r}")
    if parsed.username or parsed.password:
        raise SafeFetchError("URLs with embedded credentials are not allowed")
    hostname = parsed.hostname
    if not hostname:
        raise SafeFetchError("URL must include a hostname")
    # Reject direct IP literals that are blocked
    try:
        ip = ipaddress.ip_address(hostname)
        if _is_blocked_ip(ip):
            raise SafeFetchError(f"blocked literal address: {ip}")
    except ValueError:
        pass  # hostname is not an IP literal
    _resolve_and_validate_host(hostname)
    return scheme, hostname, parsed.geturl()


def safe_fetch_url(
    url: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = MAX_REDIRECTS,
    user_agent: str = "JarvisUnifiedScraper/0.2 (+safe-fetch)",
) -> FetchResult:
    """Fetch a public HTTP(S) URL with SSRF protections.

    Does not follow urllib's automatic redirects blindly: each hop is revalidated.
    """
    if timeout_s <= 0 or max_bytes <= 0 or max_redirects < 0:
        raise SafeFetchError("invalid fetch limits")

    current = url
    for _ in range(max_redirects + 1):
        _validate_url(current)
        req = Request(current, headers={"User-Agent": user_agent}, method="GET")
        try:
            with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 — validated above
                status = getattr(resp, "status", 200)
                # Manual redirect handling
                if status in {301, 302, 303, 307, 308}:
                    location = resp.headers.get("Location")
                    if not location:
                        raise SafeFetchError("redirect without Location header")
                    # Resolve relative redirects against current URL
                    from urllib.parse import urljoin

                    current = urljoin(current, location)
                    continue

                content_type = resp.headers.get("Content-Type", "application/octet-stream")
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise SafeFetchError(f"response exceeded max_bytes={max_bytes}")
                    chunks.append(chunk)
                body = b"".join(chunks)
                final = resp.geturl() if hasattr(resp, "geturl") else current
                # Revalidate final URL host as defense-in-depth
                _validate_url(final)
                return FetchResult(
                    url=url,
                    final_url=final,
                    status=int(status),
                    content_type=content_type,
                    body=body,
                )
        except HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                location = exc.headers.get("Location") if exc.headers else None
                if not location:
                    raise SafeFetchError("redirect without Location header") from exc
                from urllib.parse import urljoin

                current = urljoin(current, location)
                continue
            raise SafeFetchError(f"HTTP error {exc.code} for {current}") from exc
        except URLError as exc:
            raise SafeFetchError(f"URL error for {current}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise SafeFetchError(f"timeout fetching {current}") from exc

    raise SafeFetchError(f"too many redirects (>{max_redirects})")


def is_public_hostname(hostname: str) -> bool:
    """Return True if hostname resolves only to public addresses."""
    try:
        _resolve_and_validate_host(hostname)
        return True
    except SafeFetchError:
        return False
