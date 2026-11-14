"""Repro: a scalar credential could still reach a reflection.

``_renderable()`` rejected dictionaries and lists but accepted arbitrary
strings, so a credential placed in an allowlisted *string* field was rendered
verbatim. The key allowlist cannot see inside a value, so each field now has
its own format contract: hashes must be hex digests, identifiers must be
bounded identifier-shaped, and anything credential-shaped, malformed or
non-finite is reported as ``unknown``.
"""
from __future__ import annotations

import unittest

from research.paper_reflection_bridge import _render_lineage, _summary


class ScalarCredentialTests(unittest.TestCase):
    def test_credential_shaped_string_in_allowlisted_field_is_unknown(self) -> None:
        """A secret in an allowlisted string field must not be echoed."""
        data = {
            "source_event_type": "paper_close",
            "symbol": "EURUSD",
            "quote_source": "sk-live-abc123def456ghi789",
        }
        statement = _summary("paper_ledger_event", data)
        self.assertIn("quote_source=unknown", statement)
        self.assertNotIn("sk-live-abc123def456ghi789", statement)

    def test_credential_markers_are_rejected_across_fields(self) -> None:
        for secret in (
            "api_key=AKIAIOSFODNN7EXAMPLE",
            "Bearer eyJhbGciOiJIUzI1NiJ9",
            "ghp_16CharactersOfFakeToken",
            "-----BEGIN PRIVATE KEY-----",
            "client_secret: hunter2",
        ):
            with self.subTest(secret=secret):
                self.assertEqual(_render_lineage("strategy_id", secret), "unknown")

    def test_malformed_hash_is_unknown(self) -> None:
        """A hash field must hold a hex digest, not arbitrary text."""
        for field in ("strategy_config_hash", "signal_context_hash", "data_hash"):
            with self.subTest(field=field):
                self.assertEqual(_render_lineage(field, "not-a-hex-digest"), "unknown")
                self.assertEqual(_render_lineage(field, "zzzzzzzzzzzz"), "unknown")
                self.assertEqual(_render_lineage(field, "abc"), "unknown")

    def test_valid_hash_still_renders(self) -> None:
        digest = "a" * 64
        self.assertEqual(_render_lineage("data_hash", digest), digest)

    def test_non_finite_number_is_unknown(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                self.assertEqual(_render_lineage("strategy_version", value), "unknown")

    def test_finite_number_still_renders(self) -> None:
        self.assertEqual(_render_lineage("strategy_version", 3), "3")
        self.assertEqual(_render_lineage("strategy_version", 1.5), "1.5")

    def test_structured_value_is_unknown(self) -> None:
        self.assertEqual(_render_lineage("quote_source", {"api_key": "x"}), "unknown")
        self.assertEqual(_render_lineage("quote_source", ["a", "b"]), "unknown")

    def test_identifier_with_spaces_is_unknown(self) -> None:
        self.assertEqual(
            _render_lineage("strategy_id", "my strategy with spaces"), "unknown"
        )

    def test_free_text_reason_still_renders(self) -> None:
        self.assertEqual(
            _render_lineage("risk_reason", "per-symbol exposure limit exceeded"),
            "per-symbol exposure limit exceeded",
        )


if __name__ == "__main__":
    unittest.main()
