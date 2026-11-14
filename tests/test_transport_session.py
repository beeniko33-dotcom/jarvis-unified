"""Adversarial invariants for the Issue #9 transport/session boundary.

Includes a positive path that exercises build_deriv_public_session against a
real locally-established SSLSocket (Issue #32). The positive path still asserts
evidence_credit=False and never unlocks provenance.
"""
from __future__ import annotations

import socket
import ssl
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from research.forward_validation import ForwardEvidenceStore
from research.transport_session import (
    DERIV_PUBLIC_WS,
    _validate_deriv_endpoint,
    TransportSessionRecord,
    assert_no_evidence_credit,
    build_deriv_public_session,
)


def _generate_self_signed_cert(tmpdir: Path) -> tuple[Path, Path]:
    """Create a short-lived self-signed cert+key for offline TLS tests."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime as dt

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1))
        .not_valid_after(dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(u"localhost")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    key_path = tmpdir / "test.key"
    cert_path = tmpdir / "test.crt"
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


class TransportSessionTests(unittest.TestCase):
    def test_endpoint_is_exactly_pinned(self):
        self.assertEqual(_validate_deriv_endpoint(DERIV_PUBLIC_WS), DERIV_PUBLIC_WS)
        for endpoint in (
            "wss://evil.example/trading/v1/options/ws/public",
            "wss://api.derivws.com.evil.example/trading/v1/options/ws/public",
            "https://api.derivws.com/trading/v1/options/ws/public",
            "wss://user@api.derivws.com/trading/v1/options/ws/public",
            "wss://api.derivws.com/trading/v1/options/ws/public?x=1",
            "wss://api.derivws.com/other",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                _validate_deriv_endpoint(endpoint)

    def test_builder_requires_real_tls_socket(self):
        with self.assertRaisesRegex(ValueError, "SSLSocket"):
            build_deriv_public_session(
                endpoint=DERIV_PUBLIC_WS,
                tls_socket=Mock(),
            )

    def test_builder_rejects_wrong_endpoint_before_socket_use(self):
        with self.assertRaisesRegex(ValueError, "exact approved"):
            build_deriv_public_session(
                endpoint="wss://evil.example/",
                tls_socket=Mock(),
            )

    def test_session_started_at_must_be_timezone_aware(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            build_deriv_public_session(
                endpoint=DERIV_PUBLIC_WS,
                tls_socket=Mock(),
                started_at=datetime(2026, 11, 13, 12, 0, 0),
            )

    def test_session_json_copy_cannot_mutate_immutable_record(self):
        # This test asserts the record serializer's invariant. An altered JSON
        # copy is untrusted input and is not treated as a canonical record.
        record = TransportSessionRecord(
            session_id="session-test",
            endpoint=DERIV_PUBLIC_WS,
            provider="Deriv",
            started_at="2026-11-13T12:00:00+00:00",
            tls_socket_observed=True,
            peer_certificate_present=True,
            peer_certificate_sha256="abc",
            certificate_verification_mode="CERT_REQUIRED",
            hostname_check_enabled=True,
            collector_identity=None,
            notes="informational",
            evidence_credit=True,
        )
        with self.assertRaises(AssertionError):
            assert_no_evidence_credit(record)

    def test_store_still_blocks_provenance_with_forged_session_metadata(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        now = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
        store = ForwardEvidenceStore(
            Path(tmp.name) / "fwd.sqlite3",
            instrument="EURUSD",
            provider="Deriv",
            interval="tick",
            strategy_id="sma-crossover-long",
            strategy_version="1.0.0",
            clock=lambda: now,
        )
        self.addCleanup(store.close)
        item = {
            "observed_at": now.isoformat(),
            "instrument": "EURUSD",
            "provider": "Deriv",
            "source": "deriv-public-wss-tick-v1",
            "interval": "tick",
            "strategy_id": "sma-crossover-long",
            "strategy_version": "1.0.0",
            "price": "1.08500",
            "transport_endpoint": DERIV_PUBLIC_WS,
            "transport_session_id": "forged-session",
            "transport_session": {
                "session_id": "forged-session",
                "endpoint": DERIV_PUBLIC_WS,
                "provider": "Deriv",
                "tls_socket_observed": True,
                "evidence_credit": False,
            },
            "provenance_verified": True,
        }
        self.assertTrue(store.ingest(item))
        report = store.report(1)
        self.assertEqual(report["verified_observation_count"], 0)
        self.assertEqual(report["level_3_forward_evidence_gate"], "BLOCKED_PROVENANCE")
        self.assertFalse(report["level_3_certification"])
        self.assertFalse(report["provider_signature_or_equivalent_verifier_configured"])

    def test_positive_sslsocket_path_still_denies_evidence_credit(self):
        """Issue #32: exercise the real builder path with an established SSLSocket.

        Uses a local loopback TLS server and a client context that trusts the
        test CA. The resulting TransportSessionRecord must still carry
        evidence_credit=False and must never unlock provenance.
        """
        try:
            from cryptography import x509  # noqa: F401
        except ImportError:
            self.skipTest("cryptography package required for local TLS fixture")

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cert_path, key_path = _generate_self_signed_cert(Path(tmp.name))

        # Server side
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def _serve():
            try:
                conn, _ = listener.accept()
                with server_ctx.wrap_socket(conn, server_side=True) as tls_conn:
                    tls_conn.recv(1)  # wait for client data / keep alive briefly
            except Exception:
                pass
            finally:
                try:
                    listener.close()
                except Exception:
                    pass

        t = threading.Thread(target=_serve, daemon=True)
        t.start()

        # Client side — trust the test cert, require CERT_REQUIRED + hostname check
        client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        client_ctx.verify_mode = ssl.CERT_REQUIRED
        client_ctx.check_hostname = True
        client_ctx.load_verify_locations(cafile=str(cert_path))

        raw = socket.create_connection(("127.0.0.1", port), timeout=2.0)
        tls_sock = client_ctx.wrap_socket(raw, server_hostname="localhost")
        self.addCleanup(tls_sock.close)

        # Positive path: real SSLSocket with correct verification settings
        record = build_deriv_public_session(
            endpoint=DERIV_PUBLIC_WS,
            tls_socket=tls_sock,
            started_at=datetime.now(timezone.utc),
            collector_identity="test-fixture",
        )

        self.assertIsInstance(record, TransportSessionRecord)
        self.assertTrue(record.tls_socket_observed)
        self.assertTrue(record.peer_certificate_present)
        self.assertIsNotNone(record.peer_certificate_sha256)
        self.assertEqual(len(record.peer_certificate_sha256), 64)
        self.assertEqual(record.certificate_verification_mode, "CERT_REQUIRED")
        self.assertTrue(record.hostname_check_enabled)
        self.assertEqual(record.endpoint, DERIV_PUBLIC_WS)
        self.assertFalse(record.evidence_credit)
        assert_no_evidence_credit(record)

        # Explicit negative controls still required
        with self.assertRaises(ValueError):
            # CERT_NONE must be rejected
            bad_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            bad_ctx.check_hostname = False
            bad_ctx.verify_mode = ssl.CERT_NONE
            # We cannot easily re-wrap the same socket; instead assert the
            # builder would reject a socket whose context is CERT_NONE by
            # constructing a Mock that looks like SSLSocket but has bad context.
            bad_sock = Mock(spec=ssl.SSLSocket)
            bad_sock.context = bad_ctx
            bad_sock.getpeercert.return_value = b"dummy"
            build_deriv_public_session(endpoint=DERIV_PUBLIC_WS, tls_socket=bad_sock)


if __name__ == "__main__":
    unittest.main()
