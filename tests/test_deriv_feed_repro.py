"""Regression tests for defects found in the Deriv forward-evidence path.

Defect A: resolve_eurusd_symbol() accepted any symbol whose display_name normalised
to "EURUSD", but validate_deriv_observation_binding() hard-required the literal
"FRXEURUSD". A symbol the resolver accepted could therefore never pass the binding
check, so collect() raised RuntimeError on the first tick.

Defect B: deriv_feed.main() returned 0 whenever the hash chain was intact, even when
the evidence gate was BLOCKED_PROVENANCE with zero observations. A cron job or CI
step would read success while no evidence existed at all.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from research.deriv_feed import (
    DERIV_PUBLIC_WS,
    build_tick_observation,
    resolve_eurusd_symbol,
    validate_deriv_observation_binding,
)
from research.forward_validation import ForwardEvidenceStore


def _session() -> dict:
    return {
        "session_id": "s1",
        "endpoint": DERIV_PUBLIC_WS,
        "provider": "Deriv",
        "tls_socket_observed": True,
        "evidence_credit": False,
    }


def _tick(symbol: str, quote: str = "1.0850", epoch: int = 1763000000) -> str:
    return json.dumps(
        {"msg_type": "tick", "tick": {"symbol": symbol, "epoch": epoch, "quote": quote}}
    )


class ResolverValidatorAgreementTests(unittest.TestCase):
    """Defect A: anything the resolver accepts must pass the binding validator."""

    def test_display_name_only_match_is_rejected_by_resolver(self):
        # display_name says EUR/USD but the code is not the canonical Deriv code.
        with self.assertRaises(ValueError):
            resolve_eurusd_symbol([{"symbol": "EURUSD", "display_name": "EUR/USD"}])

    def test_canonical_symbol_resolves_and_validates(self):
        symbol = resolve_eurusd_symbol(
            [{"symbol": "frxEURUSD", "display_name": "EUR/USD"}]
        )
        self.assertEqual(symbol, "frxEURUSD")
        item = build_tick_observation(
            _tick(symbol),
            deriv_symbol=symbol,
            received_at=datetime.now(timezone.utc),
            transport_session=_session(),
        )
        self.assertTrue(validate_deriv_observation_binding(item))

    def test_every_resolved_symbol_passes_binding(self):
        # The invariant that was broken: resolver output must be validator-acceptable.
        for entry in (
            [{"symbol": "frxEURUSD", "display_name": "EUR/USD"}],
            [{"symbol": "frxEURUSD", "display_name": "EUR/USD", "market": "forex"}],
        ):
            symbol = resolve_eurusd_symbol(entry)
            item = build_tick_observation(
                _tick(symbol),
                deriv_symbol=symbol,
                received_at=datetime.now(timezone.utc),
                transport_session=_session(),
            )
            self.assertTrue(
                validate_deriv_observation_binding(item),
                f"resolver accepted {symbol!r} but binding rejected it",
            )

    def test_ambiguous_matches_still_rejected(self):
        with self.assertRaises(ValueError):
            resolve_eurusd_symbol(
                [
                    {"symbol": "frxEURUSD", "display_name": "EUR/USD"},
                    {"symbol": "FRXEURUSD", "display_name": "EUR/USD"},
                ]
            )


class EmptyDatabaseExitCodeTests(unittest.TestCase):
    """Defect B: an empty store must not report success."""

    def test_empty_store_gate_is_blocked(self):
        db = Path(tempfile.mkdtemp()) / "empty.sqlite3"
        store = ForwardEvidenceStore(
            db,
            instrument="EURUSD",
            provider="Deriv",
            interval="tick",
            strategy_id="sma-crossover-long",
            strategy_version="1.0.0",
        )
        try:
            report = store.report(30)
        finally:
            store.close()
        self.assertEqual(report["level_3_forward_evidence_gate"], "BLOCKED_PROVENANCE")
        self.assertEqual(report["observation_count"], 0)
        # The chain of zero records is trivially valid; that must not be read as success.
        self.assertTrue(report["event_chain_valid"])

    def test_exit_code_follows_gate_not_chain(self):
        from research.deriv_feed import exit_code_for_report

        db = Path(tempfile.mkdtemp()) / "empty.sqlite3"
        store = ForwardEvidenceStore(
            db,
            instrument="EURUSD",
            provider="Deriv",
            interval="tick",
            strategy_id="sma-crossover-long",
            strategy_version="1.0.0",
        )
        try:
            report = store.report(30)
        finally:
            store.close()
        self.assertNotEqual(exit_code_for_report(report), 0)


if __name__ == "__main__":
    unittest.main()
