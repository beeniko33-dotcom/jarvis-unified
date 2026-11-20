import unittest

from research.opportunity_sources import (
    OpportunitySource, SourceMethod, source_accepts_url, validate_source,
)


class OpportunitySourceTests(unittest.TestCase):
    def make_source(self, **changes):
        values = dict(
            source_id="company-careers",
            display_name="Company careers",
            allowed_domain="example.com",
            method=SourceMethod.RSS,
            categories=frozenset({"remote_job"}),
            terms_url="https://example.com/terms",
            robots_url="https://example.com/robots.txt",
            minimum_interval_seconds=300,
            enabled=True,
        )
        values.update(changes)
        return OpportunitySource(**values)

    def test_accepts_allowlisted_host_and_real_subdomain(self):
        source = self.make_source()
        self.assertTrue(source_accepts_url(source, "https://example.com/jobs"))
        self.assertTrue(source_accepts_url(source, "https://careers.example.com/role"))
        self.assertFalse(source_accepts_url(source, "https://example.com.attacker.test/jobs"))

    def test_disabled_source_never_accepts_fetch(self):
        self.assertFalse(source_accepts_url(self.make_source(enabled=False), "https://example.com/jobs"))

    def test_rejects_terms_or_robots_on_other_hosts(self):
        with self.assertRaises(ValueError):
            validate_source(self.make_source(robots_url="https://attacker.test/robots.txt"))

    def test_rejects_unreasonable_crawl_interval(self):
        with self.assertRaises(ValueError):
            validate_source(self.make_source(minimum_interval_seconds=1))


if __name__ == "__main__":
    unittest.main()
