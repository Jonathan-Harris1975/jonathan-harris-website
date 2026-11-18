import tempfile
import unittest
from pathlib import Path

from scripts.audits import digital_growth_audit as audit


class DigitalGrowthAuditTests(unittest.TestCase):
  def test_priority_routes_include_core_growth_journeys_and_representatives(self):
    routes = [
      "/", "/newsletter", "/podcast", "/ebooks", "/ebooks/book-one", "/ebooks/book-two",
      "/podcast/episode-one", "/transcripts/episode-one", "/blog/post-one", "/topics/ai",
    ]
    selected = audit.route_priority(routes)
    self.assertEqual(selected[0], "/")
    self.assertIn("/newsletter", selected)
    self.assertIn("/podcast", selected)
    self.assertIn("/ebooks", selected)
    self.assertIn("/ebooks/book-one", selected)
    self.assertIn("/podcast/episode-one", selected)
    self.assertIn("/transcripts/episode-one", selected)

  def test_analysis_url_is_derived_from_digital_growth_callback(self):
    self.assertEqual(
      audit.derive_analysis_url("https://zeroth-kara-jonathanharris-3296ed37.koyeb.app/audits/digital-growth/callback", None),
      "https://zeroth-kara-jonathanharris-3296ed37.koyeb.app/audits/digital-growth/analysis",
    )

  def test_heuristics_do_not_invent_performance_metrics(self):
    pages = [{
      "route": "/", "url": "https://jonathan-harris.online/", "status": 200,
      "title": "Home", "h1": "Home", "ctas": [],
    }]
    issues = audit.heuristic_issues(pages)
    text = " ".join(str(item) for item in issues).lower()
    self.assertNotIn("conversion rate", text)
    self.assertNotIn("search volume", text)
    self.assertIn("newsletter", text)

  def test_workflow_uses_dedicated_audits_bucket_and_cleans_local_temp_files(self):
    workflow = Path(".github/workflows/digital-growth-audit.yml").read_text(encoding="utf-8")
    self.assertIn("R2_BUCKET_AUDITS", workflow)
    self.assertIn("R2_PUBLIC_BASE_URL_AUDITS", workflow)
    self.assertIn("/audits/digital-growth/callback", workflow)
    self.assertIn("rm -rf artifacts/digital-growth", workflow)

  def test_newsletter_cta_uses_same_site_destination_when_label_is_glossary(self):
    for href in ("/newsletter/", "/newsletter/?source=homepage", "#home-newsletter-hero"):
      with self.subTest(href=href):
        page = {"route": "/", "url": "https://example.test/", "status": 200,
                "title": "Home", "h1": "Home", "ctas": [{"label": "Get the glossary", "href": href}]}
        issues = audit.heuristic_issues([page])
        self.assertFalse(any(row["objective"] == "Newsletter Sign-Up Rate" for row in issues))

  def test_newsletter_fragment_matches_word_boundaries_without_false_positives(self):
    for href, expected_match in (
      ("#home_newsletter_cta", True),
      ("#home.newsletter.2026", True),
      ("#home-newsletter2", False),
      ("#home-planetnewsletter-cta", False),
    ):
      with self.subTest(href=href):
        page = {"route": "/", "url": "https://example.test/", "status": 200,
                "title": "Home", "h1": "Home", "ctas": [{"label": "Get the glossary", "href": href}]}
        issues = audit.heuristic_issues([page])
        missing = any(row["objective"] == "Newsletter Sign-Up Rate" for row in issues)
        self.assertEqual(missing, not expected_match)

  def test_unrelated_destinations_cannot_satisfy_newsletter_journey(self):
    for href in ("https://other.test/newsletter/", "/contact?next=/newsletter/", "/newsletter-fake/", "javascript:newsletter()"):
      with self.subTest(href=href):
        page = {"route": "/", "url": "https://example.test/", "status": 200,
                "title": "Home", "h1": "Home", "ctas": [{"label": "Get the glossary", "href": href}]}
        issues = audit.heuristic_issues([page])
        self.assertTrue(any(row["objective"] == "Newsletter Sign-Up Rate" for row in issues))

  def test_success_callback_omits_null_error_and_writes_marker(self):
    posted = []
    original = audit.post_callback
    try:
      audit.post_callback = lambda url, token, payload: posted.append(payload)
      with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        audit.post_digital_growth_callback(
          "https://app.example.test/audits/digital-growth/callback",
          "token",
          output_dir,
          {
            "auditType": "digital-growth",
            "sessionId": "session-1",
            "status": "completed",
            "reportPrefix": "audits/test",
            "reportUrl": "https://example.test/report.html",
            "reportJsonUrl": "https://example.test/report.json",
            "error": None,
          },
        )
        self.assertEqual(len(posted), 1)
        self.assertNotIn("error", posted[0])
        self.assertTrue((output_dir / audit.CALLBACK_MARKER_FILENAME).exists())
    finally:
      audit.post_callback = original

  def test_existing_stage_workflows_clean_local_temporary_files(self):
    seo = Path(".github/workflows/seo-aeo-geo-forensic.yml").read_text(encoding="utf-8")
    mobile = Path(".github/workflows/mobile-ux-hard-gate.yml").read_text(encoding="utf-8")
    self.assertIn("rm -rf artifacts/seo-aeo-geo", seo)
    self.assertIn("rm -rf artifacts/mobile-ux", mobile)


if __name__ == "__main__":
  unittest.main()
