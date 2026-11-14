"""Regression tests for the Biquote collector's SignalR dispatch contract.

signalrcore invokes a registered handler as ``handler(message.arguments)``,
where ``message.arguments`` is the JSON array from the hub frame. The collector
registered ``on_tick(tick)`` and passed that value straight to
``build_tick_observation``, which requires a dict. Every real tick therefore
arrived as a list and was rejected, so the collector could never ingest a single
observation even though its unit tests passed.

These tests exercise the dispatch boundary rather than the validator, which is
why the original suite missed it.
"""
import unittest
from datetime import datetime, timezone

from research.biquote_feed import build_tick_observation, unwrap_tick_arguments


class BiquoteDispatchContractTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
        self.tick = {
            "symbol": "EURUSD",
            "bid": 1.08542,
            "ask": 1.08548,
            "mid": 1.08545,
            "timestamp": "2026-11-14T11:59:59Z",
            "source": "MetaTrader 5 (Broker 1)",
            "marketState": "open",
            "stale": False,
            "quoteAgeSeconds": 1,
        }

    def test_single_argument_frame_is_unwrapped(self):
        """The shape signalrcore actually delivers: a one-element list."""
        self.assertEqual(unwrap_tick_arguments([self.tick]), self.tick)

    def test_unwrapped_frame_validates(self):
        """A real dispatch frame must reach the validator as a dict."""
        item = build_tick_observation(
            unwrap_tick_arguments([self.tick]), received_at=self.now
        )
        self.assertEqual(item["instrument"], "EURUSD")
        self.assertEqual(item["mid"], "1.08545")
        self.assertFalse(item["evidence_credit"])

    def test_bare_dict_still_accepted(self):
        """Direct callers and existing tests pass a dict; keep that working."""
        self.assertEqual(unwrap_tick_arguments(self.tick), self.tick)

    def test_empty_frame_is_rejected(self):
        with self.assertRaises(ValueError):
            unwrap_tick_arguments([])

    def test_multi_argument_frame_is_rejected(self):
        """Ambiguous frames must fail closed, not silently take the first item."""
        with self.assertRaises(ValueError):
            unwrap_tick_arguments([self.tick, self.tick])

    def test_non_object_argument_is_rejected(self):
        for bad in ([1], ["EURUSD"], [None], [self.tick, 1]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                unwrap_tick_arguments(bad)


if __name__ == "__main__":
    unittest.main()
