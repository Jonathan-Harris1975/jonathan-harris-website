import argparse
import os
import unittest

from scripts.audits import mobile_ux_hard_gate as audit
from scripts.audits.common import resolve_r2_public_base_for_bucket


class MobileUxHardGateTests(unittest.TestCase):
  def test_runtime_callback_config_uses_app_url_fallback(self):
    old_app_url = os.environ.get("APP_URL")
    old_token = os.environ.get("AI_SUITE_AUDIT_CALLBACK_TOKEN")
    try:
      os.environ["APP_URL"] = "https://app.jonathan-harris.online"
      os.environ["AI_SUITE_AUDIT_CALLBACK_TOKEN"] = "token-from-env"
      args = argparse.Namespace(callback_url=None, callback_token=None)
      audit.resolve_runtime_callback_config(args)
      self.assertEqual(args.callback_url, "https://app.jonathan-harris.online/audits/mobile-ux/callback")
      self.assertEqual(args.callback_token, "token-from-env")
    finally:
      if old_app_url is None:
        os.environ.pop("APP_URL", None)
      else:
        os.environ["APP_URL"] = old_app_url
      if old_token is None:
        os.environ.pop("AI_SUITE_AUDIT_CALLBACK_TOKEN", None)
      else:
        os.environ["AI_SUITE_AUDIT_CALLBACK_TOKEN"] = old_token

  def test_missing_playwright_capability_hard_gates_browser_screenshots_and_emulation(self):
    capabilities = audit.build_capabilities("playwright import failed", "failure")
    self.assertFalse(capabilities["renderedBrowserAutomation"])
    self.assertFalse(capabilities["screenshotCapture"])
    self.assertFalse(capabilities["mobileViewportEmulation"])
    self.assertGreaterEqual(len(capabilities["blockedTests"]), 3)

  def test_audits_bucket_public_base_is_preferred_for_audits_bucket(self):
    old_bucket = os.environ.get("R2_BUCKET_AUDITS")
    old_base = os.environ.get("R2_PUBLIC_BASE_URL_AUDITS")
    try:
      os.environ["R2_BUCKET_AUDITS"] = "audits"
      os.environ["R2_PUBLIC_BASE_URL_AUDITS"] = "https://audits.example.test/"
      self.assertEqual(resolve_r2_public_base_for_bucket("audits"), "https://audits.example.test")
    finally:
      if old_bucket is None:
        os.environ.pop("R2_BUCKET_AUDITS", None)
      else:
        os.environ["R2_BUCKET_AUDITS"] = old_bucket
      if old_base is None:
        os.environ.pop("R2_PUBLIC_BASE_URL_AUDITS", None)
      else:
        os.environ["R2_PUBLIC_BASE_URL_AUDITS"] = old_base

  def test_live_404_route_is_not_treated_as_repo_static_404(self):
    self.assertEqual(audit.detect_template_family(audit.LIVE_404_ROUTE), "live-404")
    self.assertIn("__mobile-ux-404-probe__", audit.route_target("https://example.com", audit.LIVE_404_ROUTE, "session-one"))


if __name__ == "__main__":
  unittest.main()
