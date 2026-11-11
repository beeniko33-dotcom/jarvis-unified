import os
import unittest
from unittest.mock import patch

from main import main


class MainCliTests(unittest.TestCase):
    def test_serve_accepts_custom_host_and_port(self):
        seen = {}

        def fake_serve(host, port, provider):
            seen["host"] = host
            seen["port"] = port
            seen["status"] = provider()

        with patch.dict(os.environ, {}, clear=True):
            with patch("apps.api.status.serve", fake_serve):
                main(["--serve", "--host", "localhost", "--port", "9001"])

        self.assertEqual(seen["host"], "localhost")
        self.assertEqual(seen["port"], 9001)
        self.assertEqual(seen["status"]["broker"], "paper")


if __name__ == "__main__":
    unittest.main()
