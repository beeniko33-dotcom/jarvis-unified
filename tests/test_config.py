import os
import unittest
from unittest.mock import patch

from core.config import Settings


class ConfigTests(unittest.TestCase):
    def test_defaults_to_paper_and_kill_switch_on(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()
            self.assertEqual(settings.mode, "paper")
            self.assertTrue(settings.kill_switch)

    def test_rejects_non_paper_mode(self):
        with patch.dict(os.environ, {"JARVIS_MODE": "live"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()

    def test_rejects_kill_switch_override(self):
        with patch.dict(os.environ, {"KILL_SWITCH": "false"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()

    def test_rejects_public_bind(self):
        with patch.dict(os.environ, {"STATUS_HOST": "0.0.0.0"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()

    def test_rejects_invalid_risk_limit(self):
        with patch.dict(os.environ, {"MAX_DAILY_LOSS": "NaN"}, clear=True):
            with self.assertRaises(ValueError):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()
