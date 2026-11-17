import unittest
from unittest.mock import patch

from research import deriv_feed


class FakeWebSocketError(Exception):
    pass


class FakeWebSocketModule:
    WebSocketException = FakeWebSocketError


class DerivReconnectTests(unittest.TestCase):
    def test_transient_connect_failures_use_bounded_exponential_backoff(self):
        expected = (object(), "frxEURUSD", {"session_id": "fresh-session"})
        with patch.object(
            deriv_feed, "_open_public_subscription",
            side_effect=[FakeWebSocketError("offline"), OSError("reset"), expected],
        ) as open_socket, patch.object(deriv_feed.time, "sleep") as sleep:
            result = deriv_feed._open_with_bounded_retries(
                FakeWebSocketModule, 20, expected_symbol="frxEURUSD",
                max_reconnects=3, backoff_seconds=0.5,
            )
        self.assertEqual(result, expected)
        self.assertEqual(open_socket.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.5, 1.0])
        self.assertEqual(open_socket.call_args.args[2], "frxEURUSD")

    def test_retry_budget_exhaustion_fails_closed(self):
        with patch.object(
            deriv_feed, "_open_public_subscription",
            side_effect=FakeWebSocketError("connection lost"),
        ) as open_socket, patch.object(deriv_feed.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "bounded retries"):
                deriv_feed._open_with_bounded_retries(
                    FakeWebSocketModule, 20, max_reconnects=2, backoff_seconds=1,
                )
        self.assertEqual(open_socket.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

    def test_symbol_change_during_reconnect_is_not_retried_or_accepted(self):
        with patch.object(
            deriv_feed, "_open_public_subscription",
            side_effect=RuntimeError("Deriv EUR/USD symbol changed during collection"),
        ) as open_socket, patch.object(deriv_feed.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "symbol changed"):
                deriv_feed._open_with_bounded_retries(
                    FakeWebSocketModule, 20, expected_symbol="frxEURUSD",
                    max_reconnects=5,
                )
        open_socket.assert_called_once()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
