import unittest
from unittest.mock import patch

from apps.telegram.bot import TelegramStatusBot, parse_command


class TelegramStatusBotTests(unittest.TestCase):
    def setUp(self):
        self.bot = TelegramStatusBot("not-a-real-token", "12345")
        self.sent = []
        self.bot._telegram_request = lambda method, payload: self.sent.append((method, payload))

    def test_parse_command_accepts_only_read_only_commands(self):
        self.assertEqual(parse_command("/health"), "/health")
        self.assertEqual(parse_command("/status@jarvis_bot"), "/status")
        self.assertIsNone(parse_command("/buy"))
        self.assertIsNone(parse_command("status"))

    @patch("apps.telegram.bot.local_health_ok", return_value=True)
    def test_authorized_health_command_sends_only_fixed_safe_status(self, health_check):
        self.bot.handle_update(
            {"message": {"chat": {"id": 12345}, "text": "/status"}}
        )

        self.assertEqual(len(self.sent), 1)
        method, payload = self.sent[0]
        self.assertEqual(method, "sendMessage")
        self.assertEqual(payload["chat_id"], "12345")
        self.assertEqual(
            payload["text"],
            "Jarvis Unified is healthy (paper-only; live trading disabled).",
        )
        self.assertEqual(set(payload), {"chat_id", "text"})
        health_check.assert_called_once_with("http://127.0.0.1:8787/health")

    @patch("apps.telegram.bot.local_health_ok")
    def test_unauthorized_chat_is_ignored(self, health_check):
        self.bot.handle_update(
            {"message": {"chat": {"id": 99999}, "text": "/health"}}
        )

        self.assertEqual(self.sent, [])
        health_check.assert_not_called()

    def test_missing_runtime_credentials_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "TELEGRAM_BOT_TOKEN"):
            TelegramStatusBot("", "12345")
        with self.assertRaisesRegex(ValueError, "TELEGRAM_CHAT_ID"):
            TelegramStatusBot("token", "")

    def test_non_local_status_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "local health endpoint"):
            TelegramStatusBot("token", "12345", "https://example.com/health")


if __name__ == "__main__":
    unittest.main()
