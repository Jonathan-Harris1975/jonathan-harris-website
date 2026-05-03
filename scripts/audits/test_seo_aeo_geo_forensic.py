import unittest

from scripts.audits.seo_aeo_geo_forensic import _safe_detail, derive_analysis_url


class SeoAeoGeoForensicWorkflowTests(unittest.TestCase):
  def test_derives_analysis_url_only_from_expected_callback_route(self):
    self.assertEqual(
      derive_analysis_url("https://app.jonathan-harris.online/audits/seo-aeo-geo/callback"),
      "https://app.jonathan-harris.online/audits/seo-aeo-geo/analysis",
    )

  def test_rejects_non_matching_callback_route(self):
    self.assertIsNone(
      derive_analysis_url("https://app.jonathan-harris.online/audits/mobile-ux/callback")
    )

  def test_override_is_respected_for_manual_dispatches(self):
    self.assertEqual(
      derive_analysis_url(
        "https://app.jonathan-harris.online/audits/seo-aeo-geo/callback",
        "https://internal.example/audits/seo-aeo-geo/analysis/",
      ),
      "https://internal.example/audits/seo-aeo-geo/analysis",
    )

  def test_safe_detail_masks_tokens(self):
    detail = _safe_detail("HTTP 500 Bearer secret-token sk-or-secret-value")
    self.assertNotIn("secret-token", detail)
    self.assertNotIn("sk-or-secret-value", detail)
    self.assertIn("Bearer [masked]", detail)


if __name__ == "__main__":
  unittest.main()
