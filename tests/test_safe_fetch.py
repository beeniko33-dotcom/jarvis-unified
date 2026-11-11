import unittest

from packages.scraper.safe_fetch import SafeFetchError, is_public_hostname, safe_fetch_url


class SafeFetchTests(unittest.TestCase):
    def test_rejects_file_scheme(self):
        with self.assertRaises(SafeFetchError):
            safe_fetch_url("file:///etc/passwd")

    def test_rejects_localhost(self):
        with self.assertRaises(SafeFetchError):
            safe_fetch_url("http://localhost/admin")

    def test_rejects_loopback_ip(self):
        with self.assertRaises(SafeFetchError):
            safe_fetch_url("http://127.0.0.1/")

    def test_rejects_private_ip(self):
        with self.assertRaises(SafeFetchError):
            safe_fetch_url("http://192.168.1.10/")

    def test_rejects_metadata_host(self):
        with self.assertRaises(SafeFetchError):
            safe_fetch_url("http://metadata.google.internal/")

    def test_rejects_credentials_in_url(self):
        with self.assertRaises(SafeFetchError):
            safe_fetch_url("https://user:pass@example.com/")

    def test_is_public_hostname_localhost_false(self):
        self.assertFalse(is_public_hostname("localhost"))


if __name__ == "__main__":
        unittest.main()
