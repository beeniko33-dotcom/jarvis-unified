import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from packages.scraper import PageMetadata, SafeFetchError
from packages.scraper.__main__ import main


class ScraperCliTests(unittest.TestCase):
    def test_prints_metadata_as_json(self):
        expected = PageMetadata(
            source_url="https://example.com/",
            final_url="https://example.com/",
            status=200,
            title="Example",
            description=None,
            headings=("Overview",),
        )
        output = io.StringIO()
        with patch("packages.scraper.__main__.extract_page_metadata", return_value=expected):
            with redirect_stdout(output):
                main(["https://example.com/"])

        self.assertEqual(json.loads(output.getvalue()), {
            "source_url": "https://example.com/",
            "final_url": "https://example.com/",
            "status": 200,
            "title": "Example",
            "description": None,
            "headings": ["Overview"],
        })

    def test_fetch_errors_are_reported_as_cli_errors(self):
        errors = io.StringIO()
        with patch(
            "packages.scraper.__main__.extract_page_metadata",
            side_effect=SafeFetchError("blocked destination"),
        ):
            with redirect_stderr(errors), self.assertRaises(SystemExit) as result:
                main(["https://example.com/"])

        self.assertEqual(result.exception.code, 2)
        self.assertIn("blocked destination", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
