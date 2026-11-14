import unittest
from unittest.mock import patch

from packages.scraper import PageMetadata, SafeFetchError, extract_page_metadata
from packages.scraper.safe_fetch import FetchResult


class PageMetadataExtractionTests(unittest.TestCase):
    def test_extracts_only_bounded_page_metadata(self):
        body = (
            b"<html><head><title> Example   Site </title>"
            b'<meta name="description" content="A public site">'
            b"</head><body><h1>Overview</h1><h2>News</h2>"
            b"<script><h2>Hidden heading</h2></script>"
            b"<p>person@example.com</p></body></html>"
        )
        result = FetchResult(
            url="https://example.com/",
            final_url="https://example.com/article",
            status=200,
            content_type="text/html; charset=utf-8",
            body=body,
        )
        with patch("packages.scraper.extract.safe_fetch_url", return_value=result):
            page = extract_page_metadata(
                "https://example.com/",
                allowed_hosts=["example.com"],
            )

        self.assertEqual(
            page,
            PageMetadata(
                source_url="https://example.com/",
                final_url="https://example.com/article",
                status=200,
                title="Example Site",
                description="A public site",
                headings=("Overview", "News"),
            ),
        )
        self.assertNotIn("person@example.com", repr(page))

    def test_rejects_non_html_responses(self):
        result = FetchResult(
            url="https://example.com/data.json",
            final_url="https://example.com/data.json",
            status=200,
            content_type="application/json",
            body=b'{"private":"not extracted"}',
        )
        with patch("packages.scraper.extract.safe_fetch_url", return_value=result):
            with self.assertRaisesRegex(SafeFetchError, "HTML document"):
                extract_page_metadata(
                    "https://example.com/data.json",
                    allowed_hosts=["example.com"],
                )

    def test_rejects_unknown_html_charset(self):
        result = FetchResult(
            url="https://example.com/",
            final_url="https://example.com/",
            status=200,
            content_type="text/html; charset=not-a-real-encoding",
            body=b"<title>Page</title>",
        )
        with patch("packages.scraper.extract.safe_fetch_url", return_value=result):
            with self.assertRaisesRegex(SafeFetchError, "unsupported character encoding"):
                extract_page_metadata(
                    "https://example.com/",
                    allowed_hosts=["example.com"],
                )

    def test_metadata_fields_and_heading_count_are_bounded(self):
        body = (
            f"<title>{'T' * 800}</title>"
            f'<meta name="description" content="{"D" * 800}">'
            + "".join(f"<h2>{index}{'H' * 400}</h2>" for index in range(20))
        ).encode()
        result = FetchResult(
            url="https://example.com/",
            final_url="https://example.com/",
            status=200,
            content_type="text/html; charset=utf-8",
            body=body,
        )
        with patch("packages.scraper.extract.safe_fetch_url", return_value=result):
            page = extract_page_metadata(
                "https://example.com/",
                allowed_hosts=["example.com"],
            )

        self.assertLessEqual(len(page.title or ""), 500)
        self.assertLessEqual(len(page.description or ""), 500)
        self.assertLessEqual(len(page.headings), 10)
        self.assertTrue(all(len(heading) <= 200 for heading in page.headings))


if __name__ == "__main__":
    unittest.main()
