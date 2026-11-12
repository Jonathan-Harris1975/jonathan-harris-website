import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class VerifiedPrintFormatContract(unittest.TestCase):
    def test_print_migration_is_separate_and_fails_closed(self):
        sql = (ROOT / "migrations/0002_create_kdp_print_editions.sql").read_text()
        self.assertIn("live_verified", sql)
        self.assertIn("UNIQUE INDEX", sql)
        self.assertIn("REFERENCES ebooks(ebook_id)", sql)

    def test_only_verified_amazon_editions_in_public_api(self):
        js = (ROOT / "functions/api/v1/ebooks.json.js").read_text()
        self.assertIn("publicPrintFormat", js)
        self.assertIn("state = 'live_verified'", js)
        self.assertIn("amazon.co.uk", js)
        self.assertIn("print_formats", js)

    def test_pages_keep_kindle_and_use_shared_progressive_enhancement(self):
        js = (ROOT / "assets/js/ebook-print-formats.js").read_text()
        middleware = (ROOT / "functions/_middleware.js").read_text()
        self.assertIn('"/api/v1/ebooks.json"', js)
        self.assertIn('data-print-format', js)
        self.assertIn('ebook-print-formats.js', middleware)
        self.assertIn('addHomepageAgentDiscovery(context.request, page)', middleware)

if __name__ == "__main__":
    unittest.main()
