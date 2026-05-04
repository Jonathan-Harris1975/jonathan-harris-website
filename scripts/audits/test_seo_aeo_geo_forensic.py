import argparse
import os
import unittest

from scripts.audits import seo_aeo_geo_forensic as audit


class SeoAeoGeoForensicWorkflowTests(unittest.TestCase):
  def test_derives_analysis_url_only_from_expected_callback_route(self):
    self.assertEqual(
      audit.derive_analysis_url("https://app.jonathan-harris.online/audits/seo-aeo-geo/callback"),
      "https://app.jonathan-harris.online/audits/seo-aeo-geo/analysis",
    )

  def test_rejects_non_matching_callback_route(self):
    self.assertIsNone(
      audit.derive_analysis_url("https://app.jonathan-harris.online/audits/mobile-ux/callback")
    )

  def test_override_is_respected_for_manual_dispatches(self):
    self.assertEqual(
      audit.derive_analysis_url(
        "https://app.jonathan-harris.online/audits/seo-aeo-geo/callback",
        "https://internal.example/audits/seo-aeo-geo/analysis/",
      ),
      "https://internal.example/audits/seo-aeo-geo/analysis",
    )

  def test_runtime_callback_config_uses_env_fallbacks(self):
    old_url = os.environ.get("APP_URL")
    old_token = os.environ.get("AI_SUITE_AUDIT_CALLBACK_TOKEN")
    try:
      os.environ["APP_URL"] = "https://app.jonathan-harris.online"
      os.environ["AI_SUITE_AUDIT_CALLBACK_TOKEN"] = "token-from-env"
      args = argparse.Namespace(callback_url=None, callback_token=None)
      audit.resolve_runtime_callback_config(args)
      self.assertEqual(args.callback_url, "https://app.jonathan-harris.online/audits/seo-aeo-geo/callback")
      self.assertEqual(args.callback_token, "token-from-env")
    finally:
      if old_url is None:
        os.environ.pop("APP_URL", None)
      else:
        os.environ["APP_URL"] = old_url
      if old_token is None:
        os.environ.pop("AI_SUITE_AUDIT_CALLBACK_TOKEN", None)
      else:
        os.environ["AI_SUITE_AUDIT_CALLBACK_TOKEN"] = old_token

  def test_callback_missing_reason_identifies_exact_field(self):
    self.assertEqual(audit.callback_config_missing_reason(None, "token"), "missing callback_url")
    self.assertEqual(audit.callback_config_missing_reason("https://example.com/callback", None), "missing callback_token")

  def test_safe_detail_masks_tokens(self):
    detail = audit._safe_detail("HTTP 500 Bearer secret-token sk-or-secret-value github_pat_secret")
    self.assertNotIn("secret-token", detail)
    self.assertNotIn("sk-or-secret-value", detail)
    self.assertNotIn("github_pat_secret", detail)
    self.assertIn("Bearer [masked]", detail)

  def test_extract_analysis_from_async_job_response(self):
    analysis = {"executiveSummary": {"overallVerdict": "ok"}}
    payload = {"job": {"result": {"analysis": analysis}}}
    self.assertEqual(audit._extract_analysis_payload(payload), analysis)

  def test_relative_status_url_uses_analysis_endpoint_origin(self):
    self.assertEqual(
      audit._resolve_status_url(
        "https://app.example.com/audits/seo-aeo-geo/analysis",
        "/audits/seo-aeo-geo/analysis/abc123",
      ),
      "https://app.example.com/audits/seo-aeo-geo/analysis/abc123",
    )


if __name__ == "__main__":
  unittest.main()
