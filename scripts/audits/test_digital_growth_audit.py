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
      audit.derive_analysis_url("https://app.jonathan-harris.online/audits/digital-growth/callback", None),
      "https://app.jonathan-harris.online/audits/digital-growth/analysis",
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

  def test_existing_stage_workflows_clean_local_temporary_files(self):
    seo = Path(".github/workflows/seo-aeo-geo-forensic.yml").read_text(encoding="utf-8")
    mobile = Path(".github/workflows/mobile-ux-hard-gate.yml").read_text(encoding="utf-8")
    self.assertIn("rm -rf artifacts/seo-aeo-geo", seo)
    self.assertIn("rm -rf artifacts/mobile-ux", mobile)


if __name__ == "__main__":
  unittest.main()
