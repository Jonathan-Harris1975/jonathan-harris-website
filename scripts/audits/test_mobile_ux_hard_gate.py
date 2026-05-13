import argparse
import json
import os
import tempfile
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



  def test_runtime_probe_blocks_when_chromium_launch_fails(self):
    class FailingChromium:
      def launch(self, **_kwargs):
        raise RuntimeError("browser executable missing")

    class FailingPlaywright:
      chromium = FailingChromium()
      def __enter__(self):
        return self
      def __exit__(self, *_args):
        return False

    blocks = audit.probe_rendered_mobile_runtime(lambda: FailingPlaywright(), audit.Path(tempfile.mkdtemp()))
    capabilities = {item["capability"] for item in blocks}
    self.assertIn("renderedBrowserAutomation", capabilities)
    self.assertIn("screenshotCapture", capabilities)
    self.assertIn("mobileViewportEmulation", capabilities)

  def test_build_capabilities_preserves_runtime_probe_blocks(self):
    capabilities = audit.build_capabilities(None, "success", [{"capability": "screenshotCapture", "reason": "probe screenshot failed"}])
    self.assertTrue(capabilities["renderedBrowserAutomation"])
    self.assertFalse(capabilities["screenshotCapture"])
    self.assertTrue(capabilities["mobileViewportEmulation"])
    self.assertEqual(capabilities["blockedTests"][0]["capability"], "screenshotCapture")

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

  def test_failure_payload_writes_complete_diagnostic_artifacts(self):
    old_env = {
      name: os.environ.get(name)
      for name in [
        "R2_ENDPOINT",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_AUDITS",
        "R2_PUBLIC_BASE_URL_AUDITS",
      ]
    }
    for name in old_env:
      os.environ.pop(name, None)

    try:
      with tempfile.TemporaryDirectory() as tmp:
        args = argparse.Namespace(
          session_id="failure-artifact-test",
          report_prefix="audits/mobile-ux/failure-artifact-test",
          callback_url=None,
          callback_token=None,
        )
        output_dir = audit.ensure_dir(audit.Path(tmp))
        payload = audit.write_failure_payload(
          args,
          output_dir,
          "rendered execution failed",
          {"capabilities": audit.build_capabilities()},
          {"error": "browser executable missing"},
        )

        expected = ["summary.json", "coverage.json", "evidence.json", "halt.txt", "report.html"]
        for filename in expected:
          self.assertTrue((output_dir / filename).exists(), filename)

        coverage = json.loads((output_dir / "coverage.json").read_text(encoding="utf-8"))
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["status"], "failed")
        self.assertIn("reportUrl", payload)
        self.assertIn("Mobile UX audit failure report", (output_dir / "report.html").read_text(encoding="utf-8"))
    finally:
      for name, value in old_env.items():
        if value is None:
          os.environ.pop(name, None)
        else:
          os.environ[name] = value


if __name__ == "__main__":
  unittest.main()
