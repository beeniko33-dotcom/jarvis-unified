from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from research.public_rss import parse_public_feed, store_headlines


class PublicRssTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
        self.feed = "https://news.example.org/rss.xml"
        self.feed_hosts = ["news.example.org"]
        self.article_hosts = ["news.example.org", "www.example.org"]

    def test_rss_parses_headline_and_timestamp_without_body(self):
        payload = b"""<?xml version="1.0"?><rss version="2.0"><channel><item>
        <title>Market &amp; policy update</title>
        <link>https://www.example.org/story/123</link>
        <pubDate>Sun, 15 Nov 2026 10:00:00 GMT</pubDate>
        <description>FULL ARTICLE BODY MUST NOT BE STORED</description>
        </item></channel></rss>"""
        records = parse_public_feed(
            payload, publisher="Example News", feed_url=self.feed,
            allowed_feed_hosts=self.feed_hosts,
            allowed_article_hosts=self.article_hosts, retrieved_at=self.now,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, "Market & policy update")
        self.assertEqual(records[0].published_at.hour, 10)
        self.assertNotIn("FULL ARTICLE BODY", repr(records[0]))

    def test_atom_parses_alternate_link_and_updated_time(self):
        payload = b"""<feed xmlns="http://www.w3.org/2005/Atom">
        <entry><title>Central bank statement</title>
        <link rel="alternate" href="https://news.example.org/item/1"/>
        <updated>2026-11-15T11:00:00Z</updated></entry></feed>"""
        records = parse_public_feed(
            payload, publisher="Example", feed_url=self.feed,
            allowed_feed_hosts=self.feed_hosts,
            allowed_article_hosts=self.article_hosts, retrieved_at=self.now,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].published_at.hour, 11)

    def test_rejects_unallowlisted_feed_host(self):
        with self.assertRaises(ValueError):
            parse_public_feed(
                b"<rss/>", publisher="Example",
                feed_url="https://unapproved.example/rss",
                allowed_feed_hosts=self.feed_hosts,
                allowed_article_hosts=self.article_hosts, retrieved_at=self.now,
            )

    def test_skips_article_links_outside_allowlist(self):
        payload = b"""<rss><channel><item><title>Headline</title>
        <link>https://unapproved.example/story</link></item></channel></rss>"""
        records = parse_public_feed(
            payload, publisher="Example", feed_url=self.feed,
            allowed_feed_hosts=self.feed_hosts,
            allowed_article_hosts=self.article_hosts, retrieved_at=self.now,
        )
        self.assertEqual(records, [])

    def test_rejects_dtd_and_entity_declarations(self):
        payload = b'<!DOCTYPE rss [<!ENTITY x "boom">]><rss/>'
        with self.assertRaises(ValueError):
            parse_public_feed(
                payload, publisher="Example", feed_url=self.feed,
                allowed_feed_hosts=self.feed_hosts,
                allowed_article_hosts=self.article_hosts, retrieved_at=self.now,
            )

    def test_rejects_utf16_dtd_and_entity_payloads(self):
        payload = '<!DOCTYPE rss [<!ENTITY x "boom">]><rss/>'.encode("utf-16")
        with self.assertRaises(ValueError):
            parse_public_feed(
                payload, publisher="Example", feed_url=self.feed,
                allowed_feed_hosts=self.feed_hosts,
                allowed_article_hosts=self.article_hosts, retrieved_at=self.now,
            )

    def test_rejects_utf32_dtd_and_entity_payloads(self):
        payload = '<!DOCTYPE rss [<!ENTITY x "boom">]><rss/>'.encode("utf-32")
        with self.assertRaises(ValueError):
            parse_public_feed(
                payload, publisher="Example", feed_url=self.feed,
                allowed_feed_hosts=self.feed_hosts,
                allowed_article_hosts=self.article_hosts, retrieved_at=self.now,
            )

    def test_rejects_non_utf8_xml_declaration(self):
        payload = b'<?xml version="1.0" encoding="UTF-16"?><rss/>'
        with self.assertRaises(ValueError):
            parse_public_feed(
                payload, publisher="Example", feed_url=self.feed,
                allowed_feed_hosts=self.feed_hosts,
                allowed_article_hosts=self.article_hosts, retrieved_at=self.now,
            )

    def test_rejects_overlong_publisher(self):
        with self.assertRaises(ValueError):
            parse_public_feed(
                b"<rss/>", publisher="x" * 201, feed_url=self.feed,
                allowed_feed_hosts=self.feed_hosts,
                allowed_article_hosts=self.article_hosts, retrieved_at=self.now,
            )

    def test_rejects_naive_retrieval_time(self):
        with self.assertRaises(ValueError):
            parse_public_feed(
                b"<rss/>", publisher="Example", feed_url=self.feed,
                allowed_feed_hosts=self.feed_hosts,
                allowed_article_hosts=self.article_hosts,
                retrieved_at=datetime(2026, 11, 15),
            )

    def test_rejects_oversized_payload(self):
        with self.assertRaises(ValueError):
            parse_public_feed(
                b"x" * 1_000_001, publisher="Example", feed_url=self.feed,
                allowed_feed_hosts=self.feed_hosts,
                allowed_article_hosts=self.article_hosts, retrieved_at=self.now,
            )

    def test_store_is_append_only_and_deduplicates(self):
        payload = b"""<rss><channel><item><title>Headline</title>
        <link>https://news.example.org/story/1</link>
        <pubDate>Sun, 15 Nov 2026 10:00:00 GMT</pubDate>
        </item></channel></rss>"""
        records = parse_public_feed(
            payload, publisher="Example", feed_url=self.feed,
            allowed_feed_hosts=self.feed_hosts,
            allowed_article_hosts=self.article_hosts, retrieved_at=self.now,
        )
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "headlines.sqlite"
            first = store_headlines(records, db_path)
            second = store_headlines(records, db_path)
            self.assertEqual(first["inserted"], 1)
            self.assertEqual(second["duplicates"], 1)
            db = sqlite3.connect(db_path)
            row = db.execute(
                "SELECT provenance, title FROM public_headlines"
            ).fetchone()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE public_headlines SET title='edited'")
            db.close()
            self.assertEqual(row, ("candidate_unverified", "Headline"))


if __name__ == "__main__":
    unittest.main()
