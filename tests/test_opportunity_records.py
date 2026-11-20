from datetime import datetime
import unittest

from research.opportunity_records import canonical_source_url, normalize_opportunity


class OpportunityRecordTests(unittest.TestCase):
    def test_normalizes_and_deduplicates_tracking_variants(self):
        a = normalize_opportunity(
            title="Remote Python Engineer", description="Build APIs remotely.",
            category="remote_job", source_url="https://Jobs.Example.com/role/1?utm_source=x#top",
            country_eligibility=("ng", "US"),
        )
        b = normalize_opportunity(
            title="Remote Python Engineer", description="Build APIs remotely.",
            category="remote_job", source_url="https://jobs.example.com/role/1?ref=abc",
            country_eligibility=("US", "NG"),
        )
        self.assertEqual(a.fingerprint, b.fingerprint)
        self.assertEqual(a.country_eligibility, ("NG", "US"))
        self.assertEqual(a.verification_status, "unverified")
        self.assertFalse(a.external_submission_allowed)

    def test_flags_suspicious_content_without_claiming_definitive_scam(self):
        item = normalize_opportunity(
            title="Remote job with guaranteed income",
            description="Pay to apply and send bitcoin for registration.",
            category="remote_job", source_url="https://example.org/job",
        )
        self.assertIn("upfront_fee_request", item.risk_flags)
        self.assertIn("unrealistic_income_claim", item.risk_flags)
        self.assertIn("crypto_payment_request", item.risk_flags)

    def test_rejects_http_credentials_and_invalid_hosts(self):
        for url in ("http://example.com/job", "https://user:pass@example.com", "https://localhost"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                canonical_source_url(url)

    def test_rejects_naive_timestamps_and_unknown_category(self):
        with self.assertRaises(ValueError):
            normalize_opportunity(
                title="Role", description="Description", category="remote_job",
                source_url="https://example.com", published_at=datetime(2026, 1, 1),
            )
        with self.assertRaises(ValueError):
            normalize_opportunity(
                title="Role", description="Description", category="other",
                source_url="https://example.com",
            )


if __name__ == "__main__":
    unittest.main()
