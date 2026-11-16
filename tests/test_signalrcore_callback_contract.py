"""Contract tests against the installed signalrcore transport implementation.

These exercise the real BaseTransport state machine without opening a socket.
They are not a substitute for a local-server wire integration test.
"""
from __future__ import annotations

import unittest

from signalrcore.transport.base_transport import BaseTransport, TransportState


class SignalRCallbackContractTests(unittest.TestCase):
    def test_initial_open_and_reconnect_are_distinct_callbacks(self) -> None:
        events: list[str] = []
        transport = BaseTransport(
            on_open=lambda: events.append("open"),
            on_reconnect=lambda: events.append("reconnect"),
            on_close=lambda: events.append("close"),
        )

        # Initial handshake: connecting -> connected invokes on_open.
        transport._set_state(TransportState.connecting)
        transport._set_state(TransportState.connected)
        self.assertEqual(events, ["open"])

        # Successful reconnect handshake: connected -> reconnecting ->
        # connected invokes on_reconnect, not on_open.
        transport._set_state(TransportState.reconnecting)
        transport._set_state(TransportState.connected)
        self.assertEqual(events, ["open", "reconnect"])

    def test_disconnect_does_not_masquerade_as_reconnect(self) -> None:
        events: list[str] = []
        transport = BaseTransport(
            on_open=lambda: events.append("open"),
            on_reconnect=lambda: events.append("reconnect"),
            on_close=lambda: events.append("close"),
        )
        transport._set_state(TransportState.connecting)
        transport._set_state(TransportState.connected)
        transport._set_state(TransportState.disconnected)
        self.assertEqual(events, ["open", "close"])


if __name__ == "__main__":
    unittest.main()
